#!/bin/bash
# Start WebDriverAgent on the iPhone that holds the teacher view + USB tunnel on 8101, open a session with the
# no-idle-wait settings. Usage: ./start-wda-iphone.sh (phone unlocked, Khan Kids open). Then run scripts with KK_DEVICE=iphone.
set -u
D="$(cd "$(dirname "$0")" && pwd)"
[ -f "$D/local.env" ] && { set -a; . "$D/local.env"; set +a; }
UDID=${KK_IPHONE_UDID:?set KK_IPHONE_UDID in local.env}
CDID=${KK_IPHONE_CDID:?set KK_IPHONE_CDID in local.env}
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export PATH=/opt/homebrew/bin:$PATH
S=${SCRATCH:-$D/.session-iphone}; mkdir -p "$S"
pkill -f "iproxy 8101" 2>/dev/null; pgrep -f "xcodebuild.*$CDID" | xargs -r kill 2>/dev/null
nohup xcodebuild test-without-building -project $D/WebDriverAgent-iphone/WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner -destination "id=$CDID" -derivedDataPath $D/DerivedData-iphone \
  -allowProvisioningUpdates -allowProvisioningDeviceRegistration DEVELOPMENT_TEAM=${KK_APPLE_TEAM_ID:?set KK_APPLE_TEAM_ID in local.env} \
  PRODUCT_BUNDLE_IDENTIFIER=${KK_WDA_BUNDLE_ID:?set KK_WDA_BUNDLE_ID in local.env} > $S/wda.log 2>&1 &
# Plugged in -> USB tunnel on 8101. Not plugged in -> Wi-Fi straight to the phone (last known IP, saved on every start).
if xcrun devicectl list devices 2>/dev/null | grep "$UDID" | grep -q " connected "; then
  nohup iproxy 8101 8100 -u $UDID > $S/iproxy.log 2>&1 &
  URL=http://localhost:8101
else
  URL=http://$(cat $S/ip 2>/dev/null || echo ${KK_IPHONE_WIFI_IP:-}):8100; echo "phone not plugged in: using Wi-Fi $URL"
fi
echo $URL > $S/wda_url
for i in $(seq 1 120); do
  W=$(grep -o 'ServerURLHere->http://[0-9.]*:8100' $S/wda.log 2>/dev/null | tail -1 | sed 's/ServerURLHere->//')
  [ -n "$W" ] && [ "$URL" != http://localhost:8101 ] && URL=$W && echo $URL > $S/wda_url    # Wi-Fi: the phone reports its current IP
  # devicectl says " connected " for a phone paired over the NETWORK too: if the USB tunnel doesn't answer but the phone does, use Wi-Fi
  if [ -n "$W" ] && [ "$URL" = http://localhost:8101 ] && ! curl -s -m 2 $URL/status | grep -q '"ready"' && curl -s -m 2 $W/status | grep -q '"ready"'; then
    URL=$W; echo $URL > $S/wda_url; pkill -f "iproxy 8101" 2>/dev/null; echo "USB tunnel silent: using Wi-Fi $URL"
  fi
  if curl -s -m 2 $URL/status | grep -q '"ready"'; then
    curl -s $URL/status | python3 -c "import sys,json; ip=json.load(sys.stdin)['value']['ios'].get('ip'); ip and open('$S/ip','w').write(ip)"
    curl -s -X POST $URL/session -H 'Content-Type: application/json' \
      -d '{"capabilities":{"alwaysMatch":{}}}' | python3 -c "import sys,json; print(json.load(sys.stdin)['sessionId'])" > "$S/sid"
    curl -s -m 10 -X POST "$URL/session/$(cat $S/sid)/appium/settings" -H 'Content-Type: application/json' \
      -d '{"settings":{"waitForIdleTimeout":0,"animationCoolOffTimeout":0,"snapshotMaxDepth":25,"useFirstMatch":true,"customSnapshotTimeout":5,"keyboardAutocorrection":true,"keyboardPrediction":true}}' \
      | grep -q waitForIdleTimeout && echo "WDA settings applied (no idle wait)" || echo "WARNING: WDA settings not applied"
    echo "WDA ready, session $(cat $S/sid), scratch $S"; exit 0
  fi
  grep -qE "TEST FAILED|error:" $S/wda.log 2>/dev/null && { echo "WDA failed:"; grep -E "TEST FAILED|error:" $S/wda.log | head; exit 1; }
  sleep 2
done
echo "WDA timeout"; tail -20 $S/wda.log; exit 1
