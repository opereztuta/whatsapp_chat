from __future__ import annotations

import hashlib

import frappe


def execute() -> None:
    rows = frappe.get_all(
        "Messenger Contact", fields=["name", "sender_id", "connection"]
    )
    for row in rows:
        sender_id = str(row.get("sender_id") or "").strip()
        if not sender_id:
            continue
        connection = str(row.get("connection") or "legacy").strip()
        value = f"{connection}:{sender_id}"
        contact_key = hashlib.sha256(value.encode("utf-8")).hexdigest()
        frappe.db.set_value(
            "Messenger Contact",
            row["name"],
            "contact_key",
            contact_key,
            update_modified=False,
        )
