# Task 6 report: frames.py

Files: linkdigest/frames.py (new), tests/test_frames.py (new).

Tests: wrote tests/test_frames.py first, saw ImportError (no linkdigest.frames), then added frames.py.
Full suite (`.venv/bin/python tests/run_all.py`): all ok, PASS. Pillow 12.3.0 works with the
get_flattened_data / getdata fallback in dhash.

Deviations from the plan:
- Frame has a 4th field `label: str = ""` per the Amendments; added test_frame_label_defaults_to_empty_string.
- Three-scene test passed as written; the Step 4 fixture timing note was not needed.
- Staged explicit paths instead of `git add -A`.
