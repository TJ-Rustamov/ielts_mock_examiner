import asyncio
from unittest.mock import patch

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from ielts_backend.asgi import application
from speaking_app.models import SpeakingSession


class SpeakingConsumerTests(TransactionTestCase):
    async_capable = True

    @patch("speaking_app.consumers.KokoroClient.stream_audio_chunks")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_quick_scores")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_final_report")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_turn")
    @patch("speaking_app.consumers.FasterWhisperClient.transcribe_stream_buffer")
    def test_websocket_start_and_stop_flow(self, mock_stt, mock_turn, mock_report, mock_quick_scores, mock_tts_stream):
        mock_stt.return_value = "My full name is Alex Doe."
        mock_turn.return_value = {"examiner_text": "Where are you from?", "part": "ongoing"}
        mock_quick_scores.return_value = {"fc": 7.0, "lr": 7.0, "gra": 6.5, "overall_band": 6.8}
        mock_report.return_value = {
            "scores": {"fc": 7.0, "lr": 7.0, "gra": 6.5, "overall_band": 6.8},
            "analysis": {},
            "examiner_comments": "Solid performance",
        }
        mock_tts_stream.side_effect = [
            iter([b"RIFFgreeting_part1", b"RIFFgreeting_part2"]),
            iter([b"RIFFfollowup_part1"]),
        ]

        async def run_flow():
            communicator = WebsocketCommunicator(application, "/ws/speaking/test")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_json_to({"type": "session.start", "payload": {"part": "all", "candidate": {"name": "Alex"}}})
            started = await communicator.receive_json_from()
            self.assertEqual(started["type"], "session.started")

            turn_state = await communicator.receive_json_from()
            self.assertEqual(turn_state["type"], "turn.state")
            self.assertEqual(turn_state["payload"]["state"], "examiner_speaking")

            examiner_text = await communicator.receive_json_from()
            self.assertEqual(examiner_text["type"], "examiner.text")

            examiner_audio = await communicator.receive_json_from()
            self.assertEqual(examiner_audio["type"], "examiner.audio.chunk")
            self.assertEqual(examiner_audio["payload"]["seq"], 0)
            self.assertFalse(examiner_audio["payload"]["is_last"])
            chunk_id = examiner_audio["payload"]["chunk_id"]

            examiner_audio = await communicator.receive_json_from()
            self.assertEqual(examiner_audio["type"], "examiner.audio.chunk")
            self.assertEqual(examiner_audio["payload"]["seq"], 1)
            self.assertTrue(examiner_audio["payload"]["is_last"])
            self.assertEqual(examiner_audio["payload"]["chunk_id"], chunk_id)

            done = await communicator.receive_json_from()
            self.assertEqual(done["type"], "examiner.audio.done")
            self.assertEqual(done["payload"]["chunk_id"], chunk_id)

            self.assertTrue(await communicator.receive_nothing(timeout=0.05))
            await communicator.send_json_to(
                {
                    "type": "examiner.audio.playback_done",
                    "payload": {"chunk_id": chunk_id},
                }
            )

            turn_state = await communicator.receive_json_from()
            self.assertEqual(turn_state["type"], "turn.state")
            self.assertEqual(turn_state["payload"]["state"], "candidate_speaking")

            await communicator.send_json_to(
                {
                    "type": "audio.chunk",
                    "payload": {"audio_base64": "UklGRjEyMzQ=", "force_transcribe": True},
                }
            )

            turn_state = await communicator.receive_json_from()
            self.assertEqual(turn_state["type"], "turn.state")
            self.assertEqual(turn_state["payload"]["state"], "processing_candidate")

            transcript_msg = await communicator.receive_json_from()
            self.assertEqual(transcript_msg["type"], "transcript.final")

            turn_state = await communicator.receive_json_from()
            self.assertEqual(turn_state["type"], "turn.state")
            self.assertEqual(turn_state["payload"]["state"], "examiner_speaking")

            follow_up_text = await communicator.receive_json_from()
            self.assertEqual(follow_up_text["type"], "examiner.text")
            follow_up_audio = await communicator.receive_json_from()
            self.assertEqual(follow_up_audio["type"], "examiner.audio.chunk")
            self.assertEqual(follow_up_audio["payload"]["seq"], 0)
            self.assertTrue(follow_up_audio["payload"]["is_last"])
            follow_up_chunk_id = follow_up_audio["payload"]["chunk_id"]
            done = await communicator.receive_json_from()
            self.assertEqual(done["type"], "examiner.audio.done")
            self.assertEqual(done["payload"]["chunk_id"], follow_up_chunk_id)
            await communicator.send_json_to(
                {
                    "type": "examiner.audio.playback_done",
                    "payload": {"chunk_id": follow_up_chunk_id},
                }
            )

            turn_state = await communicator.receive_json_from()
            self.assertEqual(turn_state["type"], "turn.state")
            self.assertEqual(turn_state["payload"]["state"], "candidate_speaking")

            await communicator.send_json_to({"type": "session.stop", "payload": {}})
            turn_state = await communicator.receive_json_from()
            self.assertEqual(turn_state["type"], "turn.state")
            self.assertEqual(turn_state["payload"]["state"], "finished")

            partial = await communicator.receive_json_from()
            self.assertEqual(partial["type"], "session.report.partial")
            self.assertIn("scores", partial["payload"])

            final = await communicator.receive_json_from()
            self.assertEqual(final["type"], "session.report.final")

            await communicator.disconnect()

        asyncio.run(run_flow())

        self.assertEqual(SpeakingSession.objects.count(), 1)
        session = SpeakingSession.objects.first()
        self.assertEqual(session.status, "finished")
        self.assertIn("overall_band", session.scores)

    @patch.dict("os.environ", {"TTS_PLAYBACK_ACK_TIMEOUT_MS": "20"})
    @patch("speaking_app.consumers.KokoroClient.stream_audio_chunks")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_quick_scores")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_final_report")
    @patch("speaking_app.consumers.GeminiClient.generate_speaking_turn")
    def test_candidate_turn_opens_after_ack_timeout(self, mock_turn, mock_report, mock_quick_scores, mock_tts_stream):
        mock_turn.return_value = {"examiner_text": "Tell me about your hometown.", "part": "ongoing"}
        mock_quick_scores.return_value = {"fc": 7.0, "lr": 7.0, "gra": 6.5, "overall_band": 6.8}
        mock_report.return_value = {
            "scores": {"fc": 7.0, "lr": 7.0, "gra": 6.5, "overall_band": 6.8},
            "analysis": {},
            "examiner_comments": "Solid performance",
        }
        mock_tts_stream.return_value = iter([b"RIFFsinglechunk"])

        async def run_flow():
            communicator = WebsocketCommunicator(application, "/ws/speaking/test")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            await communicator.send_json_to({"type": "session.start", "payload": {"part": "all", "candidate": {"name": "Alex"}}})
            _started = await communicator.receive_json_from()
            _turn_state = await communicator.receive_json_from()
            _examiner_text = await communicator.receive_json_from()
            chunk = await communicator.receive_json_from()
            self.assertEqual(chunk["type"], "examiner.audio.chunk")
            done = await communicator.receive_json_from()
            self.assertEqual(done["type"], "examiner.audio.done")

            # Do not send playback ack; consumer should continue after timeout.
            turn_state = await communicator.receive_json_from()
            self.assertEqual(turn_state["type"], "turn.state")
            self.assertEqual(turn_state["payload"]["state"], "candidate_speaking")

            await communicator.disconnect()

        asyncio.run(run_flow())
