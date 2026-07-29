from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath
from typing import Any, cast
from urllib.parse import unquote, urlparse

import frappe
from frappe import _

IMG_FILE_TYPES = {
    "image/apng", "image/avif", "image/gif", "image/jpeg",
    "image/png", "image/svg+xml", "image/webp"}

DOC_FILE_TYPES = {
    "application/pdf", "application/vnd.ms-powerpoint",
    "application/msword", "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ("application/vnd.openxmlformats-officedocument." +
     "presentationml.presentation"),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

AUDIO_FILE_TYPES = {
    "audio/aac", "audio/amr", "audio/mp4", "audio/mpeg",
    "audio/ogg", "audio/opus", "audio/webm",
}

VIDEO_FILE_TYPES = {"video/mp4", "video/3gpp", "video/3gp"}

MIME_ALIASES = {
    "audio/mp3": "audio/mpeg",
    "audio/x-m4a": "audio/mp4",
    "audio/x-aac": "audio/aac",
    "audio/x-mpeg": "audio/mpeg",
    "video/3gp": "video/3gpp",
}

EXTENSION_TO_MIME = {
    ".aac": "audio/aac",
    ".amr": "audio/amr",
    ".apng": "image/apng",
    ".avif": "image/avif",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": (
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation"
    ),
    ".svg": "image/svg+xml",
    ".webm": "audio/webm",
    ".webp": "image/webp",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    ".3gp": "video/3gpp",
}

MIME_TO_CONTENT_TYPE = {
    **{mime_type: "image" for mime_type in IMG_FILE_TYPES},
    **{mime_type: "document" for mime_type in DOC_FILE_TYPES},
    **{mime_type: "audio" for mime_type in AUDIO_FILE_TYPES},
    **{mime_type: "video" for mime_type in VIDEO_FILE_TYPES},
}

ALLOWED_MEDIA_CONTENT_TYPES = {"image", "document", "audio", "video"}

for mime_type, extension in (
    ("audio/aac", ".aac"),
    ("audio/amr", ".amr"),
    ("audio/mp4", ".m4a"),
    ("audio/ogg", ".ogg"),
    ("audio/opus", ".opus"),
    ("audio/webm", ".webm"),
    ("video/3gpp", ".3gp"),
):
    mimetypes.add_type(mime_type, extension)


def normalize_mime_type(mime_type: str | None) -> str | None:
    if not mime_type:
        return None
    normalized = str(mime_type).split(";", 1)[0].strip().lower()
    return MIME_ALIASES.get(normalized, normalized) if normalized else None


def _extension_from_name(name: str | None) -> str:
    if not name:
        return ""
    path = unquote(urlparse(str(name)).path)
    return PurePosixPath(path).suffix.lower()


def _mime_from_name(name: str | None) -> str | None:
    extension = _extension_from_name(name)
    if extension in EXTENSION_TO_MIME:
        return EXTENSION_TO_MIME[extension]
    return normalize_mime_type(mimetypes.guess_type(name or "")[0])


def get_file_record(attachment: str | None) -> dict[str, Any] | None:
    if not attachment:
        return None
    files = frappe.get_all(
        "File",
        filters={"file_url": attachment},
        fields=[
            "name", "file_name", "file_type", "file_url", "is_private",
            "file_size", "attached_to_doctype", "attached_to_name",
        ],
        order_by="creation desc",
        limit=1,
    )
    return cast(dict[str, Any], files[0]) if files else None


def _mime_from_file_record(file_record: dict[str, Any] | None) -> str | None:
    if not file_record:
        return None
    mime_type = _mime_from_name(cast(str | None, file_record.get("file_name")))
    if mime_type:
        return mime_type
    file_type = file_record.get("file_type")
    if not file_type:
        return None
    normalized = normalize_mime_type(str(file_type))
    if normalized and "/" in normalized:
        return normalized
    return EXTENSION_TO_MIME.get(f".{str(file_type).lower().lstrip('.')}")


def detect_media_mime_type(
    attachment: str,
    explicit_mime_type: str | None = None,
) -> str | None:
    """Detect a supported MIME using explicit, File, and URL metadata."""
    explicit = normalize_mime_type(explicit_mime_type)
    if explicit and explicit not in MIME_TO_CONTENT_TYPE:
        frappe.throw(
            _("Unsupported attachment MIME type: {0}").format(explicit),
            title=_("Unsupported Attachment"),
        )

    file_record = get_file_record(attachment)
    detected = [
        candidate
        for candidate in (
            _mime_from_file_record(file_record),
            _mime_from_name(attachment),
        )
        if candidate in MIME_TO_CONTENT_TYPE
    ]
    if explicit and detected:
        expected = MIME_TO_CONTENT_TYPE[explicit]
        if any(MIME_TO_CONTENT_TYPE[item] != expected for item in detected):
            frappe.throw(
                _("Attachment MIME type {0} does not match the uploaded file.").format(
                    explicit
                ),
                title=_("Unsupported Attachment"),
            )
    return explicit or (detected[0] if detected else None)


def detect_content_type(
    attachment: str,
    explicit_mime_type: str | None = None,
) -> str:
    mime_type = detect_media_mime_type(attachment, explicit_mime_type)
    return MIME_TO_CONTENT_TYPE.get(mime_type or "", "text")


def resolve_attachment_content_type(
    attachment: str,
    explicit_mime_type: str | None = None,
    explicit_content_type: str | None = None,
) -> tuple[str, str | None]:
    mime_type = detect_media_mime_type(attachment, explicit_mime_type)
    content_type = MIME_TO_CONTENT_TYPE.get(mime_type or "")
    if not content_type:
        frappe.throw(
            _("Unsupported attachment type. Please upload an image, audio, "
              "video, PDF, Office document, or text file."),
            title=_("Unsupported Attachment"),
        )
    if explicit_content_type:
        requested = str(explicit_content_type).strip().lower()
        if requested not in ALLOWED_MEDIA_CONTENT_TYPES:
            frappe.throw(
                _("Unsupported content type: {0}").format(requested),
                title=_("Unsupported Attachment"),
            )
        if requested != content_type:
            frappe.throw(
                _("Attachment content type does not match the uploaded file."),
                title=_("Unsupported Attachment"),
            )
    return content_type, mime_type
