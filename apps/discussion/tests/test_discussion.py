"""Request comments and project discussion (FR09)."""
import pytest
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from apps.approvals.models import Decision
from apps.approvals.services import WorkflowService
from apps.audit.models import AuditEvent
from apps.core_immutable import ImmutableRecordError
from apps.discussion.models import Comment, ProjectMessage
from apps.discussion.services import DiscussionError, post_comment, post_project_message
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_comment_is_linked_to_the_revision_under_discussion(submitted, people):
    comment = post_comment(submitted, people["approver1"], "Which rollback steps apply?")
    assert comment.revision == submitted.current_revision
    WorkflowService.decide(submitted, people["approver1"], Decision.Outcome.REQUEST_CHANGES, "Add rollback")
    WorkflowService.update_content(submitted, people["requester"], submitted.title, "Now with rollback")
    WorkflowService.resubmit(submitted, people["requester"])
    submitted.refresh_from_db()
    later = post_comment(submitted, people["requester"], "Rollback added in revision 2.")
    assert (comment.revision.number, later.revision.number) == (1, 2)


def test_draft_comments_have_no_revision(draft, people):
    assert post_comment(draft, people["requester"], "Note to self").revision is None


def test_comment_notifies_requester_and_current_approver(submitted, people):
    post_comment(submitted, people["pm"], "Please prioritise this one.")
    for key in ("requester", "approver1"):
        assert Notification.objects.filter(recipient=people[key], kind=Notification.Kind.COMMENT).exists()
    assert not Notification.objects.filter(recipient=people["pm"], kind=Notification.Kind.COMMENT).exists()
    assert AuditEvent.objects.filter(request=submitted, action="comment.added").exists()


def test_viewers_and_outsiders_cannot_comment(submitted, people, client_for):
    with pytest.raises(PermissionDenied):
        post_comment(submitted, people["viewer"], "Hello")
    url = reverse("discussion:comment_create", args=["PAY", submitted.number])
    assert client_for(people["outsider"]).post(url, {"body": "Hi"}).status_code == 404


def test_empty_comment_is_refused(submitted, people):
    with pytest.raises(DiscussionError):
        post_comment(submitted, people["requester"], "   ")


def test_comments_and_messages_cannot_be_changed(submitted, people, project):
    comment = post_comment(submitted, people["requester"], "Original")
    comment.body = "Edited"
    with pytest.raises(ImmutableRecordError):
        comment.save()
    post_project_message(project, people["pm"], "Freeze on Friday")
    for model in (Comment, ProjectMessage):
        with pytest.raises(DatabaseError, match="immutable"):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(f"UPDATE {model._meta.db_table} SET body = 'tampered'")


def test_project_discussion_page_posts_and_notifies_members(project, people, client_for):
    url = reverse("discussion:project", args=["PAY"])
    client_for(people["pm"]).post(url, {"body": "Release freeze starts Friday."})
    page = client_for(people["viewer"]).get(url)
    assert b"Release freeze starts Friday." in page.content and b"New message" not in page.content
    assert Notification.objects.filter(recipient=people["viewer"], kind=Notification.Kind.DISCUSSION).exists()
    assert client_for(people["outsider"]).get(url).status_code == 404


def test_comment_appears_on_the_request_page(submitted, people, client_for):
    client = client_for(people["approver1"])
    client.post(reverse("discussion:comment_create", args=["PAY", submitted.number]), {"body": "Looks fine so far."})
    page = client.get(submitted.get_absolute_url())
    assert b"Looks fine so far." in page.content and b"on revision 1" in page.content
