"""Select platform: trade route pad size."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import EliteDangerousTradeEntity
from .trade_route import PAD_OPTIONS, requires_large_pad


class TradePadSizeSelect(EliteDangerousTradeEntity, SelectEntity, RestoreEntity):
    """Auto = large pad only when the current ship needs one."""

    _attr_options = PAD_OPTIONS
    _attr_icon = "mdi:arrow-collapse-vertical"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "ed_trade_pad_size", "Trade Pad Size", "select")

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in PAD_OPTIONS:
            self.trade.settings["pad"] = last.state

    @property
    def current_option(self):
        return self.trade.settings["pad"]

    @property
    def extra_state_attributes(self):
        return {"large_pad_required": requires_large_pad(self.trade.settings, self.coordinator.data)}

    async def async_select_option(self, option: str) -> None:
        self.trade.set_setting("pad", option)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TradePadSizeSelect(coordinator)])
