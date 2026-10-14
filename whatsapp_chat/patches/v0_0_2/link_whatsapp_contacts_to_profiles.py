from __future__ import annotations

import hashlib
from typing import cast

import frappe

from whatsapp_chat.whatsapp_chat.doctype.whatsapp_contact.whatsapp_contact import (
    WhatsAppContact,
)

from frappe_whatsapp.utils.identity import (
    alias_key,
    get_identity_scope,
    normalize_phone,
)


def execute() -> None:
    if not frappe.db.has_column("WhatsApp Contact", "whatsapp_profile"):
        return
    contacts = frappe.get_all(
        "WhatsApp Contact",
        fields=["name", "mobile_no", "whatsapp_account", "whatsapp_profile"],
    )
    for contact in contacts:
        number = normalize_phone(contact.mobile_no)
        accounts = _accounts_for_contact(
            number=number,
            configured_account=str(contact.whatsapp_account or ""),
        )
        if not accounts:
            _link_unscoped_contact(contact, number)
            continue

        source = cast(
            WhatsAppContact,
            frappe.get_doc("WhatsApp Contact", contact.name),
        )
        for index, account in enumerate(accounts):
            profile = _profile_for_account(
                account=account,
                number=number,
                existing_profile=str(contact.whatsapp_profile or ""),
            )
            identity = profile or number
            if not identity:
                continue
            identity_key = _identity_key(account, identity)
            existing = frappe.db.get_value(
                "WhatsApp Contact", {"identity_key": identity_key}, "name"
            )
            if existing:
                _set_contact_identity(
                    str(existing), account, profile, identity_key
                )
                continue

            if index == 0:
                target = source
            else:
                target = cast(WhatsAppContact, frappe.copy_doc(source))
                target.name = None
            target.whatsapp_account = account
            target.whatsapp_profile = profile
            target.identity_key = identity_key
            if index == 0:
                target.save(ignore_permissions=True)
            else:
                target.insert(ignore_permissions=True)


def _accounts_for_contact(
    *, number: str, configured_account: str
) -> list[str]:
    accounts = {configured_account} if configured_account else set()
    if number:
        for fieldname in ("from", "to"):
            accounts.update(
                str(account)
                for account in frappe.get_all(
                    "WhatsApp Message",
                    filters={fieldname: number},
                    pluck="whatsapp_account",
                )
                if account
            )
    return sorted(accounts)


def _profile_for_account(
    *, account: str, number: str, existing_profile: str
) -> str | None:
    if number:
        profile = frappe.db.get_value(
            "WhatsApp Profile Alias",
            alias_key(get_identity_scope(account), "phone", number),
            "whatsapp_profile",
        )
        if profile:
            return str(profile)
    if existing_profile:
        profile_scope = frappe.db.get_value(
            "WhatsApp Profiles", existing_profile, "identity_scope"
        )
        if profile_scope == get_identity_scope(account):
            return existing_profile
    return None


def _link_unscoped_contact(contact, number: str) -> None:
    profile = str(contact.whatsapp_profile or "")
    if not profile and number:
        matches = frappe.get_all(
            "WhatsApp Profiles",
            filters={"number": number},
            pluck="name",
            limit=2,
        )
        if len(matches) == 1:
            profile = str(matches[0])
    identity = profile or number
    if not identity:
        return
    _set_contact_identity(
        str(contact.name), "", profile or None, _identity_key("", identity)
    )


def _identity_key(account: str, identity: str) -> str:
    return hashlib.sha256(
        f"{account}:{identity}".encode("utf-8")
    ).hexdigest()


def _set_contact_identity(
    contact_name: str,
    account: str,
    profile: str | None,
    identity_key: str,
) -> None:
    frappe.db.set_value(
        "WhatsApp Contact",
        contact_name,
        {
            "whatsapp_profile": profile,
            "whatsapp_account": account or None,
            "identity_key": identity_key,
        },
        update_modified=False,
    )
