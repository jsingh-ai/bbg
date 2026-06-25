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

## Configuration

Add these values to `.env` as needed:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
ASSISTANT_ENABLED=false
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
```

Notes:

- If `ASSISTANT_ENABLED=false` or `OPENAI_API_KEY` is blank, the assistant still works in deterministic mode.
- OpenAI is only used to turn backend analysis into natural language.
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

Chat responses also include `raw.route`, which shows the deterministic router decision, resolved system, section terms, time range, and matched rule.

The assistant service also exposes:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/assistant/version" | ConvertTo-Json -Depth 20
```

That route returns backend JSON metadata such as `raw_route_supported`, `started_at`, `process_id`, and best-effort git commit/branch information.

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

Machine speed is treated as context-only by default for general process ranking. It can still appear as stop context, but it is removed from the visible ranked process-variable lists unless the user explicitly asks about speed, stops, downtime, or machine state.

State, status, and mode tags are also context-only by default for general process questions. Dependent speed and performance tags such as `current speed` and `cycle performance` are moved to context by default unless the user explicitly asks about speed, performance, or motion.

Repeated names are disambiguated with contextual labels derived from OPC path segments. For example:

- `nozzle - 3 / flow rate`
- `nozzle - a-side / current speed`
- `web tension / currentPressure`

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
- The assistant does not keep long-lived server-side conversation memory in Phase 1.

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
