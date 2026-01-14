# Copyright (c) 2024, shridhar patil and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppContact(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        contact_name: DF.Data | None
        email: DF.Link | None
        is_read: DF.Check
        last_message: DF.LongText | None
        mobile_no: DF.Data
    # end: auto-generated types

    def after_insert(self):
        if self.email:
            frappe.publish_realtime(
                "new_room_creation",
                {
                    "user": self.email,
                    "room_name": self.contact_name
                },
                user=self.email
            )

    pass
