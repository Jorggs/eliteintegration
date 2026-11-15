"""Shared base entity for the Elite Dangerous Telemetry integration."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DEVICE_NAME, DOMAIN, ENTITY_ID_PREFIX, MANUFACTURER
from .coordinator import EliteDangerousCoordinator, signal_name


class EliteDangerousEntity(Entity):
    """Base entity: pushes updates via dispatcher, no polling.

    Uses has_entity_name=True (the modern HA pattern) so the frontend shows
    "<device name> <entity name>" combined automatically -- entity `name`
    here should be just the suffix (e.g. "Balance", "Current System"), never
    a hardcoded "ED " prefix, or renaming the device to something starting
    with "ED" would double it up (e.g. "ED ED Balance").

    entity_id is set directly (not via suggested_object_id) so it is always
    e.g. "sensor.elite_dangerous_commander_ed_balance", whatever the display
    name or what the device gets renamed to. This matters because Home Assistant's real
    entity-registration logic (homeassistant/helpers/entity_platform.py,
    EntityPlatform._async_add_entity) ALWAYS prepends the device name ahead
    of suggested_object_id whenever has_entity_name=True:

        if device and entity.has_entity_name:
            suggested_object_id = f"{device_name} {entity.suggested_object_id}"

    so overriding suggested_object_id alone is not sufficient -- only a
    directly-set entity_id takes priority over that merge.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: EliteDangerousCoordinator, unique_id: str, name: str, platform: str
    ):
        self.coordinator = coordinator
        self._attr_unique_id = unique_id
        self._attr_name = name
        self.entity_id = f"{platform}.{ENTITY_ID_PREFIX}{unique_id}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            name=DEVICE_NAME,
            manufacturer=MANUFACTURER,
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_name(self.coordinator.entry_id), self._handle_update
            )
        )

    @callback
    def _handle_update(self):
        self.async_write_ha_state()
