"""CLI entry point — Sprint 4.

Transcription:
    python -m vakya --input audio.wav --mode dictation
    python -m vakya --input audio.wav --mode farm_log --language hi

TTS readback:
    python -m vakya --tts "Hello world"
    python -m vakya --tts "Hello world" --voice SPEAKER_00
    python -m vakya --tts "Hello world" --tts-save output.wav

Benchmark OmniVoice (ADR-004):
    python -m vakya --benchmark-omnivoice

Windows UI:
    python -m vakya --ui
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vakya",
        description="Vakya — offline speech-to-text + TTS",
    )

    # ── Transcription arguments ───────────────────────────────────────────────
    parser.add_argument("--input", "-i", help="Path to input WAV file (16kHz, mono, 16-bit)")
    parser.add_argument(
        "--mode", "-m",
        default="dictation",
        choices=["dictation", "notes", "farm_log", "meeting"],
        help="Output format mode (default: dictation)",
    )
    parser.add_argument("--language", "-l", default=None,
                        help="ISO 639-1 code (e.g. en, hi) or omit for auto-detect")
    parser.add_argument("--no-clipboard", action="store_true",
                        help="Skip copying result to clipboard")
    parser.add_argument("--no-log", action="store_true",
                        help="Skip writing session log file")
    parser.add_argument("--session-id", default=None,
                        help="Override auto-generated session UUID")

    # ── TTS arguments ─────────────────────────────────────────────────────────
    parser.add_argument("--tts", metavar="TEXT",
                        help="Synthesise TEXT to audio and play it back")
    parser.add_argument("--voice", metavar="SPEAKER_ID", default=None,
                        help="Speaker ID from data/voice_profiles/ for voice cloning")
    parser.add_argument("--tts-save", metavar="PATH", default=None,
                        help="Save TTS output to WAV file (use with --tts)")
    parser.add_argument("--no-play", action="store_true",
                        help="Skip audio playback (use with --tts)")

    # ── UI mode ───────────────────────────────────────────────────────────────
    parser.add_argument("--ui", action="store_true",
                        help="Launch Windows PyQt6 GUI (traditional mode + hotkey overlay)")

    # ── Benchmark arguments ───────────────────────────────────────────────────
    parser.add_argument("--benchmark-omnivoice", action="store_true",
                        help="Run OmniVoice CPU RTF benchmark (ADR-004)")

    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── UI mode ───────────────────────────────────────────────────────────────
    if args.ui:
        from vakya.platform.windows.shell import launch
        launch()
        return

    # ── Benchmark mode ────────────────────────────────────────────────────────
    if args.benchmark_omnivoice:
        _run_omnivoice_benchmark()
        return

    # ── TTS-only mode ─────────────────────────────────────────────────────────
    if args.tts:
        _run_tts(args)
        return

    # ── Transcription mode ────────────────────────────────────────────────────
    if not args.input:
        parser.error("--input is required for transcription mode")

    _run_transcription(args)


def _run_transcription(args: argparse.Namespace) -> None:
    audio_path = Path(args.input)
    if not audio_path.exists():
        print(f"Error: audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    from vakya.core.pipeline import run

    print(f"Vakya — processing {audio_path.name} (mode={args.mode})")

    result = run(
        audio_path=str(audio_path),
        mode=args.mode,
        language=args.language,
        session_id=args.session_id,
        copy_to_clipboard=not args.no_clipboard,
        write_log=not args.no_log,
    )

    print("\n" + "─" * 60)
    print(result.formatted_text)
    print("─" * 60)
    print(
        f"\nDone.  lang={result.language_detected}  "
        f"speakers={result.speaker_ids}  "
        f"stt={result.stt_engine_name}  "
        f"llm={result.llm_engine_name}  "
        f"total={result.timing.get('total_sec', 0):.1f}s  "
        f"peak={result.peak_ram_mb:.0f}MB"
    )
    if result.log_path:
        print(f"Transcript: {result.log_path}")
    if result.metadata_path:
        print(f"Metadata:   {result.metadata_path}")
    if result.vocab_terms_added:
        print(f"New vocab:  {result.vocab_terms_added}")
    if result.profiles_updated:
        print(f"Profiles updated: {result.profiles_updated}")


def _run_tts(args: argparse.Namespace) -> None:
    from vakya.core.pipeline import synthesise

    text = args.tts
    print(
        f"Vakya TTS — synthesising {len(text)} chars"
        + (f" (voice={args.voice})" if args.voice else "")
    )

    wav_bytes = synthesise(
        text=text,
        voice_profile_id=args.voice,
        play=not args.no_play,
        save_path=args.tts_save,
    )

    duration = len(wav_bytes) / (16000 * 2)  # rough estimate
    print(f"Done. Audio: ~{duration:.1f}s")
    if args.tts_save:
        print(f"Saved to: {args.tts_save}")


def _run_omnivoice_benchmark() -> None:
    print("Running OmniVoice CPU RTF benchmark (ADR-004)...")
    print("This requires OmniVoice model to be installed.")
    print()
    try:
        from vakya.core.tts.omnivoice import benchmark_rtf
        rtf = benchmark_rtf()
        print(f"\nResult: CPU RTF = {rtf:.3f}")
        if rtf < 2.0:
            print("→ OmniVoice PASSES ADR-004 threshold (RTF < 2.0)")
            print("  Update engine_factory.py: set USE_OMNIVOICE = True")
        else:
            print("→ OmniVoice FAILS ADR-004 threshold (RTF >= 2.0)")
            print("  Keep CosyVoice2 as primary TTS/cloner")
        print()
        print("Update vakya/core/tts/engine_factory.py:")
        print(f"  OMNIVOICE_CPU_RTF = {rtf:.3f}")
        print(f"  USE_OMNIVOICE = {str(rtf < 2.0)}")
    except Exception as exc:
        print(f"Benchmark failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
