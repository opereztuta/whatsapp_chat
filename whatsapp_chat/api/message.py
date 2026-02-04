import frappe
import mimetypes
from whatsapp_chat.api.auth import require_contact_access, ROLE_AGENT
from whatsapp_chat.whatsapp_chat.doctype.whatsapp_contact.whatsapp_contact \
        import WhatsAppContact
from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message import WhatsAppMessage  # noqa: E501
from typing import cast
from frappe.utils import now


IMG_FILE_TYPES = [
    "image/apng", "image/avif", "image/gif", "image/jpeg",
    "image/png", "image/svg", "image/webp"]

DOC_FILE_TYPES = [
    "application/pdf", "application/vnd.ms-powerpoint",
    "application/msword", "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ("application/vnd.openxmlformats-officedocument." +
     "presentationml.presentation"),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]

AUDIO_FILE_TYPES = [
    "audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"]


@frappe.whitelist()
def get_all(room: str):
    """Get all messages for a room (WhatsApp Contact name)."""
    require_contact_access(room)

    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))

    user_no = contact.mobile_no  # authoritative

    return frappe.db.sql("""
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
          when COALESCE(content_type, 'text') <> 'text' then message
          else NULL
        end as caption,
        COALESCE(content_type, 'text') as content_type
        from `tabWhatsApp Message`
        where (`to` = %(user_no)s or `from` = %(user_no)s)
          AND COALESCE(message_type, '') <> 'Template'
        order by creation asc
    """, {"user_no": user_no}, as_dict=True)


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
def send(room: str, content: str, attachment: str | None = None):
    """Send a message to the room contact."""
    require_contact_access(room)

    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", room))
    user_no = contact.mobile_no

    content_type = "text"
    if attachment:
        file_type = mimetypes.guess_type(attachment)[0]
        if file_type in IMG_FILE_TYPES:
            content_type = "image"
        elif file_type in DOC_FILE_TYPES:
            content_type = "document"
        elif file_type in AUDIO_FILE_TYPES:
            content_type = "audio"
        elif file_type in ["video/mp4", "video/3gp"]:
            content_type = "video"

        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": user_no,
            "type": "Outgoing",
            "attach": attachment,
            "message": content or "",     # caption support
            "content_type": content_type,
        }).insert(ignore_permissions=False)
    else:
        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": user_no,
            "type": "Outgoing",
            "message": content,
            "content_type": content_type,
        }).insert(ignore_permissions=False)

    return "ok"


def last_message(doc, method):
    if doc.type == 'Outgoing':
        mobile_no = doc.to
    else:
        mobile_no = doc.get("from")

    contact_name = frappe.db.get_value(
        "WhatsApp Contact", filters={"mobile_no": mobile_no})
    if contact_name:
        # Use set_value to avoid TimestampMismatchError from concurrent updates
        frappe.db.set_value(
            "WhatsApp Contact",
            contact_name,
            {"last_message": doc.message, "is_read": 0},
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
                "last_message": doc.message,
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
        caption = doc.message if doc.attach else None

    message_data = {
        "content": content,
        "creation": now(),
        "room": chat_doc.name,
        "contact_name": chat_doc.contact_name,
        "sender_user_no": mobile_no,
        "user": "Guest",
        "content_type": content_type,
        "caption": caption,
    }

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
