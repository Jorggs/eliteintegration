"""MQTT-backed coordinator for the Elite Dangerous Telemetry integration.

Subscribes once to every topic the standalone ED-MQTT-Telemetry app publishes
and keeps a single shared `data` dict up to date. Entities read from this
dict rather than each managing their own MQTT subscription.
"""

from __future__ import annotations

import json
import logging

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import RANK_CATEGORIES

_LOGGER = logging.getLogger(__name__)

# Home Assistant event fired for every *live* journal event, e.g.
#   trigger: event / event_type: elite_dangerous_journal
#   event_data: {event: UnderAttack}
JOURNAL_EVENT_TYPE = "elite_dangerous_journal"


def signal_name(entry_id: str) -> str:
    return f"elite_dangerous_update_{entry_id}"


class EliteDangerousCoordinator:
    """Owns the MQTT subscriptions and the shared telemetry state."""

    def __init__(self, hass: HomeAssistant, entry_id: str, root_topic: str):
        self.hass = hass
        self.entry_id = entry_id
        self.root_topic = root_topic.rstrip("/")
        self._unsubscribes = []

        self.data: dict = {
            "flags": 0,
            "flags2": 0,
            "fuel_main": 0.0,
            "fuel_reservoir": 0.0,
            "pips_sys": 0,
            "pips_eng": 0,
            "pips_wep": 0,
            "cargo": 0.0,
            "legal_state": "Unknown",
            "balance": 0,
            "guifocus": 0,
            "firegroup": 0,
            "current_system": "",
            "current_station": "",
            "current_body": "",
            "system_population": 0,
            "position": [0.0, 0.0, 0.0],
            "ship_type": "",
            "ship_type_display": "",
            "ship_name": "",
            "jump_range": 0.0,
            # From the ship's Loadout; None until the first Loadout arrives
            "fuel_capacity": None,
            "reservoir_capacity": None,
            "cargo_capacity": None,
            "ship_ident": None,
            "rebuy": None,
            "hull_value": None,
            "modules_value": None,
            # From the docking journal events
            "docking_state": "Idle",
            "docking_pad": None,
            "docking_station": None,
            "docking_denied_reason": None,
            "rank": {},
            "progress": {},
            "statistics": {},
            "game_running": False,
            # Jump target: the system/star the next hyperspace jump goes to,
            # from FSDTarget or StartJump (whichever is newer)
            "jump_target_system": None,
            "jump_target_star_class": None,
            "jump_target_ts": "",
            "jumps_remaining": None,
            # Last hyperspace jump actually started -- used to work out the
            # star class of the system you're in now
            "last_jump_system": None,
            "last_jump_star_class": None,
            # Most recent live journal event (name)
            "last_journal_event": None,
        }

    def _notify(self):
        async_dispatcher_send(self.hass, signal_name(self.entry_id))

    async def async_setup(self):
        """Subscribe to every topic we care about."""
        t = self.root_topic

        async def sub(topic: str, handler):
            unsub = await mqtt.async_subscribe(self.hass, topic, handler, qos=0)
            self._unsubscribes.append(unsub)

        # ---- Dashboard ----
        await sub(f"{t}/Dashboard/Flags", self._make_int_handler("flags"))
        await sub(f"{t}/Dashboard/Flags2", self._make_int_handler("flags2"))
        await sub(f"{t}/Dashboard/Fuel/Main", self._make_float_handler("fuel_main"))
        await sub(f"{t}/Dashboard/Fuel/Reservoir", self._make_float_handler("fuel_reservoir"))
        await sub(f"{t}/Dashboard/Pips/Sys", self._make_int_handler("pips_sys"))
        await sub(f"{t}/Dashboard/Pips/Eng", self._make_int_handler("pips_eng"))
        await sub(f"{t}/Dashboard/Pips/Wep", self._make_int_handler("pips_wep"))
        await sub(f"{t}/Dashboard/Cargo", self._make_float_handler("cargo"))
        await sub(f"{t}/Dashboard/LegalState", self._make_str_handler("legal_state"))
        await sub(f"{t}/Dashboard/Balance", self._make_int_handler("balance"))
        await sub(f"{t}/Dashboard/GuiFocus", self._make_int_handler("guifocus"))
        await sub(f"{t}/Dashboard/FireGroup", self._make_int_handler("firegroup"))

        # ---- Location ----
        await sub(f"{t}/Location/System", self._make_str_handler("current_system"))
        await sub(f"{t}/Location/Station", self._make_str_handler("current_station"))
        await sub(f"{t}/Location/Body", self._make_str_handler("current_body"))
        await sub(f"{t}/Location/Population", self._make_int_handler("system_population"))
        await sub(f"{t}/Location/StarPos", self._on_starpos)

        # ---- Ship ----
        await sub(f"{t}/Ship/Name", self._make_str_handler("ship_name"))
        await sub(f"{t}/Ship/Type", self._make_str_handler("ship_type"))
        await sub(f"{t}/Ship/TypeDisplay", self._make_str_handler("ship_type_display"))
        await sub(f"{t}/Ship/JumpRange", self._make_float_handler("jump_range"))
        await sub(f"{t}/Ship/FuelCapacity", self._make_float_handler("fuel_capacity"))
        await sub(f"{t}/Ship/ReservoirCapacity", self._make_float_handler("reservoir_capacity"))
        await sub(f"{t}/Ship/CargoCapacity", self._make_float_handler("cargo_capacity"))
        await sub(f"{t}/Ship/Ident", self._make_str_handler("ship_ident"))
        await sub(f"{t}/Ship/Rebuy", self._make_int_handler("rebuy"))
        await sub(f"{t}/Ship/HullValue", self._make_int_handler("hull_value"))
        await sub(f"{t}/Ship/ModulesValue", self._make_int_handler("modules_value"))

        # ---- Docking ----
        await sub(f"{t}/Docking", self._on_docking)

        # ---- Rank / Progress / Statistics ----
        await sub(f"{t}/Journal/Rank", self._make_dict_handler("rank", RANK_CATEGORIES))
        await sub(f"{t}/Journal/Progress", self._make_dict_handler("progress", RANK_CATEGORIES))
        await sub(f"{t}/Journal/Statistics", self._on_statistics)

        # ---- GameRunning ----
        await sub(f"{t}/GameRunning", self._on_game_running)

        # ---- Every journal event (Processed mode: one topic per event) ----
        await sub(f"{t}/Journal/+", self._on_journal)

    async def async_unload(self):
        for unsub in self._unsubscribes:
            unsub()
        self._unsubscribes.clear()

    # ---- generic scalar handlers ----

    def _make_int_handler(self, key: str):
        @callback
        def handler(msg):
            try:
                self.data[key] = int(float(msg.payload))
            except (ValueError, TypeError):
                return
            self._notify()
        return handler

    def _make_float_handler(self, key: str):
        @callback
        def handler(msg):
            try:
                self.data[key] = float(msg.payload)
            except (ValueError, TypeError):
                return
            self._notify()
        return handler

    def _make_str_handler(self, key: str):
        @callback
        def handler(msg):
            self.data[key] = msg.payload
            self._notify()
        return handler

    def _make_dict_handler(self, key: str, categories):
        @callback
        def handler(msg):
            try:
                payload = json.loads(msg.payload)
            except (ValueError, TypeError):
                return
            self.data[key] = {cat: payload[cat] for cat in categories if cat in payload}
            self._notify()
        return handler

    # ---- special handlers ----

    @callback
    def _on_starpos(self, msg):
        try:
            pos = json.loads(msg.payload)
            if isinstance(pos, list) and len(pos) >= 3:
                self.data["position"] = [float(pos[0]), float(pos[1]), float(pos[2])]
        except (ValueError, TypeError):
            return
        self._notify()

    @callback
    def _on_statistics(self, msg):
        try:
            payload = json.loads(msg.payload)
        except (ValueError, TypeError):
            return
        self.data["statistics"] = {
            k: v for k, v in payload.items() if k not in ("timestamp", "event")
        }
        self._notify()

    @callback
    def _on_game_running(self, msg):
        self.data["game_running"] = msg.payload.strip().lower() == "true"
        self._notify()

    @callback
    def _on_docking(self, msg):
        """Consolidated docking item: {"State", "Pad", "Station", "DeniedReason"}."""
        try:
            payload = json.loads(msg.payload)
        except (ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        pad = payload.get("Pad")
        try:
            pad = int(pad) if pad not in (None, "") else None
        except (ValueError, TypeError):
            pad = None
        self.data["docking_state"] = payload.get("State") or "Idle"
        self.data["docking_pad"] = pad
        self.data["docking_station"] = payload.get("Station") or None
        self.data["docking_denied_reason"] = payload.get("DeniedReason") or None
        self._notify()

    # ---- journal events ----

    @callback
    def _on_journal(self, msg):
        """Handles every Journal/<Event> topic.

        Feeds the jump-target state, and fires an `elite_dangerous_journal`
        Home Assistant event for live messages only. Retained messages
        (replayed by the broker when we subscribe, e.g. after an HA restart)
        update state but never fire events, so old events don't replay.
        """
        try:
            payload = json.loads(msg.payload)
        except (ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        name = payload.get("event") or msg.topic.rsplit("/", 1)[-1]
        ts = payload.get("timestamp") or ""
        changed = False

        if name == "FSDTarget":
            if ts >= self.data["jump_target_ts"]:
                self.data["jump_target_ts"] = ts
                self.data["jump_target_system"] = payload.get("Name")
                self.data["jump_target_star_class"] = payload.get("StarClass")
                if "RemainingJumpsInRoute" in payload:
                    self.data["jumps_remaining"] = payload.get("RemainingJumpsInRoute")
                changed = True

        elif name == "StartJump":
            # Only hyperspace jumps carry a destination star; a StartJump for
            # supercruise has no StarClass and is ignored here.
            if payload.get("JumpType") == "Hyperspace" and payload.get("StarClass"):
                self.data["last_jump_system"] = payload.get("StarSystem")
                self.data["last_jump_star_class"] = payload.get("StarClass")
                if ts >= self.data["jump_target_ts"]:
                    self.data["jump_target_ts"] = ts
                    self.data["jump_target_system"] = payload.get("StarSystem")
                    self.data["jump_target_star_class"] = payload.get("StarClass")
                changed = True

        elif name == "NavRouteClear":
            if ts >= self.data["jump_target_ts"]:
                self.data["jumps_remaining"] = 0
                changed = True

        if not msg.retain:
            self.data["last_journal_event"] = name
            changed = True
            event_data = {"event": name, "entry_id": self.entry_id}
            event_data.update({k: v for k, v in payload.items() if k != "event"})
            self.hass.bus.async_fire(JOURNAL_EVENT_TYPE, event_data)

        if changed:
            self._notify()
