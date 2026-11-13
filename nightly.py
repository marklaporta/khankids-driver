#!/usr/bin/env python3
"""Nightly pass (parent, 2026-09-11):
  1. read the Assignments report (completion + scores);
  2. carry forward critical-path misses (letters/skills), leave optional misses to the 1-day archive;
  3. schedule spaced reviews from new scores;
  4. fill tomorrow (+ one buffer day) to 3 slots (2 on weekends) from the local curriculum queues;
  5. apply (move/create) and log; run finish.py yourself when done with the iPad.
Usage:  python3 nightly.py             # THE PROCESS: read, decide, apply to the app (then verify + finish.py)
        python3 nightly.py --preview   # read + decide only; changes NOTHING in the app
        python3 nightly.py --today     # include today regardless of the 8pm cutoff (use whenever the parent explicitly asks)
        python3 nightly.py --tomorrow  # the child is done for today: horizon = next three days regardless of the clock
The app only ever holds ~7 days; the long-term sequence lives in curriculum.py and state/*.json."""
import sys, os, json, time, datetime
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
APPLY = "--preview" not in sys.argv; FORCE_TODAY = "--today" in sys.argv; FORCE_TOMORROW = "--tomorrow" in sys.argv
ROWS_FILE = sys.argv[sys.argv.index("--rows") + 1] if "--rows" in sys.argv else None   # reuse a saved scan instead of re-reading the app
def _opt(flag, default):   # --days N / --weekend N / --weekday N: one-off overrides when the parent asks for a different load
    return int(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default
OPT_DAYS, OPT_WEEKEND, OPT_WEEKDAY = _opt("--days", None), _opt("--weekend", None), _opt("--weekday", None)
sys.argv = [sys.argv[0], "none"]
import kk, fill, curriculum as C
ST = 'type == "XCUIElementTypeStaticText" AND '
TODAY = datetime.date.today()
os.makedirs(f"{D}/state", exist_ok=True)
def load(n, default):
    p = f"{D}/state/{n}.json"; return json.load(open(p)) if os.path.exists(p) else default
def save(n, v): json.dump(v, open(f"{D}/state/{n}.json", "w"), indent=1)
state = load("state", {"letter_idx": 0, "skill_idx": 0, "book_idx": 0, "reviews": [], "scored": {}, "letters_assigned": {}})

# ---------- 1. read the app ----------
def parse(dt):
    if dt == "Today": return TODAY
    if dt == "Yesterday": return TODAY - datetime.timedelta(days=1)
    if dt == "Tomorrow": return TODAY + datetime.timedelta(days=1)
    p = dt.replace(".", "").split()
    try: return datetime.date(TODAY.year, {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}[p[1]], int(p[2]))
    except Exception: return None
def read_app():
    fill.open_report("Assignments")
    kk.scroll_top(); seen = {}; last = None; stale = 0
    for _ in range(80):
        t = kk.tree(); rs = kk.rows(t)
        for title, level, dt, y in rs:
            score = next((e[1] for e in t if e[0] == "StaticText" and e[2] > 280 and abs(e[3] - y - 20) < 26 and e[1].strip()), "")
            check = any(e[0] == "Image" and "check" in e[1] and abs(e[3] - y - 15) < 30 for e in t)
            seen[(title, level, dt)] = (score, check)
        sig = tuple(r[0] for r in rs)
        if sig and sig == last:
            stale += 1
            if stale >= 2: break
        else: stale = 0
        if sig: last = sig
        kk.page_down(); time.sleep(0.3)
    out = []
    for (title, level, dt), (score, check) in seen.items():
        d = parse(dt); sc = int(score.rstrip("%")) if score.endswith("%") else None
        out.append({"title": title, "level": level, "date": d.isoformat() if d else None, "score": sc, "done": check or bool(score)})
    return out

# ---------- 2-4. decide ----------
def plan(rows):
    byday = {}
    for r in rows:
        if r["date"]: byday.setdefault(r["date"], []).append(r)
    start = 1 if FORCE_TOMORROW else (0 if (FORCE_TODAY or datetime.datetime.now().hour < 20) else 1)   # --today / --tomorrow: the parent asked, cutoff does not apply
    horizon = [TODAY + datetime.timedelta(days=i) for i in range(start, start + (OPT_DAYS or C.HORIZON_DAYS))]
    cap = {d: ((OPT_WEEKEND or C.WEEKEND_SLOTS) if d.weekday() >= 5 else (OPT_WEEKDAY or C.WEEKDAY_SLOTS)) for d in horizon}
    def full_day(d): return d.weekday() < 5 or cap[d] > 3     # a weekend day with a bigger load gets its letter + skill too
    # new scores -> reviews
    for r in rows:
        key = f"{r['title']}|{r['level']}"
        if r["done"] and r["score"] is not None and state["scored"].get(key) != r["score"]:
            state["scored"][key] = r["score"]
            for lv, off in C.review_schedule(r["score"], r["level"]):
                state["reviews"].append({"title": r["title"], "level": lv, "due": (TODAY + datetime.timedelta(days=off)).isoformat()})
    # letters assigned in the app -> their follow-ups
    for r in rows:
        if r["title"].startswith("Letter ") and r["done"] and r["date"] and r["title"] not in state["letters_assigned"]:   # follow-ups only once the child has DONE the letter
            state["letters_assigned"][r["title"]] = r["date"]
            c = r["title"].split()[-1]; d0 = datetime.date.fromisoformat(r["date"])
            state["reviews"].append({"title": f"Uppercase {c}", "level": "Main", "due": (d0 + datetime.timedelta(days=5)).isoformat()})
            if c.lower() in "bcdfghjklmnpqrstvwyz":
                state["reviews"].append({"title": f"Beginning Sound {c.lower()}", "level": "Main", "due": (d0 + datetime.timedelta(days=7)).isoformat()})
    lq = state.setdefault("lower_queued", [])
    for i, t in enumerate(sorted(state["letters_assigned"], key=lambda t: state["letters_assigned"][t])):
        c = t.split()[-1].lower()
        if c not in lq:
            lq.append(c); state["reviews"].append({"title": f"Lowercase {c}", "level": "Main", "due": (TODAY + datetime.timedelta(days=1 + i // 2)).isoformat()})
    POOL = datetime.date(TODAY.year, 12, 1)   # holding pool: parked lessons live on/after Dec 1 (moved from Oct 12-16 on 10/10)
    pooled = {(r["title"], r["level"]) for r in rows if r["date"] and datetime.date.fromisoformat(r["date"]) >= POOL}
    existing = {(r["title"], r["level"]) for r in rows} - pooled          # pooled items are available, not "assigned"
    moves, creates = [], []
    def add(item, d):
        """Put item on day d: move it out of the pool if it lives there, else create it."""
        byday.setdefault(d.isoformat(), []).append(item); existing.add((item["title"], item["level"]))
        (moves if (item["title"], item["level"]) in pooled else creates).append((item["title"], item["level"], d.month, d.day))
    # carry forward critical-path misses (dated <= today, not done)
    carry = [r for r in rows if r["date"] and datetime.date.fromisoformat(r["date"]) < TODAY and not r["done"] and r["title"] not in C.OPTIONAL]   # never touch today
    def free(d): return cap[d] - len(byday.get(d.isoformat(), []))
    def place(item, kind):
        for d in horizon:
            if free(d) > (-3 if kind == "move" else 0):      # carried misses may overfill a day by up to 3: nearest day wins
                if kind == "move":
                    byday.setdefault(d.isoformat(), []).append(item); moves.append((item["title"], item["level"], d.month, d.day))
                else: add(item, d)
                return True
        return False
    for r in carry: place(r, "move")
    # the letter spine comes first on weekdays (parent 9/16: some of each every day); reviews fill around it
    for d in horizon:
        if full_day(d) and free(d) > 0 and not any(x["title"].startswith("Letter ") for x in byday.get(d.isoformat(), [])):
            while state["letter_idx"] < len(C.LETTERS) and (f"Letter {C.LETTERS[state['letter_idx']].upper()}", "Main") in existing: state["letter_idx"] += 1
            if state["letter_idx"] < len(C.LETTERS):
                t = f"Letter {C.LETTERS[state['letter_idx']].upper()}"; state["letter_idx"] += 1
                add({"title": t, "level": "Main"}, d)
    # due reviews. Balance rules for a 10-lesson day: reviews leave 4 slots (skill + books + headroom), at most 3 letter-type
    # reviews per day, and only one level of any title inside the horizon (Practice 2 never lands days after Practice 1).
    def letter_type(t):
        w = t.split(); return len(w[-1]) == 1 and (w[0] in ("Uppercase", "Lowercase") or t.startswith("Beginning Sound "))
    hz = {h.isoformat() for h in horizon}
    in_h = {x["title"] for d in hz for x in byday.get(d, [])}
    in_h |= {r["title"] for r in rows if r["date"] and TODAY.isoformat() <= r["date"] < POOL.isoformat() and not r["title"].startswith("Letter ")}   # today's list counts too: no Practice 2 days after an unscored Practice 1
    nlet = {d: sum(1 for x in byday.get(d, []) if letter_type(x["title"])) for d in hz}
    def room(x, t):
        reserve = 4 if cap[x] >= 8 else 2 if cap[x] > 3 else 1
        return len(byday.get(x.isoformat(), [])) < cap[x] - reserve and not (letter_type(t) and nlet[x.isoformat()] >= 3)
    keep = []
    for rv in sorted(state["reviews"], key=lambda x: x["due"]):
        due = datetime.date.fromisoformat(rv["due"]); key = (rv["title"], rv["level"])
        if key in existing: continue                                   # already assigned at that level: drop from the queue
        if due > horizon[-1] or rv["title"] in in_h: keep.append(rv); continue
        nd = next((h for h in horizon if h >= due and room(h, rv["title"])), None)
        if nd is None: keep.append(rv); continue
        add({"title": rv["title"], "level": rv["level"]}, nd); in_h.add(rv["title"])
        if letter_type(rv["title"]): nlet[nd.isoformat()] += 1
    state["reviews"] = keep
    # letters, skills, books
    for d in horizon:
        if full_day(d) and free(d) > 0:
            while state["skill_idx"] < len(C.SKILLS) and tuple(C.SKILLS[state["skill_idx"]]) in existing: state["skill_idx"] += 1
            if state["skill_idx"] < len(C.SKILLS):
                t, lv = C.SKILLS[state["skill_idx"]]; state["skill_idx"] += 1
                add({"title": t, "level": lv}, d)
        def next_book():
            while state["book_idx"] < len(C.BOOKS):
                t = C.BOOKS[state["book_idx"]]; state["book_idx"] += 1
                if (t, "Main") not in existing: add({"title": t, "level": "Main"}, d); return True
            return False
        nb = 0
        while free(d) > 0 and nb < 2 and next_book(): nb += 1        # two books a day
        for t, lv in C.ENRICH:                                       # still short: practice on already-mastered skills (never extra NEW skills)
            if free(d) <= 0: break
            if (t, lv) in existing or t in in_h: continue
            add({"title": t, "level": lv}, d); in_h.add(t)
        while free(d) > 0 and next_book(): pass                       # last resort: more books
    return byday, moves, creates

def subject(title):
    return "Math" if title in {t for t, _ in C.SKILLS if t not in ("Beginning Sounds 1","Blend Sounds 2","Word Families","Beginning Sounds 2","Words: End Sound")} or title.startswith(("Count","Tap &","Groups","Number","Add ","Subtract","Compare","Measurement","Primary","Secondary","Other Colors","Patterns","Positions","Circle","Square","Triangle","Rectangle","Grouping","Last in Line")) else "ELA"

if __name__ == "__main__":
    rows = json.load(open(ROWS_FILE)) if ROWS_FILE else read_app(); save(f"scan-{TODAY}", rows)
    byday, moves, creates = plan(rows)
    print(f"\n== horizon (as of {TODAY}) ==")
    for i in range(0, 1 + (OPT_DAYS or C.HORIZON_DAYS)):
        d = TODAY + datetime.timedelta(days=i)
        print(f"  {d.strftime('%a %m/%d')}: " + "; ".join(f"{x['title']}" + (f" ({x['level']})" if x['level'] != 'Main' else "") for x in byday.get(d.isoformat(), [])))
    print(f"\nmoves (carry-forward): {moves}\ncreates: {len(creates)}")
    if not APPLY: print("\n(preview only; nothing changed in the app)"); sys.exit(0)
    save("state", state)
    log = open(f"{D}/state/nightly-{TODAY}.log", "a")
    fill.open_report("Assignments")
    for t, lv, m, d in moves:
        res = kk.redate(t, lv, m, d); log.write(f"move\t{res}\t{t}\t{lv}\t{m}/{d}\n"); print("move", res, t, lv, f"{m}/{d}")
    if creates:
        with open(f"{D}/plans/nightly-{TODAY}.tsv", "w") as f:
            for t, lv, m, d in creates: f.write(f"{subject(t)}\t{t}\t{lv}\t{m}\t{d}\n")
        fill.open_report("All Progress")
        fill.main(f"{D}/plans/nightly-{TODAY}.tsv", f"{D}/state/nightly-create-{TODAY}.log")
    print("applied; run finish.py when done with the iPad")
