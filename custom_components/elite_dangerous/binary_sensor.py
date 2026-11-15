"""Binary sensor platform for the Elite Dangerous Telemetry integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FLAGS2_BITS, FLAGS_BITS
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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EliteDangerousDockedStateSensor(coordinator),
        EliteDangerousGameRunningSensor(coordinator),
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
