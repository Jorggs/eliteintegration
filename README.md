# Elite Dangerous Telemetry - Home Assistant Integration

A native Home Assistant custom integration (not a YAML package) that creates
all the same sensors as the `elite_dangerous_processed.yaml` package, but as
proper HA entities configured through the UI, grouped under a single device.

## Why this instead of the YAML package

- **UI-based setup** -- Settings -> Devices & services -> Add Integration ->
  "Elite Dangerous Telemetry" -> enter your root topic. No YAML editing.
- **One MQTT subscription set, shared state** -- a single coordinator
  subscribes to every topic once and all ~124 entities read from one shared
  in-memory dict, rather than each entity independently parsing JSON.
- **Grouped as one device** -- "Elite Dangerous Commander" -- so all sensors
  show up together in the UI instead of a flat list.
- **Entity IDs match the YAML package** -- e.g. `sensor.ed_flags`,
  `binary_sensor.ed_docked` -- verified against the original file, so
  dashboards/automations built against the YAML package need little to no
  rework if you switch. This is pinned explicitly (via `suggested_object_id`)
  independently of the display name, so it doesn't matter what you rename
  the device to.
- **Clean naming, no prefix duplication** -- entities use the modern
  `has_entity_name` pattern: each entity's own name is just the suffix
  (e.g. "Balance", "Current System"), and Home Assistant combines it with
  the device name for display (e.g. "Elite Dangerous Commander Balance").
  Rename the device to anything you like -- e.g. "ED" -- without ending up
  with a doubled-up "ED ED Balance".

## Requirements

- Home Assistant's built-in **MQTT** integration must already be configured
  (Settings -> Devices & services -> MQTT), pointed at the same broker your
  ED-MQTT-Telemetry app publishes to.
- The app's Dashboard format set to **Processed** (Settings -> Data tab).

## Installation

1. Copy the `custom_components/elite_dangerous` folder into your Home
   Assistant config directory, so you end up with:
   ```
   <config>/custom_components/elite_dangerous/__init__.py
   <config>/custom_components/elite_dangerous/manifest.json
   <config>/custom_components/elite_dangerous/... (etc)
   ```
2. Restart Home Assistant.
3. Settings -> Devices & services -> **Add Integration** -> search
   "Elite Dangerous Telemetry".
4. Enter the root topic (default `Telemetry` -- matches the app's default).
5. Done -- entities appear immediately under the "Elite Dangerous Commander"
   device, and populate as soon as MQTT messages arrive (retained topics
   mean most will show a value right away, even before the game is running).

## What's included

- All Dashboard/Location/Ship sensors (Flags, Fuel, Pips, Cargo, Legal
  State, Balance, current System/Station/Body/Position, Ship type/name/jump
  range)
- Ship Loadout sensors: Fuel/Reservoir/Cargo Capacity, Ship Ident, Rebuy
  Cost, Hull Value, Modules Value
- Docking sensors from the docking journal events: Docking State (Idle,
  Requested, Granted, Denied, Cancelled, Timed Out, Docked), Docking Pad,
  Docking Station, Docking Denied Reason
- All 8 rank categories (level + progress %)
- All Statistics-derived sensors (jumps, distance, profits, footfalls,
  spending breakdown, exobiology, combat)
- All 32 Flags bits + 20 Flags2 bits as binary sensors
- The computed summary sensors (Vehicle Type, Flight Mode, Combat Status,
  Location Type, Status Summary, Critical Warnings) -- computed directly
  from the flag bits rather than round-tripping through other entities'
  states, so there's no update-ordering race between platforms

## Lighting and automation sensors (v1.3.0)

Added for driving lights (e.g. WLED) from game state. These read the app's
per-event `Journal/<Event>` topics, so the app's Journal format must be
**Processed** (the default).

- **Jump Star Class** / **Jump Star Type** -- the star you're about to jump
  to (from `FSDTarget`, or `StartJump` when it's newer), e.g. `K` /
  "K (Yellow-Orange) Star". Attributes: `name`, `category`, `rgb_color`
  (an LED-friendly colour for the class), `scoopable`, `jet_cone`.
- **Current Star Class** / **Current Star Type** -- the star of the system
  you're in, known once you've jumped into it. Same attributes.
- **Jump Target System**, **Jumps Remaining**
- Binary sensors: **Jump Target Scoopable**, **Jump Target Jet Cone**
  (neutron stars and white dwarfs), **Current Star Scoopable**, **Wanted**
- **Fuel Percent**, **Cargo Percent** (need the ship's Loadout capacities)
- **GUI Focus Name** -- e.g. Galaxy Map, System Map, FSS Mode
- **Last Journal Event**

### Journal events in automations

Every *live* journal event is also fired on Home Assistant's event bus as
`elite_dangerous_journal`, with the journal fields as event data. Retained
messages replayed after a restart don't fire, so old events never replay.

```yaml
triggers:
  - trigger: event
    event_type: elite_dangerous_journal
    event_data:
      event: UnderAttack
```

Useful ones for momentary light flashes: `UnderAttack`, `ShieldState`,
`HeatWarning`, `Interdicted`, `EscapeInterdiction`, `Died`, `CommitCrime`,
`Bounty`, `MissionCompleted`, `FSSDiscoveryScan`, `Touchdown`, `Liftoff`.

## Trade route from Spansh (v1.4.0)

Finds the most profitable trade route from where you are, using the
[Spansh trade planner](https://spansh.co.uk/trade), and keeps it on your
dashboard. No account or API key is needed.

**How it works**

- Spansh plans routes from a **station**, so the start is the station you're
  docked at (or the last one you docked at). Until you've docked once since
  Home Assistant started, the status is `waiting for station`.
- A new route is fetched when you **dock** (live `Docked` events only, so a
  restart doesn't trigger one), when you press **Trade Route Refresh**, and
  a few seconds after you change a setting (once a route exists).
- Docking at a stop on the current route **doesn't** re-plan it: the route
  moves on to the next hop. Docking at the last stop plans a new route.
- If Spansh finds nothing from your station -- usually because it has no
  market prices for it, which is common for Odyssey settlements and new
  colony stations -- the route starts from the nearest suitable station in
  the same system instead (matching your pad, planetary and fleet carrier
  settings; up to 3 are tried). The `start_note` attribute says so, and the
  first **Trade Buy Station** is that station.
- Your cargo capacity, credits (starting capital) and jump range come from
  the telemetry; the pad size follows your ship when set to Auto. No
  request is sent until the cargo capacity is known (Spansh finds nothing
  without it); an unknown balance is treated as unlimited credits.
- Spansh usually answers in under a minute, but can queue jobs for a few
  minutes when busy. The status shows `fetching` meanwhile.

**Settings** (all kept across restarts)

| Entity | What it does |
|---|---|
| `select.…_ed_trade_pad_size` | Auto (large pad only for ships that need one), Large only, Any |
| `number.…_ed_trade_max_hops` | Stops on the route, 1-10 |
| `number.…_ed_trade_max_hop_distance` | Max ly between two stations; **0 = your ship's jump range** |
| `number.…_ed_trade_max_arrival_distance` | Max ls from the arrival star |
| `number.…_ed_trade_max_market_age` | Prices older than this mark the route as stale (see notes) |
| `switch.…_ed_trade_planetary` | Include planetary ports |
| `switch.…_ed_trade_fleet_carriers` | Include fleet carriers |
| `switch.…_ed_trade_permit_systems` | Include permit-locked systems |
| `switch.…_ed_trade_prohibited` | Include prohibited goods |
| `switch.…_ed_trade_avoid_loops` | Don't visit a station twice |
| `switch.…_ed_trade_auto_refresh` | Fetch a new route when you dock |
| `button.…_ed_trade_refresh` | Fetch a route now |

(`…` is `elite_dangerous_commander`.)

**Sensors**

- **Trade Route** -- total route profit (CR). Attributes: `status`, `error`,
  `start_system`, `start_station`, `start_note`, `total_hops`, `next_hop`, `hops` (the full
  route), `oldest_market_age_hours`, `stale`, `last_updated`, `request` (exactly
  what was sent to Spansh), `spansh_job`, `spansh_url`.
  `hops`/`request` aren't written to the recorder database, so the route
  doesn't bloat history.
- **Trade Route Status** -- `idle`, `waiting for station`, `waiting for
  ship data` (cargo capacity not known yet), `fetching`, `ready`, `no
  route`, `error` (reason in the `error` attribute). `spansh_url` opens the
  same route on the Spansh website.
- For the next hop: **Trade Buy Station**, **Trade Sell Station**, **Trade
  Sell System**, **Trade Commodity** (attribute `cargo` lists the full load,
  as Spansh often tops the hold up with a second commodity), **Trade Hop
  Distance**, **Trade Hop Profit**, **Trade Profit Per Ton**.
- **Trade Market Age** -- age in hours of the oldest price on the route.

Each entry in `hops` has: `hop`, `from_system`, `from_station`, `to_system`,
`to_station`, `distance_ly`, `to_arrival_ls`, `commodity`, `buy_price`,
`sell_price`, `amount`, `profit`, `profit_per_ton`, `cumulative_profit`,
`from_market_age_hours`, `to_market_age_hours`, `commodities`.

**Dashboard example** (Markdown card, one line per hop, next hop in bold):

```yaml
type: markdown
title: Trade route
content: >
  {% set r = 'sensor.elite_dangerous_commander_ed_trade_route' %}
  {% set hops = state_attr(r, 'hops') or [] %}
  {% set nxt = state_attr(r, 'next_hop') %}
  **{{ states('sensor.elite_dangerous_commander_ed_trade_route_status') | title }}**
  {%- if state_attr(r, 'error') %} -- {{ state_attr(r, 'error') }}{% endif %}
  {%- if state_attr(r, 'start_note') %}

  _{{ state_attr(r, 'start_note') }}_{% endif %}

  {% for h in hops %}
  {%- set line = h.hop ~ '. Buy ' ~ h.amount ~ 't ' ~ h.commodity ~ ' at ' ~ h.from_station
     ~ ' → ' ~ h.distance_ly ~ ' ly → sell at ' ~ h.to_station ~ ' (' ~ h.to_system ~ ')'
     ~ ' · ' ~ '{:,}'.format(h.profit) ~ ' CR' %}
  {{ '**' ~ line ~ '**' if h.hop == nxt else line }}

  {% endfor %}
  {% if hops %}Total: {{ '{:,}'.format(states(r) | int(0)) }} CR
  {%- if state_attr(r, 'stale') %} ⚠ prices up to {{ state_attr(r, 'oldest_market_age_hours') }} h old{% endif %}{% endif %}
```

**Notes and limits**

- Spansh has **no documented API**. This sends the same requests as the
  Spansh trade planner page, with the field names other community tools
  use. If Spansh changes them, the status shows `error` with the reason;
  nothing else in the integration is affected.
- Spansh can only require a **large** pad, so Auto/Large only are the useful
  choices; medium-pad ships can use any station with a market.
- **Max Market Age** doesn't filter Spansh's search (its field for that isn't
  known); it only flags the route as `stale` when a price on it is older.
- Spansh's prices come from players' EDDN uploads, so a route can be out of
  date. Check the market when you dock.

## Migrating from the YAML package

If you're replacing `elite_dangerous_processed.yaml` with this integration:

1. Remove (or comment out) the YAML package file.
2. Install and configure this integration as above.
3. Restart Home Assistant.

Because entity_ids match, most dashboards and automations should keep
working. Double-check anything that referenced `sensor.ed_state_data` or
`sensor.ed_dashboard_data` directly (the old raw-JSON MQTT sensors) -- those
don't exist in this integration since there's no JSON blob to expose; every
value is its own entity from the start.

## Notes

- This has been tested by importing every module against a real installed
  `homeassistant` package and unit-testing all MQTT message handlers and
  sensor compute functions with synthetic data -- but it has **not** been
  run inside an actual live Home Assistant instance. Please report anything
  that doesn't behave as expected once installed for real.

## Tests

```
pip install pytest-homeassistant-custom-component
pytest
```

The trade-route tests run a real Home Assistant instance with MQTT and
Spansh mocked.
