#!/bin/bash
# Stop the iPad WebDriverAgent runner + USB tunnel (removes the "Automation Running" overlay). Run after finish.py.
D="$(cd "$(dirname "$0")" && pwd)"
[ -f "$D/local.env" ] && { set -a; . "$D/local.env"; set +a; }
CDID=${KK_IPAD_CDID:?set KK_IPAD_CDID in local.env}
pgrep -f "xcodebuild.*$CDID" | xargs -r kill 2>/dev/null
pkill -f "iproxy 8100" 2>/dev/null
sleep 2; pgrep -f "xcodebuild.*$CDID|iproxy 8100" >/dev/null && echo "still running" || echo "WDA stopped"
