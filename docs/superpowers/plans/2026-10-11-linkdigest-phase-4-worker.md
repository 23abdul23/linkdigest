# linkdigest Phase 4: CSV source, queue, worker

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Read the index `2026-10-11-linkdigest.md` first. Phase 3 must be tagged `gate-3`. Steps use checkbox syntax.

**Goal of this phase:** `python -m linkdigest once` and `run` read links from `links.csv`, queue them in SQLite, process them with the pipeline that already works, write `done` / `failed` / `skipped` back into the CSV, and survive crashes, restarts, retries and a user editing the file. The spec's Test A passes.

**Spec:** handoff "Input", "Queue", "Routing", "Verification A", and `research.md` Input source and Queue sections and deviations 1 and 2.

## Interfaces defined in this phase

```python
# source_csv.py
Row(row_key: str, url: str, notes: str, status: str, detail: str)
row_key(url: str) -> str                         # canonical(normalize_url(url)), or the raw text for junk rows
CsvSource(path)
  .rows() -> list[Row]                           # every row that has a url
  .mark(row_key: str, status: str, detail: str) -> bool   # True written, False if the file is locked

# jobqueue.py
Job(id: int, row_key: str, url: str, notes: str, attempts: int)
JobQueue(db_path)
  .enqueue(row_key, url, notes) -> bool          # False if the row_key already exists
  .claim() -> Job | None                         # marks it processing, attempts += 1
  .finish(job_id, status, error)                 # status: done | failed | skipped ; csv_synced = 0
  .requeue(job_id, error)                        # back of the queue
  .reset_for_retry(row_key, notes)               # user cleared the status in the CSV
  .get(row_key) -> sqlite3.Row | None
  .set_csv_synced(job_id)
  .unsynced() -> list[sqlite3.Row]               # terminal jobs whose status is not yet in the CSV

# pipeline.py (added)
sync(src, q) ; flush(src, q) ; handle(cfg, q, src, job) ; run_cycle(cfg, q, src)
run_once(cfg) ; run_forever(cfg)
```

Design rules (from `research.md`, binding): the DB is the source of truth for status, the CSV for url and notes. Always write the DB first, then the CSV. `mark()` re-reads the file from disk every time so a user's concurrent edit is never overwritten with stale data. A locked file never fails a job: the status stays in SQLite and is flushed next poll.

---

### Task 12: source_csv.py

**Files:**
- Create: `linkdigest/source_csv.py`
- Test: `tests/test_source_csv.py`

**Interfaces:**
- Consumes: `canonical`, `normalize_url`, `log`.
- Produces: `Row`, `row_key`, `CsvSource`.

- [ ] **Step 1: Write the failing tests** `tests/test_source_csv.py`

```python
import os
import tempfile
from pathlib import Path

import _run
from linkdigest import source_csv
from linkdigest.source_csv import CsvSource, row_key

HEADER = "url,notes,status,detail\r\n"


def make(d, body="", enc="utf-8"):
    p = Path(d) / "links.csv"
    p.write_bytes((HEADER + body).encode(enc))
    return p


def test_creates_file_with_header_when_missing():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "links.csv"
        src = CsvSource(p)
        assert p.read_text(encoding="utf-8-sig").splitlines()[0] == "url,notes,status,detail"
        assert src.rows() == []


def test_row_keys_unify_variants_and_junk_keeps_raw_text():
    k = row_key("https://youtu.be/abc")
    assert k == row_key("youtu.be/abc") == row_key("https://www.youtube.com/watch?v=abc&utm_source=x")
    assert row_key("hello world") == "hello world"


def test_rows_read_bom_cp1252_blank_lines_and_status_case():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "links.csv"
        p.write_bytes(b"\xef\xbb\xbf" + (HEADER + "https://a.test/x,note one,DONE,ok\r\n,,,\r\n").encode())
        rows = CsvSource(p).rows()
        assert len(rows) == 1 and rows[0].status == "done" and rows[0].notes == "note one"
        q = make(d, "https://a.test/y,caf\xe9 note,,\r\n", enc="cp1252")
        assert CsvSource(q).rows()[0].notes == "caf\xe9 note"


def test_semicolon_file_fails_loudly_with_a_helpful_message():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "links.csv"
        p.write_text("url;notes;status;detail\nhttps://a.test;n;;\n", encoding="utf-8")
        try:
            CsvSource(p).rows()
        except ValueError as e:
            assert "header" in str(e)
        else:
            raise AssertionError("expected ValueError")


def test_mark_updates_only_matching_rows_and_caps_detail():
    with tempfile.TemporaryDirectory() as d:
        p = make(d, "https://a.test/x,n1,,\r\nhttps://b.test/y,n2,,\r\nhttps://a.test/x?utm_source=z,dup,,\r\n")
        src = CsvSource(p)
        assert src.mark(row_key("https://a.test/x"), "failed", "x" * 500) is True
        rows = src.rows()
        assert [r.status for r in rows] == ["failed", "", "failed"]       # duplicate rows share the outcome
        assert len(rows[0].detail) == 300 and rows[1].notes == "n2"
        assert not list(Path(d).glob("*.tmp"))


def test_mark_unknown_key_is_a_noop():
    with tempfile.TemporaryDirectory() as d:
        p = make(d, "https://a.test/x,n,,\r\n")
        before = p.read_bytes()
        assert CsvSource(p).mark("https://nowhere.test", "done", "") is True
        assert p.read_bytes() == before


def test_mark_rereads_so_a_users_concurrent_edit_survives():
    with tempfile.TemporaryDirectory() as d:
        p = make(d, "https://a.test/x,n,,\r\n")
        src = CsvSource(p)
        src.rows()                                                    # service has seen one row
        p.write_bytes(p.read_bytes() + b"https://new.test/z,added by user,,\r\n")   # user appends a row
        src.mark(row_key("https://a.test/x"), "done", "")
        urls = [r.url for r in src.rows()]
        assert urls == ["https://a.test/x", "https://new.test/z"]


def test_locked_file_returns_false_and_leaves_no_temp_files():
    with tempfile.TemporaryDirectory() as d:
        p = make(d, "https://a.test/x,n,,\r\n")
        before = p.read_bytes()

        def locked(src, dst):
            raise PermissionError("locked by Excel")
        with _run.patched(source_csv.os, "replace", locked), _run.patched(source_csv, "_sleep", lambda s: None):
            assert CsvSource(p).mark(row_key("https://a.test/x"), "done", "") is False
        assert p.read_bytes() == before and not list(Path(d).glob("*.tmp"))


def test_hindi_note_and_commas_quotes_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = make(d)
        src = CsvSource(p)
        note = 'सिर्फ कमांड्स, "quoted", and a\nnewline'
        with open(p, "a", encoding="utf-8", newline="") as f:
            import csv
            csv.writer(f).writerow(["https://a.test/x", note, "", ""])
        src.mark(row_key("https://a.test/x"), "done", "ok")
        r = src.rows()[0]
        assert r.notes == note and r.status == "done"


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 2: Run to verify failure**

Run: `python tests/test_source_csv.py`
Expected: `ModuleNotFoundError: No module named 'linkdigest.source_csv'`.

- [ ] **Step 3: Write `linkdigest/source_csv.py`**

```python
import csv
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .classify import canonical, normalize_url
from .util import log

FIELDS = ["url", "notes", "status", "detail"]
_sleep = time.sleep


@dataclass
class Row:
    row_key: str
    url: str
    notes: str
    status: str
    detail: str


def row_key(url):
    link = normalize_url(url)
    return canonical(link) if link else url.strip()


class CsvSource:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            self._write([])

    def _read(self):
        for enc in ("utf-8-sig", "cp1252"):                  # Excel may save "CSV" as cp1252
            try:
                with open(self.path, encoding=enc, newline="") as f:
                    rd = csv.DictReader(f)
                    names = [(h or "").strip().lower() for h in (rd.fieldnames or [])]
                    if "url" not in names:
                        raise ValueError("CSV needs a header row: url,notes,status,detail "
                                         "(comma separated; check the delimiter your editor saved)")
                    return [{(k or "").strip().lower(): (v or "") for k, v in r.items() if isinstance(v, (str, type(None)))}
                            for r in rd]
            except UnicodeDecodeError:
                continue
        raise ValueError("CSV is not UTF-8 or cp1252 text")

    def rows(self):
        out = []
        for r in self._read():
            url = r.get("url", "").strip()
            if url:
                out.append(Row(row_key(url), url, r.get("notes", "").strip(),
                               r.get("status", "").strip().lower(), r.get("detail", "")))
        return out

    def mark(self, key, status, detail):
        rows = self._read()                                  # always re-read: never write stale data
        hit = False
        for r in rows:
            url = r.get("url", "").strip()
            if url and row_key(url) == key:
                r["status"], r["detail"], hit = status, detail[:300], True
        return self._write(rows) if hit else True

    def _write(self, rows):
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
                w.writeheader()
                for r in rows:
                    w.writerow({k: r.get(k, "") for k in FIELDS})
                f.flush()
                os.fsync(f.fileno())
            for attempt in range(5):
                try:
                    os.replace(tmp, self.path)
                    return True
                except PermissionError:                       # Windows: an editor holds the file open
                    if attempt < 4:
                        _sleep(1)
            log.warning("links.csv is locked by another program; status will be written on the next poll")
            return False
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
```

- [ ] **Step 4: Run all tests**

Run: `python tests/run_all.py`
Expected: all `ok`, `PASS`. The `_read` dict comprehension drops the `None` key DictReader uses for overflow columns; if a row with extra commas crashes, fix it there.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: CSV source with re-read, atomic replace and lock tolerance"
```

---

### Task 13: jobqueue.py

**Files:**
- Create: `linkdigest/jobqueue.py`
- Test: `tests/test_jobqueue.py`

**Interfaces:**
- Produces: `Job`, `JobQueue` as listed above.

- [ ] **Step 1: Write the failing tests** `tests/test_jobqueue.py`

```python
import tempfile
from pathlib import Path

import _run
from linkdigest.jobqueue import JobQueue


def db(d):
    return str(Path(d) / "jobs.db")


def test_enqueue_is_idempotent_across_restarts():
    with tempfile.TemporaryDirectory() as d:
        q = JobQueue(db(d))
        assert q.enqueue("k1", "https://a.test/1", "n") is True
        assert q.enqueue("k1", "https://other.test", "changed") is False
        q2 = JobQueue(db(d))
        assert q2.enqueue("k1", "https://a.test/1", "n") is False
        assert q2.get("k1")["url"] == "https://a.test/1"


def test_claim_is_fifo_counts_attempts_and_empties():
    with tempfile.TemporaryDirectory() as d:
        q = JobQueue(db(d))
        for k in "abc":
            q.enqueue(k, f"https://{k}.test", "")
        j = q.claim()
        assert (j.row_key, j.attempts) == ("a", 1) and q.get("a")["status"] == "processing"
        assert [q.claim().row_key, q.claim().row_key, q.claim()] == ["b", "c", None]


def test_requeue_goes_to_the_back_of_the_line():
    with tempfile.TemporaryDirectory() as d:
        q = JobQueue(db(d))
        for k in "abc":
            q.enqueue(k, f"https://{k}.test", "")
        a = q.claim()
        q.requeue(a.id, "blocked")
        assert [q.claim().row_key for _ in range(3)] == ["b", "c", "a"]
        assert q.get("a")["attempts"] == 2 and q.get("a")["error"] == "blocked"


def test_crash_recovery_resets_processing_to_queued_keeping_attempts():
    with tempfile.TemporaryDirectory() as d:
        q = JobQueue(db(d))
        q.enqueue("a", "https://a.test", "")
        q.claim()
        del q                                                    # simulated crash: no finish()
        q2 = JobQueue(db(d))
        assert q2.get("a")["status"] == "queued" and q2.get("a")["attempts"] == 1
        assert q2.claim().attempts == 2


def test_finish_unsynced_and_synced_flow():
    with tempfile.TemporaryDirectory() as d:
        q = JobQueue(db(d))
        q.enqueue("a", "https://a.test", "")
        j = q.claim()
        q.finish(j.id, "done", "")
        assert [r["row_key"] for r in q.unsynced()] == ["a"]
        q.set_csv_synced(j.id)
        assert q.unsynced() == [] and q.get("a")["csv_synced"] == 1


def test_reset_for_retry_requeues_with_fresh_attempts_and_new_notes():
    with tempfile.TemporaryDirectory() as d:
        q = JobQueue(db(d))
        q.enqueue("a", "https://a.test", "old")
        q.enqueue("b", "https://b.test", "")
        j = q.claim()
        q.finish(j.id, "failed", "boom")
        q.reset_for_retry("a", "new note")
        row = q.get("a")
        assert (row["status"], row["attempts"], row["notes"], row["error"]) == ("queued", 0, "new note", None)
        assert [q.claim().row_key, q.claim().row_key] == ["b", "a"]


def test_wal_mode_is_on():
    with tempfile.TemporaryDirectory() as d:
        q = JobQueue(db(d))
        assert q.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 2: Run to verify failure**

Run: `python tests/test_jobqueue.py`
Expected: `ModuleNotFoundError: No module named 'linkdigest.jobqueue'`.

- [ ] **Step 3: Write `linkdigest/jobqueue.py`**

```python
import datetime as dt
import sqlite3
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY,
  row_key TEXT UNIQUE NOT NULL,
  url TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL,
  seq INTEGER NOT NULL,
  csv_synced INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS jobs_status_seq ON jobs(status, seq);
"""
_NEXT_SEQ = "(SELECT COALESCE(MAX(seq), 0) + 1 FROM jobs)"


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: int
    row_key: str
    url: str
    notes: str
    attempts: int


class JobQueue:
    """SQLite queue for one worker. Each statement is its own atomic transaction (autocommit)."""

    def __init__(self, path):
        if sqlite3.sqlite_version_info < (3, 35):
            raise RuntimeError("SQLite 3.35 or newer is required (UPDATE ... RETURNING)")
        self.db = sqlite3.connect(path, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        self.db.execute("UPDATE jobs SET status='queued' WHERE status='processing'")   # crash recovery

    def enqueue(self, row_key, url, notes):
        now = _now()
        cur = self.db.execute(
            "INSERT OR IGNORE INTO jobs(row_key,url,notes,status,attempts,created,updated,seq) "
            f"VALUES(?,?,?,'queued',0,?,?,{_NEXT_SEQ})", (row_key, url, notes, now, now))
        return cur.rowcount == 1

    def claim(self):
        cur = self.db.execute(
            "UPDATE jobs SET status='processing', attempts=attempts+1, updated=? "
            "WHERE id=(SELECT id FROM jobs WHERE status='queued' ORDER BY seq LIMIT 1) "
            "RETURNING id,row_key,url,notes,attempts", (_now(),))
        r = cur.fetchall()
        return Job(*r[0]) if r else None

    def finish(self, job_id, status, error):
        self.db.execute("UPDATE jobs SET status=?, error=?, csv_synced=0, updated=? WHERE id=?",
                        (status, error, _now(), job_id))

    def requeue(self, job_id, error):
        self.db.execute(f"UPDATE jobs SET status='queued', error=?, seq={_NEXT_SEQ}, updated=? WHERE id=?",
                        (error, _now(), job_id))

    def reset_for_retry(self, row_key, notes):
        self.db.execute("UPDATE jobs SET status='queued', attempts=0, error=NULL, notes=?, csv_synced=0, "
                        f"seq={_NEXT_SEQ}, updated=? WHERE row_key=?", (notes, _now(), row_key))

    def get(self, row_key):
        return self.db.execute("SELECT * FROM jobs WHERE row_key=?", (row_key,)).fetchone()

    def set_csv_synced(self, job_id):
        self.db.execute("UPDATE jobs SET csv_synced=1 WHERE id=?", (job_id,))

    def unsynced(self):
        return self.db.execute("SELECT * FROM jobs WHERE status IN ('done','failed','skipped') "
                               "AND csv_synced=0 ORDER BY id").fetchall()
```

- [ ] **Step 4: Run all tests**

Run: `python tests/run_all.py`
Expected: all `ok`, `PASS`. If `test_requeue_goes_to_the_back_of_the_line` shows `a` first, check that `requeue` sets `seq` from the table maximum (the subquery reads the row's own old value in the same statement, so it is still the max plus one).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: SQLite job queue with crash recovery and requeue-to-back"
```

---

### Task 14: worker (sync, handle, run_cycle) and Test A

**Files:**
- Modify: `linkdigest/pipeline.py` (append the worker), `linkdigest/__main__.py` (add `once`, `run`)
- Test: `tests/test_offline.py` (spec Test A), `tests/test_worker.py`

**Interfaces:**
- Consumes: `CsvSource`, `JobQueue`, `process_job`, `deliver`, `render_notice`, error classes.
- Produces: `sync`, `flush`, `handle`, `run_cycle`, `run_once`, `run_forever`.

- [ ] **Step 1: Write the failing spec test** `tests/test_offline.py`

```python
import tempfile
from pathlib import Path

import _run
from fixtures import ROLLING_VTT, FakeResp, FakeYDL, article_html, make_video
from linkdigest import download, llm, pipeline, text_proc
from linkdigest.classify import classify
from linkdigest.config import Config
from linkdigest.jobqueue import JobQueue
from linkdigest.source_csv import CsvSource
from yt_dlp.utils import DownloadError

YT = "https://www.youtube.com/watch?v=abcdefghijk"
BLOG = "https://blog.test/post"
LONG = "https://www.youtube.com/watch?v=longlonglon"
IG = "https://www.instagram.com/reel/C-cTZA1M9mE/"
DONE = "https://blog.test/old"
EM = "—"
IG_ERR = "ERROR: [Instagram] C-cTZA1M9mE: Instagram sent an empty media response. Check if this post is accessible"
RESULT = {"summary": ["Use pip.", "Install deps.", "Run it."],
          "key_points": ["a", "b", "c", "d", "e", "Never run <script>alert(1)</script>"],
          "action_items": ["Try pip install requests"], "timestamps": [{"t": 65, "point": "Install step"}],
          "note_applied": "Only the commands are listed."}


def make_ydl(video):
    class Y(FakeYDL):
        calls = []

        def extract_info(self, url, download=False):
            Y.calls.append(("probe", url))
            if "instagram" in url:
                raise DownloadError(IG_ERR)
            if "longlong" in url:
                return {"title": "Long one", "duration": 900, "is_live": False}
            return {"title": "A talk", "duration": 270, "is_live": False}

        def download(self, urls):
            Y.calls.append(("download", urls[0]))
            out = Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
            out.write_bytes(video)
            out.with_name("v.en.vtt").write_text(ROLLING_VTT, encoding="utf-8")
    return Y


def llm_post(counter=None):
    def post(url, headers=None, json=None, timeout=None):
        if counter is not None:
            counter.append(1)
        body = __import__("json").dumps(RESULT)
        return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": body}]}}]})
    return post


def blog_get(url, headers=None, timeout=None):
    return FakeResp(200, text=article_html(), headers={"Content-Type": "text/html"})


def write_csv(path, rows):
    import csv
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "notes", "status", "detail"])
        w.writerows(rows)


def setup(d, rows):
    d = Path(d)
    write_csv(d / "links.csv", rows)
    cfg = Config(source_csv=str(d / "links.csv"), db_path=str(d / "jobs.db"), out_dir=str(d / "out"),
                 work_dir=str(d / "work"), dry_run=True, llm_api_key="k", min_text_chars=200)
    return cfg, CsvSource(cfg.source_csv), JobQueue(cfg.db_path)


def emails(cfg):
    return sorted(Path(cfg.out_dir).glob("*.html")) if Path(cfg.out_dir).exists() else []


def test_a_full_cycle_matches_the_spec():
    with tempfile.TemporaryDirectory() as d:
        video = make_video(d).read_bytes()
        Y = make_ydl(video)
        cfg, src, q = setup(d, [[YT, "only the commands", "", ""], [BLOG, "", "", ""], [LONG, "", "", ""],
                                [IG, "what is shown", "", ""], [DONE, "keep me", "done", "old detail"]])
        with _run.patched(download, "new_ydl", Y), _run.patched(text_proc, "http_get", blog_get), \
                _run.patched(llm, "http_post", llm_post()):
            pipeline.run_cycle(cfg, q, src)
            rows = {r.url: r for r in src.rows()}
            assert {u: r.status for u, r in rows.items()} == {
                YT: "done", BLOG: "done", LONG: "skipped", IG: "failed", DONE: "done"}
            assert rows[IG].detail == download.IG_BLOCKED
            assert rows[LONG].detail == "Video is 15:00, over the 5:00 limit."
            assert (rows[DONE].detail, rows[DONE].notes) == ("old detail", "keep me")     # untouched
            files = emails(cfg)
            assert len(files) == 4, [f.name for f in files]
            pages = {f.name: f.read_text(encoding="utf-8") for f in files}
            yt = next(h for h in pages.values() if "t=65s" in h)
            assert "only the commands" in yt and "1:05" in yt and "&lt;script&gt;" in yt
            blog = next(h for h in pages.values() if "Why caching matters" in h)
            assert "Timestamps" not in blog
            assert any("Skipped" in h and "15:00" in h for h in pages.values())
            assert any("Failed" in h and "Instagram blocked" in h for h in pages.values())
            for h in pages.values():
                assert EM not in h and "<script" not in h
            for f in files:
                assert EM not in f.with_suffix(".txt").read_text(encoding="utf-8")
            assert not [c for c in Y.calls if c[0] == "download" and ("longlong" in c[1] or "instagram" in c[1])]
            assert [c[0] for c in Y.calls if "instagram" in c[1]] == ["probe", "probe"]      # retried once only
            before = [f.name for f in emails(cfg)]
            pipeline.run_cycle(cfg, q, src)                                                  # second cycle
            assert [f.name for f in emails(cfg)] == before


def test_blocked_instagram_goes_to_the_back_and_never_delays_other_jobs():
    with tempfile.TemporaryDirectory() as d:
        Y = make_ydl(make_video(d).read_bytes())
        cfg, src, q = setup(d, [[IG, "", "", ""], [YT, "", "", ""], [BLOG, "", "", ""]])
        with _run.patched(download, "new_ydl", Y), _run.patched(text_proc, "http_get", blog_get), \
                _run.patched(llm, "http_post", llm_post()):
            pipeline.run_cycle(cfg, q, src)
        order = [c[1] for c in Y.calls if c[0] == "probe"]
        assert order == [IG, YT, IG], order            # the second Instagram try comes after the YouTube job
        assert {r.url: r.status for r in src.rows()} == {IG: "failed", YT: "done", BLOG: "done"}


def test_classify_sanity_for_the_spec_urls():
    assert classify(YT) == "youtube" and classify(IG) == "instagram" and classify(BLOG) == "web"


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 2: Write the failing worker tests** `tests/test_worker.py`

```python
import tempfile
from pathlib import Path

import _run
from fixtures import FakeResp, article_html
from linkdigest import llm, pipeline, source_csv, text_proc
from linkdigest.jobqueue import JobQueue
from linkdigest.source_csv import CsvSource
from test_offline import BLOG, blog_get, emails, llm_post, setup, write_csv


def run(cfg, q, src, post=None):
    with _run.patched(text_proc, "http_get", blog_get), _run.patched(llm, "http_post", post or llm_post()):
        pipeline.run_cycle(cfg, q, src)


def test_transient_errors_requeue_then_give_up_with_the_reason():
    calls = []

    def always_500(url, headers=None, json=None, timeout=None):
        calls.append(1)
        return FakeResp(500)
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [[BLOG, "", "", ""]])
        cfg.max_attempts = 3
        with _run.patched(llm, "_sleep", lambda s: None):
            run(cfg, q, src, always_500)
        row = src.rows()[0]
        assert row.status == "failed" and row.detail.startswith("Gave up after 3 attempts:"), row.detail
        assert "HTTP 500" in row.detail
        assert len(calls) == 12                                  # 3 attempts x 4 LLM tries
        assert len(emails(cfg)) == 1                             # one failure notice, nothing else


def test_permanent_errors_fail_immediately_without_retry():
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [[BLOG, "", "", ""]])
        cfg.llm_api_key = ""
        run(cfg, q, src)
        row = src.rows()[0]
        assert row.status == "failed" and "LLM_API_KEY" in row.detail
        assert q.get(row.row_key)["attempts"] == 1


def test_processing_job_is_recovered_after_a_crash_and_not_duplicated():
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [[BLOG, "", "", ""]])
        n = []
        import linkdigest.pipeline as p
        p.sync(src, q)
        q.claim()                                                # worker died while processing
        q2 = JobQueue(cfg.db_path)
        run(cfg, q2, src, llm_post(n))
        assert src.rows()[0].status == "done" and len(n) == 1 and len(emails(cfg)) == 1


def test_junk_rows_and_scheme_less_links():
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [["hello world", "", "", ""], ["blog.test/post", "", "", ""]])
        n = []
        run(cfg, q, src, llm_post(n))
        rows = src.rows()
        assert (rows[0].status, rows[0].detail) == ("failed", "Not a valid link.")
        assert rows[1].status == "done" and len(n) == 1
        assert q.get(rows[0].row_key) is None                    # junk never enters the queue


def test_same_link_twice_is_processed_once_and_both_rows_updated():
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [[BLOG, "", "", ""], [BLOG + "?utm_source=x", "", "", ""]])
        n = []
        run(cfg, q, src, llm_post(n))
        assert [r.status for r in src.rows()] == ["done", "done"] and len(n) == 1


def test_clearing_the_status_retries_the_link_once():
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [[BLOG, "", "", ""]])
        n = []
        run(cfg, q, src, llm_post(n))
        assert len(n) == 1
        write_csv(Path(cfg.source_csv), [[BLOG, "try again", "", ""]])        # user clears the status
        run(cfg, q, src, llm_post(n))
        assert len(n) == 2 and src.rows()[0].status == "done"
        run(cfg, q, src, llm_post(n))
        assert len(n) == 2                                        # and then it stays done


def test_locked_csv_never_fails_the_job_and_status_is_flushed_later():
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [[BLOG, "", "", ""]])
        real = source_csv.os.replace

        def locked(a, b):
            raise PermissionError("locked")
        with _run.patched(source_csv.os, "replace", locked), _run.patched(source_csv, "_sleep", lambda s: None):
            run(cfg, q, src)
        row = q.get(src.rows()[0].row_key)
        assert row["status"] == "done" and row["csv_synced"] == 0
        assert src.rows()[0].status in ("", "queued")             # CSV is behind, DB is right
        n = []
        run(cfg, q, src, llm_post(n))                             # file unlocked: flushed, not reprocessed
        assert src.rows()[0].status == "done" and n == [] and len(emails(cfg)) == 1


def test_a_broken_csv_never_crashes_the_cycle():
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [])
        Path(cfg.source_csv).write_text("not a header\nhttps://a.test\n", encoding="utf-8")
        run(cfg, q, src)                                          # must log and return


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 3: Run to verify failure**

Run: `python tests/test_offline.py`
Expected: `AttributeError: module 'linkdigest.pipeline' has no attribute 'run_cycle'`.

- [ ] **Step 4: Append the worker to `linkdigest/pipeline.py`**

Add these imports at the top of the file (merge with the existing ones):

```python
import time

from .errors import Blocked, ProcessingError, Skipped
from .jobqueue import JobQueue
from .mailer import deliver
from .render import Digest, render_digest, render_notice
from .source_csv import CsvSource
```

Append:

```python
TERMINAL = ("done", "failed", "skipped")


def sync(src, q):
    """Reconcile the CSV into the queue. The DB owns status, the CSV owns url and notes."""
    for row in src.rows():
        job = q.get(row.row_key)
        if job is None:
            if not normalize_url(row.url):
                if not row.status:
                    src.mark(row.row_key, "failed", "Not a valid link.")
            elif row.status in ("", "queued"):
                q.enqueue(row.row_key, normalize_url(row.url), row.notes)
                src.mark(row.row_key, "queued", "")
                log.info("queued %s", row.url)
            # any other status with no job: a row finished before this service existed, leave it alone
        elif not row.status:
            if job["status"] in TERMINAL and job["csv_synced"]:
                log.info("status cleared for %s, retrying", row.url)
                q.reset_for_retry(row.row_key, row.notes)
                src.mark(row.row_key, "queued", "")
            elif job["status"] in ("queued", "processing"):
                src.mark(row.row_key, "queued", "")


def flush(src, q):
    """Write statuses that are in the DB but not yet in the CSV (crash or locked file)."""
    for j in q.unsynced():
        if src.mark(j["row_key"], j["status"], j["error"] or ""):
            q.set_csv_synced(j["id"])


def _mark_quietly(src, key, status, detail):
    try:
        src.mark(key, status, detail[:300])
    except Exception:
        log.exception("could not write status to the CSV")


def _finish(q, src, job, status, detail):
    detail = detail[:300]
    q.finish(job.id, status, detail)                         # DB first, then CSV
    try:
        if src.mark(job.row_key, status, detail):
            q.set_csv_synced(job.id)
    except Exception:
        log.exception("could not write status for %s to the CSV", job.url)


def _notice(cfg, job, word, reason):
    if not cfg.notify_on_failure:
        return
    try:
        subject, html, text = render_notice(word, job.url, reason)
        deliver(cfg, job.id, subject, html, text)
    except Exception:
        log.exception("could not send the %s notice", word.lower())


def _fail(cfg, q, src, job, reason):
    log.warning("failed job %s: %s", job.id, reason)
    _finish(q, src, job, "failed", reason)
    _notice(cfg, job, "Failed", reason)


def handle(cfg, q, src, job):
    log.info("processing job %s: %s", job.id, job.url)
    try:
        subject, html, text = process_job(cfg, job.url, job.notes)
        deliver(cfg, job.id, subject, html, text)
    except Skipped as e:
        log.info("skipped job %s: %s", job.id, e)
        _finish(q, src, job, "skipped", str(e))
        _notice(cfg, job, "Skipped", str(e))
    except Blocked as e:
        if job.attempts < 2:                                   # Instagram: retry once, from the back
            log.warning("job %s blocked, will retry once after the other jobs: %s", job.id, e)
            q.requeue(job.id, str(e))
            _mark_quietly(src, job.row_key, "queued", "Blocked, retrying once: " + str(e))
        else:
            _fail(cfg, q, src, job, str(e))
    except ProcessingError as e:
        _fail(cfg, q, src, job, str(e))
    except Exception as e:                                     # transient: 429, 5xx, timeouts, bad JSON
        reason = str(e) or type(e).__name__
        log.exception("job %s hit a transient error", job.id)
        if job.attempts >= cfg.max_attempts:
            _fail(cfg, q, src, job, f"Gave up after {job.attempts} attempts: {reason}")
        else:
            q.requeue(job.id, reason)
            _mark_quietly(src, job.row_key, "queued", f"Retrying ({job.attempts} of {cfg.max_attempts}): {reason}")
    else:
        log.info("done job %s", job.id)
        _finish(q, src, job, "done", "")


def run_cycle(cfg, q, src):
    """One poll: sync the CSV, drain the queue, flush statuses. Never raises."""
    try:
        sync(src, q)
        while True:
            job = q.claim()
            if job is None:
                break
            handle(cfg, q, src, job)
        flush(src, q)
    except Exception:
        log.exception("cycle failed; will try again next poll")


def run_once(cfg):
    run_cycle(cfg, JobQueue(cfg.db_path), CsvSource(cfg.source_csv))


def run_forever(cfg):
    src, q = CsvSource(cfg.source_csv), JobQueue(cfg.db_path)
    log.info("watching %s every %ss (dry run: %s)", cfg.source_csv, cfg.poll_seconds, cfg.dry_run)
    while True:
        run_cycle(cfg, q, src)
        time.sleep(cfg.poll_seconds)
```

- [ ] **Step 5: Add `once` and `run` to `linkdigest/__main__.py`**

Add `from .pipeline import process_job, run_forever, run_once` (replacing the existing `process_job` import). In `build_parser()` add:

```python
    sub.add_parser("run", parents=[common], help="poll the CSV forever")
    sub.add_parser("once", parents=[common], help="poll once, drain the queue, exit")
```

In `main()` add before `return 2`:

```python
    if args.cmd == "once":
        run_once(cfg)
        return 0
    if args.cmd == "run":
        try:
            run_forever(cfg)
        except KeyboardInterrupt:
            print("stopped")
        return 0
```

- [ ] **Step 6: Run the spec test, then everything**

Run: `python tests/test_offline.py` then `python tests/run_all.py`
Expected: `PASS`. Likely first-run failures and where to look: a wrong email count means check `_notice` and `deliver` filenames (`<job id>-<slug>`); IG probes counted three times means `Blocked` retry condition (`job.attempts < 2`); `test_a` second cycle writing files means `sync` re-enqueued something, check `csv_synced` handling.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: worker loop with CSV sync, retries, crash recovery; spec Test A passes"
```

---

### Gate 4: the whole service works offline and on real links

Stop and report. Do not start Phase 5 until the user says OK.

**Needs from the user:** the URLs from earlier gates. No new keys.

- [ ] **Step 1: Regression and Test A.** `python tests/test_offline.py` prints `PASS`, then `python tests/run_all.py` prints `PASS`.

- [ ] **Step 2: Build a real CSV.** Create `links.csv` (it is git-ignored) with these rows, Instagram first on purpose:

```
url,notes,status,detail
<TEST_INSTAGRAM_URL first reel>,what is shown,,
<TEST_YOUTUBE_URL>,only the commands,,
<TEST_BLOG_URL>,focus on the main argument,,
<TEST_LONG_VIDEO_URL>,,,
<TEST_YOUTUBE_NOCAPS_URL>,,,
not a link,,,
```

- [ ] **Step 3: One real cycle.**

```bash
python -m linkdigest once --dry-run
```

Expected in the log: each job `processing`, the Instagram job either `done` or `blocked, will retry once after the other jobs` and retried last (never before the YouTube and blog jobs), step timings for every video, no traceback except for deliberate transient cases. Expected in `links.csv`: YouTube and blog `done`, long video `skipped` with the m:ss message, Instagram `done` or `failed` with the blocked message, junk row `failed` with `Not a valid link.`. In `out/`: one digest per done link, one notice for skipped, failed and junk-free. Open two digests.

- [ ] **Step 4: Idempotence.** Run `python -m linkdigest once --dry-run` again. Expected: no new files, no reprocessing, no LLM call in the log.

- [ ] **Step 5: Crash recovery on a real job.** Add a fresh row with the no-captions video, run `once --dry-run`, kill the process while it says `loading whisper model` or during `step transcript` (PowerShell: `Stop-Process -Id <pid> -Force`; Linux: `kill -9`). Run `once --dry-run` again. Expected: the job is picked up again once (`processing job` appears, row ends `done`), exactly one digest for it.

- [ ] **Step 6: Edit while running.** Start `python -m linkdigest run --dry-run` with `POLL_SECONDS=20`. Append a new row to `links.csv` in the user's usual editor and save. Expected: it is picked up within one poll and the user's edit is not lost when the service writes status. On Windows with the file still open in Excel, expect the log line `links.csv is locked by another program`, no failed job, and the status appearing after Excel closes. Report exactly what happened. Stop the service with Ctrl+C.

- [ ] **Step 7: Review.** Dispatch a fresh reviewer on the Phase 4 diff. Brief: "Check sync() against every row/DB disagreement in research.md (queue section), write order DB then CSV, any path where one bad job or bad CSV can stop the loop, retry counting for Blocked versus transient errors, SQLite usage (RETURNING, WAL, connection lifetime), CSV encoding round trips. Report only real defects." Apply real findings with a test each, rerun everything.

- [ ] **Step 8: Tag and report.**

```bash
git add -A
git commit -m "test: phase 4 review fixes"
git tag gate-4
```

Report: Test A output, the real-cycle table (row, final status, detail, seconds), what the crash and edit-while-running tests showed, review result. Ask for the OK to start Phase 5.
