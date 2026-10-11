# Task 4 report: CLI skeleton with probe

Status: DONE
- Appended the two CLI tests before the `__main__` block of tests/test_download.py. RED: both failed (FAIL, module missing).
- Created linkdigest/__main__.py verbatim from the brief. GREEN: `.venv/Scripts/python tests/test_download.py` all ok, PASS.
- `.venv/Scripts/python tests/run_all.py`: PASS (incl. hygiene/no em dash).
- `python -m linkdigest probe notalink` -> "Not a valid link.", exit=1.
- `python -m linkdigest --help` lists `probe`.
- Files: linkdigest/__main__.py (new), tests/test_download.py (+2 tests).
- Concerns: none. Unused imports `log` and `fmt_time` use as in brief (`log` is unused; kept verbatim).

## Follow-up: fix: ignore cookies files, add probe --verbose
- .gitignore: added `cookies*.txt`, `*.cookies`; hygiene test requires `cookies*.txt` (RED: "missing cookies*.txt", then GREEN).
- probe `--verbose` flag; main() uses DEBUG when set. New test test_probe_verbose_flag (RED: argparse rejected the flag, runner aborted; GREEN after).
- Unused `log` import had already been removed in 0cc7f08.
- run_all: PASS.
