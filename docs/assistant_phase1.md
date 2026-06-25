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
ASSISTANT_RUNNING_SPEED_THRESHOLD=0
ASSISTANT_MIN_STOP_MINUTES=1
ASSISTANT_MAX_ROWS=5000
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

The response shows:

- whether the assistant is enabled
- whether an OpenAI key is configured
- configured speed/good/bad tag paths
- whether those configured tags were actually found
- latest and oldest history timestamps
- compact suggestions when a configured tag path does not match a real tag

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

## Production Calculation

Production uses the configured good/bad counter tags from `opc_tag_values`.

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
- `total_down_minutes`
- `longest_stop`
- `average_stop_minutes`
- `stops`

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

## Curl Examples

Diagnostics:

```bash
curl http://127.0.0.1:8000/api/assistant/diagnostics
```

Chat:

```bash
curl -X POST http://127.0.0.1:8000/api/assistant/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How was production today?"}'
```
