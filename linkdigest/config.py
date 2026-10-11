import os
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path


def load_env(path=".env"):
    """Tiny .env loader. Real environment variables win over the file."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    source_csv: str = "./links.csv"
    poll_seconds: int = 120
    db_path: str = "./jobs.db"
    work_dir: str = ""
    out_dir: str = "./out"
    dry_run: bool = False
    max_video_seconds: int = 300
    long_video_action: str = "skip"
    frame_interval_seconds: float = 2.0
    max_frames: int = 12
    frame_hash_distance: int = 10
    whisper_model: str = "base"
    ytdlp_cookies: str = ""
    js_runtime: str = "node"
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.6-flash"
    llm_fallback_model: str = "gemini-3.5-flash-lite"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"
    max_text_chars: int = 60000
    min_text_chars: int = 500
    jina_fallback: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    mail_from: str = ""
    mail_to: str = ""
    notify_on_failure: bool = True
    max_attempts: int = 3
    test_youtube_url: str = ""
    test_youtube_nocaps_url: str = ""
    test_blog_url: str = ""
    test_long_video_url: str = ""
    test_instagram_url: str = ""
    test_instagram_post_url: str = ""

    @classmethod
    def from_env(cls):
        kw = {}
        for f in fields(cls):
            raw = os.environ.get(f.name.upper())
            if raw is None or raw == "":
                continue
            kw[f.name] = _bool(raw) if f.type is bool else f.type(raw)
        return cls(**kw)

    @property
    def work_path(self):
        return Path(self.work_dir) if self.work_dir else Path(tempfile.gettempdir()) / "linkdigest"

    @property
    def mail_sender(self):
        return self.mail_from or self.smtp_user
