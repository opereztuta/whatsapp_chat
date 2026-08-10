from __future__ import annotations

import base64
from typing import cast
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from whatsapp_chat.api.messenger import (
    download_attachment,
    get_all_messages,
    send_message,
    send_voice_note,
)
from whatsapp_chat.whatsapp_chat.doctype.messenger_contact.messenger_contact import (
    MessengerContact,
)


class TestMessengerContactScoping(FrappeTestCase):
    def test_same_sender_can_exist_on_two_meta_connections(self):
        suffix = frappe.generate_hash(length=8)
        sender_id = f"shared-sender-{suffix}"
        first = cast(
            MessengerContact,
            frappe.get_doc(
                {
                    "doctype": "Messenger Contact",
                    "sender_id": sender_id,
                    "connection": f"connection-a-{suffix}",
                    "channel": "Messenger",
                    "contact_name": "Connection A User",
                }
            ).insert(ignore_permissions=True, ignore_links=True),
        )
        second = cast(
            MessengerContact,
            frappe.get_doc(
                {
                    "doctype": "Messenger Contact",
                    "sender_id": sender_id,
                    "connection": f"connection-b-{suffix}",
                    "channel": "Messenger",
                    "contact_name": "Connection B User",
                }
            ).insert(ignore_permissions=True, ignore_links=True),
        )

        self.assertNotEqual(first.name, second.name)
        self.assertNotEqual(first.contact_key, second.contact_key)


class TestMessengerMedia(FrappeTestCase):
    def setUp(self):
        suffix = frappe.generate_hash(length=8)
        self.sender_id = f"sender-{suffix}"
        self.connection = f"connection-{suffix}"
        self.contact = cast(
            MessengerContact,
            frappe.get_doc(
                {
                    "doctype": "Messenger Contact",
                    "sender_id": self.sender_id,
                    "connection": self.connection,
                    "channel": "Messenger",
                    "contact_name": "Media User",
                }
            ).insert(ignore_permissions=True, ignore_links=True),
        )

    def _make_file(
        self,
        *,
        room: str | None = None,
        is_private: int = 1,
        extension: str = "png",
        content: bytes | None = None,
    ):
        file_content = content or base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
            "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        return frappe.get_doc(
            {
                "doctype": "File",
                "file_name": (
                    f"messenger-{frappe.generate_hash(length=8)}.{extension}"
                ),
                "attached_to_doctype": "Messenger Contact",
                "attached_to_name": room or self.contact.name,
                "content": file_content,
                "is_private": is_private,
            }
        ).save(ignore_permissions=True)

    @patch(
        "frappe_meta_messenger.utils.message_service.send_uploaded_attachment",
        return_value="META-MSG-TEST",
    )
    def test_send_private_attachment_from_contact(self, mock_send):
        file_doc = self._make_file()
        result = send_message(
            str(self.contact.name),
            attachment=str(file_doc.file_url),
            mime_type="image/png",
        )

        self.assertEqual(result["name"], "META-MSG-TEST")
        self.assertEqual(result["content_type"], "image")
        self.assertEqual(result["attachment_name"], file_doc.file_name)
        self.assertEqual(result["attachment_status"], "Ready")
        self.assertIn("download_attachment?", result["content"])
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["local_attachment"], file_doc.file_url)
        self.assertEqual(kwargs["content"], file_doc.get_content())
        file_doc.reload()
        self.assertEqual(
            file_doc.attached_to_doctype,
            "Meta Messaging Message",
        )
        self.assertEqual(file_doc.attached_to_name, "META-MSG-TEST")

    def test_rejects_foreign_attachment(self):
        other_room = f"other-room-{frappe.generate_hash(length=8)}"
        foreign_file = self._make_file(room=other_room)
        with self.assertRaises(frappe.PermissionError):
            send_message(
                str(self.contact.name),
                attachment=str(foreign_file.file_url),
                mime_type="image/png",
            )

    def test_rejects_text_and_attachment_together(self):
        file_doc = self._make_file()
        with self.assertRaises(frappe.ValidationError):
            send_message(
                str(self.contact.name),
                content="caption",
                attachment=str(file_doc.file_url),
                mime_type="image/png",
            )

    def test_rejects_oversized_mismatched_and_unsupported_channel_files(self):
        image = self._make_file()
        with patch(
            "whatsapp_chat.api.messenger.get_max_file_size",
            return_value=1,
        ), self.assertRaises(frappe.ValidationError):
            send_message(
                str(self.contact.name),
                attachment=str(image.file_url),
                mime_type="image/png",
            )

        with self.assertRaises(frappe.ValidationError):
            send_message(
                str(self.contact.name),
                attachment=str(image.file_url),
                mime_type="video/mp4",
            )

        self.contact.channel = "Instagram"
        self.contact.save(ignore_permissions=True)
        document = self._make_file(
            extension="doc",
            content=b"Messenger document fixture",
        )
        with self.assertRaises(frappe.ValidationError):
            send_message(
                str(self.contact.name),
                attachment=str(document.file_url),
                mime_type="application/msword",
            )

    @patch(
        "frappe_meta_messenger.utils.message_service.send_uploaded_attachment",
        side_effect=frappe.ValidationError("Meta upload failed"),
    )
    def test_failed_meta_upload_keeps_file_attached_to_contact(self, _mock_send):
        file_doc = self._make_file()
        with self.assertRaisesRegex(frappe.ValidationError, "Meta upload failed"):
            send_message(
                str(self.contact.name),
                attachment=str(file_doc.file_url),
                mime_type="image/png",
            )

        file_doc.reload()
        self.assertEqual(file_doc.attached_to_doctype, "Messenger Contact")
        self.assertEqual(file_doc.attached_to_name, self.contact.name)

    @patch(
        "frappe_meta_messenger.utils.message_service.send_uploaded_attachment",
        return_value="META-MSG-VOICE",
    )
    def test_send_private_recording_as_normalized_voice_note(self, mock_send):
        raw_file = self._make_file(
            extension="webm",
            content=b"browser recording",
        )
        normalized_file = self._make_file(
            extension="ogg",
            content=b"normalized ogg opus",
        )

        with patch(
            "whatsapp_chat.api.voice.normalize_voice_note_to_ogg",
            return_value=normalized_file,
        ):
            result = send_voice_note(
                str(self.contact.name),
                attachment=str(raw_file.file_url),
                mime_type="audio/webm; codecs=opus",
            )

        self.assertEqual(result["name"], "META-MSG-VOICE")
        self.assertEqual(result["content_type"], "audio")
        self.assertEqual(result["is_voice_note"], 1)
        self.assertEqual(
            result["attachment_mime_type"],
            "audio/ogg",
        )
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["attachment_type"], "audio")
        self.assertTrue(kwargs["is_voice_note"])
        self.assertEqual(kwargs["content"], normalized_file.get_content())
        normalized_file.reload()
        self.assertEqual(
            normalized_file.attached_to_doctype,
            "Meta Messaging Message",
        )
        self.assertEqual(normalized_file.attached_to_name, "META-MSG-VOICE")
        self.assertFalse(frappe.db.exists("File", raw_file.name))

    def test_voice_note_rejects_public_and_instagram_files(self):
        public_file = self._make_file(
            is_private=0,
            extension="ogg",
            content=b"audio",
        )
        with self.assertRaises(frappe.ValidationError):
            send_voice_note(
                str(self.contact.name),
                attachment=str(public_file.file_url),
                mime_type="audio/ogg",
            )

        private_file = self._make_file(
            extension="ogg",
            content=b"audio",
        )
        self.contact.channel = "Instagram"
        self.contact.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            send_voice_note(
                str(self.contact.name),
                attachment=str(private_file.file_url),
                mime_type="audio/ogg",
            )

    @patch("frappe.utils.response.send_private_file")
    def test_private_download_is_scoped_to_room_and_message(
        self,
        mock_send_private,
    ):
        message = frappe.get_doc(
            {
                "doctype": "Meta Messaging Message",
                "direction": "incoming",
                "channel": "messenger",
                "connection": self.connection,
                "sender_id": self.sender_id,
                "recipient_id": "page",
                "message_type": "image",
                "attachment_url": "https://scontent.xx.fbcdn.net/photo.png",
                "attachment_type": "image",
                "attachment_status": "Pending",
                "status": "received",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        file_doc = self._make_file(is_private=1)
        file_doc.attached_to_doctype = "Meta Messaging Message"
        file_doc.attached_to_name = message.name
        file_doc.attached_to_field = "attachment"
        file_doc.save(ignore_permissions=True)
        message.attachment = file_doc.file_url
        message.attachment_name = file_doc.file_name
        message.attachment_mime_type = "image/png"
        message.attachment_status = "Ready"
        message.save(ignore_permissions=True)

        download_attachment(str(self.contact.name), str(message.name))
        mock_send_private.assert_called_once()

        other_contact = frappe.get_doc(
            {
                "doctype": "Messenger Contact",
                "sender_id": f"other-{frappe.generate_hash(length=8)}",
                "connection": self.connection,
                "channel": "Messenger",
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        with self.assertRaises(frappe.PermissionError):
            download_attachment(str(other_contact.name), str(message.name))

        history = get_all_messages(str(self.contact.name))
        stored = next(row for row in history if row.name == message.name)
        self.assertIn("download_attachment?", stored.content)
        self.assertEqual(stored.attachment_name, file_doc.file_name)
        self.assertEqual(stored.attachment_status, "Ready")

    def test_multi_attachment_siblings_have_distinct_history_downloads(self):
        message_names = []
        for attachment_index in (1, 2):
            message = frappe.get_doc(
                {
                    "doctype": "Meta Messaging Message",
                    "direction": "incoming",
                    "channel": "messenger",
                    "connection": self.connection,
                    "sender_id": self.sender_id,
                    "recipient_id": "page",
                    "external_message_id": "mid-multi",
                    "message_type": "image",
                    "attachment_url": (
                        f"https://scontent.xx.fbcdn.net/{attachment_index}.png"
                    ),
                    "attachment_type": "image",
                    "attachment_index": attachment_index,
                    "attachment_count": 2,
                    "attachment_status": "Pending",
                    "status": "received",
                }
            ).insert(ignore_permissions=True, ignore_links=True)
            file_doc = self._make_file(is_private=1)
            file_doc.attached_to_doctype = "Meta Messaging Message"
            file_doc.attached_to_name = message.name
            file_doc.attached_to_field = "attachment"
            file_doc.save(ignore_permissions=True)
            message.attachment = file_doc.file_url
            message.attachment_name = file_doc.file_name
            message.attachment_mime_type = "image/png"
            message.attachment_status = "Ready"
            message.save(ignore_permissions=True)
            message_names.append(message.name)

        history = get_all_messages(str(self.contact.name))
        siblings = [row for row in history if row.name in message_names]

        self.assertEqual(len(siblings), 2)
        self.assertEqual({row.name for row in siblings}, set(message_names))
        self.assertEqual(len({row.content for row in siblings}), 2)
        for row in siblings:
            self.assertIn("download_attachment?", row.content)
            self.assertIn(f"message_name={row.name}", row.content)
