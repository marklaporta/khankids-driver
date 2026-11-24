#!/usr/bin/env python3
"""Khan Kids teacher-view driver over WebDriverAgent (WDA).

Everything is read from the app's accessibility tree. One tree read (~0.25 s on an iPhone) answers many questions at once
(which rows are on screen, whether a dialog is open and what it shows, the list's scroll offset), so the driver reads the
tree, decides, and acts by coordinates. Single-element predicate queries (`q`) are kept for one-off checks.
Tree coordinates are window-relative; `tap_tree` converts them to screen points through the Stage Manager transform
(`.session/xform`, "OX OY SCALE"; full screen = no file).

Usage:
  kk.py rows     # list assignment rows (title, level, date) from the Assignments report
  kk.py tree     # dump the labelled elements of the current screen
  kk.py taptext LABEL [INDEX]
"""
import json, sys, time, urllib.request, datetime, os

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

# Tree-coordinate geometry per device (iPad measured 9/7-10/25; iPhone 956x440 landscape measured 11/3-11/23). Everything that
# used to be a fixed number lives here, so both devices share one code path.
#   cat_x / title_x / score_x: x of the category, lesson-title and score columns of All Progress (exact; rows are matched on them)
#   vis_lo..vis_hi: the band where a list row is safely on screen and tappable
#   stroke: (start y, end y) of the longest upward drag that stays clear of the screen edges (the iPhone's bottom edge is the
#           home gesture, so a finger never starts below y 415 there); flick: the same for a momentum fling
#   jump: measured travel of 1, 2, 3 flicks caught by a stroke (iPhone 11/23: +-50 points); without it lists move by strokes only
G = dict(
    ipad=dict(row_title_x=120, row_top=213, row_bot=815, row_date_dy=(15, 26), row_lv_x=(0, 60), row_lv_dy=(24, 32),
              row_score_x=280, row_score_dy=(20, 26), row_check_dy=(15, 30), thumb=(75, 17), row_tap=(0, 790),
              cat_x=84, title_x=102, score_x=293, list_top=215, list_bot=800, vis_lo=225, vis_hi=690,
              drag_x=230, page=(760, 420), stroke=(760, 420), flick=(760, 260), fling=(260, 790), hdr_y=170, subj_pen=(140, 170),
              dlg_date_y=(250, 330), dlg_pen_y=(250, 320), student_box_y=300, dlg_save_y=200,
              cal_hdr_y=230, cal_left_x=(50, 650), cal_cells_x=(300, 850), cal_right_cells_x=(850, 1420), cal_cell_y=280, cal_save_y=500,
              gate=((730, 420), (450, 420), (590, 300), (590, 560))),
    iphone=dict(row_title_x=112, row_top=140, row_bot=10000, row_date_dy=(10, 18), row_lv_x=(60, 80), row_lv_dy=(16, 23),
              row_score_x=200, row_score_dy=(15, 8), row_check_dy=(0, 10), thumb=(84, 10), row_tap=(150, 395),
              cat_x=88, title_x=99, score_x=238, list_top=150, list_bot=10000, vis_lo=160, vis_hi=400,
              drag_x=150, page=(410, 190), stroke=(415, 5), flick=(400, 100), jump=(1540, 2625, 3760), cat_top=55, fling=(170, 420), hdr_y=125, subj_pen=(95, 120),
              dlg_date_y=(160, 200), dlg_pen_y=(160, 200), student_box_y=195, dlg_save_y=100,
              cal_hdr_y=80, cal_left_x=(250, 684), cal_cells_x=(260, 684), cal_right_cells_x=(684, 1100), cal_cell_y=110, cal_save_y=330,
              gate=((600, 220), (360, 220), (478, 120), (478, 330))),
)[DEVICE]
LEVELS = ("Main", "Practice 1", "Practice 2", "Basic")
TRACE = os.environ.get("KK_TRACE") == "1"               # with KK_PROFILE=1: print every request as it happens (profile_kk.py)
ST = 'type == "XCUIElementTypeStaticText" AND '

# ---------------------------------------------------------------------------------------------------------------------
# Transport, app state, input
# ---------------------------------------------------------------------------------------------------------------------
def _req(path, data=None):
    r = urllib.request.Request(WDA + path, data=json.dumps(data).encode() if data is not None else None,
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=12))

def locked():
    try: return bool(_req("/wda/locked")["value"])
    except Exception: return False
def wait_unlocked(max_min=60):
    """The device auto-locked: wait (do not hammer it) until someone unlocks it. Returns False if it never happens."""
    if not locked(): return True
    print("   [the device is locked - waiting for it to be unlocked]", flush=True)
    for _ in range(max_min * 6):
        time.sleep(10)
        if not locked(): print("   [unlocked, continuing]", flush=True); time.sleep(2); return True
    return False

BUNDLE = "org.khanacademy.Khan-Kids"
def app_state():
    """XCUIApplication state of Khan Kids: 4 = foreground, 3 = background, 2 = suspended, 1 = not running."""
    try: return _req(f"/session/{SID}/wda/apps/state", {"bundleId": BUNDLE})["value"]
    except Exception: return None
def foreground():
    """Bring Khan Kids to the front WITHOUT restarting it (the device may have been used for something else since the last step).
    activate resumes the app where it was; it only launches it if it isn't running. Returns True if it wasn't in front.
    A locked device shows the lock screen over everything (and refuses to activate apps): wait for the unlock first."""
    wait_unlocked()
    if app_state() == 4: return False
    print("   [Khan Kids is not in front - bringing it back]", flush=True)
    _req(f"/session/{SID}/wda/apps/activate", {"bundleId": BUNDLE})
    for _ in range(40):
        if app_state() == 4: break
        time.sleep(0.25)
    time.sleep(1.5)                                     # the app redraws its last screen
    return True

def _touch(*acts):
    _req(f"/session/{SID}/actions", {"actions": [{"type": "pointer", "id": "f1", "parameters": {"pointerType": "touch"}, "actions": list(acts)}]})
def tap(x, y):
    """A W3C touch tap at screen point (x, y): 0.48 s round trip on an iPhone (/wda/tap: 0.6 s)."""
    _touch({"type": "pointerMove", "duration": 0, "x": round(x), "y": round(y)}, {"type": "pointerDown", "button": 0}, {"type": "pointerUp", "button": 0})
def tap_tree(x, y): tap(OX + SC * x, OY + SC * y)
def tap_el(e, dx=None):
    """Tap a tree element: its centre, or `dx` points in from its left edge."""
    tap_tree(e[2] + (e[4] / 2 if dx is None else dx), e[3] + e[5] / 2)
_tap_el = tap_el
def swipe(x1, y1, x2, y2, d=0.3):
    _req(f"/session/{SID}/wda/dragfromtoforduration", {"fromX": x1, "fromY": y1, "toX": x2, "toY": y2, "duration": d})

def _drag(x, y1, y2, ms, hold):
    """W3C touch drag: press, move over `ms`, hold `hold` ms before release."""
    _touch({"type": "pointerMove", "duration": 0, "x": x, "y": y1}, {"type": "pointerDown", "button": 0},
           {"type": "pointerMove", "duration": ms, "x": x, "y": y2}, {"type": "pause", "duration": hold}, {"type": "pointerUp", "button": 0})
def drag_settle(x, y1, y2, fast=100, slow=70, tail=15, hold=20):
    """A drag that ends slowly, so the list stops where the finger lifts: no momentum, 0.62 s on an iPhone (11/23: the content moves
    the finger distance minus ~45-100 points of touch slop, and is still there 0.3 s later). Several strokes in one request do NOT work:
    the later ones register as taps."""
    _touch({"type": "pointerMove", "duration": 0, "x": x, "y": y1}, {"type": "pointerDown", "button": 0},
           {"type": "pointerMove", "duration": fast, "x": x, "y": y2 + (tail if y2 < y1 else -tail)},
           {"type": "pointerMove", "duration": slow, "x": x, "y": y2}, {"type": "pause", "duration": hold}, {"type": "pointerUp", "button": 0})
def page_down():
    """Advance a list by most of a screen with a few rows of overlap, so no row is ever skipped."""
    drag_settle(G["drag_x"], G["page"][0], G["page"][1])
def page_up_fast():
    _drag(G["drag_x"], G["fling"][0], G["fling"][1], 120, 0)    # fling: momentum is fine when heading for the top
SLOP = 50                                               # points a drag moves before the list follows
def scroll_by(d):
    """Move a report list's content UP by about d points (down for d < 0) with one momentum-free stroke, at most one stroke's
    worth (~360 points on an iPhone). Read the tree afterwards for the actual position."""
    top, bot = G["vis_lo"], G["stroke"][0]              # a finger starts inside the list, clear of the screen edges
    if d > 0: drag_settle(G["drag_x"], bot, max(G["stroke"][1], bot - abs(d) - SLOP))
    elif d < 0: drag_settle(G["drag_x"], top, min(G["vis_hi"] + 30, top + abs(d) + SLOP))
def flick(up=True):
    """A momentum fling (iPhone: ~1500 points over ~4 s, very repeatable). A stroke catches the moving list safely (a drag, never
    a tap: a touch to stop it would open whatever row is under the finger)."""
    a, b = G["flick"]
    if up: _drag(G["drag_x"], a, b, 120, 0)
    else: _drag(G["drag_x"], G["vis_lo"], min(G["vis_hi"] + 30, G["vis_lo"] + (a - b)), 120, 0)
STROKE_RUN, STROKE_S, FLICK_S = 330, 1.1, 0.7           # points per stroke, seconds per stroke + read, seconds per extra flick
def travel(d):
    """Move a list's content up by about d points (down for d < 0) as fast as possible. Short moves are strokes. Long ones are
    1-3 flicks caught by a stroke (G["jump"]: iPhone 1540 / 2625 / 3760 points in 1.5 / 2.3 / 3.0 s, five times a stroke's
    speed), choosing the count that leaves the least to correct. The list is at rest afterwards; read the tree for where."""
    jumps = G.get("jump")
    if not jumps or abs(d) < jumps[0] * 0.6: scroll_by(d); return
    cost = lambda k: (0.8 + FLICK_S * k + -(-abs(abs(d) - jumps[k - 1]) // STROKE_RUN) * STROKE_S)
    k = min(range(1, len(jumps) + 1), key=cost)
    if cost(k) >= -(-abs(d) // STROKE_RUN) * STROKE_S: scroll_by(d); return
    for _ in range(k): flick(d > 0)
    scroll_by(d)                                        # catches the moving list (part of the measured travel)

# ---------------------------------------------------------------------------------------------------------------------
# Reading: the accessibility tree and predicate queries
# ---------------------------------------------------------------------------------------------------------------------
def tree():
    """Every element as (type, label, x, y, w, h). Visibility/accessibility/enabled are computed per node and cost half the read
    (iPhone 11/23: 1.7 s -> 0.8 s under load, ~0.25 s idle); nothing here uses them."""
    d = _req(f"/session/{SID}/source?format=json&excluded_attributes=visible,accessible,enabled")["value"]
    out = []
    def walk(n):
        t = n.get("type", ""); l = (n.get("label") or n.get("name") or "").split("/")[-1]
        r = n.get("rect", {})
        out.append((t, l, r.get("x", 0), r.get("y", 0), r.get("width", 0), r.get("height", 0)))
        for c in n.get("children", []): walk(c)
    walk(d); return out
def texts(t=None):
    return [e for e in (t or tree()) if e[0] == "StaticText"]
def _norm(s): return " ".join(s.split())

def q(pred, many=False):
    """Find element(s) by NSPredicate. Returns an id or a list of ids (None / [] if none). A miss costs ~0.1 s, a hit ~0.2 s."""
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
def wait_for(pred, timeout=4.0, gone=False):
    t0 = time.time()
    while time.time() - t0 < timeout:
        e = q(pred)
        if (e is None) == gone: return e if not gone else True
        time.sleep(0.1)
    return None if not gone else False

# ---------------------------------------------------------------------------------------------------------------------
# Class Reports: tabs and the All Progress grade/subject
# ---------------------------------------------------------------------------------------------------------------------
def goto_tab(name):
    """Class Report tab: 'Assignments' or 'All Progress'. Waits for the tab bar (it is missing while a screen is still loading)."""
    t0 = time.time()
    while True:
        tabs = q(ST + lbl(name) + " AND rect.y < 130", many=True)
        if tabs or time.time() - t0 > 4: break
        time.sleep(0.2)
    if not tabs: raise RuntimeError(f"report tab {name!r} not on screen")
    r = rect(tabs[-1]); tap_tree(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2)
    if wait_for(ST + lbl("Class Report: " + name), 4): time.sleep(0.3)

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
def header_label(key):
    """The header row of a report's list: '<grade>: <subject>' ('Preschool (Age 3): ELA', 'Kindergarten: Math')."""
    grade, subj = REPORTS[key]
    return f"{grade}: " + {"English Language Arts": "ELA"}.get(subj, subj)

def header_row(t=None):
    """All Progress: the report's header row ('Preschool (Age 3): ELA', then its lesson count) is the top of the list content and
    stays in the tree while scrolled; its y is minus the scroll offset. None on other screens."""
    h = [e for e in (t or tree()) if e[0] == "StaticText" and ": " in e[1] and e[2] < G["cat_x"]]
    return h[0] if h else None

CUR = None                                              # the report key All Progress shows (set by set_subject)
def set_subject(name):
    """All Progress report: pick grade + subject (a REPORTS key). Nothing to do when the report already shows it; otherwise
    taps only the options that aren't selected yet and returns as soon as the new report's header row is in the tree."""
    global CUR
    grade, subj = REPORTS[name]; want = header_label(name)
    t = tree(); h = header_row(t)
    if h and h[1] == want: CUR = name; return
    if not any(e[0] == "StaticText" and e[1] == "Select Grade & Subject" for e in t):   # (a failed attempt can leave it open)
        pen = [e for e in t if e[1].startswith("edit_avatar_btn") and G["subj_pen"][0] < e[3] < G["subj_pen"][1]]
        if not pen: raise RuntimeError("grade/subject pencil not found (not on All Progress?)")
        tap_el(pen[0])
        if not wait_for(ST + lbl("Grade"), 4): raise RuntimeError("grade/subject picker did not open")
    def on(t, label):
        """The option's label and whether its own toggle is on: the Grade and Subject columns share rows, so the toggle is
        the one just LEFT of the label on the same row."""
        e = next((e for e in t if e[0] == "StaticText" and e[1] == label), None)
        if not e: raise RuntimeError(f"picker option {label!r} not found")
        return e, any(x[0] == "Image" and "onboarding_toggle2" in x[1] and abs(x[3] - e[3]) < 12 and 0 < e[2] - x[2] < 80 for x in t)
    for label in (grade, subj):
        t = tree(); e, ok = on(t, label)
        if not ok: tap_el(e)
    for _ in range(15):                                 # the toggles redraw a moment after the tap
        t = tree()
        if all(on(t, label)[1] for label in (grade, subj)): break
        time.sleep(0.1)
    else: raise RuntimeError(f"picker options {grade!r} / {subj!r} did not select")
    done = next((e for e in t if e[0] == "StaticText" and e[1] == "Done"), None)
    if not done: raise RuntimeError("picker Done not found")
    tap_el(done); CUR = None
    t0 = time.time()
    while time.time() - t0 < 8:                         # the new report loads in ~1.4 s
        h = header_row()
        if h and h[1] == want: CUR = name; return
        time.sleep(0.1)
    print(f"   [warning: report header {h[1] if h else None!r} is not {want!r}]", flush=True)

# ---------------------------------------------------------------------------------------------------------------------
# All Progress: finding a lesson row
# ---------------------------------------------------------------------------------------------------------------------
_POS = None
def positions(key):
    """{lesson title: place in the report's list, in points} from the last catalog read (state/catalog-latest.json), or {}.
    catalog.py records each row's measured place ("pos"); older reads are estimated from the order (22 points a row, more at a
    category). Only differences between nearby titles are used, so an expanded group or a stale read only costs an extra step."""
    global _POS
    if _POS is None:
        _POS = {}
        try: items = json.load(open(os.path.join(D, "state", "catalog-latest.json")))["items"]
        except Exception: items = []
        est = {}
        for c in items:
            k = c["subject"]; y, cat = est.get(k, (0, None))
            y += 22 if c["category"] == cat else 70
            est[k] = (y, c["category"])
            _POS.setdefault(k, {}).setdefault(_norm(c["title"]), c["pos"] if c.get("pos") is not None else y)
    return _POS.get(key, {})

def lesson_rows(t):
    """The lesson-title rows of an All Progress list in a tree (the category and level rows are in other columns)."""
    return [e for e in t if e[0] == "StaticText" and e[2] == G["title_x"] and e[1].strip() and e[1] not in LEVELS]

def find_lesson(title, max_steps=60):
    """Bring the lesson row `title` of the current All Progress report into the tappable band and return (row, tree), or
    (None, None). The report list jumps back to its top whenever an Assign dialog closes, so this usually travels from the top.
    With the catalog's positions it steers straight there, both directions, from wherever the list is: the target's offset from
    the nearest row in view says how far to go (`travel`: flicks for long distances, then strokes). Without them (a lesson new
    since the last catalog read) it pages down, then wraps to the top once. The end of the list is one drag that changed nothing."""
    want = _norm(title); pos = positions(CUR) if CUR else {}
    lo, hi = G["vis_lo"], G["vis_hi"]; mid = (lo + hi) // 2
    last_sig = None; wrapped = False; misses = 0; prev_y = None
    for _ in range(max_steps):
        t = tree(); rows_ = lesson_rows(t)
        hit = next((e for e in rows_ if _norm(e[1]) == want), None)
        if hit:
            y = hit[3]
            if lo <= y <= hi:
                # a momentum-free stroke leaves the list still, so one read is enough on the iPhone, whose dialog names the lesson
                # (open_assign_dialog checks it); the iPad's doesn't, so there two reads must agree before anything is tapped
                if IPHONE or (prev_y is not None and abs(y - prev_y) < 1): return hit, t
                prev_y = y; continue
            prev_y = None; scroll_by(y - mid); continue
        prev_y = None
        anchors = [(abs(pos[_norm(e[1])] - pos[want]), e) for e in rows_ if want in pos and _norm(e[1]) in pos]
        if anchors and misses < 2:
            _, a = min(anchors)
            est = a[3] + pos[want] - pos[_norm(a[1])]   # where the target should be on screen
            if TRACE: print(f"   find {title!r}: anchor {a[1]!r} y={a[3]} -> est {est:.0f}", file=sys.stderr, flush=True)
            if lo - 60 <= est <= hi + 60: misses += 1   # it should be in view but isn't: an expanded group or a moved lesson
            d = est - mid
            travel(d); continue
        sig = (header_row(t) or (None, None, None, None))[3], tuple(e[1] for e in rows_[:6])
        if sig == last_sig:                             # the last drag moved nothing: the end of the list
            if wrapped: return None, None
            scroll_top(); wrapped = True; last_sig = None; continue
        last_sig = sig
        scroll_by(10000)
    return None, None

def scroll_top(max_rounds=15):
    """To the top of a report list. With the header row (All Progress): fling only while the offset says it's not at the top.
    Without one (Assignments): fling, and stop at the first fling that changed nothing."""
    h = header_row()
    if h is not None:
        for _ in range(max_rounds):
            if h[3] > -20: break
            for _ in range(2 if h[3] < -3000 else 1): page_up_fast()
            time.sleep(0.25); h = header_row() or h
        prev = None                                     # let the bounce at the top settle
        for _ in range(8):
            h = header_row()
            if h and prev is not None and abs(h[3] - prev) < 1: return
            prev = h[3] if h else prev; time.sleep(0.15)
        return
    def sig(): return tuple(e[1] for e in texts() if e[3] > G["row_top"] and e[1].strip())[:6]
    last = sig()
    for i in range(max_rounds):
        for _ in range(1 if i == 0 else 3): page_up_fast()
        time.sleep(0.5)
        s = sig()
        if s and s == last: return
        last = s

# ---------------------------------------------------------------------------------------------------------------------
# The Assign dialog
# ---------------------------------------------------------------------------------------------------------------------
DIALOG = ST + '(label == "Select All" OR name == "Select All")'
def dialog_in(t): return any(e[0] == "StaticText" and e[1] == "Select All" for e in t)
def dialog_open(t=None): return dialog_in(t or tree())

def dialog_is(title, level, t=None):
    """iPhone only: the Assign dialog shows 'Assign\\n<title>' and the level under its thumbnail. True when both match
    (always True on the iPad, whose dialog shows neither)."""
    if not IPHONE: return True
    t = t or tree()
    heads = [e[1] for e in t if e[0] == "StaticText" and e[1].startswith("Assign") and e[3] < 100]
    t_ok = any(h.split()[:1] == ["Assign"] and " ".join(h.split()[1:]) == _norm(title) for h in heads)   # "Assign Shapes", not the "Assignments" tab
    l_ok = any(e[0] == "StaticText" and e[1] == level and e[3] < 100 and 140 < e[2] < 240 for e in t)
    return t_ok and l_ok

def dialog_state(t):
    """What the open Assign dialog shows, from one tree read: the student's checkbox (and whether it is checked), the date text,
    the date pencil, Save and the close button (tree elements, or None)."""
    box = next((e for e in t if e[0] == "Image" and "teacherlibrary_checkbox" in e[1] and e[2] < 250 and e[3] > G["student_box_y"]), None)
    pen = next((e for e in t if e[0] == "Image" and e[1].startswith("edit_avatar_btn") and G["dlg_pen_y"][0] < e[3] < G["dlg_pen_y"][1]), None)
    date = None
    if pen:                                             # the date sits left of its pencil, which moves with the text's width
        near = [e for e in t if e[0] == "StaticText" and abs(e[3] - pen[3]) < 9 and 100 < e[2] < pen[2] and e[1].strip()]
        date = near[-1][1] if near else None
    return dict(box=box, checked=bool(box) and "checkbox2" in box[1], date=date, pen=pen,
                save=next((e for e in t if e[0] == "StaticText" and e[1] == "Save" and e[3] < G["dlg_save_y"]), None),
                close=next((e for e in t if e[0] == "Image" and "leaf_hintvideo_close_btn" in e[1]), None))

def close_dialog(t=None):
    """Leave the Assign dialog (and a calendar on top of it) without saving."""
    t = t or tree()
    c = next((e for e in t if e[0] == "StaticText" and e[1] == "Cancel"), None)
    if c: tap_el(c); time.sleep(0.3); t = tree()
    x = next((e for e in t if e[0] == "Image" and "leaf_hintvideo_close_btn" in e[1]), None)
    if x: tap_el(x); wait_for(DIALOG, 3, gone=True)

def _until(pred, timeout=3.0):
    """Read the tree until pred(tree) holds; returns that tree, or None at the timeout."""
    t0 = time.time()
    while True:
        t = tree()
        if pred(t): return t
        if time.time() - t0 > timeout: return None
        time.sleep(0.05)

def open_assign_dialog(title, level):
    """Find title@level in All Progress (grade/subject already set) and open ITS Assign dialog.
    Returns (None, tree of the open dialog) or (error string, None). Every tap is on a row whose position two consecutive
    reads agreed on (a list still moving after a drag would put the tap on the NEIGHBOUR row), and on the iPhone the dialog
    must name this lesson and level before anything else happens."""
    hit, t = find_lesson(title)
    if not hit: return "row not found", None
    lo, hi = G["vis_lo"], G["vis_hi"]; mid = (lo + hi) // 2
    def levels_under(t, row):
        below = [e for e in lesson_rows(t) if e[3] > row[3] + 1]
        stop = min([e[3] for e in below], default=row[3] + 200)       # the next lesson starts the next group
        return [e for e in t if e[0] == "StaticText" and e[1] in LEVELS and G["title_x"] <= e[2] < G["score_x"] and row[3] < e[3] < stop]
    lv0 = levels_under(t, hit)
    if not lv0: tap_el(hit, dx=20)                      # a single-level lesson opens its dialog; a group expands (tapping an open one would close it)
    t0 = time.time(); prev = None; retapped = False; scrolled_group = False
    t_known = t if lv0 else None                        # an open group: find_lesson's read already shows its level rows, at rest
    while True:
        t = t_known or tree()
        if dialog_in(t): break
        if t_known: prev = next((e[3] for e in lv0 if e[1] == level), None) if IPHONE else None; t_known = None
        row = next((e for e in lesson_rows(t) if _norm(e[1]) == _norm(title)), None)
        if not row: return "row lost after tapping it", None
        lv = levels_under(t, row)
        if lv:
            mine = next((e for e in lv if e[1] == level), None)
            if not mine:                                # conclusive only once the group's end (the next lesson) is in the tree:
                if any(e[3] > lv[-1][3] for e in lesson_rows(t)) or scrolled_group:     # process.py records it as a level
                    return f"level {level} not found", None                             # the app doesn't have, for good
                scroll_by(row[3] - lo); scrolled_group = True; prev = None; continue
            y = mine[3]
            if not lo <= y <= hi: scroll_by(y - mid); prev = None; continue   # the phone's short screen: the level row can sit below the edge
            if prev is None or abs(prev - y) >= 1: prev = y; continue          # the expanding group scrolls the list: wait until it stops
            tap_el(mine, dx=20)
            t = _until(dialog_in, 4)
            if not t: return "dialog did not open", None
            break
        if time.time() - t0 > 6: return "dialog did not open", None
        if time.time() - t0 > 2.5 and not retapped:    # the first tap did not register
            if dialog_in(tree()): continue
            tap_el(row, dx=20); retapped = True
        time.sleep(0.1)
    if not dialog_is(title, level, t):                  # never touch another lesson's assignment
        lv_shown = next((e[1] for e in t if e[0] == "StaticText" and e[1] in LEVELS and e[3] < 100 and 140 < e[2] < 240), None)
        close_dialog(t)
        if not lv0 and lv_shown and lv_shown != level and dialog_is(title, lv_shown, t):
            return f"level {level} not found", None     # a single-level lesson: its dialog opened on its only level
        return "wrong dialog", None
    return None, t

# ---------------------------------------------------------------------------------------------------------------------
# Dates and the calendar
# ---------------------------------------------------------------------------------------------------------------------
MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
def _date_of(m, d):
    """The date m/d nearest to today (a plan crossing New Year)."""
    dt = datetime.date(TODAY.year, m, d)
    if (dt - TODAY).days < -180: dt = datetime.date(TODAY.year + 1, m, d)
    if (dt - TODAY).days > 180: dt = datetime.date(TODAY.year - 1, m, d)
    return dt
def date_ok(text, m, d):
    """Does a dialog's date text ('Today', 'Tomorrow', 'Thu., Nov. 26') mean month m, day d?"""
    if not text: return False
    dt = _date_of(m, d); t = text.replace(".", " ").replace(",", " ").split()
    if "Today" in t: return dt == TODAY
    if "Tomorrow" in t: return dt == TODAY + datetime.timedelta(days=1)
    return dt.strftime("%b") in t and str(d) in t

def pick_date(m, d):
    """The calendar is open (two month panes; on the iPhone the right one is off-screen). Brings month m into the LEFT pane
    (taps in the right pane don't always register), taps the day and the calendar's Save. Raises rather than guessing."""
    for _ in range(16):
        t = tree()
        left = next((e for e in t if e[0] == "StaticText" and e[3] < G["cal_hdr_y"] and e[1].split(" ")[0] in MONTH_NAMES[1:]
                     and G["cal_left_x"][0] < e[2] < G["cal_left_x"][1]), None)
        if not left or not any(e[0] == "StaticText" and e[1] == "Cancel" for e in t): time.sleep(0.15); continue   # not open yet
        lm = MONTH_NAMES.index(left[1].split(" ")[0])
        if lm == m:
            cell = next((e for e in t if e[0] == "StaticText" and e[1] == "%02d" % d and G["cal_cells_x"][0] < e[2] < G["cal_cells_x"][1]
                         and e[3] > G["cal_cell_y"]), None)
            save = next((e for e in t if e[0] == "StaticText" and e[1] == "Save" and e[3] > G["cal_save_y"]), None)
            if not cell or not save: raise RuntimeError(f"day {m}/{d} or the calendar's Save not found")
            tap_el(cell); tap_el(save); return
        name = "onboarding_avatar_next_btn" if (m - lm) % 12 <= 6 else "onboarding_avatar_back_btn"   # step the LEFT pane toward m
        # every month of the pager has its own arrows (off-screen ones too): use the LEFT pane's, inside its header
        arrow = next((e for e in t if e[0] == "Image" and name in e[1] and left[2] - 20 <= e[2] <= left[2] + left[4]), None)
        if not arrow: raise RuntimeError(f"month {m} not on screen (left month={lm}) and no arrow")
        tap_el(arrow); time.sleep(0.2)
    raise RuntimeError(f"month {m} not reached")

def set_dialog_date(m, d, s):
    """Open the dialog's calendar (s = dialog_state), pick m/d, and return the dialog's new state, read back from the screen."""
    if not s["pen"]: raise RuntimeError("date pencil not found")
    tap_el(s["pen"])
    pick_date(m, d)                                     # its first reads wait for the calendar to open
    t = _until(lambda t: not any(e[0] == "StaticText" and e[1] == "Cancel" for e in t) and dialog_in(t), 3)
    if not t: raise RuntimeError("calendar did not close")
    return dialog_state(t)

# ---------------------------------------------------------------------------------------------------------------------
# Operations: assign / re-date / unassign one lesson (All Progress, subject already set)
# ---------------------------------------------------------------------------------------------------------------------
def _save(s):
    if not s["save"]: return "dialog save not found"
    tap_el(s["save"])
    if not wait_for(DIALOG, 4, gone=True): return "dialog stayed open after Save"
    return None

def _assign_in(t, m, d):
    """An open Assign dialog (tree t): make sure the student is checked and the date is m/d, then Save.
    Returns 'created' | 'redated' (also when nothing needed changing) | an error."""
    s = dialog_state(t)
    if not s["box"]: close_dialog(t); return "checkbox not found"
    existing = s["checked"]
    if existing and date_ok(s["date"], m, d): close_dialog(t); return "redated"
    if not existing:
        tap_el(s["box"])
        t = _until(lambda t: dialog_state(t)["checked"], 2)
        if not t: close_dialog(); return "checkbox did not check"
        s = dialog_state(t)
    if not date_ok(s["date"], m, d):                    # only open the calendar when the shown date is wrong
        try: s = set_dialog_date(m, d, s)
        except Exception as ex: return f"pick failed: {ex}"
        if not date_ok(s["date"], m, d): return f"date mismatch: {s['date']}"     # never save on the wrong day
    return _save(s) or ("redated" if existing else "created")

def _unassign_in(t):
    """An open Assign dialog (tree t): uncheck the student and Save."""
    s = dialog_state(t)
    if not s["checked"]: close_dialog(t); return "not assigned"
    tap_el(s["box"])
    t = _until(lambda t: not dialog_state(t)["checked"], 2)
    if not t: close_dialog(); return "checkbox did not uncheck"
    return _save(dialog_state(t)) or "unassigned"

def fast_create2(title, level, m, d, state=None):
    """All Progress: assign title@level to the student on m/d, or re-date the existing assignment (one assignment per lesson and
    level: its dialog opens with the student already checked). Returns 'created' | 'redated' | an error."""
    err, t = open_assign_dialog(title, level)
    return err or _assign_in(t, m, d)

def unassign(title, level, tab="All Progress", date=None):
    """Remove the student's assignment of title@level (open its dialog, uncheck the student, Save), from either report tab."""
    err, t = (open_assignment(title, level, date) if tab == "Assignments" else open_assign_dialog(title, level))
    return err or _unassign_in(t)

def move(title, level, m, d, date=None):
    """Assignments tab: re-date an existing assignment. Its row is near the top of the list when it is dated in the plan's window
    (the list is newest date first), so this skips the grade/subject switch and the long trip down All Progress."""
    err, t = open_assignment(title, level, date)
    return err or _assign_in(t, m, d)
redate = move                                           # the old name (nightly.py, process.py's fallback)

# ---------------------------------------------------------------------------------------------------------------------
# The Assignments report: read by process.py; moves and unassigns of existing assignments run here
# ---------------------------------------------------------------------------------------------------------------------
import re
_DATE_LINE = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?,? ")
def rows(t=None):
    """Assignment rows: [(title, level, date, y_tree)] in the list (between G row_top and row_bot)."""
    t = t or tree()
    texts_ = [e for e in t if e[0] == "StaticText"]
    lx0, lx1 = G["row_lv_x"]; dy0, dy1 = G["row_date_dy"]; ly0, ly1 = G["row_lv_dy"]; tx = G["row_title_x"]
    levels = {round(e[3]): e[1] for e in texts_ if lx0 <= e[2] < lx1 and e[1] in LEVELS}
    out = []
    for e in texts_:
        if e[2] == tx and G["row_top"] <= e[3] < G["row_bot"] and e[1] not in ("", "Today", "Tomorrow", "Yesterday") and not _DATE_LINE.match(e[1]):
            title, y = e[1], e[3]
            date = next((x[1] for x in texts_ if x[2] == tx and dy0 <= x[3] - y <= dy1), "?")
            level = next((lv for ly, lv in levels.items() if ly0 <= ly - y <= ly1), "?")
            out.append((title, level, date, y))
    return out

_MON = {m[:3]: i for i, m in enumerate(MONTH_NAMES) if m}
def row_date(text):
    """An Assignments row's date line ('Mon., Nov. 30', 'Today', 'Tomorrow', 'Yesterday') as a date, or None."""
    if text == "Today": return TODAY
    if text == "Tomorrow": return TODAY + datetime.timedelta(days=1)
    if text == "Yesterday": return TODAY - datetime.timedelta(days=1)
    p = text.replace(".", "").replace(",", "").split()
    try: return _date_of(_MON[p[1]], int(p[2]))
    except Exception: return None

def find_assignment(title, level, date=None, max_steps=40):
    """Assignments tab: bring the row title@level on screen; returns (row, tree) or (None, None). The list is newest date first
    and, like All Progress, jumps back to its top whenever a dialog closes. With the row's current `date` (process.py knows it)
    the dates in view say which way to go; without it the search starts at the top, where the plan's week is. Steps are ~300
    points, inside the ~385 points of rows the tree holds, so consecutive reads overlap and no row is skipped."""
    lo, hi = G["row_tap"]; mid = (lo + hi) // 2
    last = None; topped = False; prev = None; first = True; inside = 0   # inside: steps taken past rows of its own date
    for _ in range(max_steps):
        t = tree(); rs = rows(t)
        r = next((x for x in rs if x[0] == title and x[1] == level), None)
        if r:
            if lo <= r[3] <= hi - 25:
                if IPHONE or (prev is not None and abs(prev - r[3]) < 1): return r, t   # see find_lesson: two reads on the iPad
                prev = r[3]; continue
            prev = None; scroll_by(r[3] - mid); continue
        prev = None
        ds = [d for d in (row_date(x[2]) for x in rs) if d]
        if date and ds:
            if date > max(ds) or (date == max(ds) and inside < 2): scroll_by(-300); inside += date == max(ds); continue   # above
            if date < min(ds) or (date == min(ds) and inside < 2): scroll_by(300); inside += date == min(ds); continue    # below
            return None, None                           # its date is in view but the row isn't: no such assignment any more
        if first and not topped: scroll_top(); topped = True; first = False; continue
        first = False
        sig = tuple(x[:3] for x in rs)
        if sig == last:                                 # the end of the list
            if topped: return None, None
            scroll_top(); topped = True; last = None; continue
        last = sig; scroll_by(300)
    return None, None

def open_assignment(title, level, date=None):
    """Assignments tab: open the Assign dialog of an existing assignment (dated `date`, if known) from its row's thumbnail.
    Returns (None, tree) or (error, None)."""
    if not q(ST + lbl("Class Report: Assignments")): return "not on Assignments report", None
    r, t = find_assignment(title, level, date)
    if not r: return "row not found", None
    tx, ty = G["thumb"]
    tap_tree(tx, r[3] + ty)
    t = _until(dialog_in, 3)
    if not t: return "dialog did not open", None
    if not dialog_is(title, level, t): close_dialog(t); return "wrong dialog", None   # never touch another lesson's assignment
    return None, t

# Report order (Preschool Age 3, captured 2026-09-07), used by fill.main (the older planner's create pass).
_ELA = (["Title & Author", "Book Pages", "Words on Signs 1", "Words on Signs 2", "Rhyming", "Hear Syllables", "Blend Syllables",
         "Blend Sounds 1", "Beginning Sounds 1", "Word Families", "Blend Sounds 2", "Beginning Sounds 2", "Words: End Sound"]
        + [f"Letter {c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [f"Lowercase {c}" for c in "abcdefghijklmnopqrstuvwxyz"]
        + [f"Uppercase {c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [f"Beginning Sound {c}" for c in "bcdfghjklmnpqrstvwyz"])
_MATH = ["Count 1 & 2", "Tap & Count to 3", "Count 3 Objects", "Groups of 3", "Number Hunt 1-3", "Tap & Count to 4", "Count 4 Objects",
         "Tap & Count to 5", "Grouping: More", "Number Combos", "Last in Line", "Add Within 3", "Subtract Within 3", "Compare Sizes",
         "Measurement", "Primary Colors", "Secondary Colors", "Other Colors", "Patterns", "Positions", "Circle", "Square", "Triangle", "Rectangle"]
ORDER = {t: i for i, t in enumerate(_ELA)}; ORDER.update({t: i for i, t in enumerate(_MATH)})

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "rows":
        for r in rows(): print(f"{r[3]:4.0f}  {r[1]:<11} {r[2]:<16} {r[0]}")
    elif cmd == "taptext":            # tap a StaticText/Image/Button by (substring of) label, optional index
        lab = sys.argv[2]; i = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        hits = [e for e in tree() if lab.lower() in e[1].lower() and e[0] in ("StaticText", "Image", "Button")]
        if not hits: print("NOT FOUND", lab); sys.exit(1)
        tap_el(hits[i]); print("tapped", hits[i])
    elif cmd == "tree":
        for e in tree():
            if e[1] and e[0] != "Other": print(e)

if os.environ.get("KK_PROFILE") == "1":                # time every category of device action (profile_kk.py)
    import profile_kk; profile_kk.start(sys.modules[__name__])
