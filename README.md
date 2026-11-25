# Port Window

[Open Port Window](https://coolcode.ca/portwindow/) · Published cruise schedules with personal planning buffers.

<!-- coolcode:guide -->
Choose Vancouver, Victoria or Juneau, search any vessel in the source schedule and filter a date range. The daily calendar counts scheduled entries and shows peak overlap among entries with both times. It does not estimate crowds, passengers or live ship positions.

Set your own minutes after arrival and before departure to see a personal planning window. Your cruise operator decides disembarkation and all-aboard times; verify these directly. Missing times remain unknown. A 24:00 departure is midnight at the end of that date. Separate overnight entries are not silently joined.

Mark favourites, explicitly save them on this device and export the filtered complete intervals as a calendar file. The export includes published times and source links; it does not turn your personal buffers into official deadlines. A capture selector preserves earlier source coverage when a schedule changes, and the changes view records observed additions, removals and time changes.

Schedules are checked daily against Cruise Line Agencies of Alaska's public PDFs. The checked date, PDF edition and sailing dates have different meanings. Open the original PDF linked from each entry and reconfirm with your operator before travel.
<!-- /coolcode:guide -->

## Build and check

No paid service or API key is required. Python 3.12+, PyMuPDF 1.26.6 for collection/tests and Node 24 are used in CI.

    python3 -m pip install -r scripts/requirements.txt
    python3 scripts/refresh.py
    node --test tests/*.test.mjs
    python3 -m unittest discover -s tests -v
    python3 scripts/build.py
    python3 -m http.server 8000 --directory dist

The static builder is offline. Browser checks use tests/browser-requirements.txt and CHROMIUM_PATH; CI uses the installed google-chrome on Ubuntu 24.04. Do not commit dist.

## Sources and collection

The [CLAA 2027 schedule index](https://claalaska.com/?page_id=1250) links the original calendars. The initial release covers 369 Vancouver, 320 Victoria and 699 Juneau entries in the October 2, 2026 editions; these are data observations, not assumed future totals. Cruise Line Agencies of Alaska owns the original publications. This application presents normalized factual dates/times with attribution and page links and does not mirror PDF files or imply endorsement. No blanket open-data licence is claimed.

The collector checks robots.txt, discovers each reviewed port's PDF from the index, verifies port/year/weekday alignment, reads positioned calendar blocks and matches time positions around the separator. It rejects ambiguous blocks, unexpected count drops, malformed files and access errors. Blank times remain null. Ship labels retain source abbreviations. ISO UTC calendar fields are derived from each port's IANA timezone, including date rollover at 24:00.

A failed collection preserves the previous good files. The full capture is web/data/index.json; the small web/data/status.json probe contains the successful checked_at, entry count, port count, season and capture hash. Checked timestamps advance only after all configured sources validate. Source editions do not advance merely because a collector ran.

Changed source captures retain up to six older captures, including their original season and port coverage. Observed changes are limited to the latest 100 entries and begin at the first capture. Changed ship names or dates appear as removal/addition. Page-layout changes alone are not reported as changed sailing times.

## Expand or customize

Edit config/ports.json to add a port from the official index with its exact code, display name, IANA timezone and a defensible minimum_calls floor. Every configured port must use the reviewed calendar layout and pass parser tests. Search, filters and counts derive from the resulting data; adding a port does not require a new UI list. To move to a new season, review its index URL and update the collector's reviewed URL check, season and test fixtures; do not guess unpublished schedules.

Run collection, tests and build, then commit configuration, code and validated captures to main. Successful main builds deploy through GitHub Actions. No repository secret is needed. Personal search text, planning buffers and favourites remain in the visitor's browser; storage happens only when Save is clicked.

## Schedules and integration

.github/workflows/pages.yml collects daily at 10:43 UTC, validates, tests the real interface, commits source captures and deploys Pages. Its named source step is “Refresh official CLAA port schedules”. The independent CoolCode server scheduler should dispatch pages.yml daily. A separate allowlisted schedule-guard.yml renews managed schedules; a guard is not evidence of fresh data. The UI warns when a capture is older than 72 hours.

tool.json supplies the hub card, source note and /portwindow/data/status.json freshness probe. Hub registry, guide import, README, audit, sitemap, watchdog collector target and Cloudflare routing are maintained centrally. The existing /portwindow/ Worker route needs no secret or server-side API.

## Coverage limits

This is a planned-call calendar for three selected ports, not a booking engine, live arrival board, itinerary guarantee, fare finder or occupancy service. Unknown intervals are excluded from timed overlap and ICS exports. Entry counts can include separate overnight rows. Calendar files can become outdated and are not subscribed calendars; re-export after checking for updates. Official source failures can delay publication without deleting the last good capture.
