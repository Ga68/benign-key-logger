## Goal

Replace the module-level mutable runtime state with explicit configuration and application objects so the code is easier to reason about, test, and audit while preserving the current CLI and logging behavior.

## Files Changed And Why

### `key_logger.py`

Reorganizes the script around:

- a `Config` dataclass for user-facing runtime settings
- a `KeyLoggerApp` class for mutable runtime state and behavior
- parser construction and argument parsing that return a `Config` instead of mutating module globals

The refactor moves SQLite lifecycle management, batching, permission hardening, WAL setup, key-state tracking, and event processing onto the app object. Pure helper functions such as key canonicalization and stringification remain top-level functions.

## Behavior Changes

The goal of this change is structural rather than user-visible. The existing public CLI and runtime behavior are intended to remain the same:

- same CLI flags and defaults
- same validation for `--full-events --no-sqlite`
- same batching policy
- same permission hardening
- same optional WAL behavior
- same modifier-state behavior
- same explicit SQLite shutdown behavior

## Approach

Split the previous globals into two categories:

- configuration chosen by the user at startup
- mutable runtime state created while the logger runs

That split is now encoded directly in the program structure instead of being implicit in module-level variables. `main()` now parses args into a `Config`, constructs a `KeyLoggerApp`, and runs it.

## Alternatives Considered

- Keep extending the module-global design. Rejected because the script had already accumulated enough startup, batching, permission, WAL, and shutdown state that the implicit shared state was becoming harder to audit.
- Break the script into multiple files immediately. Rejected because the repo’s transparency goal still benefits from keeping the implementation in a single file for now.
- Introduce a broader framework or config layer. Rejected because the immediate need was state clarity, not generality.

## What Was Tried And Did Not Work

Earlier incremental fixes improved behavior but left the module itself acting as the runtime container. That was serviceable for small changes but increasingly awkward once CLI parsing, batched writes, WAL support, and explicit shutdown were all present.

## Assumptions

- A single-file implementation is still desirable for this repository’s auditability goal.
- Explicit object boundaries improve understandability more than they harm the original “just read one script” simplicity.

## Shortcuts Or Tradeoffs

The refactor keeps some advanced tuning values as top-level constants instead of moving everything into `Config`. That keeps the public config surface smaller, but means not every knob lives in the same place yet.

## Known Limitations

- There is still no automated test suite.
- Startup transparency could still be improved by logging the effective configuration more explicitly.
- The README still needs some wording cleanup to match the current code style exactly.

## Key Decisions

- Use `Config` plus `KeyLoggerApp` as the two primary explicit objects.
- Preserve the single-file layout.
- Keep pure helper functions top-level.
- Preserve the public CLI and runtime semantics while improving the internal state model.
