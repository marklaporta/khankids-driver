#!/bin/bash
# The process, detached (the harness kills foreground commands at 10 min). Usage: nohup ./run_process.sh [nightly flags] > state/process.out 2>&1 &
cd "$(dirname "$0")"
python3 -u pool_out.py && python3 -u nightly.py --rows state/scan-2026-10-10.json "$@" && python3 -u - <<'PY'
import sys, os, json; sys.argv=[sys.argv[0],"none"]; sys.path.insert(0, os.getcwd())
import nightly, datetime
rows = nightly.read_app(); json.dump(rows, open(f"state/scan-{nightly.TODAY}-verify.json","w"), indent=1)
for i in range(0, 7):
    d = (nightly.TODAY + datetime.timedelta(days=i)).isoformat(); xs = [r for r in rows if r["date"] == d]
    print("VERIFY", d, len(xs), [r["title"] + ("" if r["level"] == "Main" else " (" + r["level"].replace("Practice ", "P") + ")") for r in xs], "done:", sum(r["done"] for r in xs))
print("VERIFY pool(Dec):", sum(1 for r in rows if r["date"] and r["date"] >= "2026-12-01"), "| stray Oct 12-16 undone:", [(r["title"], r["date"]) for r in rows if r["date"] and "2026-10-17" <= r["date"] < "2026-12-01"])
PY
python3 finish.py
echo PROCESS-DONE
