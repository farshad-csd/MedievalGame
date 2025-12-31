# constants.py - Simulation structure and game mechanics configuration
# This file defines HOW the game works, not WHAT is in it (that's in scenario_*.py files)

# =============================================================================
# GUI SETTINGS
# =============================================================================
DEFAULT_ZOOM = 1.5         # Default camera zoom level (1.5x magnification)
MIN_ZOOM = 0.5             # Minimum zoom (zoomed out)
MAX_ZOOM = 4.0             # Maximum zoom (zoomed in)
ZOOM_SPEED = 0.1           # How much zoom changes per scroll
SPEED_OPTIONS = [1, 2, 10, 20, 100]
BG_COLOR = "#f0f0f0" # UI Background Color
GRID_COLOR = "#cccccc" # UI Grid Color
TEXT_COLOR = "white" # UI Text Color
ROAD_COLOR = "#A89880" # Road cell color

# =============================================================================
# BOARD SETTINGS
# =============================================================================
CELL_SIZE = 35  # Pixels per cell for rendering

# =============================================================================
# TIMING SETTINGS
# =============================================================================
# Tick multiplier - higher = smoother movement but more CPU
# All tick-based values are multiplied by this to maintain same real-time durations
TICK_MULTIPLIER = 10  # 10 ticks per second instead of 1
BASE_UPDATE_INTERVAL = 1000  # Base update interval (before multiplier): 1 second per base tick
UPDATE_INTERVAL = BASE_UPDATE_INTERVAL // TICK_MULTIPLIER  # milliseconds per tick (100ms = 10 ticks/sec)
BASE_TICKS_PER_DAY = 1500  # Base values (in "seconds" of game time): 25 minutes real time - hunger cycle
BASE_TICKS_PER_YEAR = BASE_TICKS_PER_DAY * 3  # 4500 base ticks = 75 minutes = 3 days
TICKS_PER_DAY = BASE_TICKS_PER_DAY * TICK_MULTIPLIER  # Actual tick values (multiplied for smooth movement): 15000 ticks
TICKS_PER_YEAR = BASE_TICKS_PER_YEAR * TICK_MULTIPLIER  # 45000 ticks

# =============================================================================
# CHARACTER SETTINGS
# =============================================================================
# Configure using two intuitive ratios:
#   SPRITE_HW_RATIO: Height-to-Width ratio of the sprite shape
#   SPRITE_TILES_TALL: How many tiles tall the sprite is
#
# Sprite Proportions Reference
# ============================
# H:W Ratio | Tiles Tall | Games
# ----------|------------|----------------------------------------------
# 1:1       | 1          | Pokemon Emerald (Pokemon)
# 1.3:1     | 1          | Heroes of Hammerwatch
# 1.5:1     | 1.5        | A Link to the Past
# 1.6:1     | 2          | Sephiria
# 1.8:1     | 1          | Fallout 2
# 2:1       | 1          | Project Zomboid
# 2:1       | 1.5-2      | Children of Morta
# 2:1       | 2          | Pokemon Emerald (trainers), Pokemon Ranger: SoA, Suikoden 2
# 2.4:1     | 2.25       | Chrono Trigger
SPRITE_HW_RATIO = 1      # Height-to-width ratio (taller = bigger number)
SPRITE_TILES_TALL = 2.0   # How many tiles tall the sprite is

# Calculated dimensions (don't edit these directly)
CHARACTER_HEIGHT = SPRITE_TILES_TALL
CHARACTER_WIDTH = CHARACTER_HEIGHT / SPRITE_HW_RATIO
CHARACTER_EYE_POSITION = 0.2  # Eyes at 20% from top of rectangle

DIRECTIONS_CARDINAL = [(-1, 0), (1, 0), (0, -1), (0, 1)] # Cardinal directions
DIRECTIONS_DIAGONAL = [(-1, -1), (1, -1), (-1, 1), (1, 1)] # Diagonal directions
DIRECTIONS = DIRECTIONS_CARDINAL + DIRECTIONS_DIAGONAL # All 8 directions (cardinal first, then diagonal)

# Movement speed - characters move once every this many ticks
# Set to TICK_MULTIPLIER so characters move at 1 cell per second (same as before)
MOVEMENT_TICK_INTERVAL = TICK_MULTIPLIER
MOVEMENT_SPEED = .8 # Float-based continuous movement: cells per second
SPRINT_SPEED = 1.3      # Sprint (cells/second)

# Collision radius - how close before characters "bump" each other
# Set VERY small to allow characters to squeeze past each other like in ALTTP
# Characters can overlap significantly - this just prevents standing on exact same spot
CHARACTER_COLLISION_RADIUS = 0.15  # Tiny - only blocks when nearly on top of each other
SQUEEZE_THRESHOLD_TICKS = 3  # Ticks blocked before starting to squeeze
SQUEEZE_SLIDE_SPEED = 0.8  # How fast to slide perpendicular (relative to movement speed)

# Adjacency threshold - how close characters need to be for interactions
# Generous range so characters don't need to be perfectly aligned to trade/talk
ADJACENCY_DISTANCE = 1.3 # Within 1.3 cells - can interact from reasonable distance

# Combat range - need to be closer for attacks
COMBAT_RANGE = 1.3  # Within 1.3 cells to attack
ATTACK_ANIMATION_DURATION = 0.25  # Duration in seconds (250ms)
ATTACK_COOLDOWN_TICKS = 5  # Minimum ticks between attacks

# =============================================================================
# IDLE/WANDERING SETTINGS
# =============================================================================
IDLE_SPEED_MULTIPLIER = 0.5  # Idle characters move at half speed
IDLE_MIN_WAIT_TICKS = 30 * TICK_MULTIPLIER  # Minimum time to wait at a spot (3 seconds)
IDLE_MAX_WAIT_TICKS = 80 * TICK_MULTIPLIER  # Maximum time to wait at a spot (8 seconds)
IDLE_PAUSE_CHANCE = 0.3  # 30% chance to pause mid-journey
IDLE_PAUSE_MIN_TICKS = 10 * TICK_MULTIPLIER  # Minimum pause duration (1 second)
IDLE_PAUSE_MAX_TICKS = 30 * TICK_MULTIPLIER  # Maximum pause duration (3 seconds)

# =============================================================================
# SOLDIER PATROL SETTINGS
# =============================================================================
# Soldiers march patrol routes covering ground between buildings
PATROL_SPEED_MULTIPLIER = 0.9  # Marching pace
PATROL_CHECK_MIN_TICKS = 8 * TICK_MULTIPLIER  # Brief pause to survey area (0.8 seconds)
PATROL_CHECK_MAX_TICKS = 20 * TICK_MULTIPLIER  # Maximum survey pause (2 seconds)
PATROL_CHECK_CHANCE = 0.15  # 15% chance to do a brief check when reaching a waypoint
PATROL_APPROACH_DISTANCE = 0.8  # How close to get to a waypoint before moving to next

# =============================================================================
# SLEEP SETTINGS
# =============================================================================
SLEEP_START_FRACTION = 2/3  # Sleep starts at 2/3 of the day (latter 1/3)

# =============================================================================
# HUNGER AND HEALTH SETTINGS
# =============================================================================
MAX_HUNGER = 100
HUNGER_DECAY = 100 / TICKS_PER_DAY  # lose all hunger in 1 day (same rate, more ticks)
HUNGER_CRITICAL = 40  # always seek wheat at or below this
HUNGER_CHANCE_THRESHOLD = 60  # chance to seek wheat between CRITICAL and this

# Starvation settings
STARVATION_THRESHOLD = 0  # hunger at or below this = starving
STARVATION_DAMAGE = 1 / TICK_MULTIPLIER  # health lost per tick while starving (same rate per second)
STARVATION_MORALITY_INTERVAL = 30  # every 30 health lost, check for morality loss (unchanged, based on health not ticks)
STARVATION_MORALITY_CHANCE = 0.5  # 50% chance to lose 1 morality
STARVATION_FREEZE_HEALTH = 20  # freeze in place when health drops to this while starving

# =============================================================================
# CRIME SETTINGS
# =============================================================================
# Crime intensity (affects witness/reaction/pursuit range)
# The intensity IS the range in cells
CRIME_INTENSITY_MURDER = 17  # 17 cells (2.5x original)
CRIME_INTENSITY_THEFT = 10   # 10 cells (2.5x original)

# Theft timing (tick-based, scales with game speed)
THEFT_PATIENCE_TICKS = 60 * TICK_MULTIPLIER  # 60 seconds at 1x speed - how long to wait for crops
THEFT_COOLDOWN_TICKS = 30 * TICK_MULTIPLIER  # 30 seconds at 1x speed - cooldown after giving up

# =============================================================================
# SKILL DEFINITIONS
# =============================================================================
# Skills have: name, category ('combat', 'benign', or 'both')
# All characters have 0-100 points in each skill
SKILLS = {
    "strength": {"name": "Strength", "category": "combat"},
    "agility": {"name": "Agility", "category": "combat"},
    "stealth": {"name": "Stealth", "category": "combat"},
    "weapon_mastery": {"name": "Weapon Mastery", "category": "combat"},
    "explosives": {"name": "Explosives", "category": "combat"},
    "blacksmithing": {"name": "Blacksmithing", "category": "benign"},
    "lumberjacking": {"name": "Lumberjacking", "category": "benign"},
    "mining": {"name": "Mining", "category": "benign"},
    "construction": {"name": "Construction", "category": "both"},
    "farming": {"name": "Farming", "category": "benign"},
    "shepherding": {"name": "Shepherding", "category": "benign"},
    "carpentry": {"name": "Carpentry", "category": "both"},
    "doctor": {"name": "Doctor", "category": "both"},
    "art": {"name": "Art", "category": "benign"},
    "herbalism": {"name": "Herbalism", "category": "benign"},
    "brewing": {"name": "Brewing", "category": "benign"},
    "tailor": {"name": "Tailor", "category": "benign"},
    "bard": {"name": "Bard", "category": "benign"},
    "hospitality": {"name": "Hospitality", "category": "benign"},
    "lockpicking": {"name": "Lockpicking", "category": "benign"},
    "mercantile": {"name": "Mercantile", "category": "benign"},
}

# =============================================================================
# INVENTORY SETTINGS
# =============================================================================
# Central item registry - all items and their properties
ITEMS = {
    "wheat": {
        "name": "Wheat",
        "price": 5,
        "stack_size": 15,
    },
    "gold": {
        "name": "Gold",
        "price": 1,
        "stack_size": None,  # Infinite stacking
    },
    "bread": {
        "name": "Bread",
        "price": 7,
        "stack_size": 15,
        "hunger_value": 33,  # How much hunger restored per unit
    },
}

INVENTORY_SLOTS = 5
BARREL_SLOTS = 30

# =============================================================================
# BREAD SETTINGS
# =============================================================================
WHEAT_TO_BREAD_RATIO = 1  # 1 wheat -> 1 bread
BREAD_PER_BITE = 1
BREAD_BUFFER_TARGET = 3  # Characters want this much bread in inventory

# =============================================================================
# FARM SETTINGS
# =============================================================================
FARM_CELL_YIELD = 1
FARM_CELL_HARVEST_INTERVAL = TICKS_PER_DAY  # Uses multiplied value
FARM_HARVEST_TIME = 5 * TICK_MULTIPLIER  # 5 seconds worth of ticks
FARM_REPLANT_TIME = 5 * TICK_MULTIPLIER  # 5 seconds worth of ticks
FARM_CELL_COLORS = {
    "ready": "#90EE90",
    "harvesting": "#90EE90",
    "replanting": "#8B4513",
    "growing": "#FFD700"
}

# =============================================================================
# JOB DEFINITIONS AND TIERS
# =============================================================================
# Jobs within each tier are interchangeable in their importance
# Lower tier number = higher status/desirability

JOB_TIERS = {
    # TIER 1 — RULERS
    "King": {"tier": 1},
    "Queen": {"tier": 1},
    
    # TIER 2 — TRUSTED ADVISORS AND ADMINISTRATORS
    "Steward": {
        "tier": 2,
        "color": "#8B008B",
        "requires": {"mercantile": 50},  # Also requires allegiance (checked in code)
    },
    "Historian": {"tier": 2},
    "Weapons Trainer": {"tier": 2},
    
    # TIER 3 — SKILLED TRADES WITH STATUS
    "Trader": {
        "tier": 3,
        "color": "#FFD700",
        "requires": {"mercantile": 20},
    },
    "Soldier": {
        "tier": 3,
        "color": "#FF69B4",
        "requires": {"morality_min": 5, "confidence_min": 7, "cunning_max": 5},
    },
    "Farmer": {
        "tier": 3,
        "color": "#39db34",
        "requires": {"farming": 40},
    },
    "Doctor": {"tier": 3},
    "Blacksmith": {"tier": 3},
    "Carpenter": {"tier": 3},
    "Innkeeper": {"tier": 3},
    "Builder": {"tier": 3},
    
    # TIER 4 — COMFORTABLE SKILLED WORK
    "Servant": {"tier": 4},
    "Tailor": {"tier": 4},
    "Medicine Vendor": {"tier": 4},
    "Alcohol Vendor": {"tier": 4},
    "Explosives Vendor": {"tier": 4},
    "Artist": {"tier": 4},
    
    # TIER 5 — RESPECTABLE BUT HARDER LABOR
    "Hunter": {"tier": 5},
    "Fisherman": {"tier": 5},
    "Shepherd": {"tier": 5},
    "Mercenary": {"tier": 5},
    "Lumberjack": {"tier": 5},
    "Miner": {"tier": 5},
    "Bard": {"tier": 5},
}

# Default tier for jobs not in JOB_TIERS (unemployed, etc.)
DEFAULT_JOB_TIER = 99


# =============================================================================
# VENDOR SYSTEM
# =============================================================================
# Maps vendor job types to the goods they sell
# Each vendor type can sell one or more goods
VENDOR_GOODS = {
    "Farmer": ["wheat"],
}

TRADE_COOLDOWN = 3 * TICK_MULTIPLIER  # 3 seconds worth of ticks (quick trading)

# =============================================================================
# STEWARD / TAX SETTINGS
# =============================================================================
STEWARD_TAX_INTERVAL = TICKS_PER_YEAR  # Uses multiplied value
STEWARD_TAX_AMOUNT = 90
SOLDIER_WHEAT_PAYMENT = 6
TAX_GRACE_PERIOD = TICKS_PER_DAY * 2 // 5  # 10 real minutes before steward goes to collect
ALLEGIANCE_WHEAT_TIMEOUT = 30 * TICK_MULTIPLIER  # How long until soldiers quit

# =============================================================================
# AREA ROLES
# =============================================================================
# Standard roles that areas can have - game logic uses these roles, not area names
# Scenarios assign roles to their areas
AREA_ROLES = {
    "village": "A settlement/economic hub",
    "market": "Where trading happens, in a village",
    "military_housing": "Where soldiers live and sleep, in a village",
    "farmhouse": "Where a farmer with a farm lives",
    "farm": "Where wheat is grown, part of a village",
    "encampment": "No purpose"
}