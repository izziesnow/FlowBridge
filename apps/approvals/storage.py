"""Private document storage.

By default, files are written under ``settings.PRIVATE_MEDIA_ROOT``, which is
outside the web root and has no public URL. The only way to read a file is
through the permission-checked download view.

Hosting platforms with an ephemeral filesystem (such as a free Render web
service) lose local files whenever the service restarts. Setting
``DOCUMENT_STORAGE=database`` keeps the file contents in PostgreSQL instead.
Either way, documents have no public URL and their SHA-256 checksums are
re-verified on every download.
"""
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage


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


class DatabaseStorage(Storage):
    """Keeps file contents in the StoredFile table, for hosts whose local disk does not persist."""

    @staticmethod
    def _model():
        from .models import StoredFile  # imported late: models.py imports this module
        return StoredFile

    def _open(self, name, mode="rb"):
        row = self._model().objects.filter(name=name).only("content").first()
        if row is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(row.content), name=name)

    def _save(self, name, content):
        if hasattr(content, "seek"):
            content.seek(0)
        data = b"".join(content.chunks()) if hasattr(content, "chunks") else content.read()
        self._model().objects.create(name=name, content=data, size=len(data))
        return name

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def size(self, name):
        row = self._model().objects.filter(name=name).only("size").first()
        if row is None:
            raise FileNotFoundError(name)
        return row.size

    def url(self, name):  # pragma: no cover - deliberately unsupported
        raise NotImplementedError("Private documents have no public URL. Use the download view.")


class ConfiguredStorage(Storage):
    """Sends each call to the backend chosen by settings.DOCUMENT_STORAGE, read at call time."""

    _filesystem = PrivateStorage()
    _database = DatabaseStorage()

    def _backend(self):
        return self._database if settings.DOCUMENT_STORAGE == "database" else self._filesystem

    def _open(self, name, mode="rb"):
        return self._backend()._open(name, mode)

    def _save(self, name, content):
        return self._backend()._save(name, content)

    def exists(self, name):
        return self._backend().exists(name)

    def delete(self, name):
        return self._backend().delete(name)

    def size(self, name):
        return self._backend().size(name)

    def path(self, name):
        return self._backend().path(name)

    def url(self, name):  # pragma: no cover - deliberately unsupported
        raise NotImplementedError("Private documents have no public URL. Use the download view.")


_storage = ConfiguredStorage()


def private_storage():
    """Callable used by the FileField, so migrations store a reference rather than a path."""
    return _storage


def document_upload_to(instance, filename):
    """Store under a random name so user-supplied file names never become paths."""
    request = instance.document.request
    suffix = Path(filename).suffix.lower()[:10]
    return f"{request.project.code}/{request.number:05d}/{uuid.uuid4().hex}{suffix}"
