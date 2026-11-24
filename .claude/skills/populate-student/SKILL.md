---
name: populate-student
description: Populate / update / refresh the student's Khan Academy Kids assignments ("run the process", "update the iPad", "populate the app", "assign lessons"). Reviews all of the student's prior work and assigns the next logical lessons for the next 7 days, mastery-based. Use whenever the parent asks to populate, update, refresh or assign lessons in Khan Academy Kids.
---

# Populate the student's Khan Academy Kids assignments

Intent: a mastery-based, adaptive plan using only Khan Academy Kids. Claude is the architect of the learning plan: review
the student's performance on every prior lesson, then assign the next logical lessons in their zone of proximal development.
No gaps; fill holes before building on them; never re-assign work the student has already done well.
If `CLAUDE.local.md` exists, it holds this student's notes (observations, active holds, the parent's decisions): read it first.
If `local.env` or `state/state.json` is missing, the family hasn't been set up yet: use the `setup-student` skill first.
The family's choices (lessons a day, horizon, play content, books, excluded titles) are in `state.json` "settings";
change them there, not in `planner.py`.

## Device
- iPad (default, `KK_DEVICE=ipad`): `./start-wda.sh`. iPhone: `./start-wda-iphone.sh` and run EVERY script with
  `KK_DEVICE=iphone`. Assignments are server-side, so assigning from a parent's phone signed in as the teacher reaches the
  student's iPad. Device ids and signing come from `local.env`.
- iPhone: plugged in -> USB tunnel on 8101; not plugged in -> Wi-Fi to the phone's last known IP (`.session-iphone/ip`).
  `kk.py` picks the iPhone geometry table `kk.G`, session dir `.session-iphone`, and the start/stop scripts.
  `finish.py` on the phone does not Switch User (the next run needs no sign-in) and stops the iPhone runner.
- iPhone specifics: 956x440 landscape; the tree also holds off-screen rows (`find_lesson` brings a row into the visible band
  before tapping); the calendar's right pane is off-screen (`pick_date` always works in the left pane anyway); a finger never
  starts below y 415 (the bottom edge is the home gesture).
- Phone safety: every tap uses coordinates from a fresh tree read of a list at rest; Assignments-tab rows are tapped only when
  on screen (`G["row_tap"]`); the phone's Assign dialog names the lesson and level, and `kk.dialog_is()` must match before
  any save ("wrong dialog" otherwise).
- The driver brings Khan Kids back to the front (`kk.foreground`) and waits for an unlock (`wait_unlocked`) instead of
  relaunching it; only the student's own profile forces a relaunch (the profile picker is reachable only from a fresh start).

## Core rules
1. TWO-RESULT RULE. One good score is not enough to build on: a young child's repeat scores swing widely. A strand moves up
   a grade only on two results >= 80 at least `CONFIRM_GRADE_GAP` (7) days apart in the strand below; the next step of a
   sequential MATH strand, and the retry of a failed one, needs a second result on the step before, `CONFIRM_STEP_GAP` (2)+
   days after the first. The missing result is assigned as Practice 1 (else Practice 2) of the last lesson passed, why =
   "second result before moving on". This is the one exception to "no practice on mastered work". No practice level in the
   app = no extra requirement. Rollback ladders keep their own rule.
2. `daily` (default 5) A DAY, GATES FIRST. A gate is a rollback step or a readiness check; up to 3 go into the day before anything
   else and outside the retry limit, then 1 letter, then the queue. A small day gets finished; a big one gets cherry-picked.
3. SHORT HOLDS. A hold gets its readiness check after `HOLD_CHECK_DAYS` (5) at most, whatever `until` says, unless the hold
   has `"fixed": true` (the parent named the date). A failed check (< 70) rests `HOLD_EXTEND_DAYS` (7).
4. Holds may carry `ladder` (the readiness checks to walk, in order), `need` (how many different lessons >= 80 lift the
   hold) and `pair` (a lesson re-dated to the same day as its check, e.g. the letter's own "Letter X" lesson).
5. Word writing (More Words, Writing Words, Uppercase Words, Write Words) stays closed until 8 beginning sounds are proven.
   A focus track never jumps a weak earlier step of a sequential strand.
Test rule changes offline before touching the device: plan from `state/catalog-latest.json` + `state/assign-cache.json` and a
COPY of state (overlay + mark_done as in process.py), including what-if attempts.

## Run it
1. Device plugged in and unlocked (iPhone: every command below runs with `KK_DEVICE=iphone`). Don't touch the app while
   the student is using it. Setting Auto-Lock to Never while it charges helps; that's the parent's call.
2. `./start-wda.sh` (iPhone: `./start-wda-iphone.sh`). It also turns off WDA's wait-for-idle, which matters because Khan Kids
   animates constantly. Check that it prints "WDA settings applied".
3. Optional, read-only: `nohup python3 -u process.py --preview > state/process.out 2>&1 &`
4. Apply: `nohup python3 -u process.py > state/process.out 2>&1 &`. Add `--tomorrow` if the student is done for today;
   after 8pm that is automatic. Poll with until-loops of 9 minutes or less, because foreground commands are killed at 10
   minutes. If the device locks, the run waits up to 60 minutes for it to be unlocked instead of failing.
   If the run is interrupted, just rerun it: it is stateless and only does the remaining diff.
   Options:
   - `--days N` sets the horizon for this run (default: settings `horizon_days`, else 7).
   - `--clear-done-today` unassigns lessons finished today (their scores stay in state "attempts") and gives fresh ones for today.
   - `--clear-today` assigns nothing today; `--today-max N` sizes today for this run only.
   - `--full-catalog` forces a full catalog read; `--full-scan` re-reads every assignment.
   If the iPad is not on USB but is on Wi-Fi, `start-wda.sh` still launches the runner, which logs
   `ServerURLHere->http://<ip>:8100`. Create a session at that address and run with `WDA_URL=http://<ip>:8100`.
   A WDA restart inside a run only works over USB.
5. Verification is built in: the run ends with `VERIFIED: app matches the plan`. `python3 -u process.py --preview` should
   then print `moves 0  creates 0  unassigns 0`.
6. `python3 finish.py` returns the app to the profile picker and stops WDA, which clears the "Automation Running" overlay.
7. Log the review in `plans/<YYYY-MM>-plan.md`: what the student did, the scores, the difficulty verdict, and what is held
   for hole-filling.

## Speed design
Measured on the iPhone, 11/23: a nightly run of 15 changes takes about 2.5 minutes (`APPLIED in N min`); a full catalog read of
10 reports about 2 minutes. Per change: ~4 s to re-date or unassign, ~7-8 s when the calendar is needed.
- Measure before optimizing: `KK_PROFILE=1` times every category of device action (requests by type, sleeps by function,
  inclusive/self time per function) and writes `state/profile-*.txt`; `KK_TRACE=1` also prints every request as it happens.
- No idle waits. The start scripts post `/appium/settings`: waitForIdleTimeout 0, animationCoolOffTimeout 0,
  snapshotMaxDepth 25, useFirstMatch. Without it, every tap and query waits for a quiescence the Unity app never reaches.
- Read the tree, then act by coordinates. One tree read (`kk.tree()`, ~0.25 s; visibility attributes excluded, which halves
  it) shows the list rows and their positions, an open dialog's title, level, checkbox, date, pencil and Save
  (`kk.dialog_state`), the calendar's month and days, and the All Progress scroll offset (`kk.header_row`). A predicate query
  (`kk.q`, 0.1-0.2 s) answers one question, so it is only for one-off checks. Every tap is a W3C touch (~0.45 s, the floor:
  XCTest waits for the event to be delivered); taps are now the largest cost, about 7 per change.
- Moving through a list: `kk.drag_settle` is a drag that ends slowly, so the list stops where the finger lifts (no momentum,
  ~0.8 s for ~360 points). Long distances are flicks caught by a stroke (`kk.travel`, calibrated in `G["jump"]`: 1, 2, 3 flicks
  = 1540, 2625, 3760 points in 1.5, 2.3, 3.0 s). A plain touch must never stop a moving list: it opens the row under it.
  Several strokes in one actions request don't work (the later ones register as taps).
- Finding a lesson (`kk.find_lesson`): the All Progress list jumps back to its TOP whenever an Assign dialog closes, so each
  change travels from the top. The catalog read records each lesson's place in its list (`pos`); the target's distance from
  the nearest row in view says how far to travel, in either direction. A lesson missing from the catalog falls back to paging
  down, then wrapping to the top once; the end of a list is one drag that changed nothing.
- One pass per report, grouped by date: creates, moves and unassigns in one pass through All Progress (`fill.main_ordered`),
  creates and moves first, then unassigns. Within a report the changes go by date: a new assignment's dialog offers the last
  date picked, so same-day creates in a row skip the calendar. Operations are creates, moves of existing assignments, and
  unassigns: anything assigned, unfinished and dated from the start of the plan on that the plan doesn't want is removed
  (`kk.unassign`: open its dialog, uncheck the student, Save). The plan lives in `state/`, so the app never holds a parking
  pool. Unassigned rows also leave `state/assign-cache.json` (and the incremental read prunes cached rows in its re-read range
  that the app no longer shows).
  - Existing assignment: the dialog opens with the student's checkbox already checked. Khan Kids has one assignment per
    lesson and level. `fast_create2` changes its date in place, or closes it if the date is already right.
  - The Assignments-tab `kk.redate` is only a fallback.
  - The dialog's date is read before every Save, and the calendar opens only when it is wrong.
  - Trade-off: within a day the student sees lessons in the app's list order, not a custom order.
- Switching report (`kk.set_subject`): nothing to do when the header row already shows it; otherwise taps only the options not
  yet selected (the Grade and Subject columns share rows, so each toggle is matched to its own label) and returns when the new
  header appears (~3.5 s).
- No sticky plan. The plan is deterministic from the student's data, so a re-run without new results changes nothing.
- Incremental reads.
  - Assignments: the list is newest-date first. The scan stops at the last run's date minus 1 and merges into
    `state/assign-cache.json`.
  - All Progress catalog: a full read once a week per subject and grade, kept in `state/catalog-latest.json`. In between,
    scores from assignments override the catalog through `state.json` "attempts", which also records when each attempt happened.
    Each step is the longest stroke and is verified against the header offset (a gap backs up half a step). Categories the plan
    never uses (books when `books_per_day` is 0, play content when `include_play` is false) are carried over from the last read
    once nothing after them is used.
  - Learning Path work shows up ONLY in the All Progress catalog, not in Assignments. Whenever the parent says the student
    used the Learning Path, run with `--full-catalog` (about 2 minutes of reading).
  - A failed catalog read is loud: it prints a WARNING, uses the last good read, and refuses to plan without ELA and Math.
- "Developer App Certificate is not trusted" at WDA launch: the automatic restart usually fixes it. If it persists, trust
  the developer app on the device (Settings > General > VPN & Device Management).
- Lock and WDA drops: 12-second request timeout, wait while `/wda/locked`, and a WDA restart that never touches the app.
- CORRECTNESS: on the iPad the assign dialog does NOT show the lesson's name. If a list is still settling after a drag, the
  tap opens the NEIGHBOUR's dialog and the change lands on the wrong lesson.
  - Guard 1: a row is tapped only from a read of a list at rest (on the iPad, two consecutive reads must agree on its
    position); a group's level row is tapped only after it stopped moving (an opening group scrolls the list).
  - Guard 2 (iPhone): `kk.dialog_is` checks the dialog's lesson and level before anything is changed.
  - Guard 3: after applying, `process.py` re-reads the assignments and repairs any difference from the plan, up to 2 more
    rounds. Success is `VERIFIED: app matches the plan`. `WARNING: N differences remain` must be investigated.
- The iPad path shares all of this code but its new timings (strokes, jumps) are not yet measured: `G["ipad"]` has no `jump`
  calibration, so lists move by strokes only there. Calibrate it with a profiled run before relying on the numbers above.
- Tried and rejected (11/23): the teacher Search tab. It searches by STANDARD only (Choose Standard > framework > domain > standard,
  e.g. Head Start Preschool > P-LIT > P-LIT (All)), not by name. Results are a thumbnail grid with one thumbnail per level
  (tapping one opens the same Assign dialog, 1.9 s), but a domain's grid is ~23,000 points long (Uppercase Letters at ~17,700 vs
  ~2,350 in All Progress), it needs 4-5 taps to reach, shows no scores, and a lesson sits under several standards. All Progress
  with `find_lesson` stays faster.

NEVER edit `state/state.json` while `process.py` is running: it saves its in-memory copy at the end and overwrites the edit.

## What the process does (`process.py` + `planner.py`)
- Reads every report in `state.json` "scan_keys" (Age 3 and Age 4 ELA, Math and Logic+ to start, with more grades added as
  strands run out): every lesson, in app order, with the student's score. It also reads the Assignments report: what is
  assigned, per level, and whether it is done.
- Classifies every lesson:
  - mastered: 90% or more. Never re-assigned.
  - viewed: unscored and done. Never re-assigned. Viewed lessons are NOT progression evidence: gates, sound-lesson counts
    and grade exhaustion use `planner.proven()` (scored results), not `solid()`. A viewed lesson neither opens nor blocks anything.
  - credited: passed a reach probe. Never assigned.
  - needs work: under 90%.
  - new.
- Lesson titles repeat across grades (most Age-4 ELA lessons are the Age-3 lessons with the same scores). A title counts
  only at its lowest grade. Titles are matched case-insensitively.
- Assisted scores in `state.json` under "assisted" count as new.
- Retries are only for scores under 80 (`RETRY_BELOW`). 80-89 counts as solid, because one mis-tap at a young age is noise.
  - No retry when a harder lesson in the same strand, or the same strand one grade up, is already mastered ("superseded").
    Letters are exempt.
  - Level: Basic if the app has it and the student hasn't done it, otherwise Main; never Practice. At most 2 retries a day,
    2 or more days after the last attempt.
- Letters: the letter lessons are tracing and production practice.
  - 1 letter lesson a day right after the gates (`MIN_LETTERS_PER_DAY`), up to `LETTER_SLOTS` (2) in the normal fill, and
    more when nothing better claims the slot.
  - Ladder per letter: Letter X, Lowercase, Uppercase, Beginning Sound, "Letter X Words" (Age 4), then Ending Sound.
  - A weak stage (under 80) holds that letter's later stages.
  - Ending sounds open after 8 beginning sounds are solid. Short vowels and CVC words open after 6 ending sounds, or after
    a CVC reach probe passes.
  - Letters are item-specific, so they are never probed or credited.
- New skills, mastery-based across grades:
  - A lesson at grade g opens when its strand one grade down is solid.
  - Strands map by the same category name, or by the explicit `MATH4_PREREQ` and `ELA4_PREREQ`.
  - A strand with no mapping is HELD and logged as "unmapped strand". Write its mapping into `PREREQ_MAPS`.
- Next grade: as soon as any strand at the top grade read is exhausted and solid, the next grade (Kindergarten, then 1st
  and 2nd) is added to the reads. Never pad with Practice lessons instead.
- Reach probes run only in strands where a skill generalizes: CVC Words, Vocabulary & Sorting, Focus & Memory, Flexible
  Thinking, and the math counting ladder.
  - In-sequence strand with at least 2 mastered and none under 80, and at least 3 new lessons left: probe the 2 hardest new
    lessons. Both 90 or more on the first attempt credits the rest. One 90+ and one 80-89 adds a third probe. Anything under
    80 means no credit; re-probe after 21 days.
  - CVC Words, a gated strand: probe the first 2 lessons once Blend Sounds 2 is mastered and 6 beginning sounds are solid.
    Passing opens CVC early.
  - Credit is provisional. A later score under 80 in that strand takes it back.
  - At most 1 probe a day. State lives in `state.json` "probes", "credited" and "opened"; results print as "REACH ..." lines.
- QUEUE MODEL. Each run computes ONE ranked queue of lessons that are appropriate NOW, from the student's data alone, then
  fills the horizon day by day. The app MIRRORS the plan: no balancers, no trimming.
  - Queue order:
    1. retries (under 80, Basic level if it exists, otherwise Main, never Practice; 2 or more days after the last attempt)
    2. parent focus practice (passes holds and gates; cadence follows calendar dates)
    3. reach probes
    4. the next new step of each open strand
    5. letter stages, at most 3 per letter per plan (`LETTER_STAGES_PER_PLAN`), on separate days
  - Per-day limits: `daily` lessons, gates first, then 1 letter lesson, `books_per_day` books, 2 retries, 1 probe, and
    no two lessons from the same strand. Letters fill any slot nothing better claims, and a letter's whole tracing ladder
    (Letter X, lowercase, uppercase) may sit in one plan on separate days. Consequence: the plan front-loads, and its last
    days can be nearly empty until the next run refills them.
  - Sequential strands get only ONE untested step in the whole plan, because the next step depends on the result. A later
    step also waits while an EARLIER step is weak (struggled or under 80). These are the math counting ladder, ordinals,
    addition, subtraction, decomposing, and ELA phonological awareness. Parallel strands (shapes, colors, vocabulary,
    writing, logic) can have one step per day.
  - Readiness checks after a hold: ONE lesson of that family in the whole plan, and it is the EASIEST one: the retry of what
    failed (at Basic if available), else the lowest grade. The next run adds the next one, depending on the result.
  - A struggled lesson is never "superseded" by a different lesson's score.
  - Nothing is padded. The later days of the plan are often short because the remaining appropriate work depends on results
    the student hasn't produced yet. Each run recomputes, so those days fill as the student progresses. The notes say why a
    day is short.
- Books follow settings `books_per_day` (default 0): they are unscored and give no evidence, so never use them to fill
  short days. When the family wants them: non-fiction first, decodable Early Readers only after CVC opens.
- Today holds up to `daily` like any other day; there is no standing after-play cap. When the parent asks for a smaller or
  different day, use `--today-max N` for that run (or `state.json` "day_caps" {date: n}). If the student is done for the
  day, use `--tomorrow`.
- Play content (Logic+ songs, movement, feelings and habits) is assigned only when settings `include_play` is true;
  otherwise only the cognitive Logic+ categories are. Settings `exclude_titles` removes specific lessons.
- Diff into creates, moves and unassigns in one list-order pass, then verify and repair rounds. See Speed design.
  `EXACT_DAYS` = 2: today and tomorrow are mirrored exactly. A wanted lesson already sitting on any later day stays put,
  because the student can't see it until its date and each run re-aligns the next two days. This avoids many re-dates
  every time a day is skipped.
- Date picking ALWAYS uses the calendar's LEFT pane: taps in the right pane don't always register. `pick_date` steps the
  calendar forward first. A move that fails every round lands in "unplaceable" as a safety net.
- NEVER hand back (`finish.py`) until `pgrep -f process.py` is empty. A poll loop that times out is NOT the process exiting.
  The verification line lists any planned lesson dropped because the app has no such level; the next run plans something else.
- Re-dating a FINISHED assignment resets its green check in the app. Viewed (unscored) work is therefore remembered in
  `state.json` "attempts" ({"viewed": true}), not only in the app.
- Levels the app lacks are remembered in `state.json` "no_level" and never planned again. A new skill whose Main is in
  no_level is assigned at Basic (if the app has that level) instead of being skipped.
- The parent's observations are first-class data. Record them in `state.json` as soon as they are reported, then let the
  planner act on them.
  - "assisted": the score doesn't reflect the student's ability, because someone helped or it was brute-forced. That score
    is ignored and the lesson counts as new; a later attempt of their own counts. Example: {"Word Families": {...}}.
  - "struggled": the student couldn't do it. The lesson counts as a failed attempt (50%). Its easier Basic level comes next
    if the app has one; otherwise the lesson waits 14 days. This clears itself once a later score is 80 or more.
    Example: {"Delete Syllables": {"date", "note"}}.
  - Holds are the architect's call: at each review, start a readiness check early when the prerequisite evidence is solid,
    and say why in the plan file.
  - "hold" (generic): {"name": {"date", "until", "note", "match": regex on titles}}. The matching lessons are paused (no new
    lessons, no retries, no focus) until `until`, or `HOLD_CHECK_DAYS` at most (rule 3). Then comes a readiness check of one
    a day (or the hold's `ladder`) until `need` lessons score 80 or more, which lifts the hold to full pace; a first check
    under 70 extends it `HOLD_EXTEND_DAYS`, and the parent should be told.
  - "hold" for letter sounds: "letter_sounds" pauses every per-letter sound lesson (Beginning Sound x, Ending Sound x and
    Letter X Words, including their retries and focus practice). Letter names, tracing and phonological lessons continue.
  - "rollback": when the parent says the student doesn't get a concept at all, earlier scores in that strand stop counting.
    {"name": {"date", "note", "ladder": [[title, level], ...], "hold": regex}}: everything matching `hold` waits; the ladder
    is walked from its bottom step, one at a time, each scored 80 or more unassisted after `date` (under 70 rests 7 days,
    70-79 retries in 2 days). When the whole ladder passes, the rollback is lifted and the strand resumes.
  - Comprehension: the Kindergarten listening-comprehension strands (`planner.COMPREHENSION`: Key Ideas & Details,
    Informative Writing & Sequencing, Integrating Text & Illustrations) open from Age 3 through a TRIAL. Identify Characters
    is assigned alone, and the rest open only once it is proven (>= 80). They are sequential: one untested step per strand
    at a time. Social-emotional story books (Stories with People/Lessons) stay unmapped on purpose, since they are passive.
  - Coached results (the parent helped with strategy but didn't do it) go in "observations" and get a focus track, not an
    "assisted" flag.
  - "focus" with "repeat_ok": true allows lessons already done (re-teaching).
  - "focus" with "items" (a skill focus): an explicit practice list, `per_day` lessons a day for `days`. Repeats are
    deliberate, because the parent asked for more practice.
  - "focus" on a letter that is harder than the others: a light touch, not a drill. One extra practice-level lesson every
    3rd day (`FOCUS_EVERY_DAYS`), at most 3 per plan, for 14 days. The letter's normal ladder steps stay on their own schedule.

## Judgment each run (write it in the plan file)
- Difficulty verdict. Raise when most new Main first attempts are 90% or more for two weeks; then consider moving ELA up a
  grade as well. Lower when new Main first attempts fall under 70% for a week; then reduce new stages per day and lean on Basic.
- Anything the rules got wrong for the student. Fix the rule in `planner.py`, not by hand in the app.
- Whether the family's settings still fit (daily load, play content, books). Propose a change; the parent decides.
- Teacher settings that must stay as the parent set them (see `CLAUDE.local.md` if present). Teacher-Only Device stays OFF.
