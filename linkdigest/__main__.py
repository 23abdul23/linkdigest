import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from .classify import classify, normalize_url
from .config import Config, load_env
from .download import download, probe
from .util import fmt_time, log


def cmd_probe(cfg, url, do_download):
    """Probe a link (and optionally download it) and print what yt-dlp saw. For manual checks."""
    link = normalize_url(url)
    if not link:
        print("Not a valid link.")
        return 1
    kind = classify(link)
    try:
        p = probe(link, kind, cfg)
    except Exception as e:                      # show the class so mapped vs unmapped is visible
        print(f"{type(e).__name__}: {e}")
        return 1
    print(f"kind={kind} title={p.title!r} duration={fmt_time(p.duration)} ({p.duration}s)")
    if not do_download:
        return 0
    cfg.work_path.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="job-", dir=cfg.work_path))
    try:
        d = download(link, kind, tmp, cfg)
        print(f"downloaded={d.video.name} bytes={d.video.stat().st_size} captions={'yes' if d.vtt else 'no'}")
        return 0
    except Exception as e:
        print(f"{type(e).__name__}: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser():
    ap = argparse.ArgumentParser(prog="linkdigest")
    ap.add_argument("--dry-run", action="store_true", help="write emails to OUT_DIR instead of sending")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="probe a video link, optionally download it")
    p.add_argument("url")
    p.add_argument("--download", action="store_true")
    return ap


def main(argv=None):
    load_env()
    args = build_parser().parse_args(argv)
    cfg = Config.from_env()
    if args.dry_run:
        cfg.dry_run = True
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.cmd == "probe":
        return cmd_probe(cfg, args.url, args.download)
    return 2


if __name__ == "__main__":
    sys.exit(main())
