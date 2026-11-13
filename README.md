# khankids-driver

A mastery-based lesson planner for a young child using
[Khan Academy Kids](https://learn.khanacademy.org/khan-academy-kids/), run jointly by a parent and an AI coding agent
([Claude Code](https://claude.com/claude-code)).

**This is not a standalone tool.** It is meant to be co-managed with an agent. The scripts are the agent's hands. They read
the app, apply a plan and verify it. The parent and the agent handle the judgment:

- **The parent** watches the child and reports what the scores can't show, for example "guessed through it", "a sibling
  helped" or "ordinals aren't clicking yet". The parent also sets the limits: daily load, app settings, what's off-limits.
- **The agent** turns those reports into planner state (holds, rollbacks, focus tracks, assisted scores). It runs the
  process, judges difficulty at each review and writes its reasoning to `plans/` for the parent to read. It also repairs
  the driver when a Khan Kids, iOS or WebDriverAgent update moves a button or changes the screen layout.

Khan Academy Kids has no public API. The driver works through the app's **teacher view** on a real iPad or iPhone, using
[WebDriverAgent](https://github.com/appium/WebDriverAgent). It reads the class progress reports, plans the next lessons
from the child's results, assigns them with dates, and checks that the app matches the plan.

The planning model is deliberately strict:

- **Mastery gates.** 90%+ on a lesson's Main level is mastered; under 80% is retried at the easier Basic level.
- **Two results before moving on.** One good score from a preschooler is noise; advancing a strand needs a second result.
- **Holds and readiness checks** for skills the child isn't ready for, re-tested on a short cycle.
- **Small days.** A few lessons a day, readiness checks first, one letter, then the ranked queue.
- **The app mirrors the plan.** Each run diffs the plan against the app and creates, moves or parks assignments, then
  re-reads the app to verify.

The rules live in [`planner.py`](planner.py) and are explained in the Claude Code skill
[`.claude/skills/populate-student/SKILL.md`](.claude/skills/populate-student/SKILL.md).

> Not affiliated with or endorsed by Khan Academy. It automates the teacher view of your own class account on your own
> devices; use it in line with Khan Academy's terms.

## Requirements

- [Claude Code](https://claude.com/claude-code), or another coding agent that reads `CLAUDE.md` and skills. The repo
  is organized around it: `CLAUDE.md` gives the agent the device and app mechanics, and the `populate-student` skill
  gives it the planning process.
- A Mac with Xcode and an Apple Developer team (a free personal team works) to sign the WebDriverAgent runner.
- [Homebrew](https://brew.sh) `libimobiledevice` for the `iproxy` USB tunnel: `brew install libimobiledevice`.
- Python 3 (standard library only).
- An iPad or iPhone with Khan Academy Kids signed in to a teacher (class) account, with one student in the class.

## Setup

The agent can do these steps with you. Open the folder in Claude Code and ask it to set things up.

1. Clone WebDriverAgent into the repo folder and build the runner once for your device (`WebDriverAgent-iphone/` for an iPhone):

   ```bash
   git clone https://github.com/appium/WebDriverAgent.git
   ```

   Build it with `xcodebuild build-for-testing` (see the arguments in `start-wda.sh`), or open the project in Xcode and
   run the `WebDriverAgentRunner` test once.
2. Copy the settings template and fill it in (device ids, signing, teacher profile name, Google account):

   ```bash
   cp local.env.example local.env
   ```

3. Start from an empty state:

   ```bash
   cp state/state.example.json state/state.json
   ```

`local.env`, `state/` and `plans/` are gitignored: they hold your device ids and your child's data.

## Usage

Plug in the device, open the folder in Claude Code, and talk to it:

- "Populate the app." The `populate-student` skill starts WebDriverAgent, runs the process, verifies the result, hands the
  device back and logs the review in `plans/`.
- "Count 4 Objects was a guess." / "Hold off on letter sounds for a week." / "Make tomorrow a light day." The
  agent records your report in `state/state.json` and the next plan follows it.
- "Why did you assign that?" The reasoning is in the plan file, and the agent can explain any rule in `planner.py`.

Keep notes about your child (age, observations, your decisions) in a `CLAUDE.local.md`. Claude Code loads it
automatically, and git ignores it.

Under the hood, the agent runs these commands:

```bash
./start-wda.sh                                   # iPad; for an iPhone: ./start-wda-iphone.sh and prefix commands with KK_DEVICE=iphone
nohup python3 -u process.py --preview > state/process.out 2>&1 &   # read and plan, change nothing
nohup python3 -u process.py > state/process.out 2>&1 &             # apply and verify (ends with "VERIFIED: app matches the plan")
python3 finish.py                                # hand the device back on the profile picker and stop WDA
```

Screen geometry is measured per device in `kk.G` (iPad 1180x820 and iPhone 956x440, both landscape). A different device
or a redesigned app screen needs new measurements, and the agent can take them from the accessibility tree.

## Security and privacy

- **WebDriverAgent has no authentication.** Anyone who can reach its port can take screenshots of the device and tap
  on it. Over USB the `iproxy` tunnel listens only on `127.0.0.1`. When the iPhone falls back to Wi-Fi, WebDriverAgent
  is reachable from the whole local network while the runner is up. Use Wi-Fi only on a network you trust, and let
  `finish.py` (or `stop-wda*.sh`) stop the runner when the run is done.
- **Sign-in is automated.** `fill.enter_teacher()` picks your Google account and taps "Continue" in the Khan Kids
  teacher sign-in flow. Watch the first run, and check `KK_GOOGLE_ACCOUNT_MATCH` matches only your account.
- **`local.env` is sourced by bash.** Keep it to plain `KEY=value` lines.
- **Your child's data stays local.** `local.env`, `state/`, `plans/` and `CLAUDE.local.md` are gitignored. Never
  force-add them, and check `git status` before you push.

## License

[MIT](LICENSE)
