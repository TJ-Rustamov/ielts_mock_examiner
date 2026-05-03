import asyncio
import base64
from datetime import timedelta
import os
import json
import re
from io import BytesIO
from uuid import uuid4

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
        self.turn_state = "processing_candidate"
        self.turn_blocked_emitted = False
        self.prep_until = None
        self.speaking_until = None
        self.prep_seconds = 0
        self.speaking_seconds = int(os.getenv("SPEAKING_SECONDS_ALL", "840"))
        self.turn_end_silence_ms = int(os.getenv("TURN_END_SILENCE_MS", "650"))
        self.turn_min_speech_ms = int(os.getenv("TURN_MIN_SPEECH_MS", "400"))
        self.turn_post_examiner_guard_ms = int(os.getenv("TURN_POST_EXAMINER_GUARD_MS", "250"))
        self.tts_playback_ack_timeout_ms = int(os.getenv("TTS_PLAYBACK_ACK_TIMEOUT_MS", "45000"))
        self.pending_playback_chunk_id = None
        self.playback_timeout_task = None
        self.final_report_task = None

        # --- Part 1 specific ---
        self.part1_state = "none" # "none", "greeting", "asking_question", "evaluating"
        self.part1_current_topic = None
        self.part1_topic_questions = []
        self.part1_questions_asked = 0
        self.part1_total_questions_asked = 0
        self.candidate_name = ""

        # --- Part 2 specific ---
        self.part2_state = "none" # "none", "waiting_for_prep", "prep_active", "speaking_active", "done"
        self.part2_prep_task = None
        self.part2_speaking_task = None
        self.last_examiner_text = ""
        self.last_sample_rate = 16000
        self.last_is_pcm = True
        self.last_mime_type = "audio/wav"
        self.part2_current_topic = None

        # --- Part 3 specific ---
        self.part3_state = "none"
        self.part3_current_topic = None
        self.part3_topic_questions = []
        self.part3_questions_asked = 0

        # --- Dynamic Endpointing & Barge-in state ---
        self.is_user_speaking = False
        self.user_speech_duration_ms = 0
        self.silence_timer_ms = 0
        self.current_partial_transcript = ""
        self.interrupt_requested = False
        self.examiner_started_at = None
        
        await self.accept()

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type")
        payload = content.get("payload", {})

        try:
            if message_type == "session.start":
                await self._handle_session_start(payload)
            elif message_type == "audio.chunk":
                await self._handle_audio_chunk(payload)
            elif message_type == "examiner.audio.playback_done":
                await self._handle_playback_done(payload)
            elif message_type == "session.stop":
                await self._handle_session_stop()
            elif message_type == "timer.skip_prep":
                await self._handle_skip_prep()
            elif message_type == "timer.stop_speaking":
                await self._handle_stop_speaking()
            else:
                await self._send_error(f"Unsupported message type: {message_type}")
        except Exception as exc:
            await self._send_error(str(exc))

    async def disconnect(self, close_code):
        if self.playback_timeout_task:
            self.playback_timeout_task.cancel()
            self.playback_timeout_task = None
        if self.session and self.session.status == "active":
            await self._persist_session(status="disconnected")

    @sync_to_async
    def _fetch_random_part1_topic(self, exclude_topic=None, limit: int = 1):
        import random
        from core.models import SpeakingQuestion
        
        # Get all distinct topics for Part 1
        topics = list(SpeakingQuestion.objects.filter(part=1, is_active=True).values_list("topic", flat=True).distinct())
        if exclude_topic and exclude_topic in topics:
            topics.remove(exclude_topic)
            
        if not topics:
            # Fallback if no other topics available
            topics = list(SpeakingQuestion.objects.filter(part=1, is_active=True).values_list("topic", flat=True).distinct())
            
        if not topics:
            return None, []
            
        topic = random.choice(topics)
        
        # Get questions for this topic
        topic_qs = SpeakingQuestion.objects.filter(part=1, topic=topic, is_active=True)
        all_questions = []
        for tq in topic_qs:
            questions_list = tq.questions
            if isinstance(questions_list, str):
                try:
                    questions_list = json.loads(questions_list)
                except Exception:
                    questions_list = []
            
            if not isinstance(questions_list, list):
                continue
                
            for q in questions_list:
                if isinstance(q, dict):
                    all_questions.append(q.get("text", ""))
                else:
                    all_questions.append(str(q))
                
        # Randomly select between 1 to 4 questions
        random.shuffle(all_questions)
        num_questions = random.randint(1, min(4, max(1, len(all_questions))))
        selected = all_questions[:num_questions]
        
        return topic, selected

    @sync_to_async
    def _fetch_random_part2_topic(self):
        import random
        from core.models import SpeakingQuestion
        
        qs = list(SpeakingQuestion.objects.filter(part=2, is_active=True))
        if not qs:
            return None, "Describe a memorable event in your life."
            
        q = random.choice(qs)
        
        # Format the cue card
        text = f"{q.cue_card}\n\n"
        points_list = q.points
        if isinstance(points_list, str):
            try:
                points_list = json.loads(points_list)
            except Exception:
                points_list = []
                
        if isinstance(points_list, list):
            for p in points_list:
                if isinstance(p, dict):
                    text += f"- {p.get('text', '')}\n"
                else:
                    text += f"- {str(p)}\n"
            
        return q.topic, text

    @sync_to_async
    def _fetch_random_part3_topic(self, part2_topic=None):
        import random
        from core.models import SpeakingQuestion
        
        qs = SpeakingQuestion.objects.filter(part=3, is_active=True)
        
        # Try to match the part 2 topic if provided, otherwise random
        if part2_topic:
            # Simple keyword matching
            matched = [q for q in qs if part2_topic.lower() in q.topic.lower() or q.topic.lower() in part2_topic.lower()]
            if matched:
                q = random.choice(matched)
            elif list(qs):
                q = random.choice(list(qs))
            else:
                return None, []
        elif list(qs):
            q = random.choice(list(qs))
        else:
            return None, []
            
        all_questions = []
        questions_list = q.questions
        if isinstance(questions_list, str):
            try:
                questions_list = json.loads(questions_list)
            except Exception:
                questions_list = []
                
        if isinstance(questions_list, list):
            for p in questions_list:
                if isinstance(p, dict):
                    all_questions.append(p.get("text", ""))
                else:
                    all_questions.append(str(p))
            
        random.shuffle(all_questions)
        # Ask 3-6 questions in part 3
        num_questions = random.randint(3, min(6, max(3, len(all_questions))))
        selected = all_questions[:num_questions]
        
        return q.topic, selected

    async def _handle_session_start(self, payload):
        part = payload.get("part", "all")
        metadata = payload.get("candidate", {})
        token_key = payload.get("token")
        self.prep_seconds, self.speaking_seconds = self._get_part_timing(part)
        
        # We handle prep and speaking timing explicitly in Part 2 state machine now.
        self.prep_until = None
        self.speaking_until = None

        user_id = None
        username = None
        if token_key:
            token_obj = await sync_to_async(Token.objects.filter(key=token_key).select_related("user").first)()
            if token_obj:
                user_id = token_obj.user_id
                username = token_obj.user.username

        if part == "1" or part == "all":
            self.part1_state = "greeting"
            # Pre-fetch the first topic so it's ready
            topic, questions = await self._fetch_random_part1_topic()
            self.part1_current_topic = topic
            self.part1_topic_questions = questions
            self.part1_questions_asked = 0
            print(f"[DEBUG PART 1 START] Selected Topic: {topic}")
            print(f"[DEBUG PART 1 START] Selected Questions: {questions}")
        else:
            self.part1_state = "none"

        if part == "2" or part == "all":
            if part == "2":
                self.part2_state = "greeting"
            else:
                self.part2_state = "none"
                
            p2_topic, p2_text = await self._fetch_random_part2_topic()
            self.part2_current_topic = p2_topic
            self.part2_pregenerated_cue_card = {"text": p2_text, "audio_chunks": []}
            print(f"[DEBUG PART 2 START] Selected Topic: {p2_topic}")
            print(f"[DEBUG PART 2 START] Cue Card:\n{p2_text}")
        else:
            self.part2_state = "none"
            
        if part == "3" or part == "all":
            if part == "3":
                self.part3_state = "asking_question"
            else:
                self.part3_state = "none"
                
            p3_topic, p3_questions = await self._fetch_random_part3_topic(part2_topic=self.part2_current_topic)
            self.part3_current_topic = p3_topic
            self.part3_topic_questions = p3_questions
            self.part3_questions_asked = 0
            print(f"[DEBUG PART 3 START] Selected Topic: {p3_topic}")
            print(f"[DEBUG PART 3 START] Selected Questions: {p3_questions}")
        else:
            self.part3_state = "none"

        self.session = await sync_to_async(SpeakingSession.objects.create)(
            part=part,
            candidate_metadata={**metadata, "user_id": user_id, "username": username},
            status="active",
        )
        self.session_id = str(self.session.id)

        greeting_audio_file = "greeting.wav"
        if part == "all":
            greeting = "Hi. I am your AI mock IELTS examiner and I will be conducting your test. To start could you please tell me about yourself?"
            greeting_audio_file = "greeting.wav"
        elif part == "1":
            greeting = "Good day. I am your AI mock IELTS examiner for today. We will now conduct Part 1 of the speaking test. Could you please tell me about yourself?"
            greeting_audio_file = "greeting_part1.wav"
        elif part == "2":
            greeting = "Good day. I am your AI mock IELTS examiner for today. We will now conduct Part 2 of the speaking test. Let's begin."
            greeting_audio_file = "greeting_part2.wav"
        elif part == "3":
            greeting = "Good day. I am your AI mock IELTS examiner for today. We will now begin Part 3 of the speaking test."
            greeting_audio_file = "greeting_part3.wav"
        else:
            greeting = "Hi. I am your AI mock IELTS examiner and I will be conducting your test. To start could you please tell me about yourself?"

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
                    "turn": {
                        "end_silence_ms": self.turn_end_silence_ms,
                        "min_speech_ms": self.turn_min_speech_ms,
                    },
                },
            }
        )
        
        await self._send_static_audio(greeting_audio_file, greeting)
        
        # We pre-generated the cue card text above.
        # Now we just need to background generate the audio chunks for it using Kokoro TTS
        if part == "2" or part == "all":
            self.cue_card_generation_task = asyncio.create_task(self._generate_cue_card_audio_background())

    async def _send_static_audio(self, filename: str, text: str, force: bool = False):
        if self.stop_requested and not force:
            return

        await self._set_turn_state("examiner_speaking")
        self.examiner_started_at = timezone.now()
        self.interrupt_requested = False
        self._is_playing_static_audio = True
        
        if text:
            await self.send_json({
                "type": "examiner.text.start",
                "session_id": self.session_id,
                "payload": {},
            })
            await self.send_json({
                "type": "examiner.text.chunk",
                "session_id": self.session_id,
                "payload": {"text": text},
            })

        chunk_id = f"{self.session_id}:{uuid4().hex}"
        self.pending_playback_chunk_id = chunk_id
        self.playback_finished_event = asyncio.Event()

        static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static_audio", filename)
        try:
            with open(static_path, "rb") as f:
                audio_bytes = f.read()
        except Exception as e:
            print(f"Static audio {filename} not found: {e}")
            audio_bytes = b""

        if not self.interrupt_requested:
            if audio_bytes:
                await self.send_json({
                    "type": "examiner.audio.chunk",
                    "session_id": self.session_id,
                    "payload": {
                        "chunk_id": chunk_id,
                        "seq": 0,
                        "is_last": True,
                        "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                        "format": "wav",
                    },
                })
            else:
                # Fallback if audio file is missing
                await self.send_json({
                    "type": "examiner.audio.chunk",
                    "session_id": self.session_id,
                    "payload": {
                        "chunk_id": chunk_id,
                        "seq": 0,
                        "is_last": True,
                        "audio_base64": "",
                        "format": "wav",
                    },
                })
                
            await self.send_json({
                "type": "examiner.audio.done",
                "session_id": self.session_id,
                "payload": {"chunk_id": chunk_id},
            })
            self.playback_timeout_task = asyncio.create_task(self._wait_for_playback_timeout(chunk_id))

    async def _send_examiner_greeting(self, text: str):
        await self._send_static_audio("greeting.wav", text)


    def _calculate_dynamic_silence_threshold(self, transcript: str) -> float:
        """Returns silence threshold in seconds based on context."""
        if not transcript:
            return 4.0
            
        words = transcript.lower().split()
        if not words:
            return 4.0
            
        last_word = words[-1].strip(".,?!;")
        
        # Bridge words
        if last_word in ["and", "but", "because", "like", "so", "or", "uh", "um", "well"]:
            return 4.0
            
        # Trailing thought (verbs/prepositions - simplified check)
        trailing = ["is", "are", "was", "were", "to", "in", "on", "at", "for", "with", "about"]
        if last_word in trailing:
            return 3.5
            
        # Finality
        if transcript.endswith((".", "?", "!")):
            return 2.5
            
        return 3.0

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
            
        # Audio chunks no longer emit timer updates to prevent stuttering.
        # Timer tasks (_run_part2_prep_timer / _run_part2_speaking_timer) handle updates.
        
        now = timezone.now()
        if self.prep_until and now < self.prep_until:
            # During prep time, ignore audio chunks
            return
            
        # We handle speaking cutoff purely in the _run_part2_speaking_timer task or manual stop.

        mime_type = str(payload.get("mime_type", "audio/wav")).lower()
        is_pcm = "audio/pcm" in mime_type or "audio/raw" in mime_type
        try:
            sample_rate = int(payload.get("sample_rate", 16000))
        except (TypeError, ValueError):
            sample_rate = 16000

        self.last_sample_rate = sample_rate
        self.last_is_pcm = is_pcm
        self.last_mime_type = mime_type

        chunk = base64.b64decode(audio_b64)
        
        chunk_duration_ms = (len(chunk) / 2) / sample_rate * 1000

        # Continuous VAD Check
        is_speech = False
        if is_pcm:
            try:
                if hasattr(self.vad_service.vad, 'is_speech'):
                    frames = [chunk[i:i+640] for i in range(0, len(chunk), 640) if len(chunk[i:i+640]) == 640]
                    # Require more than one positive frame to reduce noise sensitivity
                    positive_frames = sum(1 for f in frames if self.vad_service.vad.is_speech(f, sample_rate))
                    is_speech = positive_frames >= (len(frames) // 2) if len(frames) > 0 else False
                else:
                    is_speech = any(b != 0 for b in chunk)
            except Exception:
                is_speech = False
        else:
            is_speech = True

        if is_speech:
            self.is_user_speaking = True
            self.silence_timer_ms = 0
            self.user_speech_duration_ms += chunk_duration_ms
        else:
            self.is_user_speaking = False
            self.silence_timer_ms += chunk_duration_ms
            # Only reset speech duration if there's significant silence
            if self.silence_timer_ms > 300:
                self.user_speech_duration_ms = 0

        # Barge-In Logic
        if self.turn_state == "examiner_speaking":
            return

        if self.turn_state == "preparation":
            return

        if self.turn_state != "candidate_speaking":
            return
            
        # Only accumulate audio if user has started speaking
        if self.user_speech_duration_ms > 0 or self.silence_timer_ms < 500:
            self.audio_buffer.write(chunk)

        # Dynamic Endpointing Logic
        force_transcribe = bool(payload.get("force_transcribe", False))
        
        # Get live transcript every 1 second of audio
        raw_audio_len = len(self.audio_buffer.getvalue())
        audio_sec = (raw_audio_len / 2) / sample_rate
        
        should_transcribe = force_transcribe
        
        if self.part2_state == "speaking_active":
            should_transcribe = force_transcribe  # Never transcribe on silence in Part 2 speaking, wait for timer/button
        else:
            speech_ms = self.user_speech_duration_ms
            if speech_ms < 1500:
                dynamic_threshold_s = 1.3  # Very patient for short utterances (e.g. "um...")
            elif speech_ms < 4000:
                dynamic_threshold_s = 1.0  # Medium patience
            else:
                dynamic_threshold_s = 0.8  # Still fairly patient for long speeches to allow gathering thoughts

            if self.silence_timer_ms >= (dynamic_threshold_s * 1000):
                should_transcribe = True

        if not should_transcribe:
            return

        self.processing_audio = True
        try:
            raw_audio = self.audio_buffer.getvalue()
            await self._set_turn_state("processing_candidate")
            
            # Reset counters
            self.silence_timer_ms = 0
            self.user_speech_duration_ms = 0
            self.current_partial_transcript = ""
            
            if not raw_audio:
                await self._set_turn_state("candidate_speaking")
                return

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
                await self._set_turn_state("candidate_speaking")
                return

            words = [w for w in transcript.split() if w.strip()]
            if len(words) < 2 and len(transcript) < 8:
                await self._set_turn_state("candidate_speaking")
                return

            self.conversation_history.append({"role": "user", "content": transcript})
            await self.send_json(
                {
                    "type": "transcript.final",
                    "session_id": self.session_id,
                    "payload": {"text": transcript},
                }
            )

            await self._send_examiner_turn_stream()
            
        finally:
            self.processing_audio = False

    async def _handle_skip_prep(self):
        if self.part2_state != "prep_active":
            return
        if self.part2_prep_task:
            self.part2_prep_task.cancel()
            self.part2_prep_task = None
        
        await self.send_json({
            "type": "timer.update",
            "session_id": self.session_id,
            "payload": {"phase": "prep", "seconds_left": 0}
        })
        self.part2_state = "prep_finished_waiting_for_speech"
        
        # We don't send the text to the history because it's a structural instruction
        await self._send_static_audio("prep_time_up.wav", "")

    async def _handle_stop_speaking(self):
        if self.part2_state != "speaking_active":
            return
        if self.part2_speaking_task:
            self.part2_speaking_task.cancel()
            self.part2_speaking_task = None
            
        self.part2_state = "done"
        await self._force_candidate_cutoff()

    async def _handle_session_stop(self):
        if not self.session:
            await self._send_error("Session is not started")
            return
        self.stop_requested = True
        if self.playback_timeout_task:
            self.playback_timeout_task.cancel()
            self.playback_timeout_task = None
        self.pending_playback_chunk_id = None
        
        if hasattr(self, "playback_finished_event"):
            self.playback_finished_event.set()

        await self._finalize_session_start_background()

    async def _handle_playback_done(self, payload):
        chunk_id = str(payload.get("chunk_id", "")).strip()
        if not chunk_id:
            return
        await self._finish_examiner_playback(chunk_id)

    def _get_part_timing(self, part: str) -> tuple[int, int]:
        normalized = str(part).strip().lower()
        if normalized == "2":
            return int(os.getenv("PREP_SECONDS_PART2", "60")), int(os.getenv("SPEAKING_SECONDS_PART2", "120"))
        return 0, 0

    async def _generate_cue_card_audio_background(self):
        try:
            full_text = self.part2_pregenerated_cue_card.get("text", "")
            if not full_text:
                return

            cleaned_text = full_text.replace("\n", ". ").replace("- ", " ")
            
            audio_bytes = await sync_to_async(self.tts_client.generate_audio, thread_sensitive=False)(cleaned_text)
            if audio_bytes:
                self.part2_pregenerated_cue_card["audio_chunks"] = [(cleaned_text, audio_bytes)]
            else:
                self.part2_pregenerated_cue_card["audio_chunks"] = []
                
            if self.part2_state == "waiting_for_cue_card":
                self.part2_state = "cue_card"
                await self._send_pregenerated_cue_card()
        except Exception as e:
            print(f"Failed to generate cue card audio background: {e}")

    async def _send_pregenerated_cue_card(self):
        if self.stop_requested:
            return

        await self._set_turn_state("examiner_speaking")
        self.examiner_started_at = timezone.now()
        self.interrupt_requested = False
        self._is_playing_static_audio = False
        
        chunk_id = f"{self.session_id}:{uuid4().hex}"
        self.pending_playback_chunk_id = chunk_id
        self.playback_finished_event = asyncio.Event()
        
        cue_card = self.part2_pregenerated_cue_card
        
        await self.send_json({
            "type": "examiner.text.start",
            "session_id": self.session_id,
            "payload": {},
        })
        
        # We don't send character-by-character chunking, we just drop the whole text block
        # The frontend handles it natively. We format it nicely for cue card logic.
        formatted_text = "[PART2] " + cue_card["text"]
        await self.send_json({
            "type": "examiner.text.chunk",
            "session_id": self.session_id,
            "payload": {"text": formatted_text},
        })

        if getattr(self, "cue_card_generation_task", None):
            await self.cue_card_generation_task
            self.cue_card_generation_task = None
        
        seq = 0
        audio_chunks = cue_card["audio_chunks"]
        for idx, (_, audio_bytes) in enumerate(audio_chunks):
            if self.interrupt_requested:
                break
            is_last = (idx == len(audio_chunks) - 1)
            await self.send_json({
                "type": "examiner.audio.chunk",
                "session_id": self.session_id,
                "payload": {
                    "chunk_id": chunk_id,
                    "seq": seq,
                    "is_last": is_last,
                    "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                    "format": "wav",
                },
            })
            seq += 1
            
        if not self.interrupt_requested:
            if not audio_chunks:
                # Fallback if generation completely failed
                await self.send_json({
                    "type": "examiner.audio.chunk",
                    "session_id": self.session_id,
                    "payload": {
                        "chunk_id": chunk_id,
                        "seq": seq,
                        "is_last": True,
                        "audio_base64": "",
                        "format": "wav",
                    },
                })
            await self.send_json({
                "type": "examiner.audio.done",
                "session_id": self.session_id,
                "payload": {"chunk_id": chunk_id},
            })
            self.playback_timeout_task = asyncio.create_task(self._wait_for_playback_timeout(chunk_id))

    async def _send_examiner_turn_stream(self):
        if self.stop_requested:
            return
            
        self.playback_finished_event = asyncio.Event()

        part = str(getattr(self.session, "part", "all")).strip().lower()

        # Part 1 logic check
        if part == "1" or (part == "all" and self.part2_state == "none"):
            # Check if we need to evaluate and transition topic
            if self.part1_state == "greeting":
                # User just responded with their name
                self.part1_state = "asking_question"
                
                # Setup specific question injection
                self.part1_questions_asked += 1
                self.part1_total_questions_asked += 1
                questions_str = json.dumps(self.part1_topic_questions)
                
                if part == "all":
                    forced_q_text = f"The candidate has just introduced themselves. Acknowledge their introduction, naturally introduce the topic '{self.part1_current_topic}' (e.g., 'Now let's talk about {self.part1_current_topic}'), and ask a relevant question dynamically selected from this list of suggested questions: {questions_str}. Formulate it conversationally. Do not hallucinate other topics. Do not mention that you are an AI. Do not prefix with 'Examiner:'."
                else:
                    forced_q_text = f"The candidate has just provided their name. Acknowledge their name, naturally introduce the topic '{self.part1_current_topic}' (e.g., 'Now let's talk about {self.part1_current_topic}'), and ask a relevant question dynamically selected from this list of suggested questions: {questions_str}. Formulate it conversationally. Do not hallucinate other topics. Do not mention that you are an AI. Do not prefix with 'Examiner:'."
                print(f"[DEBUG PART 1] Injected Prompt for 1st Q: {forced_q_text}")
                
                history_for_gen = self.conversation_history
                
            elif self.part1_state == "asking_question":
                if self.part1_questions_asked >= len(self.part1_topic_questions) and len(self.part1_topic_questions) > 0:
                    # End of topic, we need to evaluate
                    self.part1_state = "evaluating"
                    
                    # Quickly evaluate
                    history_for_eval = list(self.conversation_history)
                    history_for_eval.append({
                        "role": "system",
                        "content": "Evaluate the candidate's performance in Part 1 so far. If the candidate has provided full, well-developed answers demonstrating good fluency and depth, OR if they have answered several questions already, return STRICTLY the word 'MOVE_TO_PART_2'. Only return 'CONTINUE_PART_1' if their answers were extremely short and you still need more evidence."
                    })
                    
                    try:
                        # Use a direct non-streaming call for quick evaluation
                        eval_result_dict = await sync_to_async(self.gemini_client.generate_speaking_turn, thread_sensitive=False)(history_for_eval, part="1")
                        eval_text = eval_result_dict.get("examiner_text", "").strip().upper()
                        print(f"[DEBUG PART 1] AI Evaluation Result: {eval_text}")
                        
                        if ("MOVE_TO" in eval_text and self.part1_total_questions_asked >= 2) or self.part1_total_questions_asked >= 10:
                            # Move to Part 2 if running in 'all' mode, or end if just '1'
                            if part == "1":
                                self.conversation_history.append({"role": "assistant", "content": "Thank you, that is the end of Part 1 and the test."})
                                self.stop_requested = True
                                asyncio.create_task(self._finalize_session_start_background())
                                return
                            else:
                                # Transition to Part 2
                                print("[DEBUG PART 1] Moving to Part 2")
                                self.part2_state = "greeting"
                                self.part1_state = "none"
                                self.conversation_history.append({"role": "assistant", "content": "Now, let's move on to Part 2 of the test."})
                                await self._send_static_audio("move_to_part2.wav", "Now, let's move on to Part 2 of the test.")
                                return
                    except Exception as e:
                        print(f"[DEBUG PART 1] Eval failed: {e}")
                    
                    # If we continue (or eval failed)
                    topic, questions = await self._fetch_random_part1_topic(exclude_topic=self.part1_current_topic)
                    self.part1_current_topic = topic
                    self.part1_topic_questions = questions
                    self.part1_questions_asked = 1
                    self.part1_total_questions_asked += 1
                    self.part1_state = "asking_question"
                    
                    print(f"[DEBUG PART 1 NEXT TOPIC] Selected Topic: {topic}")
                    print(f"[DEBUG PART 1 NEXT TOPIC] Selected Questions: {questions}")
                    
                    # The AI will naturally handle the transition now
                    # await self._send_static_audio("next_topic.wav", "")
                    
                    questions_str = json.dumps(self.part1_topic_questions)
                    forced_q_text = f"We are moving to a new topic. Naturally introduce the new topic '{self.part1_current_topic}' (e.g., 'Let's move on to talk about {self.part1_current_topic}') and dynamically ask a relevant question from this list: {questions_str}. Formulate it conversationally. Do not hallucinate other topics. Do not prefix with 'Examiner:'."
                    print(f"[DEBUG PART 1] Injected Prompt for Next Topic Q: {forced_q_text}")
                    history_for_gen = self.conversation_history
                    
                else:
                    # Still asking questions for current topic
                    self.part1_questions_asked += 1
                    self.part1_total_questions_asked += 1
                    questions_str = json.dumps(self.part1_topic_questions)
                    
                    forced_q_text = f"We are discussing the topic '{self.part1_current_topic}'. Based on the candidate's previous response, ask a natural follow-up question OR dynamically select an appropriate next question from this list of suggested questions: {questions_str}. Integrate it naturally and conversationally. Do not prefix with 'Examiner:'."
                    print(f"[DEBUG PART 1] Injected Prompt for Follow-up Q: {forced_q_text}")
                    history_for_gen = self.conversation_history
            else:
                history_for_gen = self.conversation_history
                forced_q_text = None
        elif part == "3" or (part == "all" and self.part3_state != "none"):
            if self.part3_state == "asking_question":
                if self.part3_questions_asked >= len(self.part3_topic_questions) and len(self.part3_topic_questions) > 0:
                    # Part 3 is done, finish the test
                    self.conversation_history.append({"role": "assistant", "content": "Thank you, that is the end of the speaking test."})
                    self.stop_requested = True
                    asyncio.create_task(self._finalize_session_start_background())
                    return
                else:
                    if self.part3_questions_asked == 0 and part == "3":
                        self.part3_questions_asked += 1
                        questions_str = json.dumps(self.part3_topic_questions)
                        forced_q_text = f"We are starting Part 3 of the test. Naturally introduce the topic '{self.part3_current_topic}' and dynamically select an appropriate first question from these suggested questions: {questions_str}. Formulate it conversationally. Do not hallucinate other topics. Do not prefix with 'Examiner:'."
                    else:
                        self.part3_questions_asked += 1
                        questions_str = json.dumps(self.part3_topic_questions)
                        forced_q_text = f"We are in Part 3 discussing the topic '{self.part3_current_topic}'. Based on the candidate's last response, either ask a natural follow-up question, OR select an appropriate next question from these suggested questions: {questions_str}. Formulate it conversationally. Do not prefix with 'Examiner:'."
                    print(f"[DEBUG PART 3] Injected Prompt for Q: {forced_q_text}")
                    history_for_gen = self.conversation_history
            else:
                history_for_gen = self.conversation_history
                forced_q_text = None
        else:
            history_for_gen = self.conversation_history
            forced_q_text = None

        await self._set_turn_state("examiner_speaking")
        self.examiner_started_at = timezone.now()
        self.interrupt_requested = False
        self._is_playing_static_audio = False
        
        # Generate a unified chunk_id for this whole turn
        chunk_id = f"{self.session_id}:{uuid4().hex}"
        self.pending_playback_chunk_id = chunk_id
        
        # Trim history to prevent unlimited growth (4 turns = 8 messages max)
        MAX_HISTORY = 8
        trimmed_history = history_for_gen[-MAX_HISTORY:] if len(history_for_gen) > MAX_HISTORY else history_for_gen

        # We start the stream from Gemini
        generator = self.gemini_client.generate_speaking_turn_stream(
            trimmed_history, 
            part=part, 
            forced_question=forced_q_text
        )
        
        def _next_text_chunk():
            try:
                return next(generator, None)
            except Exception:
                return {"text": "", "is_last": True}
        
        buffer = ""
        full_text = ""
        seq = 0
        sentence_buffer = []
        test_concluded = False
        
        # Notify frontend we are starting to stream text
        await self.send_json(
            {
                "type": "examiner.text.start",
                "session_id": self.session_id,
                "payload": {},
            }
        )

        self.interrupted_remaining_text = ""
        _collected_unsent = False
        
        # Create a queue and a worker for parallel TTS generation
        tts_queue = asyncio.Queue()
        async def tts_worker():
            while True:
                item = await tts_queue.get()
                if item is None:
                    tts_queue.task_done()
                    break
                sentence, current_seq, current_chunk_id, is_final_chunk = item
                if not self.interrupt_requested:
                    await self._synthesize_and_send_sentence(sentence, current_seq, current_chunk_id, is_final_chunk)
                tts_queue.task_done()
                
        tts_task = asyncio.create_task(tts_worker())
        
        while True:
            chunk = await sync_to_async(_next_text_chunk, thread_sensitive=True)()
            if not chunk:
                break
                
            text = chunk.get("text", "")
            is_last = chunk.get("is_last", False)
            
            if self.interrupt_requested:
                if not _collected_unsent:
                    _collected_unsent = True
                    if sentence_buffer:
                        self.interrupted_remaining_text += " ".join(sentence_buffer) + " "
                        sentence_buffer = []
                    if buffer:
                        self.interrupted_remaining_text += buffer
                        buffer = ""
                if text:
                    self.interrupted_remaining_text += text
                continue
            
            if text:
                buffer += text
                full_text += text
            
            # Prevent synthesis if Gemini decides to print test conclusion evaluations
            if "Scores:" in full_text or "Overall Band" in full_text or "overall_band" in full_text:
                 test_concluded = True
                 buffer = ""  # clear buffer so it doesn't synthesize the evaluation payload
                 is_last = True
            
            # Output Sanitization: Remove hidden system artifacts or markdown that might leak
            # from the streaming output.
            buffer = buffer.replace("[System Note]", "").replace("Examiner:", "").replace("**", "")
            
            if "[PART2]" in full_text:
                if self.part2_state != "cue_card":
                    self.part2_state = "cue_card"
                    if self.prep_seconds == 0 or self.speaking_seconds == 0:
                        self.prep_seconds, self.speaking_seconds = self._get_part_timing("2")
                # We only strip from buffer to prevent TTS from reading it.
                # We leave it in full_text and text so the frontend can intercept it and style the cue card.
                buffer = buffer.replace("[PART2]", "").lstrip()

            if text:
                await self.send_json({
                    "type": "examiner.text.chunk",
                    "session_id": self.session_id,
                    "payload": {"text": text},
                })

            # Look for sentences to synthesize
            chunks = re.split(r'(?<=[.!?])\s+', buffer)
            if len(chunks) == 1:
                # Secondary split on commas for long clauses
                if len(buffer) > 60 and ',' in buffer:
                    parts = buffer.split(',', 1)
                    sentence_buffer.append(parts[0].strip() + ',')
                    buffer = parts[1].lstrip()
                    
                    combined = " ".join(sentence_buffer)
                    await tts_queue.put((combined, seq, chunk_id, False))
                    seq += 1
                    sentence_buffer = []
            elif len(chunks) > 1:
                # We have at least one complete sentence
                complete_chunks = chunks[:-1]
                buffer = chunks[-1] # keep the incomplete part
                
                for sentence in complete_chunks:
                    if self.interrupt_requested:
                        break
                    sentence = sentence.strip()
                    if sentence:
                        sentence_buffer.append(sentence)
                        combined = " ".join(sentence_buffer)
                        await tts_queue.put((combined, seq, chunk_id, False))
                        seq += 1
                        sentence_buffer = []

            if is_last:
                if not self.interrupt_requested:
                    # Flush the remaining buffer
                    if buffer.strip():
                        sentence_buffer.append(buffer.strip())
                    
                    last_chunk_sent = False
                    
                    if sentence_buffer:
                        combined = ". ".join(sentence_buffer) + "."
                        if not combined.endswith("."):
                            combined += "."
                        is_final = (self.part2_state != "cue_card")
                        await tts_queue.put((combined, seq, chunk_id, is_final))
                        seq += 1
                        if is_final:
                            last_chunk_sent = True
                        
                    # Append the strict text marker for Part 2 prep without phrase matching reliance
                    if self.part2_state == "cue_card":
                        prep_text = ""
                        # prep_text is handled by the model prompt, so we don't need to append it again here.
                        pass

                    if not last_chunk_sent:
                         # We need to tell frontend we are done
                         await self.send_json(
                            {
                                "type": "examiner.audio.chunk",
                                "session_id": self.session_id,
                                "payload": {
                                    "chunk_id": chunk_id,
                                    "seq": seq,
                                    "is_last": True,
                                    "audio_base64": "",
                                    "format": "wav",
                                },
                            }
                        )
                break
        
        # Stop the TTS worker
        await tts_queue.put(None)
        await tts_task
        
        self.last_examiner_text = full_text.replace("[PART2]", "").strip()
        self.conversation_history.append({"role": "assistant", "content": full_text.replace("[PART2]", "").strip()})
        
        if not self.interrupt_requested:
            await self.send_json(
                {
                    "type": "examiner.audio.done",
                    "session_id": self.session_id,
                    "payload": {"chunk_id": chunk_id},
                }
            )
            
            if test_concluded:
                self.stop_requested = True
                asyncio.create_task(self._finalize_session_start_background())
                return
            
            self.playback_timeout_task = asyncio.create_task(self._wait_for_playback_timeout(chunk_id))
                
    async def _synthesize_and_send_sentence(self, sentence: str, seq: int, chunk_id: str, is_last: bool):
        audio_bytes = await sync_to_async(self.tts_client.generate_audio, thread_sensitive=False)(sentence)
        
        if audio_bytes and not self.interrupt_requested:
            await self.send_json(
                {
                    "type": "examiner.audio.chunk",
                    "session_id": self.session_id,
                    "payload": {
                        "chunk_id": chunk_id,
                        "seq": seq,
                        "is_last": is_last,
                        "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                        "format": "wav",
                    },
                }
            )

    async def _finalize_session(self):
        if self.playback_timeout_task:
            self.playback_timeout_task.cancel()
            self.playback_timeout_task = None
        self.pending_playback_chunk_id = None
        if not self._has_candidate_response():
            report = self._build_not_commenced_report()
            transcript = "\n".join([
                f"{item['role']}: {item['content']}" for item in self.conversation_history if item["role"] in {"assistant", "user"}
            ])
            await self._persist_session(status="finished", transcript=transcript, report=report)
            await self._set_turn_state("finished")
            await self.send_json(
                {
                    "type": "session.report",
                    "session_id": self.session_id,
                    "payload": report,
                }
            )
            await self.close()
            return

        part = getattr(self.session, "part", "all")
        report = await sync_to_async(self.gemini_client.generate_speaking_final_report, thread_sensitive=False)(
            self.conversation_history, part=part
        )

        transcript = "\n".join([
            f"{item['role']}: {item['content']}" for item in self.conversation_history if item["role"] in {"assistant", "user"}
        ])

        await self._persist_session(status="finished", transcript=transcript, report=report)
        await self._set_turn_state("finished")

        await self.send_json(
            {
                "type": "session.report",
                "session_id": self.session_id,
                "payload": report,
            }
        )
        await self.close()

    async def _finalize_session_start_background(self):
        if self.playback_timeout_task:
            self.playback_timeout_task.cancel()
            self.playback_timeout_task = None
        self.pending_playback_chunk_id = None

        # Determine the farewell text based on history or default
        farewell_text = "Thank you, that is the end of the speaking test."
        if getattr(self.session, "part", "all") == "1":
            farewell_text = "Thank you, that is the end of Part 1 and the test."
        elif getattr(self.session, "part", "all") == "2" and not self._has_candidate_response():
             farewell_text = "I see. We will now conclude the test. Thank you."

        await self._send_static_audio("farewell.wav", farewell_text, force=True)

        transcript = "\n".join(
            [f"{item['role']}: {item['content']}" for item in self.conversation_history if item["role"] in {"assistant", "user"}]
        )

        if not self._has_candidate_response():
            report = self._build_not_commenced_report()
            await self._persist_session(status="finished", transcript=transcript, report=report)
            await self._set_turn_state("finished")
            await asyncio.sleep(4)
            await self.send_json(
                {
                    "type": "session.report.final",
                    "session_id": self.session_id,
                    "payload": report,
                }
            )
            await self.close()
            return

        try:
            part = getattr(self.session, "part", "all")
            quick_scores = await sync_to_async(self.gemini_client.generate_speaking_quick_scores, thread_sensitive=False)(
                self.conversation_history, part=part
            )
        except Exception:
            quick_scores = None

        if hasattr(self, "playback_finished_event"):
            try:
                await asyncio.wait_for(self.playback_finished_event.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                pass

        if quick_scores is None:
            await self._finalize_session()
            return

        await self._persist_session(status="evaluating", transcript=transcript, report={"scores": quick_scores})
        await self._set_turn_state("finished")

        await self.send_json(
            {
                "type": "session.report.partial",
                "session_id": self.session_id,
                "payload": {
                    "scores": quick_scores,
                    "detail_status": "processing",
                },
            }
        )

        self.final_report_task = asyncio.create_task(self._build_and_publish_full_report(transcript))

    async def _build_and_publish_full_report(self, transcript: str):
        try:
            try:
                part = getattr(self.session, "part", "all")
                report = await sync_to_async(self.gemini_client.generate_speaking_final_report, thread_sensitive=False)(
                    self.conversation_history, part=part
                )
            except Exception as exc:
                await self._persist_session(status="finished", transcript=transcript, report={"scores": self.session.scores})
                try:
                    await self.send_json(
                        {
                                 "type": "session.report.final",
                            "session_id": self.session_id,
                            "payload": {
                                "scores": self.session.scores or {},
                                "analysis": {},
                                "examiner_comments": f"Detailed evaluation is temporarily unavailable: {exc}",
                            },
                        }
                    )
                    await self.close()
                except Exception:
                    pass
                return

            await self._persist_session(status="finished", transcript=transcript, report=report)
            try:
                await self.send_json(
                    {
                        "type": "session.report.final",
                        "session_id": self.session_id,
                        "payload": report,
                    }
                )
                await self.close()
            except Exception:
                pass
        finally:
            self.final_report_task = None

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

    async def _set_turn_state(self, state: str):
        self.turn_state = state
        self.audio_buffer = BytesIO()
        self.user_speech_duration_ms = 0
        self.silence_timer_ms = 0
        if state == "candidate_speaking":
            self.turn_blocked_emitted = False
        await self.send_json(
            {
                "type": "turn.state",
                "session_id": self.session_id,
                "payload": {"state": state},
            }
        )

    async def _send_turn_blocked_once(self, reason: str):
        if self.turn_blocked_emitted:
            return
        self.turn_blocked_emitted = True
        await self.send_json(
            {
                "type": "turn.blocked",
                "session_id": self.session_id,
                "payload": {"reason": reason},
            }
        )

    async def _wait_for_playback_timeout(self, chunk_id: str):
        try:
            await asyncio.sleep(max(0, self.tts_playback_ack_timeout_ms) / 1000)
            await self._finish_examiner_playback(chunk_id)
        except asyncio.CancelledError:
            return

    async def _finish_examiner_playback(self, chunk_id: str):
        if chunk_id != self.pending_playback_chunk_id:
            return
        self.pending_playback_chunk_id = None
        timeout_task = self.playback_timeout_task
        if timeout_task and timeout_task is not asyncio.current_task():
            timeout_task.cancel()
        self.playback_timeout_task = None
        
        if hasattr(self, "playback_finished_event"):
            self.playback_finished_event.set()
            
        await asyncio.sleep(max(0, self.turn_post_examiner_guard_ms) / 1000)
        
        if self.part2_state == "greeting":
            if getattr(self, "part2_pregenerated_cue_card", None):
                self.part2_state = "cue_card"
                await self._send_pregenerated_cue_card()
            else:
                self.part2_state = "waiting_for_cue_card"
            return
        elif self.part2_state == "cue_card":
            self.part2_state = "prep_instructions"
            await self._send_static_audio("prep_instructions.wav", "You will have 1 minute to prepare your answer, and then you will have 1 to 2 minutes to speak. Your preparation time starts now.")
            return
        elif self.part2_state == "prep_instructions":
            self.part2_state = "prep_active"
            await self._start_part2_prep()
            return
        elif self.part2_state == "prep_finished_waiting_for_speech":
            self.part2_state = "speaking_active"
            await self._start_part2_speaking()
            return
            
        part_mode = str(getattr(self.session, "part", "all")).strip().lower()
        if part_mode == "3" and self.part3_state == "asking_question" and getattr(self, "part3_questions_asked", 0) == 0:
            await self._send_examiner_turn_stream()
            return
            
        if not self.stop_requested and self.turn_state != "finished":
            await self._set_turn_state("candidate_speaking")

    async def _start_part2_prep(self):
        self.prep_until = timezone.now() + timedelta(seconds=self.prep_seconds)
        await self._set_turn_state("preparation")
        await self.send_json({
            "type": "timer.start_prep",
            "session_id": self.session_id,
            "payload": {"seconds": self.prep_seconds}
        })
        self.part2_prep_task = asyncio.create_task(self._run_part2_prep_timer())

    async def _run_part2_prep_timer(self):
        try:
            for seconds_left in range(self.prep_seconds, 0, -1):
                if self.stop_requested:
                    return
                await self.send_json({
                    "type": "timer.update",
                    "session_id": self.session_id,
                    "payload": {"phase": "prep", "seconds_left": seconds_left}
                })
                await asyncio.sleep(1)
            
            if self.stop_requested:
                return

            await self.send_json({
                "type": "timer.update",
                "session_id": self.session_id,
                "payload": {"phase": "prep", "seconds_left": 0}
            })
            self.part2_state = "prep_finished_waiting_for_speech"
            await self._send_static_audio("prep_time_up.wav", "")
        except asyncio.CancelledError:
            pass

    async def _send_examiner_direct_text(self, text: str):
        if self.stop_requested:
            return

        await self._set_turn_state("examiner_speaking")
        self.examiner_started_at = timezone.now()
        self.interrupt_requested = False
        self.last_examiner_text = text
        self.conversation_history.append({"role": "assistant", "content": text})
        
        await self.send_json({
            "type": "examiner.text.start",
            "session_id": self.session_id,
            "payload": {},
        })
        await self.send_json({
            "type": "examiner.text.chunk",
            "session_id": self.session_id,
            "payload": {"text": text},
        })
        
        chunk_id = f"{self.session_id}:{uuid4().hex}"
        self.pending_playback_chunk_id = chunk_id

        sentences = text.replace("?", ".").replace("!", ".").split(".")
        seq = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and not self.interrupt_requested:
                is_last = (seq == len(sentences) - 1)
                await self._synthesize_and_send_sentence(sentence, seq, chunk_id, is_last)
                seq += 1

        if not self.interrupt_requested:
            await self.send_json({
                "type": "examiner.audio.done",
                "session_id": self.session_id,
                "payload": {"chunk_id": chunk_id},
            })
            self.playback_timeout_task = asyncio.create_task(self._wait_for_playback_timeout(chunk_id))

    async def _start_part2_speaking(self):
        self.prep_until = None
        self.speaking_until = timezone.now() + timedelta(seconds=self.speaking_seconds + 5)
        await self._set_turn_state("candidate_speaking")
        await self.send_json({
            "type": "timer.start_speaking",
            "session_id": self.session_id,
            "payload": {"seconds": self.speaking_seconds}
        })
        self.part2_speaking_task = asyncio.create_task(self._run_part2_speaking_timer())

    async def _run_part2_speaking_timer(self):
        try:
            total_time = self.speaking_seconds
            for seconds_left in range(total_time, 0, -1):
                if self.stop_requested:
                    return
                await self.send_json({
                    "type": "timer.update",
                    "session_id": self.session_id,
                    "payload": {"phase": "speaking", "seconds_left": seconds_left}
                })
                await asyncio.sleep(1)

            if self.stop_requested:
                return
                
            await self.send_json({
                "type": "timer.update",
                "session_id": self.session_id,
                "payload": {"phase": "speaking", "seconds_left": 0}
            })
            
            # Give candidate 5 seconds buffer to finish sentence
            await asyncio.sleep(5)
            
            if self.stop_requested:
                return

            self.part2_state = "done"
            await self._force_candidate_cutoff()
        except asyncio.CancelledError:
            pass

    async def _force_candidate_cutoff(self):
        if self.turn_state != "candidate_speaking":
            return
        
        raw_audio = self.audio_buffer.getvalue()
        if not raw_audio:
            # Candidate remained completely silent.
            part_mode = str(getattr(self.session, "part", "all")).strip().lower()
            
            if part_mode == "2":
                self.conversation_history.append({"role": "user", "content": "[Candidate remained completely silent during Part 2]"})
                self.conversation_history.append({"role": "assistant", "content": "I see. We will now conclude the test. Thank you."})
                self.stop_requested = True
                asyncio.create_task(self._finalize_session_start_background())
                return
                
            self.part3_state = "asking_question"
            self.conversation_history.append({"role": "user", "content": "[Candidate remained completely silent during Part 2]"})
            self.conversation_history.append({"role": "assistant", "content": "I see. Then let's move on to Part 3."})
            await self._send_static_audio("move_to_part3.wav", "I see. Then let's move on to Part 3.")
            # We don't trigger the Gemini stream directly here because _send_static_audio will wait for playback.
            # BUT we need to trigger Gemini to ask Part 3! 
            # So we can just wait for playback of move_to_part3 and then trigger stream. 
            # Or simpler: trigger stream but tell the stream not to synthesize the first sentence.
            # Actually, to make it perfectly robust, we trigger stream after the move_to_part3 playback?
            # Let's just trigger the stream directly; it will queue its audio right after the static one!
            
            # Setup first question for part 3
            self.part3_questions_asked = 1
            questions_str = json.dumps(self.part3_topic_questions)
            forced_q_text = f"We are moving to Part 3. I have just played a transition audio. Naturally introduce the topic '{self.part3_current_topic}' (e.g., 'Now let's consider {self.part3_current_topic} more generally') and dynamically select an appropriate first question from these suggested questions: {questions_str}. Formulate it conversationally. Do not hallucinate other topics. Do not prefix with 'Examiner:'."
            print(f"[DEBUG PART 3 START] Injected Prompt for 1st Q: {forced_q_text}")
            
            # Start stream
            self._is_playing_static_audio = False
            self.examiner_started_at = timezone.now()
            self.interrupt_requested = False
            chunk_id = f"{self.session_id}:{uuid4().hex}"
            self.pending_playback_chunk_id = chunk_id
            
            generator = self.gemini_client.generate_speaking_turn_stream(
                self.conversation_history, 
                part="all", 
                forced_question=forced_q_text
            )
            # Proceed with standard generation loop
            def _next_text_chunk_fallback():
                try:
                    return next(generator, None)
                except Exception:
                    return {"text": "", "is_last": True}
                    
            buffer = ""
            full_text = ""
            seq = 0
            sentence_buffer = []
            
            await self.send_json(
                {
                    "type": "examiner.text.start",
                    "session_id": self.session_id,
                    "payload": {},
                }
            )

            tts_queue = asyncio.Queue()
            async def tts_worker():
                while True:
                    item = await tts_queue.get()
                    if item is None:
                        tts_queue.task_done()
                        break
                    sentence, current_seq, current_chunk_id, is_final_chunk = item
                    if not self.interrupt_requested:
                        await self._synthesize_and_send_sentence(sentence, current_seq, current_chunk_id, is_final_chunk)
                    tts_queue.task_done()
                    
            tts_task = asyncio.create_task(tts_worker())

            while True:
                if self.interrupt_requested:
                    break
                    
                chunk = await sync_to_async(_next_text_chunk_fallback, thread_sensitive=True)()
                if not chunk:
                    break
                    
                text = chunk.get("text", "")
                is_last = chunk.get("is_last", False)
                
                if text:
                    buffer += text
                    full_text += text
                    
                    buffer = buffer.replace("[System Note]", "").replace("Examiner:", "").replace("**", "")

                    if text:
                        await self.send_json({
                            "type": "examiner.text.chunk",
                            "session_id": self.session_id,
                            "payload": {"text": text},
                        })

                    chunks = re.split(r'(?<=[.!?])\s+', buffer)
                    if len(chunks) == 1:
                        # Secondary split on commas for long clauses
                        if len(buffer) > 60 and ',' in buffer:
                            parts = buffer.split(',', 1)
                            sentence_buffer.append(parts[0].strip() + ',')
                            buffer = parts[1].lstrip()
                            
                            combined = " ".join(sentence_buffer)
                            await tts_queue.put((combined, seq, chunk_id, False))
                            seq += 1
                            sentence_buffer = []
                    elif len(chunks) > 1:
                        complete_chunks = chunks[:-1]
                        buffer = chunks[-1]
                        
                        for sentence in complete_chunks:
                                if self.interrupt_requested:
                                    break
                                sentence = sentence.strip()
                                if sentence:
                                    sentence_buffer.append(sentence)
                                    combined = " ".join(sentence_buffer)
                                    await tts_queue.put((combined, seq, chunk_id, False))
                                    seq += 1
                                    sentence_buffer = []

                if is_last:
                    if not self.interrupt_requested:
                        if buffer.strip():
                            sentence_buffer.append(buffer.strip())
                        
                        last_chunk_sent = False
                        
                        if sentence_buffer:
                            combined = ". ".join(sentence_buffer) + "."
                            if not combined.endswith("."):
                                combined += "."
                            await tts_queue.put((combined, seq, chunk_id, True))
                            seq += 1
                            last_chunk_sent = True

                        if not last_chunk_sent:
                             await self.send_json(
                                {
                                    "type": "examiner.audio.chunk",
                                    "session_id": self.session_id,
                                    "payload": {
                                        "chunk_id": chunk_id,
                                        "seq": seq,
                                        "is_last": True,
                                        "audio_base64": "",
                                        "format": "wav",
                                    },
                                }
                            )
                    break
            
            await tts_queue.put(None)
            await tts_task
            
            self.last_examiner_text = full_text.strip()
            self.conversation_history.append({"role": "assistant", "content": full_text.strip()})
            
            if not self.interrupt_requested:
                await self.send_json(
                    {
                        "type": "examiner.audio.done",
                        "session_id": self.session_id,
                        "payload": {"chunk_id": chunk_id},
                    }
                )
                self.playback_timeout_task = asyncio.create_task(self._wait_for_playback_timeout(chunk_id))
                
            return

        self.processing_audio = True
        try:
            await self._set_turn_state("processing_candidate")
            
            self.silence_timer_ms = 0
            self.user_speech_duration_ms = 0
            self.current_partial_transcript = ""
            
            part_mode = str(getattr(self.session, "part", "all")).strip().lower()

            if part_mode == "2":
                self.stop_requested = True
                self.conversation_history.append({"role": "assistant", "content": "I see. We will now conclude the test. Thank you."})
                
                async def finish_part2_and_eval():
                    try:
                        if getattr(self, "last_is_pcm", True):
                            transcript = await sync_to_async(self.stt_client.transcribe_pcm16_bytes, thread_sensitive=False)(
                                raw_audio, self.last_sample_rate
                            )
                        else:
                            file_ext = ".webm" if "webm" in getattr(self, "last_mime_type", "") else ".wav"
                            transcript = await sync_to_async(self.stt_client.transcribe_stream_buffer, thread_sensitive=False)(
                                BytesIO(raw_audio), file_extension=file_ext
                            )
                        transcript = transcript.strip()
                        if transcript:
                            self.conversation_history.insert(-1, {"role": "user", "content": transcript})
                            await self.send_json({
                                "type": "transcript.final",
                                "session_id": self.session_id,
                                "payload": {"text": transcript},
                            })
                        else:
                            self.conversation_history.insert(-1, {"role": "user", "content": "[Candidate remained completely silent during Part 2]"})
                    except Exception as e:
                        print(f"Background STT failed before eval: {e}")
                        self.conversation_history.insert(-1, {"role": "user", "content": "[Candidate response could not be transcribed]"})
                    
                    await self._finalize_session_start_background()

                asyncio.create_task(finish_part2_and_eval())
                return

            # Start transcription in background
            asyncio.create_task(self._background_transcribe_part2(raw_audio, self.last_sample_rate))

            self.part3_state = "asking_question"
            # Immediately add placeholder to conversation history and trigger examiner
            self.conversation_history.append({"role": "user", "content": "[Candidate completed Part 2 response and it is being evaluated in the background]"})
            await self.send_json({
                "type": "transcript.final",
                "session_id": self.session_id,
                "payload": {"text": "[Candidate completed Part 2 response and it is being evaluated in the background]"},
            })
            
            self.conversation_history.append({"role": "assistant", "content": "I see. Then let's move on to Part 3."})
            await self._send_static_audio("move_to_part3.wav", "I see. Then let's move on to Part 3.")
            
            # Setup first question for part 3
            self.part3_questions_asked = 1
            questions_str = json.dumps(self.part3_topic_questions)
            forced_q_text = f"We are moving to Part 3. I have just played a transition audio. Naturally introduce the topic '{self.part3_current_topic}' (e.g., 'Now let's consider {self.part3_current_topic} more generally') and dynamically select an appropriate first question from these suggested questions: {questions_str}. Formulate it conversationally. Do not hallucinate other topics. Do not prefix with 'Examiner:'."
            print(f"[DEBUG PART 3 START] Injected Prompt for 1st Q: {forced_q_text}")
            
            # Start stream
            self._is_playing_static_audio = False
            self.examiner_started_at = timezone.now()
            self.interrupt_requested = False
            chunk_id = f"{self.session_id}:{uuid4().hex}"
            self.pending_playback_chunk_id = chunk_id
            
            generator = self.gemini_client.generate_speaking_turn_stream(
                self.conversation_history, 
                part="all", 
                forced_question=forced_q_text
            )
            # Proceed with standard generation loop
            def _next_text_chunk_bg():
                try:
                    return next(generator, None)
                except Exception:
                    return {"text": "", "is_last": True}
                    
            buffer = ""
            full_text = ""
            seq = 0
            sentence_buffer = []
            
            await self.send_json(
                {
                    "type": "examiner.text.start",
                    "session_id": self.session_id,
                    "payload": {},
                }
            )

            tts_queue = asyncio.Queue()
            async def tts_worker():
                while True:
                    item = await tts_queue.get()
                    if item is None:
                        tts_queue.task_done()
                        break
                    sentence, current_seq, current_chunk_id, is_final_chunk = item
                    if not self.interrupt_requested:
                        await self._synthesize_and_send_sentence(sentence, current_seq, current_chunk_id, is_final_chunk)
                    tts_queue.task_done()
                    
            tts_task = asyncio.create_task(tts_worker())

            while True:
                if self.interrupt_requested:
                    break
                    
                chunk = await sync_to_async(_next_text_chunk_bg, thread_sensitive=True)()
                if not chunk:
                    break
                    
                text = chunk.get("text", "")
                is_last = chunk.get("is_last", False)
                
                if text:
                    buffer += text
                    full_text += text
                    
                    buffer = buffer.replace("[System Note]", "").replace("Examiner:", "").replace("**", "")

                    if text:
                        await self.send_json({
                            "type": "examiner.text.chunk",
                            "session_id": self.session_id,
                            "payload": {"text": text},
                        })

                    chunks = re.split(r'(?<=[.!?])\s+', buffer)
                    if len(chunks) == 1:
                        # Secondary split on commas for long clauses
                        if len(buffer) > 60 and ',' in buffer:
                            parts = buffer.split(',', 1)
                            sentence_buffer.append(parts[0].strip() + ',')
                            buffer = parts[1].lstrip()
                            
                            combined = " ".join(sentence_buffer)
                            await tts_queue.put((combined, seq, chunk_id, False))
                            seq += 1
                            sentence_buffer = []
                    elif len(chunks) > 1:
                        complete_chunks = chunks[:-1]
                        buffer = chunks[-1]
                        
                        for sentence in complete_chunks:
                                if self.interrupt_requested:
                                    break
                                sentence = sentence.strip()
                                if sentence:
                                    sentence_buffer.append(sentence)
                                    combined = " ".join(sentence_buffer)
                                    await tts_queue.put((combined, seq, chunk_id, False))
                                    seq += 1
                                    sentence_buffer = []

                if is_last:
                    if not self.interrupt_requested:
                        if buffer.strip():
                            sentence_buffer.append(buffer.strip())
                        
                        last_chunk_sent = False
                        
                        if sentence_buffer:
                            combined = ". ".join(sentence_buffer) + "."
                            if not combined.endswith("."):
                                combined += "."
                            await tts_queue.put((combined, seq, chunk_id, True))
                            seq += 1
                            last_chunk_sent = True

                        if not last_chunk_sent:
                             await self.send_json(
                                {
                                    "type": "examiner.audio.chunk",
                                    "session_id": self.session_id,
                                    "payload": {
                                        "chunk_id": chunk_id,
                                        "seq": seq,
                                        "is_last": True,
                                        "audio_base64": "",
                                        "format": "wav",
                                    },
                                }
                            )
                    break
            
            await tts_queue.put(None)
            await tts_task
            
            self.last_examiner_text = full_text.strip()
            self.conversation_history.append({"role": "assistant", "content": full_text.strip()})
            
            if not self.interrupt_requested:
                await self.send_json(
                    {
                        "type": "examiner.audio.done",
                        "session_id": self.session_id,
                        "payload": {"chunk_id": chunk_id},
                    }
                )
                self.playback_timeout_task = asyncio.create_task(self._wait_for_playback_timeout(chunk_id))
        except Exception:
            await self._set_turn_state("candidate_speaking")
        finally:
            self.processing_audio = False

    async def _background_transcribe_part2(self, raw_audio, sample_rate):
        if not raw_audio:
            return
        try:
            if getattr(self, "last_is_pcm", True):
                transcript = await sync_to_async(self.stt_client.transcribe_pcm16_bytes, thread_sensitive=False)(
                    raw_audio, sample_rate
                )
            else:
                file_ext = ".webm" if "webm" in getattr(self, "last_mime_type", "") else ".wav"
                transcript = await sync_to_async(self.stt_client.transcribe_stream_buffer, thread_sensitive=False)(
                    BytesIO(raw_audio), file_extension=file_ext
                )
            transcript = transcript.strip()
            if transcript:
                # Send to frontend just for logging/display
                await self.send_json({
                    "type": "transcript.final",
                    "session_id": self.session_id,
                    "payload": {"text": f"[Part 2 evaluated] {transcript}"},
                })
                # Replace the placeholder in the conversation history
                for item in reversed(self.conversation_history):
                    if item["role"] == "user" and "evaluated in the background" in str(item["content"]):
                        item["content"] = transcript
                        break
        except Exception as e:
            print(f"Background STT failed: {e}")

    def _has_candidate_response(self) -> bool:
        return any(
            str(item.get("content", "")).strip()
            for item in self.conversation_history
            if item.get("role") == "user"
        )

    def _build_not_commenced_report(self) -> dict:
        return {
            "scores": {"fc": 0.0, "lr": 0.0, "gra": 0.0, "overall_band": 0.0},
            "analysis": {
                "fc": {"good": [], "not_so_good": ["No spoken response was provided by the candidate."]},
                "lr": {"good": [], "not_so_good": ["No lexical evidence is available without a candidate response."]},
                "gra": {"good": [], "not_so_good": ["No grammatical evidence is available without a candidate response."]},
            },
            "examiner_comments": (
                "The speaking test has not commenced because the candidate did not provide a valid spoken response to the opening question. "
                "As a result, it is not possible to evaluate fluency and coherence, lexical resource, or grammatical range and accuracy."
            ),
        }
