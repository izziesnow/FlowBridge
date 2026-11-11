"""Private document storage.

Files are written under ``settings.PRIVATE_MEDIA_ROOT``, which is outside the
web root and has no public URL. The only way to read a file is through the
permission-checked download view.
"""
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """File storage rooted at PRIVATE_MEDIA_ROOT, read at call time (so tests can override it)."""

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):  # pragma: no cover - deliberately unsupported
        raise NotImplementedError("Private documents have no public URL. Use the download view.")


_storage = PrivateStorage()


def private_storage():
    """Callable used by the FileField, so migrations store a reference rather than a path."""
    return _storage


def document_upload_to(instance, filename):
    """Store under a random name so user-supplied file names never become paths."""
    request = instance.document.request
    suffix = Path(filename).suffix.lower()[:10]
    return f"{request.project.code}/{request.number:05d}/{uuid.uuid4().hex}{suffix}"
