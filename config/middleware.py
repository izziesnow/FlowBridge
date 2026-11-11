"""Middleware used when Flowbridge runs without its Nginx proxy, for example on a hosting platform."""
from django.conf import settings
from django.db import connection
from django.http import HttpResponse

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"


class HealthCheckMiddleware:
    """Answer /healthz before host and HTTPS checks, so a platform's internal probe always reaches it.

    The response only says whether the app can reach its database; it reveals nothing else.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz":
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Send the headers Nginx adds in the Docker Compose stack (Section 4.3.3) when there is no Nginx.

    Switched on with SECURITY_HEADERS_IN_APP, so the Compose stack does not send them twice.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.SECURITY_HEADERS_IN_APP:
            response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response
