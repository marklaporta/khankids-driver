#!/usr/bin/env python3
"""One-off 10/10: move every undone lesson dated Oct 12-16 (the old holding pool) to Dec 1, then write a scan with the new dates."""
import sys, os, json, time, datetime; sys.argv=[sys.argv[0],"none"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kk, fill, nightly
ST='type == "XCUIElementTypeStaticText" AND '
rows = nightly.read_app(); json.dump(rows, open("state/scan-2026-10-10-pre.json","w"), indent=1)
todo = [r for r in rows if r["date"] and "2026-10-12" <= r["date"] <= "2026-10-16" and not r["done"]]
print("to move:", len(todo), flush=True)
fill.open_report("Assignments"); ok = 0
for r in todo:
    kk.scroll_top(); res = kk.redate(r["title"], r["level"], 12, 1)
    if res != "redated":
        x = kk.q(ST + kk.lbl("Cancel"))
        if x: kk.click(x); time.sleep(0.3)
        c = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
        if kk.q(kk.DIALOG) and c: kk.click(c); time.sleep(0.5)
        kk.scroll_top(); res = kk.redate(r["title"], r["level"], 12, 1)
    if res == "redated": r["date"] = "2026-12-01"; ok += 1
    print("pool", res, r["title"], r["level"], flush=True)
json.dump(rows, open("state/scan-2026-10-10.json","w"), indent=1)
print(f"moved {ok}/{len(todo)}", flush=True)
