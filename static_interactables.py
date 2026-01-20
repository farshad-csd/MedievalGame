# static_interactables.py - Static interactable objects (barrels, beds, stoves, campfires)
"""
Classes for static world objects that characters can interact with.

Each class:
- Holds its own state (position, home, owner, inventory)
- Provides methods for interaction
- Is instantiated by GameState during initialization
"""

import math
from constants import ITEMS, ADJACENCY_DISTANCE, INVENTORY_SLOTS, BARREL_SLOTS


class Interactable:
    """Base class for all interactable objects."""
    
    def __init__(self, name, x, y, home=None, zone=None):
        """
        Args:
            name: Display name for this object
            x: X position (cell coordinate) - interior coords if zone is set
            y: Y position (cell coordinate) - interior coords if zone is set
            home: Home area name (for access control)
            zone: Interior name if inside a building, None if in exterior world
        """
        self.name = name
        self.x = x
        self.y = y
        self.home = home
        self.zone = zone  # None = exterior, "Interior Name" = inside that interior
        
        # Interior projection parameters (set via set_interior_projection when in interior)
        self._interior_proj_x = 0
        self._interior_proj_y = 0
        self._interior_scale_x = 1.0
        self._interior_scale_y = 1.0
    
    def set_interior_projection(self, interior):
        """Configure projection params when placed in an interior.
        
        Args:
            interior: Interior object this interactable is placed in
        """
        self._interior_proj_x = interior.exterior_x
        self._interior_proj_y = interior.exterior_y
        self._interior_scale_x = interior.scale_x
        self._interior_scale_y = interior.scale_y
    
    @property
    def world_x(self):
        """Get world X coordinate (projected if in interior)."""
        if self.zone is None:
            return self.x + 0.5
        return self._interior_proj_x + ((self.x + 0.5) * self._interior_scale_x)
    
    @property
    def world_y(self):
        """Get world Y coordinate (projected if in interior)."""
        if self.zone is None:
            return self.y + 0.5
        return self._interior_proj_y + ((self.y + 0.5) * self._interior_scale_y)
    
    @property
    def position(self):
        """Get (x, y) tuple."""
        return (self.x, self.y)
    
    @property
    def center(self):
        """Get center point (for distance calculations)."""
        return (self.x + 0.5, self.y + 0.5)
    
    def distance_to(self, char):
        """Calculate distance from character to this object's center.
        Uses interior coords (prevailing_x/y) when both are in same interior zone,
        world coords (x/y) when both are in exterior.
        """
        cx, cy = self.center
        
        # Use interior coords when object is in an interior
        if self.zone is not None:
            # Character must have interior coords set if they're in an interior
            char_x = char.prevailing_x
            char_y = char.prevailing_y
        else:
            # Use world coords for exterior objects
            char_x = char.x
            char_y = char.y
        
        return math.sqrt((char_x - cx) ** 2 + (char_y - cy) ** 2)
    
    def is_adjacent(self, char):
        """Check if character is adjacent to this object.
        Character must be in the same zone (interior or exterior) as the object.
        """
        # Check zone match first - both must be in same zone
        char_zone = char.zone if hasattr(char, 'zone') else None
        if char_zone != self.zone:
            return False
        return self.distance_to(char) <= ADJACENCY_DISTANCE
    
    def __repr__(self):
        return f"<{self.__class__.__name__} '{self.name}' at ({self.x}, {self.y})>"


class Barrel(Interactable):
    """
    Storage container with inventory slots.
    Can be owned by a character and associated with a home area.
    """
    
    def __init__(self, name, x, y, home=None, owner=None, slots=BARREL_SLOTS, zone=None):
        super().__init__(name, x, y, home, zone=zone)
        self.owner = owner
        self.inventory = [None] * slots
    
    def can_use(self, char):
        """Check if character can use (take from) this barrel.
        Owner can always use it. Others can use if their home matches.
        """
        if self.owner == char.name:
            return True
        return char.get('home') == self.home
    
    # =========================================================================
    # INVENTORY METHODS
    # =========================================================================
    
    def get_item(self, item_type):
        """Get total amount of an item type in this barrel."""
        total = 0
        for slot in self.inventory:
            if slot and slot['type'] == item_type:
                total += slot['amount']
        return total
    
    def can_add_item(self, item_type, amount):
        """Check if barrel can add this much of an item."""
        stack_size = ITEMS[item_type]["stack_size"]
        
        # None means unlimited stacking
        if stack_size is None:
            # Check for any same-type slot or empty slot
            for slot in self.inventory:
                if slot is None or slot['type'] == item_type:
                    return True
            return False
        
        space = 0
        for slot in self.inventory:
            if slot is None:
                space += stack_size
            elif slot['type'] == item_type and slot['amount'] < stack_size:
                space += stack_size - slot['amount']
        return space >= amount
    
    def add_item(self, item_type, amount):
        """Add item to inventory. Returns amount actually added."""
        stack_size = ITEMS[item_type]["stack_size"]
        remaining = amount
        
        # Handle unlimited stacking (None)
        if stack_size is None:
            # First, try to add to existing stack of same type
            for slot in self.inventory:
                if slot and slot['type'] == item_type:
                    slot['amount'] += remaining
                    return amount
            
            # Then, use first empty slot
            for i, slot in enumerate(self.inventory):
                if slot is None:
                    self.inventory[i] = {'type': item_type, 'amount': remaining}
                    return amount
            
            return 0  # No space
        
        # Normal stacking with limit
        # First, fill existing stacks
        for slot in self.inventory:
            if slot and slot['type'] == item_type and slot['amount'] < stack_size:
                can_add = stack_size - slot['amount']
                to_add = min(remaining, can_add)
                slot['amount'] += to_add
                remaining -= to_add
                if remaining <= 0:
                    return amount
        
        # Then, use empty slots
        for i, slot in enumerate(self.inventory):
            if slot is None:
                to_add = min(remaining, stack_size)
                self.inventory[i] = {'type': item_type, 'amount': to_add}
                remaining -= to_add
                if remaining <= 0:
                    return amount
        
        return amount - remaining
    
    def remove_item(self, item_type, amount):
        """Remove item from inventory. Returns amount actually removed."""
        remaining = amount
        
        # Remove from stacks (prefer smaller stacks first to consolidate)
        item_slots = [(i, slot) for i, slot in enumerate(self.inventory) 
                     if slot and slot['type'] == item_type]
        item_slots.sort(key=lambda x: x[1]['amount'])
        
        for i, slot in item_slots:
            to_remove = min(remaining, slot['amount'])
            slot['amount'] -= to_remove
            remaining -= to_remove
            
            # Remove empty slot
            if slot['amount'] <= 0:
                self.inventory[i] = None
            
            if remaining <= 0:
                return amount
        
        return amount - remaining
    
    # Convenience methods for common items


class Corpse(Interactable):
    """
    Corpse of a dead character with lootable inventory.
    Remains indefinitely until looted/removed.
    """

    def __init__(self, name, character_name, x, y, zone=None, facing='down', job=None, morality=5, inventory_size=None):
        """
        Args:
            name: Display name (e.g., "John Smith's Corpse")
            character_name: Name of the dead character
            x: X position - EXACT float position where character died (not cell coords)
            y: Y position - EXACT float position where character died (not cell coords)
            zone: Interior name if inside, None if exterior
            facing: Facing direction when died (for sprite)
            job: Job of character (for sprite selection)
            morality: Morality of character (for sprite selection)
            inventory_size: Size of inventory (defaults to INVENTORY_SLOTS if not provided)
        """
        # Store exact position (don't call super().__init__ which expects cell coords)
        self.name = name
        self.x = x  # Float position
        self.y = y  # Float position
        self.home = None
        self.zone = zone

        # Interior projection parameters
        self._interior_proj_x = 0
        self._interior_proj_y = 0
        self._interior_scale_x = 1.0
        self._interior_scale_y = 1.0

        self.character_name = character_name
        self.facing = facing
        self.job = job
        self.morality = morality
        # Match the character's inventory size exactly
        size = inventory_size if inventory_size is not None else INVENTORY_SLOTS
        self.inventory = [None] * size

    @property
    def center(self):
        """Get center point (for distance calculations). Corpse uses exact position."""
        return (self.x, self.y)

    def can_use(self, char):
        """Anyone can loot a corpse."""
        return True

    # =========================================================================
    # INVENTORY METHODS (identical to Barrel)
    # =========================================================================

    def get_item(self, item_type):
        """Get total amount of an item type in this corpse."""
        total = 0
        for slot in self.inventory:
            if slot and slot['type'] == item_type:
                total += slot['amount']
        return total

    def can_add_item(self, item_type, amount):
        """Check if corpse can add this much of an item."""
        stack_size = ITEMS[item_type]["stack_size"]

        # None means unlimited stacking
        if stack_size is None:
            # Check for any same-type slot or empty slot
            for slot in self.inventory:
                if slot is None or slot['type'] == item_type:
                    return True
            return False

        space = 0
        for slot in self.inventory:
            if slot is None:
                space += stack_size
            elif slot['type'] == item_type and slot['amount'] < stack_size:
                space += stack_size - slot['amount']
        return space >= amount

    def add_item(self, item_type, amount):
        """Add item to inventory. Returns amount actually added."""
        stack_size = ITEMS[item_type]["stack_size"]
        remaining = amount

        # Handle unlimited stacking (None)
        if stack_size is None:
            # First, try to add to existing stack of same type
            for slot in self.inventory:
                if slot and slot['type'] == item_type:
                    slot['amount'] += remaining
                    return amount

            # Then, use first empty slot
            for i, slot in enumerate(self.inventory):
                if slot is None:
                    self.inventory[i] = {'type': item_type, 'amount': remaining}
                    return amount

            return 0  # No space

        # Normal stacking with limit
        # First, fill existing stacks
        for slot in self.inventory:
            if slot and slot['type'] == item_type and slot['amount'] < stack_size:
                can_add = stack_size - slot['amount']
                to_add = min(remaining, can_add)
                slot['amount'] += to_add
                remaining -= to_add
                if remaining <= 0:
                    return amount

        # Then, use empty slots
        for i, slot in enumerate(self.inventory):
            if slot is None:
                to_add = min(remaining, stack_size)
                self.inventory[i] = {'type': item_type, 'amount': to_add}
                remaining -= to_add
                if remaining <= 0:
                    return amount

        return amount - remaining

    def remove_item(self, item_type, amount):
        """Remove item from inventory. Returns amount actually removed."""
        remaining = amount

        # Remove from stacks (prefer smaller stacks first to consolidate)
        item_slots = [(i, slot) for i, slot in enumerate(self.inventory)
                     if slot and slot['type'] == item_type]
        item_slots.sort(key=lambda x: x[1]['amount'])

        for i, slot in item_slots:
            to_remove = min(remaining, slot['amount'])
            slot['amount'] -= to_remove
            remaining -= to_remove

            # Remove empty slot
            if slot['amount'] <= 0:
                self.inventory[i] = None

            if remaining <= 0:
                return amount

        return amount - remaining


class Bed(Interactable):
    """
    Sleeping spot that can be owned by a character.
    Associated with a home area.
    Beds are 2 cells tall visually, but have expanded collision bounds.
    """

    def __init__(self, name, x, y, home=None, owner=None, zone=None, height=2):
        super().__init__(name, x, y, home, zone=zone)
        self.owner = owner
        self.height = height  # Visual height (2 cells)
        # Collision padding - extends hitbox beyond visual bounds
        self.collision_pad_top = 0.3     # Extend collision above bed
        self.collision_pad_bottom = 0.5  # Extend collision below bed (front)
        self.collision_pad_left = 0.2    # Extend collision left
        self.collision_pad_right = 0.2   # Extend collision right
    
    @property
    def center(self):
        """Get center point (for distance calculations). Accounts for height."""
        return (self.x + 0.5, self.y + self.height / 2)
    
    @property
    def collision_bounds(self):
        """Get expanded collision bounds (x_min, y_min, x_max, y_max)."""
        return (
            self.x - self.collision_pad_left,
            self.y - self.collision_pad_top,
            self.x + 1 + self.collision_pad_right,
            self.y + self.height + self.collision_pad_bottom
        )
    
    def contains_point(self, px, py):
        """Check if a point is within the bed's collision area."""
        x_min, y_min, x_max, y_max = self.collision_bounds
        return (x_min <= px < x_max and y_min <= py < y_max)
    
    def assign_owner(self, owner_name):
        """Assign an owner to this bed."""
        self.owner = owner_name
    
    def unassign_owner(self):
        """Remove owner from this bed."""
        self.owner = None
    
    def is_owned(self):
        """Check if this bed has an owner."""
        return self.owner is not None
    
    def is_owned_by(self, char_name):
        """Check if this bed is owned by the given character."""
        return self.owner == char_name


class Stove(Interactable):
    """
    Cooking spot associated with a home area.
    Characters can only use stoves in their home area.
    """
    
    def __init__(self, name, x, y, home=None, zone=None):
        super().__init__(name, x, y, home, zone=zone)
    
    def can_use(self, char):
        """Check if character can use this stove.
        Requires character's home to match stove's home.
        """
        char_home = char.get('home')
        if char_home is None:
            return False
        return char_home == self.home


class Campfire(Interactable):
    """
    Temporary cooking/sleeping spot created by characters.
    Unlike other interactables, campfires are dynamically created.
    """
    
    def __init__(self, x, y, owner_name=None, zone=None):
        super().__init__(f"Campfire", x, y, home=None, zone=zone)
        self.owner = owner_name
    
    def can_use(self, char):
        """Anyone can use a campfire."""
        return True
    
    def is_owned_by(self, char_name):
        """Check if this campfire is owned by the given character."""
        return self.owner == char_name


class Tree(Interactable):
    """
    A tree occupying a single cell.
    Currently no interaction - just a static world object.
    """
    
    def __init__(self, x, y):
        super().__init__("Tree", x, y, home=None)
    
    def __repr__(self):
        return f"<Tree at ({self.x}, {self.y})>"


class House(Interactable):
    """
    A house occupying multiple cells defined by bounds.
    Currently no interaction - just a static world object.
    
    The position (x, y) is the top-left corner of the house.
    The full footprint is defined by bounds [y_start, x_start, y_end, x_end].
    """
    
    def __init__(self, name, bounds, allegiance=None):
        """
        Args:
            name: Display name for this house
            bounds: [y_start, x_start, y_end, x_end] defining the house footprint
            allegiance: Which faction/village this house belongs to
        """
        y_start, x_start, y_end, x_end = bounds
        super().__init__(name, x_start, y_start, home=None)
        self.bounds = bounds
        self.allegiance = allegiance
        self.width = x_end - x_start
        self.height = y_end - y_start
        
        # Interior space (set by GameState._init_interiors)
        self.interior = None
    
    @property
    def center(self):
        """Get center point of the house (for distance calculations)."""
        y_start, x_start, y_end, x_end = self.bounds
        return ((x_start + x_end) / 2, (y_start + y_end) / 2)
    
    def contains_point(self, x, y):
        """Check if a point is within this house's bounds."""
        y_start, x_start, y_end, x_end = self.bounds
        return x_start <= x < x_end and y_start <= y < y_end
    
    def get_cells(self):
        """Get all cells occupied by this house."""
        y_start, x_start, y_end, x_end = self.bounds
        cells = []
        for cy in range(y_start, y_end):
            for cx in range(x_start, x_end):
                cells.append((cx, cy))
        return cells
    
    def __repr__(self):
        return f"<House '{self.name}' bounds={self.bounds}>"


# =============================================================================
# MANAGER CLASS
# =============================================================================

class InteractableManager:
    """
    Manages all interactable objects in the game world.
    Provides lookup methods by position, home, owner, etc.
    """
    
    def __init__(self):
        self.barrels = {}  # (x, y) -> Barrel
        self.beds = {}     # (x, y) -> Bed
        self.stoves = {}   # (x, y) -> Stove
        self.campfires = {}  # (x, y) -> Campfire
        self.trees = {}    # (x, y) -> Tree
        self.houses = {}   # name -> House
    
    # =========================================================================
    # INITIALIZATION
    # =========================================================================
    
    def init_barrels(self, barrel_defs):
        """Initialize barrels from configuration list."""
        self.barrels = {}
        for barrel_def in barrel_defs:
            x, y = barrel_def["position"]
            zone = barrel_def.get("zone")  # None for exterior, interior name for inside
            barrel = Barrel(
                name=barrel_def["name"],
                x=x, y=y,
                home=barrel_def.get("home"),
                zone=zone
            )
            # Key includes zone to allow same coords in different zones
            self.barrels[(x, y, zone)] = barrel
    
    def init_beds(self, bed_defs):
        """Initialize beds from configuration list."""
        self.beds = {}
        for bed_def in bed_defs:
            x, y = bed_def["position"]
            zone = bed_def.get("zone")  # None for exterior, interior name for inside
            bed = Bed(
                name=bed_def["name"],
                x=x, y=y,
                home=bed_def.get("home"),
                zone=zone,
                height=bed_def.get("height", 2)  # Default to 2 cells tall visually
            )
            # Key includes zone to allow same coords in different zones
            self.beds[(x, y, zone)] = bed
    
    def init_stoves(self, stove_defs):
        """Initialize stoves from configuration list."""
        self.stoves = {}
        for stove_def in stove_defs:
            x, y = stove_def["position"]
            zone = stove_def.get("zone")  # None for exterior, interior name for inside
            stove = Stove(
                name=stove_def["name"],
                x=x, y=y,
                home=stove_def.get("home"),
                zone=zone
            )
            # Key includes zone to allow same coords in different zones
            self.stoves[(x, y, zone)] = stove
    
    def init_trees(self, tree_positions):
        """Initialize trees from list of (x, y) positions."""
        self.trees = {}
        for pos in tree_positions:
            x, y = pos
            tree = Tree(x, y)
            self.trees[(x, y)] = tree
    
    def init_houses(self, house_defs):
        """Initialize houses from configuration list.
        
        Args:
            house_defs: List of dicts with 'name', 'bounds', and optionally 'allegiance'
        """
        self.houses = {}
        for house_def in house_defs:
            house = House(
                name=house_def["name"],
                bounds=house_def["bounds"],
                allegiance=house_def.get("allegiance")
            )
            self.houses[house.name] = house
    
    def reset(self, barrel_defs, bed_defs, stove_defs, tree_positions=None, house_defs=None):
        """Reset all interactables from configuration."""
        self.init_barrels(barrel_defs)
        self.init_beds(bed_defs)
        self.init_stoves(stove_defs)
        self.init_trees(tree_positions or [])
        self.init_houses(house_defs or [])
        self.campfires = {}
    
    # =========================================================================
    # BARREL LOOKUPS
    # =========================================================================
    
    def get_barrel_at(self, x, y, zone=None):
        """Get barrel at position in the given zone, if any."""
        return self.barrels.get((x, y, zone))
    
    def get_barrel_by_home(self, home):
        """Get barrel in the given home area."""
        for barrel in self.barrels.values():
            if barrel.home == home:
                return barrel
        return None
    
    def get_barrel_by_owner(self, owner_name):
        """Get barrel owned by the given character name."""
        for barrel in self.barrels.values():
            if barrel.owner == owner_name:
                return barrel
        return None
    
    def get_barrel_position(self, barrel):
        """Get the (x, y) position of a barrel."""
        return barrel.position if barrel else None
    
    def is_adjacent_to_barrel(self, char, barrel):
        """Check if character is adjacent to the barrel."""
        return barrel.is_adjacent(char) if barrel else False
    
    # =========================================================================
    # BED LOOKUPS
    # =========================================================================
    
    def get_bed_at(self, x, y, zone=None):
        """Get bed at position in the given zone, if any."""
        return self.beds.get((x, y, zone))
    
    def get_bed_by_owner(self, owner_name):
        """Get bed owned by the given character name."""
        for bed in self.beds.values():
            if bed.owner == owner_name:
                return bed
        return None
    
    def get_bed_position(self, bed):
        """Get the (x, y) position of a bed."""
        return bed.position if bed else None
    
    def get_unowned_bed_by_home(self, home):
        """Get an unowned bed in the given home area."""
        for bed in self.beds.values():
            if bed.home == home and bed.owner is None:
                return bed
        return None
    
    def assign_bed_owner(self, bed, owner_name):
        """Assign an owner to a bed."""
        if bed:
            bed.assign_owner(owner_name)
    
    def unassign_bed_owner(self, owner_name):
        """Remove bed ownership from a character. Returns the bed if found."""
        for bed in self.beds.values():
            if bed.owner == owner_name:
                bed.unassign_owner()
                return bed
        return None
    
    # =========================================================================
    # STOVE LOOKUPS
    # =========================================================================
    
    def get_stove_at(self, x, y, zone=None):
        """Get stove at position in the given zone, if any."""
        return self.stoves.get((x, y, zone))
    
    def get_stove_position(self, stove):
        """Get the (x, y) position of a stove."""
        return stove.position if stove else None
    
    def is_adjacent_to_stove(self, char, stove):
        """Check if character is adjacent to the stove."""
        return stove.is_adjacent(char) if stove else False
    
    def get_adjacent_stove(self, char):
        """Get any stove adjacent to the character, or None."""
        for stove in self.stoves.values():
            if stove.is_adjacent(char):
                return stove
        return None
    
    def can_use_stove(self, char, stove):
        """Check if character can use this stove."""
        return stove.can_use(char) if stove else False
    
    def get_stoves_for_char(self, char):
        """Get all stoves this character can use (home matches and same zone)."""
        char_zone = getattr(char, 'zone', None)
        return [(stove.position, stove) for stove in self.stoves.values()
                if stove.can_use(char) and stove.zone == char_zone]
    
    # =========================================================================
    # CAMPFIRE METHODS
    # =========================================================================
    
    def add_campfire(self, x, y, owner_name=None, zone=None):
        """Create a new campfire at position in the given zone."""
        campfire = Campfire(x, y, owner_name, zone=zone)
        self.campfires[(x, y, zone)] = campfire
        return campfire
    
    def get_campfire_at(self, x, y, zone=None):
        """Get campfire at position in the given zone, if any."""
        return self.campfires.get((x, y, zone))
    
    def remove_campfire(self, x, y, zone=None):
        """Remove campfire at position in the given zone."""
        if (x, y, zone) in self.campfires:
            del self.campfires[(x, y, zone)]
    
    def is_adjacent_to_camp(self, char, camp_position):
        """Check if character is adjacent to a camp position.
        Works with position tuple (x, y) directly since camps may be stored on characters.
        """
        if not camp_position:
            return False
        cx, cy = camp_position
        camp_center_x = cx + 0.5
        camp_center_y = cy + 0.5
        dist = math.sqrt((char.x - camp_center_x) ** 2 + (char.y - camp_center_y) ** 2)
        return dist <= ADJACENCY_DISTANCE
    
    def get_adjacent_campfire(self, char):
        """Get any campfire adjacent to the character, or None."""
        for campfire in self.campfires.values():
            if campfire.is_adjacent(char):
                return campfire
        return None
    
    # =========================================================================
    # TREE LOOKUPS
    # =========================================================================
    
    def get_tree_at(self, x, y):
        """Get tree at position, if any."""
        return self.trees.get((x, y))
    
    def has_tree_at(self, x, y):
        """Check if there is a tree at the given position."""
        return (x, y) in self.trees
    
    def get_all_tree_positions(self):
        """Get list of all tree positions."""
        return list(self.trees.keys())
    
    def remove_tree(self, x, y):
        """Remove tree at position."""
        if (x, y) in self.trees:
            del self.trees[(x, y)]
    
    # =========================================================================
    # HOUSE LOOKUPS
    # =========================================================================
    
    def get_house_by_name(self, name):
        """Get house by its name."""
        return self.houses.get(name)
    
    def get_house_at(self, x, y):
        """Get house that contains the given point, if any."""
        for house in self.houses.values():
            if house.contains_point(x, y):
                return house
        return None
    
    def get_all_houses(self):
        """Get list of all houses."""
        return list(self.houses.values())
    
    def get_houses_by_allegiance(self, allegiance):
        """Get all houses belonging to a specific allegiance."""
        return [h for h in self.houses.values() if h.allegiance == allegiance]
    
    def is_point_in_house(self, x, y):
        """Check if a point is inside any house."""
        return self.get_house_at(x, y) is not None
