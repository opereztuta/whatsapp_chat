import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from whatsapp_chat.api import config


class TestInstagramCapability(unittest.TestCase):
    def test_app_is_optional(self):
        with patch.object(config.frappe, "get_installed_apps", return_value=["frappe"]):
            self.assertEqual(
                config._instagram_capability("agent@example.com"), (False, False)
            )

    def test_unmigrated_optional_app_is_ignored(self):
        mock_db = MagicMock()
        mock_db.exists.return_value = False
        with (
            patch.object(
                config.frappe, "get_installed_apps", return_value=["frappe_instagram"]
            ),
            patch.object(config.frappe, "db", mock_db),
        ):
            self.assertEqual(
                config._instagram_capability("agent@example.com"), (False, False)
            )
        mock_db.exists.assert_called_once_with("DocType", "Instagram Settings")

    def test_instagram_roles_are_allowed(self):
        mock_db = MagicMock()
        mock_db.exists.return_value = True
        mock_db.get_single_value.return_value = 1
        for role in ("Instagram Agent", "Instagram Manager", "System Manager"):
            with (
                self.subTest(role=role),
                patch.object(
                    config.frappe,
                    "get_installed_apps",
                    return_value=["frappe_instagram"],
                ),
                patch.object(config.frappe, "get_roles", return_value=[role]),
                patch.object(config.frappe, "db", mock_db),
            ):
                self.assertEqual(
                    config._instagram_capability("user@example.com"), (True, True)
                )

    def test_user_without_instagram_role_is_denied(self):
        mock_db = MagicMock()
        mock_db.exists.return_value = True
        mock_db.get_single_value.return_value = 1
        with (
            patch.object(
                config.frappe, "get_installed_apps", return_value=["frappe_instagram"]
            ),
            patch.object(config.frappe, "get_roles", return_value=["Sales User"]),
            patch.object(config.frappe, "db", mock_db),
        ):
            self.assertEqual(
                config._instagram_capability("sales@example.com"), (True, False)
            )

    def test_disabled_native_app_does_not_enable_widget(self):
        mock_db = MagicMock()
        mock_db.exists.return_value = True
        mock_db.get_single_value.return_value = 0
        with (
            patch.object(
                config.frappe, "get_installed_apps", return_value=["frappe_instagram"]
            ),
            patch.object(
                config.frappe, "get_roles", return_value=["Instagram Manager"]
            ),
            patch.object(config.frappe, "db", mock_db),
        ):
            self.assertEqual(
                config._instagram_capability("manager@example.com"), (False, False)
            )

    def test_instagram_access_is_independent_from_legacy_widgets(self):
        mock_db = MagicMock()
        mock_db.get_value.return_value = "System User"
        with (
            patch.object(
                config.frappe, "session", SimpleNamespace(user="agent@example.com")
            ),
            patch.object(config.frappe, "db", mock_db),
            patch.object(config, "_instagram_capability", return_value=(True, True)),
            patch.object(config, "can_access_chat", return_value=False),
            patch.object(config, "get_admin_name", return_value="Instagram Agent"),
            patch.object(config, "get_user_settings", return_value={}),
        ):
            settings = config.settings()

        self.assertTrue(settings["can_access_instagram"])
        self.assertFalse(settings["can_access_whatsapp"])
        self.assertFalse(settings["can_access_messenger"])
        self.assertTrue(settings["can_access_ui"])


class TestInstagramCapabilityDatabase(FrappeTestCase):
    def test_single_doctype_is_detected_without_a_physical_table(self):
        if "frappe_instagram" not in frappe.get_installed_apps():
            self.skipTest(
                "frappe_instagram is optional and is not installed on this site"
            )

        original = frappe.db.get_single_value("Instagram Settings", "enabled")
        try:
            frappe.db.set_single_value("Instagram Settings", "enabled", 1)
            with patch.object(
                config.frappe, "get_roles", return_value=["Instagram Agent"]
            ):
                self.assertEqual(
                    config._instagram_capability("agent@example.com"), (True, True)
                )
        finally:
            frappe.db.set_single_value("Instagram Settings", "enabled", original or 0)
