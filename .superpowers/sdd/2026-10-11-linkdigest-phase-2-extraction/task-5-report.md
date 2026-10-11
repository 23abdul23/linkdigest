# Task 5 report: transcript.py

## Files
- Created `linkdigest/transcript.py` (Transcript, parse_vtt, _get_model, _load_wav, transcribe_audio), exactly as in the plan.
- Created `tests/test_transcript.py` (5 tests, as in the plan).
- Modified `tests/fixtures.py`: appended `ROLLING_VTT`, `ROLLING_EXPECTED`, `make_video`; added `import random` to the top import block. The plan's unused `subprocess` and `tempfile` imports were not added, `pathlib` was already imported.

## Tests
Test-first: `tests/test_transcript.py` failed with ImportError before the module existed. Now 5/5 pass, and `tests/run_all.py` passes. numpy is installed, so the fake-Whisper test really ran (no skip).

Real stack checks (offline, no model downloaded): faster-whisper 1.2.1 imports; `WhisperModel.transcribe` accepts `beam_size`, `vad_filter`, `task`; `_load_wav` returns a float32 array from a real WAV. Not run: a real model load and transcription (needs a model download).

## Deviations
None in behaviour. No defect found in the plan code. Only the fixtures import placement differs, as noted above.
