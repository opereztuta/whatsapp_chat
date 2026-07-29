from typing import cast
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.core.api.file import get_max_file_size
from frappe.utils import get_url, now

from whatsapp_chat.api.auth import ROLE_AGENT
from whatsapp_chat.api.media import (
    get_file_record,
    resolve_attachment_content_type,
)
from whatsapp_chat.whatsapp_chat.doctype.messenger_contact.messenger_contact import MessengerContact


def _message_preview(doc) -> str:
    """Return a short text preview of the message for the contact list."""
    message_type = (doc.message_type or "text").lower()
    if message_type == "text":
        return doc.text or ""

    labels = {
        "image": "Image",
        "audio": "Audio",
        "video": "Video",
        "file": "Document",
        "sticker": "Sticker",
    }
    return labels.get(message_type, message_type.capitalize())


def _normalized_content_type(value: str | None) -> str:
    content_type = str(value or "text").lower()
    return "file" if content_type == "attachment" else content_type


def _stored_attachment_url(doc, room: str) -> str | None:
    attachment = str(doc.attachment or "")
    if not attachment:
        return None
    if attachment.startswith("/private/"):
        query = urlencode({"room": room, "message_name": doc.name})
        return (
            "/api/method/whatsapp_chat.api.messenger.download_attachment?"
            f"{query}"
        )
    return attachment


def _message_data(doc, chat_doc, *, media_update: bool = False) -> dict:
    content_type = _normalized_content_type(doc.message_type)
    stored_url = _stored_attachment_url(doc, str(chat_doc.name))
    content = (
        doc.text or ""
        if content_type == "text"
        else stored_url or doc.attachment_url or doc.text or ""
    )
    return {
        "name": doc.name,
        "content": content,
        "provider_attachment_url": doc.attachment_url,
        "provider_attachment_id": doc.provider_attachment_id,
        "creation": str(doc.creation or now()),
        "room": chat_doc.name,
        "contact_name": chat_doc.contact_name,
        "channel": chat_doc.channel,
        "sender_user_no": doc.sender_id,
        "user": "Guest",
        "content_type": content_type,
        "attachment_name": doc.attachment_name,
        "attachment_mime_type": doc.attachment_mime_type,
        "attachment_status": doc.attachment_status,
        "caption": None,
        "preview": _message_preview(doc),
        "messenger": True,
        "media_update": media_update,
    }


def _target_users(chat_doc) -> set[str]:
    users = set(
        frappe.get_all(
            "Has Role",
            filters={"role": "System Manager", "parenttype": "User"},
            pluck="parent",
        )
    )
    if chat_doc.email:
        users.add(chat_doc.email)
    else:
        users.update(
            frappe.get_all(
                "Has Role",
                filters={"role": ROLE_AGENT, "parenttype": "User"},
                pluck="parent",
            )
        )
    return users


def _publish_message(doc, chat_doc, *, media_update: bool = False) -> None:
    message_data = _message_data(doc, chat_doc, media_update=media_update)
    for user in _target_users(chat_doc):
        frappe.publish_realtime(
            "latest_messenger_updates",
            message_data,
            user=user,
        )
        frappe.publish_realtime(
            chat_doc.name,
            message_data,
            user=user,
        )


def last_message(doc, method):
    """
    Hook: Meta Messaging Message.after_insert
    - Finds or creates a Messenger Contact for the sender.
    - Updates last_message preview and is_read flag.
    - Publishes realtime events for the chat UI (incoming only).
    """
    # direction is lowercase in Meta Messaging Message: 'incoming' / 'outgoing'
    is_outgoing = (doc.direction or "").lower() == "outgoing"

    # For outgoing messages we sent, 
    # the person we're talking to is recipient_id.
    # For incoming, the person talking to us is sender_id.
    sender_id = doc.recipient_id if is_outgoing else doc.sender_id

    if not sender_id:
        return

    preview = _message_preview(doc)

    contact_name = frappe.db.get_value(
        "Messenger Contact",
        filters={"sender_id": sender_id, "connection": doc.connection},
    )

    if contact_name:
        frappe.db.set_value(
            "Messenger Contact",
            contact_name,
            {"last_message": preview, "is_read": 0},
            update_modified=True,
        )
        chat_doc = cast(
            MessengerContact,
            frappe.get_doc("Messenger Contact", str(contact_name)),
        )
    else:
        contact_name = sender_id
        if doc.connection:
            try:
                from frappe_meta_messenger.utils.meta_api import get_user_profile
                profile = get_user_profile(str(doc.connection), sender_id)
                contact_name = profile.get("name") or sender_id
            except Exception:
                pass

        chat_doc = cast(
            MessengerContact,
            frappe.get_doc({
                "doctype": "Messenger Contact",
                "sender_id": sender_id,
                "contact_name": contact_name,
                "last_message": preview,
                "is_read": 0,
                "channel": _normalise_channel(doc.channel),
                "connection": doc.connection,
            }),
        )
        chat_doc.insert(ignore_permissions=True)

    # Don't push realtime for outgoing — agent already sees it locally
    if is_outgoing:
        return

    _publish_message(doc, chat_doc)


def attachment_updated(doc, method):
    """Publish a replacement event when async inbound media becomes terminal."""
    if (doc.direction or "").lower() != "incoming":
        return
    if doc.attachment_status not in {"Ready", "Failed"}:
        return
    if not (
        doc.has_value_changed("attachment_status")
        or doc.has_value_changed("attachment")
    ):
        return

    contact_name = frappe.db.get_value(
        "Messenger Contact",
        filters={"sender_id": doc.sender_id, "connection": doc.connection},
    )
    if not contact_name:
        return
    chat_doc = frappe.get_doc("Messenger Contact", contact_name)
    _publish_message(doc, chat_doc, media_update=True)


def _normalise_channel(channel: str | None) -> str:
    """Map raw channel values from Meta Messaging Message to our Select options."""
    mapping = {
        "instagram": "Instagram",
        "messenger": "Messenger",
    }
    return mapping.get((channel or "").lower(), "Messenger")


def _require_messenger_contact_access(room: str) -> None:
    from whatsapp_chat.api.auth import require_chat_access
    require_chat_access()

    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if "System Manager" in roles:
        return

    contact = cast(
        MessengerContact,
        frappe.get_doc("Messenger Contact", room),
    )
    if contact.email == user:
        return
    if (contact.email or "") == "":
        return  # shared inbox

    frappe.throw(
        frappe._("You are not allowed to access this conversation."),
        frappe.PermissionError,
    )


@frappe.whitelist()
def get_contacts():
    """Return Messenger Contacts visible to the current user."""
    from whatsapp_chat.api.auth import require_chat_access
    require_chat_access()

    user = frappe.session.user
    roles = set(frappe.get_roles(user))

    if "System Manager" in roles:
        return frappe.db.get_all(
            "Messenger Contact", fields=["*"], order_by="modified desc")

    return frappe.db.get_all(
        "Messenger Contact",
        filters={"email": ["in", [user, ""]]},
        fields=["*"],
        order_by="modified desc",
    )


@frappe.whitelist()
def mark_as_read(room: str):
    _require_messenger_contact_access(room)
    frappe.db.set_value(
        "Messenger Contact", room, "is_read", 1, update_modified=False)
    frappe.db.commit()
    return "ok"


@frappe.whitelist()
def send_message(
    room: str,
    content: str = "",
    attachment: str | None = None,
    mime_type: str | None = None,
):
    _require_messenger_contact_access(room)

    content = (content or "").strip()
    attachment = str(attachment or "").strip() or None
    if attachment and content:
        frappe.throw(_("Send text and attachments as separate messages."))
    if not attachment and not content:
        frappe.throw(_("Message cannot be empty."))

    contact = cast(MessengerContact, frappe.get_doc("Messenger Contact", room))

    if not contact.connection:
        frappe.throw(frappe._("This contact has no Meta Connection configured."))

    if attachment:
        file_record = get_file_record(attachment)
        if not file_record:
            frappe.throw(_("Could not find the uploaded attachment."))
        if (
            file_record.get("attached_to_doctype") != "Messenger Contact"
            or file_record.get("attached_to_name") != room
        ):
            raise frappe.PermissionError(
                _("This attachment does not belong to the conversation.")
            )
        if int(file_record.get("file_size") or 0) > get_max_file_size():
            frappe.throw(
                _("Attachment exceeds the site's maximum file size."),
                title=_("Attachment Too Large"),
            )

        detected_type, detected_mime = resolve_attachment_content_type(
            attachment,
            explicit_mime_type=mime_type,
        )
        meta_type = "file" if detected_type == "document" else detected_type
        if (
            _normalise_channel(str(contact.channel)) == "Instagram"
            and meta_type not in {"image", "video"}
        ):
            frappe.throw(
                _("Instagram supports image and video attachments only."),
                title=_("Unsupported Attachment"),
            )

        file_doc = frappe.get_doc("File", file_record["name"])
        file_content = file_doc.get_content()
        if isinstance(file_content, str):
            file_content = file_content.encode("utf-8")
        if not isinstance(file_content, bytes) or not file_content:
            frappe.throw(
                _("Could not read the uploaded attachment."),
                title=_("Invalid Attachment"),
            )

        from frappe_meta_messenger.utils.message_service import (
            send_uploaded_attachment,
        )

        message_name = send_uploaded_attachment(
            connection_name=str(contact.connection),
            recipient_id=contact.sender_id,
            content=file_content,
            attachment_type=meta_type,
            attachment_name=str(file_record.get("file_name") or ""),
            attachment_mime_type=str(detected_mime or ""),
            local_attachment=attachment,
        )
        frappe.db.set_value(
            "File",
            file_record["name"],
            {
                "attached_to_doctype": "Meta Messaging Message",
                "attached_to_name": message_name,
                "attached_to_field": "attachment",
            },
            update_modified=False,
        )
        query = urlencode({"room": room, "message_name": message_name})
        content_url = (
            "/api/method/whatsapp_chat.api.messenger."
            f"download_attachment?{query}"
        )
        return {
            "name": message_name,
            "content": content_url,
            "direction": "outgoing",
            "content_type": meta_type,
            "attachment_name": file_record.get("file_name"),
            "attachment_mime_type": detected_mime,
            "attachment_status": "Ready",
            "provider_attachment_id": frappe.db.get_value(
                "Meta Messaging Message",
                message_name,
                "provider_attachment_id",
            ),
            "caption": None,
        }

    from frappe_meta_messenger.utils.message_service import send_text
    message_name = send_text(
        connection_name=str(contact.connection),
        recipient_id=contact.sender_id,
        text=content,
    )

    return {
        "name": message_name,
        "content": content,
        "direction": "outgoing",
        "content_type": "text",
    }


@frappe.whitelist()
def get_all_messages(room: str):
    """Return all Meta Messaging Messages for a Messenger Contact."""
    _require_messenger_contact_access(room)

    contact = cast(
        MessengerContact,
        frappe.get_doc("Messenger Contact", room),
    )
    sender_id = contact.sender_id
    connection = contact.connection

    messages = frappe.db.sql("""
        SELECT
            name,
            creation,
            direction,
            CASE WHEN direction = 'outgoing' THEN 'Administrator'
                 ELSE sender_id
            END AS sender_user_no,
            CASE WHEN LOWER(COALESCE(message_type, 'text')) = 'text'
                      THEN COALESCE(text, '')
                 ELSE COALESCE(attachment, attachment_url, text, '')
            END AS content,
            LOWER(COALESCE(message_type, 'text')) AS content_type,
            NULL AS caption,
            attachment,
            attachment_url AS provider_attachment_url,
            provider_attachment_id,
            attachment_name,
            attachment_mime_type,
            attachment_status,
            0 AS is_voice_note
        FROM `tabMeta Messaging Message`
        WHERE connection = %(connection)s
          AND (sender_id = %(sender_id)s OR recipient_id = %(sender_id)s)
        ORDER BY creation ASC
    """, {"sender_id": sender_id, "connection": connection}, as_dict=True)

    for message in messages:
        message.content_type = _normalized_content_type(message.content_type)
        if (
            message.get("attachment")
            and str(message.attachment).startswith("/private/")
        ):
            query = urlencode({"room": room, "message_name": message.name})
            message.content = (
                "/api/method/whatsapp_chat.api.messenger."
                f"download_attachment?{query}"
            )
    return messages


@frappe.whitelist()
def download_attachment(room: str, message_name: str):
    """Serve one stored private attachment after conversation access checks."""
    _require_messenger_contact_access(room)
    contact = cast(
        MessengerContact,
        frappe.get_doc("Messenger Contact", room),
    )
    message = frappe.get_doc("Meta Messaging Message", message_name)
    participant_matches = (
        message.sender_id == contact.sender_id
        or message.recipient_id == contact.sender_id
    )
    if message.connection != contact.connection or not participant_matches:
        raise frappe.PermissionError(_("Attachment is not part of this conversation."))
    if not message.attachment:
        raise frappe.DoesNotExistError

    files = frappe.get_all(
        "File",
        filters={
            "file_url": message.attachment,
            "attached_to_doctype": "Meta Messaging Message",
            "attached_to_name": message.name,
        },
        fields=["file_url", "is_private"],
        limit=1,
    )
    if not files:
        raise frappe.DoesNotExistError
    file_url = files[0].file_url
    if files[0].is_private:
        from frappe.utils.response import send_private_file

        return send_private_file(file_url.split("/private", 1)[1])

    from werkzeug.utils import redirect

    return redirect(
        file_url
        if str(file_url).startswith(("http://", "https://"))
        else f"{get_url().rstrip('/')}/{str(file_url).lstrip('/')}"
    )
