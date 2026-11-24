#!/usr/bin/env python3
"""Read Class Reports > All Progress for every subject: the app's full lesson catalog in its own order, with the child's score per lesson.
Writes state/catalog-YYYY-MM-DD.json: [{subject, category, title, score, status}]. Read-only (scrolls, never assigns).

Each item also records "pos", its place in the list in points (row y minus the header row's y), which `kk.find_lesson` uses to
steer straight to a lesson.

Speed (11/23): each report list is virtualized, but the tree holds a window of rows wider than the screen (iPhone: ~20 rows, of which
~13 are visible). A step is the longest momentum-free stroke (`G["stroke"]`) and is verified: the new read must reach back to rows
already seen (by the header row's offset), else it backs up half a step. A report stops at the first category the plan never uses (books when `books_per_day` is 0, Logic+
play content when `include_play` is false) once everything after it is unused too; those rows are carried over from the last read.
KK_CATALOG_ALL=1 reads every row."""
import sys, os, json, time, datetime; SUBJECTS = sys.argv[1:] or ["ELA", "Math", "Logic+"]; sys.argv=[sys.argv[0],"none"]; D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import kk, fill, planner
st_ = json.load(open(f"{D}/state/state.json")) if os.path.exists(f"{D}/state/state.json") else {}
planner.configure(st_.get("settings", {}))
prev = json.load(open(f"{D}/state/catalog-latest.json"))["items"] if os.path.exists(f"{D}/state/catalog-latest.json") else []
READ_ALL = os.environ.get("KK_CATALOG_ALL") == "1"

def unused(subj, cat):
    """A category the plan never assigns from under the family's settings."""
    base = kk.split_key(subj)[0]
    if base == "ELA": return planner.BOOKS_PER_DAY == 0 and cat in planner.BOOK_CATS_READERS + planner.BOOK_CATS_NONFIC + ("Stories with Lessons", "Stories with People")
    if base == "Logic+": return not planner.INCLUDE_PLAY and cat not in planner.LOGIC_OK_CATEGORIES
    return False

def cut_after(subj):
    """(categories in the last read's order, index of the last one the plan can use); None = read everything."""
    order = []
    for c in prev:
        if c["subject"] == subj and c["category"] not in order: order.append(c["category"])
    need = [i for i, c in enumerate(order) if not unused(subj, c)]
    if READ_ALL or not order or not need or need[-1] == len(order) - 1: return None
    return order, need[-1]

CX, TX, SX = kk.G["cat_x"], kk.G["title_x"], kk.G["score_x"]
TOP, BOT = kk.G.get("cat_top", kk.G["list_top"]), kk.G["list_bot"]
P0, P1 = kk.G["stroke"]
def rows():
    t = kk.tree()
    return sorted([e for e in t if e[0] == "StaticText" and TOP <= e[3] < BOT and e[2] in (CX, TX, SX)], key=lambda e: e[3]), t
def header_y(t): h = kk.header_row(t); return h[3] if h else None
def at_top(t): h = header_y(t); return h is not None and h > -20

out = []; failed = []
fill.open_report("All Progress")
for subj in SUBJECTS:
    t0 = time.time()
    try: kk.set_subject(subj)
    except Exception as ex: print("subject", subj, "failed", ex, flush=True); failed.append(subj); continue
    st, t = rows()
    if not at_top(t): kk.scroll_top(); st, t = rows()
    cut = cut_after(subj); stop = False
    prev_last = next((c["title"] for c in reversed(prev) if c["subject"] == subj), None)
    seen = []; catof = {}; cat = None; last = None; stale = 0; steps = 0; backs = 0; reach = None   # reach: list position read down to
    for _ in range(200):
        # the category at the TOP of this read = the category of the first row already seen (reads overlap);
        # carrying the last header from the previous read mis-files rows that sit above it
        hy = header_y(t); titles = [e for e in st if e[2] == TX]
        if steps and titles and (all(e[1] not in catof for e in titles) if hy is None else titles[0][3] - hy > reach + 4):
            # a gap between this read and the last one (rows may have been skipped): back up half a step and read again
            kk.scroll_by(-(P0 - P1) // 2); backs += 1
            st, t = rows(); continue
        if hy is not None and titles: reach = max(reach or -1e9, titles[-1][3] - hy)
        for e in st:
            if e[2] == CX: break
            if e[2] == TX and e[1] in catof: cat = catof[e[1]]; break
        new = 0
        for e in st:
            if e[2] == CX:
                cat = e[1].replace("\n", " ")
                if cut and cat in cut[0] and cut[0].index(cat) > cut[1]: stop = True; break
            elif e[2] == TX and e[1].strip():
                sc = next((x[1] for x in st if x[2] == SX and abs(x[3] - e[3]) < 6), "")
                if e[1] not in catof:
                    catof[e[1]] = cat; new += 1
                    seen.append({"subject": subj, "category": cat, "title": e[1], "score": sc, "pos": None if hy is None else e[3] - hy})
        if stop: break
        sig = tuple((e[2], e[1]) for e in st)
        if sig == last:
            stale += 1                                 # a drag that moved nothing: the end of the list. One bump is enough when the
            if stale >= 2 or (prev_last and prev_last in catof): break     # last read's final row has been seen; else try once more
        else: stale = 0
        last = sig
        kk.drag_settle(kk.G["drag_x"], P0, P1); steps += 1
        st, t = rows()
    tail = []
    if stop:
        got = {x["title"] for x in seen}
        tail = [dict(c) for c in prev if c["subject"] == subj and c["category"] in cut[0] and cut[0].index(c["category"]) > cut[1] and c["title"] not in got]
        for c in tail: c.pop("pct", None); c.pop("status", None)
    print(subj, len(seen), "lessons read" + (f" + {len(tail)} unused carried over" if tail else ""),
          f"({steps} steps, {backs} back-ups, {time.time() - t0:.0f} s)", flush=True)
    out += seen + tail
for x in out:
    s = x["score"]; x["pct"] = int(s.rstrip("%")) if s.endswith("%") else None
    x["status"] = "mastered" if (x["pct"] or 0) >= 90 else "needs_work" if x["pct"] is not None else "viewed" if s == "Viewed" else "new" if not s else s
json.dump(out, open(f"state/catalog-{datetime.date.today()}-{'-'.join(SUBJECTS)}.json", "w"), indent=1)
print("CATALOG-DONE", len(out), "FAILED:" if failed else "", *failed, flush=True)
if failed: sys.exit(2)
