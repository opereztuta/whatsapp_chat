# Copyright (c) 2024, shridhar patil and contributors
# For license information, please see license.txt

import frappe
import hashlib
from frappe.model.document import Document


class WhatsAppContact(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        contact_name: DF.Data | None
        email: DF.Link | None
        identity_key: DF.Data | None
        is_read: DF.Check
        last_message: DF.LongText | None
        mobile_no: DF.Data | None
        parent_user_id: DF.Data | None
        user_id: DF.Data | None
        username: DF.Data | None
        whatsapp_account: DF.Link | None
        whatsapp_profile: DF.Link | None
    # end: auto-generated types

    def validate(self):
        if not (
            self.get("whatsapp_profile") or self.mobile_no
            or self.get("user_id") or self.get("parent_user_id")
        ):
            frappe.throw("A WhatsApp identity is required.")
        profile_name = None
        if self.get("whatsapp_profile"):
            profile = frappe.db.get_value(
                "WhatsApp Profiles",
                self.get("whatsapp_profile"),
                [
                    "profile_name", "username", "number", "user_id",
                    "parent_user_id", "whatsapp_account",
                ],
                as_dict=True,
            ) or {}
            profile_name = profile.get("profile_name")
            self.username = self.username or profile.get("username")
            self.mobile_no = self.mobile_no or profile.get("number")
            self.user_id = self.get("user_id") or profile.get("user_id")
            self.parent_user_id = (
                self.get("parent_user_id")
                or profile.get("parent_user_id")
            )
            self.whatsapp_account = (
                self.get("whatsapp_account")
                or profile.get("whatsapp_account")
            )
        if not self.contact_name:
            self.contact_name = (
                profile_name or self.get("username") or self.mobile_no
                or _masked_bsuid(
                    self.get("user_id") or self.get("parent_user_id")
                )
            )
        identity = (
            self.get("whatsapp_profile") or self.get("user_id")
            or self.get("parent_user_id") or self.mobile_no
        )
        raw_key = f"{self.get('whatsapp_account') or ''}:{identity}"
        self.set(
            "identity_key",
            hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
        )

    def after_insert(self):
        if self.email:
            frappe.publish_realtime(
                "new_room_creation",
                {
                    "room": self.name,
                    "room_name": self.contact_name,
                    "mobile_no": self.mobile_no,
                    "is_read": self.is_read,
                    "last_message": self.last_message or "",
                    "modified": str(self.modified),
                },
                user=self.email
            )



def _masked_bsuid(value):
    value = str(value or "")
    if not value:
        return None
    prefix = value.split(".", 1)[0]
    return f"{prefix}.…{value[-4:]}"
