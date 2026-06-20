## Goal

Make `launchd/install.sh` generate the LaunchAgent plist robustly for any path.
The installer filled the template with raw `sed` substitution, which breaks when
a resolved path (interpreter, repo, DB, or log dir) contains characters that are
significant to XML (`&` `<` `>` `"`) or to `sed` (`|` `\` `&`): the result is
invalid XML or a mis-substituted value. Switch to the structured `plutil` tool
already used to lint the file. (Addresses upstream PR review feedback.)

## Files Changed And Why

### `launchd/install.sh`

- Replaced the `sed` substitution block with `cp template → dest` followed by
  `plutil -replace` calls. `plutil` writes through the property-list serializer,
  so values are stored literally and any XML-significant character is escaped
  correctly — no manual escaping, no delimiter hazard.
  - Scalars by key: `Label`, `WorkingDirectory`, `StandardOutPath`,
    `StandardErrorPath` via `plutil -replace <key> -string "$VALUE"`.
  - The entire `ProgramArguments` array is replaced in one shot with
    `plutil -replace ProgramArguments -json "$PA_JSON"`, where `$PA_JSON` is
    built by the already-resolved interpreter
    (`"$PYTHON" -c 'import json,sys; print(json.dumps([...]))'`). Building the
    JSON with `json.dumps` escapes every argv element (including lone
    backslashes and quotes) safely.
- Added a placeholder guard: after substitution, `grep -q '__[A-Z_]*__'` fails
  the install if any `__TOKEN__` survived, because a wrong-but-valid plist still
  passes `plutil -lint`. `set -eu` and the existing `plutil -lint` are retained.

## Behavior Changes

- The installed plist is now correct for paths containing `&`, `<`, `>`, `"`,
  `|`, or `\`; previously such a path produced invalid XML or a wrong value.
- The generated plist no longer carries the template's explanatory XML comments:
  `plutil` rewrites the file canonically and drops comments. This only affects
  the installed copy (which already says "do not hand-edit"); the template keeps
  its comments and remains the documented source of truth.
- No change to `key_logger.py`, to `uninstall.sh`, or to what the agent runs.

## Approach

Prefer the structured macOS-native tool (`plutil`, already a dependency of this
script via `-lint`) over hand-rolled escaping. Replace scalars by key path and
the array as a whole — never by element index — and build the array's JSON with
the interpreter that is already resolved and validated earlier in the script, so
no second utility and no shell-quoting minefield is introduced.

## Alternatives Considered

### Per-index `plutil -replace ProgramArguments.<N>`
Rejected: on macOS this **inserts** at index N rather than overwriting it.
Replacing indices 0, 1, 3 of the 4-element template array yields a 7-element
array with a stray literal `__DB__` — and `plutil -lint` still reports OK, so the
breakage would ship silently. Replacing the whole array via `-json` avoids this.

### `/usr/libexec/PlistBuddy -c "Set :ProgramArguments:N ..."`
Rejected: PlistBuddy's `-c` argument does its own quote/backslash parsing and
silently drops a lone `\` from a value. It also adds a second tool. The
`plutil -replace -json` route has neither problem.

### Escape values, keep `sed`
Rejected: correct double-escaping (XML then `sed`) in POSIX `sh` is fiddly and
error-prone, and the reviewer's preferred option was a structured plist tool.

## Assumptions

- `plutil` and a working `$PYTHON` are available — both already required by this
  script (it lints with `plutil` and resolves the interpreter's real path with
  `$PYTHON -c`), so no new dependency.
- The template defines `Label`, `WorkingDirectory`, `StandardOutPath`,
  `StandardErrorPath`, and a 4-element `ProgramArguments`
  (`[python, script, --sqlite-file, db]`); the install script's key paths and
  JSON layout track that structure.

## Shortcuts Or Tradeoffs

- `ProgramArguments` is rebuilt wholesale rather than edited element-by-element,
  which couples the install script to the array's intended shape — but that is
  precisely what the per-index insert bug forces, and the layout lives in one
  place in both files.
- The installed plist loses the template's comments (see Behavior Changes); an
  acceptable cost for correct, injection-safe generation.

## Known Limitations

- `plutil -lint` validates XML well-formedness, not semantic correctness, so it
  cannot by itself catch a wrong-but-valid plist; the placeholder guard covers
  the most likely such mistake (an unsubstituted token).
- macOS-only, like the rest of the `launchd/` tooling.

## Key Decisions

- Generate the plist with structured `plutil`, never raw `sed`.
- Replace `ProgramArguments` as a whole via `-json` (built with `json.dumps`),
  never by element index (which inserts, not overwrites).
- Add a hard placeholder guard before `plutil -lint`.
