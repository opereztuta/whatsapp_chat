# Copyright (c) 2024, shridhar patil and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from typing import cast

from whatsapp_chat.whatsapp_chat.doctype.whatsapp_contact.whatsapp_contact import (
    WhatsAppContact,
)


class TestWhatsAppContact(FrappeTestCase):
    def test_bsuid_only_contact_uses_masked_display_name(self):
        suffix = frappe.generate_hash(length=12)
        user_id = f"US.{suffix}"

        contact = cast(
            WhatsAppContact,
            frappe.get_doc({
                "doctype": "WhatsApp Contact",
                "user_id": user_id,
            }).insert(ignore_permissions=True),
        )

        self.assertEqual(contact.contact_name, f"US.…{suffix[-4:]}")
