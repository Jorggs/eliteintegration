"""Most-profitable trade route from the Spansh trade planner.

Spansh (https://spansh.co.uk/trade) has no documented public API, so this
uses the same requests its trade planner web page makes:

    POST https://spansh.co.uk/api/trade/route   (form-encoded) -> {"job": "<uuid>"}
    GET  https://spansh.co.uk/api/results/<uuid>               -> {"state", "status", "result"}

The job is polled every few seconds until its state is "completed". If
Spansh changes how this works, the route sensors go to an "error" status
with the reason; the rest of the integration is unaffected.

Route searches start from a station (Spansh needs one): the station you're
docked at, or the last one you docked at. A new route is fetched when you
dock (unless the station is a stop on the current route, in which case the
route just moves on to the next hop), when you press Refresh, and a few
seconds after you change a setting.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .const import LARGE_PAD_SHIPS
from .coordinator import JOURNAL_EVENT_TYPE, EliteDangerousCoordinator, signal_name

_LOGGER = logging.getLogger(__name__)

SPANSH_ROUTE_URL = "https://spansh.co.uk/api/trade/route"
SPANSH_RESULTS_URL = "https://spansh.co.uk/api/results/{job}"
USER_AGENT = "HomeAssistant-EliteDangerous (github.com/Jorggs/eliteintegration)"

POLL_INTERVAL = 5  # seconds between result checks
MAX_WAIT = 300  # Spansh can queue jobs for a few minutes when busy
SETTINGS_DEBOUNCE = 4  # seconds to wait after a setting changes
MIN_AUTO_INTERVAL = 20  # seconds between automatic (non-button) requests

# ---- statuses ----
STATUS_IDLE = "idle"
STATUS_WAITING = "waiting for station"
STATUS_FETCHING = "fetching"
STATUS_READY = "ready"
STATUS_NO_ROUTE = "no route"
STATUS_ERROR = "error"
STATUSES = [STATUS_IDLE, STATUS_WAITING, STATUS_FETCHING, STATUS_READY, STATUS_NO_ROUTE, STATUS_ERROR]

# ---- pad options ----
PAD_AUTO = "Auto"
PAD_LARGE = "Large only"
PAD_ANY = "Any"
PAD_OPTIONS = [PAD_AUTO, PAD_LARGE, PAD_ANY]

# ---- settings: key -> default ----
DEFAULT_SETTINGS = {
    "pad": PAD_AUTO,
    "max_hops": 3,
    "max_hop_distance": 0.0,  # ly; 0 = use the ship's jump range
    "max_arrival_ls": 5000,
    "max_market_age_hours": 48,
    "allow_planetary": False,
    "allow_fleet_carriers": False,
    "allow_permit": False,
    "allow_prohibited": False,
    "avoid_loops": True,
    "auto_refresh": True,
}


def trade_signal_name(entry_id: str) -> str:
    return f"elite_dangerous_trade_update_{entry_id}"


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _age_hours(epoch, now):
    """Spansh gives market_updated_at as epoch seconds (sometimes an ISO string)."""
    if epoch in (None, "", 0):
        return None
    try:
        ts = float(epoch)
    except (TypeError, ValueError):
        try:
            from datetime import datetime

            ts = datetime.fromisoformat(str(epoch).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return round(max(now - ts, 0) / 3600, 1)


def build_payload(settings: dict, data: dict, system: str, station: str) -> dict:
    """Form fields for POST /api/trade/route.

    Field names are the ones the Spansh trade planner page sends. Booleans are
    sent as "1" when on and left out when off, as an HTML form does.
    """
    hop_ly = _f(settings.get("max_hop_distance"))
    if hop_ly <= 0:
        hop_ly = _f(data.get("jump_range")) or 20.0

    payload = {
        "system": system,
        "station": station,
        "max_hops": _i(settings.get("max_hops"), 3),
        "max_hop_distance": round(hop_ly, 2),
        "max_system_distance": _i(settings.get("max_arrival_ls"), 5000) or 10_000_000,
    }
    cargo = data.get("cargo_capacity")
    if cargo:
        payload["max_cargo"] = _i(cargo)
    balance = data.get("balance")
    if balance:
        payload["starting_capital"] = _i(balance)

    if requires_large_pad(settings, data):
        payload["requires_large_pad"] = "1"

    flags = {
        "allow_planetary": "allow_planetary",
        "allow_fleet_carriers": "allow_player_owned",
        "allow_permit": "permit",
        "allow_prohibited": "allow_prohibited",
        "avoid_loops": "unique",
    }
    for setting, field in flags.items():
        if settings.get(setting):
            payload[field] = "1"
    return payload


def requires_large_pad(settings: dict, data: dict) -> bool:
    pad = settings.get("pad", PAD_AUTO)
    if pad == PAD_LARGE:
        return True
    if pad == PAD_ANY:
        return False
    return (data.get("ship_type") or "").lower() in LARGE_PAD_SHIPS


def parse_result(result: list, now: float | None = None) -> list[dict]:
    """Spansh result[] (one entry per hop) -> list of plain hop dicts."""
    now = now or time.time()
    hops = []
    for n, seg in enumerate(result or [], start=1):
        src = seg.get("source") or {}
        dst = seg.get("destination") or {}
        commodities = []
        for c in seg.get("commodities") or []:
            commodities.append({
                "name": c.get("name", ""),
                "amount": _i(c.get("amount")),
                "buy_price": _i((c.get("source_commodity") or {}).get("buy_price")),
                "sell_price": _i((c.get("destination_commodity") or {}).get("sell_price")),
                "profit": _i(c.get("total_profit")),
            })
        # Spansh tops the hold up with several commodities; the main one is
        # the one that earns most, but profit counts the whole load.
        commodities.sort(key=lambda c: c["profit"], reverse=True)
        amount = sum(c["amount"] for c in commodities)
        profit = sum(c["profit"] for c in commodities) or _i(seg.get("total_profit"))
        main = commodities[0] if commodities else {}
        hops.append({
            "hop": n,
            "from_system": src.get("system", ""),
            "from_station": src.get("station", ""),
            "to_system": dst.get("system", ""),
            "to_station": dst.get("station", ""),
            "distance_ly": round(_f(seg.get("distance")), 2),
            "to_arrival_ls": _i(dst.get("distance_to_arrival")) if dst.get("distance_to_arrival") is not None else None,
            "commodity": main.get("name"),
            "buy_price": main.get("buy_price"),
            "sell_price": main.get("sell_price"),
            "amount": amount,
            "profit": profit,
            "profit_per_ton": round(profit / amount) if amount else None,
            "cumulative_profit": _i(seg.get("cumulative_profit")) or None,
            "from_market_age_hours": _age_hours(src.get("market_updated_at"), now),
            "to_market_age_hours": _age_hours(dst.get("market_updated_at"), now),
            "commodities": commodities,
        })
    # Fill in cumulative profit if Spansh didn't give it
    running = 0
    for hop in hops:
        running += hop["profit"]
        if hop["cumulative_profit"] is None:
            hop["cumulative_profit"] = running
    return hops


class SpanshError(Exception):
    """Spansh refused the request or returned something unexpected."""


class TradeRouteManager:
    """Holds the trade settings and the current route, and talks to Spansh."""

    def __init__(self, hass: HomeAssistant, coordinator: EliteDangerousCoordinator):
        self.hass = hass
        self.coordinator = coordinator
        self.entry_id = coordinator.entry_id
        self.settings: dict = dict(DEFAULT_SETTINGS)

        self.status = STATUS_IDLE
        self.error: str | None = None
        self.hops: list[dict] = []
        self.next_hop_index = 0
        self.start_system: str | None = None
        self.start_station: str | None = None
        self.last_updated: float | None = None
        self.request_settings: dict = {}

        # Last station docked at (Spansh needs a station to start from)
        self.station_system: str | None = None
        self.station_name: str | None = None

        self._task: asyncio.Task | None = None
        self._debounce = None
        self._last_auto_request = 0.0
        self._last_ship_type = None
        self._unsubs = []

    # ---- lifecycle ----

    async def async_setup(self):
        self._unsubs.append(self.hass.bus.async_listen(JOURNAL_EVENT_TYPE, self._on_journal))
        self._unsubs.append(
            async_dispatcher_connect(self.hass, signal_name(self.entry_id), self._on_telemetry)
        )
        self._last_ship_type = self.coordinator.data.get("ship_type")
        # Docked at startup (retained MQTT)? Use that station.
        data = self.coordinator.data
        if data.get("current_station") and data.get("current_system"):
            self.station_system = data["current_system"]
            self.station_name = data["current_station"]

    async def async_unload(self):
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._debounce:
            self._debounce()
            self._debounce = None
        if self._task and not self._task.done():
            self._task.cancel()

    def _notify(self):
        async_dispatcher_send(self.hass, trade_signal_name(self.entry_id))

    # ---- inputs ----

    @callback
    def _on_telemetry(self):
        data = self.coordinator.data
        if data.get("current_station") and data.get("current_system"):
            if (data["current_system"], data["current_station"]) != (self.station_system, self.station_name):
                self.station_system = data["current_system"]
                self.station_name = data["current_station"]
                self._notify()
        ship = data.get("ship_type")
        if ship and ship != self._last_ship_type:
            was_large = (self._last_ship_type or "").lower() in LARGE_PAD_SHIPS
            self._last_ship_type = ship
            # Changing ship can change pad size and cargo, so look again
            if self.settings["pad"] == PAD_AUTO and was_large != ((ship or "").lower() in LARGE_PAD_SHIPS):
                self.schedule_refresh()

    @callback
    def _on_journal(self, event: Event):
        if event.data.get("entry_id") != self.entry_id:
            return
        if event.data.get("event") != "Docked":
            return
        system = event.data.get("StarSystem")
        station = event.data.get("StationName")
        if not system or not station:
            return
        self.station_system, self.station_name = system, station

        # Docked at a stop on the current route: move along it instead of re-planning
        for i, hop in enumerate(self.hops):
            if hop["to_station"] == station and hop["to_system"] == system:
                self.next_hop_index = i + 1
                self._notify()
                if self.next_hop_index < len(self.hops):
                    return
                break  # end of the route: plan a new one from here

        if self.settings.get("auto_refresh"):
            self.hass.async_create_task(self.async_refresh(auto=True))
        else:
            self._notify()

    def set_setting(self, key: str, value):
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        self._notify()
        if key != "auto_refresh" and self.hops:
            self.schedule_refresh()

    @callback
    def schedule_refresh(self):
        """Refresh a few seconds from now, so dragging a slider sends one request."""
        from homeassistant.helpers.event import async_call_later

        if self._debounce:
            self._debounce()

        @callback
        def _fire(_now):
            self._debounce = None
            self.hass.async_create_task(self.async_refresh(auto=True))

        self._debounce = async_call_later(self.hass, SETTINGS_DEBOUNCE, _fire)

    # ---- fetching ----

    async def async_refresh(self, auto: bool = False):
        if not self.station_name or not self.station_system:
            self.status = STATUS_WAITING
            self.error = "Dock at a station first: Spansh plans routes from a station"
            self._notify()
            return
        now = time.monotonic()
        if auto and now - self._last_auto_request < MIN_AUTO_INTERVAL:
            self.schedule_refresh()
            return
        self._last_auto_request = now
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = self.hass.async_create_task(self._fetch(self.station_system, self.station_name))

    async def _fetch(self, system: str, station: str):
        payload = build_payload(self.settings, self.coordinator.data, system, station)
        self.status = STATUS_FETCHING
        self.error = None
        self._notify()
        try:
            result = await self._spansh(payload)
        except asyncio.CancelledError:
            raise
        except SpanshError as err:
            self._fail(str(err))
            return
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._fail(f"Couldn't reach Spansh: {err or type(err).__name__}")
            return
        except Exception as err:  # noqa: BLE001 - never let this break the integration
            _LOGGER.exception("Unexpected error fetching trade route")
            self._fail(f"Unexpected error: {err}")
            return

        self.hops = parse_result(result)
        self.next_hop_index = 0
        self.start_system, self.start_station = system, station
        self.last_updated = time.time()
        self.request_settings = {k: v for k, v in payload.items() if k not in ("system", "station")}
        self.status = STATUS_READY if self.hops else STATUS_NO_ROUTE
        if not self.hops:
            self.error = "Spansh found no profitable route with these settings"
        self._notify()

    def _fail(self, message: str):
        _LOGGER.warning("Trade route: %s", message)
        self.status = STATUS_ERROR
        self.error = message
        self._notify()

    async def _spansh(self, payload: dict) -> list:
        session = async_get_clientsession(self.hass)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        timeout = aiohttp.ClientTimeout(total=30)

        async with session.post(SPANSH_ROUTE_URL, data=payload, headers=headers, timeout=timeout) as resp:
            body = await self._json(resp)
            if resp.status >= 400:
                raise SpanshError(f"Spansh refused the request ({resp.status}): {body.get('error') or body}")
        job = body.get("job")
        if not job:
            raise SpanshError(f"Spansh didn't return a job ID: {body}")
        _LOGGER.debug("Spansh trade job %s queued: %s", job, payload)

        started = time.monotonic()
        while time.monotonic() - started < MAX_WAIT:
            await asyncio.sleep(POLL_INTERVAL)
            async with session.get(
                SPANSH_RESULTS_URL.format(job=job), headers=headers, timeout=timeout
            ) as resp:
                body = await self._json(resp)
                if resp.status >= 400 and resp.status != 404:
                    raise SpanshError(f"Spansh result check failed ({resp.status}): {body.get('error') or body}")
            if body.get("state") == "completed":
                if body.get("status") not in (None, "ok"):
                    raise SpanshError(f"Spansh couldn't plan the route: {body.get('error') or body.get('status')}")
                return body.get("result") or []
            if body.get("error"):
                raise SpanshError(f"Spansh: {body['error']}")
        raise SpanshError(f"Spansh didn't finish within {MAX_WAIT // 60} minutes")

    @staticmethod
    async def _json(resp) -> dict:
        try:
            body = await resp.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError):
            text = (await resp.text())[:200]
            raise SpanshError(f"Unexpected reply from Spansh ({resp.status}): {text}")
        if not isinstance(body, dict):
            raise SpanshError(f"Unexpected reply from Spansh: {str(body)[:200]}")
        return body

    # ---- derived values for the sensors ----

    @property
    def next_hop(self) -> dict | None:
        if 0 <= self.next_hop_index < len(self.hops):
            return self.hops[self.next_hop_index]
        return None

    @property
    def total_profit(self) -> int | None:
        if not self.hops:
            return None
        return self.hops[-1]["cumulative_profit"]

    @property
    def oldest_market_age_hours(self) -> float | None:
        ages = [
            a for h in self.hops
            for a in (h["from_market_age_hours"], h["to_market_age_hours"]) if a is not None
        ]
        return max(ages) if ages else None

    @property
    def stale(self) -> bool:
        oldest = self.oldest_market_age_hours
        limit = _f(self.settings.get("max_market_age_hours"))
        return bool(oldest is not None and limit > 0 and oldest > limit)
