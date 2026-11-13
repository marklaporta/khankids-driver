#!/usr/bin/env python3
"""THE PROCESS (populate-student skill). Global, idempotent; a rerun after any interruption just finishes the remaining diff.
 1. read their progress: All Progress catalog (full read weekly, or --full-catalog) + Assignments report (incremental since last run)
 2. planner.plan(): 5 lessons/day (gates first) over the horizon (needs-work retries + next new lessons, hole-filling, mastery-based grades)
 3. (no sticky step: the plan is authoritative and the app mirrors it exactly)
 4. ONE pass per report subject in list order through All Progress: creates new assignments, re-dates existing ones
    (pre-checked dialog), parks unwanted future ones to Dec 1. Assignments-tab re-date only as a fallback.
 5. finish: print the plan; verify with `process.py --preview` (moves/creates/parks all 0).
Usage: nohup python3 -u process.py [--preview] [--tomorrow] [--full-catalog] [--full-scan] > state/process.out 2>&1 &"""
import sys, os, json, time, datetime, subprocess
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
PREVIEW = "--preview" in sys.argv; TOMORROW = "--tomorrow" in sys.argv
FULL_CAT = "--full-catalog" in sys.argv; FULL_SCAN = "--full-scan" in sys.argv
CLEAR_DONE_TODAY = "--clear-done-today" in sys.argv
CLEAR_TODAY = "--clear-today" in sys.argv               # parent 10/14: nothing assigned today (the child does the Learning Path instead)     # parent 10/10: take today's finished (green-check) lessons out of their view
DAYS = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 7
TODAY_MAX = int(sys.argv[sys.argv.index("--today-max") + 1]) if "--today-max" in sys.argv else None   # parent can override the after-play cap
sys.argv = [sys.argv[0], "none"]
import kk, fill, planner, nightly
TODAY = datetime.date.today(); NOW = datetime.datetime.now()
PARK = (12, 1)
EXACT_DAYS = 2      # architect's call 10/13: mirror the plan exactly for the next 2 days; later lessons may sit on any later day
                    # (invisible to them until their date; each run re-aligns before the child can see them). Saves ~60 re-dates per skipped day.
ST = 'type == "XCUIElementTypeStaticText" AND '
SP = f"{D}/state/state.json"
state = json.load(open(SP))
def save_state(): json.dump(state, open(SP, "w"), indent=1)

# ---------- 1a. catalog: full read weekly, merged per report key ----------
CAT = f"{D}/state/catalog-latest.json"
def catalog():
    keys = state.get("scan_keys", ["ELA", "Math", "Logic+", "ELA4", "Math4", "Logic+4"])
    latest = json.load(open(CAT)) if os.path.exists(CAT) else {"keys": {}, "items": []}
    stale = [k for k in keys if FULL_CAT or k not in latest["keys"]
             or (TODAY - datetime.date.fromisoformat(latest["keys"][k])).days >= 7]
    if stale:
        r = subprocess.run([sys.executable, "-u", f"{D}/catalog.py", *stale])
        f = f"{D}/state/catalog-{TODAY}-{'-'.join(stale)}.json"
        got = json.load(open(f)) if os.path.exists(f) else []
        ok = {c["subject"] for c in got}
        if r.returncode != 0 or set(stale) - ok:
            print("WARNING: catalog read failed for", sorted(set(stale) - ok), "- using the last good read for those", flush=True)
        latest["items"] = [c for c in latest["items"] if c["subject"] not in ok] + got
        for k in ok: latest["keys"][k] = TODAY.isoformat()
        json.dump(latest, open(CAT, "w"), indent=1)
    missing = [k for k in keys if k not in latest["keys"]]
    if any(k in ("ELA", "Math") for k in missing): sys.exit(f"cannot plan: no catalog for {missing}")
    return latest

def overlay(latest):
    """Scores the child earned AFTER a subject's last full read (from their assignments) override the catalog score.
    Titles are canonicalized case-insensitively to the lowest grade's spelling ("The Cup is Up" at Age 4 IS "The Cup Is Up")."""
    att = state.get("attempts", {}); items = []
    canon = {}
    for c in sorted(latest["items"], key=lambda c: kk.split_key(c["subject"])[1]): canon.setdefault(c["title"].lower(), c["title"])
    for c in latest["items"]:
        c = dict(c); c["title"] = canon[c["title"].lower()]; since = latest["keys"].get(c["subject"], "9999")
        newer = [(v["date"], v["score"]) for k, v in att.items() if k.split("|")[0] == c["title"] and v["date"] >= since and v["score"] is not None]
        if newer and c["status"] not in ("viewed",):
            c["pct"] = max(newer)[1]; c["score"] = f"{c['pct']}%"
            c["status"] = "mastered" if c["pct"] >= planner.MASTERY else "needs_work"
        items.append(c)
    return items

def mark_done(cat, rows):
    """A lesson the child finished without a score (green check, unscored type) is 'viewed', even if the catalog read predates it."""
    done_unscored = {r["title"] for r in rows if r["done"] and r["score"] is None} | \
                    {k.split("|")[0] for k, v in state.get("attempts", {}).items() if v.get("viewed")}
    for c in cat:
        if c["status"] == "new" and c["title"] in done_unscored: c["status"] = "viewed"; c["score"] = "Viewed"
    return cat

# ---------- 1b. assignments: incremental (list is newest-date first) ----------
AC = f"{D}/state/assign-cache.json"
def read_assignments():
    cache = json.load(open(AC)) if os.path.exists(AC) and not FULL_SCAN else {}
    last = state.get("last_run")
    cutoff = (datetime.date.fromisoformat(last) - datetime.timedelta(days=1)) if (last and cache) else None
    safe_open("Assignments"); kk.scroll_top()
    seen = {}; prev = None; stale = 0
    for _ in range(90):
        t = kk.tree(); rs = kk.rows(t)
        for title, level, dt, y in rs:
            g = kk.G; so, sw = g["row_score_dy"]; co, cw = g["row_check_dy"]
            score = next((e[1] for e in t if e[0] == "StaticText" and e[2] > g["row_score_x"] and abs(e[3] - y - so) < sw and e[1].strip()), "")
            check = any(e[0] == "Image" and "check" in e[1] and abs(e[3] - y - co) < cw for e in t)
            seen[(title, level)] = (dt, score, check)
        ds = [nightly.parse(dt) for _, _, dt, _ in rs]
        if cutoff and ds and all(d and d < cutoff for d in ds): break        # everything older is unchanged since last run
        sig = tuple(r[0] for r in rs)
        if sig and sig == prev:
            stale += 1
            if stale >= 2: break
        else: stale = 0
        if sig: prev = sig
        kk.page_down(); time.sleep(0.3)
    for (title, level), (dt, score, check) in seen.items():
        d = nightly.parse(dt); sc = int(score.rstrip("%")) if score.endswith("%") else None
        cache[f"{title}|{level}"] = {"title": title, "level": level, "date": d.isoformat() if d else None, "score": sc, "done": check or bool(score)}
    json.dump(cache, open(AC, "w"), indent=1)
    rows = list(cache.values())
    att = state.setdefault("attempts", {})                                   # record WHEN each score appeared
    for r in rows:
        k = f"{r['title']}|{r['level']}"
        if r["done"] and r["score"] is None and not att.get(k):        # unscored + done = viewed; remember it ourselves, because
            att[k] = {"score": None, "date": min(r["date"] or TODAY.isoformat(), TODAY.isoformat()), "viewed": True}   # re-dating resets the check
        if r["done"] and r["score"] is not None and att.get(k, {}).get("score") != r["score"]:
            first = att.get(k, {}).get("first", att.get(k, {}).get("score", r["score"]))   # probes are judged on the FIRST attempt
            att[k] = {"score": r["score"], "date": min(r["date"] or TODAY.isoformat(), TODAY.isoformat()), "first": first}
    return rows

# ---------- helpers ----------
def ensure_session():
    """WDA can come back with our session gone: open a new one (and re-apply the no-idle-wait settings)."""
    try: kk._req(f"/session/{kk.SID}"); return
    except Exception: pass
    sid = kk._req("/session", {"capabilities": {"alwaysMatch": {}}})["sessionId"]
    kk.SID = sid; open(f"{kk.SESS}/sid", "w").write(sid)
    try: kk._req(f"/session/{sid}/appium/settings", {"settings": {"waitForIdleTimeout": 0, "animationCoolOffTimeout": 0,
                  "snapshotMaxDepth": 25, "useFirstMatch": True, "customSnapshotTimeout": 5}})
    except Exception: pass
    print("new WDA session", sid, flush=True)

def alive_or_restart():
    kk.wait_unlocked()
    if not fill.alive():
        print("WDA down -> restarting", flush=True)
        for _ in range(10):                             # it often comes back by itself within seconds
            time.sleep(3)
            if fill.alive(): break
        else:
            subprocess.run([kk.START], env={**os.environ, "SCRATCH": kk.SESS}, check=True, capture_output=True)
            kk.SID = open(f"{kk.SESS}/sid").read().strip()
    ensure_session()
    fill.SID = kk.SID if hasattr(fill, "SID") else None

def safe_open(tab):
    for attempt in range(3):
        try: alive_or_restart(); fill.open_report(tab); return
        except Exception as ex: print(f"open_report({tab}) failed: {ex!r}; retrying", flush=True); time.sleep(3)
    raise RuntimeError(f"could not open {tab}")

def fallback_redate(ops, log):
    """Assignments-tab re-date for anything the All Progress pass could not reach."""
    if not ops: return
    safe_open("Assignments")
    for t, lv, d in ops:
        try: kk.scroll_top(); res = kk.redate(t, lv, d.month, d.day)
        except Exception as ex: res = f"error {ex!r}"
        log.write(f"fallback\t{res}\t{t}\t{lv}\t{d}\n"); log.flush(); print("fallback", res, t, lv, d, flush=True)

def main():
    t0 = time.time()
    latest = catalog(); cat = overlay(latest)
    rows = read_assignments(); save_state(); cat = overlay(latest); cat = mark_done(cat, rows)
    print(f"read done in {(time.time()-t0)/60:.1f} min", flush=True)
    start = 1 if (TOMORROW or NOW.hour >= 20) else 0
    horizon = [TODAY + datetime.timedelta(days=i) for i in range(start, start + DAYS)]
    played_today = any(r["done"] and r["date"] == TODAY.isoformat() for r in rows) or \
                   any(v.get("date") == TODAY.isoformat() for v in state.get("attempts", {}).values())
    caps = {TODAY: TODAY_MAX} if (TODAY_MAX is not None and horizon[0] == TODAY) else {}   # no standing after-play cap (parent 10/11)
    # one-off day sizes the parent asked for (e.g. a bigger day for one date only): state "day_caps" {date: n}.
    # They survive reruns on that day and are dropped once the date has passed; --today-max still wins for today.
    state["day_caps"] = {d: n for d, n in state.get("day_caps", {}).items() if d >= TODAY.isoformat()}
    for d, n in state["day_caps"].items(): caps.setdefault(datetime.date.fromisoformat(d), n)
    if caps: print("day sizes set by the parent:", {str(d): n for d, n in caps.items()}, flush=True)
    days, les, _ = planner.plan(cat, rows, state, horizon, caps)       # the plan is authoritative; the app mirrors it
    if planner.plan.scan_keys != state.get("scan_keys"):
        print("grades to read from now on:", planner.plan.scan_keys, flush=True); state["scan_keys"] = planner.plan.scan_keys
    print("held for hole-filling:", planner.plan.held, flush=True)
    for n_ in planner.plan.notes: print("  *", n_, flush=True)

    want = {(x["title"], x["level"]): (d, x["subject"]) for d, xs in days.items() for x in xs}
    lowest = {}
    for c in cat:
        if c["title"] not in lowest or kk.split_key(c["subject"])[1] < kk.split_key(lowest[c["title"]])[1]: lowest[c["title"]] = c["subject"]
    park_date = datetime.date(TODAY.year, *PARK)
    def diff(rows):
        rowmap = {(r["title"], r["level"]): r for r in rows}
        ops = []                                        # (subject, title, level, date, kind)
        exact_until = horizon[min(EXACT_DAYS, len(horizon)) - 1].isoformat()  # the child only SEES today's list: today+tomorrow must be exact;
        later_ok = lambda dt: dt and exact_until < dt < park_date.isoformat()   # later days only need the lesson assigned somewhere later
        for k, (d, subj) in want.items():
            r = rowmap.get(k)
            if r and r["date"] == d.isoformat(): continue
            if r and not r["done"] and d.isoformat() > exact_until and later_ok(r["date"]): continue   # no churn between future days
            ops.append((lowest.get(k[0], subj) if r else subj, k[0], k[1], d, "move" if r else "create"))
        for k, r in rowmap.items():
            if not r["done"] and r["date"] and horizon[0].isoformat() <= r["date"] < park_date.isoformat() and k not in want:
                ops.append((lowest.get(k[0]), k[0], k[1], park_date, "park"))
            elif CLEAR_TODAY and not r["done"] and r["date"] == TODAY.isoformat() and k not in want:
                ops.append((lowest.get(k[0]), k[0], k[1], park_date, "park"))      # today emptied on request
            elif CLEAR_DONE_TODAY and r["done"] and r["date"] == TODAY.isoformat() and k not in want:
                ops.append((lowest.get(k[0]), k[0], k[1], park_date, "park"))      # finished today: out of their view
        return ops
    ops = diff(rows)
    print(f"\n== plan {horizon[0]} .. {horizon[-1]} ==")
    for d, xs in days.items():
        print(f"  {d.strftime('%a %m/%d')}: " + "; ".join(x["title"] + ("" if x["level"] == "Main" else f" ({x['level']})")
              + ("" if x["subject"] in ("ELA", "Math", "Logic+") else f" [{x['subject']}]") for x in xs), flush=True)
    n = {k: sum(1 for o in ops if o[4] == k) for k in ("move", "create", "park")}
    print(f"\nmoves {n['move']}  creates {n['create']}  parks {n['park']}", flush=True)
    json.dump({d.isoformat(): xs for d, xs in days.items()}, open(f"{D}/state/plan-{TODAY}.json", "w"), indent=1)
    if PREVIEW: save_state(); print("(preview only; nothing changed in the app)"); return

    log = open(f"{D}/state/process-{TODAY}.log", "a")
    order = list(kk.REPORTS)
    pos = {(c["subject"], c["title"]): i for i, c in enumerate(cat)}
    for rnd in range(3):
        if not ops: break
        if rnd: print(f"\nrepair round {rnd}: {len(ops)} differences after re-read: {[(o[1], o[2], str(o[3]), o[4]) for o in ops]}", flush=True)
        reachable = sorted([o for o in ops if o[0] in kk.REPORTS], key=lambda o: (order.index(o[0]), pos.get((o[0], o[1]), 10**6), o[2]))
        fallback = [(o[1], o[2], o[3]) for o in ops if o[0] not in kk.REPORTS]
        tsv = f"{D}/plans/process-{TODAY}-r{rnd}.tsv"
        with open(tsv, "w") as f:
            for subj, t, lv, d, kind in reachable: f.write(f"{subj}\t{t}\t{lv}\t{d.month}\t{d.day}\n")
        safe_open("All Progress")
        res = fill.main_ordered(tsv, f"{D}/state/process-create-{TODAY}-r{rnd}-{NOW:%H%M}.log")
        for subj, t, lv, d, kind in reachable:
            r = res.get((t, lv, str(d.month), str(d.day)), "")
            if r.startswith("level") and kind == "create" and [t, lv] not in state.setdefault("no_level", []): state["no_level"].append([t, lv])
            if r not in ("created", "redated", "done before") and kind in ("move", "park"): fallback.append((t, lv, d))
        fallback_redate(fallback, log)
        state["last_run"] = (TODAY - datetime.timedelta(days=1)).isoformat()      # re-read today's rows fully
        ops = diff(read_assignments())
        dropped = [o for o in ops if o[4] == "create" and [o[1], o[2]] in state.get("no_level", [])]
        ops = [o for o in ops if o not in dropped]
        dropped_all = locals().get("dropped_all", []) + dropped
    for o in ops:                                       # failed every round: set aside so it can't stall future runs
        if o[4] == "move" and [o[1], o[2]] not in state.setdefault("unplaceable", []): state["unplaceable"].append([o[1], o[2]])
    save_state()
    msg = "VERIFIED: app matches the plan" if not ops else f"WARNING: {len(ops)} differences remain: {[(o[1], o[2], str(o[3]), o[4]) for o in ops]}"
    dl = {(o[1], o[2], str(o[3])) for o in locals().get("dropped_all", [])}
    if dl: msg += f" | {len(dl)} planned lesson(s) dropped (the app has no such level; the next run plans something else): {sorted(dl)}"
    print(msg, flush=True)
    state["last_run"] = TODAY.isoformat(); save_state()
    print(f"APPLIED in {(time.time()-t0)/60:.1f} min", flush=True)

if __name__ == "__main__":
    main()
