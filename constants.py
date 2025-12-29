# constants.py - Simulation structure and game mechanics configuration
# This file defines HOW the game works, not WHAT is in it (that's in scenario.py)

# =============================================================================
# BOARD SETTINGS
# =============================================================================
SIZE = 20
CELL_SIZE = 35

# =============================================================================
# TICK RATE SETTINGS
# =============================================================================
# Tick multiplier - higher = smoother movement but more CPU
# All tick-based values are multiplied by this to maintain same real-time durations
TICK_MULTIPLIER = 10  # 10 ticks per second instead of 1

# Base update interval (before multiplier)
BASE_UPDATE_INTERVAL = 1000  # 1 second per base tick
UPDATE_INTERVAL = BASE_UPDATE_INTERVAL // TICK_MULTIPLIER  # milliseconds per tick (100ms = 10 ticks/sec)

# =============================================================================
# AREA ROLES
# =============================================================================
# Standard roles that areas can have - game logic uses these roles, not area names
# Scenarios assign roles to their areas
AREA_ROLES = {
    "military_housing": "Where soldiers live and sleep",
    "farm": "Where food is grown",
    "market": "Where trading happens",
    "residential": "General village living area",
}

# Standard allegiance name for the main settlement
PRIMARY_ALLEGIANCE = "VILLAGE"

# =============================================================================
# TIME SETTINGS
# =============================================================================
# Base values (in "seconds" of game time)
BASE_TICKS_PER_DAY = 1500  # 25 minutes real time - hunger cycle
BASE_TICKS_PER_YEAR = BASE_TICKS_PER_DAY * 3  # 4500 base ticks = 75 minutes = 3 days

# Actual tick values (multiplied for smooth movement)
TICKS_PER_DAY = BASE_TICKS_PER_DAY * TICK_MULTIPLIER  # 15000 ticks
TICKS_PER_YEAR = BASE_TICKS_PER_YEAR * TICK_MULTIPLIER  # 45000 ticks

# =============================================================================
# CRIME SETTINGS
# =============================================================================
# Crime intensity (affects witness/reaction/pursuit range)
# The intensity IS the range in cells
CRIME_INTENSITY_MURDER = 17  # 17 cells (2.5x original)
CRIME_INTENSITY_THEFT = 10   # 10 cells (2.5x original)

# =============================================================================
# HUNGER AND HEALTH SETTINGS
# =============================================================================
MAX_HUNGER = 100
HUNGER_DECAY = 100 / TICKS_PER_DAY  # lose all hunger in 1 day (same rate, more ticks)
HUNGER_CRITICAL = 40  # always seek food at or below this
HUNGER_CHANCE_THRESHOLD = 60  # chance to seek food between CRITICAL and this

# Starvation settings
STARVATION_THRESHOLD = 0  # hunger at or below this = starving
STARVATION_DAMAGE = 1 / TICK_MULTIPLIER  # health lost per tick while starving (same rate per second)
STARVATION_MORALITY_INTERVAL = 30  # every 30 health lost, check for morality loss (unchanged, based on health not ticks)
STARVATION_MORALITY_CHANCE = 0.5  # 50% chance to lose 1 morality
STARVATION_FREEZE_HEALTH = 20  # freeze in place when health drops to this while starving

# =============================================================================
# INVENTORY SETTINGS
# =============================================================================
INVENTORY_SLOTS = 5
FOOD_STACK_SIZE = 15  # Max food per inventory slot
# Money is infinitely stackable and takes 1 slot

# =============================================================================
# FOOD AND EATING SETTINGS
# =============================================================================
FOOD_PER_BITE = 1
HUNGER_PER_FOOD = 33
FOOD_TO_EAT = 3
FOOD_BUFFER_TARGET = 3  # Characters want 1 day of food in inventory

# =============================================================================
# BARREL SETTINGS
# =============================================================================
BARREL_SLOTS = 30
BARREL_FOOD_STACK_SIZE = 15  # Same as character inventory

# =============================================================================
# FARM SETTINGS
# =============================================================================
FARM_CELL_YIELD = 1
FARM_CELL_HARVEST_INTERVAL = TICKS_PER_DAY  # Uses multiplied value
FARM_HARVEST_TIME = 5 * TICK_MULTIPLIER  # 5 seconds worth of ticks
FARM_REPLANT_TIME = 5 * TICK_MULTIPLIER  # 5 seconds worth of ticks

# =============================================================================
# TRADING SETTINGS
# =============================================================================
FOOD_PRICE_PER_UNIT = 5  # 5 gold per food
FARMER_PERSONAL_RESERVE = 10  # Food needed to feed self for a year (~3 food/day × 3 days)
TRADE_COOLDOWN = 3 * TICK_MULTIPLIER  # 3 seconds worth of ticks (quick trading)

# =============================================================================
# VENDOR SYSTEM
# =============================================================================
# Maps vendor job types to the goods they sell
# Each vendor type can sell one or more goods
VENDOR_GOODS = {
    "Farmer": ["food"],
    "Trader": ["food", "medicine", "tools", "clothing"],
    "Medicine Vendor": ["medicine"],
    "Alcohol Vendor": ["alcohol"],
    "Explosives Vendor": ["explosives"],
    "Blacksmith": ["weapons", "tools", "armor"],
    "Tailor": ["clothing"],
    "Innkeeper": ["food", "alcohol", "lodging"],
    "Doctor": ["medicine", "medical_service"],
    "Carpenter": ["tools", "furniture"],
    "Hunter": ["food", "leather", "furs"],
    "Fisherman": ["food"],
}

# Prices per unit of each goods type
GOODS_PRICES = {
    "food": 5,
    "medicine": 15,
    "alcohol": 8,
    "explosives": 50,
    "weapons": 100,
    "tools": 25,
    "armor": 150,
    "clothing": 20,
    "lodging": 10,
    "medical_service": 30,
    "furniture": 40,
    "leather": 12,
    "furs": 35,
}

# Stack sizes for different goods in inventory
GOODS_STACK_SIZES = {
    "food": 15,
    "medicine": 10,
    "alcohol": 10,
    "explosives": 5,
    "weapons": 1,
    "tools": 5,
    "armor": 1,
    "clothing": 5,
    "lodging": 1,  # Services don't stack
    "medical_service": 1,
    "furniture": 1,
    "leather": 10,
    "furs": 5,
}

# Personal reserve amounts - vendors keep this much for themselves
VENDOR_PERSONAL_RESERVE = {
    "food": 10,
    "medicine": 2,
    "alcohol": 2,
    "explosives": 1,
    "weapons": 0,
    "tools": 1,
    "armor": 0,
    "clothing": 1,
    "lodging": 0,
    "medical_service": 0,
    "furniture": 0,
    "leather": 2,
    "furs": 1,
}

# =============================================================================
# STEWARD / TAX SETTINGS
# =============================================================================
STEWARD_TAX_INTERVAL = TICKS_PER_YEAR  # Uses multiplied value
STEWARD_TAX_AMOUNT = 90
SOLDIER_FOOD_PAYMENT = 6
TAX_GRACE_PERIOD = TICKS_PER_DAY // 2  # Uses multiplied value

# =============================================================================
# ALLEGIANCE SETTINGS
# =============================================================================
ALLEGIANCE_FOOD_TIMEOUT = 30 * TICK_MULTIPLIER  # 30 seconds worth of ticks

# =============================================================================
# MOVEMENT
# =============================================================================
# Cardinal directions
DIRECTIONS_CARDINAL = [(-1, 0), (1, 0), (0, -1), (0, 1)]
# Diagonal directions
DIRECTIONS_DIAGONAL = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
# All 8 directions (cardinal first, then diagonal)
DIRECTIONS = DIRECTIONS_CARDINAL + DIRECTIONS_DIAGONAL

# Movement speed - characters move once every this many ticks
# Set to TICK_MULTIPLIER so characters move at 1 cell per second (same as before)
MOVEMENT_TICK_INTERVAL = TICK_MULTIPLIER

# =============================================================================
# ALTTP-STYLE MOVEMENT (Float-based continuous movement)
# =============================================================================
# Movement speed in cells per second (ALTTP Link moves ~1.5 tiles/sec)
MOVEMENT_SPEED = 1.0 # cells per second (doubled for snappier feel)

# Character hitbox dimensions (in cells, not pixels)
# ALTTP Link is roughly 16x22 in a 16x16 world (1.0 x 1.375 cells)
# Characters are taller than wide, allowing them to weave between obstacles
# =============================================================================
# CHARACTER SPRITE DIMENSIONS
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

SPRITE_HW_RATIO = 1.5      # Height-to-width ratio (taller = bigger number)
SPRITE_TILES_TALL = 1    # How many tiles tall the sprite is

# Calculated dimensions (don't edit these directly)
CHARACTER_HEIGHT = SPRITE_TILES_TALL
CHARACTER_WIDTH = CHARACTER_HEIGHT / SPRITE_HW_RATIO
CHARACTER_EYE_POSITION = 0.2  # Eyes at 10% from top of rectangle

# =============================================================================
# CAMERA SETTINGS
# =============================================================================
DEFAULT_ZOOM = 1.5         # Default camera zoom level (1.5x magnification)
MIN_ZOOM = 0.5             # Minimum zoom (zoomed out)
MAX_ZOOM = 4.0             # Maximum zoom (zoomed in)
ZOOM_SPEED = 0.1           # How much zoom changes per scroll

# =============================================================================
# PLAYER SPRINT
# =============================================================================
SPRINT_SPEED = 2         # Player speed while sprinting (cells/second)

# Collision radius - how close before characters "bump" each other
# Set VERY small to allow characters to squeeze past each other like in ALTTP
# Characters can overlap significantly - this just prevents standing on exact same spot
CHARACTER_COLLISION_RADIUS = 0.15  # Tiny - only blocks when nearly on top of each other

# Adjacency threshold - how close characters need to be for interactions
# Generous range so characters don't need to be perfectly aligned to trade/talk
ADJACENCY_DISTANCE = 1.3 # Within 1.8 cells - can interact from reasonable distance

# Combat range - need to be closer for attacks
COMBAT_RANGE = 1.3  # Within 1.3 cells to attack

# Legacy constants for compatibility (no longer used for actual movement)
PLAYER_MOVE_INTERVAL_MS = 480  # Kept for reference
NPC_MOVE_DURATION_MS = 960
PLAYER_MOVE_DURATION_MS = 720
NPC_MOVE_TICK_INTERVAL = 6

# =============================================================================
# SLEEP SETTINGS
# =============================================================================
SLEEP_START_FRACTION = 2/3  # Sleep starts at 2/3 of the day (latter 1/3)

# =============================================================================
# VISUAL SETTINGS
# =============================================================================
# Farm cell state colors
FARM_CELL_COLORS = {
    "ready": "#90EE90",
    "harvesting": "#90EE90",
    "replanting": "#8B4513",
    "growing": "#FFD700"
}

# Job-based colors (dynamic, overrides morality-based color)
JOB_COLORS = {
    "Farmer": "#39db34",
    "Steward": "#8B008B",
    "Soldier": "#FF69B4",
    "Trader": "#FFD700",  # Gold color for traders
}

# UI Colors
BG_COLOR = "#f0f0f0"
GRID_COLOR = "#cccccc"
TEXT_COLOR = "white"

# =============================================================================
# JOB DEFINITIONS AND TIERS
# =============================================================================
# Jobs within each tier are interchangeable in their importance
# Lower tier number = higher status/desirability

JOB_TIERS = {
    # TIER 1 — RULERS
    "King": 1,              # Absolute top, answers to no one
    "Queen": 1,             # Shares royal privilege and comfort
    
    # TIER 2 — TRUSTED ADVISORS AND ADMINISTRATORS
    "Steward": 2,           # Power, respect, comfortable living (Village Leader)
    "Historian": 2,         # Literate, valued, clean work, close to power
    "Weapons Trainer": 2,   # Skilled, respected, secure position
    
    # TIER 3 — SKILLED TRADES WITH STATUS
    "Trader": 3,            # Wealth potential, independence, travels
    "Soldier": 3,           # Steady pay and food, but dangerous and takes orders
    "Farmer": 3,            # Hard labor, low pay, dependent on others
    "Doctor": 3,            # Rare skill, well-paid, respected
    "Blacksmith": 3,        # Essential, well-paid, respected craft
    "Carpenter": 3,         # Skilled, always needed
    "Innkeeper": 3,         # Owns property, steady income, social hub
    "Builder": 3,           # Good pay, essential work
    
    # TIER 4 — COMFORTABLE SKILLED WORK
    "Servant": 4,           # No independence, does what they're told, lowest free status
    "Tailor": 4,            # Clean work, steady demand
    "Medicine Vendor": 4,   # Decent income, specialized knowledge
    "Alcohol Vendor": 4,    # Steady demand, social role
    "Explosives Vendor": 4, # Rare skill, dangerous but lucrative
    "Artist": 4,            # Uncertain income but clean, creative work
    
    # TIER 5 — RESPECTABLE BUT HARDER LABOR
    "Hunter": 5,            # Independence, skill-based, but weather-dependent
    "Fisherman": 5,         # Steady food source, but hard and wet work
    "Shepherd": 5,          # Lonely, exposed to elements, but peaceful
    "Mercenary": 5,         # Good pay sometimes, but no security, violent, disreputable
    "Lumberjack": 5,        # Dangerous, exhausting, low status
    "Miner": 5,             # Dangerous, dark, short lifespan, grim work
    "Bard": 5,              # Freedom, travels, fed and housed by audiences
}

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
# GAME SPEED OPTIONS
# =============================================================================
SPEED_OPTIONS = [1, 2, 10, 20, 100]