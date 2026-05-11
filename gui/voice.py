"""
Voice I/O workers — microphone recording, Whisper transcription, gTTS/afplay TTS.

Three QThread subclasses so all I/O stays off the Qt main thread:
  RecordWorker      — streams mic until stop() is called
  TranscribeWorker  — runs faster-whisper on the captured audio array
  TtsWorker         — synthesises text via gTTS, plays via macOS afplay
                      (separate process — no conflict with the adhan pygame mixer)
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000  # Hz — Whisper's native sample rate

SUPPORTED_LANGUAGES = ["English", "Urdu", "Hindi", "Turkish", "Arabic"]

# ISO 639-1 codes understood by both Whisper and gTTS
_LANG_CODE = {
    "English": "en",
    "Urdu":    "ur",
    "Hindi":   "hi",
    "Turkish": "tr",
    "Arabic":  "ar",
}


def lang_code(language: str) -> str:
    return _LANG_CODE.get(language, "en")


class RecordWorker(QThread):
    """
    Captures microphone audio in 100 ms chunks until stop() is called.
    Emits finished(audio_array, sample_rate) when recording ends.
    """
    finished = pyqtSignal(object, int)
    error    = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._stop_flag = False

    def stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        import sounddevice as sd
        chunks: list[np.ndarray] = []
        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE, channels=1, dtype="float32"
            ) as stream:
                while not self._stop_flag:
                    chunk, _ = stream.read(_SAMPLE_RATE // 10)
                    chunks.append(chunk.copy())
        except Exception as e:
            logger.warning("Recording error: %s", e)
            self.error.emit(str(e))
            return
        if chunks:
            audio = np.concatenate(chunks, axis=0).flatten()
            self.finished.emit(audio, _SAMPLE_RATE)


class TranscribeWorker(QThread):
    """
    Runs faster-whisper on a numpy float32 audio array.
    Emits result(transcript_text) or error(message).
    """
    result = pyqtSignal(str)
    error  = pyqtSignal(str)

    def __init__(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: str = "English",
        model_size: str = "large-v3",
    ) -> None:
        super().__init__()
        self._audio = audio
        self._sr = sample_rate
        self._lang = lang_code(language)
        self._model_size = model_size

    def run(self) -> None:
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(
                self._audio,
                language=self._lang,
                beam_size=5,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            self.result.emit(text)
        except Exception as e:
            logger.warning("Transcription error: %s", e)
            self.error.emit(str(e))


class TtsWorker(QThread):
    """
    Synthesises text via gTTS, saves to a temp mp3, then plays it with
    macOS afplay (a separate process — no pygame conflict with the adhan mixer).
    Emits finished() on completion or error(message) on failure.
    """
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, text: str, language: str = "English") -> None:
        super().__init__()
        self._text = text
        self._lang = lang_code(language)

    def run(self) -> None:
        import subprocess
        tmp: Path | None = None
        try:
            from gtts import gTTS
            tts = gTTS(text=self._text, lang=self._lang, slow=False)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp = Path(f.name)
            tts.save(str(tmp))
            # afplay is a macOS built-in — runs in a child process, no pygame contention
            subprocess.run(["afplay", str(tmp)], check=True)
            self.finished.emit()
        except Exception as e:
            logger.warning("TTS error: %s", e)
            self.error.emit(str(e))
        finally:
            if tmp and tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
