from dataclasses import dataclass, field

try:
    import webrtcvad  # type: ignore
except Exception:
    webrtcvad = None


class _FallbackVad:
    def __init__(self, _mode: int):
        pass

    def is_speech(self, frame: bytes, _sample_rate: int) -> bool:
        # Simple energy gate fallback for environments where webrtcvad is unavailable.
        return any(b != 0 for b in frame)


@dataclass
class VADService:
    mode: int = 2
    sample_rate: int = 16000
    frame_ms: int = 20
    silence_frames_to_end: int = 20
    vad: object = field(init=False)
    _silence_counter: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if webrtcvad is None:
            self.vad = _FallbackVad(self.mode)
        else:
            self.vad = webrtcvad.Vad(self.mode)

    @property
    def frame_bytes(self) -> int:
        return int(self.sample_rate * (self.frame_ms / 1000.0) * 2)

    def _frame_bytes_for_rate(self, sample_rate: int) -> int:
        return int(sample_rate * (self.frame_ms / 1000.0) * 2)

    def reset(self) -> None:
        self._silence_counter = 0

    def detect_end_of_speech(self, pcm_chunk: bytes, sample_rate: int | None = None) -> bool:
        rate = int(sample_rate or self.sample_rate)
        if rate not in {8000, 16000, 32000, 48000}:
            rate = self.sample_rate

        frame_bytes = self._frame_bytes_for_rate(rate)
        if len(pcm_chunk) < frame_bytes:
            return False

        end_detected = False
        for idx in range(0, len(pcm_chunk) - frame_bytes + 1, frame_bytes):
            frame = pcm_chunk[idx : idx + frame_bytes]
            try:
                is_speech = self.vad.is_speech(frame, rate)
            except Exception:
                # Non-PCM/unsupported frames (e.g. compressed browser chunks) should not crash the flow.
                return False
            if is_speech:
                self._silence_counter = 0
            else:
                self._silence_counter += 1
            if self._silence_counter >= self.silence_frames_to_end:
                end_detected = True
                self._silence_counter = 0
        return end_detected
