import re

import _run

ROOT = _run.ROOT
EM_DASH = "\u2014"
SCAN_DIRS = ["linkdigest", "tests"]
SCAN_FILES = ["smoke.py", "smoke_ig.py", "README.md", ".env.example", ".gitignore",
              "requirements.txt", "requirements-whisper.txt"]
SECRET_KEYS = ["LLM_API_KEY", "SMTP_USER", "SMTP_PASS", "MAIL_FROM", "MAIL_TO", "YTDLP_COOKIES"]


def project_files():
    out = []
    for d in SCAN_DIRS:
        out += [p for p in (ROOT / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    out += [ROOT / f for f in SCAN_FILES if (ROOT / f).exists()]
    return out


def env_values():
    vals = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.split(" #")[0].strip()
    return vals


def test_no_em_dash():
    bad = [str(p.relative_to(ROOT)) for p in project_files()
           if EM_DASH in p.read_text(encoding="utf-8", errors="ignore")]
    assert not bad, f"em dash found in {bad}"


def test_gitignore_has_required_entries():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    for need in (".env", "*.db", "links.csv", "out/", ".venv/"):
        assert need in lines, f".gitignore is missing {need}"


def test_env_example_secrets_blank():
    vals = env_values()
    for k in SECRET_KEYS:
        assert k in vals and vals[k] == "", f"{k} must be present and blank"
    for k, v in vals.items():
        if k.startswith("TEST_"):
            assert v == "", f"{k} must be blank in the example"


def test_no_key_shaped_strings():
    pat = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{20,}")
    bad = [str(p.relative_to(ROOT)) for p in project_files()
           if pat.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not bad, f"key-shaped string in {bad}"


if __name__ == "__main__":
    _run.main(globals())
