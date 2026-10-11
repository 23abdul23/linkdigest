import importlib
import sys

import _run

ok = True
for path in sorted(_run.TESTS.glob("test_*.py")):
    print(f"== {path.stem}")
    mod = importlib.import_module(path.stem)
    ok = _run.run(vars(mod)) and ok
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
