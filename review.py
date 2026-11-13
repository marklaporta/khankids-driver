#!/usr/bin/env python3
"""Read the Assignments report with completion/scores -> .session/review.json"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.argv=[sys.argv[0],"none"]
import kk, fill
ST='type == "XCUIElementTypeStaticText" AND '
fill.open_report("Assignments")
def rows_with_scores():
    t=kk.tree(); out=[]
    for title,level,dt,y in kk.rows(t):
        score=next((e[1] for e in t if e[0]=="StaticText" and e[2]>280 and abs(e[3]-y-20)<26 and e[1].strip()), "")
        check=any(e[0]=="Image" and "check" in e[1] and abs(e[3]-y-15)<30 for e in t)
        out.append((title,level,dt,score,check))
    return out
kk.scroll_top(); seen={}; last=None; stale=0
for _ in range(80):
    rs=rows_with_scores()
    for t,l,dt,sc,ck in rs: seen[(t,l,dt)]=(sc,ck)
    sig=tuple(r[0] for r in rs)
    if sig and sig==last:
        stale+=1
        if stale>=2: break
    else: stale=0
    if sig: last=sig
    kk.swipe(230,720,230,300,0.8); time.sleep(0.5)
rows=[(t,l,dt,sc,ck) for (t,l,dt),(sc,ck) in seen.items()]
json.dump(rows, open(".session/review.json","w"))
print(len(rows),"rows")
for t,l,dt,sc,ck in sorted(rows, key=lambda r: r[2]):
    if any(k in dt for k in ("Today","Yesterday","Tomorrow","Sep.  7","Sep.  8","Sep.  9","Sep. 10","Sep. 11","Sep. 12","Sep. 13","Sep. 14")):
        print(f"  {dt:<15} {t} ({l})  {sc or '-'}  {'DONE' if ck else ''}")
