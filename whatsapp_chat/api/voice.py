from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, cast

import frappe
from frappe import _
from frappe.core.doctype.file.file import File
from frappe.utils import cint

from whatsapp_chat.api.media import get_file_record


VOICE_NOTE_MIME_TYPE = "audio/ogg"
VOICE_NOTE_MIME_WITH_CODEC = "audio/ogg; codecs=opus"


def get_file_doc_for_attachment(attachment: str) -> File | None:
    file_record = get_file_record(attachment)
    if not file_record:
        return None
    return cast(File, frappe.get_doc("File", file_record["name"]))


def get_local_file_path(file_doc: File) -> str:
    file_path = str(file_doc.get_full_path())
    if file_path.startswith(("http://", "https://")):
        frappe.throw(
            _("Remote voice note files cannot be converted before sending."),
            title=_("Unsupported Voice Note Format"),
        )
    return file_path


def probe_voice_note(file_doc: File, *, log_prefix: str) -> dict[str, Any]:
    """Return authoritative stream/container metadata for an uploaded recording."""
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        frappe.throw(
            _("Voice recording requires ffprobe on the application server."),
            title=_("Voice Recording Unavailable"),
        )

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-of",
        "json",
        "-show_format",
        "-show_streams",
        get_local_file_path(file_doc),
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        payload = json.loads(result.stdout.decode("utf-8") or "{}")
    except Exception as exc:
        stderr = getattr(exc, "stderr", b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        frappe.log_error(
            title=f"{log_prefix}: ffprobe failed",
            message=f"{frappe.get_traceback()}\n\n{str(stderr)[:4000]}",
        )
        frappe.throw(
            _("The uploaded recording is not a valid audio file."),
            title=_("Invalid Voice Note"),
        )

    streams = [
        stream
        for stream in payload.get("streams") or []
        if isinstance(stream, dict)
    ]
    audio_streams = [
        stream for stream in streams if stream.get("codec_type") == "audio"
    ]
    video_streams = [
        stream for stream in streams if stream.get("codec_type") == "video"
    ]
    if not audio_streams or video_streams:
        frappe.throw(
            _("Voice notes must contain audio only."),
            title=_("Invalid Voice Note"),
        )

    audio = audio_streams[0]
    format_payload = payload.get("format") or {}
    try:
        duration = float(format_payload.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    return {
        "codec_name": str(audio.get("codec_name") or "").lower(),
        "format_name": str(format_payload.get("format_name") or "").lower(),
        "sample_rate": str(audio.get("sample_rate") or ""),
        "channels": cint(audio.get("channels")),
        "duration": duration,
    }


def normalize_voice_note_to_ogg(
    *,
    attachment: str,
    attached_to_doctype: str,
    attached_to_name: str,
    max_bytes: int,
    log_prefix: str,
) -> File:
    """Validate and normalize browser audio to a strict Ogg/Opus voice profile."""
    file_doc = get_file_doc_for_attachment(attachment)
    if not file_doc:
        frappe.throw(
            _("Could not find the uploaded voice note file."),
            title=_("Voice Note Upload Failed"),
        )
    if (
        file_doc.attached_to_doctype != attached_to_doctype
        or file_doc.attached_to_name != attached_to_name
    ):
        raise frappe.PermissionError(
            _("This voice note does not belong to the conversation.")
        )

    input_path = get_local_file_path(file_doc)
    file_size = os.path.getsize(input_path)
    if file_size <= 0:
        frappe.throw(
            _("The recorded voice note is empty."),
            title=_("Empty Voice Note"),
        )
    if file_size > max_bytes:
        frappe.throw(
            _("Voice note exceeds the maximum allowed file size."),
            title=_("Voice Note Too Large"),
        )

    probe_voice_note(file_doc, log_prefix=log_prefix)

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        frappe.throw(
            _("Voice recording requires ffmpeg on the application server."),
            title=_("Voice Recording Unavailable"),
        )

    with tempfile.TemporaryDirectory(prefix="voice-note-") as temp_dir:
        output_path = os.path.join(temp_dir, "voice-note.ogg")
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-vn",
            "-map_metadata",
            "-1",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            "-application",
            "voip",
            "-f",
            "ogg",
            output_path,
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except Exception as exc:
            stderr = getattr(exc, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            frappe.log_error(
                title=f"{log_prefix}: ffmpeg conversion failed",
                message=f"{frappe.get_traceback()}\n\n{str(stderr)[:4000]}",
            )
            frappe.throw(
                _("Could not prepare this recording for delivery. Please try again."),
                title=_("Voice Note Conversion Failed"),
            )

        with open(output_path, "rb") as converted_file:
            converted_content = converted_file.read()

    if not converted_content:
        frappe.throw(
            _("Voice note conversion produced an empty file."),
            title=_("Voice Note Conversion Failed"),
        )
    if len(converted_content) > max_bytes:
        frappe.throw(
            _("Converted voice note exceeds the maximum allowed file size."),
            title=_("Voice Note Too Large"),
        )

    normalized = cast(
        File,
        frappe.get_doc(
            {
                "doctype": "File",
                "file_name": f"voice-note-{frappe.generate_hash(length=10)}.ogg",
                "attached_to_doctype": attached_to_doctype,
                "attached_to_name": attached_to_name,
                "content": converted_content,
                "is_private": cint(file_doc.is_private),
            }
        ),
    )
    normalized.save(ignore_permissions=True)
    return normalized
