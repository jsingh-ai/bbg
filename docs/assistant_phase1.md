# Assistant Phase 1

## Scope

Phase 1 adds a read-only ChatGPT-style production/process analyst to the BBG OPC Dashboard.

It can answer questions such as:

- How was production today?
- Compare today to yesterday.
- How many stops did I have in the last 24 hours?
- What was my longest stop?
- What changed the most in the last hour?
- What changed around the last stop?
- What happened in the unwinder, dancer, format, or storage cylinder section?

## Safety

- The assistant is read-only.
- It only uses `SELECT` queries.
- It does not write to MySQL.
- Codex should not run tests, builds, or runtime validation commands for this feature set because verification happens on the deployed VM.
- It does not acknowledge alerts.
- It does not edit recipes, layouts, sections, or tag visibility.
- It does not expose `OPENAI_API_KEY` to the frontend.
- Assistant endpoints expose operational diagnostics and should be protected by the same network/auth boundary as the dashboard.

## Configuration

Add these values to `.env` as needed:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT_SECONDS=10
OPENAI_MAX_OUTPUT_TOKENS=350
OPENAI_TEMPERATURE=0.1
ASSISTANT_ENABLED=false
ASSISTANT_LLM_SEND_RAW=false
ASSISTANT_EXPOSE_RAW_RESPONSE=false
ASSISTANT_DEFAULT_TIMEZONE=America/Chicago
ASSISTANT_SPEED_TAG_PATH=Global PV/200 - format/state/machine speed
ASSISTANT_GOOD_BAGS_TAG_PATH=Global PV/info/state/shift: good
ASSISTANT_BAD_BAGS_TAG_PATH=Global PV/info/state/shift: bad
ASSISTANT_TOTAL_BAGS_TAG_PATH=Global PV/info/state/endless counter
ASSISTANT_PRODUCTION_MODE=auto
ASSISTANT_RUNNING_SPEED_THRESHOLD=0
ASSISTANT_MIN_STOP_MINUTES=1
ASSISTANT_MAX_ROWS=5000
ASSISTANT_EXCLUDED_SECTION_KEYS=i,alarm system
ASSISTANT_EXCLUDED_PATH_CONTAINS=/i/o/,alarm system
ASSISTANT_EXCLUDED_TAG_TERMS=counter,count,number of,good,bad,total,shift,job,active alarms,max severity,storageWear
ASSISTANT_EXCLUDED_STATE_TERMS=state,status,mode
ASSISTANT_STATE_CONTEXT_ENABLED=true
ASSISTANT_DEPENDENT_SPEED_TERMS=current speed,cycle performance
ASSISTANT_SPEED_CONTEXT_ENABLED=true
ASSISTANT_CONTEXT_ENABLED=true
ASSISTANT_CONTEXT_MAX_TURNS=5
ASSISTANT_CONTEXT_MAX_AGE_MINUTES=120
ASSISTANT_CONTEXT_MAX_CONVERSATIONS=200
ASSISTANT_CONTEXT_MESSAGE_MAX_CHARS=500
```

Notes:

- If `ASSISTANT_ENABLED=false` or `OPENAI_API_KEY` is blank, the assistant still works in deterministic mode.
- OpenAI is optional and only used to turn backend analysis into natural language.
- If `ASSISTANT_ENABLED=true`, computed assistant context may be sent to OpenAI.
- The frontend never receives `OPENAI_API_KEY`.
- SQL, DB credentials, environment values, and secrets are not sent to OpenAI.
- LLM output is bounded by `OPENAI_MAX_OUTPUT_TOKENS`, and the deterministic fallback answer is used if OpenAI fails or times out.
- If `ASSISTANT_LLM_SEND_RAW=false`, OpenAI receives a reduced payload made from the backend answer inputs, cards, tables, warnings, and compact route metadata.
- If `ASSISTANT_LLM_SEND_RAW=true`, OpenAI receives the fuller backend-computed `raw` analysis object. Use this only if you are comfortable sending detailed OPC labels, paths, counters, and timing context to OpenAI.
- If `ASSISTANT_EXPOSE_RAW_RESPONSE=false`, chat responses return only compact `raw.route` and `raw.llm` metadata to the frontend. Set it to `true` only when you need full raw debug output during VM troubleshooting.
- Assistant chat requests are bounded: `message` is limited to 2000 characters and `conversation_id` is limited to 128 safe characters.
- All calculations happen in backend code first.

## Diagnostics

Use the diagnostics endpoint first when calibrating tag paths:

```bash
curl http://127.0.0.1:8000/api/assistant/diagnostics
```

PowerShell:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/diagnostics" | ConvertTo-Json -Depth 20
```

The response shows:

- whether the assistant is enabled
- whether an OpenAI key is configured
- configured speed/good/bad tag paths
- whether those configured tags were actually found
- latest and oldest history timestamps
- compact suggestions when a configured tag path does not match a real tag

Chat responses also include `raw.route`, which shows the deterministic router decision, resolved system, section terms, time range, matched rule, and follow-up metadata under `raw.route.followup`.

## Shared Intent Vocabulary

The assistant uses a centralized intent vocabulary before any database analysis or optional LLM wording step.

Shared term groups cover:

- production: production, bags, good bags, bad bags, scrap, rejects, quality, shift production, output
- stops: stop, stops, stopped, downtime, longest stop, machine stopped
- change analysis: changed the most, most changed, unstable, variation, uncertainty, moving the most, bouncing
- around-stop analysis: changed around stop, changed before stop, around the last stop, before the last stop, when speed went to 0
- context categories: speed, state/status/mode, alarms, counters, PLC/I/O/system health
- compare modifiers: compare, vs, versus, better than, worse than

`compare` is treated as a modifier, not as production by itself.

Examples:

- `Compare today to yesterday` defaults to production because no other subject is present.
- `Compare speed this week` does not route to production.
- `Compare stops this week` does not route to production; stop comparison is not implemented yet.
- `Compare unwinder today to yesterday` resolves the unwinder section instead of production.

PLC/I/O matching is token-safe:

- `io` only matches as a standalone token.
- `i/o` only matches explicitly.
- `production` does not accidentally trigger PLC/I/O context.

The assistant service also exposes:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/version" | ConvertTo-Json -Depth 20
```

That route returns backend JSON metadata such as `raw_route_supported`, `started_at`, `process_id`, best-effort git commit/branch information, and `conversation_memory` stats. The memory stats do not expose stored messages.

## Follow-Up Context

The assistant now supports lightweight follow-up context using in-memory state only.

- It stores only the last 5 route summaries per `conversation_id`.
- It stores truncated user messages plus route-level context: intent, time range, compare flag, resolved system, section terms, subject, stop time, and a timestamp.
- User messages are capped by `ASSISTANT_CONTEXT_MESSAGE_MAX_CHARS`.
- The process keeps at most `ASSISTANT_CONTEXT_MAX_CONVERSATIONS` active conversations and evicts the least recently used conversation when the limit is exceeded.
- It does not store full assistant responses.
- It does not store DB rows.
- It does not store OpenAI prompts or responses.
- It does not survive backend restart.
- It does not write to MySQL.
- If multiple uvicorn workers are used, follow-up context may not be consistent across workers.
- For reliable Phase 1 follow-ups, run one backend process.

Frontend behavior:

- `AssistantPanel` sends a stable `conversation_id` for the current browser chat session.
- The browser stores only the `conversation_id` in `sessionStorage` under `bbg_assistant_conversation_id`.
- Refreshing the page keeps follow-up continuity within the same browser session.
- Chat messages are not stored in `sessionStorage`.
- `Clear Chat` only clears visible messages and the input box.
- `New Conversation` clears the local chat view, asks the backend to clear the old in-memory conversation when the clear endpoint is available, rotates the browser-side `conversation_id`, and updates `sessionStorage`.
- Use `New Conversation` when you want to reset follow-up context.

Debug behavior:

- `raw.route.followup.used_context` tells you whether a follow-up inherited context.
- `raw.route.followup.reason` explains why context was or was not applied.
- `raw.route.followup.original_intent` and `original_time_range` show the first route decision before memory was applied.
- `raw.route.followup.resolved_intent` and `resolved_time_range` show the final route decision used for analysis.
- `raw.route.followup.previous_*`, `inherited_*`, `changed_intent`, and `changed_time_range` fields show what was reused and what changed.

Follow-up inheritance is intentionally narrow:

- previous production plus a time-only follow-up inherits production for the new time range
- previous stops plus a bags/production follow-up switches to production and inherits the previous time range
- previous production plus a stops follow-up switches to stops and inherits the previous time range
- previous around-stop/process analysis plus a section follow-up keeps the process intent and adds the new section
- previous section plus a time-only follow-up keeps the section and uses the new time range
- unrelated messages such as `compare speed` after a production answer do not inherit production context

### Missing Tag Warnings

If a configured production or speed tag is missing:

- the assistant will not guess and use a fuzzy match for calculations
- diagnostics will return likely alternatives
- you should update the matching `.env` tag path manually

This is intentional. Diagnostics suggestions are advisory only and are not automatically used for calculations.

### Updating `.env` Tag Paths

If diagnostics shows a missing required tag:

1. copy the suggested `opc_path`
2. update the relevant `.env` setting
3. restart the backend
4. rerun `/api/assistant/diagnostics`

## Process Taxonomy

The assistant uses a deterministic taxonomy for known systems and sections before any language-model wording layer.

Examples:

- `unwinder` and `winder` resolve to unwinder sections
- `dancer` and `dance` resolve to dancer sections
- `storage cylinder` resolves to storage cylinder sections
- `format` and `machine speed` resolve to format sections
- `plc`, `io`, `i/o`, `system health`, and `plc temperature` resolve to the PLC/I/O/system group

This prevents ordinary short words from incorrectly resolving to section `i`.

## Process Filters

For process-analysis questions, the assistant applies default filters to suppress system-health noise, counters, and zero-range rows.

Default filter env vars:

```env
ASSISTANT_EXCLUDED_SECTION_KEYS=i,alarm system
ASSISTANT_EXCLUDED_PATH_CONTAINS=/i/o/,alarm system
ASSISTANT_EXCLUDED_TAG_TERMS=counter,count,number of,good,bad,total,shift,job,active alarms,max severity,storageWear
```

Short excluded section keys are matched safely:

- if the excluded term is 1-2 characters long, it must match the full normalized section key exactly
- example: `i` excludes only section key `i`
- it does not exclude `020 - unwinder`, `290 - storage cylinder`, `360 - bottom sealing`, or `A00-I16 - general`

These filters apply to:

- most changed parameter analysis
- values around stop analysis
- section summaries

They do not apply to:

- production summary
- production debug
- production candidates
- explicit PLC / I/O / system-health style questions

Machine speed is treated as context-only by default for general process ranking. It can still appear as stop context, but it is removed from the visible ranked process-variable lists unless the user explicitly asks about speed, performance, motion, or machine-speed behavior.

State, status, and mode tags are also context-only by default for general process questions. Dependent speed and performance tags such as `current speed` and `cycle performance` are moved to context by default unless the user explicitly asks about speed, performance, or motion.

The assistant uses category-specific bypass flags instead of one broad override:

- speed/performance questions can enable speed context without automatically enabling state, alarms, counters, or PLC/I/O
- state/status questions can enable state context without pulling speed rows into ranked process movement
- alarm questions can bypass alarm-system exclusions without re-enabling counters or PLC/I/O noise
- counter questions can expose counters without changing unrelated filter categories
- PLC/I/O questions can bypass `/i/o/` exclusions without changing alarm, counter, or speed handling

Stop and downtime questions do not automatically allow speed or dependent-speed rows to become ranked process-cause candidates. Those rows stay in context unless the user explicitly asks for speed/performance behavior.

Context rows are deduplicated by stable OPC-path-first keys, and repeated answer labels are disambiguated with section context when needed.

Repeated names are disambiguated with contextual labels derived from OPC path segments. For example:

- `nozzle - 3 / flow rate`
- `nozzle - a-side / current speed`
- `web tension / currentPressure`

Around-stop defaults are intentionally strict. For `What changed around the last stop?`, ranked before/after process tables exclude:

- machine speed, which is treated as the stop marker
- dependent speed/performance rows such as `current speed` and `cycle performance`
- state/status/mode rows
- counters and production counts
- alarms and max-severity rows
- PLC/I/O/system-health rows
- zero-range and zero-score rows

Those categories are kept in context buckets when useful:

- `raw.context.machine_speed`
- `raw.context.dependent_speed_changes`
- `raw.context.state_changes`
- `raw.context.alarm_changes`
- `raw.context.counter_changes`
- `raw.context.plc_changes`

Explicit category questions are independent:

- speed questions show machine/dependent-speed context clearly, but speed is still not described as a process cause
- state/status questions can allow state rows without also allowing speed, alarms, counters, or PLC/I/O rows
- alarm questions can show alarm context without enabling counters, speed, state, or PLC/I/O
- counter questions can show counter context without enabling speed, state, alarms, or PLC/I/O
- PLC/I/O questions can show PLC/I/O context without enabling unrelated categories

Visible rows and context rows are deduped by lowercase `opc_path` first. If `opc_path` is missing, the fallback key is lowercase `section_key|label`. When duplicates are found, the assistant keeps the row with the strongest range/score, then sample count.

Query limiting is reported in `raw.limits` and in a `Query Limits` table when applicable. Most-changed analysis uses SQL aggregation per tag and applies the safety cap after SQL ranking by movement/range. Around-stop analysis first selects candidate tag IDs, then fetches rows for those candidate tags around the stop. If `raw.limits.truncated=true`, the answer should be treated as capped rather than complete.

## Production Calculation

Production uses the configured good/bad counter tags from `opc_tag_values`.

Optional total-counter support:

- `ASSISTANT_TOTAL_BAGS_TAG_PATH`
- `ASSISTANT_PRODUCTION_MODE=auto`

When good/bad semantics look suspicious, the assistant still shows those values with warnings but can also show a `Total Counter` card from the configured total-production counter.

Plain production questions such as `How was production today?` no longer auto-compare to yesterday. Comparison is only added when the user explicitly asks, such as `Compare today to yesterday` or `today vs yesterday`.

Method:

1. Load minute-resolution numeric samples in the selected range.
2. Sort by `created_at`.
3. Add only positive counter increments.
4. If a counter value decreases, treat that as a reset and continue from the new baseline.

Returned production metrics:

- `good_bags`
- `bad_bags`
- `total_bags`
- `bad_rate_pct`
- `first_timestamp`
- `last_timestamp`

For production validation, you can also inspect the raw counter behavior with:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/production-debug" | ConvertTo-Json -Depth 20
```

This shows:

- first and last samples for the configured good/bad counters
- positive-delta sum used for production
- raw first-to-last delta
- reset count detected in the window

You can also inspect likely production counter candidates with:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/production-candidates" | ConvertTo-Json -Depth 20
```

Use that endpoint to tune:

- `ASSISTANT_GOOD_BAGS_TAG_PATH`
- `ASSISTANT_BAD_BAGS_TAG_PATH`
- `ASSISTANT_TOTAL_BAGS_TAG_PATH`

If bad delta is much larger than good delta or the bad rate is extremely high, the assistant now returns sanity warnings so you can verify the configured production counters.

The Assistant panel also includes a compact `Production Candidates` section that calls `/api/assistant/production-candidates` and shows candidate labels, sections, deltas, and OPC paths.

Diagnostics suggestions are not automatically used for calculations. This is intentional so production and downtime analytics never silently switch to the wrong OPC tag.

## Stop Detection

Stop detection uses the configured speed tag from `opc_tag_values`.

Method:

1. A machine is considered running when speed is `> ASSISTANT_RUNNING_SPEED_THRESHOLD`.
2. A stop starts when speed transitions from running to `<= threshold`.
3. A stop ends when speed transitions back above threshold.
4. Duration is calculated in minutes from timestamps.
5. Stops shorter than `ASSISTANT_MIN_STOP_MINUTES` are excluded.

Returned stop metrics:

- `stop_count`
- `transition_stop_count`
- `downtime_period_count`
- `total_down_minutes`
- `longest_stop`
- `average_stop_minutes`
- `stops`

If the first in-range speed sample is already at or below the stop threshold, the assistant marks that downtime period as open at the start of the selected range instead of pretending it observed the transition into the stop.

If the last speed sample is still at or below the threshold, the final stop is marked open-ended.

The machine speed tag remains the stop marker. It is not presented as proof of process cause in around-stop analysis.

Around-stop analysis keeps categories independent:

- default stop questions exclude counters, alarms, PLC/I/O, state/status values, dependent speeds, zero-range rows, and the speed marker from ranked process-candidate tables
- explicit state questions can show state/status changes without automatically promoting speed rows
- explicit speed questions keep machine speed and dependent speed/performance rows in the `Speed / Performance Context` table and still avoid presenting them as process-cause proof
- visible context tables are deduplicated before they are returned

## Parameter Change Ranking

Most-changed parameter analysis only uses numeric rows:

- `value_kind = 1`
- `value_num IS NOT NULL`

For each tag, Phase 1 calculates:

- sample count
- min
- max
- average
- standard deviation
- range
- normalized movement score

Movement score:

```text
range / max(abs(avg), 1)
```

To avoid ranking obvious production counters as unstable process parameters, Phase 1 excludes paths and labels containing terms like:

- good
- bad
- total
- count
- counter
- shift
- job

## Known Limitations

- Only one machine is assumed right now and the assistant uses `DEFAULT_MACHINE_ID`.
- All timing is approximate to minute-level because the source history is minute resolution.
- Correlation is not proof of cause.
- Tag paths may need adjustment in `.env`.
- Section matching is string-based and depends on current section/tag naming.
- Follow-up memory is process-local only, capped to 5 recent turns, and does not survive backend restart.

## Recommended First Tests

- `How was production today?`
- `How many stops in the last 24 hours?`
- `What changed around the last stop?`

## PowerShell Test Commands

These are for VM validation only.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/diagnostics" | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/version" | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/production-debug" | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/production-candidates" | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"How was production today?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"Compare today to yesterday"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"How many stops in the last 24 hours?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"What changed the most in the last hour?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"What happened in the unwinder today?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"What changed around the last stop?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"Show me state changes around the last stop"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"Show me speed changes around the last stop"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"message":"What happened in the dancer today?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"conversation_id":"followup-prod","message":"How was production today?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"conversation_id":"followup-prod","message":"What about this week?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"conversation_id":"followup-stops","message":"How many stops this week?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"conversation_id":"followup-stops","message":"What about bags?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"conversation_id":"followup-stop-section","message":"What changed around the last stop?"}' | ConvertTo-Json -Depth 20
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/chat" -Method Post -ContentType "application/json" -Body '{"conversation_id":"followup-stop-section","message":"What about unwinder?"}' | ConvertTo-Json -Depth 20
```
