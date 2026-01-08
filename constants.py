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
BG_COLOR = "#000000" # UI Background Color
GRID_COLOR = "#cccccc" # UI Grid Color
ROAD_COLOR = "#A89880" # Road cell color
START_MUTED = True         # Start with music muted (toggle with M key)

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
# 2:1       | 1          | Drova: Forsaken Kin
# 2:1       | 1.5-2      | Children of Morta
# 2:1       | 2          | Pokemon Emerald (trainers), Pokemon Ranger: SoA, Suikoden 2
# 2.4:1     | 2.25       | Chrono Trigger
SPRITE_HW_RATIO = 1      # Height-to-width ratio (taller = bigger number)
SPRITE_TILES_TALL = 2.5   # How many tiles tall the sprite is

# Calculated dimensions (don't edit these directly)
CHARACTER_HEIGHT = SPRITE_TILES_TALL
CHARACTER_WIDTH = CHARACTER_HEIGHT / SPRITE_HW_RATIO

DIRECTIONS_CARDINAL = [(-1, 0), (1, 0), (0, -1), (0, 1)] # Cardinal directions
DIRECTIONS_DIAGONAL = [(-1, -1), (1, -1), (-1, 1), (1, 1)] # Diagonal directions
DIRECTIONS = DIRECTIONS_CARDINAL + DIRECTIONS_DIAGONAL # All 8 directions (cardinal first, then diagonal)

# Movement speed - characters move once every this many ticks
# Set to TICK_MULTIPLIER so characters move at 1 cell per second (same as before)
MOVEMENT_SPEED = .8 # Float-based continuous movement: cells per second
SPRINT_SPEED = 1.2      # Sprint (cells/second)

# Collision radius - how close before characters "bump" each other
# Set VERY small to allow characters to squeeze past each other like in ALTTP
# Characters can overlap significantly - this just prevents standing on exact same spot
CHARACTER_COLLISION_RADIUS = 0.15  # Tiny - only blocks when nearly on top of each other
SQUEEZE_THRESHOLD_TICKS = 3  # Ticks blocked before starting to squeeze
SQUEEZE_SLIDE_SPEED = 0.8  # How fast to slide perpendicular (relative to movement speed)

# Adjacency threshold - how close characters need to be for object interactions
ADJACENCY_DISTANCE = 0.8  # Within 0.8 cells for barrels, beds, stoves, dialogue, etc.
# Interact distance - tighter radius for player E interactions (must also be facing target)
INTERACT_DISTANCE = 0.8  # Within 0.8 cells for E interactions

# Door threshold - how close to a door to trigger zone transition (entering/exiting buildings)
DOOR_THRESHOLD = 0.5

# =============================================================================
# COMBAT SETTINGS
# =============================================================================
# Weapon reach - actual hit detection range for attacks
WEAPON_REACH = 1.4  # How far a sword swing can hit

# NPC combat behavior distances
MELEE_ATTACK_DISTANCE = 1.4  # NPCs attack when this close to target
COMBAT_SPACE = 1.0  # NPCs backpedal if target gets closer than this
COMBAT_SPRINT_DISTANCE = .5  # NPCs sprint if target is this far beyond attack range

# Attack timing
ATTACK_ANIMATION_DURATION = 0.25  # Duration in seconds (250ms)
ATTACK_COOLDOWN_TICKS = 5  # Minimum ticks between attacks
ATTACK_DAMAGE_TICKS_BEFORE_END = 1  # Ticks before animation ends that damage registers (0 = at end)

# Heavy attack settings (player only)
# Player must hold attack button for THRESHOLD time before charge begins
# Then charge fills over CHARGE_TIME seconds (total hold = THRESHOLD + CHARGE_TIME for max)
HEAVY_ATTACK_THRESHOLD_TICKS = 3  # ~0.25 seconds at 10 ticks/sec before charge starts
HEAVY_ATTACK_CHARGE_TICKS = 10   # ~2.0 seconds at 10 ticks/sec to fill meter
HEAVY_ATTACK_MIN_MULTIPLIER = 1.001  # Damage multiplier at minimum charge
HEAVY_ATTACK_MAX_MULTIPLIER = 6.0    # Damage multiplier at full charge

# =============================================================================
# PERCEPTION SETTINGS (Vision and Hearing)
# =============================================================================
# Sound radius - how far sound travels (attacks, screams, etc.)
SOUND_RADIUS = 3.0  # cells - characters hear events within this range

# Vision settings
VISION_RANGE = 8.0  # cells - how far characters can see
VISION_CONE_ANGLE = 80  # degrees - field of view (120 = wide peripheral vision)

# =============================================================================
# DEBUG VISUALIZATION SETTINGS
# =============================================================================
# Set any of these to True to show debug overlays

# Perception debug - vision cones and sound radii
SHOW_PERCEPTION_DEBUG = False

# Character hitbox debug - collision and sprite boundaries
SHOW_CHARACTER_HITBOXES = False       # Master toggle for all character hitbox visualization
SHOW_COLLISION_RADIUS = False          # Circle showing CHARACTER_COLLISION_RADIUS (red)
SHOW_SPRITE_BOUNDS = False             # Rectangle showing full sprite dimensions (blue)
SHOW_INTERACTION_RADIUS = True       # Circle showing ADJACENCY_DISTANCE (green)
SHOW_ATTACK_RANGE = False             # Circle showing WEAPON_REACH (orange)
SHOW_ATTACK_CONE = False               # Player's directional attack hitbox (yellow) - the actual hit zone
SHOW_CHARACTER_POSITION = True        # Small dot at exact x,y position (white)

# Hitbox colors (RGBA tuples - use with rl.Color(*COLOR))
DEBUG_COLOR_COLLISION = (255, 80, 80, 180)      # Red - collision radius
DEBUG_COLOR_SPRITE = (80, 120, 255, 150)        # Blue - sprite bounds
DEBUG_COLOR_INTERACT = (80, 255, 80, 120)       # Green - interaction radius
DEBUG_COLOR_ATTACK = (255, 180, 60, 120)        # Orange - attack range (circle)
DEBUG_COLOR_ATTACK_CONE = (255, 255, 0, 100)    # Yellow - player's directional attack cone
DEBUG_COLOR_POSITION = (255, 255, 255, 255)     # White - center position dot

# Attack cone geometry (matches resolve_attack hit detection)
ATTACK_CONE_HALF_WIDTH = 0.7          # Perpendicular distance for hit detection (NPCs only)
ATTACK_CONE_ANGLE = 50                # Total cone angle in degrees at max range (360° aiming)
ATTACK_CONE_BASE_ANGLE = 150           # Total cone angle in degrees at player position (minimum width)

# Block/defense settings
BLOCK_MOVEMENT_SPEED = 0.4            # Movement speed while blocking (cells/second)
SHIELD_COLOR = (80, 160, 255, 180)    # Light blue, semi-transparent

# Arrow/projectile settings
ARROW_SPEED = 6.5                    # cells per second
ARROW_MAX_RANGE = 15.0                # cells before disappearing
ARROW_LENGTH = 0.8                    # visual length in cells
ARROW_THICKNESS = .8                   # pixels

# =============================================================================
# DEBUG GAMEPLAY SETTINGS
# =============================================================================
DEBUG_TRIPLE_PLAYER_HEALTH = False    # Player starts with 300 HP instead of 100

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
MAX_FATIGUE = 100
MAX_STAMINA = 100

# =============================================================================
# STAMINA SETTINGS (Skyrim-style sprinting)
# =============================================================================
# Stamina drain rate while sprinting (per tick)
# With 100 stamina and drain of 2.0/tick, can sprint for 50 ticks (~5 seconds at 1x)
STAMINA_DRAIN_PER_TICK = 2.0  # Stamina points per tick while sprinting

# Stamina regeneration rate when not sprinting (per tick)
STAMINA_REGEN_PER_TICK = 0.5  # Stamina points per tick

# Delay before stamina starts regenerating after stopping sprint (in ticks)
STAMINA_REGEN_DELAY_TICKS = 8  # ~0.8 seconds at 1x speed

# Minimum stamina required to START sprinting (not to maintain)
# Prevents rapidly tapping sprint to get micro-bursts
STAMINA_SPRINT_THRESHOLD = 10.0

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
CRIME_INTENSITY_MURDER = 17
CRIME_INTENSITY_ASSAULT = 15
CRIME_INTENSITY_THEFT = 10

# Theft timing (tick-based, scales with game speed)
THEFT_PATIENCE_TICKS = 60 * TICK_MULTIPLIER  # 60 seconds at 1x speed - how long to wait for crops
THEFT_COOLDOWN_TICKS = 30 * TICK_MULTIPLIER  # 30 seconds at 1x speed - cooldown after giving up

# Flee behavior
FLEE_DEFENDER_RANGE = 20  # Always run to defenders within this range (cells)
FLEE_TIMEOUT_TICKS = 30 * TICK_MULTIPLIER  # Max time to flee without a defender (30 seconds)
FLEE_SAFE_DISTANCE = 10.0  # Stop fleeing when this far from attacker (cells)
FLEE_DANGER_DISTANCE = 6.0  # Start fleeing again if attacker gets this close (cells)
FLEE_DISTANCE_DIVISOR = 2  # Flee distance = crime intensity / this value

# Reporting crimes
REPORT_ADJACENCY_DISTANCE = 1  # Must be within this distance to report crimes to soldiers

# =============================================================================
# SKILL DEFINITIONS
# =============================================================================
# Skills have: name, category ('combat', 'benign', or 'both')
# All characters have 0-100 points in each skill
SKILLS = {
    "strength": {"name": "Strength", "category": "combat"}, # warrior
    "agility": {"name": "Agility", "category": "combat"}, # warrior
    "mercantile": {"name": "Mercantile", "category": "benign"}, # vendor
    "demolition": {"name": "Demolition", "category": "combat"}, # vendor
    "smithing": {"name": "Smithing", "category": "benign"}, # vendor
    "logging": {"name": "Logging", "category": "benign"}, # vendor
    "mining": {"name": "Mining", "category": "benign"}, # vendor
    "farming": {"name": "Farming", "category": "benign"}, # vendor
    "herding": {"name": "Herding", "category": "benign"}, # vendor
    "carpentry": {"name": "Carpentry", "category": "both"}, # vendor
    "doctor": {"name": "Doctor", "category": "both"}, # vendor
    "art": {"name": "Art", "category": "benign"}, # vendor
    "herbalism": {"name": "Herbalism", "category": "benign"}, # vendor
    "brewing": {"name": "Brewing", "category": "benign"}, # vendor
    "tailor": {"name": "Tailor", "category": "benign"}, # vendor
    "hospitality": {"name": "Hospitality", "category": "benign"}, # vendor
    "grifting": {"name": "Grifting", "category": "benign"}, # thief: forging, lockpicking, breaking out, impersonation, trust building, lying, keeping stuff in jail
    "bard": {"name": "Bard", "category": "benign"}, # thief
}

# in a village, there's a Headman - turns into a reeve if owned by a kingdom
# you need a town hall, effectively a store house
# you need somewhere for guards to sleep - lets call it a guard house
# guards in a free village can be mercenaries, only need a few

# reeve pays taxes for the entire village to the steward - steward 
# town hall becomes a guarded store hosue
# guard house becomes a proper tower, which is effectively an extra barracks - patrols come from the kingdom, stay in the barracks, then get relieved and go back to the kingdom

# so you make a camp
# you have some mercanaries - you can have them patrol the camp perimeter
# you sleep, and then relieve them before they get too tired

# you can own a shed
# you make a house
# same thing - and they need somewhere to sleep in your house

# you have enough building skill, farming/shepherding skill in your party (no mercenaries), there are three houses, enough loyalty, enough net worth/experience 
# you can become a village
# your house becomes the storehouse - you become a reeve
# guards can live out of your house, but you probably want a guard house (which you can now build)
# you should make roads to existing roads so people visit
# a sign wouldn't hurt
# a bulletin board can be made - you can write to it from preset things

# a reeve/headman can't naturally become a steward of a kingdom - thats reserved for in-kingdom traders with high literacy
# if a king dies and there's no heir, a knight becomes king
# a person can be come a noble if they are a steward, a knight, or have earned favor in some way - need to figure out how succession works
# nobles have permanent, free housing in the castle (inner walls)
# kingdoms have outer walls, gate guards, internal patrol, external patrol, royal guard
# knights commanded troops of guards during war time? 
# knights had squires
# there's a weapon trainer who is a knight? guards could train with him? train with wooden swords?
# guards could get knighted for valor? adventurers (mercenaries) who help citizens can get knighted? bards, artists can get knighted?
# stewards who get kicked out are back to zero - travelling merchants - hold a grudge
# kingdoms are expected to grow? 
# land deeds and price for them, and taxation price, based on village occupancy - and kingdom space available
# villages can grow infinitely and get walls, walls need to be created when the max village size is reached - at which point only farms/stables can be outside of them
# knights could live in the castle, but dont have to - knights can do whatever they want in the entire kingdom - build anywhere, take guards, etc
# but they have responsibilities during war time
# knights who don't do their job get banished
# when there's a major disturbance or there's a war effort, knights heed the call

# criminal record
# did villages have jails?
# castle involved barrels

# noble is a status - anybody could be one, but namely knights
# stewards were automatically nobles - just being the best trader got you there
# great artists, bards, etc could be made nobles
# nobles + knights fight for succession

# building skill increases via digging
# should carpentry be a separate skill?

# you can buy plots of land in a village, price and tax depending on the size
# taxes should be payable in net value
# roads will be built to your house

# knights show up when summoned, create when needed
# consider conseqwuences of poaching/shepherding/lumberjacking/mining on kingdoms' land
# mining companies/vendor companies - how that works



# =============================================================================
# INVENTORY SETTINGS
# =============================================================================
# Central item registry - all items and their properties
# All item display info is here - inventory_menu.py reads from this
ITEMS = {
    "wheat": {
        "name": "Wheat",
        "price": 5,
        "stack_size": 15,
        "sprite": "Wheat.png",  # In sprites/items/
        "color": (245, 222, 130, 200),  # RGBA fallback color
        "icon": "W",  # Fallback text icon
    },
    "gold": {
        "name": "Gold",
        "price": 1,
        "stack_size": None,  # Infinite stacking
        "sprite": "Gold.png",
        "color": (218, 165, 32, 200),
        "icon": "$",
    },
    "bread": {
        "name": "Bread",
        "price": 7,
        "stack_size": 15,
        "hunger_value": 33,  # How much hunger restored per unit
        "sprite": "Bread.png",
        "color": (160, 82, 45, 200),
        "icon": "B",
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
# ONGOING ACTIONS (Player timed actions like harvesting, planting, chopping)
# =============================================================================
# Duration in seconds (real-time, not affected by game speed)
ONGOING_ACTION_HARVEST_DURATION = 5.0  # 5 seconds to harvest
ONGOING_ACTION_PLANT_DURATION = 5.0    # 5 seconds to plant
ONGOING_ACTION_CHOP_DURATION = 8.0     # 8 seconds to chop tree (future)

# Progress bar color (blue, RGBA)
UI_COLOR_PROGRESS_BAR = (80, 140, 220, 220)  # Blue progress bar

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
    "Knight": {"tier": 2},

    
    # TIER 3 - THINGS WE NEED OR THE GAME BREAKS
    "Soldier": { # Knightable
        "tier": 3,
        "color": "#FF69B4",
        "requires": {"morality_min": 5, "confidence_min": 7, "cunning_max": 5},
    },
    "Trader": { # Knightable based on brewing skills - may turn stuff into other stuff to sell for more based on skills - (i.e. medicine, alcohol, explosives) - but NOT FOOD
        "tier": 3,
        "color": "#FFD700",
        "requires": {"mercantile": 30}, # becoming a trader may unlock by having, say 30 mercantile. so a farmer that's good at making explosives may start selling stuff with high enough mercantile
    }, 
    "Farmer": {
        "tier": 3,
        "color": "#39db34",
        "requires": {"farming": 40},
    },
    "Innkeeper": {"tier": 3},
    "Weapons Trainer": {"tier": 3}, # Knightable

    # TIER 4 — COMFORTABLE SKILLED WORK
    "Doctor": {"tier": 3}, # Knightable
    "Carpenter": {"tier": 3}, # Knightable (commissions)
    "Tailor": {"tier": 3}, # Knightable (commissions)
    "Artist": {"tier": 3}, # Knightable (commissions)
    "Blacksmith": {"tier": 3}, # Knightable (commissions)
    "Servant": {"tier": 3},
    
    # TIER 5 — RESPECTABLE BUT HARDER LABOR
    "Hunter": {"tier": 5}, # son of (bow)
    "Fisherman": {"tier": 5}, # son of (fishing pole)
    "Logger": {"tier": 5}, # son of (axe, strength)
    "Herder": {"tier": 5}, # son of (whip, dagger)
    "Miner": {"tier": 5},
    "Mercenary": {"tier": 5}, # Knightable
    "Bard": {"tier": 5}, # Knightable
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


# Soldier — The classic route. Valor in battle, knighted on the field.
# Mercenary — Same deal, though looked down on. A mercenary captain who wins a crucial battle could be rewarded.
# Weapons Trainer — Long service training a lord's household, possibly already from minor noble stock.

# Plausible with royal favor:

# Trader — Wealthy merchant who finances the crown's wars, loans money, provides ships. Later medieval period especially.
# Doctor — Royal physician who saves the king's life or serves for decades.
# Artist — Court painter or sculptor in direct service to royalty.
# Bard — Troubadours and poets sometimes moved in noble circles. A famous one with a patron could be elevated.
# Carpenter - makes nice furniture

# every kid after should try to get knighted to - and keep the family's land entact - eventually, it'll get repocessesed if the kid isn't at least a squire

# should be able to make easily: campfire, post (requires rope), wooden sword, fishing rod, torch
# swinging a wooden sword forever would get you to be a better swordsman - up to a point. then you need real experience or a trainer

# =============================================================================
# UI COLOR SCHEME (shared across all menus)
# =============================================================================
# These are RGBA tuples - convert to rl.Color in each file that uses them
# Example: rl.Color(*UI_COLOR_BOX_BG)

# Panel/box backgrounds
UI_COLOR_BOX_BG = (15, 12, 10, 230)           # Dark brown, high opacity
UI_COLOR_BOX_BG_MEDIUM = (15, 12, 10, 200)    # Dark brown, medium opacity  
UI_COLOR_BOX_BG_LIGHT = (15, 12, 10, 180)     # Dark brown, lower opacity

# Borders
UI_COLOR_BORDER = (90, 75, 60, 255)           # Light brown border
UI_COLOR_BORDER_INNER = (60, 50, 40, 255)     # Darker inner border

# Text
UI_COLOR_TEXT = (240, 230, 210, 255)          # Warm white text
UI_COLOR_TEXT_DIM = (180, 170, 150, 255)      # Dimmed text
UI_COLOR_TEXT_FAINT = (120, 115, 100, 128)    # Very faint text

# Interactive elements
UI_COLOR_OPTION_SELECTED = (255, 255, 255, 30)   # Selection highlight
UI_COLOR_OPTION_HOVER = (255, 255, 255, 15)      # Hover highlight

# Slot backgrounds (for inventory)
UI_COLOR_SLOT_BG = (255, 255, 255, 20)        # Empty slot
UI_COLOR_SLOT_ACTIVE = (255, 255, 255, 50)    # Slot with item
UI_COLOR_SLOT_SELECTED = (140, 180, 120, 100) # Selected slot (green tint)
UI_COLOR_SLOT_BORDER = (255, 255, 255, 60)    # Slot border
UI_COLOR_SLOT_BORDER_SELECTED = (140, 180, 120, 255)  # Selected slot border (green)

# Accent colors
UI_COLOR_CURSOR = (220, 180, 100, 255)        # Gold cursor/highlight
UI_COLOR_HEADER_GREEN = (140, 180, 120, 255)  # Green header text


# Aiming chevron visual settings
AIM_CHEVRON_FEET_OFFSET = 10          # Pixels to offset chevron downward (toward feet)
AIM_CHEVRON_THICKNESS = 4
AIM_CHEVRON_COLOR = (255, 255, 255, 120)