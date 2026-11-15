"""Binary sensor platform for the Elite Dangerous Telemetry integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FLAGS2_BITS, FLAGS_BITS, classify_star
from .entity import EliteDangerousEntity


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


class EliteDangerousBinarySensor(EliteDangerousEntity, BinarySensorEntity):
    def __init__(self, coordinator, unique_id, name, icon, device_class, source_key, bit):
        super().__init__(coordinator, unique_id, name, "binary_sensor")
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._source_key = source_key
        self._bit = bit

    @property
    def is_on(self):
        value = int(self.coordinator.data.get(self._source_key, 0) or 0)
        return (value & (1 << self._bit)) != 0


class EliteDangerousDockedStateSensor(EliteDangerousEntity, BinarySensorEntity):
    """Docked status derived from Location/Docked/Undocked events rather than
    the cockpit Flags bit -- can be a beat faster/more reliable at the moment
    of docking/undocking."""

    _attr_icon = "mdi:space-station"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ed_docked_state", "Docked State", "binary_sensor")

    @property
    def is_on(self):
        return bool(self.coordinator.data.get("current_station"))


class EliteDangerousGameRunningSensor(EliteDangerousEntity, BinarySensorEntity):
    """On while the Elite Dangerous process is running on the PC (from the
    app's Telemetry/GameRunning topic). Note: this only means the game is
    open, not that you are in a session."""

    _attr_icon = "mdi:gamepad-variant"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ed_game_running", "Game Running", "binary_sensor")

    @property
    def is_on(self):
        return bool(self.coordinator.data.get("game_running", False))


class EliteDangerousComputedBinarySensor(EliteDangerousEntity, BinarySensorEntity):
    """Binary sensor computed from the shared data dict."""

    def __init__(self, coordinator, unique_id, name, icon, compute_fn):
        super().__init__(coordinator, unique_id, name, "binary_sensor")
        self._attr_icon = icon
        self._compute_fn = compute_fn

    @property
    def is_on(self):
        try:
            return bool(self._compute_fn(self.coordinator.data))
        except Exception:  # noqa: BLE001
            return None


def _star_flag(class_key_fn, field):
    def value(data):
        info = classify_star(class_key_fn(data))
        return bool(info and info[field])
    return value


def _jump_class(data):
    return data.get("jump_target_star_class")


def _current_class(data):
    if data.get("last_jump_system") and data.get("last_jump_system") == data.get("current_system"):
        return data.get("last_jump_star_class")
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EliteDangerousDockedStateSensor(coordinator),
        EliteDangerousGameRunningSensor(coordinator),
        EliteDangerousComputedBinarySensor(
            coordinator, "ed_jump_target_scoopable", "Jump Target Scoopable",
            "mdi:fuel", _star_flag(_jump_class, "scoopable")),
        EliteDangerousComputedBinarySensor(
            coordinator, "ed_jump_target_jet_cone", "Jump Target Jet Cone",
            "mdi:alert-decagram", _star_flag(_jump_class, "jet_cone")),
        EliteDangerousComputedBinarySensor(
            coordinator, "ed_current_star_scoopable", "Current Star Scoopable",
            "mdi:fuel", _star_flag(_current_class, "scoopable")),
        EliteDangerousComputedBinarySensor(
            coordinator, "ed_wanted", "Wanted",
            "mdi:handcuffs", lambda data: data.get("legal_state") == "Wanted"),
    ]

    # Special-case names that don't follow the plain "ED <Name>" -> unique_id
    # slug pattern used in the original YAML package, to keep entity_ids
    # identical for anyone migrating from it.
    special_slugs = {
        "Hardpoints Deployed": "ed_hardpoints",
        "In Main Ship": "ed_in_mainship",
        "Cargo Scoop Deployed": "ed_cargo_scoop",
        "Landing Gear Down": "ed_landing_gear",
    }

    for bit, name, icon, device_class in FLAGS_BITS:
        slug = special_slugs.get(name, f"ed_{_slug(name)}")
        entities.append(
            EliteDangerousBinarySensor(
                coordinator, slug, name, icon, device_class, "flags", bit
            )
        )

    for bit, name, icon, device_class in FLAGS2_BITS:
        slug = f"ed_{_slug(name)}"
        entities.append(
            EliteDangerousBinarySensor(
                coordinator, slug, name, icon, device_class, "flags2", bit
            )
        )

    async_add_entities(entities)
