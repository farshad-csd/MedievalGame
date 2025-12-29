# game_state.py - Pure data model for game state (no logic, no UI)
"""
This module contains the GameState class which holds ALL mutable game state.
It is purely a data container - no game logic, no rendering.
"""

import random
from constants import (
    SIZE, MAX_HUNGER, FARM_CELL_HARVEST_INTERVAL,
    INVENTORY_SLOTS, FOOD_STACK_SIZE, BARREL_SLOTS, BARREL_FOOD_STACK_SIZE,
    SKILLS
)
from scenario_world import AREAS, BARRELS, BEDS
from scenario_characters import CHARACTER_TEMPLATES


class GameState:
    """
    Pure data container for all game state.
    
    This class:
    - Holds all mutable game data
    - Provides methods to initialize/reset the world
    - Does NOT contain game logic (that's in game_logic.py)
    - Does NOT contain rendering code (that's in gui.py)
    """
    
    def __init__(self):
        # Time tracking
        self.ticks = 0
        self.game_speed = 1
        self.paused = False
        
        # World data
        self.area_map = [[None for _ in range(SIZE)] for _ in range(SIZE)]
        self.farm_cells = {}  # (x, y) -> {'state': str, 'timer': int}
        self.barrels = {}  # (x, y) -> {'name': str, 'home': str, 'owner': str, 'inventory': list}
        self.beds = {}  # (x, y) -> {'name': str, 'home': str, 'owner': str}
        
        # Character data
        self.characters = []  # List of character dicts
        self.player = None    # Reference to player character dict
        
        # Action log
        self.action_log = []
        
        # Initialize world
        self._init_areas()
        self._init_farm_cells()
        self._init_barrels()
        self._init_beds()
        self._init_characters()
    
    def _init_areas(self):
        """Initialize the area map from AREAS configuration"""
        for area in AREAS:
            name = area["name"]
            start_y, start_x, end_y, end_x = area["bounds"]
            for y in range(start_y, end_y):
                for x in range(start_x, end_x):
                    if 0 <= y < SIZE and 0 <= x < SIZE:
                        self.area_map[y][x] = name
    
    def _init_farm_cells(self):
        """Initialize harvestable farm cells"""
        for area in AREAS:
            if area.get("has_farm_cells"):
                bounds = area.get("farm_cell_bounds", area["bounds"])
                y_start, x_start, y_end, x_end = bounds
                allegiance = area.get("allegiance")  # Farm's allegiance (e.g., "VILLAGE" or None)
                for y in range(y_start, y_end):
                    for x in range(x_start, x_end):
                        if 0 <= y < SIZE and 0 <= x < SIZE:
                            self.farm_cells[(x, y)] = {
                                'state': 'ready',
                                'timer': 0,
                                'allegiance': allegiance
                            }
    
    def _init_barrels(self):
        """Initialize barrels from BARRELS configuration.
        Ownership is assigned at runtime based on jobs, not from config.
        """
        for barrel_def in BARRELS:
            x, y = barrel_def["position"]
            self.barrels[(x, y)] = {
                'name': barrel_def["name"],
                'home': barrel_def["home"],
                'owner': None,  # Assigned at runtime based on jobs
                'inventory': [None] * BARREL_SLOTS
            }
    
    def _init_beds(self):
        """Initialize beds from BEDS configuration.
        Ownership is assigned at runtime based on jobs, not from config.
        """
        for bed_def in BEDS:
            x, y = bed_def["position"]
            self.beds[(x, y)] = {
                'name': bed_def["name"],
                'home': bed_def["home"],
                'owner': None  # Assigned at runtime based on jobs
            }
    
    def _init_characters(self):
        """Initialize characters from templates.
        Homes, beds, and barrels are assigned based on starting_job, not hardcoded in config.
        """
        occupied = set()
        
        # Get default spawn area (residential area)
        default_spawn_area = self.get_area_by_role('residential')
        
        for name, template in CHARACTER_TEMPLATES.items():
            # Determine home area based on job
            starting_job = template.get('starting_job')
            home_area = self._get_home_for_job(starting_job, template.get('starting_home'))
            
            # Find spawn location in home area (or default if no home)
            spawn_area = home_area or default_spawn_area
            x, y = self._find_spawn_location(spawn_area, occupied)
            occupied.add((x, y))
            
            # Create character dict with all state
            char = self._create_character(name, template, x, y, home_area)
            self.characters.append(char)
            
            # Assign bed and barrel based on job
            if starting_job:
                self._assign_job_resources(char, starting_job, home_area)
            
            if template.get('is_player', False):
                self.player = char
    
    def _get_home_for_job(self, job, fallback_home):
        """Get the appropriate home area for a job."""
        if job == 'Steward':
            return self.get_area_by_role('military_housing')
        elif job == 'Soldier':
            return self.get_area_by_role('military_housing')
        elif job == 'Farmer':
            return self.get_area_by_role('farm')
        else:
            return fallback_home  # Unemployed use starting_home from template
    
    def _assign_job_resources(self, char, job, home_area):
        """Assign bed and barrel ownership based on job."""
        char_name = char['name']
        
        # Assign an unowned bed in the home area
        bed = self.get_unowned_bed_by_home(home_area)
        if bed:
            self.assign_bed_owner(bed, char_name)
        
        # Steward owns the barracks barrel
        if job == 'Steward':
            barrel = self.get_barrel_by_home(home_area)
            if barrel:
                barrel['owner'] = char_name
        # Farmer owns the farm barrel
        elif job == 'Farmer':
            barrel = self.get_barrel_by_home(home_area)
            if barrel:
                barrel['owner'] = char_name
    
    def _find_spawn_location(self, area_name, occupied):
        """Find a valid spawn location in the given area"""
        cells = []
        for y in range(SIZE):
            for x in range(SIZE):
                if self.area_map[y][x] == area_name:
                    cells.append((x, y))
        
        # Try to find unoccupied cell in area
        if cells:
            random.shuffle(cells)
            for x, y in cells:
                if (x, y) not in occupied:
                    return x, y
        
        # Fallback: find any unoccupied cell
        for _ in range(1000):
            x = random.randint(0, SIZE - 1)
            y = random.randint(0, SIZE - 1)
            if (x, y) not in occupied:
                return x, y
        
        # Last resort: just return something
        return random.randint(0, SIZE - 1), random.randint(0, SIZE - 1)
    
    def _create_character(self, name, template, x, y, home_area):
        """Create a character dict from template"""
        # Build initial inventory from starting money/food
        inventory = self._build_initial_inventory(
            template['starting_money'], 
            template['starting_food']
        )
        
        # Initialize skills - all start at 0, then apply starting_skills from template
        skills = {skill_id: 0 for skill_id in SKILLS}
        for skill_id, value in template.get('starting_skills', {}).items():
            skills[skill_id] = value
        
        return {
            # Identity
            'name': name,
            
            # Position
            'x': x,
            'y': y,
            
            # Core stats (mutable)
            'age': template['starting_age'],
            'health': 100,
            'hunger': MAX_HUNGER,
            'inventory': inventory,  # New inventory system
            'morality': template['morality'],  # Mutable copy of morality trait
            'skills': skills,  # Skill levels (0-100)
            
            # Current state (can change during game)
            'job': template['starting_job'],
            'allegiance': template['starting_allegiance'],
            'home': home_area,  # Determined by job, not hardcoded in template
            
            # Combat/social state
            'robbery_target': None,
            'theft_target': None,  # Farm cell being targeted for theft
            'flee_from': None,  # Character to flee from (set when witnessing crime)
            'is_murderer': False,
            'is_thief': False,  # Has stolen from farm
            'is_aggressor': False,
            
            # Crime knowledge - unified system
            # known_crimes: {criminal_id: [{'intensity': int, 'allegiance': str/None}, ...]}
            'known_crimes': {},
            # unreported_crimes: {(criminal_id, intensity, crime_allegiance), ...}
            'unreported_crimes': set(),
            
            # Starvation state
            'is_starving': False,
            'is_frozen': False,  # True when starving + health <= 20
            'starvation_health_lost': 0,  # Tracks health lost for morality checks
            'ticks_starving': 0,  # How long character has been starving (for robbery escalation)
            
            # Sleep state
            'is_sleeping': False,
            'camp_position': None,  # (x, y) of camp if character has made one
            
            # Job-specific state
            'tax_late_ticks': 0,
            'tax_collection_target': None,
            'tax_paid_this_cycle': False,
            'paid_this_cycle': False,
            'soldier_stopped': False,
            'asked_steward_for_food': False,
            'food_seek_ticks': 0,
            
            # Logging flags (to avoid spam)
            '_idle_logged': False,
            '_work_logged': False,
            
            # Visual state
            'facing': 'down',  # 'up', 'down', 'left', 'right'
        }
    
    def _build_initial_inventory(self, money, food):
        """Build inventory from starting money and food amounts."""
        inventory = [None] * INVENTORY_SLOTS
        slot_idx = 0
        
        # Add money slot if any
        if money > 0 and slot_idx < INVENTORY_SLOTS:
            inventory[slot_idx] = {'type': 'money', 'amount': money}
            slot_idx += 1
        
        # Add food slots (stacks of FOOD_STACK_SIZE)
        remaining_food = food
        while remaining_food > 0 and slot_idx < INVENTORY_SLOTS:
            stack_amount = min(remaining_food, FOOD_STACK_SIZE)
            inventory[slot_idx] = {'type': 'food', 'amount': stack_amount}
            remaining_food -= stack_amount
            slot_idx += 1
        
        return inventory
    
    # =========================================================================
    # QUERY METHODS (pure data access, no side effects)
    # =========================================================================
    
    def get_character(self, name):
        """Get a character by name"""
        for char in self.characters:
            if char['name'] == name:
                return char
        return None
    
    def get_characters_by_job(self, job):
        """Get all characters with a specific job"""
        return [c for c in self.characters if c.get('job') == job]
    
    def get_area_at(self, x, y):
        """Get the area name at a position"""
        if 0 <= x < SIZE and 0 <= y < SIZE:
            return self.area_map[y][x]
        return None
    
    def get_area_by_role(self, role):
        """Get the first area with the specified role. Returns area name or None."""
        for area_def in AREAS:
            if area_def.get("role") == role:
                return area_def["name"]
        return None
    
    def get_areas_by_role(self, role):
        """Get all areas with the specified role. Returns list of area names."""
        return [area_def["name"] for area_def in AREAS if area_def.get("role") == role]
    
    def get_area_role(self, area_name):
        """Get the role of an area by its name. Returns role or None."""
        for area_def in AREAS:
            if area_def["name"] == area_name:
                return area_def.get("role")
        return None
    
    def is_position_valid(self, x, y):
        """Check if position is within bounds"""
        return 0 <= x < SIZE and 0 <= y < SIZE
    
    def is_occupied(self, x, y):
        """Check if a cell is occupied by any character"""
        for char in self.characters:
            if char['x'] == x and char['y'] == y:
                return True
        return False
    
    def get_character_at(self, x, y):
        """Get character at position, if any"""
        for char in self.characters:
            if char['x'] == x and char['y'] == y:
                return char
        return None
    
    def is_in_village(self, x, y):
        """Check if position is in the village area (including sub-areas)"""
        area = self.area_map[y][x] if self.is_position_valid(x, y) else None
        # Check against AREAS config for is_village_part
        for area_def in AREAS:
            if area_def["name"] == area and area_def.get("is_village_part"):
                return True
        return False
    
    def get_area_cells(self, area_name):
        """Get all cells belonging to an area"""
        cells = []
        for y in range(SIZE):
            for x in range(SIZE):
                if self.area_map[y][x] == area_name:
                    cells.append((x, y))
        return cells
    
    def get_village_perimeter(self):
        """Get cells forming the perimeter around the village in clockwise order"""
        # Find village bounds
        min_x, max_x = SIZE, 0
        min_y, max_y = SIZE, 0
        
        for y in range(SIZE):
            for x in range(SIZE):
                if self.is_in_village(x, y):
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)
        
        # Build perimeter in clockwise order (one cell outside village bounds)
        perimeter = []
        
        # Top edge: left to right
        for x in range(min_x - 1, max_x + 2):
            if self.is_position_valid(x, min_y - 1):
                perimeter.append((x, min_y - 1))
        
        # Right edge: top to bottom (skip corner already added)
        for y in range(min_y, max_y + 2):
            if self.is_position_valid(max_x + 1, y):
                perimeter.append((max_x + 1, y))
        
        # Bottom edge: right to left (skip corner already added)
        for x in range(max_x, min_x - 2, -1):
            if self.is_position_valid(x, max_y + 1):
                perimeter.append((x, max_y + 1))
        
        # Left edge: bottom to top (skip corners already added)
        for y in range(max_y, min_y - 1, -1):
            if self.is_position_valid(min_x - 1, y):
                perimeter.append((min_x - 1, y))
        
        return perimeter
    
    def get_farm_cell_state(self, x, y):
        """Get the state of a farm cell"""
        return self.farm_cells.get((x, y))
    
    def get_area_allegiance(self, x, y):
        """Get the allegiance of the area at a position"""
        area_name = self.get_area_at(x, y)
        if area_name:
            for area_def in AREAS:
                if area_def["name"] == area_name:
                    return area_def.get("allegiance")
        return None
    
    def get_farm_cell_allegiance(self, x, y):
        """Get the allegiance of a farm cell"""
        cell = self.farm_cells.get((x, y))
        if cell:
            return cell.get('allegiance')
        return None
    
    def get_template(self, name):
        """Get the static template for a character by name"""
        return CHARACTER_TEMPLATES.get(name)
    
    # =========================================================================
    # MODIFICATION METHODS (simple state changes)
    # =========================================================================
    
    def remove_character(self, char):
        """Remove a character from the game"""
        if char in self.characters:
            self.characters.remove(char)
        if char == self.player:
            self.player = None
    
    def log_action(self, message):
        """Add a message to the action log"""
        from constants import TICKS_PER_DAY, TICKS_PER_YEAR
        year = (self.ticks // TICKS_PER_YEAR) + 1
        day = ((self.ticks % TICKS_PER_YEAR) // TICKS_PER_DAY) + 1
        log_entry = f"[Y{year}D{day}] {message}"
        self.action_log.append(log_entry)
        
        # Keep only last 100 entries
        if len(self.action_log) > 100:
            self.action_log = self.action_log[-100:]
    
    def reset(self):
        """Reset game to initial state"""
        self.ticks = 0
        self.game_speed = 1
        self.paused = False
        self.characters = []
        self.player = None
        self.farm_cells = {}
        self.barrels = {}
        self.action_log = []
        self.area_map = [[None for _ in range(SIZE)] for _ in range(SIZE)]
        
        self._init_areas()
        self._init_farm_cells()
        self._init_barrels()
        self._init_characters()
    
    # =========================================================================
    # INVENTORY METHODS
    # =========================================================================
    
    def get_food(self, char):
        """Get total food from character's inventory."""
        total = 0
        for slot in char['inventory']:
            if slot and slot['type'] == 'food':
                total += slot['amount']
        return total
    
    def get_money(self, char):
        """Get total money from character's inventory."""
        for slot in char['inventory']:
            if slot and slot['type'] == 'money':
                return slot['amount']
        return 0
    
    def has_money_slot(self, char):
        """Check if character has a money slot in inventory."""
        for slot in char['inventory']:
            if slot and slot['type'] == 'money':
                return True
        return False
    
    def can_add_food(self, char, amount):
        """Check if character can add this much food to inventory."""
        space = 0
        for slot in char['inventory']:
            if slot is None:
                space += FOOD_STACK_SIZE
            elif slot['type'] == 'food' and slot['amount'] < FOOD_STACK_SIZE:
                space += FOOD_STACK_SIZE - slot['amount']
        return space >= amount
    
    def can_add_money(self, char):
        """Check if character can add money (has money slot or empty slot)."""
        for slot in char['inventory']:
            if slot is None:
                return True
            if slot['type'] == 'money':
                return True
        return False
    
    def add_food(self, char, amount):
        """Add food to character's inventory. Returns amount actually added."""
        remaining = amount
        
        # First, fill existing food stacks
        for slot in char['inventory']:
            if slot and slot['type'] == 'food' and slot['amount'] < FOOD_STACK_SIZE:
                can_add = FOOD_STACK_SIZE - slot['amount']
                to_add = min(remaining, can_add)
                slot['amount'] += to_add
                remaining -= to_add
                if remaining <= 0:
                    return amount
        
        # Then, use empty slots
        for i, slot in enumerate(char['inventory']):
            if slot is None:
                to_add = min(remaining, FOOD_STACK_SIZE)
                char['inventory'][i] = {'type': 'food', 'amount': to_add}
                remaining -= to_add
                if remaining <= 0:
                    return amount
        
        return amount - remaining  # Return amount actually added
    
    def remove_food(self, char, amount):
        """Remove food from character's inventory. Returns amount actually removed."""
        remaining = amount
        
        # Remove from food stacks (prefer smaller stacks first to consolidate)
        food_slots = [(i, slot) for i, slot in enumerate(char['inventory']) 
                      if slot and slot['type'] == 'food']
        food_slots.sort(key=lambda x: x[1]['amount'])
        
        for i, slot in food_slots:
            to_remove = min(remaining, slot['amount'])
            slot['amount'] -= to_remove
            remaining -= to_remove
            
            # Remove empty slot
            if slot['amount'] <= 0:
                char['inventory'][i] = None
            
            if remaining <= 0:
                return amount
        
        return amount - remaining  # Return amount actually removed
    
    def add_money(self, char, amount):
        """Add money to character's inventory. Returns amount actually added."""
        # Find existing money slot
        for slot in char['inventory']:
            if slot and slot['type'] == 'money':
                slot['amount'] += amount
                return amount
        
        # Find empty slot
        for i, slot in enumerate(char['inventory']):
            if slot is None:
                char['inventory'][i] = {'type': 'money', 'amount': amount}
                return amount
        
        return 0  # No space
    
    def remove_money(self, char, amount):
        """Remove money from character's inventory. Returns amount actually removed."""
        for i, slot in enumerate(char['inventory']):
            if slot and slot['type'] == 'money':
                to_remove = min(amount, slot['amount'])
                slot['amount'] -= to_remove
                
                # Remove empty money slot
                if slot['amount'] <= 0:
                    char['inventory'][i] = None
                
                return to_remove
        
        return 0  # No money to remove
    
    def transfer_all_items(self, from_char, to_char):
        """Transfer all items from one character to another (for looting)."""
        # Transfer money
        money = self.get_money(from_char)
        if money > 0:
            self.remove_money(from_char, money)
            self.add_money(to_char, money)
        
        # Transfer food
        food = self.get_food(from_char)
        if food > 0:
            self.remove_food(from_char, food)
            self.add_food(to_char, food)
    
    def get_inventory_space(self, char):
        """Get remaining food capacity in inventory."""
        space = 0
        for slot in char['inventory']:
            if slot is None:
                space += FOOD_STACK_SIZE
            elif slot['type'] == 'food' and slot['amount'] < FOOD_STACK_SIZE:
                space += FOOD_STACK_SIZE - slot['amount']
        return space
    
    def is_inventory_full(self, char):
        """Check if inventory has no empty slots and all food stacks are full."""
        for slot in char['inventory']:
            if slot is None:
                return False
            if slot['type'] == 'food' and slot['amount'] < FOOD_STACK_SIZE:
                return False
        return True
    
    # =========================================================================
    # BARREL METHODS
    # =========================================================================
    
    def get_barrel_at(self, x, y):
        """Get barrel at position, if any"""
        return self.barrels.get((x, y))
    
    def get_barrel_by_home(self, home):
        """Get barrel in the given home area"""
        for pos, barrel in self.barrels.items():
            if barrel['home'] == home:
                return barrel
        return None
    
    def get_barrel_by_owner(self, owner_name):
        """Get barrel owned by the given character name"""
        for pos, barrel in self.barrels.items():
            if barrel['owner'] == owner_name:
                return barrel
        return None
    
    def get_barrel_position(self, barrel):
        """Get the (x, y) position of a barrel"""
        for pos, b in self.barrels.items():
            if b is barrel:
                return pos
        return None
    
    def is_adjacent_to_barrel(self, char, barrel):
        """Check if character is adjacent to the barrel"""
        pos = self.get_barrel_position(barrel)
        if not pos:
            return False
        bx, by = pos
        dx = abs(char['x'] - bx)
        dy = abs(char['y'] - by)
        return (dx == 1 and dy == 0) or (dx == 0 and dy == 1) or (dx == 0 and dy == 0)
    
    def can_use_barrel(self, char, barrel):
        """Check if character can use (take from) this barrel.
        Owner can always use it. Others can use if their home matches barrel's home.
        """
        if barrel['owner'] == char['name']:
            return True
        return char.get('home') == barrel['home']
    
    def get_barrel_food(self, barrel):
        """Get total food from barrel's inventory."""
        total = 0
        for slot in barrel['inventory']:
            if slot and slot['type'] == 'food':
                total += slot['amount']
        return total
    
    def get_barrel_money(self, barrel):
        """Get total money from barrel's inventory."""
        for slot in barrel['inventory']:
            if slot and slot['type'] == 'money':
                return slot['amount']
        return 0
    
    def can_barrel_add_food(self, barrel, amount):
        """Check if barrel can add this much food to inventory."""
        space = 0
        for slot in barrel['inventory']:
            if slot is None:
                space += BARREL_FOOD_STACK_SIZE
            elif slot['type'] == 'food' and slot['amount'] < BARREL_FOOD_STACK_SIZE:
                space += BARREL_FOOD_STACK_SIZE - slot['amount']
        return space >= amount
    
    def add_barrel_food(self, barrel, amount):
        """Add food to barrel's inventory. Returns amount actually added."""
        remaining = amount
        
        # First, fill existing food stacks
        for slot in barrel['inventory']:
            if slot and slot['type'] == 'food' and slot['amount'] < BARREL_FOOD_STACK_SIZE:
                can_add = BARREL_FOOD_STACK_SIZE - slot['amount']
                to_add = min(remaining, can_add)
                slot['amount'] += to_add
                remaining -= to_add
                if remaining <= 0:
                    return amount
        
        # Then, use empty slots
        for i, slot in enumerate(barrel['inventory']):
            if slot is None:
                to_add = min(remaining, BARREL_FOOD_STACK_SIZE)
                barrel['inventory'][i] = {'type': 'food', 'amount': to_add}
                remaining -= to_add
                if remaining <= 0:
                    return amount
        
        return amount - remaining  # Return amount actually added
    
    def remove_barrel_food(self, barrel, amount):
        """Remove food from barrel's inventory. Returns amount actually removed."""
        remaining = amount
        
        # Remove from food stacks (prefer smaller stacks first to consolidate)
        food_slots = [(i, slot) for i, slot in enumerate(barrel['inventory']) 
                      if slot and slot['type'] == 'food']
        food_slots.sort(key=lambda x: x[1]['amount'])
        
        for i, slot in food_slots:
            to_remove = min(remaining, slot['amount'])
            slot['amount'] -= to_remove
            remaining -= to_remove
            
            # Remove empty slot
            if slot['amount'] <= 0:
                barrel['inventory'][i] = None
            
            if remaining <= 0:
                return amount
        
        return amount - remaining  # Return amount actually removed
    
    def add_barrel_money(self, barrel, amount):
        """Add money to barrel's inventory. Returns amount actually added."""
        # Find existing money slot
        for slot in barrel['inventory']:
            if slot and slot['type'] == 'money':
                slot['amount'] += amount
                return amount
        
        # Find empty slot
        for i, slot in enumerate(barrel['inventory']):
            if slot is None:
                barrel['inventory'][i] = {'type': 'money', 'amount': amount}
                return amount
        
        return 0  # No space
    
    def remove_barrel_money(self, barrel, amount):
        """Remove money from barrel's inventory. Returns amount actually removed."""
        for i, slot in enumerate(barrel['inventory']):
            if slot and slot['type'] == 'money':
                to_remove = min(amount, slot['amount'])
                slot['amount'] -= to_remove
                
                # Remove empty money slot
                if slot['amount'] <= 0:
                    barrel['inventory'][i] = None
                
                return to_remove
        
        return 0  # No money to remove
    
    # =========================================================================
    # BED METHODS
    # =========================================================================
    
    def get_bed_at(self, x, y):
        """Get bed at position, if any"""
        return self.beds.get((x, y))
    
    def get_bed_by_owner(self, owner_name):
        """Get bed owned by the given character name"""
        for pos, bed in self.beds.items():
            if bed['owner'] == owner_name:
                return bed
        return None
    
    def get_bed_position(self, bed):
        """Get the (x, y) position of a bed"""
        for pos, b in self.beds.items():
            if b is bed:
                return pos
        return None
    
    def get_unowned_bed_by_home(self, home):
        """Get an unowned bed in the given home area"""
        for pos, bed in self.beds.items():
            if bed['home'] == home and bed['owner'] is None:
                return bed
        return None
    
    def assign_bed_owner(self, bed, owner_name):
        """Assign an owner to a bed"""
        bed['owner'] = owner_name
    
    def unassign_bed_owner(self, owner_name):
        """Remove bed ownership from a character. Returns the bed if found."""
        for pos, bed in self.beds.items():
            if bed['owner'] == owner_name:
                bed['owner'] = None
                return bed
        return None