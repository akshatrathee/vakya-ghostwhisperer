"""WhisperX diarizer — unified STT+diarization layer for Windows.

WhisperX (m-bain/whisperX, BSD-2) packages faster-whisper + pyannote-audio
+ forced alignment into a single pip-installable package that installs
reliably on Windows where standalone pyannote-audio does not.

On Windows this replaces both the STT step and diarization step with a
single WhisperX call. The result is adapted to our STTResult + DiarSegment
interfaces so the rest of the pipeline is unaffected.

See ADR-005 for the rationale.
"""

from __future__ import annotations

import logging
import os
import tracemalloc
from typing import List

from .base import Diarizer, DiarSegment
from ..stt.base import STTEngine, STTResult, STTSegment

log = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "stt", "faster-whisper-large-v3-turbo",
)


class WhisperXEngine(STTEngine, Diarizer):
    """Satisfies both STTEngine and Diarizer interfaces.

    Call transcribe_and_diarize() to get both results in one pass.
    transcribe() and diarize() individually work but are less efficient.
    """

    def __init__(
        self,
        model_dir: str | None = None,
        hf_token: str | None = None,
        device: str = "cpu",
    ) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._hf_token = hf_token or os.environ.get("HF_TOKEN", "")
        self._device = device
        self._model = None
        self._align_model = None
        self._diarize_model = None

        if not self._hf_token:
            log.warning(
                "WhisperX: HF_TOKEN not set. Speaker diarization will be skipped. "
                "Provide a HuggingFace token via the onboarding wizard or set the "
                "HF_TOKEN environment variable to enable speaker labels."
            )

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import whisperx  # type: ignore

            self._model = whisperx.load_model(
                self._model_dir,
                device=self._device,
                compute_type="int8",
            )
            log.info("WhisperX model loaded from %s", self._model_dir)
        except ImportError as exc:
            raise ImportError(
                "whisperx not installed. Run: pip install whisperx"
            ) from exc

    def transcribe_and_diarize(
        self,
        audio_path: str,
        language: str = "auto",
        vocab_hint: List[str] | None = None,
        num_speakers: int | None = None,
    ) -> tuple[STTResult, List[DiarSegment]]:
        self._load()
        import whisperx  # type: ignore

        tracemalloc.start()

        lang = None if language == "auto" else language
        prompt = ", ".join(vocab_hint) if vocab_hint else None

        audio = whisperx.load_audio(audio_path)

        result = self._model.transcribe(
            audio,
            language=lang,
            initial_prompt=prompt,
            batch_size=4,
        )
        detected_lang = result.get("language", lang or "en")

        # Align word timestamps
        align_model, metadata = whisperx.load_align_model(
            language_code=detected_lang, device=self._device
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, self._device
        )

        # Diarize — requires HF_TOKEN; skip with warning if absent
        if self._hf_token:
            diarize_model = whisperx.DiarizationPipeline(
                use_auth_token=self._hf_token, device=self._device
            )
            diarize_segments = diarize_model(audio, num_speakers=num_speakers)
            result = whisperx.assign_word_speakers(diarize_segments, result)
        else:
            log.warning(
                "WhisperX: diarization skipped — no HF_TOKEN. "
                "All speech will be attributed to 'Speaker 1'. "
                "Set HF_TOKEN to enable speaker identification."
            )
            diarize_segments = None

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        log.info("WhisperX: peak RAM=%.1fMB, lang=%s", peak / 1e6, detected_lang)

        stt_segments = [
            STTSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
                speaker_id=seg.get("speaker", "Speaker 1"),
            )
            for seg in result["segments"]
        ]
        full_text = " ".join(s.text for s in stt_segments)
        stt_result = STTResult(
            text=full_text,
            segments=stt_segments,
            language_detected=detected_lang,
        )

        if diarize_segments is not None:
            diar_segments = [
                DiarSegment(
                    speaker_id=row.speaker,
                    start_sec=row.start,
                    end_sec=row.end,
                )
                for _, row in diarize_segments.iterrows()
            ]
        else:
            diar_segments = []

        return stt_result, diar_segments

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        vocab_hint: List[str] | None = None,
    ) -> STTResult:
        stt_result, _ = self.transcribe_and_diarize(audio_path, language, vocab_hint)
        return stt_result

    def diarize(self, audio_path: str) -> List[DiarSegment]:
        _, diar_segments = self.transcribe_and_diarize(audio_path)
        return diar_segments
