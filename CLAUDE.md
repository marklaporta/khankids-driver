# Khan Kids lesson driver

Drives the Khan Academy Kids teacher view on an iPad or iPhone from this Mac via WebDriverAgent (WDA): it reads the
student's progress reports and assigns lessons. The planning (what to assign, when) is the `populate-student` skill
(`.claude/skills/populate-student/SKILL.md`): `process.py` reads, plans with `planner.py`, applies and verifies.
`nightly.py` is the older planner, kept for `read_app()`. First-time setup, and revisiting a family's choices, is the
`setup-student` skill: if `local.env` or `state/state.json` is missing, start there.

Personal settings (device ids, signing, teacher and Google account names) live in the gitignored `local.env`
(template: `local.env.example`). Student-specific notes, if any, live in `CLAUDE.local.md`. Never put either kind of
detail in a tracked file. `state/` and `plans/` hold the student's data and are gitignored too. The family's choices
(lessons a day, horizon, play content, books) are `state.json` "settings", applied by `planner.configure()`.

## Session start
- iPad (default): `./start-wda.sh`. iPhone: `./start-wda-iphone.sh`, then run every script with `KK_DEVICE=iphone`.
  Each launches the pre-built WDA runner, opens the USB tunnel (iPad 8100, iPhone 8101; the iPhone falls back to Wi-Fi),
  applies the no-idle-wait settings and writes the session id to `.session/` or `.session-iphone/`.
- `./ipad.sh tap X Y | shot NAME [delay] | type "text" | swipe x1 y1 x2 y2`: coordinates in iPad points (1180x820 landscape).
- `python3 kk.py rows|fixdates PLAN.tsv|tree`: drives the Assignments report from the accessibility tree (reliable; prefer
  it over blind taps). If the app runs in a scaled Stage Manager window, `.session/xform` holds "OX OY SCALE"
  (screen = origin + scale * tree coords). Dialogs are in the tree. Per-device geometry lives in `kk.G`.
- Gotcha: in the Assign dialog the date pencil moves with the date text width; never use a fixed coordinate for it.
  `shot` saves `NAME.png` and a 1000px `NAMEs.png` in `.session/`; scaled px * 1.18 = points.
- If the runner fails after an iOS/Xcode update, rebuild with `xcodebuild build-for-testing` using the same project,
  destination and signing arguments as the start script.

## App navigation
- Profile picker -> tap the teacher profile -> "Grown-Ups Only" gate: swipe in the direction it names.
- A Google sign-in prompt follows on each entry to the teacher profile: iOS "Continue" -> pick the account -> "Continue".
  `fill.enter_teacher()` handles it, using `KK_TEACHER_NAME` and `KK_GOOGLE_ACCOUNT_MATCH`. Sign in once per session.
- Teacher tabs: Students | Assignments | Search | Letters | Reading | Math | Logic+ | Books | Videos.
- Assign: tap a lesson thumbnail (or Main/Practice/Basic in Class Reports > All Progress) -> check the student -> edit Date -> Save.
- Teacher Settings: gear at the top-left of the teacher home; switch image `settings_onoff_btn1` = ON, `btn2` = OFF.
  Changing any setting needs the parent's OK.

## Sign-in discipline
Sign in to the teacher profile once per check-in. `fill.enter_teacher()` detects where the app is (`fill.where()`) and only
goes through the picker and Google prompt when actually at the picker; `fill.open_report(tab)` navigates within the
teacher view. Never terminate or relaunch the app between scripts; a WDA restart must not touch the app. At the very end
run `python3 finish.py` to hand the device back on the profile picker (on an iPhone it stays in the teacher view).
Do not enable "Teacher-Only Device": it would also remove the grown-ups gate for the student.

## Running
- Don't run anything against the device while the student is using it.
- Commands are killed after 10 minutes in the foreground: run `nohup python3 -u process.py > state/process.out 2>&1 &`
  and poll. If a run is cut off, rerun it; it is idempotent.
- `--preview` changes nothing (don't call it a "dry run").
