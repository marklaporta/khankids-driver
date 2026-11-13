#!/usr/bin/env python3
"""Apply a weekly plan: park (redate away) + move (redate) from the Assignments tab, create from All Progress, verify."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.argv=[sys.argv[0],"none"]+sys.argv[1:]
import kk, fill
ST='type == "XCUIElementTypeStaticText" AND '
def on_tab(name):
    return bool(kk.q(ST + kk.lbl("Class Report: " + name)))
def to_tab(name):
    for _ in range(4):
        if on_tab(name): return True
        kk.goto_tab(name); time.sleep(1.0)
    raise RuntimeError(f"could not switch to {name} tab")
def to_assignments():
    fill.open_report("Assignments")
def redate_file(path, log):
    plan=[l.rstrip("\n").split("\t") for l in open(path) if l.strip()]
    done=set(l.split("\t")[1] for l in open(log) if l.startswith("redated")) if os.path.exists(log) else set()
    with open(log,"a") as out:
        for t,l,m,d in plan:
            if f"{t}|{l}" in done: continue
            for attempt in (1,2,3):
                try:
                    fill.ensure("ELA"); to_tab("Assignments")
                    res=kk.redate(t,l,int(m),int(d))
                except Exception as ex: res=f"error {ex!r}"
                if res=="redated": break
                try:
                    for _ in range(8): kk.swipe(230,250,230,760,0.4)
                except Exception: pass
            out.write(f"{res}\t{t}|{l}\t{m}\t{d}\n"); out.flush(); print(f"{res:<14} {t} ({l}) -> {m}/{d}", flush=True)
if __name__=="__main__":
    to_assignments()
    print("== park =="); redate_file("plans/park_h2.tsv", ".session/park_h2.log")
    print("== move =="); redate_file("plans/move_h2.tsv", ".session/move_h2.log")
    print("== create =="); to_tab("All Progress"); fill.main("plans/empty_create.tsv", ".session/empty_create.log")
    print("== verify =="); to_tab("Assignments")
    rows=kk.scan()
    wk=[(t,l,dt) for t,l,dt in rows if any(k in dt for k in ("Today","Tomorrow","Sep. 13"))]
    json.dump(wk, open(".session/week1_verify.json","w"))
    for t,l,dt in sorted(wk, key=lambda x: x[2]): print(f"  {dt:<15} {t} ({l})")
    print("DONE")   # stay in the teacher view; run `python3 finish.py` at the very end of the check-in
