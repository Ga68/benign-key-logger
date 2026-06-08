## Goal

Let the logger start automatically at login so it can accumulate key/bigram
frequency stats continuously, without the user having to remember to launch it.
Do this without weakening the project's benign/auditable posture: no new
capability, no change to defaults, and no `launchctl`/`subprocess` code added to
`key_logger.py` itself.

## Files Changed And Why

### `launchd/local.benign-key-logger.plist.template` (new)

The LaunchAgent definition, with `__PLACEHOLDER__`-style path tokens so the repo
holds no machine-specific absolute paths. Notable, deliberate choices encoded in
it:

- **User LaunchAgent, not a LaunchDaemon.** It loads into the `gui/<uid>` domain
  (the logged-in session). A daemon runs outside the user's GUI session and would
  see no keyboard events, so an agent is the only correct option here.
- **Absolute `--sqlite-file` plus `WorkingDirectory`.** `launchd` runs with
  `cwd=/`, and the script's `--sqlite-file` default is the *relative*
  `key_log.sqlite`. Left alone, the DB would be written to `/key_log.sqlite`. The
  agent passes an absolute DB path; `WorkingDirectory` is a backup for the same
  reason.
- **Privacy-preserving invocation only.** `ProgramArguments` is just the
  interpreter, the script, and `--sqlite-file <abs path>`. No `--stdout`,
  `--raw-events`, `--trigrams`, or `--file`, so the background run uses the same
  aggregate-counts-only default as a foreground run.
- **`RunAtLoad` = true** (start at login); **`KeepAlive` = { Crashed = true }**
  (restart on abnormal exit, not on clean logout). A comment notes this does
  *not* rescue the silent no-permission case (see below), since that is not a
  crash.
- **`StandardErrorPath`/`StandardOutPath`** under `~/Library/Logs/benign-key-logger/`
  capture the script's startup config summary and "starting to listen" line
  (logged to stderr). These hold only status lines, never keystrokes (stdout echo
  is off).

### `launchd/install.sh` (new)

Generates the concrete plist from the template (path substitution via `sed`),
`plutil -lint`s it, and loads it with the modern
`launchctl bootstrap gui/$(id -u)` (booting out any prior copy first, so re-runs
are idempotent). It then prints the one thing it cannot do for the user: the
exact **resolved real interpreter path** to add under Input Monitoring. The real
path is computed with `python -c 'os.path.realpath(sys.executable)'` because TCC
attaches the grant to the resolved binary (`.../bin/python3.11`), not the
`python` symlink the agent invokes. Interpreter location is overridable via
`PYTHON_OVERRIDE`.

### `launchd/uninstall.sh` (new)

`launchctl bootout` + remove the installed plist. Leaves captured data untouched
and does not alter System Settings; reminds the user how to revoke the grant.

### `README.md`

New "Running automatically at login (macOS LaunchAgent)" subsection under Usage
(agent-vs-daemon rationale, the manual Input-Monitoring grant, the silent-failure
warning, install/verify/uninstall commands, and the conda-rebuild caveat). Three
Audit Checklist bullets: auto-start is opt-in and self-contained; the launch
tooling is readable plain text with no network and a bounded set of write
targets; and `key_logger.py` is unchanged by this feature.

## Behavior Changes

- No change to `key_logger.py` and no change to any default. Nothing runs
  automatically unless the user explicitly runs `sh launchd/install.sh`.
- Once installed, the same script runs at login with counts-only storage, writing
  to the repo's `key_log.sqlite` and status logs to `~/Library/Logs/benign-key-logger/`.

## Approach

Keep all auto-start machinery as separate, auditable ops files in `launchd/` and
leave the logger pristine. Reuse the existing privacy-preserving CLI defaults
rather than adding any new flag or mode. Make the install/uninstall path
idempotent and self-describing, and put the unavoidable manual step (granting the
interpreter keyboard access) front and centre in both the installer output and
the README, because on a `launchd`-started process macOS neither inherits the
Terminal grant nor prompts, and pynput fails silently without it.

## Alternatives Considered

### Add `--install-launch-agent` to `key_logger.py`
Rejected: it would introduce `subprocess`/`launchctl` into the single auditable
file, eroding the "no shelling out" property the benign audit relies on, and push
the script to write outside its data path.

### LaunchDaemon instead of LaunchAgent
Rejected: a daemon runs outside the user's GUI login session and would capture no
keystrokes; it also needs root. An agent in `gui/<uid>` is the correct scope.

### Minimal signed `.app` bundle for a stable TCC identity
Considered and documented as a more robust option (it survives conda env
rebuilds because the grant binds to a stable bundle id rather than the
interpreter binary). Not built: it adds an `Info.plist` + code-signing step, and
for a single user a one-time re-grant after an env rebuild is simpler. Left as a
documented future hardening.

### Docs-only manual install (no scripts)
Rejected in favor of the turnkey scripts at the user's request; the scripts are
short and readable, and the manual `launchctl` commands are still shown in the
README for anyone who prefers them.

## Assumptions

- The conda `keylogger` env interpreter is at
  `~/opt/miniconda3/envs/keylogger/bin/python` (overridable via `PYTHON_OVERRIDE`).
- The user will manually grant Input Monitoring (and, if needed, Accessibility)
  to the resolved interpreter binary — this cannot be automated and is required
  for any capture at all.
- Paths involved contain no `|` character (the `sed` substitution delimiter);
  true for the standard home/repo locations here.

## Shortcuts Or Tradeoffs

- The label and default interpreter path are constants near the top of the
  scripts; changing them is a one-line edit rather than a CLI flag.
- `KeepAlive` restarts only on crash, so a clean but unwanted exit would stay
  down until next login. This is intentional to avoid fighting manual stops, and
  is irrelevant to the silent-permission case anyway.

## Known Limitations

- **Silent failure without permission:** if Input Monitoring is not granted, the
  agent runs but logs nothing and does not error; `KeepAlive` cannot detect this.
  The README's verification step (watch the DB grow) is the intended check.
- **Conda env rebuilds invalidate the grant:** macOS binds the permission to the
  resolved `python3.11` binary; recreating the env requires re-granting once.
- macOS-only, like the rest of the project's OS-specific guidance.

## Key Decisions

- A user LaunchAgent in `gui/<uid>`, never a LaunchDaemon.
- `key_logger.py` is untouched; all launch tooling lives in `launchd/`.
- Absolute `--sqlite-file` (+ `WorkingDirectory`) so the DB never lands in `/`.
- Reuse the counts-only privacy defaults; introduce no new invasive flag.
- Grant the resolved interpreter binary directly; `.app`-bundle identity is
  documented but not built.
- Modern `launchctl bootstrap`/`bootout`; idempotent install.
