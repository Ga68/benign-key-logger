## Goal

Reduce SQLite overhead during logging by batching commits instead of forcing a full transaction commit on every single keystroke.

## Files Changed And Why

### `key_logger.py`

Adds buffered SQLite commit state, a hybrid flush policy, and a final forced flush on clean shutdown. The logging path now inserts rows immediately but commits only when the pending write count reaches the configured threshold or enough time has elapsed since the last commit.

### `README.md`

Documents the new batching policy so users understand the performance/durability tradeoff and the specific thresholds the logger uses.

## Behavior Changes

- SQLite writes are committed every 50 events or every 5 seconds, whichever comes first.
- A clean process shutdown forces a final flush of any remaining pending SQLite writes.
- Keystrokes may remain uncommitted briefly during normal operation, but the logger avoids paying full SQLite commit cost on every event.

## Approach

Use a simple hybrid policy based on both event count and elapsed time:

- event threshold: 50 writes
- time threshold: 5 seconds

The event threshold is chosen to be roughly consistent with a fast typist around 100 WPM, which keeps the pending batch size small while still reducing commit churn substantially.

## Alternatives Considered

- Keep per-event commits. Rejected because the overhead is disproportionate for a local analytics logger and can make the listener the throughput bottleneck.
- Use a time-only threshold. Rejected because a burst of typing could still accumulate a larger-than-necessary batch before the timer elapsed.
- Use an event-only threshold. Rejected because very light typing would leave small batches pending for too long.

## Assumptions

- Losing at most a small recent batch on a crash is acceptable for this repository's keyboard-usage-analysis purpose.
- A 5-second window is short enough to keep the durability risk bounded while still materially reducing commit frequency.

## Shortcuts Or Tradeoffs

The implementation uses `atexit` for clean-shutdown flushing rather than building a more elaborate signal-handling layer. That covers normal interpreter exits and unhandled exceptions, but not abrupt termination such as `kill -9`.

## Known Limitations

- This commit does not enable WAL mode.
- SQLite writes are still performed synchronously from the listener path; only the commit frequency changes.

## Key Decisions

- Use a hybrid threshold instead of time-only or count-only batching.
- Pick 50 events for consistency with roughly 100 WPM typing over a 5-second window.
- Force a final flush on clean shutdown so ordinary exits do not leave pending rows behind.
