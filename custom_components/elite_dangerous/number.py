"""Number platform: trade route search limits."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EliteDangerousTradeEntity

# (unique_id, name, setting key, min, max, step, unit, mode, icon, integer?)
TRADE_NUMBERS = [
    ("ed_trade_max_hops", "Trade Max Hops", "max_hops", 1, 10, 1, None,
     NumberMode.SLIDER, "mdi:numeric", True),
    # 0 means "use the ship's current jump range"
    ("ed_trade_max_hop_distance", "Trade Max Hop Distance", "max_hop_distance", 0, 150, 0.5, "ly",
     NumberMode.SLIDER, "mdi:map-marker-distance", False),
    ("ed_trade_max_arrival_distance", "Trade Max Arrival Distance", "max_arrival_ls", 100, 1000000, 100, "ls",
     NumberMode.BOX, "mdi:orbit", True),
    ("ed_trade_max_market_age", "Trade Max Market Age", "max_market_age_hours", 1, 720, 1, "h",
     NumberMode.SLIDER, "mdi:clock-outline", True),
]


class TradeNumber(EliteDangerousTradeEntity, RestoreNumber):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, unique_id, name, key, minimum, maximum, step, unit, mode, icon, integer):
        super().__init__(coordinator, unique_id, name, "number")
        self._key = key
        self._integer = integer
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_mode = mode
        self._attr_icon = icon

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value is not None:
            self.trade.settings[self._key] = self._clean(last.native_value)

    def _clean(self, value):
        return int(round(value)) if self._integer else float(value)

    @property
    def native_value(self):
        return self.trade.settings[self._key]

    async def async_set_native_value(self, value: float) -> None:
        self.trade.set_setting(self._key, self._clean(value))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TradeNumber(coordinator, *d) for d in TRADE_NUMBERS])
