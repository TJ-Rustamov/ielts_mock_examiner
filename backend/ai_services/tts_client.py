import io
import math
import os
import struct
import wave
from functools import cached_property
from pathlib import Path

import numpy as np
import soundfile as sf


class KokoroClient:
    """Generate WAV bytes from Kokoro model. Falls back to a tone when runtime fails."""

    def __init__(self) -> None:
        self.model_path = os.getenv("KOKORO_MODEL_PATH", "")
        self.voice = os.getenv("KOKORO_VOICE", "af_heart")
        self.lang_code = os.getenv("KOKORO_LANG_CODE", "a")
        self.device = os.getenv("KOKORO_DEVICE", "cpu")
        self.repo_id = os.getenv("KOKORO_REPO_ID", "hexgrad/Kokoro-82M")
        self.repo_dir = str(Path(self.model_path).parent) if self.model_path.endswith(".pth") else self.model_path
        self.speed = 1.0

        # Allow admin-configured voice/speed override when DB is available.
        try:
            from core.models import SpeakingConfiguration

            cfg = SpeakingConfiguration.objects.first()
            if cfg:
                self.voice = cfg.voice or self.voice
                self.speed = float(cfg.speed or 1.0)
        except Exception:
            pass

    def _resolve_voice(self, value: str | None = None) -> str:
        voice_name = (value or self.voice or "").strip()
        if voice_name.endswith(".pt"):
            return voice_name
        if not self.repo_dir:
            return voice_name

        candidate = Path(self.repo_dir) / "voices" / f"{voice_name}.pt"
        if candidate.exists():
            return str(candidate)
        return voice_name

    @staticmethod
    def _normalize_speed(speed: float | None) -> float:
        try:
            numeric = float(speed or 1.0)
        except (TypeError, ValueError):
            numeric = 1.0
        return max(0.5, min(2.0, numeric))

    def _apply_speed(self, audio: np.ndarray, speed: float) -> np.ndarray:
        if audio.size == 0:
            return audio

        normalized = self._normalize_speed(speed)
        if abs(normalized - 1.0) < 1e-3:
            return np.asarray(audio, dtype=np.float32)

        source = np.asarray(audio, dtype=np.float32).reshape(-1)
        source_x = np.arange(source.shape[0], dtype=np.float32)
        target_len = max(1, int(source.shape[0] / normalized))
        target_x = np.linspace(0, max(0, source.shape[0] - 1), num=target_len, dtype=np.float32)
        stretched = np.interp(target_x, source_x, source).astype(np.float32)
        return stretched

    @cached_property
    def pipeline(self):
        if not self.model_path:
            return None
        try:
            from kokoro import KPipeline
            from kokoro.model import KModel

            config_path = str(Path(self.repo_dir) / "config.json")
            if not Path(config_path).exists() or not Path(self.model_path).exists():
                return None

            model = KModel(config=config_path, model=self.model_path).to(self.device).eval()

            return KPipeline(
                lang_code=self.lang_code,
                repo_id=self.repo_id,
                model=model,
                device=self.device,
            )
        except Exception:
            return None

    def generate_audio(self, text: str, voice: str | None = None, speed: float | None = None) -> bytes:
        if not text.strip():
            return self._fallback_tone(".")

        if not self.pipeline:
            return self._fallback_tone(text)

        try:
            chunks: list[np.ndarray] = []
            resolved_voice = self._resolve_voice(voice)
            normalized_speed = self._normalize_speed(speed if speed is not None else self.speed)

            for piece in self._split_text(text):
                piece = piece.strip()
                if not piece:
                    continue

                generated = False
                # Some kokoro builds accept repo_id at call-time, others do not.
                for call in (
                    lambda: self.pipeline(piece, voice=resolved_voice, repo_id=self.repo_id),
                    lambda: self.pipeline(piece, voice=resolved_voice),
                ):
                    try:
                        generator = call()
                        for _gs, _ps, audio in generator:
                            arr = np.asarray(audio, dtype=np.float32)
                            if arr.size:
                                chunks.append(arr)
                        generated = True
                        break
                    except TypeError:
                        continue
                    except Exception:
                        break
                if not generated:
                    continue

            if not chunks:
                return self._fallback_tone(text)

            merged = np.concatenate(chunks, axis=0)
            merged = self._apply_speed(merged, normalized_speed)
            audio_bytes = io.BytesIO()
            sf.write(audio_bytes, merged, 24000, format="WAV")
            return audio_bytes.getvalue()
        except Exception:
            return self._fallback_tone(text)

    def _split_text(self, text: str, max_chars: int = 260) -> list[str]:
        cleaned = " ".join(text.split())
        if len(cleaned) <= max_chars:
            return [cleaned]

        pieces: list[str] = []
        current = ""
        for sentence in cleaned.replace("?", ".").replace("!", ".").split("."):
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = f"{current}. {sentence}".strip(". ").strip() if current else sentence
            if len(candidate) > max_chars:
                if current:
                    pieces.append(current.strip())
                current = sentence
            else:
                current = candidate
        if current:
            pieces.append(current.strip())
        return pieces or [cleaned[:max_chars]]

    def _fallback_tone(self, text: str) -> bytes:
        sample_rate = 16000
        duration_s = max(0.25, min(3.0, len(text) / 40.0))
        freq = 440.0
        num_samples = int(sample_rate * duration_s)

        audio_bytes = io.BytesIO()
        with wave.open(audio_bytes, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            for i in range(num_samples):
                value = int(1600 * math.sin(2 * math.pi * freq * i / sample_rate))
                wav_file.writeframesraw(struct.pack("<h", value))

        return audio_bytes.getvalue()
