#!/usr/bin/env python3
"""Khan Kids teacher-view driver over WebDriverAgent.

Reads the app's accessibility tree (window-relative 1180x820 coords) and converts to
screen points via the Stage-Manager window transform measured on 2026-09-07.

Usage:
  kk.py rows                 # list assignment rows (title, level, date) from the Assignments report
  kk.py fixdates PLAN.tsv    # PLAN: title<TAB>level<TAB>M<TAB>D per line; edits each assignment's date
"""
import json, subprocess, sys, time, urllib.request, datetime, os

D = os.path.dirname(os.path.abspath(__file__))           # repo root
def _load_local_env(path=os.path.join(D, "local.env")):
    """Personal settings (device ids, signing, account names) live in the gitignored local.env; the environment wins."""
    if not os.path.exists(path): return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_local_env()
TEACHER_NAME = os.environ.get("KK_TEACHER_NAME", "")             # teacher profile name on the app's profile picker
GOOGLE_ACCOUNT_MATCH = os.environ.get("KK_GOOGLE_ACCOUNT_MATCH", "")   # identifies the Google account in the sign-in sheet

# KK_DEVICE=iphone drives an iPhone signed in to the teacher view (tunnel 8101, session dir .session-iphone)
DEVICE = os.environ.get("KK_DEVICE", "ipad")
IPHONE = DEVICE == "iphone"
SESS = os.path.join(D, ".session-iphone" if IPHONE else ".session")
START = os.path.join(D, "start-wda-iphone.sh" if IPHONE else "start-wda.sh")
_wu = f"{SESS}/wda_url"                                   # the iPhone start script writes USB (localhost:8101) or Wi-Fi (http://<ip>:8100)
WDA = os.environ.get("WDA_URL") or (open(_wu).read().strip() if IPHONE and os.path.exists(_wu) else
                                     "http://localhost:8101" if IPHONE else "http://localhost:8100")   # iPad Wi-Fi fallback: WDA_URL=http://<ip>:8100
SID = open(f"{SESS}/sid").read().strip()
# window origin + scale (screen = O + SC*tree). Fullscreen = "0 0 1"; Stage-Manager window seen 2026-09-07 = "83 57 0.86".
_xf = f"{SESS}/xform"
OX, OY, SC = (map(float, open(_xf).read().split()) if os.path.exists(_xf) else (0, 0, 1))
TODAY = datetime.date.today()

# Tree-coordinate geometry per device (iPad measured 9/7-10/25; iPhone 956x440 landscape measured 11/3). Everything that
# used to be a fixed number lives here, so both devices share one code path.
G = dict(
    ipad=dict(row_title_x=120, row_top=213, row_bot=815, row_date_dy=(15, 26), row_lv_x=(0, 60), row_lv_dy=(24, 32),
              row_score_x=280, row_score_dy=(20, 26), row_check_dy=(15, 30), thumb=(75, 17), row_tap=(0, 790),
              cat_x=84, title_x=102, score_x=293, list_top=215, list_bot=800, vis_lo=225, vis_hi=690,
              drag_x=230, page=(760, 420), nudge=200, fling=(260, 790), hdr_y=170, subj_pen=(140, 170),
              dlg_date_y=(250, 330), dlg_pen_y=(250, 320), student_box_y=300, dlg_save_y=200,
              cal_hdr_y=230, cal_left_x=(50, 650), cal_cells_x=(300, 850), cal_right_cells_x=(850, 1420), cal_cell_y=280, cal_save_y=500,
              gate=((730, 420), (450, 420), (590, 300), (590, 560))),
    iphone=dict(row_title_x=112, row_top=140, row_bot=10000, row_date_dy=(10, 18), row_lv_x=(60, 80), row_lv_dy=(16, 23),
              row_score_x=200, row_score_dy=(15, 8), row_check_dy=(0, 10), thumb=(84, 10), row_tap=(150, 395),
              cat_x=88, title_x=99, score_x=238, list_top=150, list_bot=10000, vis_lo=160, vis_hi=400,
              drag_x=150, page=(410, 190), nudge=120, fling=(170, 420), hdr_y=125, subj_pen=(95, 120),
              dlg_date_y=(160, 200), dlg_pen_y=(160, 200), student_box_y=195, dlg_save_y=100,
              cal_hdr_y=80, cal_left_x=(250, 684), cal_cells_x=(260, 684), cal_right_cells_x=(684, 1100), cal_cell_y=110, cal_save_y=330,
              gate=((600, 220), (360, 220), (478, 120), (478, 330))),
)[DEVICE]

def _req(path, data=None):
    r = urllib.request.Request(WDA + path, data=json.dumps(data).encode() if data is not None else None,
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=12))

def locked():
    try: return bool(_req("/wda/locked")["value"])
    except Exception: return False
def wait_unlocked(max_min=60):
    """The iPad auto-locked: wait (do not hammer it) until someone unlocks it. Returns False if it never happens."""
    if not locked(): return True
    print("   [iPad is locked - waiting for it to be unlocked]", flush=True)
    for _ in range(max_min * 6):
        time.sleep(10)
        if not locked(): print("   [unlocked, continuing]", flush=True); time.sleep(2); return True
    return False

def tap(x, y):  _req(f"/session/{SID}/wda/tap", {"x": x, "y": y})
def tap_tree(x, y): tap(OX + SC * x, OY + SC * y)
def swipe(x1, y1, x2, y2, d=0.3):
    _req(f"/session/{SID}/wda/dragfromtoforduration", {"fromX": x1, "fromY": y1, "toX": x2, "toY": y2, "duration": d})

def tree():
    d = _req(f"/session/{SID}/source?format=json")["value"]
    out = []
    def walk(n):
        t = n.get("type", ""); l = (n.get("label") or n.get("name") or "").split("/")[-1]
        r = n.get("rect", {})
        out.append((t, l, r.get("x", 0), r.get("y", 0), r.get("width", 0), r.get("height", 0)))
        for c in n.get("children", []): walk(c)
    walk(d); return out

def rows(t=None):
    """Assignment rows: [(title, level, date, y_tree)] in the list (between G row_top and row_bot)."""
    t = t or tree()
    texts = [e for e in t if e[0] == "StaticText"]
    lx0, lx1 = G["row_lv_x"]; dy0, dy1 = G["row_date_dy"]; ly0, ly1 = G["row_lv_dy"]; tx = G["row_title_x"]
    levels = {round(e[3]): e[1] for e in texts if lx0 <= e[2] < lx1 and e[1] in ("Main", "Practice 1", "Practice 2", "Basic")}
    out = []
    for e in texts:
        if e[2] == tx and G["row_top"] <= e[3] < G["row_bot"] and e[1] not in ("", "Today", "Tomorrow", "Yesterday") and not e[1].startswith(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            title, y = e[1], e[3]
            date = next((d[1] for d in texts if d[2] == tx and dy0 <= d[3] - y <= dy1), "?")
            level = next((lv for ly, lv in levels.items() if ly0 <= ly - y <= ly1), "?")
            out.append((title, level, date, y))
    return out

def dialog_open(t=None):
    t = t or tree()
    return any(e[0] == "StaticText" and e[1] == "Select All" for e in t)

def datestr(m, d):
    dt = datetime.date(2026, m, d)
    if dt == TODAY: return "Today"
    if dt == TODAY + datetime.timedelta(days=1): return "Tomorrow"
    return f"{dt.strftime('%a')}., {dt.strftime('%b')}. {d:2d}"

def _tap_el(e): tap_tree(e[2] + e[4] / 2, e[3] + e[5] / 2)

def _cal_left_month():
    """Return the month index shown in the LEFT calendar pane, or None."""
    MON={'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,'July':7,'August':8,'September':9,'October':10,'November':11,'December':12}
    for e in texts():
        if e[3] < G["cal_hdr_y"] and e[1].split(' ')[0] in MON and G["cal_left_x"][0] < e[2] < G["cal_left_x"][1]:
            return MON[e[1].split(' ')[0]]
    return None

def _month_pane(m):
    """'left' / 'right' if month m's header is on screen, else None (position filtered inside the predicate)."""
    base = 'type == "XCUIElementTypeStaticText" AND rect.y < %d AND label BEGINSWITH "%s " AND ' % (G["cal_hdr_y"], MONTH_NAMES[m])
    if q(base + 'rect.x > %d AND rect.x < %d' % G["cal_left_x"]): return "left"
    if q(base + 'rect.x >= %d' % G["cal_left_x"][1]): return "right"
    return None
def pick_date(m, d):
    """Calendar open (two month panes). Use whichever pane shows month m; step the left pane if needed.
    Never guesses: raises if month m is not on screen (a wrong date is worse than a failed create)."""
    pane = _month_pane(m)
    if pane == "right":                       # right-pane taps don't always register (Nov 1, 10/25): bring the month to the LEFT pane
        nx = sorted(q('type == "XCUIElementTypeImage" AND name CONTAINS "onboarding_avatar_next_btn"', many=True), key=lambda i: rect(i)['x'])
        if nx: click(nx[0]); time.sleep(0.6); pane = _month_pane(m)
    if pane == "left":
        xmin, xmax = G["cal_cells_x"]
        cell = q('type == "XCUIElementTypeStaticText" AND %s AND rect.x > %d AND rect.x < %d AND rect.y > %d' % (lbl("%02d" % d), xmin, xmax, G["cal_cell_y"]))
        if cell:
            click(cell); time.sleep(0.2)
            sv = q('type == "XCUIElementTypeStaticText" AND %s AND rect.y > %d' % (lbl("Save"), G["cal_save_y"]))
            click(sv); time.sleep(0.3); return
    lm = None
    for _ in range(8):
        lm = _cal_left_month()
        if lm is None: time.sleep(0.4); continue
        if lm == m or lm % 12 + 1 == m: break
        name = "onboarding_avatar_next_btn" if (m - lm) % 12 <= 6 else "onboarding_avatar_back_btn"   # step the LEFT pane toward m
        arrows = sorted(q('type == "XCUIElementTypeImage" AND name CONTAINS "%s"' % name, many=True), key=lambda i: rect(i)['x'])
        if not arrows: break
        click(arrows[0]); time.sleep(0.5)
    if lm == m: xmin, xmax = G["cal_cells_x"]            # left pane (iPad: day columns at x 317..781)
    elif lm is not None and lm % 12 + 1 == m: xmin, xmax = G["cal_right_cells_x"]   # right pane (iPad: x 872..1337; off-screen on the iPhone)
    else: raise RuntimeError(f"month {m} not on screen (left month={lm})")
    cells=[i for i, r in ((i, rect(i)) for i in q('type == "XCUIElementTypeStaticText" AND ' + lbl("%02d" % d), many=True)) if xmin < r['x'] < xmax and r['y']>G["cal_cell_y"]]
    if not cells: raise RuntimeError(f"day {m}/{d} not found (left month={lm})")
    click(cells[0]); time.sleep(0.2)
    sv=[i for i in q('type == "XCUIElementTypeStaticText" AND ' + lbl("Save"), many=True) if rect(i)['y']>G["cal_save_y"]]
    click(sv[0]); time.sleep(0.4)

def date_ok(text, m, d):
    """Does the dialog's 'Date: ...' text mean month m, day d?"""
    dt = datetime.date(TODAY.year, m, d); t = text.replace(".", " ").replace(",", " ").split()
    if "Today" in t: return dt == TODAY
    if "Tomorrow" in t: return dt == TODAY + datetime.timedelta(days=1)
    return dt.strftime("%b") in t and str(d) in t

MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
def _date_texts(m, d):
    dt = datetime.date(TODAY.year, m, d); mon = dt.strftime("%b")
    out = [f"{mon}. {d}", f"{mon}.  {d}"]
    if dt == TODAY: out.append("Today")
    if dt == TODAY + datetime.timedelta(days=1): out.append("Tomorrow")
    return out
def dialog_date_ok(m, d, explain=False):
    """One predicate query: is the target date shown on the dialog's date line (y 250-330, right of the list column)?
    The slow tree read only runs when explain=True, to report what IS shown."""
    pred = ('type == "XCUIElementTypeStaticText" AND rect.y > %d AND rect.y < %d AND rect.x > 140 AND (' % G["dlg_date_y"]
            + " OR ".join(f'label ENDSWITH "{t}"' for t in _date_texts(m, d)) + ')')
    if q(pred): return True, " / ".join(_date_texts(m, d))
    return dialog_date_ok_slow(m, d) if explain else (False, None)
def dialog_date_ok_slow(m, d):
    """Read the date shown beside the pencil in the open assign/edit dialog ('Date: Today' or just 'Today') and check it."""
    t = tree(); pens = [e for e in t if e[0] == "Image" and e[1].startswith("edit_avatar_btn") and G["dlg_pen_y"][0] < e[3] < G["dlg_pen_y"][1]]
    if not pens: return False, "no pencil"
    px, py = pens[-1][2], pens[-1][3]
    near = [e[1] for e in t if e[0] == "StaticText" and abs(e[3] - py) < 9 and 100 < e[2] < px and e[1].strip()]
    if not near: return False, "no date text"
    return date_ok(near[-1], m, d), near[-1]

def set_date_in_dialog(m, d):
    t = tree()
    pencil = [e for e in t if e[1].startswith("edit_avatar_btn") and G["dlg_pen_y"][0] < e[3] < G["dlg_pen_y"][1]]
    if not pencil: raise RuntimeError("pencil not found in dialog")
    e = pencil[0]; tap_tree(e[2] + e[4] / 2, e[3] + e[5] / 2); time.sleep(1.3)
    pick_date(m, d)
    save = [e for e in t if e[0] == "StaticText" and e[1] == "Save" and e[3] < G["dlg_save_y"]]
    e = save[0]; tap_tree(e[2] + e[4] / 2, e[3] + e[5] / 2); time.sleep(2.0)

def find_row(title, level, tries=14):
    """Scroll the Assignments list until the row is visible; return (row, tree)."""
    last = None
    for i in range(tries):
        t = tree(); rs = rows(t)
        for r in rs:
            if r[0] == title and (level == "*" or r[1] == level) and r[3] < 800:
                return r, t
        sig = tuple(r[0] for r in rs)       # compare titles, not y positions (y can repeat after a scroll)
        if sig == last:                     # no movement: at end -> go to top
            swipe(230, 250, 230, 750, 0.6); swipe(230, 250, 230, 750, 0.6); swipe(230, 250, 230, 750, 0.6); time.sleep(1.2)
            last = None; continue
        last = sig
        swipe(230, 640, 230, 340, 1.2); time.sleep(1.0)
    return None, None

def scan():
    """Scroll from top to bottom and return every (title, level, date) in the Assignments list."""
    for _ in range(4): swipe(230, 250, 230, 750, 0.6)
    time.sleep(1.2); seen = []; last = None
    for _ in range(25):
        rs = rows()
        for r in rs:
            key = (r[0], r[1], r[2])
            if key not in seen: seen.append(key)
        sig = tuple(r[0] for r in rs)
        if sig == last: break
        last = sig; swipe(230, 640, 230, 340, 1.2); time.sleep(1.0)
    for r in rows():
        if (r[0], r[1], r[2]) not in seen: seen.append((r[0], r[1], r[2]))
    return seen

def texts(t=None):
    return [e for e in (t or tree()) if e[0] == "StaticText"]

def goto_tab(name):
    """Class Report tab: 'Assignments' or 'All Progress'."""
    e = [e for e in texts() if e[1] == name and e[3] < 130][-1]; _tap_el(e); time.sleep(2.5)

REPORTS = {   # report key -> (grade label, subject label) in the All Progress Grade/Subject picker
    "ELA": ("Preschool (Age 3)", "English Language Arts"), "Math": ("Preschool (Age 3)", "Math"), "Logic+": ("Preschool (Age 3)", "Logic+"),
    "ELA4": ("Preschool (Age 4)", "English Language Arts"), "Math4": ("Preschool (Age 4)", "Math"), "Logic+4": ("Preschool (Age 4)", "Logic+"),
    "ELAK": ("Kindergarten", "English Language Arts"), "MathK": ("Kindergarten", "Math"), "Logic+K": ("Kindergarten", "Logic+"),
    "ELA1": ("1st Grade", "English Language Arts"), "Math1": ("1st Grade", "Math"),
    "ELA2": ("2nd Grade", "English Language Arts"), "Math2": ("2nd Grade", "Math"),
}
GRADE_OF = {"": 3, "4": 4, "K": 5, "1": 6, "2": 7}      # report-key suffix -> grade rank (Age 3 = 3 ... 2nd grade = 7)
def split_key(key):
    base = "Logic+" if key.startswith("Logic+") else "ELA" if key.startswith("ELA") else "Math"
    return base, GRADE_OF[key[len(base):]]
def key_for(base, grade): return base + {v: k for k, v in GRADE_OF.items()}[grade]
def report_header():
    return next((e[1] for e in texts() if e[3] < G["hdr_y"] and e[1].startswith("Pre-K")), "")
def set_subject(name):
    """All Progress report: pick grade + subject by element (no fixed coordinates). name is a REPORTS key."""
    grade, subj = REPORTS[name]
    ST = 'type == "XCUIElementTypeStaticText" AND '
    pen = [e for e in tree() if e[1].startswith("edit_avatar_btn") and G["subj_pen"][0] < e[3] < G["subj_pen"][1]][0]; _tap_el(pen)
    if not wait_for(ST + lbl("Grade"), 4): raise RuntimeError("grade/subject picker did not open")
    for label in (grade, subj):
        e = q(ST + lbl(label))
        if not e: raise RuntimeError(f"picker option {label!r} not found")
        click(e); time.sleep(0.4)
    t = tree()
    for label in (grade, subj):
        ly = next(e[3] for e in t if e[0] == "StaticText" and e[1] == label)
        on = [e for e in t if e[0] == "Image" and "onboarding_toggle2" in e[1] and abs(e[3] - ly) < 12]
        if not on: raise RuntimeError(f"picker option {label!r} did not select")
    click(q(ST + lbl("Done"))); time.sleep(3)

def find_text(title, tries=14):
    """Scroll the All Progress list until a StaticText == title is visible; return element."""
    last = None
    for _ in range(tries):
        t = tree(); hits = [e for e in t if e[0] == "StaticText" and e[1] == title and 215 < e[3] < 790]
        if hits: return hits[0]
        sig = tuple(e[3] for e in t if e[0] == "StaticText" and e[3] > 215)[:6]
        if sig == last:
            for _ in range(5): swipe(230, 250, 230, 750, 0.6)
            time.sleep(1.2); last = None; continue
        last = sig; swipe(230, 640, 230, 340, 1.2); time.sleep(1.0)
    return None

def createmany(path, log):
    """PLAN rows: subject, title, level, M, D. Groups by subject; appends results to log."""
    plan = [l.rstrip("\n").split("\t") for l in open(path) if l.strip() and not l.startswith("#")]
    done = set()
    if os.path.exists(log):
        for l in open(log):
            if l.startswith("created"): done.add(tuple(l.split("\t")[1:4]))
    with open(log, "a") as out:
        for subj in ("ELA", "Math"):
            items = [r for r in plan if r[0] == subj and tuple(r[1:4]) not in done]
            if not items: continue
            set_subject(subj)
            for _, title, level, m, d in items:
                try: res = create(title, level, int(m), int(d))
                except Exception as ex: res = f"error {ex!r}"
                if res != "created" and dialog_open():          # leave a clean state
                    x = [e for e in tree() if e[1].startswith("leaf_hintvideo_close_btn")]
                    if x: _tap_el(x[0]); time.sleep(1)
                out.write(f"{res}\t{title}\t{level}\t{m}\t{d}\n"); out.flush(); print(res, title, level, m, d)

def create(title, level, m, d):
    """From All Progress (subject already set): assign title@level to the student on m/d."""
    e = find_text(title, tries=30)
    if not e: return "row not found"
    _tap_el(e); time.sleep(1.2)                       # single lessons open the dialog; groups expand
    if not dialog_open():
        lv = [x for x in texts() if x[1] == level and 0 < x[3] - e[3] < 130 and x[2] > e[2] - 5]
        if not lv:                                    # maybe it was expanded and we collapsed it: tap again
            _tap_el(e); time.sleep(1.2)
            lv = [x for x in texts() if x[1] == level and 0 < x[3] - e[3] < 130 and x[2] > e[2] - 5]
        if not lv: return f"level {level} not found under {title}"
        _tap_el(lv[0]); time.sleep(2.2)
        if not dialog_open(): return "dialog did not open"
    t = tree()
    cb = [x for x in t if x[1].startswith("teacherlibrary_checkbox") and x[2] < 200 and x[3] > 300][0]; _tap_el(cb); time.sleep(0.6)
    set_date_in_dialog(m, d)
    return "created"

def fixdates(plan):
    ok, bad = [], []
    for title, level, m, d in plan:
        want = datestr(m, d)
        r, t = find_row(title, level)
        if not r: bad.append((title, level, "row not found")); print("MISSING", title, level); continue
        if r[2] == want: ok.append((title, level, want)); print("ok   ", title, level, want); continue
        tap_tree(75, r[3] + 17); time.sleep(2.2)          # thumbnail
        if not dialog_open(): time.sleep(1.5)
        if not dialog_open(): bad.append((title, level, "dialog did not open")); print("NODLG", title); continue
        set_date_in_dialog(m, d)
        r2, _ = find_row(title, level, tries=14)
        got = r2[2] if r2 else "?"
        if got == want: ok.append((title, level, want)); print("fixed", title, level, want)
        else: bad.append((title, level, f"got {got}")); print("WRONG", title, level, "wanted", want, "got", got)
    print(f"\n{len(ok)} ok, {len(bad)} problems"); [print("  ", b) for b in bad]

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "rows":
        for r in rows(): print(f"{r[3]:4.0f}  {r[1]:<11} {r[2]:<16} {r[0]}")
    elif cmd == "fixdates":
        plan = [l.rstrip("\n").split("\t") for l in open(sys.argv[2]) if l.strip() and not l.startswith("#")]
        fixdates([(a, b, int(c), int(d)) for a, b, c, d in plan])
    elif cmd == "taptext":            # tap a StaticText/Image by (substring of) label, optional index
        q = sys.argv[2]; i = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        hits = [e for e in tree() if q.lower() in e[1].lower() and e[0] in ("StaticText", "Image", "Button")]
        if not hits: print("NOT FOUND", q); sys.exit(1)
        e = hits[i]; tap_tree(e[2] + e[4] / 2, e[3] + e[5] / 2); print("tapped", e)
    elif cmd == "scan":
        for t_, lv, dt in scan(): print(f"{lv:<11} {dt:<16} {t_}")
    elif cmd == "create":             # kk.py create SUBJECT "Title" LEVEL M D   (from Class Report > All Progress)
        subj, title, level, m, d = sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6])
        set_subject(subj); print(title, level, m, d, "->", create(title, level, m, d))
    elif cmd == "diff":               # kk.py diff PLAN.tsv  -> scan the list and compare to plan
        plan = [l.rstrip("\n").split("\t") for l in open(sys.argv[2]) if l.strip() and not l.startswith("#")]
        want = {(a, b): datestr(int(c), int(d)) for a, b, c, d in plan}
        have = {(a, b): c for a, b, c in scan()}
        for k in sorted(set(want) | set(have)):
            w, h = want.get(k), have.get(k)
            if w != h: print(f"{'MISSING' if h is None else 'EXTRA' if w is None else 'DATE'}  {k[0]} ({k[1]}): plan={w} app={h}")
        print(f"{sum(1 for k in want if have.get(k) == want[k])}/{len(want)} match")
    elif cmd == "createmany":         # kk.py createmany PLAN.tsv LOG   (from Class Report > All Progress)
        createmany(sys.argv[2], sys.argv[3])
    elif cmd == "tree":
        for e in tree():
            if e[1] and e[0] != "Other": print(e)

# ---------------------------------------------------------------------------------------------
# FAST PATH (2026-09-07): element queries + scrollToVisible + click by element id; no tree dumps,
# no coordinate transform, and the create dialog keeps the last-picked date so batch by date.
# ---------------------------------------------------------------------------------------------
def q(pred, many=False):
    """Find element(s) by NSPredicate on label/type. Returns id or list of ids ([] if none)."""
    body = {"using": "predicate string", "value": pred}
    try:
        r = _req(f"/session/{SID}/elements" if many else f"/session/{SID}/element", body)
    except Exception:
        return [] if many else None
    v = r.get("value")
    if many: return [x.get("ELEMENT") or x.get("element-6066-11e4-a52e-4f735466cecf") for x in (v or [])]
    if not v or "error" in v: return None
    return v.get("ELEMENT") or v.get("element-6066-11e4-a52e-4f735466cecf")

def lbl(s):
    s = s.replace('"', '\\"'); return '(label == "%s" OR name == "%s")' % (s, s)
def click(eid): _req(f"/session/{SID}/element/{eid}/click", {})
def rect(eid): return _req(f"/session/{SID}/element/{eid}/rect")["value"]
def show(eid): _req(f"/session/{SID}/wda/element/{eid}/scroll", {"toVisible": True})

def wait_for(pred, timeout=4.0, gone=False):
    t0 = time.time()
    while time.time() - t0 < timeout:
        e = q(pred)
        if (e is None) == gone: return e if not gone else True
        time.sleep(0.15)
    return None if not gone else False

DIALOG = 'type == "XCUIElementTypeStaticText" AND (label == "Select All" OR name == "Select All")'

def fast_create(title, level, m, d, state):
    """All Progress report. state = {'date': (m,d) currently remembered by the dialog or None}."""
    tid = q('type == "XCUIElementTypeStaticText" AND ' + lbl(title))
    if not tid: return "row not found"
    show(tid); time.sleep(0.3)
    click(tid)
    if not wait_for(DIALOG, 1.5):                      # it was a group: pick the level row under it
        ty = rect(tid)["y"]
        cands = [(rect(i), i) for i in q('type == "XCUIElementTypeStaticText" AND ' + lbl(level), many=True)]
        below = sorted([(r["y"] - ty, i) for r, i in cands if 0 < r["y"] - ty < 140])
        if not below:                                  # maybe we collapsed it; tap again
            click(tid); time.sleep(0.6)
            cands = [(rect(i), i) for i in q('type == "XCUIElementTypeStaticText" AND ' + lbl(level), many=True)]
            below = sorted([(r["y"] - ty, i) for r, i in cands if 0 < r["y"] - ty < 140])
        if not below: return f"level {level} not found"
        click(below[0][1])
        if not wait_for(DIALOG, 4): return "dialog did not open"
    cb = q('type == "XCUIElementTypeImage" AND name CONTAINS "teacherlibrary_checkbox"', many=True)
    cbs = sorted([(rect(i), i) for i in cb], key=lambda x: x[0]["y"])
    student = [i for r, i in cbs if r["x"] < 250 and r["y"] > 300]
    if not student: return "checkbox not found"
    click(student[0]); time.sleep(0.2)
    if state.get("date") != (m, d):
        pen = [i for i in q('type == "XCUIElementTypeImage" AND name CONTAINS "edit_avatar_btn"', many=True)
               if 250 < rect(i)["y"] < 320]
        if not pen: return "pencil not found"
        click(pen[0])
        if not wait_for('type == "XCUIElementTypeStaticText" AND ' + lbl("Cancel"), 3): return "calendar did not open"
        if m == 10:
            nxt = [i for i in q('type == "XCUIElementTypeImage" AND name CONTAINS "onboarding_avatar_next_btn"', many=True) if rect(i)["x"] < 870]
            click(nxt[0]); time.sleep(0.5)
        cells = [i for i in q('type == "XCUIElementTypeStaticText" AND ' + lbl("%02d" % d), many=True) if 300 < rect(i)["x"] < 870 and rect(i)["y"] > 280]
        if not cells: return "day cell not found"
        click(cells[0]); time.sleep(0.2)
        sv = [i for i in q('type == "XCUIElementTypeStaticText" AND ' + lbl("Save"), many=True) if rect(i)["y"] > 500]
        click(sv[0]); time.sleep(0.4)
        state["date"] = (m, d)
    sv = [i for i in q('type == "XCUIElementTypeStaticText" AND ' + lbl("Save"), many=True) if rect(i)["y"] < 200]
    click(sv[0])
    wait_for(DIALOG, 4, gone=True)
    return "created"

def fast_createmany(path, log):
    plan = [l.rstrip("\n").split("\t") for l in open(path) if l.strip() and not l.startswith("#")]
    done = set()
    if os.path.exists(log):
        for l in open(log):
            if l.startswith("created"): done.add(tuple(l.split("\t")[1:4]))
    state = {"date": None}
    with open(log, "a") as out:
        for subj in ("ELA", "Math"):
            items = [r for r in plan if r[0] == subj and tuple(r[1:4]) not in done]
            if not items: continue
            set_subject(subj); state["date"] = None
            items.sort(key=lambda r: (int(r[3]), int(r[4])))          # batch by date -> calendar once per day
            for _, title, level, m, d in items:
                t0 = time.time()
                try: res = fast_create(title, level, int(m), int(d), state)
                except Exception as ex: res = f"error {ex!r}"
                if res != "created":
                    x = q('type == "XCUIElementTypeStaticText" AND ' + lbl("Cancel"))
                    if x: click(x); time.sleep(0.3)
                    if q(DIALOG):
                        x = q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
                        if x: click(x); time.sleep(0.5)
                    state["date"] = None
                out.write(f"{res}\t{title}\t{level}\t{m}\t{d}\n"); out.flush()
                print(f"{res:<12} {title} {level} {m}/{d}  ({time.time()-t0:.1f}s)")

if __name__ == "__main__" and sys.argv[1] == "fastcreate":      # kk.py fastcreate PLAN.tsv LOG
    fast_createmany(sys.argv[2], sys.argv[3])

# Report order (Preschool Age 3, captured 2026-09-07) so a create pass scrolls the list once, top to bottom.
_ELA = (["Title & Author", "Book Pages", "Words on Signs 1", "Words on Signs 2", "Rhyming", "Hear Syllables", "Blend Syllables",
         "Blend Sounds 1", "Beginning Sounds 1", "Word Families", "Blend Sounds 2", "Beginning Sounds 2", "Words: End Sound"]
        + [f"Letter {c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [f"Lowercase {c}" for c in "abcdefghijklmnopqrstuvwxyz"]
        + [f"Uppercase {c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [f"Beginning Sound {c}" for c in "bcdfghjklmnpqrstvwyz"]
        + ["Draw Lines", "Draw Lines, Shapes", "Letters, Numbers", "Write Words", "Lines and Circles",
           "Farm Animals", "Vehicles", "Food", "Around the House", "Animals & Colors", "Weather", "Fruit", "Jungle Animals", "Kitchen", "Outdoors",
           "Opposites 1", "Opposites 2", "Opposites 3",
           "Mud", "Sad Ollo", "The Big Bed", "Reya's Bug", "What Is It?", "Jam in the Vat", "So Hot", "Hop Hop Hop", "The Cup Is Up",
           "Look At My Pen", "Look at It Go", "Come On", "Peck's Big Day", "Gum on the Rug", "Fun to Read", "The Big Fish", "The Box",
           "Race to the Lake", "A Nice Day", "Ollo's Bike", "Peck Plays a Tune", "Play Ball", "Something New", "Why", "Being Together", "Cool Beans",
           "Baby Dogs", "Baby Horses", "Baby Tigers", "Baby Ducks", "Baby Gorillas", "Kangaroos", "Baby Hippos", "Baby Pandas", "Baby Elephants",
           "Snakes", "Butterflies", "Baby Rabbits", "Baby Pigs", "Baby Cats",
           "Leaf Cutter Ants", "Seeds Grow", "Food for Fido", "Looking at Eggs", "Baby on Board", "Out at Night", "Animal Groups",
           "Walk with Camels", "Bird Beaks", "Beaver Builders", "Drip Drop", "On the Move", "Plates on My Plate", "Push Push Pull"])
_MATH = ["Count 1 & 2", "Tap & Count to 3", "Count 3 Objects", "Groups of 3", "Number Hunt 1-3", "Tap & Count to 4", "Count 4 Objects",
         "Tap & Count to 5", "Grouping: More", "Number Combos", "Last in Line", "Add Within 3", "Subtract Within 3", "Compare Sizes",
         "Measurement", "Primary Colors", "Secondary Colors", "Other Colors", "Patterns", "Positions", "Circle", "Square", "Triangle", "Rectangle"]
ORDER = {t: i for i, t in enumerate(_ELA)}; ORDER.update({t: i for i, t in enumerate(_MATH)})

def first_visible_title():
    """Signature of the visible LIST rows (labels of StaticTexts below the header), for scroll-movement detection."""
    try: return tuple(e[1] for e in texts() if e[3] > G["row_top"] and e[1].strip())[:6]
    except Exception: return ()

def _drag(x, y1, y2, ms, hold):
    """W3C touch drag: press, move over `ms`, hold `hold` ms before release (the hold kills fling momentum)."""
    _req(f"/session/{SID}/actions", {"actions": [{"type": "pointer", "id": "f1", "parameters": {"pointerType": "touch"}, "actions": [
        {"type": "pointerMove", "duration": 0, "x": x, "y": y1}, {"type": "pointerDown", "button": 0},
        {"type": "pointerMove", "duration": ms, "x": x, "y": y2}, {"type": "pause", "duration": hold}, {"type": "pointerUp", "button": 0}]}]})
def page_down():
    """Advance a report list ~17 rows with a 3-row overlap, so no row is ever skipped (measured 10/10: ~1.25 s vs 2.3 s swipe)."""
    _drag(G["drag_x"], G["page"][0], G["page"][1], 350, 200)
def page_up_fast():
    _drag(G["drag_x"], G["fling"][0], G["fling"][1], 120, 0)    # fling: momentum is fine when heading for the top

def settled(eid, tries=6):
    """Wait until an element stops moving (a list can still be settling after a drag; tapping then hits the NEIGHBOUR row).
    Returns its stable rect."""
    r = rect(eid)
    for _ in range(tries):
        time.sleep(0.25); r2 = rect(eid)
        if abs(r2["y"] - r["y"]) < 1: return r2
        r = r2
    return r

def find_el(title, max_drags=70):
    """Page down until the row renders (cheap predicate lookup per page); detect the list end only every 6th page."""
    pred = 'type == "XCUIElementTypeStaticText" AND rect.x > %d AND ' % (G["cat_x"] + 5) + lbl(title)   # lesson column only: a category can share its lesson's name ("Shapes")
    wrapped = False; last = None
    for i in range(max_drags):
        e = q(pred)
        if e:
            for _ in range(4):                          # bring it into the tappable band (the tree also holds off-screen rows)
                y = rect(e)["y"]; x0, n = G["drag_x"], G["nudge"]; mid = (G["vis_lo"] + G["vis_hi"]) // 2
                if y > G["vis_hi"]: _drag(x0, mid + n // 2, mid - n // 2, 300, 250)
                elif y < G["vis_lo"]: _drag(x0, mid - n // 2, mid + n // 2, 300, 250)
                else: break
                time.sleep(0.4); e = q(pred)
                if not e: break
            if e and G["vis_lo"] - 40 <= rect(e)["y"] <= G["vis_hi"] + 40: return e
        if i % 6 == 5:
            sig = first_visible_title()
            if sig and sig == last:                     # list end
                if wrapped: return None
                scroll_top(); wrapped = True; last = None; continue
            if sig: last = sig
        page_down(); time.sleep(0.3)
    return None

def scroll_top(max_rounds=15):
    """Fling up in threes until the visible rows stop changing."""
    last = None
    for _ in range(max_rounds):
        for _ in range(3): page_up_fast()
        time.sleep(0.5)
        sig = first_visible_title()
        if sig and sig == last: return
        last = sig

def find_el_old(title, max_scroll=90):
    """Scroll down until the row renders; wrap to top ONCE only if bottom reached without a match."""
    pred = 'type == "XCUIElementTypeStaticText" AND ' + lbl(title)
    wrapped = False; last = None
    for _ in range(max_scroll):
        e = q(pred)
        if e:
            y = rect(e)["y"]
            if y > 690:
                swipe(230, 600, 230, 380, 0.6); time.sleep(0.4); e = q(pred)
            return e
        sig = first_visible_title()
        if sig and sig == last:                      # no movement (ignore empty/failed reads) -> bottom
            if wrapped: return None
            scroll_top(); wrapped = True; last = None; continue
        if sig: last = sig
        swipe(230, 720, 230, 250, 0.7); time.sleep(0.5)
    return None

def dialog_is(title, level):
    """iPhone only: the Assign dialog shows 'Assign\n<title>' and the level under its thumbnail. True when both match
    (always True on the iPad, whose dialog shows neither)."""
    if not IPHONE: return True
    ST = 'type == "XCUIElementTypeStaticText" AND '
    heads = [_req(f"/session/{SID}/element/{h}/attribute/label")["value"] for h in q(ST + 'label BEGINSWITH "Assign" AND rect.y < 100', many=True)]
    t_ok = any(h.split()[:1] == ["Assign"] and " ".join(h.split()[1:]) == " ".join(title.split()) for h in heads)   # "Assign Shapes", not the "Assignments" tab
    l_ok = q(ST + lbl(level) + " AND rect.y < 100 AND rect.x > 140 AND rect.x < 240")
    return bool(t_ok and l_ok)
def close_dialog():
    x = q('type == "XCUIElementTypeStaticText" AND ' + lbl("Cancel"))
    if x: click(x); time.sleep(0.3)
    c = q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
    if c: click(c); wait_for(DIALOG, 3, gone=True)

def fast_create2(title, level, m, d, state):
    """Reliable element-order path (~12 s/lesson). find row -> open dialog -> the student -> date (once/day) -> Save."""
    ST = 'type == "XCUIElementTypeStaticText" AND '
    tid = find_el(title)
    if not tid: return "row not found"
    r0 = settled(tid); ty = r0["y"]
    tap(r0["x"] + 40, r0["y"] + r0["height"] // 2); time.sleep(0.3)     # tap the settled label itself
    if IPHONE and not q(DIALOG):                        # the phone's list scrolls to show an opened group: re-measure the title
        t2 = q(ST + "rect.x > %d AND " % (G["cat_x"] + 5) + lbl(title))
        if t2: tid = t2; r0 = settled(t2); ty = r0["y"]
    has_levels = q(ST + lbl(level) + " AND rect.y > %d AND rect.y < %d" % (ty, ty + 140))   # level rows directly UNDER this title
    if not q(DIALOG) and not has_levels:                # leaf row inside an expanded group (e.g. "Letter H"): tap the label itself, up to 3x
        for _ in range(3):
            tap(r0["x"] + 60, r0["y"] + r0["height"] // 2); time.sleep(1.2)
            if q(DIALOG): break
    if not q(DIALOG):                                   # group row: tap the level row just under the title
        lv_pred = ST + lbl(level) + " AND rect.y > %d AND rect.y < %d" % (ty, ty + 140)
        lv = q(lv_pred)
        if not lv:
            click(tid); time.sleep(0.5); lv = q(lv_pred)
        if not lv: return f"level {level} not found"
        if IPHONE and settled(lv)["y"] > G["vis_hi"]:   # the phone's short screen: the level row can sit below the bottom edge
            mid = (G["vis_lo"] + G["vis_hi"]) // 2; _drag(G["drag_x"], mid + 60, mid - 80, 300, 250); time.sleep(0.4)
            t3 = q(ST + "rect.x > %d AND " % (G["cat_x"] + 5) + lbl(title))
            if not t3: return f"level {level} not found"
            ty = settled(t3)["y"]; lv = q(ST + lbl(level) + " AND rect.y > %d AND rect.y < %d" % (ty, ty + 140))
            if not lv: return f"level {level} not found"
        ly = rect(lv)["y"]                              # it must be OUR level row: no other lesson title in between
        if q(ST + 'rect.x > 95 AND rect.x < 130 AND rect.y > %d AND rect.y < %d AND NOT (label IN {"Main", "Practice 1", "Practice 2", "Basic"})' % (ty + 5, ly - 5)):
            return f"level {level} not found"
        if IPHONE: lr = settled(lv); tap(lr["x"] + 40, lr["y"] + lr["height"] / 2)   # an element click on the phone scrolls instead; wait out the list's own scroll
        else: click(lv)
        if not wait_for(DIALOG, 4): return "dialog did not open"
    if not dialog_is(title, level): close_dialog(); return "wrong dialog"      # never touch another lesson's assignment
    def student_box(name):
        e = q('type == "XCUIElementTypeImage" AND name CONTAINS "%s" AND rect.x < 250 AND rect.y > %d' % (name, G["student_box_y"]))
        return [e] if e else []
    if student_box("teacherlibrary_checkbox2"):            # already assigned at this level (one assignment per lesson+level):
        ok, shown = dialog_date_ok(m, d)                # the dialog is THEIR assignment -> change its date in place
        if ok:
            x = q(ST + lbl("Cancel"))
            if x: click(x)
            else:
                c = q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
                if c: click(c)
            wait_for(DIALOG, 3, gone=True); return "redated"
        state["date"] = None                            # its own date is showing, not the remembered one
        existing = True
    else:
        existing = False
        student = student_box("teacherlibrary_checkbox")
        if not student: return "checkbox not found"
        click(student[0]); time.sleep(0.3)
    checked = student_box("teacherlibrary_checkbox2")
    if not existing and not checked: return "checkbox did not check"   # element ids go stale when the image swaps, so re-query
    if not dialog_date_ok(m, d)[0]:                     # read the date the dialog shows; only open the calendar when it is wrong
        pen = q('type == "XCUIElementTypeImage" AND name CONTAINS "edit_avatar_btn" AND rect.y > %d AND rect.y < %d' % G["dlg_pen_y"])
        if not pen: return "pencil not found"
        click(pen)
        if not wait_for(ST + lbl("Cancel"), 3): return "calendar did not open"
        try: pick_date(m, d)
        except Exception as ex: return f"pick failed: {ex}"
        ok, shown = dialog_date_ok(m, d)
        if not ok: return f"date mismatch: {dialog_date_ok(m, d, explain=True)[1]}"     # never save on the wrong day
        state["date"] = (m, d)
    sv = q(ST + lbl("Save") + " AND rect.y < %d" % G["dlg_save_y"])
    if not sv: return "dialog save not found"
    click(sv)
    wait_for(DIALOG, 4, gone=True)
    return "redated" if existing else "created"

def fast_createmany2(path, log):
    plan = [l.rstrip("\n").split("\t") for l in open(path) if l.strip() and not l.startswith("#")]
    done = set()
    if os.path.exists(log):
        for l in open(log):
            if l.startswith("created"): done.add(tuple(l.split("\t")[1:4]))
    state = {"date": None}
    with open(log, "a") as out:
        for subj in ("ELA", "Math"):
            items = [r for r in plan if r[0] == subj and tuple(r[1:4]) not in done]
            if not items: continue
            set_subject(subj); state["date"] = None
            for _ in range(6): swipe(230, 250, 230, 750, 0.5)
            items.sort(key=lambda r: (ORDER.get(r[1], 9999), int(r[3]), int(r[4])))   # report order, then date
            for _, title, level, m, d in items:
                t0 = time.time()
                try: res = fast_create2(title, level, int(m), int(d), state)
                except Exception as ex: res = f"error {ex!r}"
                if res != "created":
                    x = q('type == "XCUIElementTypeStaticText" AND ' + lbl("Cancel"))
                    if x: click(x); time.sleep(0.3)
                    if q(DIALOG):
                        x = q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
                        if x: click(x); time.sleep(0.5)
                    state["date"] = None
                out.write(f"{res}\t{title}\t{level}\t{m}\t{d}\n"); out.flush()
                print(f"{res:<12} {title} {level} {m}/{d}  ({time.time()-t0:.1f}s)", flush=True)

if __name__ == "__main__" and sys.argv[1] == "fastcreate2":     # kk.py fastcreate2 PLAN.tsv LOG
    fast_createmany2(sys.argv[2], sys.argv[3])

def redate_many(path, log):
    plan=[l.rstrip("\n").split("\t") for l in open(path) if l.strip() and not l.startswith("#")]
    done=set()
    if os.path.exists(log):
        for l in open(log):
            if l.startswith("redated"): done.add(tuple(l.split("\t")[1:3]))
    with open(log,"a") as out:
        for title,level,m,d in plan:
            if (title,level) in done: continue
            t0=time.time()
            try: res=redate(title,level,int(m),int(d))
            except Exception as ex: res=f"error {ex!r}"
            if res not in ("redated",):
                x=q('type == "XCUIElementTypeStaticText" AND '+lbl("Cancel"))
                if x: click(x); time.sleep(0.3)
                if q(DIALOG):
                    c=q('type == "XCUIElementTypeImage" AND name CONTAINS "leaf_hintvideo_close_btn"')
                    if c: click(c); time.sleep(0.5)
            out.write(f"{res}\t{title}\t{level}\t{m}\t{d}\n"); out.flush()
            print(f"{res:<14} {title} {level} -> {m}/{d} ({time.time()-t0:.1f}s)", flush=True)

if __name__=="__main__" and sys.argv[1]=="redate":       # kk.py redate PLAN.tsv LOG
    redate_many(sys.argv[2], sys.argv[3])

def find_row_lv(title, level, max_scroll=60):
    """Assignments tab: scroll until a row with this title AND level is visible; return its tree y or None."""
    wrapped=False; last=None
    for _ in range(max_scroll):
        rs=rows()
        for t,l,dt,y in rs:
            if t==title and l==level and G["row_tap"][0] <= y < G["row_tap"][1]: return y   # on screen only (the phone's tree holds off-screen rows)
        sig=tuple(r[0] for r in rs)
        if sig and sig==last:
            if wrapped: return None
            scroll_top(); wrapped=True; last=None; continue
        if sig: last=sig
        page_down(); time.sleep(0.5)
    return None

def redate(title, level, m, d):
    """Edit an EXISTING assignment (Assignments tab) to a new date; level-aware."""
    ST='type == "XCUIElementTypeStaticText" AND '
    if not q(ST + lbl("Class Report: Assignments")): return "not on Assignments report"
    y=find_row_lv(title, level)
    if y is None: return "row not found"
    tx, ty = G["thumb"]
    tap_tree(tx, y+ty); time.sleep(2.0)
    if not q(DIALOG):
        tap_tree(tx, y+ty); time.sleep(2.0)
        if not q(DIALOG): return "dialog did not open"
    if not dialog_is(title, level): close_dialog(); return "wrong dialog"
    pen=[i for i in q('type == "XCUIElementTypeImage" AND name CONTAINS "edit_avatar_btn"', many=True) if G["dlg_pen_y"][0]<rect(i)["y"]<G["dlg_pen_y"][1]]
    if not pen: return "pencil not found"
    click(pen[0])
    if not wait_for(ST+lbl("Cancel"),3): return "calendar did not open"
    try: pick_date(m,d)
    except Exception as ex: return f"pick failed: {ex}"
    ok, shown = dialog_date_ok(m, d)
    if not ok: return f"date mismatch: {shown}"
    sv=[i for i in q(ST+lbl("Save"), many=True) if rect(i)["y"]<G["dlg_save_y"]]
    if not sv: return "dialog save not found"
    click(sv[0]); wait_for(DIALOG,4,gone=True)
    return "redated"
