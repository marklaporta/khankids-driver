#!/usr/bin/env python3
"""End of check-in: return to the profile picker via Switch User (no relaunch, no extra sign-ins)."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.argv=[sys.argv[0],"none"]
import fill; print("now at:", fill.finish())

# hand-back is complete; also stop the WDA runner so the "Automation Running" overlay leaves the iPad (parent 9/16)
import subprocess, os
import kk
if kk.IPHONE:   # WDA turns the phone's autocorrect + predictive text off at startup; give them back to the parent (11/7)
    try: kk._req(f"/session/{kk.SID}/appium/settings", {"settings": {"keyboardAutocorrection": True, "keyboardPrediction": True}})
    except Exception as ex: print("could not restore keyboard settings:", ex)
subprocess.run([os.path.join(kk.D, "stop-wda-iphone.sh" if kk.IPHONE else "stop-wda.sh")])
