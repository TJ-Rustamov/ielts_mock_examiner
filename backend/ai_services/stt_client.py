import io
import os
import re
import tempfile
import wave
from functools import cached_property

from faster_whisper import WhisperModel


class FasterWhisperClient:
    def __init__(self) -> None:
        self.model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
        self.device = os.getenv("WHISPER_DEVICE", "cpu")
        self.compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    def _normalize_model_source(self) -> str:
        source = str(self.model_size or "base").strip()
        if not source:
            return "base"

        # If source exists as-is, use it directly.
        if os.path.exists(source):
            return source

        normalized = source.replace("\\", "/")
        is_windows_abs = bool(re.match(r"^[A-Za-z]:/", normalized))
        models_marker = "/models/"

        # Docker mounts host ./models to /models. Translate host-style absolute
        # paths (for example D:/university/models/...) to the in-container path.
        marker_index = normalized.lower().find(models_marker)
        if is_windows_abs and marker_index >= 0:
            mapped = "/models/" + normalized[marker_index + len(models_marker) :]
            mapped = mapped.rstrip("/")
            if os.path.exists(mapped):
                return mapped

        return source

    @cached_property
    def model(self) -> WhisperModel:
        model_source = self._normalize_model_source()
        try:
            return WhisperModel(model_source, device=self.device, compute_type=self.compute_type)
        except Exception as exc:
            raise RuntimeError(
                "Failed to initialize Whisper model from WHISPER_MODEL_SIZE="
                f"'{self.model_size}'. If running in Docker, use '/models/<model-dir>' "
                "or keep the host path under a '/models' segment."
            ) from exc

    def transcribe_audio_bytes(self, audio_bytes: bytes, file_extension: str = ".wav") -> str:
        if not audio_bytes:
            return ""

        suffix = file_extension if file_extension.startswith(".") else f".{file_extension}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        try:
            segments, _ = self.model.transcribe(temp_path, beam_size=1)
            text_parts = [segment.text.strip() for segment in segments if segment.text.strip()]
            return " ".join(text_parts)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def transcribe_stream_buffer(self, stream: io.BytesIO, file_extension: str = ".wav") -> str:
        return self.transcribe_audio_bytes(stream.getvalue(), file_extension=file_extension)

    def transcribe_pcm16_bytes(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        if not pcm_bytes:
            return ""

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)

        return self.transcribe_audio_bytes(wav_io.getvalue(), file_extension=".wav")
