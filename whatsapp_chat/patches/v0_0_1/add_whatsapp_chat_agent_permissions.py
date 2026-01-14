import frappe

ROLE_NAME = "WhatsApp Chat Agent"

PERMISSIONS = {
    "WhatsApp Contact": dict(read=1, write=1, create=1),
    "WhatsApp Message": dict(read=1, write=1, create=1),
}


def execute():
    # Ensure role exists first
    try:
        from whatsapp_chat.install import ensure_whatsapp_chat_agent_role
        ensure_whatsapp_chat_agent_role()
    except Exception:
        # If import fails for any reason, fall back to local creation
        ensure_role_exists()

    for doctype, perms in PERMISSIONS.items():
        ensure_docperm(doctype, ROLE_NAME, perms)


def ensure_role_exists():
    if frappe.db.exists("Role", ROLE_NAME):
        return
    frappe.get_doc({
        "doctype": "Role",
        "role_name": ROLE_NAME,
        "desk_access": 1,
    }).insert(ignore_permissions=True)


def ensure_docperm(doctype: str, role: str, perms: dict):
    """
    Create DocPerm rows if missing.
    Idempotent: won't duplicate existing permission row for the role.
    """
    # If there is already any perm row for this role on this doctype,
    # do nothing.
    existing = frappe.db.exists(
        "DocPerm",
        {"parent": doctype, "role": role, "permlevel": 0},
    )
    if existing:
        return

    # Only include fields that exist in this Frappe version
    docperm_meta = frappe.get_meta("DocPerm")
    allowed_fields = {df.fieldname for df in docperm_meta.fields}

    doc = {
        "doctype": "DocPerm",
        "parent": doctype,
        "parenttype": "DocType",
        "parentfield": "permissions",
        "role": role,
        "permlevel": 0,
    }

    for k, v in perms.items():
        if k in allowed_fields:
            doc[k] = v

    frappe.get_doc(doc).insert(ignore_permissions=True)
