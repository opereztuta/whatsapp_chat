import frappe

ROLE_NAME = "WhatsApp Chat Agent"


def execute():
    # Make it safe + idempotent
    if frappe.db.exists("Role", ROLE_NAME):
        return

    doc = frappe.get_doc({
        "doctype": "Role",
        "role_name": ROLE_NAME,
        "desk_access": 1,
    })
    doc.insert(ignore_permissions=True)
