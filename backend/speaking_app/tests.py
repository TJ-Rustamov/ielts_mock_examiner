import asyncio
from unittest.mock import patch

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from ielts_backend.asgi import application
from speaking_app.models import SpeakingSession


class SpeakingConsumerTests(TransactionTestCase):
    async_capable = True

    @patch("speaking_app.consumers.KokoroClient.generate_audio")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_final_report")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_turn")
    @patch("speaking_app.consumers.FasterWhisperClient.transcribe_stream_buffer")
    def test_websocket_start_and_stop_flow(self, mock_stt, mock_turn, mock_report, mock_tts):
        mock_stt.return_value = "My full name is Alex Doe."
        mock_turn.return_value = {"examiner_text": "Where are you from?", "part": "ongoing"}
        mock_report.return_value = {
            "scores": {"fc": 7.0, "lr": 7.0, "gra": 6.5, "overall_band": 6.8},
            "analysis": {},
            "examiner_comments": "Solid performance",
        }
        mock_tts.return_value = b"RIFFfakeWAV"

        async def run_flow():
            communicator = WebsocketCommunicator(application, "/ws/speaking/test")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_json_to({"type": "session.start", "payload": {"part": "all", "candidate": {"name": "Alex"}}})
            started = await communicator.receive_json_from()
            self.assertEqual(started["type"], "session.started")

            examiner_text = await communicator.receive_json_from()
            self.assertEqual(examiner_text["type"], "examiner.text")

            examiner_audio = await communicator.receive_json_from()
            self.assertEqual(examiner_audio["type"], "examiner.audio")

            await communicator.send_json_to(
                {
                    "type": "audio.chunk",
                    "payload": {"audio_base64": "UklGRjEyMzQ=", "force_transcribe": True},
                }
            )

            transcript_msg = await communicator.receive_json_from()
            self.assertEqual(transcript_msg["type"], "transcript.final")

            follow_up_text = await communicator.receive_json_from()
            self.assertEqual(follow_up_text["type"], "examiner.text")
            follow_up_audio = await communicator.receive_json_from()
            self.assertEqual(follow_up_audio["type"], "examiner.audio")

            await communicator.send_json_to({"type": "session.stop", "payload": {}})
            report = await communicator.receive_json_from()
            self.assertEqual(report["type"], "session.report")

            await communicator.disconnect()

        asyncio.run(run_flow())

        self.assertEqual(SpeakingSession.objects.count(), 1)
        session = SpeakingSession.objects.first()
        self.assertEqual(session.status, "finished")
        self.assertIn("overall_band", session.scores)