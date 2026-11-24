"""KK_PROFILE=1: time every category of device action for one process (process.py, catalog.py, a test script).
Records each WDA request by type, every sleep by the function that slept, and inclusive/self time of the driver's functions.
The report is printed and written to state/profile-<time>.txt when the process exits."""
import time, sys, os, atexit, collections, datetime, functools, re

T0 = time.time(); _sleep = time.sleep
TRACE = os.environ.get("KK_TRACE") == "1"             # also print every request and sleep as it happens
req = collections.defaultdict(lambda: [0, 0.0])        # request type -> [count, seconds]
slp = collections.defaultdict(lambda: [0, 0.0])        # sleeping function -> [count, seconds]
fn = collections.defaultdict(lambda: [0, 0.0, 0.0])    # function -> [calls, inclusive s, self s]
stack = []                                             # [name, start, time spent in profiled callees]

def _kind(path, data):
    p = re.sub(r"/session/[^/]+", "", path)
    p = re.sub(r"/element/[^/]+/", "/element/ID/", p)
    if p.startswith("/source"): return "tree read (source)"
    if p in ("/element", "/elements"):
        return "find " + ("many " if p == "/elements" else "") + ("(predicate)" if data and "predicate" in str(data.get("using", "")) else "")
    if p.endswith("/rect"): return "element rect"
    if p.endswith("/click"): return "element click"
    if "/attribute/" in p: return "element attribute"
    if p == "/actions":
        acts = data["actions"][0]["actions"]
        moves = [a for a in acts if a["type"] == "pointerMove" and a.get("duration")]
        return "drag (settle)" if len(moves) > 1 else "drag/fling" if moves else "tap"
    return p.lstrip("/")

def _sleep_hook(x):
    f = sys._getframe(1); name = f.f_code.co_name
    if name == "<lambda>" and f.f_back: name = f.f_back.f_code.co_name
    slp[f"{os.path.basename(f.f_code.co_filename)}:{name}"][0] += 1; slp[f"{os.path.basename(f.f_code.co_filename)}:{name}"][1] += x
    if TRACE: print(f"  {time.time() - T0:7.2f} {x:5.2f}  sleep                  {name}", file=sys.stderr, flush=True)
    _sleep(x)

def wrap_req(f):
    @functools.wraps(f)
    def w(path, data=None):
        t = time.time()
        try: return f(path, data)
        finally:
            dt = time.time() - t; k = _kind(path, data); req[k][0] += 1; req[k][1] += dt
            if TRACE: print(f"  {t - T0:7.2f} {dt:5.2f}  {k:22s} {' > '.join(s[0].split('.')[-1] for s in stack[-3:])}" + (f"  {data['value'][:70]}" if data and "value" in data else ""), file=sys.stderr, flush=True)
    return w

def wrap_fn(name, f):
    @functools.wraps(f)
    def w(*a, **k):
        stack.append([name, time.time(), 0.0])
        try: return f(*a, **k)
        finally:
            n, t, ch = stack.pop(); dt = time.time() - t
            r = fn[n]; r[0] += 1; r[1] += dt; r[2] += dt - ch
            if stack: stack[-1][2] += dt
    return w

def install(mod, names=None, skip=("_req",)):
    for name in names or [n for n, v in vars(mod).items() if callable(v) and getattr(v, "__module__", None) == mod.__name__ and not isinstance(v, type)]:
        if name in skip or name.startswith("__"): continue
        setattr(mod, name, wrap_fn(f"{mod.__name__}.{name}", getattr(mod, name)))

def report():
    total = time.time() - T0
    out = [f"== profile {datetime.datetime.now():%Y-%m-%d %H:%M} {' '.join(sys.argv)}  total {total:.1f} s"]
    rq = sum(v[1] for v in req.values()); sl = sum(v[1] for v in slp.values())
    out.append(f"device requests {rq:.1f} s ({100*rq/total:.0f}%), sleeps {sl:.1f} s ({100*sl/total:.0f}%), other (Python, waiting) {total-rq-sl:.1f} s")
    out.append("\n-- requests by type: count, total s, avg s")
    for k, (n, s) in sorted(req.items(), key=lambda kv: -kv[1][1]): out.append(f"  {k:28s} {n:5d} {s:8.1f} {s/n:6.2f}")
    out.append("\n-- sleeps by function: count, total s")
    for k, (n, s) in sorted(slp.items(), key=lambda kv: -kv[1][1]): out.append(f"  {k:34s} {n:5d} {s:8.1f}")
    out.append("\n-- functions: calls, inclusive s, self s (self = inclusive minus its profiled callees)")
    for k, (n, inc, se) in sorted(fn.items(), key=lambda kv: -kv[1][1])[:40]: out.append(f"  {k:34s} {n:5d} {inc:8.1f} {se:8.1f}")
    txt = "\n".join(out)
    print(txt, file=sys.stderr, flush=True)
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
    if os.path.isdir(d): open(os.path.join(d, f"profile-{datetime.datetime.now():%Y-%m-%d-%H%M%S}.txt"), "w").write(txt + "\n")

def start(kk):
    time.sleep = _sleep_hook
    kk._req = wrap_req(kk._req)
    install(kk, skip=("_req", "lbl", "split_key"))
    atexit.register(report)
