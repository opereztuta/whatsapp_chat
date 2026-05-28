import frappe
from whatsapp_chat.api.auth import require_chat_access, can_access_chat


@frappe.whitelist()
def create(contact_name, mobile_no, email):
    require_chat_access()

    # Optional: only allow assigning to allowed agents
    if email and not can_access_chat(email):
        frappe.throw(
            "Target user is not allowed to use WhatsApp Chat.",
            frappe.PermissionError)

    doc = frappe.get_doc({
        "doctype": "WhatsApp Contact",
        "contact_name": contact_name,
        "mobile_no": mobile_no,
        "email": email,
    })
    doc.insert(ignore_permissions=False)
    return doc.name


@frappe.whitelist()
def get():
    """Return contacts for current user (and optionally unassigned)."""
    require_chat_access()

    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    print("contacts for user loading::", user, roles)   # ← shows in terminal

    if "System Manager" in roles:
        return frappe.db.get_all("WhatsApp Contact", fields=["*"])

    # shared inbox: allow unassigned ('') + assigned-to-me
    return frappe.db.get_all(
        "WhatsApp Contact",
        filters={"email": ["in", [user, ""]]},
        fields=["*"],
    )
