"""The Elite Dangerous Telemetry integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_ROOT_TOPIC, DEFAULT_ROOT_TOPIC, DOMAIN, ENTITY_ID_PREFIX
from .coordinator import EliteDangerousCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


def _migrate_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename any of this integration's entities that are registered without
    the standard prefix (e.g. sensor.ed_fuel_capacity) to the standard form
    (sensor.elite_dangerous_commander_ed_fuel_capacity). Home Assistant keeps
    the ID an entity was first registered with, so the code change alone
    wouldn't fix entities that already exist. History follows the rename."""
    registry = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        platform, _, object_id = ent.entity_id.partition(".")
        wanted = f"{platform}.{ENTITY_ID_PREFIX}{ent.unique_id}"
        if ent.entity_id == wanted:
            continue
        if registry.async_get(wanted):
            _LOGGER.warning(
                "Can't rename %s to %s: that entity ID is already taken", ent.entity_id, wanted
            )
            continue
        _LOGGER.info("Renaming %s to %s", ent.entity_id, wanted)
        registry.async_update_entity(ent.entity_id, new_entity_id=wanted)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    root_topic = entry.data.get(CONF_ROOT_TOPIC, DEFAULT_ROOT_TOPIC)

    _migrate_entity_ids(hass, entry)

    coordinator = EliteDangerousCoordinator(hass, entry.entry_id, root_topic)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: EliteDangerousCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()
    return unload_ok
