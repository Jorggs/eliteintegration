"""Trade route tests: Spansh is mocked; everything else is a real HA instance."""

import json
import time

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.elite_dangerous.const import DOMAIN
from custom_components.elite_dangerous import trade_route
from custom_components.elite_dangerous.trade_route import (
    SPANSH_RESULTS_URL,
    SPANSH_ROUTE_URL,
    build_payload,
    parse_result,
)

P = "elite_dangerous_commander_"
JOB = "D4B856DE-E8EE-11F0-9669-A4FEAA21881D"


def seg(src, dst, comms, cumulative, age_s=3600):
    now = time.time()
    return {
        "source": {"system": src[0], "station": src[1], "market_updated_at": now - age_s},
        "destination": {"system": dst[0], "station": dst[1], "market_updated_at": now - 2 * age_s,
                         "distance_to_arrival": 812.4},
        "distance": 14.37,
        "cumulative_profit": cumulative,
        "commodities": [
            {"name": n, "amount": a, "total_profit": p,
             "source_commodity": {"buy_price": b}, "destination_commodity": {"sell_price": s}}
            for n, a, b, s, p in comms
        ],
    }


ROUTE = [
    seg(("Sol", "Galileo"), ("Alpha Centauri", "Hutton Orbital"),
        [("Silver", 1, 30363, 41188, 10825), ("Cobalt", 140, 845, 20108, 2696820)], 2707645),
    seg(("Alpha Centauri", "Hutton Orbital"), ("Barnard's Star", "Miller Depot"),
        [("Gold", 141, 9000, 12000, 423000)], 3130645),
]


def test_parse_result_whole_hold_and_ages():
    hops = parse_result(ROUTE)
    assert len(hops) == 2
    h = hops[0]
    assert h["commodity"] == "Cobalt"
    assert h["amount"] == 141
    assert h["profit"] == 2707645
    assert h["profit_per_ton"] == round(2707645 / 141)
    assert h["to_arrival_ls"] == 812
    assert 0.9 < h["from_market_age_hours"] < 1.1
    assert 1.9 < h["to_market_age_hours"] < 2.1
    assert hops[1]["cumulative_profit"] == 3130645


def test_parse_result_fills_cumulative():
    r = [dict(ROUTE[0], cumulative_profit=None), dict(ROUTE[1], cumulative_profit=None)]
    hops = parse_result(r)
    assert hops[1]["cumulative_profit"] == 2707645 + 423000


def test_build_payload():
    settings = dict(trade_route.DEFAULT_SETTINGS, allow_planetary=True)
    data = {"jump_range": 28.4, "cargo_capacity": 456, "balance": 50_000_000, "ship_type": "Anaconda"}
    p = build_payload(settings, data, "Sol", "Galileo")
    assert p["system"] == "Sol" and p["station"] == "Galileo"
    assert p["max_hop_distance"] == 28.4  # 0 = ship jump range
    assert p["max_cargo"] == 456
    assert p["starting_capital"] == 50_000_000
    assert p["requires_large_pad"] == "1"  # Auto + Anaconda
    assert p["allow_planetary"] == "1"
    assert p["unique"] == "1"
    assert "allow_player_owned" not in p
    # Unknown balance: credits shouldn't limit the route
    p = build_payload(settings, dict(data, balance=0), "Sol", "Galileo")
    assert p["starting_capital"] == trade_route.UNLIMITED_CAPITAL
    p = build_payload(dict(settings, pad="Any"), data, "Sol", "Galileo")
    assert "requires_large_pad" not in p
    p = build_payload(settings, dict(data, ship_type="python"), "Sol", "Galileo")
    assert "requires_large_pad" not in p


async def _setup(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={"root_topic": "Telemetry"},
                            unique_id="elite_dangerous_Telemetry")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def fast_poll(monkeypatch):
    monkeypatch.setattr(trade_route, "POLL_INTERVAL", 0)


async def test_entities_created(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    for eid in [
        f"sensor.{P}ed_trade_route", f"sensor.{P}ed_trade_route_status",
        f"sensor.{P}ed_trade_sell_station", f"select.{P}ed_trade_pad_size",
        f"number.{P}ed_trade_max_hops", f"number.{P}ed_trade_max_hop_distance",
        f"switch.{P}ed_trade_planetary", f"switch.{P}ed_trade_auto_refresh",
        f"button.{P}ed_trade_refresh",
        f"sensor.{P}ed_balance",  # existing sensors still there
    ]:
        assert hass.states.get(eid) is not None, eid
    assert hass.states.get(f"sensor.{P}ed_trade_route_status").state == "idle"
    assert hass.states.get(f"select.{P}ed_trade_pad_size").state == "Auto"


async def test_refresh_without_station(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    await hass.services.async_call("button", "press", {"entity_id": f"button.{P}ed_trade_refresh"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{P}ed_trade_route_status").state == "waiting for station"


async def test_dock_fetches_route_then_advances(hass, mqtt_mock, aioclient_mock, fast_poll):
    aioclient_mock.post(SPANSH_ROUTE_URL, status=202, json={"job": JOB, "status": "queued"})
    aioclient_mock.get(SPANSH_RESULTS_URL.format(job=JOB), json={"state": "completed", "status": "ok", "result": ROUTE})
    await _setup(hass, mqtt_mock)

    async_fire_mqtt_message(hass, "Telemetry/Ship/Type", "Anaconda")
    async_fire_mqtt_message(hass, "Telemetry/Ship/CargoCapacity", "456")
    async_fire_mqtt_message(hass, "Telemetry/Ship/JumpRange", "31.2")
    async_fire_mqtt_message(hass, "Telemetry/Dashboard/Balance", "50000000")
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "timestamp": "2026-11-25T18:00:00Z", "StarSystem": "Sol", "StationName": "Galileo"}))
    await hass.async_block_till_done()

    # Request contents
    _, _, sent, _ = aioclient_mock.mock_calls[0]
    assert sent["system"] == "Sol" and sent["station"] == "Galileo"
    assert sent["requires_large_pad"] == "1"
    assert sent["max_cargo"] == 456 and sent["max_hop_distance"] == 31.2

    route = hass.states.get(f"sensor.{P}ed_trade_route")
    assert route.state == "3130645"
    assert route.attributes["total_hops"] == 2
    assert route.attributes["next_hop"] == 1
    assert route.attributes["hops"][0]["commodity"] == "Cobalt"
    assert route.attributes["spansh_url"] == f"https://spansh.co.uk/trade/results/{JOB}"
    assert hass.states.get(f"sensor.{P}ed_trade_route_status").state == "ready"
    assert hass.states.get(f"sensor.{P}ed_trade_buy_station").state == "Galileo"
    assert hass.states.get(f"sensor.{P}ed_trade_sell_station").state == "Hutton Orbital"
    assert hass.states.get(f"sensor.{P}ed_trade_commodity").state == "Cobalt"

    # Docking at the first sell station moves to hop 2 without asking Spansh again
    calls = aioclient_mock.call_count
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "timestamp": "2026-11-25T18:20:00Z",
         "StarSystem": "Alpha Centauri", "StationName": "Hutton Orbital"}))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == calls
    assert hass.states.get(f"sensor.{P}ed_trade_route").attributes["next_hop"] == 2
    assert hass.states.get(f"sensor.{P}ed_trade_sell_station").state == "Miller Depot"
    assert hass.states.get(f"sensor.{P}ed_trade_commodity").state == "Gold"


async def test_retained_dock_does_not_fetch(hass, mqtt_mock, aioclient_mock):
    await _setup(hass, mqtt_mock)
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "StarSystem": "Sol", "StationName": "Galileo"}), retain=True)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 0


async def test_spansh_error_is_reported(hass, mqtt_mock, aioclient_mock, fast_poll):
    aioclient_mock.post(SPANSH_ROUTE_URL, status=400, json={"error": "Could not find starting station"})
    await _setup(hass, mqtt_mock)
    async_fire_mqtt_message(hass, "Telemetry/Ship/CargoCapacity", "200")
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "StarSystem": "Sol", "StationName": "Nowhere"}))
    await hass.async_block_till_done()
    status = hass.states.get(f"sensor.{P}ed_trade_route_status")
    assert status.state == "error"
    assert "Could not find starting station" in status.attributes["error"]
    # (the station lookup for a fallback isn't mocked, so no fallback was possible)
    # Rest of the integration still fine
    assert hass.states.get(f"sensor.{P}ed_balance") is not None


async def test_no_route(hass, mqtt_mock, aioclient_mock, fast_poll):
    aioclient_mock.post(SPANSH_ROUTE_URL, status=202, json={"job": JOB})
    aioclient_mock.get(SPANSH_RESULTS_URL.format(job=JOB), json={"state": "completed", "status": "ok", "result": []})
    await _setup(hass, mqtt_mock)
    async_fire_mqtt_message(hass, "Telemetry/Ship/CargoCapacity", "200")
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "StarSystem": "Sol", "StationName": "Galileo"}))
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{P}ed_trade_route_status").state == "no route"


async def test_settings_change(hass, mqtt_mock):
    await _setup(hass, mqtt_mock)
    await hass.services.async_call("switch", "turn_on", {"entity_id": f"switch.{P}ed_trade_planetary"}, blocking=True)
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": f"number.{P}ed_trade_max_hops", "value": 5}, blocking=True)
    await hass.services.async_call("select", "select_option",
                                   {"entity_id": f"select.{P}ed_trade_pad_size", "option": "Large only"}, blocking=True)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    trade = hass.data[DOMAIN][entry.entry_id].trade
    assert trade.settings["allow_planetary"] is True
    assert trade.settings["max_hops"] == 5
    assert trade.settings["pad"] == "Large only"
    assert hass.states.get(f"switch.{P}ed_trade_planetary").state == "on"


async def test_no_cargo_capacity_does_not_ask_spansh(hass, mqtt_mock, aioclient_mock):
    await _setup(hass, mqtt_mock)
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "StarSystem": "HIP 41832", "StationName": "Babcock Hub"}))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 0
    status = hass.states.get(f"sensor.{P}ed_trade_route_status")
    assert status.state == "waiting for ship data"
    assert "Cargo capacity" in status.attributes["error"]


async def test_real_spansh_reply_shape(hass):
    """A segment exactly as Spansh returned it on 2026-11-25 (HIP 41832 / Babcock Hub)."""
    real = [{"commodities": [{"amount": 200, "destination_commodity": {"buy_price": 0, "demand": 20904, "sell_price": 7535, "supply": 0},
                              "name": "Progenitor Cells", "profit": 1928,
                              "source_commodity": {"buy_price": 5607, "demand": 1, "sell_price": 5541, "supply": 6143},
                              "total_profit": 385600}],
             "cumulative_profit": 385600,
             "destination": {"distance_to_arrival": 230, "market_id": 3229056768, "market_updated_at": 1792616709,
                             "station": "Reed Dock", "system": "HIP 41308", "system_id64": 633541300930},
             "distance": 40.2141362932551,
             "source": {"distance_to_arrival": 3, "market_id": 4257409027, "market_updated_at": 1793548256,
                        "station": "Babcock Hub", "system": "HIP 41832", "system_id64": 908419207866},
             "total_profit": 385600}]
    h = parse_result(real)[0]
    assert (h["from_station"], h["to_station"], h["to_system"]) == ("Babcock Hub", "Reed Dock", "HIP 41308")
    assert (h["commodity"], h["amount"], h["buy_price"], h["sell_price"]) == ("Progenitor Cells", 200, 5607, 7535)
    assert h["profit"] == 385600 and h["profit_per_ton"] == 1928
    assert h["distance_ly"] == 40.21 and h["to_arrival_ls"] == 230


# Stations from Spansh's HIP 41832 record (2026-11-25), trimmed to the fields used
HIP_41832_STATIONS = [
    {"name": "K1V-8QZ", "type": "Drake-Class Carrier", "controlling_minor_faction": "FleetCarrier",
     "distance_to_arrival": 0.0, "has_market": True, "has_large_pad": True, "large_pads": 8, "medium_pads": 4},
    {"name": "JKFH", "type": "Drake-Class Carrier", "controlling_minor_faction": "FleetCarrier",
     "distance_to_arrival": 1687.16, "has_market": True, "has_large_pad": True, "large_pads": 16, "medium_pads": 8},
    {"name": "Black Works", "type": "Outpost", "distance_to_arrival": 1684.72, "has_market": True,
     "has_large_pad": False, "large_pads": 0, "medium_pads": 1},
    {"name": "Card City", "type": "Asteroid base", "distance_to_arrival": 1686.74, "has_market": True,
     "has_large_pad": True, "large_pads": 6, "medium_pads": 8},
    {"name": "Fukui Platform", "type": "Outpost", "distance_to_arrival": 1686.91, "has_market": True,
     "has_large_pad": False, "large_pads": 0, "medium_pads": 1},
    {"name": "Babcock Hub", "type": "Outpost", "distance_to_arrival": 3.47, "has_market": True,
     "has_large_pad": False, "large_pads": 0, "medium_pads": 1},
    {"name": "Diesel's Folly", "type": "Coriolis Starport", "distance_to_arrival": 1687.26, "has_market": True,
     "has_large_pad": True, "large_pads": 6, "medium_pads": 12},
    {"name": "Gagnan Gateway", "type": "Planetary Outpost", "distance_to_arrival": 1257.14, "has_market": True,
     "has_large_pad": True, "large_pads": 4, "medium_pads": 4},
    {"name": "Blackman Terminal", "distance_to_arrival": 1268.61, "has_market": True, "has_large_pad": False},
    {"name": "Potter Laboratory", "type": "Settlement", "distance_to_arrival": 1689.61, "has_large_pad": True,
     "large_pads": 1, "medium_pads": 0},
    {"name": "Feng's Genetics", "type": "Settlement", "distance_to_arrival": 1686.97, "has_market": True,
     "has_large_pad": True, "large_pads": 1, "medium_pads": 0},
    {"name": "Hardy Arms Encampment", "type": "Settlement", "distance_to_arrival": 1670.78, "has_market": True,
     "has_large_pad": False, "large_pads": 0, "medium_pads": 1},
]


def test_pick_fallback_stations():
    from custom_components.elite_dangerous.trade_route import pick_fallback_stations

    s = dict(trade_route.DEFAULT_SETTINGS)
    names = [st["name"] for st in pick_fallback_stations(HIP_41832_STATIONS, "Feng's Genetics", s, {"ship_type": "python"})]
    # Same planet first, biggest port first when equally close; no carriers,
    # settlements, planetary outposts, or stations without a type/market
    assert names[:4] == ["Diesel's Folly", "Card City", "Fukui Platform", "Black Works"]
    assert "JKFH" not in names and "Gagnan Gateway" not in names
    assert "Hardy Arms Encampment" not in names and "Blackman Terminal" not in names
    assert names[-1] == "Babcock Hub"  # furthest away
    # Large-pad ship: only stations with a large pad
    names = [st["name"] for st in pick_fallback_stations(HIP_41832_STATIONS, "Feng's Genetics", s, {"ship_type": "anaconda"})]
    assert names == ["Diesel's Folly", "Card City"]
    # Settings switch carriers and planetary back on
    names = [st["name"] for st in pick_fallback_stations(
        HIP_41832_STATIONS, "Feng's Genetics", dict(s, allow_fleet_carriers=True, allow_planetary=True), {})]
    assert "JKFH" in names and "Gagnan Gateway" in names and "Hardy Arms Encampment" in names


async def test_falls_back_to_nearby_station(hass, mqtt_mock, aioclient_mock, fast_poll):
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse
    from yarl import URL

    jobs = {"Feng's Genetics": "JOB-FENG", "Diesel's Folly": "JOB-DIESEL"}

    async def post(method, url, data):
        return AiohttpClientMockResponse(method, url, status=202, json={"job": jobs[data["station"]]})

    aioclient_mock.post(SPANSH_ROUTE_URL, side_effect=post)
    aioclient_mock.get(SPANSH_RESULTS_URL.format(job="JOB-FENG"),
                       json={"state": "completed", "status": "ok", "result": []})
    diesel_route = [seg(("HIP 41832", "Diesel's Folly"), ("HIP 41308", "Reed Dock"),
                        [("Progenitor Cells", 200, 5607, 7535, 385600)], 385600)]
    aioclient_mock.get(SPANSH_RESULTS_URL.format(job="JOB-DIESEL"),
                       json={"state": "completed", "status": "ok", "result": diesel_route})
    aioclient_mock.get(trade_route.SPANSH_SYSTEM_URL.format(id64=908419207866),
                       json={"record": {"name": "HIP 41832", "stations": HIP_41832_STATIONS}})

    await _setup(hass, mqtt_mock)
    async_fire_mqtt_message(hass, "Telemetry/Ship/Type", "python")
    async_fire_mqtt_message(hass, "Telemetry/Ship/CargoCapacity", "200")
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "StarSystem": "HIP 41832", "StationName": "Feng's Genetics",
         "SystemAddress": 908419207866}))
    await hass.async_block_till_done()

    route = hass.states.get(f"sensor.{P}ed_trade_route")
    assert hass.states.get(f"sensor.{P}ed_trade_route_status").state == "ready"
    assert route.attributes["start_station"] == "Diesel's Folly"
    assert "Feng's Genetics" in route.attributes["start_note"]
    assert "Diesel's Folly" in route.attributes["start_note"]
    assert hass.states.get(f"sensor.{P}ed_trade_buy_station").state == "Diesel's Folly"

    # Flying over to Diesel's Folly to buy doesn't throw the route away
    calls = aioclient_mock.call_count
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "StarSystem": "HIP 41832", "StationName": "Diesel's Folly",
         "SystemAddress": 908419207866}))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == calls
    assert hass.states.get(f"sensor.{P}ed_trade_sell_station").state == "Reed Dock"


async def test_fallback_by_system_name(hass, mqtt_mock, aioclient_mock, fast_poll):
    """Without a SystemAddress, the system is found with Spansh's search."""
    aioclient_mock.post(SPANSH_ROUTE_URL, status=202, json={"job": JOB})
    aioclient_mock.get(SPANSH_RESULTS_URL.format(job=JOB), json={"state": "completed", "status": "ok", "result": []})
    aioclient_mock.get(trade_route.SPANSH_SEARCH_URL, json={"results": [
        {"type": "body", "record": {"name": "HIP 41832"}},
        {"type": "system", "record": {"name": "HIP 41832", "stations": HIP_41832_STATIONS}},
    ]})
    await _setup(hass, mqtt_mock)
    async_fire_mqtt_message(hass, "Telemetry/Ship/CargoCapacity", "200")
    async_fire_mqtt_message(hass, "Telemetry/Journal/Docked", json.dumps(
        {"event": "Docked", "StarSystem": "HIP 41832", "StationName": "Feng's Genetics"}))
    await hass.async_block_till_done()
    # 1 route from Feng's + search + MAX_FALLBACKS more route attempts (each POST + GET)
    posts = [c for c in aioclient_mock.mock_calls if c[0].lower() == "post"]
    assert [c[2]["station"] for c in posts] == ["Feng's Genetics", "Diesel's Folly", "Card City", "Fukui Platform"]
    status = hass.states.get(f"sensor.{P}ed_trade_route_status")
    assert status.state == "no route"
    assert "nearby stations" in status.attributes["error"]
