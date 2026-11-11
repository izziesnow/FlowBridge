from django import template

register = template.Library()

STATE_CLASSES = {
    "DRAFT": "text-bg-secondary",
    "IN_REVIEW": "text-bg-primary",
    "CHANGES_REQUESTED": "text-bg-warning",
    "APPROVED": "text-bg-success",
    "REJECTED": "text-bg-danger",
    "CANCELLED": "text-bg-dark",
    "ACTIVE": "text-bg-primary",
    "PENDING": "text-bg-light border",
    "COMPLETED": "text-bg-success",
    "CLOSED": "text-bg-light border",
    "APPROVE": "text-bg-success",
    "REJECT": "text-bg-danger",
    "REQUEST_CHANGES": "text-bg-warning",
    "PUBLISHED": "text-bg-success",
    "CHANGES_REQUESTED_CYCLE": "text-bg-warning",
}


@register.filter
def badge_class(value):
    return STATE_CLASSES.get(str(value), "text-bg-secondary")


@register.filter
def filesize(value):
    size = float(value or 0)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
