## Goal

Improve the project’s transparency by making the effective runtime configuration more visible at startup, showing CLI defaults directly in `--help`, and aligning the README with the current code structure and trust model.

## Files Changed And Why

### `key_logger.py`

Uses `argparse.ArgumentDefaultsHelpFormatter` so default values are visible in the CLI help output, and adds startup log lines that summarize the effective configuration and output paths before the listener starts.

### `README.md`

Updates the stale description of the code style, notes that the help output now shows defaults and that startup logs summarize the active configuration, and adds a small audit checklist that highlights the main trust-relevant properties of the tool.

## Behavior Changes

- `python3 key_logger.py --help` now shows default values for the exposed CLI options.
- Normal startup now logs the active sink configuration and output paths before listening begins.
- The README now better matches the current implementation style and provides a concise audit checklist for users who want a quick trust review.

## Approach

Surface information that was already implicit rather than adding new behavior:

- expose defaults through the parser formatter
- log the effective runtime config derived from the parsed `Config`
- document the trust-relevant properties in one short checklist

## Alternatives Considered

- Keep relying on the README and source inspection alone. Rejected because the program itself should make its active behavior obvious at runtime.
- Add a dedicated `--dry-run` or `--print-config` mode. Rejected for now because a startup summary already covers the main transparency need with less interface expansion.

## Assumptions

- A short startup summary improves trust more than it adds noise.
- The help output is one of the primary audit surfaces for a small CLI tool like this.

## Shortcuts Or Tradeoffs

The startup summary is intentionally concise and logs only the major user-facing settings and paths, not every internal tuning constant.

## Known Limitations

- The project still does not have an automated test suite.
- The README still depends on users to understand that OS-level secure input behavior is platform-specific.

## Key Decisions

- Show CLI defaults directly in `--help`.
- Log the effective config at startup.
- Add an explicit audit checklist to the README instead of leaving the trust model scattered across sections.
