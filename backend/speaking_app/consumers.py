import base64
from datetime import timedelta
import json
import os
from io import BytesIO

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone
from rest_framework.authtoken.models import Token

from ai_services.gemini_client import GeminiClient
from ai_services.stt_client import FasterWhisperClient
from ai_services.tts_client import KokoroClient
from ai_services.vad_service import VADService
from speaking_app.models import SpeakingSession


class SpeakingTestConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.gemini_client = GeminiClient()
        self.stt_client = FasterWhisperClient()
        self.tts_client = KokoroClient()
        self.vad_service = VADService(
            mode=int(os.getenv("VAD_MODE", "2")),
            silence_frames_to_end=int(os.getenv("VAD_SILENCE_FRAMES", "12")),
        )

        self.audio_buffer = BytesIO()
        self.conversation_history = []
        self.session = None
        self.session_id = None
        self.processing_audio = False
        self.stop_requested = False
        self.prep_until = None
        self.speaking_until = None
        self.prep_seconds = 0
        self.speaking_seconds = int(os.getenv("SPEAKING_SECONDS_ALL", "840"))

        await self.accept()

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type")
        payload = content.get("payload", {})

        try:
            if message_type == "session.start":
                await self._handle_session_start(payload)
            elif message_type == "audio.chunk":
                await self._handle_audio_chunk(payload)
            elif message_type == "session.stop":
                await self._handle_session_stop()
            else:
                await self._send_error(f"Unsupported message type: {message_type}")
        except Exception as exc:
            await self._send_error(str(exc))

    async def disconnect(self, close_code):
        if self.session and self.session.status == "active":
            await self._persist_session(status="disconnected")

    async def _handle_session_start(self, payload):
        part = payload.get("part", "all")
        metadata = payload.get("candidate", {})
        token_key = payload.get("token")
        self.prep_seconds, self.speaking_seconds = self._get_part_timing(part)
        now = timezone.now()
        if self.prep_seconds > 0:
            self.prep_until = now + timedelta(seconds=self.prep_seconds)
            self.speaking_until = self.prep_until + timedelta(seconds=self.speaking_seconds)
        elif self.speaking_seconds > 0:
            self.prep_until = None
            self.speaking_until = now + timedelta(seconds=self.speaking_seconds)
        else:
            self.prep_until = None
            self.speaking_until = None

        user_id = None
        username = None
        if token_key:
            token_obj = await sync_to_async(Token.objects.filter(key=token_key).select_related("user").first)()
            if token_obj:
                user_id = token_obj.user_id
                username = token_obj.user.username

        self.session = await sync_to_async(SpeakingSession.objects.create)(
            part=part,
            candidate_metadata={**metadata, "user_id": user_id, "username": username},
            status="active",
        )
        self.session_id = str(self.session.id)

        greeting = "Good day. My name is Examiner Smith and I will be your examiner today. Can you tell me your full name?"
        self.conversation_history.append({"role": "assistant", "content": greeting})

        await self.send_json(
            {
                "type": "session.started",
                "session_id": self.session_id,
                "payload": {
                    "part": part,
                    "timers": {
                        "prep_seconds": self.prep_seconds,
                        "speaking_seconds": self.speaking_seconds,
                    },
                },
            }
        )
        await self._send_examiner_turn(greeting)

    async def _handle_audio_chunk(self, payload):
        if not self.session:
            await self._send_error("Session is not started")
            return
        if self.stop_requested:
            return
        if self.processing_audio:
            return

        audio_b64 = payload.get("audio_base64") or payload.get("audio")
        if not audio_b64:
            await self._send_error("Missing audio_base64 in payload")
            return
        now = timezone.now()
        if self.prep_until and now < self.prep_until:
            seconds_left = max(0, int((self.prep_until - now).total_seconds()))
            await self.send_json(
                {
                    "type": "timer.update",
                    "session_id": self.session_id,
                    "payload": {"phase": "prep", "seconds_left": seconds_left},
                }
            )
            return

        if self.speaking_until and now >= self.speaking_until:
            await self._finalize_session()
            return

        mime_type = str(payload.get("mime_type", "audio/wav")).lower()
        is_pcm = "audio/pcm" in mime_type or "audio/raw" in mime_type
        try:
            sample_rate = int(payload.get("sample_rate", 16000))
        except (TypeError, ValueError):
            sample_rate = 16000

        chunk = base64.b64decode(audio_b64)
        self.audio_buffer.write(chunk)

        force_transcribe = bool(payload.get("force_transcribe", False))
        end_of_speech = False
        if is_pcm and not force_transcribe:
            end_of_speech = self.vad_service.detect_end_of_speech(chunk, sample_rate=sample_rate)
            # Safety flush: do not wait forever if VAD misses a boundary.
            max_pcm_seconds = float(os.getenv("PCM_FORCE_TRANSCRIBE_SECONDS", "6"))
            if len(self.audio_buffer.getvalue()) >= int(sample_rate * 2 * max_pcm_seconds):
                force_transcribe = True
        if not (force_transcribe or end_of_speech):
            return

        self.processing_audio = True
        try:
            raw_audio = self.audio_buffer.getvalue()
            self.audio_buffer = BytesIO()

            if is_pcm:
                transcript = await sync_to_async(self.stt_client.transcribe_pcm16_bytes, thread_sensitive=False)(
                    raw_audio, sample_rate
                )
            else:
                file_extension = ".webm" if "webm" in mime_type else ".wav"
                transcript = await sync_to_async(self.stt_client.transcribe_stream_buffer, thread_sensitive=False)(
                    BytesIO(raw_audio), file_extension=file_extension
                )

            transcript = transcript.strip()
            if not transcript:
                return

            # Ignore common noise/echo artifacts so the examiner doesn't advance by itself.
            words = [w for w in transcript.split() if w.strip()]
            if len(words) < 2 and len(transcript) < 8:
                return

            self.conversation_history.append({"role": "user", "content": transcript})
            await self.send_json(
                {
                    "type": "transcript.final",
                    "session_id": self.session_id,
                    "payload": {"text": transcript},
                }
            )

            turn = await sync_to_async(self.gemini_client.generate_speaking_turn, thread_sensitive=False)(self.conversation_history)
            examiner_text = str(turn.get("examiner_text", "Can you explain that a bit more?"))
            self.conversation_history.append({"role": "assistant", "content": examiner_text})

            await self._send_examiner_turn(examiner_text)

            if turn.get("part") == "finished":
                await self._finalize_session()
        finally:
            self.processing_audio = False

    async def _handle_session_stop(self):
        if not self.session:
            await self._send_error("Session is not started")
            return
        self.stop_requested = True

        await self._finalize_session()

    def _get_part_timing(self, part: str) -> tuple[int, int]:
        normalized = str(part).strip().lower()
        if normalized == "2":
            return int(os.getenv("PREP_SECONDS_PART2", "60")), int(os.getenv("SPEAKING_SECONDS_PART2", "120"))
        return 0, 0

    async def _send_examiner_turn(self, text: str):
        if self.stop_requested:
            return
        audio_bytes = await sync_to_async(self.tts_client.generate_audio, thread_sensitive=False)(text)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        await self.send_json(
            {
                "type": "examiner.text",
                "session_id": self.session_id,
                "payload": {"text": text},
            }
        )
        await self.send_json(
            {
                "type": "examiner.audio",
                "session_id": self.session_id,
                "payload": {"audio_base64": audio_b64, "format": "wav"},
            }
        )

    async def _finalize_session(self):
        report = await sync_to_async(self.gemini_client.generate_speaking_final_report, thread_sensitive=False)(
            self.conversation_history
        )

        transcript = "\n".join([
            f"{item['role']}: {item['content']}" for item in self.conversation_history if item["role"] in {"assistant", "user"}
        ])

        await self._persist_session(status="finished", transcript=transcript, report=report)

        await self.send_json(
            {
                "type": "session.report",
                "session_id": self.session_id,
                "payload": report,
            }
        )
        await self.close()

    async def _persist_session(self, status: str, transcript: str | None = None, report: dict | None = None):
        self.session.status = status
        self.session.conversation_history = self.conversation_history
        if transcript is not None:
            self.session.transcript = transcript
        if report is not None:
            self.session.final_report = report
            self.session.scores = report.get("scores", {})
        await sync_to_async(self.session.save)()

    async def _send_error(self, message: str):
        await self.send_json(
            {
                "type": "error",
                "session_id": self.session_id,
                "payload": {"message": message},
            }
        )
