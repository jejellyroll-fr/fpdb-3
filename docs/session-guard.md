# Session Guard

Limits for the session being played, and an alert when one is reached
([#395](https://github.com/jejellyroll-fr/fpdb-3/issues/395)).

The Session Guard is **informational only**: it reads imported hands and never
closes, sits out, clicks or otherwise touches a poker client. It gives no
bankroll advice.

## Using it

**Tools > Session Guard** opens the dialog. Tick the limits to watch, set them,
then **Start**:

| Limit | Fires when |
| --- | --- |
| Loss (money) / Loss (BB) | the session has lost at least that much |
| Win (money) / Win (BB) | the session has won at least that much |
| Session duration | that long has passed since the session's first hand |
| Hands | the session has played that many hands |
| Drawdown from peak (BB / money) | the result has fallen that far below the session's best point |

Drawdown example: the session reached +220 BB and now stands at -90 BB, a
drawdown of 310 BB, which fires a 300 BB drawdown limit.

While the guard runs, the status bar shows the session's result, duration and
hands; it turns red while a limit is reached, and a click reopens the dialog.
The dialog can be closed: the guard keeps running. **Stop** ends it; **Apply**
changes the limits of a running guard.

**Save as defaults** stores the ticked limits in `HUD_config.xml` (an optional
`<session_guard>` element) and the dialog offers them next time. The guard
itself always starts from the dialog: one session's configuration.

## Alerts

When a limit is reached a non-modal window names it and gives its current
value and threshold (`Loss (BB): 520.0 BB / 500.0 BB`), and the taskbar entry
flashes. It never takes the focus from a table and never blocks importing or
the HUD.

Each limit fires **once**. Then:

- **Acknowledge** quiets it until its value goes back under the threshold and
  crosses it again: a loss limit hit, recovered and hit again warns twice; a
  duration or hand count, which only grows, warns once.
- **Later** closes the window; the status bar stays red until acknowledged.
- **Reset alerts** arms every limit again; one still past its threshold fires
  at the next reading.
- A new session starts with every limit armed: an alert from the previous
  session is never carried over. Changing a limit's threshold re-arms it.

## Which session

The session is the Session Viewer's (`session_analytics.build_sessions`): the
hero's cash hands, split after a pause of more than 30 minutes or a change of
currency. The **current** session is the last one, while its last hand is less
than 30 minutes old; otherwise nothing is watched until the next hand starts a
new session.

- The hero is every enabled site's hero: its configured aliases, or else the
  players imported as hero.
- BB values follow the viewer's rule: if a hand of the session has no usable
  big blind (fixed limit), BB limits show as unavailable instead of being
  measured on part of the session. Money limits always apply.
- Money limits are in the session's currency (a session has only one).
- Duration runs on the clock from the first hand, not only when hands arrive.

The guard reads the database every 30 seconds through the main window's
connection, and ends its read transaction each time (never one left idle open
on PostgreSQL or MySQL). The query covers the last day of hands and is
widened, twice as far back each time, until the current session's first hand
is found: a long session is never measured from halfway. Hand times are read
as UTC on every backend (on MySQL whatever the connection's time zone), since
they are compared with the clock.

## Code

- `fpdb_3_legacy/session_guard.py` — the Qt-free model: `GuardLimits`,
  `SessionSnapshot`, `SessionGuard` (thresholds, firing, acknowledgement,
  reset), `current_session` / `load_current_session` and the database read
  `fetch_since` (the `sessionGuardHands` query: one hero id and a cut-off as
  parameters).
- `fpdb_3_legacy/session_guard_dialog.py` — the monitor (timer), the dialog,
  the status-bar indicator and the alert.

## Not included

Loss limits in buy-ins or as a percentage of a stake: express them in BB
(5 buy-ins of 100 BB = 500 BB).
