"""Constants for the Elite Dangerous Telemetry integration."""

DOMAIN = "elite_dangerous"
CONF_ROOT_TOPIC = "root_topic"
DEFAULT_ROOT_TOPIC = "Telemetry"

MANUFACTURER = "Frontier Developments (unofficial integration)"
DEVICE_NAME = "Elite Dangerous Commander"

# Every entity ID is "<platform>.<ENTITY_ID_PREFIX><unique_id>", e.g.
# sensor.elite_dangerous_commander_ed_balance
ENTITY_ID_PREFIX = "elite_dangerous_commander_"

# ---- Rank name tables, indexed by level (0-8, except Federation/Empire 0-14) ----
RANK_NAMES = {
    "Combat": [
        "Harmless", "Mostly Harmless", "Novice", "Competent", "Expert",
        "Master", "Dangerous", "Deadly", "Elite",
    ],
    "Trade": [
        "Penniless", "Mostly Penniless", "Peddler", "Dealer", "Merchant",
        "Broker", "Entrepreneur", "Tycoon", "Elite",
    ],
    "Explore": [
        "Aimless", "Mostly Aimless", "Scout", "Surveyor", "Trailblazer",
        "Pathfinder", "Ranger", "Pioneer", "Elite",
    ],
    "CQC": [
        "Helpless", "Mostly Helpless", "Amateur", "Semi Professional",
        "Professional", "Champion", "Hero", "Gladiator", "Elite",
    ],
    "Exobiologist": [
        "Directionless", "Mostly Directionless", "Compiler", "Collector",
        "Cataloguer", "Taxonomist", "Ecologist", "Geneticist", "Elite",
    ],
    "Soldier": [
        "Defenceless", "Mostly Defenceless", "Rookie", "Soldier",
        "Gunslinger", "Warrior", "Gladiator", "Deadeye", "Elite",
    ],
    "Federation": [
        "None", "Recruit", "Cadet", "Midshipman", "Petty Officer",
        "Chief Petty Officer", "Warrant Officer", "Ensign", "Lieutenant",
        "Lt. Commander", "Post Commander", "Post Captain", "Rear Admiral",
        "Vice Admiral", "Admiral",
    ],
    "Empire": [
        "None", "Outsider", "Serf", "Master", "Squire", "Knight", "Lord",
        "Baron", "Viscount", "Count", "Earl", "Marquis", "Duke", "Prince",
        "King",
    ],
}

RANK_CATEGORIES = (
    "Combat", "Trade", "Explore", "Federation", "Empire",
    "CQC", "Exobiologist", "Soldier",
)

RANK_ICONS = {
    "Combat": "mdi:sword-cross",
    "Trade": "mdi:currency-usd",
    "Explore": "mdi:telescope",
    "Federation": "mdi:shield-star",
    "Empire": "mdi:crown",
    "CQC": "mdi:sword",
    "Exobiologist": "mdi:leaf",
    "Soldier": "mdi:pistol",
}

# ---- Ship internal-code -> display-name lookup ----
# Fallback only: the game itself provides the display name via the journal's
# "ShipType_Localised"/"Ship_Localised" field (captured as ship_type_display
# in the coordinator), which is used first and needs no maintenance as new
# ships are added. This table only matters if that field is ever missing.
SHIP_NAMES = {
    "adder": "Adder",
    "anaconda": "Anaconda",
    "asp": "Asp Explorer",
    "asp_scout": "Asp Scout",
    "belugaliner": "Beluga Liner",
    "cobramkiii": "Cobra Mk III",
    "cobramkiv": "Cobra Mk IV",
    "cutter": "Imperial Cutter",
    "diamondback": "Diamondback Scout",
    "diamondbackxl": "Diamondback Explorer",
    "dolphin": "Dolphin",
    "eagle": "Eagle",
    "empire_courier": "Imperial Courier",
    "empire_eagle": "Imperial Eagle",
    "empire_trader": "Imperial Clipper",
    "explorer_nx": "Caspian Explorer",
    "federation_corvette": "Federal Corvette",
    "federation_dropship": "Federal Dropship",
    "federation_dropship_mkii": "Federal Assault Ship",
    "federation_gunship": "Federal Gunship",
    "ferdelance": "Fer-de-Lance",
    "hauler": "Hauler",
    "independant_trader": "Keelback",
    "krait_light": "Krait Phantom",
    "krait_mkii": "Krait Mk II",
    "mamba": "Mamba",
    "mandalay": "Mandalay",
    "orca": "Orca",
    "panthermkii": "Panther Clipper",
    "python": "Python",
    "python_nx": "Python Mk II",
    "sidewinder": "Sidewinder",
    "type6": "Type-6 Transporter",
    "type7": "Type-7 Transporter",
    "type8": "Type-8 Transporter",
    "type9": "Type-9 Heavy",
    "type9_military": "Type-10 Defender",
    "type10": "Type-10 Defender",
    "typex": "Alliance Chieftain",
    "typex_2": "Alliance Crusader",
    "typex_3": "Alliance Challenger",
    "viper": "Viper Mk III",
    "viper_mkiv": "Viper Mk IV",
    "vulture": "Vulture",
}

# ---- Flags (Status.json bit 0) -> (bit_index, name, icon, device_class) ----
FLAGS_BITS = [
    (0, "Docked", "mdi:dock", None),
    (1, "Landed", "mdi:airplane-landing", None),
    (2, "Landing Gear Down", "mdi:airplane-landing", None),
    (3, "Shields Up", "mdi:shield", None),
    (4, "Supercruise", "mdi:fast-forward", None),
    (5, "Flight Assist Off", "mdi:airplane-off", None),
    (6, "Hardpoints Deployed", "mdi:sword-cross", None),
    (7, "In Wing", "mdi:account-group", None),
    (8, "Lights On", "mdi:lightbulb-on", None),
    (9, "Cargo Scoop Deployed", "mdi:package-variant", None),
    (10, "Silent Running", "mdi:volume-off", None),
    (11, "Scooping Fuel", "mdi:fuel", None),
    (12, "SRV Handbrake", "mdi:car-brake-parking", None),
    (13, "SRV Turret View", "mdi:rotate-3d-variant", None),
    (14, "SRV Turret Retracted", "mdi:arrow-collapse-down", None),
    (15, "SRV Drive Assist", "mdi:car-cruise-control", None),
    (16, "FSD Mass Locked", "mdi:lock", None),
    (17, "FSD Charging", "mdi:play-speed", None),
    (18, "FSD Cooldown", "mdi:snowflake", None),
    (19, "Low Fuel", "mdi:gauge-empty", "problem"),
    (20, "Overheating", "mdi:fire-alert", "problem"),
    (21, "Has Lat Long", "mdi:map-marker", None),
    (22, "In Danger", "mdi:alert", "problem"),
    (23, "Being Interdicted", "mdi:alert-circle", "problem"),
    (24, "In Main Ship", "mdi:space-station", None),
    (25, "In Fighter", "mdi:rocket", None),
    (26, "In SRV", "mdi:car", None),
    (27, "HUD Analysis Mode", "mdi:scanner", None),
    (28, "Night Vision", "mdi:weather-night", None),
    (29, "Altitude from Avg Radius", "mdi:altimeter", None),
    (30, "FSD Jump", "mdi:rocket-launch", None),
    (31, "SRV High Beam", "mdi:car-light-high", None),
]

# ---- Flags2 (Odyssey on-foot / multicrew) ----
FLAGS2_BITS = [
    (0, "On Foot", "mdi:walk", None),
    (1, "In Taxi", "mdi:taxi", None),
    (2, "In Multicrew", "mdi:account-multiple", None),
    (3, "On Foot In Station", "mdi:walk", None),
    (4, "On Foot On Planet", "mdi:walk", None),
    (5, "Aim Down Sight", "mdi:crosshairs-gps", None),
    (6, "Low Oxygen", "mdi:air-filter", "problem"),
    (7, "Low Health", "mdi:heart-pulse", "problem"),
    (8, "Cold", "mdi:snowflake", None),
    (9, "Hot", "mdi:fire", None),
    (10, "Very Cold", "mdi:snowflake-alert", "problem"),
    (11, "Very Hot", "mdi:fire-alert", "problem"),
    (12, "Glide Mode", "mdi:paper-airplane", None),
    (13, "On Foot In Hangar", "mdi:walk", None),
    (14, "On Foot Social Space", "mdi:walk", None),
    (15, "On Foot Exterior", "mdi:walk", None),
    (16, "Breathable Atmosphere", "mdi:weather-windy", None),
    (17, "Telepresence Multicrew", "mdi:account-multiple", None),
    (18, "Physical Multicrew", "mdi:account-multiple", None),
    (19, "FSD Hyperdrive Charging", "mdi:play-speed", None),
]
