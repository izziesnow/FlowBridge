import pytest
from django.db import IntegrityError
from django.urls import reverse

from apps.accounts.models import User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_email_is_case_insensitive_and_unique():
    user = User.objects.create_user("Ada.Obi@ZTL.example", PASSWORD, full_name="Ada Obi")
    assert user.email == "ada.obi@ztl.example"
    with pytest.raises(IntegrityError):
        User.objects.create_user("ADA.OBI@ztl.example", PASSWORD, full_name="Duplicate")


def test_passwords_are_stored_as_salted_hashes():
    user = User.objects.create_user("hash@ztl.example", PASSWORD, full_name="Hash Test")
    assert user.password.startswith(("pbkdf2_sha256$", "argon2", "scrypt")) and PASSWORD not in user.password


def test_sign_in_with_email(client):
    User.objects.create_user("signin@ztl.example", PASSWORD, full_name="Sign In")
    response = client.post(reverse("accounts:login"), {"username": "SignIn@ztl.example", "password": PASSWORD})
    assert response.status_code == 302 and response.url == reverse("dashboard")


def test_wrong_password_is_refused(client):
    User.objects.create_user("deny@ztl.example", PASSWORD, full_name="Deny")
    response = client.post(reverse("accounts:login"), {"username": "deny@ztl.example", "password": "wrong"})
    assert response.status_code == 200 and "_auth_user_id" not in client.session
