#!/bin/bash
# Start WebDriverAgent on the iPad + USB tunnel, wait until ready, open a session.
# Usage: ./start-wda.sh   (iPad plugged in, unlocked)
set -u
D="$(cd "$(dirname "$0")" && pwd)"
[ -f "$D/local.env" ] && { set -a; . "$D/local.env"; set +a; }
UDID=${KK_IPAD_UDID:?set KK_IPAD_UDID in local.env}
CDID=${KK_IPAD_CDID:?set KK_IPAD_CDID in local.env}
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export PATH=/opt/homebrew/bin:$PATH
S=${SCRATCH:-$D/.session}; mkdir -p "$S"
pkill -f "iproxy 8100" 2>/dev/null; pgrep -f "xcodebuild.*$CDID" | xargs -r kill 2>/dev/null   # iPad runner only (do not kill the iPhone runner)
nohup xcodebuild test-without-building -project $D/WebDriverAgent/WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner -destination "id=$CDID" -derivedDataPath $D/DerivedData \
  -allowProvisioningUpdates DEVELOPMENT_TEAM=${KK_APPLE_TEAM_ID:?set KK_APPLE_TEAM_ID in local.env} \
  PRODUCT_BUNDLE_IDENTIFIER=${KK_WDA_BUNDLE_ID:?set KK_WDA_BUNDLE_ID in local.env} > $D/wda.log 2>&1 &
nohup iproxy 8100 8100 -u $UDID > $D/iproxy.log 2>&1 &
for i in $(seq 1 90); do
  if curl -s -m 2 http://localhost:8100/status | grep -q '"ready"'; then
    curl -s -X POST http://localhost:8100/session -H 'Content-Type: application/json' \
      -d '{"capabilities":{"alwaysMatch":{}}}' | python3 -c "import sys,json; print(json.load(sys.stdin)['sessionId'])" > "$S/sid"
    curl -s -m 10 -X POST "http://localhost:8100/session/$(cat $S/sid)/appium/settings" -H 'Content-Type: application/json' \
      -d '{"settings":{"waitForIdleTimeout":0,"animationCoolOffTimeout":0,"snapshotMaxDepth":25,"useFirstMatch":true,"customSnapshotTimeout":5}}' \
      | grep -q waitForIdleTimeout && echo "WDA settings applied (no idle wait)" || echo "WARNING: WDA settings not applied"
    echo "WDA ready, session $(cat $S/sid), scratch $S"; exit 0
  fi
  grep -qE "TEST FAILED|error:" $D/wda.log 2>/dev/null && { echo "WDA failed:"; grep -E "TEST FAILED|error:" $D/wda.log | head; exit 1; }
  sleep 2
done
echo "WDA timeout"; tail -20 $D/wda.log; exit 1
