"""Tiny assert-based test runner. No pytest."""
import contextlib
import pathlib
import sys
import traceback

TESTS = pathlib.Path(__file__).resolve().parent
ROOT = TESTS.parent
for p in (str(ROOT), str(TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)


def run(namespace):
    ok = True
    for name, fn in list(namespace.items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:
                ok = False
                print(f"FAIL {name}")
                traceback.print_exc()
            else:
                print(f"ok   {name}")
    return ok


def main(namespace):
    ok = run(namespace)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)
