from django.core.mail.backends.base import BaseEmailBackend


class FailingBackend(BaseEmailBackend):
    """Test double for an unreachable mail server."""

    def send_messages(self, email_messages):
        raise ConnectionError("SMTP server unreachable")
