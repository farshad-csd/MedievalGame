# game_state.py - Pure data model for game state (no game rules, no UI)
"""
This module contains the GameState class which holds ALL mutable game state.
It is a data container with pure query methods - no game rules, no rendering.

Query methods here are pure lookups (get_character, get_area_at, is_sleep_time).
Game rules and behavior logic live in game_logic.py.
"""

import random
import math
from constants import (
    MAX_HUNGER, FARM_CELL_HARVEST_INTERVAL, ITEMS,
    INVENTORY_SLOTS, BARREL_SLOTS,
    SKILLS, CELL_SIZE,
    CHARACTER_WIDTH, CHARACTER_HEIGHT, ADJACENCY_DISTANCE, CHARACTER_COLLISION_RADIUS
)
from scenario_world import AREAS, BARRELS, BEDS, STOVES, SIZE, TREES, HOUSES
from scenario_characters import CHARACTER_TEMPLATES
from character import Character, create_character
from static_interactables import InteractableManager


class GameState:
    """
    Data container for all game state with pure query methods.
    
    This class:
    - Holds all mutable game data (characters, areas, ticks, etc.)
    - Provides pure query methods (lookups, distance, etc.)
    - Provides simple modification methods (remove_character, log_action)
    - Does NOT contain game rules/behavior (that's in game_logic.py)
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
        
        # Interactable objects (barrels, beds, stoves, campfires, trees, houses)
        self.interactables = InteractableManager()
        
        # Character data
        self.characters = []  # List of Character instances
        self.player = None    # Reference to player Character
        
        # Death animations (purely visual - characters are removed from game logic immediately)
        self.death_animations = []  # List of {'x': float, 'y': float, 'name': str, 'start_time': float, 'facing': str, 'job': str, 'morality': int}
        
        # Action log
        self.action_log = []
        self.log_total_count = 0  # Total entries ever added (for UI sync)
        
        # Initialize world
        self._init_areas()
        self._init_farm_cells()
        self._init_interactables()
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
        """Initialize harvestable farm cells.
        
        Supports two formats:
        - farm_cells: [[x, y], ...] - explicit list of cell coordinates (new format)
        - farm_cell_bounds: [y_start, x_start, y_end, x_end] - rectangular bounds (legacy)
        """
        for area in AREAS:
            if area.get("has_farm_cells"):
                allegiance = area.get("allegiance")  # Farm's allegiance (e.g., "Dunmere" or None)
                
                if "farm_cells" in area:
                    for cell in area["farm_cells"]:
                        x, y = cell[0], cell[1]
                        if 0 <= y < SIZE and 0 <= x < SIZE:
                            self.farm_cells[(x, y)] = {
                                'state': 'ready',
                                'timer': 0,
                                'allegiance': allegiance
                            }
    
    def _init_interactables(self):
        """Initialize all interactable objects (barrels, beds, stoves, trees, houses)."""
        self.interactables.init_barrels(BARRELS)
        self.interactables.init_beds(BEDS)
        self.interactables.init_stoves(STOVES)
        self.interactables.init_trees(TREES)
        self.interactables.init_houses(HOUSES)
    
    def _init_characters(self):
        """Initialize characters from templates.
        Homes, beds, and barrels are assigned based on starting_job, not hardcoded in config.
        """
        occupied = set()
        
        for name, template in CHARACTER_TEMPLATES.items():
            # Determine home area based on job
            starting_job = template.get('starting_job')

            # Find spawn location in home area (or default if no home)
            home_area = template.get('starting_home')
            x, y = self._find_spawn_location(home_area, occupied)
            occupied.add((x, y))
            
            # Create Character object (not dict)
            char = create_character(name, x, y, home_area)
            self.characters.append(char)
            
            # Assign bed and barrel based on job
            if starting_job:
                self._assign_job_resources(char, starting_job, home_area)
            
            if char.is_player:
                self.player = char
    
    
    def _assign_job_resources(self, char, job, home_area):
        """Assign bed and barrel ownership based on job."""
        char_name = char.name
        
        # Assign an unowned bed in the home area
        bed = self.interactables.get_unowned_bed_by_home(home_area)
        if bed:
            self.interactables.assign_bed_owner(bed, char_name)
        
        # Steward owns the barracks barrel
        if job == 'Steward':
            barrel = self.interactables.get_barrel_by_home(home_area)
            if barrel:
                barrel.owner = char_name
        # Farmer owns the farm barrel
        elif job == 'Farmer':
            barrel = self.interactables.get_barrel_by_home(home_area)
            if barrel:
                barrel.owner = char_name
    
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
        """Get the area name at a position. Works with float positions."""
        cell_x = int(x)
        cell_y = int(y)
        if 0 <= cell_x < SIZE and 0 <= cell_y < SIZE:
            return self.area_map[cell_y][cell_x]
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
    
    def get_villages(self):
        """Get all areas that are villages (have role='village').
        Villages define allegiances - the village name IS the allegiance.
        """
        return [area_def["name"] for area_def in AREAS if area_def.get("role") == "village"]
    
    def is_village_area(self, area_name):
        """Check if an area is a village (has role='village')."""
        return self.get_area_role(area_name) == "village"
    
    def get_allegiance_of_area(self, area_name):
        """Get the allegiance that an area belongs to.
        - If area is a village (role='village'), the allegiance is the village name itself
        - If area has an 'allegiance' field, return that
        - Otherwise return None
        """
        for area_def in AREAS:
            if area_def["name"] == area_name:
                if area_def.get("role") == "village":
                    return area_name  # Village's allegiance is itself
                return area_def.get("allegiance")
        return None
    
    def get_areas_for_allegiance(self, allegiance):
        """Get all areas that belong to an allegiance.
        This includes the village itself and all areas with allegiance=<village>.
        """
        areas = []
        for area_def in AREAS:
            area_name = area_def["name"]
            if area_def.get("role") == "village" and area_name == allegiance:
                areas.append(area_name)
            elif area_def.get("allegiance") == allegiance:
                areas.append(area_name)
        return areas
    
    def get_steward_for_allegiance(self, allegiance):
        """Find the steward character for a given allegiance."""
        for char in self.characters:
            if char.get('job') == 'Steward' and char.get('allegiance') == allegiance:
                return char
        return None
    
    def is_position_valid(self, x, y):
        """Check if position is within bounds (works with float positions)"""
        return 0 <= x < SIZE and 0 <= y < SIZE
    
    def is_position_blocked(self, x, y, exclude_char=None):
        """Check if a position would hard-collide with any character.
        Uses a small collision radius to allow characters to squeeze past each other
        like in ALTTP - characters can overlap significantly but can't stand on same spot.
        
        Args:
            x, y: Position to check (float)
            exclude_char: Character to exclude from check (for self-collision)
        """
        for char in self.characters:
            if char is exclude_char:
                continue
            # Use small collision radius - characters can squeeze past each other
            dx = abs(char['x'] - x)
            dy = abs(char['y'] - y)
            # Only block if centers are VERY close (within 2x collision radius)
            collision_dist = CHARACTER_COLLISION_RADIUS * 2
            if dx < collision_dist and dy < collision_dist:
                # Use circular distance for smoother collision
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < collision_dist:
                    return True
        return False
    
    def is_occupied(self, x, y):
        """Check if a cell is occupied by any character (for grid-based queries).
        Converts float position to cell and checks if any character's center is in that cell.
        """
        cell_x = int(x)
        cell_y = int(y)
        for char in self.characters:
            char_cell_x = int(char['x'])
            char_cell_y = int(char['y'])
            if char_cell_x == cell_x and char_cell_y == cell_y:
                return True
        return False
    
    def get_character_at(self, x, y):
        """Get character whose center is in the cell at position (x, y)."""
        cell_x = int(x)
        cell_y = int(y)
        for char in self.characters:
            char_cell_x = int(char['x'])
            char_cell_y = int(char['y'])
            if char_cell_x == cell_x and char_cell_y == cell_y:
                return char
        return None
    
    def get_character_near(self, x, y, radius=None):
        """Get the closest character within radius of position (x, y).
        Uses float-based distance calculation.
        
        Args:
            x, y: Position to check (float)
            radius: Maximum distance (default: ADJACENCY_DISTANCE)
        """
        if radius is None:
            radius = ADJACENCY_DISTANCE
        
        closest = None
        closest_dist = float('inf')
        
        for char in self.characters:
            dist = math.sqrt((char['x'] - x) ** 2 + (char['y'] - y) ** 2)
            if dist < radius and dist < closest_dist:
                closest = char
                closest_dist = dist
        
        return closest
    
    def is_in_village(self, x, y):
        """Check if position is in any village or area belonging to a village.
        Returns True if the area has an allegiance (is part of a settlement).
        Works with float positions - uses the cell containing the point.
        """
        cell_x = int(x)
        cell_y = int(y)
        if not (0 <= cell_x < SIZE and 0 <= cell_y < SIZE):
            return False
        area = self.area_map[cell_y][cell_x]
        if not area:
            return False
        # Check if this area has an allegiance (is part of a settlement)
        allegiance = self.get_allegiance_of_area(area)
        return allegiance is not None
    
    def is_in_allegiance(self, x, y, allegiance):
        """Check if position is in an area belonging to a specific allegiance.
        Works with float positions.
        """
        cell_x = int(x)
        cell_y = int(y)
        if not (0 <= cell_x < SIZE and 0 <= cell_y < SIZE):
            return False
        area = self.area_map[cell_y][cell_x]
        if not area:
            return False
        area_allegiance = self.get_allegiance_of_area(area)
        return area_allegiance == allegiance
    
    def get_allegiance_at(self, x, y):
        """Get the allegiance at a position, if any.
        Works with float positions.
        """
        area = self.get_area_at(x, y)
        if area:
            return self.get_allegiance_of_area(area)
        return None
    
    def get_area_cells(self, area_name):
        """Get all cells belonging to an area"""
        cells = []
        for y in range(SIZE):
            for x in range(SIZE):
                if self.area_map[y][x] == area_name:
                    cells.append((x, y))
        return cells
    
    def get_area_bounds(self, area_name):
        """Get the bounding box of an area as (min_x, min_y, max_x, max_y).
        Returns None if area not found.
        """
        cells = self.get_area_cells(area_name)
        if not cells:
            return None
        
        min_x = min(c[0] for c in cells)
        max_x = max(c[0] for c in cells)
        min_y = min(c[1] for c in cells)
        max_y = max(c[1] for c in cells)
        return (min_x, min_y, max_x, max_y)
    
    def get_village_bounds(self):
        """Get the bounding box of all village areas combined."""
        min_x, max_x = SIZE, 0
        min_y, max_y = SIZE, 0
        found = False
        
        for y in range(SIZE):
            for x in range(SIZE):
                if self.is_in_village(x, y):
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)
                    found = True
        
        if not found:
            return None
        return (min_x, min_y, max_x, max_y)
    
    def get_area_points_of_interest(self, area_name, is_village=False):
        """Get interesting points within an area for idle wandering.
        Returns list of (x, y) float positions representing:
        - Center of area
        - Corners of area
        - Midpoints of edges
        Avoids farm cells.
        """
        if is_village:
            bounds = self.get_village_bounds()
        else:
            bounds = self.get_area_bounds(area_name)
        
        if not bounds:
            return []
        
        min_x, min_y, max_x, max_y = bounds
        
        # Calculate center and edge midpoints (as float positions, cell centers)
        center_x = (min_x + max_x) / 2.0 + 0.5
        center_y = (min_y + max_y) / 2.0 + 0.5
        
        # Points of interest (cell centers)
        points = [
            # Center
            (center_x, center_y),
            # Corners (slightly inward to stay in area)
            (min_x + 0.5, min_y + 0.5),  # Top-left
            (max_x + 0.5, min_y + 0.5),  # Top-right
            (min_x + 0.5, max_y + 0.5),  # Bottom-left
            (max_x + 0.5, max_y + 0.5),  # Bottom-right
            # Edge midpoints
            (center_x, min_y + 0.5),  # Top edge
            (center_x, max_y + 0.5),  # Bottom edge
            (min_x + 0.5, center_y),  # Left edge
            (max_x + 0.5, center_y),  # Right edge
        ]
        
        # Filter out points that are on farm cells
        valid_points = []
        for px, py in points:
            cell_x, cell_y = int(px), int(py)
            if (cell_x, cell_y) not in self.farm_cells:
                # Also verify the point is actually in the target area
                if is_village:
                    if self.is_in_village(cell_x, cell_y):
                        valid_points.append((px, py))
                else:
                    if self.get_area_at(cell_x, cell_y) == area_name:
                        valid_points.append((px, py))
        
        return valid_points
    
    def get_valid_idle_cells(self, area_name, is_village=False):
        """Get all valid cells for idle wandering in an area.
        Excludes farm cells.
        """
        valid_cells = []
        for y in range(SIZE):
            for x in range(SIZE):
                # Skip farm cells
                if (x, y) in self.farm_cells:
                    continue
                
                if is_village:
                    if self.is_in_village(x, y):
                        valid_cells.append((x, y))
                else:
                    if self.get_area_at(x, y) == area_name:
                        valid_cells.append((x, y))
        return valid_cells
    
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
    
    def get_patrol_waypoints(self, allegiance=None):
        """Get patrol waypoints for soldiers - a grid of points covering walkable ground.
        
        Generates waypoints spread across the village area to ensure soldiers
        cover ground between buildings, along roads, and through open spaces.
        Points are spaced ~3 cells apart to create a patrol route that covers
        the entire settlement over time.
        
        Args:
            allegiance: If specified, only return waypoints in areas belonging to this allegiance
        
        Returns list of (x, y) tuples for patrol route points.
        """
        waypoints = []
        
        # Get bounds of all areas belonging to this allegiance
        min_x, min_y = SIZE, SIZE
        max_x, max_y = 0, 0
        
        for area_def in AREAS:
            # Check allegiance
            area_allegiance = area_def.get('allegiance')
            if area_def.get('role') == 'village':
                area_allegiance = area_def['name']
            
            if allegiance and area_allegiance != allegiance:
                continue
            
            bounds = area_def.get('bounds', [0, 0, 0, 0])
            y_start, x_start, y_end, x_end = bounds
            
            min_x = min(min_x, x_start)
            min_y = min(min_y, y_start)
            max_x = max(max_x, x_end)
            max_y = max(max_y, y_end)
        
        if min_x >= max_x or min_y >= max_y:
            return []
        
        # Generate grid of patrol points with ~3 cell spacing
        spacing = 3
        
        for y in range(min_y + 1, max_y - 1, spacing):
            for x in range(min_x + 1, max_x - 1, spacing):
                # Check if this point is in a valid patrol area (not inside a building)
                # We want points in open ground, roads, market - not inside house interiors
                px, py = x + 0.5, y + 0.5
                
                if not self.is_position_valid(px, py):
                    continue
                
                # Skip farm cells - don't patrol through crops
                if (x, y) in self.farm_cells:
                    continue
                
                # Check area at this position
                area = self.get_area_at(px, py)
                if area:
                    role = self.get_area_role(area)
                    # Skip interior of houses/farmhouses (soldiers patrol outside, not inside homes)
                    # But include military_housing, market, village (open areas)
                    if role in ('house', 'farmhouse'):
                        continue
                
                waypoints.append((px, py))
        
        return waypoints
    
    def get_farm_cell_state(self, x, y):
        """Get the state of a farm cell. Works with float positions."""
        cell_x = int(x)
        cell_y = int(y)
        return self.farm_cells.get((cell_x, cell_y))
    
    def get_area_allegiance(self, x, y):
        """Get the allegiance of the area at a position. Works with float positions.
        Deprecated - use get_allegiance_at instead.
        """
        return self.get_allegiance_at(x, y)
    
    def get_farm_cell_allegiance(self, x, y):
        """Get the allegiance of a farm cell. Works with float positions."""
        cell_x = int(x)
        cell_y = int(y)
        cell = self.farm_cells.get((cell_x, cell_y))
        if cell:
            return cell.get('allegiance')
        return None
    
    def get_template(self, name):
        """Get the static template for a character by name"""
        return CHARACTER_TEMPLATES.get(name)
    
    def get_distance(self, char1, char2):
        """Euclidean distance between two characters (float-based)."""
        import math
        return math.sqrt((char1['x'] - char2['x']) ** 2 + (char1['y'] - char2['y']) ** 2)
    
    def get_steward(self):
        """Get the steward character, or None if no steward exists."""
        for char in self.characters:
            if char.get('job') == 'Steward':
                return char
        return None
    
    def get_allegiance_count(self, allegiance):
        """Count all characters with a specific allegiance."""
        return sum(1 for c in self.characters if c.get('allegiance') == allegiance)
    
    def get_character_bed(self, char):
        """Get the bed owned by this character, if any."""
        return self.interactables.get_bed_by_owner(char['name'])
    
    def is_sleep_time(self):
        """Check if it's currently sleep time (latter portion of day)."""
        from constants import TICKS_PER_DAY, SLEEP_START_FRACTION
        day_tick = self.ticks % TICKS_PER_DAY
        return day_tick >= TICKS_PER_DAY * SLEEP_START_FRACTION
    
    # =========================================================================
    # MODIFICATION METHODS (simple state changes)
    # =========================================================================
    
    def remove_character(self, char):
        """Remove a character from the game and clear all references to them"""
        if char in self.characters:
            self.characters.remove(char)
        if char == self.player:
            self.player = None
        
        # Get the id before clearing references (needed for known_crimes lookup)
        char_id = id(char)
        
        # Clear all references to this character from other characters
        for other in self.characters:
            if other.get('robbery_target') == char:
                other['robbery_target'] = None
                other['is_aggressor'] = False
            if other.get('flee_from') == char:
                other['flee_from'] = None
            if other.get('tax_collection_target') == char:
                other['tax_collection_target'] = None
            # Clear from known_crimes memory (uses id() as key)
            if 'known_crimes' in other and char_id in other['known_crimes']:
                del other['known_crimes'][char_id]
    
    def log_action(self, message):
        """Add a message to the action log"""
        from constants import TICKS_PER_DAY, TICKS_PER_YEAR
        year = (self.ticks // TICKS_PER_YEAR) + 1
        day = ((self.ticks % TICKS_PER_YEAR) // TICKS_PER_DAY) + 1
        day_tick = self.ticks % TICKS_PER_DAY
        log_entry = f"[Y{year}D{day}T{day_tick}] {message}"
        self.action_log.append(log_entry)
        
        # Track total entries ever added (for debug window sync)
        self.log_total_count = getattr(self, 'log_total_count', 0) + 1
        
        # Keep only last 1000 entries (increased from 100)
        if len(self.action_log) > 1000:
            self.action_log = self.action_log[-1000:]
    
    def reset(self):
        """Reset game to initial state"""
        self.ticks = 0
        self.game_speed = 1
        self.paused = False
        self.characters = []
        self.player = None
        self.farm_cells = {}
        self.death_animations = []
        self.action_log = []
        self.log_total_count = 0
        self.area_map = [[None for _ in range(SIZE)] for _ in range(SIZE)]
        
        self._init_areas()
        self._init_farm_cells()
        self._init_interactables()
        self._init_characters()
