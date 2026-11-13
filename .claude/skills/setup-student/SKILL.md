---
name: setup-student
description: First-time setup and onboarding for this repo. Checks the Mac and device prerequisites, builds WebDriverAgent, writes local.env, and interviews the parent about the child and their goals and content choices, then writes the family's settings and notes and runs a first preview. Use when someone has just cloned the repo, when local.env or state/state.json is missing, or when the parent says "set me up", "get started", "onboard", or wants to revisit their choices (daily load, play content, videos, books, starting grade).
---

# Set up a new family

Goal: a parent who just cloned this repo ends with a working driver, family settings that reflect *their* choices, and a
first plan they have looked at and agreed to. The parent is the authority on the child and on what the app should be
for. Propose sensible defaults and explain trade-offs briefly, but don't impose this repo's defaults as the right answer.

Everything you learn about the child and every device or account value stays in gitignored files: `local.env`,
`state/state.json`, `CLAUDE.local.md`, `plans/`. Never write those details into a tracked file, a commit, or a GitHub
issue. Run `git status` before finishing; no personal file may show up there.

If `local.env`, `state/state.json` and `CLAUDE.local.md` already exist, this is a revisit. Show the current settings,
ask what they want to change, and skip the parts that are already done.

## 1. Prerequisites (check, then fix with the parent's OK)
- macOS with Xcode: `xcodebuild -version`. The Xcode license must be accepted. That needs the parent's password, so ask
  them to run `sudo xcodebuild -license accept` themselves.
- `iproxy` for the USB tunnel: `which iproxy`, else `brew install libimobiledevice`. Ask before installing.
- Python 3 (standard library only).
- An Apple ID signed in to Xcode (Settings > Accounts). A free personal team works, but its signing expires after 7 days,
  so the runner then needs a rebuild. A paid team lasts a year.

## 2. Khan Academy Kids: what the parent needs to have done
Ask, and explain where something is missing:
- The child uses Khan Academy Kids on an iPad or iPhone.
- The account is a teacher (class) account with the child as the only student. Assigning lessons by date only exists in
  the teacher view. A parent account can be converted, or the parent can sign up as a teacher.
- Which device holds the teacher view. It can be the child's iPad (teacher and student share the profile picker,
  `KK_DEVICE=ipad`, the default) or the parent's iPhone (`KK_DEVICE=iphone`; assignments sync to the child's device).
  Note the teacher profile's name as it shows on the picker, and the Google account used to sign in, if any.
- Supported layouts: iPad in landscape (1180x820 points) and iPhone in landscape (956x440). On another size the geometry
  table `kk.G` needs a new entry, measured from the accessibility tree. Say so up front, and plan to do it together.

## 3. Device and WebDriverAgent
- Plug in the device, unlock it, and tap "Trust". Turn on Developer Mode (Settings > Privacy & Security), and
  Settings > Developer > Enable UI Automation.
- Read the ids: `xcrun devicectl list devices` gives the CoreDevice id (CDID); `xcrun xctrace list devices` or the
  devicectl details give the UDID.
- Ask for the Apple team id (Xcode > Settings > Accounts, or the error message of a first build) and a bundle id they
  own, e.g. `com.<their-name>.WebDriverAgentRunner`.
- `git clone https://github.com/appium/WebDriverAgent.git` into `WebDriverAgent/` (or `WebDriverAgent-iphone/` for the
  iPhone). Build once with `xcodebuild build-for-testing`, using the project, scheme, destination and signing arguments
  from the start script. On the first launch the device asks the parent to trust the developer app (Settings > General >
  VPN & Device Management).
- Write `local.env` from `local.env.example`. Then run the start script and check that it prints "WDA ready" and "WDA
  settings applied".

## 4. The interview
Do it as a conversation in a few small batches, not one long form. Use multiple-choice questions where the options are
clear, and open questions for the child. Record answers as you go. The parent can skip anything; use the default and
note that it was skipped.

**The child** (goes to `CLAUDE.local.md`):
- What to call them. A first name or a nickname, kept local.
- Age, and roughly what they can do now: letters, letter sounds, counting, shapes, attention span.
- Interests (animals, vehicles, music...). These steer book and non-fiction choices and help explain the plan to them.
- Anything already known: lessons they struggle with or rush through, siblings who help, how they react to hard work.

**Goals** (go to `CLAUDE.local.md` and steer every review):
- What the parent wants from the app, e.g. school readiness by a date, reading, numeracy, or just steady practice.
- How they see screen time and free play. That decides the content choices below.
- How much they want to be involved. Do they want to read a short review after each run? How often will they run it?

**Settings** (go to `state/state.json` "settings"; the defaults are in brackets):
- `daily` [5]: lessons a day. Small days get finished; big days get cherry-picked.
- `horizon_days` [7]: how many days ahead are planned. Today and tomorrow are mirrored exactly, and later days are
  topped up each run.
- `include_play` [false]: whether the Logic+ songs, movement, feelings and habits lessons count as assignable work.
  With false, only the cognitive Logic+ categories ("Flexible Thinking", "Focus & Memory") are assigned. Some families
  want the social-emotional and movement content. Both are reasonable choices.
- `books_per_day` [0]: books are unscored, so they give the planner no evidence. Some families still want reading in
  every day. If they do, non-fiction about the child's interests comes first, and decodable readers only once the child
  can sound out CVC words.
- `exclude_titles` [[]]: any specific lessons the parent never wants assigned.
- Starting grade: "scan_keys" (top level of state.json, not inside settings). Start one level below where the child is,
  so holes get found, and let reach probes credit what they already know:
  - age 3-4: `["ELA","Math","Logic+","ELA4","Math4","Logic+4"]`
  - age 5 or kindergarten: `["ELA4","Math4","Logic+4","ELAK","MathK","Logic+K"]`
  - 1st grade: `["ELAK","MathK","Logic+K","ELA1","Math1"]`

  The planner adds the next grade by itself as strands run out.

**App settings the parent controls in the teacher view** (Teacher Settings, the gear at the top-left of the teacher
home). Ask each one; don't assume:
- "Show students Videos tab", "Show students Create tab": whether the child can browse videos or free-play outside the
  assignments.
- "Show students Assignments first": whether assignments are the first thing the child sees.
- "Fast-Forward Button in Lessons".
- "Archive Assignments after": how long finished lessons stay visible. 1 day keeps the list short.
- Never turn on "Teacher-Only Device": it removes the grown-ups gate for the child too.

Offer to set the switches through the driver (each change needs a yes), or tell the parent where they are.

## 5. Write the family's files
- `state/state.json`: copy `state/state.example.json`, then set "settings" and "scan_keys" from the interview.
- `CLAUDE.local.md`: the child (name, age, abilities, interests, known observations), the goals, the content choices and
  why, the app settings as chosen, the device that holds the teacher view, and how the parent wants to be involved.
  Write it as plain notes for a future session. It's what the `populate-student` skill reads first.
- `plans/<YYYY-MM>-plan.md`: start the month's log with the goals and the starting settings.
- Optional: offer a private git history for `plans/` and `state/`, in a separate repository that is never pushed to a
  public remote. The public repo ignores those files on purpose.

## 6. First run, together
- Start the runner. Then run `nohup python3 -u process.py --preview > state/process.out 2>&1 &`. The first run reads
  the whole catalog (10 minutes or more), so poll it in under-10-minute waits.
- Go through the planned days with the parent: why each lesson is there, what's held and why, and how full each day
  is. Adjust settings or `CLAUDE.local.md` until they agree. Re-running the preview only replans; it doesn't touch the app.
- On their yes, apply: `nohup python3 -u process.py > state/process.out 2>&1 &`. Wait for `VERIFIED: app matches the
  plan`, then `python3 finish.py`.
- Tell them how day-to-day use works: say "populate the app" whenever they want a refresh, and tell the agent what they
  see the child do. Observations go into the planner state, and the next plan follows them.
