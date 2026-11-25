"""Switch platform: trade route filters."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import EliteDangerousTradeEntity

# (unique_id, name, setting key, icon)
TRADE_SWITCHES = [
    ("ed_trade_planetary", "Trade Planetary Stations", "allow_planetary", "mdi:earth"),
    ("ed_trade_fleet_carriers", "Trade Fleet Carriers", "allow_fleet_carriers", "mdi:ferry"),
    ("ed_trade_permit_systems", "Trade Permit Systems", "allow_permit", "mdi:card-account-details"),
    ("ed_trade_prohibited", "Trade Prohibited Goods", "allow_prohibited", "mdi:cancel"),
    ("ed_trade_avoid_loops", "Trade Avoid Loops", "avoid_loops", "mdi:sync-off"),
    ("ed_trade_auto_refresh", "Trade Auto Refresh", "auto_refresh", "mdi:refresh-auto"),
]


class TradeSwitch(EliteDangerousTradeEntity, SwitchEntity, RestoreEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, unique_id, name, key, icon):
        super().__init__(coordinator, unique_id, name, "switch")
        self._key = key
        self._attr_icon = icon

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in ("on", "off"):
            self.trade.settings[self._key] = last.state == STATE_ON

    @property
    def is_on(self):
        return bool(self.trade.settings[self._key])

    async def async_turn_on(self, **kwargs) -> None:
        self.trade.set_setting(self._key, True)

    async def async_turn_off(self, **kwargs) -> None:
        self.trade.set_setting(self._key, False)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TradeSwitch(coordinator, *d) for d in TRADE_SWITCHES])
