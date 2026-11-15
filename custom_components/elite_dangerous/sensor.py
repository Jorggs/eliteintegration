"""Sensor platform for the Elite Dangerous Telemetry integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    GUI_FOCUS_NAMES,
    RANK_CATEGORIES,
    RANK_ICONS,
    RANK_NAMES,
    SHIP_NAMES,
    classify_star,
)
from .entity import EliteDangerousEntity


def _bit(value: int, n: int) -> bool:
    return (int(value or 0) & (1 << n)) != 0


def _rank_name(category: str, level: int) -> str:
    names = RANK_NAMES.get(category, [])
    if 0 <= level < len(names):
        return names[level]
    return names[-1] if names else "Unknown"


DOCKING_DENIED_REASONS = {
    "NoSpace": "No pad free",
    "TooLarge": "Ship too large",
    "Hostile": "Station hostile",
    "Offences": "Offences",
    "Distance": "Too far away",
    "ActiveFighter": "Fighter deployed",
    "RestrictedAccess": "Restricted access",
    "NoReason": "No reason given",
}

DOCKING_ICONS = {
    "Idle": "mdi:rocket-outline",
    "Requested": "mdi:radio-tower",
    "Granted": "mdi:check-circle",
    "Denied": "mdi:close-octagon",
    "Cancelled": "mdi:cancel",
    "Timed Out": "mdi:timer-off",
    "Docked": "mdi:space-station",
}


def _denied_reason(data):
    code = data.get("docking_denied_reason")
    if not code:
        return None
    if code in DOCKING_DENIED_REASONS:
        return DOCKING_DENIED_REASONS[code]
    # Unknown code: split CamelCase into words
    return "".join(" " + c if c.isupper() else c for c in code).strip()


def _current_star_class(data):
    """Star class of the system you're in: known when the last hyperspace
    jump you started was to the system you're now in."""
    if data.get("last_jump_system") and data.get("last_jump_system") == data.get("current_system"):
        return data.get("last_jump_star_class")
    return None


def _star_attrs(class_fn):
    def attrs(data):
        info = classify_star(class_fn(data))
        if not info:
            return {}
        return {k: v for k, v in info.items() if k != "class"}
    return attrs


def _star_type(class_fn):
    def value(data):
        info = classify_star(class_fn(data))
        return info["name"] if info else None
    return value


def _percent(value_key, capacity_key):
    def value(data):
        cap = data.get(capacity_key)
        if not cap:
            return None
        return round(100 * float(data.get(value_key) or 0) / float(cap), 1)
    return value


def _jump_target_class(data):
    return data.get("jump_target_star_class")


# Each entry: (unique_id, name, unit, device_class, icon, compute_fn(data)[, attrs_fn(data)])
def _build_descriptors():
    d = []

    # ---- Ship / commander ----
    d.append(("ed_current_system", "Current System", None, None, "mdi:map-marker-star",
              lambda data: data["current_system"] or "Unknown"))
    d.append(("ed_current_station", "Current Station", None, None, "mdi:space-station",
              lambda data: data["current_station"] or "In Space"))
    d.append(("ed_current_body", "Current Body", None, None, "mdi:circle",
              lambda data: data["current_body"] or "Unknown"))
    d.append(("ed_current_ship", "Current Ship", None, None, "mdi:space-invaders",
              lambda data: data["ship_type_display"] or SHIP_NAMES.get(
                  (data["ship_type"] or "").lower(),
                  (data["ship_type"] or "Unknown").replace("_", " ").title())))
    d.append(("ed_ship_name", "Ship Name", None, None, "mdi:rename-box",
              lambda data: data["ship_name"] or "Unnamed"))
    d.append(("ed_jump_range", "Jump Range", "ly", None, "mdi:map-marker-distance",
              lambda data: round(data["jump_range"], 2)))
    d.append(("ed_fuel_capacity", "Fuel Capacity", "t", None, "mdi:gas-station",
              lambda data: data["fuel_capacity"]))
    d.append(("ed_reservoir_capacity", "Reservoir Capacity", "t", None, "mdi:gas-station-outline",
              lambda data: data["reservoir_capacity"]))
    d.append(("ed_cargo_capacity", "Cargo Capacity", "t", None, "mdi:package-variant",
              lambda data: data["cargo_capacity"]))
    d.append(("ed_ship_ident", "Ship Ident", None, None, "mdi:identifier",
              lambda data: data["ship_ident"]))
    d.append(("ed_rebuy_cost", "Rebuy Cost", "CR", "monetary", "mdi:cash-refund",
              lambda data: data["rebuy"]))
    d.append(("ed_hull_value", "Hull Value", "CR", "monetary", "mdi:ship-wheel",
              lambda data: data["hull_value"]))
    d.append(("ed_modules_value", "Modules Value", "CR", "monetary", "mdi:cog",
              lambda data: data["modules_value"]))
    # ---- Docking ----
    d.append(("ed_docking_state", "Docking State", None, None,
              lambda data: DOCKING_ICONS.get(data["docking_state"], "mdi:space-station"),
              lambda data: data["docking_state"] or "Idle"))
    d.append(("ed_docking_pad", "Docking Pad", None, None, "mdi:numeric",
              lambda data: data["docking_pad"]))
    d.append(("ed_docking_station", "Docking Station", None, None, "mdi:space-station",
              lambda data: data["docking_station"]))
    d.append(("ed_docking_denied_reason", "Docking Denied Reason", None, None, "mdi:close-octagon",
              _denied_reason))
    d.append(("ed_balance", "Balance", "CR", "monetary", "mdi:cash-multiple",
              lambda data: data["balance"]))
    d.append(("ed_credits", "Credits", "CR", "monetary", "mdi:cash-multiple",
              lambda data: data["balance"]))
    d.append(("ed_credits_formatted", "Credits Formatted", None, None, "mdi:cash-multiple",
              lambda data: f"{data['balance']:,}"))
    d.append(("ed_system_population", "System Population", None, None, "mdi:account-group",
              lambda data: data["system_population"]))

    # ---- Ranks / progress ----
    for cat in RANK_CATEGORIES:
        icon = RANK_ICONS[cat]
        d.append((
            f"ed_{cat.lower()}_rank", f"{cat} Rank", None, None, icon,
            (lambda data, c=cat: _rank_name(c, data["rank"].get(c, 0)))
        ))
        d.append((
            f"ed_{cat.lower()}_progress", f"{cat} Progress", "%", None, icon,
            (lambda data, c=cat: data["progress"].get(c, 0))
        ))

    # ---- Statistics ----
    def stat(group, field, default=0):
        return lambda data: data["statistics"].get(group, {}).get(field, default)

    d.append(("ed_total_jumps", "Total Jumps", None, None, "mdi:rocket-launch",
              stat("Exploration", "Total_Hyperspace_Jumps")))
    d.append(("ed_total_distance", "Total Distance", "ly", None, "mdi:ruler",
              lambda data: round(data["statistics"].get("Exploration", {}).get("Total_Hyperspace_Distance", 0), 2)))
    d.append(("ed_systems_visited", "Systems Visited", None, None, "mdi:map",
              stat("Exploration", "Systems_Visited")))
    d.append(("ed_exploration_profits", "Exploration Profits", "CR", "monetary", "mdi:cash",
              stat("Exploration", "Exploration_Profits")))
    d.append(("ed_trading_profits", "Trading Profits", "CR", "monetary", "mdi:cash",
              stat("Trading", "Market_Profits")))
    d.append(("ed_bounty_profits", "Bounty Profits", "CR", "monetary", "mdi:target",
              stat("Combat", "Bounty_Hunting_Profit")))
    d.append(("ed_exobiology_profits", "Exobiology Profits", "CR", "monetary", "mdi:bacteria",
              stat("Exobiology", "Organic_Data_Profits")))
    d.append(("ed_time_played", "Time Played", "hours", None, "mdi:clock",
              lambda data: round(data["statistics"].get("Exploration", {}).get("Time_Played", 0) / 3600, 1)))
    d.append(("ed_first_footfalls", "First Footfalls", None, None, "mdi:foot-print",
              stat("Exploration", "First_Footfalls")))
    d.append(("ed_planet_footfalls", "Planet Footfalls", None, None, "mdi:foot-print",
              stat("Exploration", "Planet_Footfalls")))
    d.append(("ed_planets_scanned_l3", "Planets Scanned L3", None, None, "mdi:telescope",
              stat("Exploration", "Planets_Scanned_To_Level_3")))

    d.append(("ed_total_wealth", "Total Wealth", "CR", "monetary", "mdi:bank",
              stat("Bank_Account", "Current_Wealth")))
    d.append(("ed_spent_ships", "Spent on Ships", "CR", "monetary", "mdi:space-invaders",
              stat("Bank_Account", "Spent_On_Ships")))
    d.append(("ed_spent_outfitting", "Spent on Outfitting", "CR", "monetary", "mdi:cog",
              stat("Bank_Account", "Spent_On_Outfitting")))
    d.append(("ed_spent_repairs", "Spent on Repairs", "CR", "monetary", "mdi:wrench",
              stat("Bank_Account", "Spent_On_Repairs")))
    d.append(("ed_spent_fuel", "Spent on Fuel", "CR", "monetary", "mdi:gas-station",
              stat("Bank_Account", "Spent_On_Fuel")))
    d.append(("ed_spent_insurance", "Spent on Insurance", "CR", "monetary", "mdi:shield-alert",
              stat("Bank_Account", "Spent_On_Insurance")))
    d.append(("ed_insurance_claims", "Insurance Claims", None, None, "mdi:shield-alert",
              stat("Bank_Account", "Insurance_Claims")))
    d.append(("ed_ships_owned", "Ships Owned", None, None, "mdi:space-invaders",
              stat("Bank_Account", "Owned_Ship_Count")))

    d.append(("ed_organic_species", "Organic Species Scanned", None, None, "mdi:bacteria",
              stat("Exobiology", "Organic_Data")))
    d.append(("ed_organic_genus", "Organic Genus Found", None, None, "mdi:bacteria-outline",
              stat("Exobiology", "Organic_Genus")))

    d.append(("ed_bounties_claimed", "Bounties Claimed", None, None, "mdi:target",
              stat("Combat", "Bounties_Claimed")))
    d.append(("ed_assassinations", "Assassinations", None, None, "mdi:sword-cross",
              stat("Combat", "Assassinations")))

    # ---- Position ----
    d.append(("ed_position_x", "Position X", "ly", None, "mdi:axis-x-arrow",
              lambda data: data["position"][0]))
    d.append(("ed_position_y", "Position Y", "ly", None, "mdi:axis-y-arrow",
              lambda data: data["position"][1]))
    d.append(("ed_position_z", "Position Z", "ly", None, "mdi:axis-z-arrow",
              lambda data: data["position"][2]))
    d.append(("ed_distance_from_sol", "Distance from Sol", "ly", None, "mdi:earth",
              lambda data: round(sum(v ** 2 for v in data["position"]) ** 0.5, 2)))

    # ---- Dashboard direct pass-through ----
    d.append(("ed_flags", "Flags", None, None, "mdi:flag", lambda data: data["flags"]))
    d.append(("ed_flags2", "Flags2", None, None, "mdi:flag", lambda data: data["flags2"]))
    d.append(("ed_fuel_main", "Fuel Main", "t", "weight", "mdi:gas-station",
              lambda data: data["fuel_main"]))
    d.append(("ed_fuel_reservoir", "Fuel Reservoir", "t", "weight", "mdi:gas-station",
              lambda data: data["fuel_reservoir"]))
    d.append(("ed_system_pips", "System Pips", None, None, "mdi:hexagon-slice-3",
              lambda data: data["pips_sys"]))
    d.append(("ed_engine_pips", "Engine Pips", None, None, "mdi:engine",
              lambda data: data["pips_eng"]))
    d.append(("ed_weapons_pips", "Weapons Pips", None, None, "mdi:crosshairs",
              lambda data: data["pips_wep"]))
    d.append(("ed_pips_display", "Pips Display", None, None, "mdi:gauge",
              lambda data: f"SYS:{data['pips_sys']} | ENG:{data['pips_eng']} | WEP:{data['pips_wep']}"))
    d.append(("ed_cargo", "Cargo", "t", "weight", "mdi:package", lambda data: data["cargo"]))
    d.append(("ed_legal_state", "Legal State", None, None, "mdi:gavel",
              lambda data: data["legal_state"] or "Unknown"))
    d.append(("ed_guifocus", "GuiFocus", None, None, "mdi:monitor", lambda data: data["guifocus"]))
    d.append(("ed_firegroup", "FireGroup", None, None, "mdi:target-variant",
              lambda data: data["firegroup"]))

    d.append(("ed_gui_focus_name", "GUI Focus Name", None, None, "mdi:monitor-eye",
              lambda data: GUI_FOCUS_NAMES.get(data["guifocus"], f"Unknown ({data['guifocus']})")))
    d.append(("ed_fuel_percent", "Fuel Percent", "%", None, "mdi:gauge",
              _percent("fuel_main", "fuel_capacity")))
    d.append(("ed_cargo_percent", "Cargo Percent", "%", None, "mdi:package-variant-closed",
              _percent("cargo", "cargo_capacity")))

    # ---- Jump target / stars ----
    d.append(("ed_jump_target_system", "Jump Target System", None, None, "mdi:crosshairs-gps",
              lambda data: data["jump_target_system"]))
    d.append(("ed_jumps_remaining", "Jumps Remaining", None, None, "mdi:map-marker-path",
              lambda data: data["jumps_remaining"]))
    d.append(("ed_jump_star_class", "Jump Star Class", None, None, "mdi:star-four-points",
              _jump_target_class, _star_attrs(_jump_target_class)))
    d.append(("ed_jump_star_type", "Jump Star Type", None, None, "mdi:star-four-points-outline",
              _star_type(_jump_target_class), _star_attrs(_jump_target_class)))
    d.append(("ed_current_star_class", "Current Star Class", None, None, "mdi:white-balance-sunny",
              _current_star_class, _star_attrs(_current_star_class)))
    d.append(("ed_current_star_type", "Current Star Type", None, None, "mdi:white-balance-sunny",
              _star_type(_current_star_class), _star_attrs(_current_star_class)))
    d.append(("ed_last_journal_event", "Last Journal Event", None, None, "mdi:book-open-variant",
              lambda data: data["last_journal_event"]))

    # ---- Summary sensors (computed directly from flag bits) ----
    d.append(("ed_vehicle_type", "Vehicle Type", None, None, "mdi:space-invaders", _vehicle_type))
    d.append(("ed_flight_mode", "Flight Mode", None, None, "mdi:airplane", _flight_mode))
    d.append(("ed_combat_status", "Combat Status", None, None, "mdi:shield-check", _combat_status))
    d.append(("ed_location_type", "Location Type", None, None, "mdi:map-marker", _location_type))
    d.append(("ed_status_summary", "Status Summary", None, None, "mdi:gauge", _status_summary))
    d.append(("ed_critical_warnings", "Critical Warnings", None, None, _critical_warnings_icon, _critical_warnings))

    return d


def _vehicle_type(data):
    flags, flags2 = data["flags"], data["flags2"]
    if _bit(flags2, 0):
        return "On Foot"
    if _bit(flags2, 1):
        return "Taxi"
    if _bit(flags, 26):
        return "SRV"
    if _bit(flags, 25):
        return "Fighter"
    if _bit(flags, 24):
        return "Ship"
    return "Unknown"


def _flight_mode(data):
    flags, flags2 = data["flags"], data["flags2"]
    if _bit(flags, 0):
        return "Docked"
    if _bit(flags, 1):
        return "Landed"
    if _bit(flags, 30):
        return "Hyperspace Jump"
    if _bit(flags2, 12):
        return "Glide Mode"
    if _bit(flags, 4):
        return "Supercruise"
    return "Normal Space"


def _combat_status(data):
    flags = data["flags"]
    if _bit(flags, 22) or _bit(flags, 23):
        return "In Danger"
    if _bit(flags, 6):
        return "Hardpoints Deployed"
    if _bit(flags, 3):
        return "Shields Up - Safe"
    return "Safe"


def _location_type(data):
    flags, flags2 = data["flags"], data["flags2"]
    if _bit(flags2, 3):
        return "On Foot - Station"
    if _bit(flags2, 14):
        return "On Foot - Social Space"
    if _bit(flags2, 13):
        return "On Foot - Hangar"
    if _bit(flags2, 15):
        return "On Foot - Exterior"
    if _bit(flags2, 4):
        return "On Foot - Planet Surface"
    if _bit(flags, 0):
        return f"Docked - {data['current_station'] or 'Unknown'}"
    if _bit(flags, 1):
        return f"Landed - {data['current_body'] or 'Unknown'}"
    if _bit(flags, 4):
        return "In Supercruise"
    return "Normal Space"


def _status_summary(data):
    flags, flags2 = data["flags"], data["flags2"]
    items = []
    if _bit(flags2, 0):
        items.append("On Foot")
    elif _bit(flags, 24):
        items.append("MainShip")
    elif _bit(flags, 25):
        items.append("Fighter")
    elif _bit(flags, 26):
        items.append("SRV")
    elif _bit(flags2, 1):
        items.append("Taxi")

    if _bit(flags, 0):
        items.append("Docked")
    elif _bit(flags, 1):
        items.append("Landed")
    elif _bit(flags, 4):
        items.append("Supercruise")
    elif _bit(flags, 30):
        items.append("Jumping")
    elif _bit(flags2, 12):
        items.append("Gliding")

    if _bit(flags, 6):
        items.append("Hardpoints")
    if _bit(flags, 3):
        items.append("Shields")
    if _bit(flags, 10):
        items.append("Silent")
    if _bit(flags, 11):
        items.append("Scooping")
    if _bit(flags2, 2):
        items.append("Multicrew")
    if _bit(flags, 19):
        items.append("\u26a0\ufe0f LOW FUEL")
    if _bit(flags, 20):
        items.append("\u26a0\ufe0f OVERHEATING")
    if _bit(flags, 22):
        items.append("\u26a0\ufe0f DANGER")
    if _bit(flags, 23):
        items.append("\u26a0\ufe0f INTERDICTION")
    if _bit(flags2, 6):
        items.append("\u26a0\ufe0f LOW O2")
    if _bit(flags2, 7):
        items.append("\u26a0\ufe0f LOW HEALTH")

    return " \u2022 ".join(items) if items else "In Space"


def _critical_warnings_icon(data):
    flags, flags2 = data["flags"], data["flags2"]
    any_warning = (
        _bit(flags, 19) or _bit(flags, 20) or _bit(flags, 22) or _bit(flags, 23)
        or _bit(flags2, 6) or _bit(flags2, 7) or _bit(flags2, 10) or _bit(flags2, 11)
    )
    return "mdi:alert-circle" if any_warning else "mdi:check-circle"


def _critical_warnings(data):
    flags, flags2 = data["flags"], data["flags2"]
    warnings = []
    if _bit(flags, 19):
        warnings.append("Low Fuel")
    if _bit(flags, 20):
        warnings.append("Overheating")
    if _bit(flags, 22):
        warnings.append("In Danger")
    if _bit(flags, 23):
        warnings.append("Being Interdicted")
    if _bit(flags2, 6):
        warnings.append("Low Oxygen")
    if _bit(flags2, 7):
        warnings.append("Low Health")
    if _bit(flags2, 10):
        warnings.append("Very Cold")
    if _bit(flags2, 11):
        warnings.append("Very Hot")
    return ", ".join(warnings) if warnings else "All Clear"


class EliteDangerousSensor(EliteDangerousEntity, SensorEntity):
    def __init__(self, coordinator, unique_id, name, unit, device_class, icon, compute_fn,
                 attrs_fn=None):
        super().__init__(coordinator, unique_id, name, "sensor")
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._icon = icon
        self._compute_fn = compute_fn
        self._attrs_fn = attrs_fn

    @property
    def extra_state_attributes(self):
        if not self._attrs_fn:
            return None
        try:
            return self._attrs_fn(self.coordinator.data) or None
        except Exception:  # noqa: BLE001
            return None

    @property
    def icon(self):
        if callable(self._icon):
            try:
                return self._icon(self.coordinator.data)
            except Exception:  # noqa: BLE001
                return "mdi:help-circle"
        return self._icon

    @property
    def native_value(self):
        try:
            return self._compute_fn(self.coordinator.data)
        except Exception:  # noqa: BLE001 - never let one bad field break the entity
            return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EliteDangerousSensor(coordinator, *descriptor)
        for descriptor in _build_descriptors()
    ]
    async_add_entities(entities)
