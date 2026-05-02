from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import SimpleTestCase

from ai_services.gemini_client import GeminiClient
from ai_services.stt_client import FasterWhisperClient
from ai_services.tts_client import KokoroClient
from ai_services.utils import extract_json_from_text
from ai_services.vad_service import VADService


class ParserTests(SimpleTestCase):
    def test_extract_json_plain(self):
        data = extract_json_from_text('{"scores": {"tr": 7}}')
        self.assertEqual(data["scores"]["tr"], 7)

    def test_extract_json_markdown_wrapped(self):
        data = extract_json_from_text('```json\n{"scores": {"ta": 6.5}}\n```')
        self.assertEqual(data["scores"]["ta"], 6.5)

    def test_extract_json_embedded_in_text(self):
        payload = 'Here is your result:\\n```json\\n{"scores":{"fc":7}}\\n```\\nThanks.'
        data = extract_json_from_text(payload)
        self.assertEqual(data["scores"]["fc"], 7)

    def test_extract_json_invalid_raises(self):
        with self.assertRaises(ValueError):
            extract_json_from_text("no json here")


class STTClientTests(SimpleTestCase):
    def test_transcribe_audio_bytes_with_mocked_model(self):
        class Segment:
            def __init__(self, text):
                self.text = text

        client = FasterWhisperClient()
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([Segment("hello"), Segment("world")], None)
        client.__dict__["model"] = fake_model

        text = client.transcribe_audio_bytes(b"RIFF....")
        self.assertEqual(text, "hello world")

    @patch("ai_services.stt_client.os.path.exists")
    def test_normalize_model_source_maps_windows_models_path(self, mock_exists):
        client = FasterWhisperClient()
        client.model_size = "D:/university/models/faster-whisper-base.en"

        def exists_side_effect(path):
            return path == "/models/faster-whisper-base.en"

        mock_exists.side_effect = exists_side_effect
        self.assertEqual(client._normalize_model_source(), "/models/faster-whisper-base.en")


class GeminiClientTests(SimpleTestCase):
    def test_generate_speaking_final_report_requires_valid_scores(self):
        client = GeminiClient()
        client.speaking_model = "test-model"
        client._generate_json = lambda _prompt, task: {"analysis": {}, "examiner_comments": "ok"}  # type: ignore[assignment]

        with self.assertRaises(ValueError):
            client.generate_speaking_final_report([{"role": "user", "content": "hello"}])


class TTSClientTests(SimpleTestCase):
    def test_generate_audio_returns_wav_bytes(self):
        audio = KokoroClient().generate_audio("Hello there")
        self.assertTrue(audio.startswith(b"RIFF"))

    def test_stream_audio_chunks_returns_wav_chunks(self):
        chunks = list(KokoroClient().stream_audio_chunks("Hello there. How are you today?"))
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(chunks[0].startswith(b"RIFF"))


class VADServiceTests(SimpleTestCase):
    def test_detect_end_of_speech_after_silence(self):
        service = VADService(mode=2, silence_frames_to_end=3)
        decisions = iter([True, False, False, False])
        service.vad.is_speech = lambda _f, _sr: next(decisions)

        chunk = b"\x00" * service.frame_bytes * 4
        self.assertTrue(service.detect_end_of_speech(chunk))
