"""Global planner — the architecture of the student's learning plan (parent 10/10: TimeBack-like, mastery-based, not age cohorts).
Every run looks at ALL their lessons (every grade read) and decides, per day: what needs more work, what is NEW and next in its
strand, and where a REACH probe can place them further ahead. Never re-assigns work the child already did well (>=90) or viewed.
Rules and their reasons are logged in plans/ and the populate-student skill; Fable reviews 10/10 shaped the thresholds."""
import datetime
import kk

MASTERY = 90
PREREQ = 80                 # a prerequisite below this blocks what builds on it; 80-89 counts as solid (one mis-tap at age 3)
RETRY_BELOW = 80            # retry only < 80 (80-89 retries were the "trivial repeats" the parent rejected; ~2/3 of retries)
RETRY_GAP_DAYS = 2
STRUGGLE_WAIT_DAYS = 14
FOCUS_DAYS = 14             # a parent focus request lasts two weeks unless renewed
FOCUS_EVERY_DAYS = 3        # parent 10/10: "don't go crazy on t" -> one extra practice lesson every 3rd day,
FOCUS_MAX = 3               # at most 3 per plan, on top of the letter's normal ladder     # a lesson the child could not do and that has no easier level comes back after 2 weeks
MAX_RETRIES_PER_DAY = 2
LETTER_STAGES_PER_PLAN = 3  # parent 10/12: tracing is productive now -> a letter's whole tracing ladder may be in one plan (separate days)
MIN_LETTERS_PER_DAY = 1     # placed right after the day's gate lessons (2 before 11/10, when the day held 10)
LETTER_SLOTS = 2            # parent 10/10: the child can NAME every letter; the letter lessons are tracing/production practice -> a few daily
MAX_EXTRA_LETTERS = 7       # parent 10/10: 10 a day unless path-dependent. Different letters are independent, so when the day's
                            # new skills run out, tracing lessons for MORE letters fill the day (one stage per letter per day)
DAILY = 5                   # parent 11/10 (inception-to-date review): a small day gets finished; a big one gets cherry-picked
                            # and the gate lessons sit undone. Gates go in first.
MAX_GATES_PER_DAY = 3       # gate = a rollback step or a readiness check: the lessons the rest of the plan is waiting on
HOLD_CHECK_DAYS = 5         # a hold gets its readiness check after 5 days at most (holds tended to pass their first check)
HOLD_EXTEND_DAYS = 7        # a failed check (< 70) rests a week (was 14)
CONFIRM_STEP_GAP = 2        # sequential math: the next step needs a SECOND result >= 80 on the step before, on a later day
CONFIRM_GRADE_GAP = 7       # moving a strand up a grade needs two results >= 80 at least a week apart in the strand below
                            # (their repeat scores swing 30+ points, and every "not ready" came right after a single good score)
BOOKS_PER_DAY = 0           # no book slots: books are unscored and give no evidence. Books are never assigned;
                            # the child can still read them on their own. Set back to 1 to restore (non-fiction first, decodables after CVC).
LETTER_ORDER = "satinpcehrdmgoulfbjwkvxyzq"
BS_GATE_FOR_ENDING = 8      # ending sounds open after this many beginning sounds are solid
ENDING_GATE_FOR_VOWELS = 6  # short vowels / CVC open after this many ending sounds are solid (or a CVC probe passes)
LOGIC_OK_CATEGORIES = ("Flexible Thinking", "Focus & Memory")      # cognitive work only (songs/movement/feelings excluded)
NOT_WORK = {"What do you hear?", "The Muffin Man", "Apples & Bananas", "Hickory Dickory", "Old MacDonald", "Hello A, Hello Z",
            "Mystery Box", "Uh Huh"}
NOT_WORK_DEFAULT = frozenset(NOT_WORK)
BOOK_CATS_READERS = ("Early Readers", "Stories")
INCLUDE_PLAY = False        # False: Logic+ only in LOGIC_OK_CATEGORIES, and NOT_WORK titles (songs etc.) are never assigned
BOOK_CATS_NONFIC = ("National Geographic Young Explorer", "Non-Fiction: Animals", "Non-Fiction: Vehicles")
LETTER_CATS = ("Phonics: Extra", "Lowercase", "Uppercase", "Beginning Letter", "Ending Letter", "Short Vowel")   # item-specific: never credited

# Family choices, set per family in state.json "settings" (written by the setup-student skill). Defaults are the constants above.
SETTINGS = {"daily": "DAILY", "books_per_day": "BOOKS_PER_DAY", "max_retries_per_day": "MAX_RETRIES_PER_DAY",
            "letter_slots": "LETTER_SLOTS", "max_gates_per_day": "MAX_GATES_PER_DAY"}
def configure(settings):
    """Apply state.json "settings": the integer knobs above, "include_play" (bool) and "exclude_titles" (list of lesson titles)."""
    g = globals()
    for key, name in SETTINGS.items():
        if key in settings: g[name] = int(settings[key])
    if "include_play" in settings: g["INCLUDE_PLAY"] = bool(settings["include_play"])
    g["NOT_WORK"] = (set() if g["INCLUDE_PLAY"] else set(NOT_WORK_DEFAULT)) | set(settings.get("exclude_titles", []))
def logic_ok(v):
    """Logic+ lessons count as work only in the cognitive categories, unless the family includes play content."""
    return INCLUDE_PLAY or not v["subject"].startswith("Logic+") or v["category"] in LOGIC_OK_CATEGORIES

# Strand ladders across grades. A lesson at grade g opens when these strands one grade down are solid.
MATH4_PREREQ = {
    "Count to 3": ["Count to 2", "Count to 3"], "Count to 4": ["Count to 2", "Count to 3", "Count to 4"],
    "Count to 5": ["Count to 3", "Count to 4", "Count to 5"], "Count to 6": ["Count to 4", "Count to 5"], "Count to 7": ["Count to 4", "Count to 5"],
    "Compare Numbers": ["Compare Numbers"], "Compare Ordinal Numbers": ["Last"],
    "Addition within 4": ["Addition within 3", "Count to 4"], "Subtraction within 4": ["Subtraction within 3", "Count to 4"],
    "Compare Sizes": ["Compare Sizes"], "Colors": ["Colors"], "Patterns": ["Patterns"], "Positions": ["Positions"], "Shapes": ["Shapes"],
}
ELA4_PREREQ = {             # Age-4 ELA strands with no same-named Age-3 strand (explicit; the old "80% of the grade" rule never passed)
    "Print Concepts: Words, Letters": ["Print Concepts: Words"],   # NOTE: its "More Words" is spelling -> held with letter sounds
    "Phonological Awareness: Add Phonemes": ["Phonological Awareness: Onset & Rime", "Phonological Awareness: Three-Phoneme Words"],
    "Writing Words": ["Writing Lines, Letters, Words"],
    "Prepositions": [],
}
MATHK_PREREQ = {            # Kindergarten math strands (read 10/10): each waits on the Age-4 strand(s) under it
    "Count to 4": ["Count to 4"], "Count to 5": ["Count to 5"], "Count to 6": ["Count to 6"], "Count to 7": ["Count to 7"],
    "Count to 8": ["Count to 6", "Count to 7"], "Count to 9": ["Count to 6", "Count to 7"], "Count to 10": ["Count to 6", "Count to 7"],
    "Count to 15": ["Count to 7"], "Count to 20": ["Count to 7"], "Zero": ["Count to 4"],
    "Compare Numbers": ["Compare Numbers"], "Compare Ordinal Numbers": ["Compare Ordinal Numbers"],
    "Addition within 5": ["Addition within 4"], "Subtraction within 5": ["Subtraction within 4"],
    "Decompose Numbers within 10": ["Compare Numbers", "Addition within 4"],
    "Compare Sizes": ["Compare Sizes"], "Colors": ["Colors"], "Patterns": ["Patterns"], "Positions": ["Positions"], "Shapes": ["Shapes"],
}
# Kindergarten listening comprehension (parent 11/8: "add both"): read-aloud stories with questions. Open from Age 3, but only after a
# TRIAL lesson scores >= 80 on their own; until then the trial is the only one. Sequential: one untested step per strand at a time.
COMPREHENSION = ("Key Ideas & Details", "Informative Writing & Sequencing", "Integrating Text & Illustrations")
COMPREHENSION_TRIAL = "Identify Characters"
ELAK_PREREQ = {c: [] for c in COMPREHENSION}
PREREQ_MAPS = {("Math", 4): MATH4_PREREQ, ("ELA", 4): ELA4_PREREQ, ("Math", 5): MATHK_PREREQ, ("ELA", 5): ELAK_PREREQ}   # Kindergarten maps get written as its strands appear (held + logged until then)

# Reach probes (parent 10/10): only where a skill GENERALIZES across lessons. Letters/sounds are item-specific: never probed.
PROBE_STRANDS = ("CVC Words", "Vocabulary & Sorting Objects", "Focus & Memory", "Flexible Thinking", "COUNT LADDER")
PROBE_REPROBE_DAYS = 21
MAX_PROBES_PER_DAY = 1

import re as _re
def is_letter_sound(title):
    """Per-letter sound lessons: 'Beginning Sound b', 'Ending Sound t', 'Letter B Words' (not the phonological 'Beginning Sounds 1')."""
    return bool(_re.match(r"^(Beginning|Ending) Sound [a-z]$", title) or _re.match(r"^Letter [A-Z] Words$", title))
HOLD_MATCH = {"letter_sounds": r"^((Beginning|Ending) Sound [a-z]|Letter [A-Z] Words|More Words|Writing Words|Uppercase Words|Write Words)$"}   # word writing waits for sounds (10/13)
def solid(v): return v["status"] in ("mastered", "viewed", "credited") or (v["status"] == "needs_work" and v["pct"] >= PREREQ)
# Progression evidence = SCORED results only (parent 10/31): an unscored green check ("viewed") is accepted as done and never
# re-assigned, but it neither opens nor blocks anything. Gates, sound counts and grade exhaustion use proven(), not solid().
def proven(v): return v["status"] in ("mastered", "credited") or (v["status"] == "needs_work" and v["pct"] >= PREREQ)
def base_grade(subject): return kk.split_key(subject)
def strand_of(v):
    """Strand id: (report key, category); math 'Count to N' categories form one ladder per grade."""
    cat = v["category"] or ""
    if base_grade(v["subject"])[0] == "Math" and cat.startswith("Count to"): return (v["subject"], "COUNT LADDER")
    return (v["subject"], cat)

def evaluate(catalog, rows, state):
    att = state.get("attempts", {})
    # an "assisted" flag covers only the attempt(s) up to the date it was recorded; a later attempt of their own counts
    assisted = {k.split("|")[0] for k, v in state.get("assisted", {}).items()
                if not any(a.split("|")[0] == k.split("|")[0] and x.get("date", "") > v.get("date", "") for a, x in att.items())}
    credited = state.get("credited", {})
    struggled = {t: v for t, v in state.get("struggled", {}).items()     # cleared once the child scores >= 80 on it afterwards
                 if not any(k.split("|")[0] == t and a.get("date", "") > v["date"] and (a.get("score") or 0) >= PREREQ for k, a in att.items())}
    les = {}
    for i, c in enumerate(catalog):
        k = (c["subject"], c["title"])
        if k in les: continue
        st = c["status"]
        if c["title"] in assisted: st = "new"
        if st == "new" and c["title"] in credited: st = "credited"
        les[k] = {**c, "status": st, "last_attempt": None, "levels_done": {}, "pos": i}
        sg = struggled.get(c["title"])                  # parent saw them unable to do it: treat as a failed attempt (< 70)
        if sg and st in ("new", "needs_work"):
            les[k].update(status="needs_work", pct=min(c.get("pct") or 50, 50), struggled=sg["date"])
        if c["category"] and (c["category"].startswith(("Phonics: Extra", "Early Readers", "Stories", "Non-Fiction", "National Geo", "Opposites"))
                              or c["subject"].startswith("Logic+")): les[k]["levels"] = ["Main"]
    lowest = {}
    for k in les:
        if k[1] not in lowest or base_grade(k[0])[1] < base_grade(lowest[k[1]])[1]: lowest[k[1]] = k[0]
    attempts = state.get("attempts", {}); today = datetime.date.today().isoformat()
    # what the child has DONE comes from our own record first: re-dating a finished assignment (e.g. clearing it to the pool)
    # resets its checkmark in the app, so the app alone forgets completed levels
    for key, a in attempts.items():
        t, lv = key.split("|")
        if t in lowest and (a.get("score") is not None or a.get("viewed")):
            les[(lowest[t], t)]["levels_done"].setdefault(lv, a.get("score"))
            if t not in assisted and a.get("date") and a["date"] <= today and (les[(lowest[t], t)]["last_attempt"] or "") < a["date"]:
                les[(lowest[t], t)]["last_attempt"] = a["date"]          # their real last try (app dates move when lessons are re-dated)
    for r in rows:
        for k in [(lowest[r["title"]], r["title"])] if r["title"] in lowest else []:
            if r["done"] and r["date"]:
                les[k]["levels_done"][r["level"]] = r["score"]
                when = attempts.get(f"{r['title']}|{r['level']}", {}).get("date") or (r["date"] if r["date"] <= today else None)
                if when and r["title"] not in assisted and (les[k]["last_attempt"] or "") < when: les[k]["last_attempt"] = when
    return les

def order_day(items):
    """Order within a day (as planned; the app shows its own list order for new creates). Books last as the reward."""
    g = {"letter": [], "retry": [], "probe": [], "math": [], "skill": [], "logic": [], "book": []}
    for x in items:
        w = x["why"]
        g["retry" if w.startswith("needs") else "probe" if w.startswith("reach") else "letter" if "letter" in w else
          "math" if "math" in w else "skill" if "skill" in w else "logic" if "logic" in w else "book"].append(x)
    out = []; pattern = ["letter", "retry", "math", "probe", "skill", "letter", "logic", "math", "retry", "letter", "skill", "logic"]
    while any(g[k] for k in pattern):
        for k in pattern:
            if g[k]: out.append(g[k].pop(0))
    return out + g["book"]

def plan(catalog, rows, state, horizon, caps=None):
    today = horizon[0]
    caps = caps or {}
    def cap(d): return caps.get(d, DAILY)
    les = evaluate(catalog, rows, state); held = []; notes = []
    lowest = {}
    for k in les:
        if k[1] not in lowest or base_grade(k[0])[1] < base_grade(lowest[k[1]])[1]: lowest[k[1]] = k[0]
    by_title = {}
    for k, v in sorted(les.items(), key=lambda kv: base_grade(kv[0][0])[1]): by_title.setdefault(k[1], v)
    no_level = {tuple(x) for x in state.get("no_level", [])} | {tuple(x) for x in state.get("unplaceable", [])}   # app can't hold / won't move
    attempts = state.get("attempts", {})
    def status(t): return by_title.get(t, {}).get("status", "missing")
    def first_score(t):
        a = attempts.get(f"{t}|Main", {})
        return a.get("first", a.get("score"))
    def is_book(v): return (v["category"] or "") in BOOK_CATS_READERS + BOOK_CATS_NONFIC
    def is_skill(v):
        if is_book(v) or v["title"] in NOT_WORK: return False
        return logic_ok(v)
    def norm(cat): return (cat or "").lower().replace("within 4", "within").replace("within 3", "within")
    strands = {}
    for v in sorted(les.values(), key=lambda v: v["pos"]):
        if lowest.get(v["title"]) == v["subject"]: strands.setdefault(strand_of(v), []).append(v)   # repeats of lower-grade titles excluded

    # ---- 0. probes: evaluate results, un-credit on contrary evidence --------------------------------------------------
    # when the letter-sound lessons aren't understood yet, the parent can pause them:
    # state["hold"]["letter_sounds"] = {"date", "until", "note"}: pause every per-letter sound lesson until `until`, then ramp back in.
    # After `until`: ONE sound lesson a day only until one comes back >= 80 (it clicked) -> then the full ladder at normal pace
    # (parent 10/10: once the child understands one, give them more). If the first check scores < 70, the pause extends by 14 days.
    # Generic HOLDS (the parent's "not ready yet"): state["hold"][name] = {"date", "until", "note", "match": regex on titles}.
    # Until `until`: none of those lessons. Then a readiness check: ONE a day until one scores >= 80 -> hold lifted, full pace
    # (parent: once it clicks, give them more). A first check < 70 extends the hold 14 days (tell the parent).
    held_families, checking_families, ladder_pick = {}, {}, {}
    for name, hd in list(state.get("hold", {}).items()):
        rx = hd.get("match") or HOLD_MATCH.get(name)
        if not rx: continue
        until = datetime.date.fromisoformat(hd["until"])
        if not hd.get("fixed"):                                           # 11/10: check after HOLD_CHECK_DAYS at most ("fixed" keeps the parent's date)
            until = min(until, datetime.date.fromisoformat(hd["date"]) + datetime.timedelta(days=HOLD_CHECK_DAYS))
        u = until.isoformat()
        scored = sorted((a.get("date"), a.get("score"), k) for k, a in attempts.items()
                        if _re.match(rx, k.split("|")[0]) and a.get("score") is not None and a.get("date", "") >= min(u, hd.get("check_from", u)))
        checks = [(d_, sc) for d_, sc, _ in scored if d_ >= u]
        latest = checks[-1][1] if checks else None                       # judge on their LATEST check
        need = hd.get("need", 1)                                         # how many DIFFERENT lessons must pass to lift the hold
        passes = sorted({k.split("|")[0] for _, sc, k in scored if sc >= PREREQ})
        if today < until:
            held_families[name] = rx; notes.append(f"{name} paused until {u} ({hd['note']})")
        elif len(passes) >= need and (latest is None or latest >= 70):
            state["hold"].pop(name); notes.append(f"{name.upper()} CLICKED {passes} {checks}: hold lifted, full pace resumes")
        elif latest is not None and latest < 70:
            hd.setdefault("check_from", u)                               # earlier passes still count after the rest
            hd["until"] = (datetime.date.fromisoformat(checks[-1][0]) + datetime.timedelta(days=HOLD_EXTEND_DAYS)).isoformat(); hd["fixed"] = True
            held_families[name] = rx; notes.append(f"{name.upper()} NOT YET {checks}: pause extended to {hd['until']} (tell the parent)")
        else:
            hd.setdefault("check_from", u)
            checking_families[name] = rx
            # "ladder" (11/10, letter sounds): the checks are walked in this order, starting from what the child has PASSED, not from the
            # lesson the child failed; "pair" re-teaches the letter's own "Letter X" lesson the same day.
            tried = {k for _, _, k in scored} | {f"{t}|{lv}" for t, lv in state.get("no_level", [])}
            step = next(((t, lv) for t, lv in hd.get("ladder", []) if f"{t}|{lv}" not in tried), None)
            if step: ladder_pick[name] = (step[0], step[1], hd.get("pair"))
            notes.append(f"{name}: readiness check, {len(passes)} of {need} passed {passes}" + (f"; next: {step[0]} ({step[1]})" if step else ""))
    # ROLLBACKS (when the parent sees the child doesn't get a concept at all, roll back to an earlier lesson in that strand):
    # state["rollback"][name] = {"date", "note", "ladder": [[title, level], ...], "hold": regex}. Their earlier scores in the strand are
    # NOT evidence (parent saw the child doesn't get it). Everything matching `hold` waits; the ladder is walked from the bottom, one step at a
    # time, each step scored >= 80 on their own AFTER `date`. A step < 70 rests 7 days, 70-79 retries in 2. All steps passed -> lifted.
    rollback_items = []; rollback_titles = set()
    for name, rb in list(state.get("rollback", {}).items()):
        step = None
        for t, lv in rb["ladder"]:
            # coached/assisted attempts (state "assisted" recorded on or after the attempt) are not clean evidence (parent 11/9)
            def coached(k, a): return k in state.get("assisted", {}) and a.get("date", "") <= state["assisted"][k].get("date", "")
            tries = [(a["date"], a["score"], coached(k, a)) for k, a in attempts.items()
                     if k == f"{t}|{lv}" and a.get("score") is not None and a.get("date", "") >= rb["date"]]
            mine = sorted((d, sc) for d, sc, c in tries if not c)
            if mine and mine[-1][1] >= PREREQ: continue
            nb = None
            if mine: nb = datetime.date.fromisoformat(mine[-1][0]) + datetime.timedelta(days=7 if mine[-1][1] < 70 else RETRY_GAP_DAYS)
            elif any(c for _, _, c in tries):   # coached pass: re-test on their own after a gap, so it shows what stuck
                nb = datetime.date.fromisoformat(max(d for d, _, c in tries if c)) + datetime.timedelta(days=RETRY_GAP_DAYS)
            step = (t, lv, nb, mine); break
        if step is None:
            state["rollback"].pop(name); notes.append(f"ROLLBACK {name.upper()} PASSED: {rb['ladder']} -> strand resumes"); continue
        held_families[f"rollback:{name}"] = rb["hold"]
        for t, lv in rb["ladder"]: rollback_titles.add(t)         # only while the rollback is active
        rollback_items.append((name, *step))
        notes.append(f"rollback {name}: evaluating at {step[0]} ({step[1]}), tries since {rb['date']}: {step[3] or 'none'}; later lessons wait ({rb['note']})")
    # Word WRITING (spelling "nuts") needs several letter sounds, not just the first one that clicks: it stays closed until
    # BS_GATE_FOR_ENDING beginning sounds are proven, the same bar as ending sounds (11/10; it used to return the day the hold lifted).
    if sum(1 for t, v in by_title.items() if _re.match(r"^Beginning Sound [a-z]$", t) and proven(v)) < BS_GATE_FOR_ENDING:
        held_families["word_writing"] = r"^(More Words|Writing Words|Uppercase Words|Write Words)$"
    def held_title(t): return any(_re.match(rx, t) for rx in held_families.values())
    def checking_title(t): return next((n for n, rx in checking_families.items() if _re.match(rx, t)), None)
    sounds_held = "letter_sounds" in held_families
    sounds_ramp = "letter_sounds" in checking_families
    probes = state.setdefault("probes", {}); credited = state.setdefault("credited", {}); opened = state.setdefault("opened", [])
    for sk, p in probes.items():
        if p["status"] not in ("pending", "third"): continue
        sc = [first_score(t) for t in p["titles"]]
        if any(s is None for s in sc): continue
        strand = strands.get(tuple(p["strand"]), [])
        if all(s >= MASTERY for s in sc):
            p["status"] = "passed"; p["result"] = sc
            if p["kind"] == "open": opened.append(list(p["strand"])); notes.append(f"REACH PASSED {p['strand'][1]}: strand opened early {sc}")
            else:
                for v in strand:
                    if v["status"] == "new": credited[v["title"]] = {"by": f"probe:{p['strand'][1]}", "date": today.isoformat()}; v["status"] = "credited"
                notes.append(f"REACH PASSED {p['strand'][1]} {sc}: remaining lessons credited")
        elif any(s < PREREQ for s in sc):
            p["status"] = "failed"; p["result"] = sc; p["next_ok"] = (today + datetime.timedelta(days=PROBE_REPROBE_DAYS)).isoformat()
            notes.append(f"REACH FAILED {p['strand'][1]} {sc}: normal sequence; re-probe after {p['next_ok']}")
        elif p["status"] == "pending":
            nxt = [v["title"] for v in strand if v["status"] == "new" and v["title"] not in p["titles"]]
            if nxt: p["titles"].append(nxt[-1]); p["status"] = "third"; notes.append(f"REACH MIXED {p['strand'][1]} {sc}: third probe {nxt[-1]}")
            else: p["status"] = "failed"; p["next_ok"] = (today + datetime.timedelta(days=PROBE_REPROBE_DAYS)).isoformat()
        else:
            p["status"] = "failed"; p["result"] = sc; p["next_ok"] = (today + datetime.timedelta(days=PROBE_REPROBE_DAYS)).isoformat()
    for t, c in list(credited.items()):                 # credit is provisional: a weak score in that strand takes it back
        v = by_title.get(t)
        if not v: continue
        weak = [w["title"] for w in strands.get(strand_of(v), []) if w["status"] == "needs_work" and w["pct"] < PREREQ
                and (w["last_attempt"] or "") >= c["date"]]
        if weak: del credited[t]; v["status"] = "new"; notes.append(f"UN-CREDITED {t}: {weak[0]} scored under {PREREQ}")
    def is_open(v): return [v["subject"], v["category"]] in opened

    # =====================================================================================================================
    # QUEUE MODEL (Fable review 10/11; parent: "populate the next 10 lessons, regardless of where they sit").
    # Every run computes, from their data alone, ONE ranked queue of lessons that are appropriate NOW, then fills the horizon
    # day by day under per-day limits. Sequential strands contribute ONE untested step to the whole plan (the next step
    # depends on that result). Nothing is padded: a day stays short when only outcome-dependent work is left.
    # The app then mirrors the plan exactly (process.py: no sticky, no balancing).
    # =====================================================================================================================
    def is_sequential(v):
        cat = v["category"] or ""; base = base_grade(v["subject"])[0]
        if base == "Math": return cat.startswith(("Count to", "Compare Ordinal", "Addition", "Subtraction", "Decompose", "Zero"))
        if base == "ELA": return cat.startswith("Phonological Awareness") or cat in COMPREHENSION
        return False
    Q = []                                              # queue items
    def add(title, level, subject, why, prio, strand=None, kind="skill", not_before=None, track=None, letter=None, pair=None):
        Q.append({"title": title, "level": level, "subject": subject, "why": why, "prio": prio, "seq": len(Q), "strand": strand,
                  "kind": kind, "family": checking_title(title), "not_before": not_before, "track": track, "letter": letter, "pair": pair})

    # ---- 0b. TWO-RESULT RULE (parent 11/10) -------------------------------------------------------------------------------
    # One good score is not enough to build on: their repeat scores swing 30+ points, and the parent's
    # observations often overrule a passing score. Before the next step of a sequential math strand, and before a strand moves up
    # a grade, there must be TWO results >= 80 of their own, `gap` days apart. If not, the missing one is assigned as a Practice level
    # of the last lesson the child passed (the one narrow exception to "no practice on mastered work"), and what builds on it waits.
    def own_results(w):
        out = []
        for k, a in attempts.items():
            t, lv = k.split("|")
            if t != w["title"] or a.get("score") is None: continue
            if k in state.get("assisted", {}) and a.get("date", "") <= state["assisted"][k].get("date", ""): continue
            out.append((a.get("date") or "2026-09-01", lv, a["score"]))
        if not any(lv == "Main" for _, lv, _ in out) and w.get("pct") is not None and w["title"] not in {k.split("|")[0] for k in state.get("assisted", {})}:
            out.append(("2026-09-01", "Main", w["pct"]))          # scored before the log began (9/7): counts as an old result
        return out
    confirms = {}
    def needs_confirm(ws, gap):
        """None when the lessons `ws` hold two results >= 80 at least `gap` days apart (or the app has no level left to ask with)."""
        good = sorted(r for w in ws for r in own_results(w) if r[2] >= PREREQ)
        if not good: return None
        day = datetime.date.fromisoformat
        if (day(good[-1][0]) - day(good[0][0])).days >= gap: return None
        for w in sorted(ws, key=lambda w: -w["pos"]):
            if not proven(w) or held_title(w["title"]) or w["title"] in rollback_titles: continue
            done = {lv for _, lv, _ in own_results(w)} | set(w["levels_done"])
            lv = next((l for l in ("Practice 1", "Practice 2") if l not in done and (w["title"], l) not in no_level
                       and l in w.get("levels", [l])), None)
            if lv:
                nb = max(day(good[0][0]) + datetime.timedelta(days=gap), day(good[-1][0]) + datetime.timedelta(days=1))
                if (w["title"], lv) not in confirms or nb < confirms[(w["title"], lv)][1]: confirms[(w["title"], lv)] = (w, nb)
                return w["title"], lv, nb
        return None
    def below_strand(v):
        """The lessons one grade down that a lesson builds on (explicit PREREQ_MAPS first, else the same category name); None = unmapped."""
        base, g = base_grade(v["subject"]); cat = v["category"] or ""
        below = [w for w in les.values() if base_grade(w["subject"]) == (base, g - 1) and is_skill(w)]
        pm = PREREQ_MAPS.get((base, g), {})
        if cat in pm: return [w for w in below if w["category"] in pm[cat]]
        return [w for w in below if norm(w["category"]) == norm(cat)] or (None if below else [])
    def step_confirm(v):
        """Sequential math: a second result on the step before (same strand), else on the strand a grade below."""
        prev = [w for w in les.values() if strand_of(w) == strand_of(v) and w["pos"] < v["pos"] and proven(w) and w["status"] != "credited"]
        if prev: return needs_confirm([max(prev, key=lambda w: w["pos"])], CONFIRM_STEP_GAP)
        return needs_confirm(below_strand(v) or [], CONFIRM_GRADE_GAP)

    # ---- 1. needs work: < 80, not proven by a later lesson of the SAME category, not held -------------------------------
    def superseded(v):
        if (v["category"] or "").startswith(LETTER_CATS): return False
        if v.get("struggled"): return False            # parent saw them struggle: a different lesson's 100 doesn't cancel the retry
        same = [w for w in les.values() if w["subject"] == v["subject"] and w["category"] == v["category"]]
        return any(w["pos"] > v["pos"] and w["status"] == "mastered" for w in same)
    retries = []
    for v in les.values():
        if v["status"] != "needs_work" or by_title.get(v["title"]) is not v or v["pct"] >= RETRY_BELOW: continue
        if held_title(v["title"]): continue
        if v["subject"].startswith("Logic+") and (not logic_ok(v) or v["title"] in NOT_WORK): continue
        if superseded(v): notes.append(f"superseded (no retry): {v['title']} {v['pct']}"); continue
        if is_sequential(v) and base_grade(v["subject"])[0] == "Math":
            nc = step_confirm(v)                       # e.g. 4th-6th (41) is not retried the day after ONE pass on 1st-3rd
            if nc: held.append((v["title"], f"retry waits for a second result: {nc[0]} ({nc[1]}) from {nc[2]}")); continue
        done = v["levels_done"]
        basic_ok = "Basic" not in done and (v["title"], "Basic") not in no_level and "Basic" in v.get("levels", ["Basic"])
        last = v.get("struggled") or v["last_attempt"]
        nb = (datetime.date.fromisoformat(last) + datetime.timedelta(days=RETRY_GAP_DAYS)) if last else None
        if basic_ok: level = "Basic"                   # remediation = the EASIER level; Practice is a different variant, not remediation
        else:
            level = "Main"
            if v.get("struggled"):                     # couldn't do it and there is no easier level: rest it, counted from their LATEST try
                nb = datetime.date.fromisoformat(max(v["struggled"], v["last_attempt"] or "")) + datetime.timedelta(days=STRUGGLE_WAIT_DAYS)
                if nb > horizon[-1]: held.append((v["title"], f"struggled {v['struggled']}, no Basic level: back from {nb}")); continue
        retries.append((v["pct"], v["title"], level, v["subject"], nb, strand_of(v)))
    for pct, t, lv, sk, nb, st in sorted(retries, key=lambda r: r[0]):
        add(t, lv, sk, f"needs work ({pct}%)", 0, strand=st, kind="retry", not_before=nb)

    for name, t, lv, nb, mine in rollback_items:
        sk = next((v["subject"] for v in sorted(les.values(), key=lambda v: base_grade(v["subject"])[1]) if v["title"] == t), "Math")
        add(t, lv, sk, f"rollback {name}: re-evaluate from {t} ({lv})", -1, kind="gate", not_before=nb)
    for name, (t, lv, pair) in ladder_pick.items():      # readiness check that starts from a lesson the child passed (+ its Letter X lesson)
        v = by_title.get(t)
        if v: add(t, lv, v["subject"], f"readiness check: {name}", -2, kind="gate",
                  pair=f"Letter {t[-1].upper()}" if pair and _re.match(r"^(Beginning|Ending) Sound [a-z]$", t) else None)

    # ---- 2. letters: ladder per letter (tracing; sounds only when not held) ---------------------------------------------
    def stages(c):
        s_ = [f"Letter {c.upper()}", f"Lowercase {c}", f"Uppercase {c.upper()}"]
        if sounds_held: return s_
        if f"Beginning Sound {c}" in by_title: s_.append(f"Beginning Sound {c}")
        s_.append(f"Letter {c.upper()} Words")
        return s_
    bs_solid = sum(1 for t, v in by_title.items() if _re.match(r"^Beginning Sound [a-z]$", t) and proven(v))
    end_solid = sum(1 for t, v in by_title.items() if _re.match(r"^Ending Sound [a-z]$", t) and proven(v))
    letter_items = []
    for c in LETTER_ORDER:
        all_st = stages(c) + [f"Ending Sound {c}"]
        weak = next((t for t in all_st if t in by_title and by_title[t]["status"] == "needs_work" and not solid(by_title[t])), None)
        st_ = [t for t in stages(c) if status(t) == "new"]
        if weak: st_ = [t for t in st_ if all_st.index(t) < all_st.index(weak)]; held.append((c, weak))
        if bs_solid >= BS_GATE_FOR_ENDING and status(f"Ending Sound {c}") == "new" and not weak: st_.append(f"Ending Sound {c}")
        for k, t in enumerate(st_[:LETTER_STAGES_PER_PLAN]):          # at most 2 stages of a letter per plan, on separate days
            letter_items.append((k, c, t))

    # ---- 3. new skills, mastery-based across grades -----------------------------------------------------------------------
    def gate(v):
        base, g = base_grade(v["subject"]); cat = v["category"] or ""
        if base == "ELA" and cat.startswith(LETTER_CATS[:5]): return False
        if lowest.get(v["title"], v["subject"]) != v["subject"]: return False
        if base == "ELA" and cat.startswith(("Short Vowel", "CVC")) and end_solid < ENDING_GATE_FOR_VOWELS and not is_open(v): return False
        if cat in COMPREHENSION and v["title"] != COMPREHENSION_TRIAL:
            tv = by_title.get(COMPREHENSION_TRIAL)
            if not (tv and proven(tv)): held.append((v["title"], f"comprehension waits for the trial ({COMPREHENSION_TRIAL} >= 80)")); return False
        strand = below_strand(v)
        if strand is None: held.append((v["title"], f"unmapped strand '{cat}' (add it to PREREQ_MAPS)")); return False
        if not strand and cat not in PREREQ_MAPS.get((base, g), {}): return True      # nothing is read a grade down
        gaps = [w["title"] for w in strand if w["status"] != "viewed" and not proven(w)]   # unscored: no evidence either way
        if gaps:
            why = "blocked by hold" if any(held_title(t) for t in gaps) else "hole"
            held.append((v["title"], f"{why}: {', '.join(gaps[:3])}")); return False
        if v["title"] in rollback_titles: return True     # a rollback ladder is its own, stricter evidence rule
        nc = needs_confirm(strand, CONFIRM_GRADE_GAP)      # up a grade only on two results a week apart in the strand below
        if nc: held.append((v["title"], f"up a grade waits for a second result: {nc[0]} ({nc[1]}) from {nc[2]}")); return False
        return True
    new_skills = []; seq_taken = set()
    for c in sorted(catalog, key=lambda c: base_grade(c["subject"])[1]):
        v = les.get((c["subject"], c["title"]))
        if not v or v["status"] != "new" or not is_skill(v) or held_title(c["title"]): continue
        if (c["title"], "Main") in no_level and ((c["title"], "Basic") in no_level or "Basic" not in v.get("levels", ["Basic"])): continue
        if any(x[0] == c["title"] for x in new_skills): continue
        if not gate(v): continue
        st = strand_of(v)
        if is_sequential(v):
            if st in seq_taken: continue               # one untested step per sequential strand in the whole plan
            weak_before = [w["title"] for w in les.values() if strand_of(w) == st and w["pos"] < v["pos"]
                           and w["status"] == "needs_work" and not solid(w)]
            if weak_before:                            # a failed/struggled earlier step: fill that hole first
                held.append((v["title"], f"hole: {', '.join(weak_before[:2])}")); seq_taken.add(st); continue
            seq_taken.add(st)
            prev = [w for w in les.values() if strand_of(w) == st and w["pos"] < v["pos"] and proven(w) and w["status"] != "credited"]
            nc = needs_confirm([max(prev, key=lambda w: w["pos"])], CONFIRM_STEP_GAP) if prev and base_grade(v["subject"])[0] == "Math" else None
            if nc: held.append((v["title"], f"next step waits for a second result: {nc[0]} ({nc[1]}) from {nc[2]}")); continue
        new_skills.append((c["title"], c["subject"], st, base_grade(c["subject"])[0]))

    # ---- 4. reach probes (unchanged rules; at most one a day) --------------------------------------------------------------
    probe_items = []
    for sk, members in strands.items():
        name = sk[1]
        if not any(name.startswith(p) for p in PROBE_STRANDS): continue
        key = f"{sk[0]}|{name}"; p = probes.get(key)
        if p and (p["status"] in ("pending", "third", "passed") or p.get("next_ok", "") > today.isoformat()): 
            if p["status"] in ("pending", "third"):
                probe_items += [(t, by_title[t]["subject"], name) for t in p["titles"] if status(t) == "new"]
            continue
        new = [v for v in members if v["status"] == "new" and is_skill(v)]
        if len(new) < 3: continue
        if name.startswith("CVC Words"):                 # gated strand: reach = can the child already do it? (open early if so)
            if sounds_held or sounds_ramp: continue      # CVC needs letter sounds; never while those are paused or unproven
            if is_open(new[0]) or end_solid >= ENDING_GATE_FOR_VOWELS: continue
            if not (status("Blend Sounds 2") == "mastered" and bs_solid >= 6): continue
            titles, kind = [new[0]["title"], new[1]["title"]], "open"
        else:                                            # in-sequence strand: test out of the rest
            mastered = [v for v in members if v["status"] == "mastered"]
            weak = [v for v in members if v["status"] == "needs_work" and v["pct"] < PREREQ]
            if len(mastered) < 2 or weak: continue
            titles, kind = [new[-1]["title"], new[-2]["title"]], "credit"
        probes[key] = {"strand": list(sk), "titles": titles, "kind": kind, "status": "pending", "assigned": today.isoformat()}
        notes.append(f"REACH ASSIGNED {name} ({kind}): {titles}")
        probe_items += [(t, by_title[t]["subject"], name) for t in titles]
    probe_titles = {t for t, _, _ in probe_items}
    for t, sk, name in probe_items: add(t, "Main", sk, f"reach probe: {name}", 3, strand=("probe", name), kind="probe")

    # ---- 1b. parent focus: through holds AND gates; cadence by calendar date ---------------------------------------------
    for c, f in state.get("focus", {}).items():
        fdate = datetime.date.fromisoformat(f["date"])
        if (today - fdate).days > f.get("days", FOCUS_DAYS): continue
        if "items" in f: cand = [tuple(x) for x in f["items"]]; per_day, every, offset, fmax = f.get("per_day", 1), 1, 0, f.get("max", 99); why = f"focus: {c}"
        else:
            U, l = c.upper(), c.lower()
            cand = [(f"Lowercase {l}", "Practice 1"), (f"Uppercase {U}", "Practice 1"), (f"Lowercase {l}", "Practice 2"),
                    (f"Uppercase {U}", "Practice 2"), (f"Beginning Sound {l}", "Practice 1")]
            per_day, every, offset, fmax = 1, FOCUS_EVERY_DAYS, 1, FOCUS_MAX; why = f"focus: letter {l}"
        n = 0
        repeat_ok = f.get("repeat_ok", False)           # parent asked for re-teaching: done lessons may be assigned again
        for t, lv in cand:
            v = by_title.get(t)
            if not v or (t, lv) in no_level or held_title(t): continue
            if lv in v["levels_done"] and not repeat_ok: continue
            if lv == "Main" and v.get("struggled"): continue      # the child can't do the Main yet: focus uses the other levels
            if lv == "Main" and v["status"] == "new" and is_sequential(v) and any(        # 11/10: a focus doesn't jump a weak step either
                    strand_of(w) == strand_of(v) and w["pos"] < v["pos"] and w["status"] == "needs_work" and not solid(w) for w in les.values()): continue
            a = attempts.get(f"{t}|{lv}", {})
            if repeat_ok and a.get("score") is not None and a["score"] >= MASTERY and a.get("date", "") >= f["date"]: continue   # passed since the focus began
            if lv == "Main" and not repeat_ok and (v["status"] not in ("new", "needs_work") or (v["status"] == "new" and not gate(v))): continue
            if lv != "Main" and lv not in v.get("levels", [lv]): continue
            if n >= fmax: break
            add(t, lv, v["subject"], why, 2, strand=strand_of(v), kind="focus",
                track={"name": c, "per_day": per_day, "every": every, "offset": offset, "start": fdate}); n += 1

    for t, sk, st, base in new_skills:
        if t in probe_titles: continue
        lv = "Basic" if (t, "Main") in no_level else "Main"          # the app has no reachable Main (e.g. Prepositions): start at Basic
        add(t, lv, sk, f"next {'math' if base == 'Math' else 'logic' if base == 'Logic+' else 'ELA skill'}", 4, strand=st)
    for k, c, t in letter_items: add(t, "Main", by_title[t]["subject"], "next letter stage", 5 + k, strand=("letter", c), kind="letter", letter=c)
    cat_sorted = sorted(catalog, key=lambda c: base_grade(c["subject"])[1])
    # Books: Early Readers are DECODABLE phonics readers for a child who can sound out CVC words; before that they are
    # meaningless. So: non-fiction on the child's interests first, then read-aloud Stories; decodable Early Readers only once the child can decode
    # (ending sounds solid enough to open short vowels / CVC).
    def book_titles(cats):
        return list(dict.fromkeys(c["title"] for c in cat_sorted if c["subject"].startswith("ELA") and c["category"] in cats and status(c["title"]) == "new"))
    can_decode = end_solid >= ENDING_GATE_FOR_VOWELS
    nonfic = book_titles(BOOK_CATS_NONFIC)
    stories = [t for t in book_titles(("Stories",)) if t not in nonfic]
    readers = [t for t in book_titles(("Early Readers",)) if t not in nonfic + stories] if can_decode else []
    for t in nonfic + stories + readers:
        add(t, "Main", "ELA", "book: non-fiction" if t in nonfic else "book: story" if t in stories else "book: early reader", 7, kind="book")

    # ---- 5. fill the horizon from the queue ------------------------------------------------------------------------------
    import math as _math
    for (t, lv), (w, nb) in confirms.items():
        add(t, lv, w["subject"], f"second result before moving on ({lv})", 1, strand=strand_of(w), kind="confirm", not_before=nb)
    Q = [x for x in Q if x["title"] not in rollback_titles or x["why"].startswith("rollback")]
    Q = [x for x in Q if not (x["family"] in ladder_pick and not x["why"].startswith("readiness check"))]   # a ladder picks its own check
    Q.sort(key=lambda x: (x["prio"], x["seq"]))
    # readiness check = the EASIEST lesson of the family: a retry of what the child failed first (lowest prio), then the lowest grade
    chosen = {}
    for x in sorted(Q, key=lambda x: (x["prio"], base_grade(x["subject"])[1], x["seq"])):
        if x["family"] and x["family"] not in chosen: chosen[x["family"]] = id(x)
    Q = [x for x in Q if not x["family"] or chosen.get(x["family"]) == id(x)]
    for x in Q:
        if x["family"]: x["kind"] = "gate"            # a readiness check is a gate: first into the day, outside the retry limit
    days = {d: [] for d in horizon}; placed = set(); families_used = set(); letter_day = {}
    def fits(d, x, letter_quota):
        day = days[d]
        if len(day) >= cap(d) or (x["title"], x["level"]) in placed: return False
        if x["not_before"] and d < x["not_before"]: return False
        if x["family"] and x["family"] in families_used: return False          # readiness check: one in the whole plan
        k = x["kind"]
        if k == "book" and sum(1 for y in day if y["kind"] == "book") >= BOOKS_PER_DAY: return False
        if k == "retry" and sum(1 for y in day if y["kind"] == "retry") >= MAX_RETRIES_PER_DAY: return False
        if k == "gate" and sum(1 for y in day if y["kind"] == "gate") >= MAX_GATES_PER_DAY: return False
        if k == "probe" and sum(1 for y in day if y["kind"] == "probe") >= MAX_PROBES_PER_DAY: return False
        if k == "letter":
            if sum(1 for y in day if y["kind"] == "letter") >= letter_quota: return False
            if letter_day.get(x["letter"]) and letter_day[x["letter"]] >= d: return False      # next stage of a letter: a later day
        if k == "focus":
            tr = x["track"]
            if (d - tr["start"]).days % tr["every"] != tr["offset"] % tr["every"]: return False
            if sum(1 for y in day if y.get("track") and y["track"]["name"] == tr["name"]) >= tr["per_day"]: return False
        if x["strand"] and any(y["strand"] == x["strand"] for y in day): return False   # variety: one per strand per day
        return True
    for i, d in enumerate(horizon):
        days_left = len(horizon) - i
        for passno in (-1, 0, 1, 2):                  # pass -1: GATES first (11/10); pass 0: a letter every day (parent: "letters every time")
            left = sum(1 for x in Q if x["kind"] == "letter" and (x["title"], x["level"]) not in placed)
            # parent 10/12: no letter cap when letters are what's left. Pass 2 lets letters fill any slot nothing better claimed.
            quota = MIN_LETTERS_PER_DAY if passno == 0 else LETTER_SLOTS if passno == 1 else DAILY
            for x in Q:
                if passno == -1 and x["kind"] != "gate": continue
                if passno == 0 and x["kind"] != "letter": continue
                if fits(d, x, quota):
                    days[d].append(x); placed.add((x["title"], x["level"]))
                    pv = by_title.get(x.get("pair") or "")
                    if pv and len(days[d]) < cap(d) and (pv["title"], "Main") not in placed:   # the letter's own lesson, same day
                        days[d].append({"title": pv["title"], "level": "Main", "subject": pv["subject"], "kind": "pair", "strand": None,
                                        "why": f"taught again with its sound check ({x['title']})"})
                        placed.add((pv["title"], "Main"))
                    if x["family"]: families_used.add(x["family"])
                    if x["kind"] == "letter": letter_day[x["letter"]] = d
        if len(days[d]) < cap(d):
            notes.append(f"{d}: {len(days[d])} lessons - the rest of the appropriate work waits on earlier results or holds")
        days[d] = [{"title": x["title"], "level": x["level"], "subject": x["subject"], "why": x["why"]} for x in days[d]]
    for t, sk, name in probe_items:
        if (t, "Main") not in placed: notes.append(f"probe not placed: {t}")

    # ---- 6. which grades to read: the next grade opens for reading when any strand at the top grade is exhausted -----
    nxt = set(state.get("scan_keys", ["ELA", "Math", "Logic+", "ELA4", "Math4", "Logic+4"]))
    for base in ("ELA", "Math", "Logic+"):
        top = max((base_grade(k[0])[1] for k in les if base_grade(k[0])[0] == base), default=3)
        done_strands = [sk for sk, ws in strands.items() if base_grade(sk[0]) == (base, top)
                        and any(proven(w) for w in ws if is_skill(w))
                        and all(w["status"] == "viewed" or proven(w) for w in ws if is_skill(w))]
        if done_strands and top < 7:
            try: nxt.add(kk.key_for(base, top + 1)); notes.append(f"reading {kk.key_for(base, top + 1)} next: {base} strand(s) exhausted at grade {top}: {[s[1] for s in done_strands][:4]}")
            except KeyError: pass
    plan.scan_keys = sorted(k for k in nxt if k in kk.REPORTS)
    plan.held = held; plan.notes = notes
    return days, les, retries
