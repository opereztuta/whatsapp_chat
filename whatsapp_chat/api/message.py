import frappe
from frappe import _
from frappe.utils import cint
from whatsapp_chat.api.auth import require_contact_access, ROLE_AGENT
from whatsapp_chat.whatsapp_chat.doctype.whatsapp_contact.whatsapp_contact \
        import WhatsAppContact
from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message import WhatsAppMessage  # noqa: E501
from typing import Any, cast
from frappe.utils import now
from whatsapp_chat.api.media import (
    detect_content_type,
    detect_media_mime_type,
    resolve_attachment_content_type,
)
from whatsapp_chat.api.voice import (
    VOICE_NOTE_MIME_WITH_CODEC,
    get_file_doc_for_attachment,
    normalize_voice_note_to_ogg,
)


UNSUPPORTED_OUTBOUND_AUDIO_TYPES = {"audio/webm"}
MAX_VOICE_NOTE_BYTES = 16 * 1024 * 1024
VOICE_NOTE_TRANSCODE_MIME_TYPES = {"audio/mp4", "audio/opus", "audio/webm"}


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


def _contact_value(contact: Any, fieldname: str) -> Any:
    getter = getattr(contact, "get", None)
    if callable(getter):
        return getter(fieldname)
    return getattr(contact, fieldname, None)


def _calling_identity_kwargs(contact: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "phone_number": _contact_value(contact, "mobile_no"),
    }
    recipient = (
        _contact_value(contact, "user_id")
        or _contact_value(contact, "parent_user_id")
    )
    optional = {
        "recipient": recipient,
        "contact_profile": _contact_value(contact, "whatsapp_profile"),
        "whatsapp_account": _contact_value(contact, "whatsapp_account"),
    }
    kwargs.update({key: value for key, value in optional.items() if value})
    return kwargs


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
    converted_doc = normalize_voice_note_to_ogg(
        attachment=attachment,
        attached_to_doctype="WhatsApp Contact",
        attached_to_name=room,
        max_bytes=MAX_VOICE_NOTE_BYTES,
        log_prefix="WhatsApp voice note",
    )
    return str(converted_doc.file_url)


def _prepare_voice_note_attachment(
        *, room: str, attachment: str, mime_type: str | None
) -> tuple[str, str | None]:
    content_type, detected_mime_type = resolve_attachment_content_type(
        attachment=attachment,
        explicit_mime_type=mime_type,
        explicit_content_type="audio",
    )
    if content_type != "audio":
        frappe.throw(
            _("Voice notes must be audio files."),
            title=_("Unsupported Voice Note Format"),
        )

    file_doc = get_file_doc_for_attachment(attachment)
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
    detected_mime_type = VOICE_NOTE_MIME_WITH_CODEC

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

    user_no = contact.mobile_no

    is_voice_note_select = (
        "COALESCE(is_voice_note, 0) as is_voice_note"
        if frappe.get_meta("WhatsApp Message").has_field("is_voice_note")
        else "0 as is_voice_note"
    )

    identity_filter = (
        "contact_profile = %(profile)s"
        if contact.get("whatsapp_profile")
        else "(`to` = %(user_no)s or `from` = %(user_no)s)"
    )
    account_filter = (
        "AND whatsapp_account = %(whatsapp_account)s"
        if contact.get("whatsapp_account") else ""
    )
    raw_messages = frappe.db.sql(f"""
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
        where {identity_filter}
          {account_filter}
          AND COALESCE(message_type, '') <> 'Template'
        order by creation asc
    """, {
        "user_no": user_no,
        "profile": contact.get("whatsapp_profile"),
        "whatsapp_account": contact.get("whatsapp_account"),
    }, as_dict=True)
    messages = cast(list[dict[str, Any]], raw_messages)

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


@frappe.whitelist()
def get_call_state(room: str):
    """Return WhatsApp calling state for the current chat room."""
    require_contact_access(room)
    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))
    identity_kwargs = _calling_identity_kwargs(contact)
    if not (identity_kwargs.get("phone_number") or identity_kwargs.get("recipient")):
        frappe.throw(_("This contact has no callable WhatsApp identity."))

    from frappe_whatsapp.utils.calling import get_call_state as _get_state
    return _get_state(
        **identity_kwargs,
        contact=room,
        agent_user=frappe.session.user,
    )


@frappe.whitelist()
def start_call(room: str):
    """Start a WhatsApp outbound call when permission is already active."""
    require_contact_access(room)
    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))
    identity_kwargs = _calling_identity_kwargs(contact)
    if not (identity_kwargs.get("phone_number") or identity_kwargs.get("recipient")):
        frappe.throw(_("This contact has no callable WhatsApp identity."))

    from frappe_whatsapp.utils.calling import start_outbound_call
    return start_outbound_call(
        **identity_kwargs,
        contact=room,
        agent_user=frappe.session.user,
    )


@frappe.whitelist()
def request_call_permission(room: str):
    """Explicitly send a call-permission template without starting a call."""
    require_contact_access(room)
    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))
    identity_kwargs = _calling_identity_kwargs(contact)
    if not (identity_kwargs.get("phone_number") or identity_kwargs.get("recipient")):
        frappe.throw(_("This contact has no callable WhatsApp identity."))

    from frappe_whatsapp.utils.calling import request_call_permission as _request
    return _request(
        **identity_kwargs,
        contact=room,
        agent_user=frappe.session.user,
    )


@frappe.whitelist()
def request_contact_info(
    room: str,
    message: str | None = None,
):
    """Ask a WhatsApp user to voluntarily share their phone number."""
    require_contact_access(room)
    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room),
    )
    if not (
        contact.mobile_no
        or contact.get("user_id")
        or contact.get("parent_user_id")
    ):
        frappe.throw(_("This contact has no messageable WhatsApp identity."))

    prompt = message or _("Please share your contact information.")
    doc = cast(
        WhatsAppMessage,
        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": contact.mobile_no,
            "recipient": (
                contact.get("user_id") or contact.get("parent_user_id")
            ),
            "contact_profile": contact.get("whatsapp_profile"),
            "whatsapp_account": contact.get("whatsapp_account"),
            "type": "Outgoing",
            "message": prompt,
            "content_type": "contact_request",
        }).insert(ignore_permissions=False),
    )
    return {
        "message_name": doc.name,
        "provider_message_id": doc.message_id,
        "content": prompt,
    }


def send_whatsapp_read_receipts(room):
    """Send read receipts to WhatsApp for unread incoming messages."""
    try:
        # Get the contact's mobile number
        contact = cast(
            WhatsAppContact,
            frappe.get_doc("WhatsApp Contact", room))

        if not (contact.mobile_no or contact.get("whatsapp_profile")):
            return

        # Find unread incoming messages for this contact
        filters = {
            "type": "Incoming",
            "status": ["not in", ["marked as read"]]
        }
        filters[
            "contact_profile" if contact.get("whatsapp_profile") else "from"
        ] = contact.get("whatsapp_profile") or contact.mobile_no
        if contact.get("whatsapp_account"):
            filters["whatsapp_account"] = contact.get("whatsapp_account")
        unread_messages = frappe.get_all(
            "WhatsApp Message",
            filters=filters,
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
    recipient = contact.get("user_id") or contact.get("parent_user_id")

    resolved_content_type = "text"
    detected_mime_type = None
    content = content or ""
    if attachment:
        resolved_content_type, detected_mime_type = \
            resolve_attachment_content_type(
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
            "recipient": recipient,
            "contact_profile": contact.get("whatsapp_profile"),
            "whatsapp_account": contact.get("whatsapp_account"),
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
            "recipient": recipient,
            "contact_profile": contact.get("whatsapp_profile"),
            "whatsapp_account": contact.get("whatsapp_account"),
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
        "recipient": contact.get("user_id") or contact.get("parent_user_id"),
        "contact_profile": contact.get("whatsapp_profile"),
        "whatsapp_account": contact.get("whatsapp_account"),
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
    contact_profile = doc.get("contact_profile")
    whatsapp_account = doc.get("whatsapp_account")
    contact_name = None
    candidates = []
    if contact_profile:
        candidates.append({
            "whatsapp_profile": contact_profile,
            "whatsapp_account": whatsapp_account,
        })
    if mobile_no:
        candidates.append({
            "mobile_no": mobile_no,
            "whatsapp_account": whatsapp_account,
        })
        # Backward compatibility for rooms created before account linkage.
        candidates.append({"mobile_no": mobile_no, "whatsapp_account": ["is", "not set"]})
    for filters in candidates:
        contact_name = frappe.db.get_value("WhatsApp Contact", filters=filters)
        if contact_name:
            break
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
                "whatsapp_profile": contact_profile,
                "whatsapp_account": whatsapp_account,
                "user_id": doc.get("from_user_id") or doc.get("recipient_user_id") or doc.get("recipient"),
                "parent_user_id": doc.get("from_parent_user_id") or doc.get("recipient_parent_user_id"),
                "username": doc.get("username"),
                "last_message": preview,
                "contact_name": (
                    doc.get("profile_name") or doc.get("username")
                    or mobile_no
                ),
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
        "sender_user_no": mobile_no or doc.get("from_user_id"),
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
