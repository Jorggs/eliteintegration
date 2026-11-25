"""Button platform: fetch a new trade route now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EliteDangerousTradeEntity


class TradeRefreshButton(EliteDangerousTradeEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ed_trade_refresh", "Trade Route Refresh", "button")

    async def async_press(self) -> None:
        await self.trade.async_refresh()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TradeRefreshButton(coordinator)])
