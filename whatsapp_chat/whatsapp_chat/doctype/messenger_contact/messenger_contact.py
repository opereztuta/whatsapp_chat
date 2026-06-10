# Copyright (c) 2026, contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MessengerContact(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        channel: DF.Literal["Messenger", "Instagram"]
        connection: DF.Link | None
        contact_name: DF.Data | None
        email: DF.Link | None
        is_read: DF.Check
        last_message: DF.LongText | None
        sender_id: DF.Data
    # end: auto-generated types

    def after_insert(self):

        self.channel = "Messenger"
        if self.email:
            frappe.publish_realtime(
                "new_messenger_room_creation",
                {
                    "room": self.name,
                    "room_name": self.contact_name,
                    "sender_id": self.sender_id,
                    "channel": self.channel,
                    "is_read": self.is_read,
                    "last_message": self.last_message or "",
                    "modified": str(self.modified),
                },
                user=self.email
            )
