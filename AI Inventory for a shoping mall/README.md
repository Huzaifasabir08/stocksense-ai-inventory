# StockSense: AI Inventory for a Shopping Mall

Full-stack local inventory application for Nowshera Shopping Mall.

## Start

Double-click `Start-StockSense.bat`. It uses the Python 3 launcher, waits for the
actual server to become ready, and then opens `http://127.0.0.1:8765`. Reopening it
reuses the same server. A detached supervisor restarts the server after unexpected
exits; closing the launcher or browser does not stop the server. Startup logs are
in `.runtime/server.log` and `.runtime/launcher.log`.

The frontend and API run in one Python server; no separate frontend build or
backend process is needed. Login and API requests use the current website origin.
`STOCKSENSE_PORT` can override the default port for both server and launcher.
Occupied ports produce an error without killing unrelated processes or silently
switching to a different port. The parent folder's launcher forwards to this
complete project rather than its incomplete copy. Databases are not reset.

For terminal startup without opening a browser: `python launch.py --no-browser`.

Manager: `manager@stocksense.local` / `manager123`

Staff: `staff@stocksense.local` / `staff123`

The SQLite database is created automatically as `stocksense.db`. Set `AI_DISABLED=1` before starting to demonstrate the AI failure state; normal inventory pages and forms remain available.

## Validation

Run `python test_acceptance.py` to validate grounded answers, confirmation safety, negative-stock protection, staff privacy, and AI failure resilience.

Run `python test_startup.py` to check repeated launches, both login roles, APIs,
conflict handling, automatic crash recovery, and preservation of the existing
database. This test deliberately terminates only this project's server to verify
recovery; active in-memory sessions must sign in again afterward.
