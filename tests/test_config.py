import os
import tempfile
from pathlib import Path

import _run
from linkdigest import config
from linkdigest.config import Config, load_env


def test_load_env_parses_comments_quotes_and_does_not_override():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ".env"
        p.write_text('# c\nFOO_T1=bar  # tail\nFOO_T2="quoted value"\nFOO_T3=\nEXIST_T4=file\n', encoding="utf-8")
        os.environ["EXIST_T4"] = "real"
        try:
            load_env(str(p))
            assert os.environ["FOO_T1"] == "bar"
            assert os.environ["FOO_T2"] == "quoted value"
            assert os.environ["FOO_T3"] == ""
            assert os.environ["EXIST_T4"] == "real"
        finally:
            for k in ("FOO_T1", "FOO_T2", "FOO_T3", "EXIST_T4"):
                os.environ.pop(k, None)


def test_from_env_types_and_blank_means_default():
    os.environ.update({"POLL_SECONDS": "30", "DRY_RUN": "true", "MAX_FRAMES": "", "FRAME_INTERVAL_SECONDS": "4"})
    try:
        c = Config.from_env()
        assert c.poll_seconds == 30 and isinstance(c.poll_seconds, int)
        assert c.dry_run is True
        assert c.max_frames == 12
        assert c.frame_interval_seconds == 4.0
        assert c.max_slides == 10
        os.environ["MAX_SLIDES"] = "4"
        assert Config.from_env().max_slides == 4
    finally:
        for k in ("POLL_SECONDS", "DRY_RUN", "MAX_FRAMES", "FRAME_INTERVAL_SECONDS", "MAX_SLIDES"):
            os.environ.pop(k, None)


def test_work_path_and_sender_defaults():
    c = Config()
    assert c.work_path.name == "linkdigest"
    assert Config(smtp_user="a@b.c").mail_sender == "a@b.c"
    assert Config(smtp_user="a@b.c", mail_from="x@y.z").mail_sender == "x@y.z"


if __name__ == "__main__":
    _run.main(globals())
