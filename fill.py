#!/usr/bin/env python3
"""Resilient filler: creates assignments from a subject-tagged TSV, date-major so the dialog's remembered
date is reused, and restarts WDA + re-enters the teacher view if the connection dies.
usage: python3 fill.py PLAN.tsv LOG"""
import sys, os, time, subprocess, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.argv = [sys.argv[0], "none"] + sys.argv[1:]
import kk
ST = 'type == "XCUIElementTypeStaticText" AND '
D = os.path.dirname(os.path.abspath(__file__))

def alive():
    try: return kk._req("/status")["value"].get("ready") is True
    except Exception: return False

def where():
    """'report' | 'teacher' | 'settings' | 'picker' | 'student' | 'unknown' — without touching the app."""
    try:
        if kk.q(ST + '(label BEGINSWITH "Class Report")'): return "report"
        if kk.q('name CONTAINS "ClassReport"'): return "teacher"
        if kk.q(ST + kk.lbl("Teacher Settings")): return "settings"
        if kk.q(ST + kk.lbl("Sign Out")) and kk.q(ST + kk.lbl(kk.TEACHER_NAME)): return "picker"
        if kk.q('name CONTAINS "SiteMap"') or kk.q('name CONTAINS "Library"'): return "student"
    except Exception: pass
    return "unknown"

def enter_teacher():
    """Reach the Students page of the teacher view WITHOUT relaunching the app unless unavoidable.
    Signs in (Google prompt) only when coming from the profile picker."""
    if not kk.TEACHER_NAME: raise RuntimeError("set KK_TEACHER_NAME in local.env (see local.env.example)")
    w = where()
    if w == "teacher": return
    if w in ("report", "settings"):
        b = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "sandbox_back_btn"')
        if b: kk.click(b); time.sleep(2)
        if where() == "teacher": return
    if w == "student" or where() == "unknown":
        # the student's profile (or something unexpected): the only way to the picker is a relaunch
        kk._req(f"/session/{kk.SID}/wda/apps/terminate", {"bundleId": "org.khanacademy.Khan-Kids"}); time.sleep(2)
        kk._req(f"/session/{kk.SID}/wda/apps/launch", {"bundleId": "org.khanacademy.Khan-Kids"}); time.sleep(6)
    d = kk.wait_for(ST + kk.lbl(kk.TEACHER_NAME), 10)
    if not d: raise RuntimeError("profile picker not found")
    kk.click(d); time.sleep(2.5)
    gate = [e[1] for e in kk.texts() if "Swipe" in e[1]]
    g = gate[0].upper() if gate else "LEFT"
    (rx, ry), (lx, ly), (ux, uy), (dx, dy) = kk.G["gate"]      # right end, left end, top, bottom of the gate swipe
    if "RIGHT" in g: kk.swipe(lx, ly, rx, ry, 0.4)
    elif "DOWN" in g: kk.swipe(ux, uy, dx, dy, 0.4)
    elif "UP" in g: kk.swipe(dx, dy, ux, uy, 0.4)
    else: kk.swipe(rx, ry, lx, ly, 0.4)
    time.sleep(3)
    try: kk._req(f"/session/{kk.SID}/alert/accept", {}); time.sleep(4)
    except Exception: pass
    for _ in range(14):
        if kk.q('name CONTAINS "ClassReport"'): break
        c = kk.q('type == "XCUIElementTypeButton" AND (label == "Continue" OR name == "Continue")')
        if c: kk.click(c); time.sleep(4); continue
        acct = kk.GOOGLE_ACCOUNT_MATCH.replace("\\", "\\\\").replace('"', '\\"')   # escaped for the NSPredicate string
        a = kk.q(f'label CONTAINS[c] "{acct}" AND NOT (label CONTAINS "Switch")') if acct else None
        if a: kk.click(a); time.sleep(3); continue
        time.sleep(1.5)
    if not kk.q('name CONTAINS "ClassReport"'): raise RuntimeError("could not reach teacher view")

def dismiss_modals():
    """Close a calendar / Assign dialog / picker left open by an interrupted run."""
    for _ in range(3):
        c = kk.q(ST + kk.lbl("Cancel"))
        if c: kk.click(c); time.sleep(0.4); continue
        if kk.q(kk.DIALOG):
            x = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
            if x: kk.click(x); time.sleep(0.6); continue
        d = kk.q(ST + kk.lbl("Done"))
        if d and kk.q(ST + '(label == "Select Students" OR label == "Select Grade & Subject")'): kk.click(d); time.sleep(0.6); continue
        break

def open_report(tab="All Progress"):
    """From anywhere in the teacher view, open Class Reports on the given tab (no sign-in if already inside)."""
    dismiss_modals()
    w = where()
    if w == "settings":
        b = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "sandbox_back_btn"')
        if b: kk.click(b); time.sleep(2); w = where()
    if w not in ("report", "teacher"): enter_teacher(); w = where()
    if w != "report":
        kk.click(kk.q('name CONTAINS "ClassReport"')); kk.wait_for(ST + kk.lbl("All Progress"), 6); time.sleep(0.5)
        x = kk.q('name CONTAINS "close"')
        if x and kk.rect(x)["y"] < 80: kk.click(x); time.sleep(0.5)
    for _ in range(4):
        if kk.q(ST + kk.lbl("Class Report: " + tab)): return
        kk.goto_tab(tab); time.sleep(1.0)

def finish():
    """End of a check-in: back to the profile picker via the app's own Switch User button (no relaunch).
    On the parent's iPhone it stops at the teacher home instead (a personal phone; the next run then needs no sign-in)."""
    if where() in ("report", "settings"):
        b = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "sandbox_back_btn"')
        if b: kk.click(b); time.sleep(2)
    if kk.IPHONE: return where()
    su = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "switchuser"')
    if su: kk.click(su); time.sleep(2)
    return where()

def on_report():
    """On Class Report > All Progress? One predicate query, no tree dump."""
    return kk.q(ST + 'label == "Class Report: All Progress"') is not None

def ensure(subject):
    kk.wait_unlocked()
    if alive():
        if on_report(): return False
        open_report("All Progress"); kk.set_subject(subject); return True
    print("WDA down -> restarting", flush=True)
    subprocess.run([kk.START], env={**os.environ, "SCRATCH": kk.SESS}, check=True, capture_output=True)
    kk.SID = open(f"{kk.SESS}/sid").read().strip()
    open_report("All Progress"); kk.set_subject(subject)
    return True

def main_ordered(path, log):
    """One pass per report subject, rows already sorted by their position in that subject's list, so find_el only ever
    scrolls DOWN a little. Creates new assignments and re-dates existing ones (pre-checked dialog) in the same pass.
    Returns {(title, level, m, d): result}."""
    plan = [l.rstrip("\n").split("\t") for l in open(path) if l.strip() and not l.startswith("#")]
    done = set()
    if os.path.exists(log):
        for l in open(log):
            f = l.rstrip("\n").split("\t")
            if f[0] in ("created", "redated"): done.add(tuple(f[1:5]))
    cur = None; state = {"date": None}; results = {}
    with open(log, "a") as out:
        for subj, title, level, m, d in plan:
            if (title, level, m, d) in done: results[(title, level, m, d)] = "done before"; continue
            t0 = time.time(); res = None
            for attempt in (1, 2):
                try:
                    if ensure(subj): cur = subj
                    if cur != subj:
                        kk.set_subject(subj); cur = subj; kk.scroll_top()
                    res = kk.fast_create2(title, level, int(m), int(d), state)
                except Exception as ex:
                    res = f"error {ex!r}"; time.sleep(1)
                if res in ("created", "redated") or res.startswith("level"): break
                try:
                    x = kk.q(ST + kk.lbl("Cancel"))
                    if x: kk.click(x); time.sleep(0.3)
                    if kk.q(kk.DIALOG):
                        c = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
                        if c: kk.click(c); time.sleep(0.5)
                except Exception: time.sleep(1)
            results[(title, level, m, d)] = res
            out.write(f"{res}\t{title}\t{level}\t{m}\t{d}\n"); out.flush()
            print(f"{res:<12} {title} {level} {m}/{d}  ({time.time()-t0:.1f}s)", flush=True)
    return results

def main(path, log):
    plan = [l.rstrip("\n").split("\t") for l in open(path) if l.strip() and not l.startswith("#")]
    done = set()
    if os.path.exists(log):
        for l in open(log):
            if l.startswith("created"): done.add(tuple(l.split("\t")[1:3]))
    with open(log, "a") as out:
        for subj in kk.REPORTS:
            items = [r for r in plan if r[0] == subj and (r[1], r[2]) not in done]
            if not items: continue
            items.sort(key=lambda r: (int(r[3]), int(r[4]), kk.ORDER.get(r[1], 9999)))
            ensure(subj); kk.set_subject(subj); state = {"date": None}
            for _ in range(8): kk.swipe(230, 250, 230, 750, 0.4)
            for _, title, level, m, d in items:
                t0 = time.time(); res = None
                for attempt in (1, 2):
                    try:
                        if ensure(subj): state["date"] = None
                        res = kk.fast_create2(title, level, int(m), int(d), state); break
                    except Exception as ex:
                        res = f"error {ex!r}"; time.sleep(2)
                if res != "created":
                    try:
                        x = kk.q(ST + kk.lbl("Cancel"))
                        if x: kk.click(x); time.sleep(0.3)
                        if kk.q(kk.DIALOG):
                            c = kk.q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
                            if c: kk.click(c); time.sleep(0.5)
                    except Exception: pass
                    state["date"] = None
                out.write(f"{res}\t{title}\t{level}\t{m}\t{d}\n"); out.flush()
                print(f"{res:<12} {title} {level} {m}/{d}  ({time.time()-t0:.1f}s)", flush=True)

if __name__ == "__main__": main(sys.argv[2], sys.argv[3])
