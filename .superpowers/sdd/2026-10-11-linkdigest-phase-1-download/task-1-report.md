# Task 1 report

Status: DONE. Commit 4f02807 "chore: scaffold, env template, test runner, hygiene test".

Done: skipped git init; created .venv (Python 3.12.10); wrote tests first, then the files. Added `.superpowers/` to .gitignore. Installed requirements.txt into the venv (succeeded). .venv not committed.

RED (`.venv/Scripts/python tests/test_hygiene.py`, before .gitignore/.env.example existed): test_no_em_dash, test_gitignore_has_required_entries, test_env_example_secrets_blank FAILED with FileNotFoundError; test_no_key_shaped_strings ok; FAIL.

GREEN: four `ok` lines then PASS; `tests/run_all.py` also PASS.

Files: .gitignore, .env.example, requirements.txt, requirements-whisper.txt, linkdigest/__init__.py, tests/_run.py, tests/run_all.py, tests/test_hygiene.py.

Concern (fixed): the brief text had `EM_DASH = "<literal em dash>"` in test_hygiene.py, which made the test flag itself. I wrote it as the escape `"—"` (the intended form). Git warns LF->CRLF on Windows (autocrlf), harmless.
