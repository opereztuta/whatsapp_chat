import frappe
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
from frappe import _
from frappe.utils import cint
from whatsapp_chat.api.auth import require_contact_access, ROLE_AGENT
from whatsapp_chat.whatsapp_chat.doctype.whatsapp_contact.whatsapp_contact \
        import WhatsAppContact
from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message import WhatsAppMessage  # noqa: E501
from typing import Any, cast
from frappe.utils import now


IMG_FILE_TYPES = {
    "image/apng", "image/avif", "image/gif", "image/jpeg",
    "image/png", "image/svg+xml", "image/webp"}

DOC_FILE_TYPES = {
    "application/pdf", "application/vnd.ms-powerpoint",
    "application/msword", "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ("application/vnd.openxmlformats-officedocument." +
     "presentationml.presentation"),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

AUDIO_FILE_TYPES = {
    "audio/aac",
    "audio/amr",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/opus",
    "audio/webm",
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
UNSUPPORTED_OUTBOUND_AUDIO_TYPES = {"audio/webm"}
MAX_VOICE_NOTE_BYTES = 16 * 1024 * 1024
VOICE_NOTE_TRANSCODE_MIME_TYPES = {"audio/mp4", "audio/opus", "audio/webm"}

mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("audio/amr", ".amr")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/ogg", ".oga")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/opus", ".opus")
mimetypes.add_type("audio/webm", ".webm")
mimetypes.add_type("video/3gpp", ".3gp")


def normalize_mime_type(mime_type: str | None) -> str | None:
    """Return a lower-case MIME value without parameters."""
    if not mime_type:
        return None

    normalized = str(mime_type).split(";", 1)[0].strip().lower()
    if not normalized:
        return None

    return MIME_ALIASES.get(normalized, normalized)


def _extension_from_name(name: str | None) -> str:
    if not name:
        return ""

    path = unquote(urlparse(str(name)).path)
    return PurePosixPath(path).suffix.lower()


def _mime_from_name(name: str | None) -> str | None:
    extension = _extension_from_name(name)
    if extension in EXTENSION_TO_MIME:
        return EXTENSION_TO_MIME[extension]

    guessed = mimetypes.guess_type(name or "")[0]
    return normalize_mime_type(guessed)


def _get_file_record(attachment: str | None) -> dict[str, Any] | None:
    if not attachment:
        return None

    files = frappe.get_all(
        "File",
        filters={"file_url": attachment},
        fields=["name", "file_name", "file_type", "file_url", "is_private"],
        limit=1,
    )
    if not files:
        return None

    return cast(dict[str, Any], files[0])


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
        attachment: str, explicit_mime_type: str | None = None
) -> str | None:
    """Detect a whitelisted media MIME from explicit MIME, File, or URL.

    Client-provided MIME is only accepted when it is in our supported
    whitelist and does not conflict with server-visible file metadata.
    """
    explicit = normalize_mime_type(explicit_mime_type)
    if explicit and explicit not in MIME_TO_CONTENT_TYPE:
        frappe.throw(
            _("Unsupported attachment MIME type: {0}").format(explicit),
            title=_("Unsupported Attachment"),
        )

    file_record = _get_file_record(attachment)
    detected_candidates = [
        _mime_from_file_record(file_record),
        _mime_from_name(attachment),
    ]
    detected_candidates = [
        candidate for candidate in detected_candidates
        if candidate in MIME_TO_CONTENT_TYPE
    ]

    if explicit and detected_candidates:
        explicit_content_type = MIME_TO_CONTENT_TYPE[explicit]
        for candidate in detected_candidates:
            if MIME_TO_CONTENT_TYPE[candidate] != explicit_content_type:
                frappe.throw(
                    _(
                        "Attachment MIME type {0} does not match the "
                        "uploaded file."
                    ).format(explicit),
                    title=_("Unsupported Attachment"),
                )

    if explicit:
        return explicit

    return detected_candidates[0] if detected_candidates else None


def detect_content_type(
        attachment: str, explicit_mime_type: str | None = None) -> str:
    """Return the WhatsApp content type for a supported attachment."""
    mime_type = detect_media_mime_type(attachment, explicit_mime_type)
    return MIME_TO_CONTENT_TYPE.get(mime_type or "", "text")


def _resolve_attachment_content_type(
        attachment: str,
        explicit_mime_type: str | None = None,
        explicit_content_type: str | None = None,
) -> tuple[str, str | None]:
    mime_type = detect_media_mime_type(attachment, explicit_mime_type)
    content_type = MIME_TO_CONTENT_TYPE.get(mime_type or "")

    if not content_type:
        frappe.throw(
            _("Unsupported attachment type. Please upload an image, audio, "
              "video, PDF, or Office document."),
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


def _ensure_supported_outbound_media(
        *, content_type: str, mime_type: str | None) -> None:
    if content_type == "audio" and mime_type in UNSUPPORTED_OUTBOUND_AUDIO_TYPES:
        frappe.throw(
            _("WhatsApp does not support sending WebM audio directly. "
              "Record in Ogg/Opus or MP4 audio, or enable ffmpeg so voice "
              "notes can be converted before sending."),
            title=_("Unsupported Voice Note Format"),
        )


def _set_if_has_field(doc, fieldname: str, value: Any) -> None:
    if doc.meta.has_field(fieldname):
        doc.set(fieldname, value)


def _get_file_doc_for_attachment(attachment: str):
    file_record = _get_file_record(attachment)
    if not file_record:
        return None

    return frappe.get_doc("File", file_record["name"])


def _get_local_file_path(file_doc) -> str:
    file_path = str(file_doc.get_full_path())
    if file_path.startswith(("http://", "https://")):
        frappe.throw(
            _("Remote voice note files cannot be converted before sending."),
            title=_("Unsupported Voice Note Format"),
        )
    return file_path


def _get_voice_note_audio_metadata(file_doc) -> dict[str, str]:
    """Probe uploaded audio so browser MIME labels are not blindly trusted."""
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return {}

    file_path = _get_local_file_path(file_doc)
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-of",
        "json",
        "-show_format",
        "-show_streams",
        file_path,
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
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "WhatsApp voice note ffprobe failed",
        )
        return {}

    streams = payload.get("streams") or []
    audio_stream = next(
        (
            stream for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        {},
    )
    format_payload = payload.get("format") or {}

    metadata = {
        "codec_name": str(audio_stream.get("codec_name") or "").lower(),
        "format_name": str(format_payload.get("format_name") or "").lower(),
    }
    return {key: value for key, value in metadata.items() if value}


def _requires_voice_note_transcode(
        mime_type: str | None,
        metadata: dict[str, str] | None = None,
) -> bool:
    """Return True when the recorded audio should be normalized to Ogg/Opus."""
    metadata = metadata or {}
    codec_name = metadata.get("codec_name")
    format_name = metadata.get("format_name", "")

    if mime_type == "audio/ogg":
        return bool(codec_name and codec_name != "opus")

    if mime_type == "audio/mp4":
        # Browser MediaRecorder can produce MP4 containers with Opus tracks.
        # Meta rejects those even when the MIME is audio/mp4. M4A/AAC is safe.
        return codec_name != "aac"

    if mime_type in VOICE_NOTE_TRANSCODE_MIME_TYPES:
        return True

    if codec_name == "opus" and "ogg" not in format_name:
        return True

    return False


def _transcode_voice_note_to_ogg(*, room: str, attachment: str) -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        frappe.throw(
            _("Your browser recorded WebM audio, which WhatsApp cannot send "
              "directly. Ask an administrator to install ffmpeg on the "
              "server, or use a browser that records Ogg/Opus or MP4 audio."),
            title=_("Unsupported Voice Note Format"),
        )

    file_doc = _get_file_doc_for_attachment(attachment)
    if not file_doc:
        frappe.throw(
            _("Could not find the uploaded voice note file."),
            title=_("Voice Note Upload Failed"),
        )

    input_path = _get_local_file_path(file_doc)
    file_size = os.path.getsize(input_path)
    if file_size > MAX_VOICE_NOTE_BYTES:
        frappe.throw(
            _("Voice notes must be 16 MB or smaller."),
            title=_("Voice Note Too Large"),
        )

    with tempfile.TemporaryDirectory(prefix="whatsapp-voice-") as temp_dir:
        output_path = os.path.join(temp_dir, "voice-note.ogg")
        # WhatsApp voice notes must be Ogg/Opus, mono, 48 kHz.
        # -application voip biases the encoder toward speech.
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
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "WhatsApp voice note ffmpeg conversion failed",
            )
            frappe.throw(
                _("Could not convert this WebM recording into a WhatsApp "
                  "audio message. Please try another browser or contact an "
                  "administrator."),
                title=_("Voice Note Conversion Failed"),
            )

        with open(output_path, "rb") as converted_file:
            converted_content = converted_file.read()

    if len(converted_content) > MAX_VOICE_NOTE_BYTES:
        frappe.throw(
            _("Converted voice note is larger than WhatsApp's 16 MB limit."),
            title=_("Voice Note Too Large"),
        )

    from frappe.core.doctype.file.file import File

    converted_doc = cast(File, frappe.get_doc({
        "doctype": "File",
        "file_name": f"voice-note-{frappe.generate_hash(length=10)}.ogg",
        "attached_to_doctype": "WhatsApp Contact",
        "attached_to_name": room,
        "content": converted_content,
        "is_private": cint(file_doc.get("is_private")),
    }))
    converted_doc.save(ignore_permissions=True)
    return str(converted_doc.file_url)


def _prepare_voice_note_attachment(
        *, room: str, attachment: str, mime_type: str | None
) -> tuple[str, str | None]:
    content_type, detected_mime_type = _resolve_attachment_content_type(
        attachment=attachment,
        explicit_mime_type=mime_type,
        explicit_content_type="audio",
    )
    if content_type != "audio":
        frappe.throw(
            _("Voice notes must be audio files."),
            title=_("Unsupported Voice Note Format"),
        )

    file_doc = _get_file_doc_for_attachment(attachment)
    if not file_doc:
        frappe.throw(
            _("Could not find the uploaded voice note file."),
            title=_("Voice Note Upload Failed"),
        )

    # Always re-encode PTT audio to a strict Ogg/Opus profile.
    # WhatsApp (especially Apple clients) shows "This audio is no longer
    # available" when the file is even slightly off-spec — passing through
    # the browser's recording is not safe even when ffprobe says it's
    # already Ogg/Opus, because preskip, channel mapping, or bitrate may
    # differ from what the recipient client expects.
    attachment = _transcode_voice_note_to_ogg(
        room=room,
        attachment=attachment,
    )
    detected_mime_type = "audio/ogg; codecs=opus"

    return attachment, detected_mime_type


def _media_preview(content_type: str, is_voice_note: bool = False) -> str:
    if content_type == "audio":
        return _("Voice note")
    labels = {
        "image": _("Image"),
        "document": _("Document"),
        "video": _("Video"),
        "sticker": _("Sticker"),
    }
    return labels.get(content_type, "")


def _message_preview(doc) -> str:
    content_type = (doc.content_type or "text").lower()
    message = doc.message or ""
    if content_type == "text":
        return message

    return message or _media_preview(
        content_type,
        is_voice_note=bool(doc.get("is_voice_note")),
    )


@frappe.whitelist()
def get_all(room: str):
    """Get all messages for a room (WhatsApp Contact name)."""
    require_contact_access(room)

    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))

    user_no = contact.mobile_no  # authoritative

    is_voice_note_select = (
        "COALESCE(is_voice_note, 0) as is_voice_note"
        if frappe.get_meta("WhatsApp Message").has_field("is_voice_note")
        else "0 as is_voice_note"
    )

    messages = frappe.db.sql(f"""
        SELECT creation,
        case
          when `to` <> '' then `to`
          else
          'Administrator'
        end as sender_user_no,
        case
          when COALESCE(content_type,'text') = 'text' then COALESCE(message,'')
          else COALESCE(attach, message, '')
        end as content,
        case
          when COALESCE(content_type, 'text') <> 'text'
            and COALESCE(message, '') <> ''
            and COALESCE(message, '') <> COALESCE(attach, '')
            then message
          else NULL
        end as caption,
        COALESCE(content_type, 'text') as content_type,
        {is_voice_note_select}
        from `tabWhatsApp Message`
        where (`to` = %(user_no)s or `from` = %(user_no)s)
          AND COALESCE(message_type, '') <> 'Template'
        order by creation asc
    """, {"user_no": user_no}, as_dict=True)

    for message in messages:
        if message.get("content_type") != "text":
            attachment = message.get("content")
            message["attachment_mime_type"] = (
                detect_media_mime_type(attachment)
                if attachment else None
            )

    return messages


@frappe.whitelist()
def mark_as_read(room: str):
    require_contact_access(room)
    frappe.db.set_value(
        "WhatsApp Contact", room, "is_read", 1, update_modified=False)
    frappe.db.commit()
    send_whatsapp_read_receipts(room)
    return "ok"


def send_whatsapp_read_receipts(room):
    """Send read receipts to WhatsApp for unread incoming messages."""
    try:
        # Get the contact's mobile number
        contact = cast(
            WhatsAppContact,
            frappe.get_doc("WhatsApp Contact", room))

        if not contact.mobile_no:
            return

        # Find unread incoming messages for this contact
        unread_messages = frappe.get_all(
            "WhatsApp Message",
            filters={
                "from": contact.mobile_no,
                "type": "Incoming",
                "status": ["not in", ["marked as read"]]
            },
            fields=["name", "whatsapp_account"],
            order_by="creation desc",
            limit=10
        )

        if not unread_messages:
            return

        # Check if auto read receipt is enabled for the account
        for msg in unread_messages:
            if not msg.whatsapp_account:
                continue

            allow_auto_read = frappe.db.get_value(
                "WhatsApp Account",
                msg.whatsapp_account,
                "allow_auto_read_receipt"
            )

            if allow_auto_read:
                try:
                    msg_doc = cast(
                        WhatsAppMessage,
                        frappe.get_doc("WhatsApp Message", msg.name))
                    msg_doc.send_read_receipt()
                except Exception as e:
                    frappe.log_error(
                        ("Failed to send read receipt "
                         f"for {msg.name}: {str(e)}"),
                        "WhatsApp Chat Read Receipt")
    except Exception as e:
        frappe.log_error(
            f"send_whatsapp_read_receipts error: {str(e)}",
            "WhatsApp Chat Read Receipt")


@frappe.whitelist()
def send(
        room: str,
        content: str | None = "",
        attachment: str | None = None,
        mime_type: str | None = None,
        content_type: str | None = None,
):
    """Send a message to the room contact."""
    require_contact_access(room)

    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))
    user_no = contact.mobile_no

    resolved_content_type = "text"
    detected_mime_type = None
    content = content or ""
    if attachment:
        resolved_content_type, detected_mime_type = \
            _resolve_attachment_content_type(
                attachment=attachment,
                explicit_mime_type=mime_type,
                explicit_content_type=content_type,
            )
        _ensure_supported_outbound_media(
            content_type=resolved_content_type,
            mime_type=detected_mime_type,
        )

        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": user_no,
            "type": "Outgoing",
            "attach": attachment,
            "message": content,
            "content_type": resolved_content_type,
        }).insert(ignore_permissions=False)
    else:
        if content_type and str(content_type).strip().lower() != "text":
            frappe.throw(
                _("Content type is only allowed for attachments."),
                title=_("Unsupported Attachment"),
            )
        if not content:
            frappe.throw(_("Message cannot be empty."))

        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": user_no,
            "type": "Outgoing",
            "message": content,
            "content_type": resolved_content_type,
        }).insert(ignore_permissions=False)

    return {
        "content": attachment or content,
        "caption": content if attachment else None,
        "content_type": resolved_content_type,
        "attachment_mime_type": detected_mime_type,
        "is_voice_note": 0,
    }


@frappe.whitelist()
def send_voice_note(
        room: str, attachment: str, mime_type: str | None = None):
    """Send a recorded WhatsApp voice note to the room contact."""
    require_contact_access(room)

    if not attachment:
        frappe.throw(_("Voice note attachment is required."))

    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))
    attachment, detected_mime_type = _prepare_voice_note_attachment(
        room=room,
        attachment=attachment,
        mime_type=mime_type,
    )

    doc = frappe.get_doc({
        "doctype": "WhatsApp Message",
        "to": contact.mobile_no,
        "type": "Outgoing",
        "attach": attachment,
        "message": "",
        "content_type": "audio",
    })
    _set_if_has_field(doc, "is_voice_note", 1)
    doc.insert(ignore_permissions=False)

    return {
        "content": attachment,
        "caption": None,
        "content_type": "audio",
        "attachment_mime_type": detected_mime_type,
        "is_voice_note": 1,
    }


def last_message(doc, method):
    if doc.type == 'Outgoing':
        mobile_no = doc.to
    else:
        mobile_no = doc.get("from")
    preview = _message_preview(doc)

    contact_name = frappe.db.get_value(
        "WhatsApp Contact", filters={"mobile_no": mobile_no})
    if contact_name:
        # Use set_value to avoid TimestampMismatchError from concurrent updates
        frappe.db.set_value(
            "WhatsApp Contact",
            contact_name,
            {"last_message": preview, "is_read": 0},
            update_modified=True
        )
        # Get fresh contact data for realtime publishing
        chat_doc = cast(
            WhatsAppContact,
            frappe.get_doc("WhatsApp Contact", str(contact_name))
        )
    else:
        chat_doc = cast(
            WhatsAppContact,
            frappe.get_doc({
                "doctype": "WhatsApp Contact",
                "mobile_no": mobile_no,
                "last_message": preview,
                "contact_name": mobile_no,
                "is_read": 0
            }))
        chat_doc.insert(ignore_permissions=True)

    # Only publish realtime for incoming messages
    if doc.type == 'Outgoing':
        return "ok"

    # Determine content and caption based on content_type
    content_type = doc.content_type or 'text'
    if content_type == 'text':
        content = doc.message or ''
        caption = None
    else:
        content = doc.attach or doc.message or ''
        caption = (
            doc.message
            if doc.attach and (doc.message or "") != (doc.attach or "")
            else None
        )

    message_data = {
        "content": content,
        "creation": now(),
        "room": chat_doc.name,
        "contact_name": chat_doc.contact_name,
        "sender_user_no": mobile_no,
        "user": "Guest",
        "content_type": content_type,
        "caption": caption,
        "preview": preview,
    }
    if doc.meta.has_field("is_voice_note"):
        message_data["is_voice_note"] = cint(doc.get("is_voice_note"))
    if content_type != "text" and content:
        message_data["attachment_mime_type"] = detect_media_mime_type(content)

    # Determine which users should receive the realtime update
    target_users = set()

    # Always include System Managers (e.g., Administrator)
    system_managers = frappe.get_all(
        "Has Role",
        filters={"role": "System Manager", "parenttype": "User"},
        pluck="parent"
    )
    target_users.update(system_managers)

    if chat_doc.email:
        # Contact is assigned to a specific agent
        target_users.add(chat_doc.email)
    else:
        # Shared inbox: notify all WhatsApp Chat Agents
        agents = frappe.get_all(
            "Has Role",
            filters={"role": ROLE_AGENT, "parenttype": "User"},
            pluck="parent"
        )
        target_users.update(agents)

    # Publish to all target users
    for user in target_users:
        # Notify chat list
        frappe.publish_realtime(
            "latest_chat_updates",
            message_data,
            user=user
        )
        # Notify open chat room
        frappe.publish_realtime(
            chat_doc.name,
            message_data,
            user=user
        )

    return "ok"
