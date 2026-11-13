#!/usr/bin/env python3
"""Read Class Reports > All Progress for every subject: the app's full lesson catalog in its own order, with the child's score per lesson.
Writes state/catalog-YYYY-MM-DD.json: [{subject, category, title, score, status}]. Read-only (scrolls, never assigns)."""
import sys, os, json, time, datetime; SUBJECTS = sys.argv[1:] or ["ELA", "Math", "Logic+"]; sys.argv=[sys.argv[0],"none"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kk, fill
out = []; failed = []
fill.open_report("All Progress")
for subj in SUBJECTS:
    try: kk.set_subject(subj)
    except Exception as ex: print("subject", subj, "failed", ex, flush=True); failed.append(subj); continue
    time.sleep(1.0); kk.scroll_top(); time.sleep(0.6)
    seen = []; catof = {}; cat = None; last = None; stale = 0
    for _ in range(150):
        t = kk.tree(); st = sorted([e for e in t if e[0] == "StaticText" and kk.G["list_top"] <= e[3] < kk.G["list_bot"]], key=lambda e: e[3])
        CX, TX, SX = kk.G["cat_x"], kk.G["title_x"], kk.G["score_x"]
        # the category at the TOP of this screen = the category of the first row already seen (screens overlap);
        # carrying the last header from the previous screen mis-files rows that sit above it
        for e in st:
            if e[2] == CX: break
            if e[2] == TX and e[1] in catof: cat = catof[e[1]]; break
        for e in st:
            if e[2] == CX: cat = e[1].replace("\n", " ")
            elif e[2] == TX and e[1].strip():
                sc = next((x[1] for x in st if x[2] == SX and abs(x[3] - e[3]) < 6), "")
                if e[1] not in catof:
                    catof[e[1]] = cat; seen.append({"subject": subj, "category": cat, "title": e[1], "score": sc})
        sig = tuple((e[2], e[1]) for e in st)
        if sig == last:
            stale += 1
            if stale >= 2: break
        else: stale = 0
        last = sig; kk.page_down(); time.sleep(0.3)
    print(subj, len(seen), "lessons", flush=True); out += seen
for x in out:
    s = x["score"]; x["pct"] = int(s.rstrip("%")) if s.endswith("%") else None
    x["status"] = "mastered" if (x["pct"] or 0) >= 90 else "needs_work" if x["pct"] is not None else "viewed" if s == "Viewed" else "new" if not s else s
json.dump(out, open(f"state/catalog-{datetime.date.today()}-{'-'.join(SUBJECTS)}.json", "w"), indent=1)
print("CATALOG-DONE", len(out), "FAILED:" if failed else "", *failed, flush=True)
if failed: sys.exit(2)
