import frappe

ROLE_NAME = "WhatsApp Chat Agent"


def after_install():
    ensure_whatsapp_chat_agent_role()


def ensure_whatsapp_chat_agent_role() -> None:
    """Create role if it doesn't exist (idempotent)."""
    if frappe.db.exists("Role", ROLE_NAME):
        return

    doc = frappe.get_doc({
        "doctype": "Role",
        "role_name": ROLE_NAME,
        "desk_access": 1,   # typical for desk users
    })
    doc.insert(ignore_permissions=True)
