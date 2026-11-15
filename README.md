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
