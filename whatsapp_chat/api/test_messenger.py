from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMessengerContactScoping(FrappeTestCase):
    def test_same_sender_can_exist_on_two_meta_connections(self):
        suffix = frappe.generate_hash(length=8)
        sender_id = f"shared-sender-{suffix}"
        first = frappe.get_doc(
            {
                "doctype": "Messenger Contact",
                "sender_id": sender_id,
                "connection": f"connection-a-{suffix}",
                "channel": "Messenger",
                "contact_name": "Connection A User",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        second = frappe.get_doc(
            {
                "doctype": "Messenger Contact",
                "sender_id": sender_id,
                "connection": f"connection-b-{suffix}",
                "channel": "Messenger",
                "contact_name": "Connection B User",
            }
        ).insert(ignore_permissions=True, ignore_links=True)

        self.assertNotEqual(first.name, second.name)
        self.assertNotEqual(first.contact_key, second.contact_key)
