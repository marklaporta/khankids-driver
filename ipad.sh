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
