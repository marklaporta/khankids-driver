#!/bin/bash
# usage: ipad.sh tap X Y | ipad.sh shot NAME | ipad.sh type "text" | ipad.sh swipe x1 y1 x2 y2
S=${SCRATCH:-"$(cd "$(dirname "$0")" && pwd)/.session"}
sid=$(cat $S/sid)
case "$1" in
  tap) curl -s -X POST http://localhost:8100/session/$sid/wda/tap -H 'Content-Type: application/json' -d "{\"x\":$2,\"y\":$3}" >/dev/null; echo "tapped $2,$3";;
  shot) sleep ${3:-3}; curl -s http://localhost:8100/screenshot | python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('$S/$2.png','wb').write(base64.b64decode(d['value']))"; sips -Z 1000 $S/$2.png --out $S/${2}s.png >/dev/null; echo "$S/${2}s.png";;
  type) curl -s -X POST http://localhost:8100/session/$sid/wda/keys -H 'Content-Type: application/json' -d "{\"value\":[\"$2\"]}" >/dev/null; echo typed;;
  swipe) curl -s -X POST http://localhost:8100/session/$sid/wda/dragfromtoforduration -H 'Content-Type: application/json' -d "{\"fromX\":$2,\"fromY\":$3,\"toX\":$4,\"toY\":$5,\"duration\":0.3}" >/dev/null; echo swiped;;
esac
# assign-date helper: after an Assign dialog is open, set date (M/D in Sep or Oct 2026), check the student, Save.
# usage: ipad.sh assign 9 8   |  ipad.sh assign 10 2
if [ "$1" = assign ]; then
  M=$2; D=$3
  cols=(389 455 522 588 655 721 787)   # Sun..Sat (points)
  rows=(320 371 422 473 525 576)       # week rows
  if [ "$M" = 9 ]; then off=2; else off=4; fi   # Sep 1 = Tue(2), Oct 1 = Thu(4)
  idx=$((off + D - 1)); r=$((idx / 7)); c=$((idx % 7))
  $0 tap 232 394 >/dev/null; sleep 0.6          # check the student
  $0 tap 393 326 >/dev/null; sleep 1.2          # open calendar
  [ "$M" = 10 ] && { $0 tap 794 230 >/dev/null; sleep 0.8; }
  $0 tap ${cols[$c]} ${rows[$r]} >/dev/null; sleep 0.6
  $0 tap 746 581 >/dev/null; sleep 1.0          # calendar Save
  $0 tap 913 162 >/dev/null; sleep 1.5          # dialog Save
  echo "assigned for $M/$D"
fi
