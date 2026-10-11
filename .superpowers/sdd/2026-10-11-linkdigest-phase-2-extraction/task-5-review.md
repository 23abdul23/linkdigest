# Task 5 review (commit 2cdeaf9)

Verdict: clean. No real defects. `.venv/bin/python tests/run_all.py` prints PASS (5/5 transcript tests, hygiene tests ok).

Matches the plan and the research Transcription section: base int8 CPU, beam_size=1, vad_filter, task=transcribe, stdlib wave to float32 numpy, language logged, missing faster-whisper message names the package and `pip install`. Commit message is plain with no attribution lines. No em dashes, no secrets. Tests are meaningful: the rolling VTT test asserts exact output, the no-audio test uses a real ffmpeg-generated silent video, the fake-model test asserts the transcribe kwargs, text stripping, blank-segment drop and the language banner.

## Extra parse_vtt probes (scratch, all behaved correctly)
- Cue id line before timestamp, `align:` settings, mm:ss without hours, hours over 1, CRLF, BOM, NOTE and STYLE blocks (including NOTE containing "-->"), header with no blank line before the first cue, whitespace-only separator lines, word-timing tags, HTML entities: all fine.
- Repeated legit line far apart (6 cues later): kept. Rolling cue whose line 1 is the previous line 2: deduped. Empty/whitespace cues: skipped, no crash.

## transcribe_audio probes
- Real mp4 with a tone: WAV loads as float32 mono, peak < 1.0, transcribe called, "No speech was detected." banner path works.
- Silent video (no audio stream) and a junk file: ffmpeg error becomes RuntimeError, caught, source "none" plus banner. Empty-WAV (<= 44 bytes) branch also covered.
- Non-English banner and model cache keyed by name: correct. 16-bit/mono assumption is guaranteed by the ffmpeg flags.

## Minors (no action required)
1. linkdigest/transcript.py:36-37: a legitimately repeated line inside the 4-cue window ("no" / "no", "ha" in consecutive cues) is dropped. Indistinguishable from rolling captions; acceptable for auto captions, slightly lossy for manual subs.
2. linkdigest/transcript.py:70: `except RuntimeError` treats any ffmpeg failure (corrupt file, disk full) as "no readable audio track". The banner is reasonable but can hide a real error; ffmpeg's stderr is not logged. `subprocess.TimeoutExpired` (600 s in run_ffmpeg) is not caught and propagates.
3. linkdigest/transcript.py:23: `&nbsp;` becomes U+00A0 and survives inside a line ("x\xa0y"). Cosmetic.
4. linkdigest/transcript.py:12: timestamp regex requires whitespace before `-->`; `00:01.000-->00:02.000` yields no cues. Non-standard, rare.
5. requirements-whisper.txt does not list numpy; it arrives transitively via faster-whisper, and the test skips cleanly if absent.
6. Real model load and transcription remain unrun (needs model download), as the task report states.
