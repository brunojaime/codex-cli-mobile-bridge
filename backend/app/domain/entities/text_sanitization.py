from __future__ import annotations

_MISSING_IMAGE_ATTACHMENT_MARKERS = (
    "could not read the local image",
    "failed to read image at",
    "codex-remote-retry-assets",
)
_MISSING_IMAGE_ATTACHMENT_MESSAGE = (
    "The original image attachment is no longer available on this server. "
    "Reattach it to continue."
)


def sanitize_image_attachment_error_text(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in _MISSING_IMAGE_ATTACHMENT_MARKERS):
        return _MISSING_IMAGE_ATTACHMENT_MESSAGE
    return value
