# Port Window

[Open Port Window](https://coolcode.ca/portwindow/) · Published cruise schedules with clear source years and personal planning buffers.

<!-- coolcode:guide -->
Choose a port and its published schedule year, search any vessel in that source, and filter dates. Pacific coverage includes Vancouver, Victoria and Juneau. Maritime coverage includes Halifax, Charlottetown, Saint John, Sydney and Louisbourg, with an explicit availability notice when an official schedule cannot yet be downloaded.

Each port keeps its own year and last successful check. Sydney and Louisbourg currently publish 2026 schedules, while the Pacific sources publish 2027. Past sailing dates are labelled as a prior season. A fresh download of an old schedule does not turn it into an upcoming schedule. Halifax's public source is currently inaccessible to the collector; Charlottetown says its schedule is coming soon, and Saint John says the 2027 release is expected in January. Their official links stay prominent.

Use the daily calendar to compare scheduled entries and peak overlap among intervals with both times. It does not estimate crowds or passenger numbers. Set your own minutes after arrival and before departure to estimate a planning window; your operator decides disembarkation and all-aboard times. Blank times remain unknown, 24:00 means the end of that date, and separate overnight rows remain separate.

Favourites stay in this tab until you explicitly save them on this device. Export complete filtered intervals as an ICS calendar file, including source years, source links and each port's real check time. Historical captures retain their original coverage. The changes view records observed additions, removals and time changes.

Sources are checked independently every day. If one fails, its earlier verified rows and their original check time remain visible while other ports can update. An unavailable port without a prior capture shows no fabricated calls. Always confirm plans with the official port source and your cruise operator.
<!-- /coolcode:guide -->

## Build and check

No paid service or API key is required. Python 3.12+, PyMuPDF 1.26.6 for collection/tests and Node 24 are used in CI.

    python3 -m pip install -r scripts/requirements.txt
    python3 scripts/refresh.py
    node --test tests/*.test.mjs
    python3 -m unittest discover -s tests -v
    python3 scripts/build.py
    python3 -m http.server 8000 --directory dist

The builder is offline. It gives HTML-referenced CSS, JavaScript imports and the public capture one deterministic content version, preventing a returning browser from mixing old modules with a newly published interface. Browser checks use tests/browser-requirements.txt and CHROMIUM_PATH; CI uses installed google-chrome on Ubuntu 24.04. Do not commit dist.

## Actual source coverage

These are observations from the November 25, 2026 integration check, not fixed future counts:

| Port | Official source | Published coverage |
| --- | --- | --- |
| Vancouver | [CLAA schedule index](https://claalaska.com/?page_id=1250) | 369 entries, 2027; October 2, 2026 edition |
| Victoria | [CLAA schedule index](https://claalaska.com/?page_id=1250) | 320 entries, 2027; October 2, 2026 edition |
| Juneau | [CLAA schedule index](https://claalaska.com/?page_id=1250) | 699 entries, 2027; October 2, 2026 edition |
| Halifax | [Port Halifax](https://www.porthalifax.ca/cruise/cruise-schedule/) | No complete verified capture; normal collection returns HTTP 403 |
| Charlottetown | [Port Charlottetown](https://portcharlottetown.com/upcoming-cruise/) | Official page says the schedule is coming soon |
| Saint John | [Port Saint John](https://www.sjport.com/cruise-schedule) | 2026 season ended; official page expects its 2027 schedule in January |
| Sydney | [Port of Sydney](https://www.sydneyport.ca/cruiseschedule) | 90 entries, April 9–November 3, 2026; tentative April 29 edition |
| Louisbourg | [Port of Sydney / Louisbourg](https://www.sydneyport.ca/cruiseschedule) | Six entries, September 9–October 15, 2026; no edition date printed |

The Halifax browser attempt also failed; indexed search excerpts were incomplete and were not used to fabricate a full snapshot. Charlottetown's vendor retail hours are not vessel arrival/departure times and are not ingested. No current reliable official call schedule was found for Digby or Summerside; Pictou's reviewed page still described 2025, so those ports are not represented as current coverage.

Each source organization owns its original publication. Port Window normalizes factual dates/times with attribution and links, does not mirror PDFs, and does not claim endorsement or a blanket open-data licence. Source access uses ordinary public requests and respects robots.txt. It does not bypass authentication or challenges.

## Collection and failure handling

config/ports.json declares each port's adapter, source, IANA timezone and record floor. The CLAA adapter discovers the current linked PDF, verifies port/year/weekday alignment and reads positioned calendar blocks. The Sydney/Louisbourg adapter follows the current labelled download links, reads explicit full-year rows and verifies the named PDF title. The public HTML adapter accepts dated vessel tables with arrival/departure headers; ambiguous schedule years are rejected. Missing values stay null. Ship labels preserve source abbreviations and footnotes.

Sources fail independently. A malformed PDF, access denial, robots restriction, unknown layout or unexpected count drop retains that port's earlier verified rows. Its status becomes retained, its last successful checked_at stays unchanged, and its attempted_at advances. A newly configured failed source is unavailable with zero rows and no successful check. A verified release notice is pending: its availability-check time is recorded separately from a nonexistent schedule check. No valid source and no prior rows means the refresh fails without writing public files.

web/data/index.json uses schema 2 with per-port season, status, checked_at, attempted_at, availability_checked_at, source edition and coverage count. Historical schema-1 Pacific captures remain readable. web/data/status.json is a small hashed probe with:

- checked_at: the **oldest successful check among ports with available schedules**, including retained data.
- attempted_at: the latest collector attempt; this is not a data-freshness timestamp.
- state: ok only when every configured source has a successfully checked schedule; otherwise partial.
- successful_count, failed_count and pending_count, plus per-port status and real check times.
- count, port_count, configured_port_count and the actual published seasons.

Thus a blocked source cannot silently receive a fresh check date. If all sources fail but old rows exist, the public availability report can update while the schedule check remains old. The homepage/watchdog uses checked_at, never attempted_at. The app warns when an available schedule is older than 72 hours.

Up to six earlier changed captures and 100 observed differences are retained. Captures retain original seasons and port coverage. Source editions are not replaced by run dates. Ship-name/date changes appear as removal/addition; pagination changes alone are not time changes.

## Expand or customize

Edit config/ports.json to add a reviewed official port with a unique code, display name, region, IANA timezone, adapter and defensible minimum_calls floor. The CLAA source has an explicit configured year; Maritime PDF/HTML adapters derive the year from the actual publication. A new HTML layout or ambiguous season must be reviewed before its data is accepted. The frontend derives ports, years, searches and counts from the source data, not a starter list.

Run collection, tests and build; review the per-port outcomes and commit source/configuration/captures to main. Successful main builds deploy through GitHub Actions. Historical captures preserve earlier coverage when changing sources or seasons. A pending release will be accepted automatically only if its resulting publication matches the validated adapter; otherwise it remains visibly unavailable for review.

Personal search text, buffers and favourites stay in the visitor's browser. Storage happens only when Save is clicked. Sources and standard CoolCode aggregate visit reporting make ordinary public requests.

## Schedules and integration

.github/workflows/pages.yml runs daily at 10:43 UTC. Its source step is “Refresh official port schedules”. It reports individual source failures as visible workflow warnings, tests, commits the validated capture/status and deploys Pages. The independent CoolCode scheduler should dispatch pages.yml daily. The separate allowlisted schedule guard renews managed schedules; a successful guard is not evidence of fresh source data.

tool.json supplies the card, source note and /portwindow/data/status.json probe. The probe paths checked_at and count are unchanged, but the label is now “Oldest available schedule checked”. Central integration must update the guide and named collection step. The existing /portwindow/ Cloudflare route needs no secret or additional API.

## Limits

This is a published-call planning tool, not a live arrival board, booking engine, fare finder or occupancy service. Past seasons are historical information. Unknown or non-same-day intervals are excluded from timed overlap and calendar export. Calendar files are dated exports, not subscriptions; re-export after checking for changes.
