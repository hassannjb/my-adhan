#!/usr/bin/env python3
"""
Download and cache both Whisper models used by the voice feature.

  tiny     — ~75 MB  — fast, lower accuracy
  large-v3 — ~1.5 GB — slower, much higher accuracy (default in the GUI)

Run once before using voice input:
    python3 scripts/download_whisper_models.py
"""
import time
from faster_whisper import WhisperModel

for name in ("tiny", "large-v3"):
    print(f"Downloading {name}...", flush=True)
    t0 = time.time()
    WhisperModel(name, device="cpu", compute_type="int8")
    print(f"  {name} ready ({time.time() - t0:.1f}s)")

print("\nBoth models cached. Voice input is ready.")
