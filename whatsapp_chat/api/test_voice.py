from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from whatsapp_chat.api.voice import (
    normalize_voice_note_to_ogg,
    probe_voice_note,
)


class TestVoiceNoteNormalization(FrappeTestCase):
    def setUp(self):
        suffix = frappe.generate_hash(length=8)
        self.contact = frappe.get_doc(
            {
                "doctype": "Messenger Contact",
                "sender_id": f"voice-sender-{suffix}",
                "connection": f"voice-connection-{suffix}",
                "channel": "Messenger",
                "contact_name": "Voice Test",
            }
        ).insert(ignore_permissions=True, ignore_links=True)

    def test_normalizes_to_private_ogg_opus_profile(self):
        uploaded = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": f"browser-{frappe.generate_hash(length=8)}.webm",
                "attached_to_doctype": "Messenger Contact",
                "attached_to_name": self.contact.name,
                "content": b"browser audio",
                "is_private": 1,
            }
        ).save(ignore_permissions=True)

        def fake_ffmpeg(command, **_kwargs):
            with open(command[-1], "wb") as output:
                output.write(b"normalized ogg opus")
            return MagicMock(stdout=b"", stderr=b"")

        with patch(
            "whatsapp_chat.api.voice.probe_voice_note",
            return_value={
                "codec_name": "opus",
                "format_name": "matroska,webm",
                "sample_rate": "48000",
                "channels": 1,
                "duration": 1.0,
            },
        ), patch(
            "whatsapp_chat.api.voice.shutil.which",
            return_value="/usr/bin/ffmpeg",
        ), patch(
            "whatsapp_chat.api.voice.subprocess.run",
            side_effect=fake_ffmpeg,
        ) as mock_run:
            normalized = normalize_voice_note_to_ogg(
                attachment=str(uploaded.file_url),
                attached_to_doctype="Messenger Contact",
                attached_to_name=str(self.contact.name),
                max_bytes=1024,
                log_prefix="Test voice note",
            )

        command = mock_run.call_args.args[0]
        self.assertIn("libopus", command)
        self.assertIn("48000", command)
        self.assertIn("64k", command)
        self.assertEqual(normalized.is_private, 1)
        self.assertTrue(str(normalized.file_name).endswith(".ogg"))
        self.assertEqual(normalized.get_content(), b"normalized ogg opus")

    @patch(
        "whatsapp_chat.api.voice.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    @patch("whatsapp_chat.api.voice.subprocess.run")
    def test_probe_rejects_recordings_with_video(
        self,
        mock_run,
        _mock_which,
    ):
        mock_run.return_value = SimpleNamespace(
            stdout=json.dumps(
                {
                    "streams": [
                        {"codec_type": "audio", "codec_name": "opus"},
                        {"codec_type": "video", "codec_name": "vp9"},
                    ],
                    "format": {"format_name": "matroska,webm"},
                }
            ).encode(),
            stderr=b"",
        )
        file_doc = SimpleNamespace(get_full_path=lambda: "/tmp/fake.webm")

        with self.assertRaises(frappe.ValidationError):
            probe_voice_note(file_doc, log_prefix="Test voice note")
