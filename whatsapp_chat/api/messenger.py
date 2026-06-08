import frappe
from frappe.utils import now
from typing import cast
from whatsapp_chat.api.auth import ROLE_AGENT
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


def last_message(doc, method):
    """
    Hook: Meta Messaging Message.after_insert
    - Finds or creates a Messenger Contact for the sender.
    - Updates last_message preview and is_read flag.
    - Publishes realtime events for the chat UI (incoming only).
    """
    print("HEREEEE")
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
        "Messenger Contact", filters={"sender_id": sender_id}
    )

    if contact_name:
        frappe.db.set_value(
            "Messenger Contact",
            contact_name,
            {"last_message": preview, "is_read": 0},
            update_modified=True,
        )
        chat_doc = frappe.get_doc("Messenger Contact", str(contact_name))
    else:
        contact_name = sender_id
        if doc.connection:
            try:
                from frappe_meta_messenger.utils.meta_api import get_user_profile
                profile = get_user_profile(str(doc.connection), sender_id)
                contact_name = profile.get("name") or sender_id
            except Exception:
                pass

        chat_doc = frappe.get_doc({
            "doctype": "Messenger Contact",
            "sender_id": sender_id,
            "contact_name": contact_name,
            "last_message": preview,
            "is_read": 0,
            "channel": _normalise_channel(doc.channel),
            "connection": doc.connection,
        })
        chat_doc.insert(ignore_permissions=True)

    # Don't push realtime for outgoing — agent already sees it locally
    if is_outgoing:
        return

    content_type = (doc.message_type or "text").lower()
    content = (
        doc.text or ""
        if content_type == "text"
        else doc.attachment_url or doc.text or ""
    )

    message_data = {
        "content": content,
        "creation": now(),
        "room": chat_doc.name,
        "contact_name": chat_doc.contact_name,
        "sender_user_no": sender_id,
        "user": "Guest",
        "content_type": content_type,
        "caption": None,
        "preview": preview,
        "messenger": True,   # lets the UI distinguish from WhatsApp
    }

    # Determine target users (same logic as WhatsApp)
    target_users = set()

    system_managers = frappe.get_all(
        "Has Role",
        filters={"role": "System Manager", "parenttype": "User"},
        pluck="parent",
    )
    target_users.update(system_managers)

    if chat_doc.email:
        target_users.add(chat_doc.email)
    else:
        agents = frappe.get_all(
            "Has Role",
            filters={"role": ROLE_AGENT, "parenttype": "User"},
            pluck="parent",
        )
        target_users.update(agents)

    for user in target_users:
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

    contact = frappe.get_doc("Messenger Contact", room)
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
def send_message(room: str, content: str):
    _require_messenger_contact_access(room)

    content = (content or "").strip()
    if not content:
        frappe.throw(frappe._("Message cannot be empty."))

    contact = cast(MessengerContact, frappe.get_doc("Messenger Contact", room))

    if not contact.connection:
        frappe.throw(frappe._("This contact has no Meta Connection configured."))

    from frappe_meta_messenger.utils.message_service import send_text
    send_text(
        connection_name=str(contact.connection),
        recipient_id=contact.sender_id,
        text=content,
    )

    return {
        "content": content,
        "direction": "outgoing",
        "content_type": "text",
    }


@frappe.whitelist()
def get_all_messages(room: str):
    """Return all Meta Messaging Messages for a Messenger Contact."""
    _require_messenger_contact_access(room)

    contact = frappe.get_doc("Messenger Contact", room)
    sender_id = contact.sender_id

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
                 ELSE COALESCE(attachment_url, text, '')
            END AS content,
            LOWER(COALESCE(message_type, 'text')) AS content_type,
            NULL AS caption,
            NULL AS attachment_mime_type,
            0 AS is_voice_note
        FROM `tabMeta Messaging Message`
        WHERE sender_id = %(sender_id)s OR recipient_id = %(sender_id)s
        ORDER BY creation ASC
    """, {"sender_id": sender_id}, as_dict=True)

    return messages
