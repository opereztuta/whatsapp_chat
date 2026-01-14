import frappe
from frappe import _
from typing import cast
from whatsapp_chat.whatsapp_chat.doctype.whatsapp_contact.whatsapp_contact \
        import WhatsAppContact

ROLE_AGENT = "WhatsApp Chat Agent"


def can_access_chat(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False

    roles = set(frappe.get_roles(user))
    if "System Manager" in roles:
        return True
    if ROLE_AGENT in roles:
        return True

    allowed = frappe.get_conf().get("whatsapp_chat_allowed_users") or []
    return user in set(allowed)


def require_chat_access():
    if not can_access_chat():
        frappe.throw(
            _("Not permitted to access WhatsApp Chat."),
            frappe.PermissionError)


def require_contact_access(contact_name: str):
    """
    Ensures current user can access this WhatsApp Contact room.
    Rule:
      - System Manager can access all.
      - Agents can access contacts assigned to them (email == session user)
        and (optionally) unassigned contacts (email == '') if you want a
        shared inbox.
    """
    require_chat_access()

    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    if "System Manager" in roles:
        return

    contact = cast(
        WhatsAppContact,
        frappe.get_doc("WhatsApp Contact", contact_name))

    # Change this behavior depending on your policy:
    allow_unassigned = True  # shared inbox if contact.email == ''
    if contact.email == user:
        return
    if allow_unassigned and (contact.email or "") == "":
        return

    frappe.throw(
        _("You are not allowed to access this conversation."),
        frappe.PermissionError)
