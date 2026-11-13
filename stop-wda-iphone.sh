#!/bin/bash
# Stop the iPhone WebDriverAgent runner + tunnel (removes the "Automation Running" overlay from the phone).
D="$(cd "$(dirname "$0")" && pwd)"
[ -f "$D/local.env" ] && { set -a; . "$D/local.env"; set +a; }
CDID=${KK_IPHONE_CDID:?set KK_IPHONE_CDID in local.env}
pgrep -f "xcodebuild.*$CDID" | xargs -r kill 2>/dev/null
pkill -f "iproxy 8101" 2>/dev/null
sleep 2; pgrep -f "xcodebuild.*$CDID|iproxy 8101" >/dev/null && echo "still running" || echo "WDA stopped"
