import frappe
from frappe.utils import now
from whatsapp_chat.api.auth import ROLE_AGENT


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
        chat_doc = frappe.get_doc({
            "doctype": "Messenger Contact",
            "sender_id": sender_id,
            "contact_name": sender_id,   # default name to ID until enriched
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
