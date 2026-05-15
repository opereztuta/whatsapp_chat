from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from whatsapp_chat.api.message import (
    detect_content_type,
    get_all,
    send_voice_note,
    _requires_voice_note_transcode,
)


class TestWhatsAppChatMessageAudio(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.reload_doc("frappe_whatsapp", "doctype", "whatsapp_message")

    def _create_contact(self):
        suffix = frappe.generate_hash(length=8)
        return frappe.get_doc({
            "doctype": "WhatsApp Contact",
            "contact_name": f"Voice Contact {suffix}",
            "mobile_no": f"1555{suffix[:7]}",
        }).insert(ignore_permissions=True)

    def _create_account(self):
        suffix = frappe.generate_hash(length=8)
        return frappe.get_doc({
            "doctype": "WhatsApp Account",
            "account_name": f"Voice Test Account {suffix}",
            "status": "Active",
            "is_default_outgoing": 1,
            "url": "https://graph.facebook.com",
            "version": "v19.0",
            "phone_id": f"phone-{suffix}",
            "webhook_verify_token": f"verify-{suffix}",
        }).insert(ignore_permissions=True)

    def _create_file(self, *, contact, file_name="voice-note.ogg"):
        return frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "attached_to_doctype": "WhatsApp Contact",
            "attached_to_name": contact.name,
            "content": b"fake audio bytes",
        }).insert(ignore_permissions=True)

    def test_detect_content_type_for_audio_extensions(self):
        cases = {
            "/files/voice.ogg": "audio",
            "/files/voice.opus": "audio",
            "/files/voice.m4a": "audio",
            "/files/voice.mp3": "audio",
            "/files/voice.aac": "audio",
            "/files/voice.amr": "audio",
            "/files/voice.webm": "audio",
        }

        for attachment, expected in cases.items():
            self.assertEqual(detect_content_type(attachment), expected)

    def test_voice_note_transcode_detection_for_browser_audio(self):
        self.assertFalse(_requires_voice_note_transcode(
            "audio/ogg",
            {"codec_name": "opus", "format_name": "ogg"},
        ))
        self.assertTrue(_requires_voice_note_transcode(
            "audio/ogg",
            {"codec_name": "vorbis", "format_name": "ogg"},
        ))
        self.assertFalse(_requires_voice_note_transcode(
            "audio/mp4",
            {"codec_name": "aac", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        ))
        self.assertTrue(_requires_voice_note_transcode(
            "audio/mp4",
            {"codec_name": "opus", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        ))
        self.assertTrue(_requires_voice_note_transcode(
            "audio/webm",
            {"codec_name": "opus", "format_name": "matroska,webm"},
        ))

    @patch(
        "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message."
        "whatsapp_message.WhatsAppMessage._check_consent"
    )
    @patch(
        "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message."
        "whatsapp_message.get_service_window_status",
        return_value=(True, ""),
    )
    @patch(
        "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message."
        "whatsapp_message.WhatsAppMessage._upload_local_audio_to_whatsapp",
        return_value="test-media-id",
    )
    @patch(
        "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message."
        "whatsapp_message.WhatsAppMessage.notify"
    )
    @patch(
        "whatsapp_chat.api.message._transcode_voice_note_to_ogg",
        side_effect=lambda *, room, attachment: attachment,
    )
    def test_send_voice_note_inserts_audio_without_file_url_caption(
        self,
        _mock_transcode,
        _mock_notify,
        _mock_upload_media,
        _mock_service_window,
        _mock_check_consent,
    ):
        self._create_account()
        contact = self._create_contact()
        file_doc = self._create_file(contact=contact)

        result = send_voice_note(
            room=contact.name,
            attachment=file_doc.file_url,
            mime_type="audio/ogg; codecs=opus",
        )

        self.assertEqual(result["content_type"], "audio")
        self.assertEqual(result["caption"], None)

        message_name = frappe.db.get_value(
            "WhatsApp Message",
            {
                "to": contact.mobile_no,
                "content_type": "audio",
                "attach": file_doc.file_url,
            },
            "name",
        )
        self.assertTrue(message_name)

        message_doc = frappe.get_doc("WhatsApp Message", message_name)
        self.assertEqual(message_doc.message, "")
        self.assertEqual(message_doc.attach, file_doc.file_url)
        if message_doc.meta.has_field("is_voice_note"):
            self.assertEqual(message_doc.is_voice_note, 1)

        contact.reload()
        self.assertEqual(contact.last_message, "Voice note")

    def test_get_all_returns_audio_content_and_empty_caption(self):
        account = self._create_account()
        contact = self._create_contact()
        file_doc = self._create_file(contact=contact)

        message_doc = frappe.get_doc({
            "doctype": "WhatsApp Message",
            "type": "Incoming",
            "from": contact.mobile_no,
            "message_id": f"wamid.{frappe.generate_hash(length=8)}",
            "message": "",
            "content_type": "audio",
            "attach": file_doc.file_url,
            "whatsapp_account": account.name,
        })
        if message_doc.meta.has_field("is_voice_note"):
            message_doc.is_voice_note = 1
        message_doc.insert(ignore_permissions=True)

        messages = get_all(contact.name)
        audio_messages = [
            message for message in messages
            if message.content_type == "audio"
            and message.content == file_doc.file_url
        ]

        self.assertEqual(len(audio_messages), 1)
        self.assertEqual(audio_messages[0].caption, None)
        self.assertEqual(audio_messages[0].attachment_mime_type, "audio/ogg")
        self.assertEqual(audio_messages[0].is_voice_note, 1)
