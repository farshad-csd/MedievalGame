# interiors.py - Interior spaces for buildings (Pokemon-style separate dimensions)
"""
Interior system for buildings with coordinate projection.

Design:
- Each building can have an interior that exists as a separate dimension
- Interior size can differ from exterior footprint (e.g., 4x4 exterior -> 16x16 interior)
- Characters inside have projected world coordinates for perception/simulation
- Windows allow cross-boundary perception and player "security camera" viewing

Coordinate Projection:
    exterior_x = building_x + (interior_x / interior_width) * exterior_width
    exterior_y = building_y + (interior_y / interior_height) * exterior_height
    
    interior_x = (world_x - building_x) / exterior_width * interior_width
    interior_y = (world_y - building_y) / exterior_height * interior_height
"""


class Interior:
    """
    Represents the interior space of a building.
    
    The interior is a separate coordinate space that projects onto the building's
    exterior footprint. Characters inside have both interior coordinates (for
    movement/collision within) and projected world coordinates (for perception).
    """
    
    def __init__(self, house, interior_width=4, interior_height=4):
        """
        Create an interior for a house.
        
        Args:
            house: The House object this interior belongs to
            interior_width: Width of interior in cells (default 4)
            interior_height: Height of interior in cells (default 4)
        """
        self.house = house
        self.name = house.name
        
        # Interior dimensions
        self.width = interior_width
        self.height = interior_height
        
        # Exterior footprint (from house bounds)
        y_start, x_start, y_end, x_end = house.bounds
        self.exterior_x = x_start
        self.exterior_y = y_start
        self.exterior_width = x_end - x_start
        self.exterior_height = y_end - y_start
        
        # Calculate scale factors
        self.scale_x = self.exterior_width / self.width
        self.scale_y = self.exterior_height / self.height
        
        # Interior cells - initially all empty (white)
        # None = empty/walkable, other values for furniture etc.
        self.cells = [[None for _ in range(self.width)] for _ in range(self.height)]
        
        # Objects inside the interior
        self.objects = []  # List of interior objects (beds, stoves, etc.)
        
        # Windows - positions where perception crosses boundary
        self.windows = []  # List of Window objects
        
        # Door position (in interior coordinates) - in front wall
        self.door_x = self.width // 2
        self.door_y = self.height  # Front wall (outside walkable area)
        
        # Door position in exterior (world) coordinates
        self.exterior_door_x = self.exterior_x + self.exterior_width // 2
        self.exterior_door_y = self.exterior_y + self.exterior_height  # Just outside bottom edge
    
    # =========================================================================
    # COORDINATE PROJECTION
    # =========================================================================
    
    def interior_to_world(self, interior_x, interior_y):
        """
        Project interior coordinates to world coordinates.
        
        Args:
            interior_x: X position in interior space
            interior_y: Y position in interior space
            
        Returns:
            (world_x, world_y) tuple
        """
        world_x = self.exterior_x + (interior_x / self.width) * self.exterior_width
        world_y = self.exterior_y + (interior_y / self.height) * self.exterior_height
        return (world_x, world_y)
    
    def world_to_interior(self, world_x, world_y):
        """
        Project world coordinates to interior coordinates.
        
        Args:
            world_x: X position in world space
            world_y: Y position in world space
            
        Returns:
            (interior_x, interior_y) tuple
        """
        interior_x = (world_x - self.exterior_x) / self.exterior_width * self.width
        interior_y = (world_y - self.exterior_y) / self.exterior_height * self.height
        return (interior_x, interior_y)
    
    def is_inside_bounds(self, interior_x, interior_y):
        """Check if interior coordinates are within bounds."""
        return (0 <= interior_x < self.width and 
                0 <= interior_y < self.height)
    
    def is_position_blocked(self, interior_x, interior_y):
        """
        Check if a position in the interior is blocked.
        
        Args:
            interior_x: X position (can be float)
            interior_y: Y position (can be float)
            
        Returns:
            True if blocked, False if walkable
        """
        cell_x = int(interior_x)
        cell_y = int(interior_y)
        
        # Out of bounds = blocked
        if not self.is_inside_bounds(cell_x, cell_y):
            return True
        
        # Check cell content
        cell = self.cells[cell_y][cell_x]
        if cell is not None:
            # Some cells might be passable (depends on content type)
            # For now, any non-None cell is blocked
            return True
        
        return False
    
    def get_cell(self, x, y):
        """Get the content of a cell."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y][x]
        return None
    
    def set_cell(self, x, y, value):
        """Set the content of a cell."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y][x] = value
    
    # =========================================================================
    # ENTRY/EXIT
    # =========================================================================
    
    def get_entry_position(self):
        """
        Get the position a character should be placed at when entering.
        
        Returns:
            (interior_x, interior_y) tuple - just inside the door (on floor)
        """
        # Door is in front wall at y=height, spawn player just inside at y=height-1
        return (self.door_x + 0.5, self.height - 0.5)
    
    def get_exit_position(self):
        """
        Get the world position a character should be placed at when exiting.
        
        Returns:
            (world_x, world_y) tuple - just outside the door
        """
        return (self.exterior_door_x + 0.5, self.exterior_door_y + 0.5)
    
    def is_at_door(self, interior_x, interior_y, threshold=0.5):
        """
        Check if a position is at the door (for exiting).
        Door is in front wall at y=height. Player must be standing basically
        ON the door from the north side (inside the building).
        
        Args:
            interior_x: X position in interior
            interior_y: Y position in interior
            threshold: How close to door counts as "at door" (tight by default)
            
        Returns:
            True if at door
        """
        # Door is centered at (door_x + 0.5, height)
        # Player must be at the very bottom of the floor (y close to height)
        # and horizontally aligned with the door
        
        # Horizontal distance from door center
        dx = abs(interior_x - (self.door_x + 0.5))
        
        # Player must be at the bottom edge of the floor (y approaching height)
        # The floor ends at y = height, so player should be very close to that
        # Using (height - 0.3) as the "door zone" - must be in bottom 0.3 of last row
        distance_from_door_edge = self.height - interior_y
        
        # Must be horizontally aligned with door AND at the very bottom of floor
        return dx < threshold and distance_from_door_edge < 0.5 and distance_from_door_edge >= 0
    
    # =========================================================================
    # WINDOWS
    # =========================================================================
    
    def add_window(self, interior_x, interior_y, facing):
        """
        Add a window at the given interior position.
        
        Args:
            interior_x: X cell position in interior
            interior_y: Y cell position in interior
            facing: Direction the window faces ('north', 'south', 'east', 'west')
        """
        window = Window(self, interior_x, interior_y, facing)
        self.windows.append(window)
        return window
    
    def get_window_at(self, interior_x, interior_y):
        """Get window at the given interior position, if any."""
        cell_x = int(interior_x)
        cell_y = int(interior_y)
        for window in self.windows:
            if window.interior_x == cell_x and window.interior_y == cell_y:
                return window
        return None
    
    def setup_default_windows(self):
        """
        Set up default windows on walls around the interior (except front).
        Walls are at: y=-1 (back), y=height (front), x=-1 (left), x=width (right)
        """
        # North wall (back wall at y=-1) - centered window
        self.add_window(self.width // 2, -1, 'north')
        
        # East wall (right wall at x=width)
        self.add_window(self.width, self.height // 2, 'east')
        
        # West wall (left wall at x=-1)
        self.add_window(-1, self.height // 2, 'west')
    
    def __repr__(self):
        return f"<Interior '{self.name}' {self.width}x{self.height} -> {self.exterior_width}x{self.exterior_height}>"


class Window:
    """
    A window in an interior that allows cross-boundary perception.
    
    For NPCs: Standing near a window extends perception into/out of the building.
    For Player: Interacting with a window provides "security camera" view.
    """
    
    def __init__(self, interior, interior_x, interior_y, facing):
        """
        Create a window.
        
        Args:
            interior: The Interior this window belongs to
            interior_x: X cell position in interior
            interior_y: Y cell position in interior  
            facing: Direction the window faces ('north', 'south', 'east', 'west')
        """
        self.interior = interior
        self.interior_x = interior_x
        self.interior_y = interior_y
        self.facing = facing
        
        # Calculate world position of this window
        self.world_x, self.world_y = interior.interior_to_world(
            interior_x + 0.5, interior_y + 0.5
        )
        
        # Calculate exterior cell this window looks out onto
        self._calculate_exterior_position()
    
    def _calculate_exterior_position(self):
        """Calculate the exterior cell this window looks out onto."""
        house = self.interior.house
        y_start, x_start, y_end, x_end = house.bounds
        
        # Map interior edge position to exterior edge
        if self.facing == 'north':
            self.exterior_look_x = x_start + (self.interior_x / self.interior.width) * self.interior.exterior_width
            self.exterior_look_y = y_start - 0.5  # Just outside top
        elif self.facing == 'south':
            self.exterior_look_x = x_start + (self.interior_x / self.interior.width) * self.interior.exterior_width
            self.exterior_look_y = y_end + 0.5  # Just outside bottom
        elif self.facing == 'east':
            self.exterior_look_x = x_end + 0.5  # Just outside right
            self.exterior_look_y = y_start + (self.interior_y / self.interior.height) * self.interior.exterior_height
        elif self.facing == 'west':
            self.exterior_look_x = x_start - 0.5  # Just outside left
            self.exterior_look_y = y_start + (self.interior_y / self.interior.height) * self.interior.exterior_height
    
    def is_character_near(self, char_x, char_y, threshold=1.5):
        """
        Check if a character (in interior coordinates) is near this window.
        
        Args:
            char_x: Character X in interior coordinates
            char_y: Character Y in interior coordinates
            threshold: Distance threshold
            
        Returns:
            True if character is near window
        """
        dx = abs(char_x - (self.interior_x + 0.5))
        dy = abs(char_y - (self.interior_y + 0.5))
        return (dx * dx + dy * dy) < (threshold * threshold)
    
    def is_character_near_exterior(self, world_x, world_y, threshold=1.5):
        """
        Check if a character (in world coordinates) is near this window from outside.
        
        Args:
            world_x: Character X in world coordinates
            world_y: Character Y in world coordinates
            threshold: Distance threshold
            
        Returns:
            True if character is near window from exterior
        """
        dx = abs(world_x - self.exterior_look_x)
        dy = abs(world_y - self.exterior_look_y)
        return (dx * dx + dy * dy) < (threshold * threshold)
    
    def get_exterior_look_position(self):
        """
        Get the world position this window looks out onto.
        Used for "security camera" view.
        
        Returns:
            (world_x, world_y) tuple
        """
        return (self.exterior_look_x, self.exterior_look_y)
    
    def __repr__(self):
        return f"<Window at ({self.interior_x}, {self.interior_y}) facing {self.facing}>"


class InteriorManager:
    """
    Manages all building interiors.
    
    Provides lookups and handles the relationship between houses and their interiors.
    """
    
    def __init__(self):
        self.interiors = {}  # house_name -> Interior
    
    def create_interior(self, house, width=4, height=4):
        """
        Create an interior for a house.
        
        Args:
            house: House object
            width: Interior width (default 4)
            height: Interior height (default 4)
            
        Returns:
            Interior object
        """
        interior = Interior(house, width, height)
        interior.setup_default_windows()
        self.interiors[house.name] = interior
        return interior
    
    def get_interior(self, house_name):
        """Get interior by house name."""
        return self.interiors.get(house_name)
    
    def get_interior_at_world_pos(self, world_x, world_y):
        """
        Get the interior whose exterior footprint contains this world position.
        
        Args:
            world_x: World X coordinate
            world_y: World Y coordinate
            
        Returns:
            Interior if position is inside a house footprint, None otherwise
        """
        for interior in self.interiors.values():
            house = interior.house
            if house.contains_point(world_x, world_y):
                return interior
        return None
    
    def get_all_interiors(self):
        """Get list of all interiors."""
        return list(self.interiors.values())
    
    def project_to_world(self, char):
        """
        Get a character's world coordinates, handling interior projection.
        
        Args:
            char: Character object
            
        Returns:
            (world_x, world_y) tuple
        """
        zone = getattr(char, 'zone', None)
        
        if zone is None:
            # Character is in exterior - use direct coordinates
            return (char.x, char.y)
        
        # Character is in an interior - project coordinates
        interior = self.interiors.get(zone)
        if interior:
            return interior.interior_to_world(char.x, char.y)
        
        # Fallback if interior not found
        return (char.x, char.y)
    
    def reset(self):
        """Clear all interiors."""
        self.interiors = {}