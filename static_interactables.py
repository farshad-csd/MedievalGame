# static_interactables.py - Static interactable objects (barrels, beds, stoves, campfires)
"""
Classes for static world objects that characters can interact with.

Each class:
- Holds its own state (position, home, owner, inventory)
- Provides methods for interaction
- Is instantiated by GameState during initialization
"""

import math
from constants import ITEMS, ADJACENCY_DISTANCE, INVENTORY_SLOTS


class Interactable:
    """Base class for all interactable objects."""
    
    def __init__(self, name, x, y, home=None):
        """
        Args:
            name: Display name for this object
            x: X position (cell coordinate)
            y: Y position (cell coordinate)
            home: Home area name (for access control)
        """
        self.name = name
        self.x = x
        self.y = y
        self.home = home
    
    @property
    def position(self):
        """Get (x, y) tuple."""
        return (self.x, self.y)
    
    @property
    def center(self):
        """Get center point (for distance calculations)."""
        return (self.x + 0.5, self.y + 0.5)
    
    def distance_to(self, char):
        """Calculate distance from character to this object's center."""
        cx, cy = self.center
        return math.sqrt((char.x - cx) ** 2 + (char.y - cy) ** 2)
    
    def is_adjacent(self, char):
        """Check if character is adjacent to this object."""
        return self.distance_to(char) <= ADJACENCY_DISTANCE
    
    def __repr__(self):
        return f"<{self.__class__.__name__} '{self.name}' at ({self.x}, {self.y})>"


class Barrel(Interactable):
    """
    Storage container with inventory slots.
    Can be owned by a character and associated with a home area.
    """
    
    def __init__(self, name, x, y, home=None, owner=None, slots=INVENTORY_SLOTS):
        super().__init__(name, x, y, home)
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
    def get_wheat(self):
        return self.get_item('wheat')
    
    def add_wheat(self, amount):
        return self.add_item('wheat', amount)
    
    def remove_wheat(self, amount):
        return self.remove_item('wheat', amount)
    
    def can_add_wheat(self, amount):
        return self.can_add_item('wheat', amount)


class Bed(Interactable):
    """
    Sleeping spot that can be owned by a character.
    Associated with a home area.
    """
    
    def __init__(self, name, x, y, home=None, owner=None):
        super().__init__(name, x, y, home)
        self.owner = owner
    
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
    
    def __init__(self, name, x, y, home=None):
        super().__init__(name, x, y, home)
    
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
    
    def __init__(self, x, y, owner_name=None):
        super().__init__(f"Campfire", x, y, home=None)
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
            barrel = Barrel(
                name=barrel_def["name"],
                x=x, y=y,
                home=barrel_def.get("home")
            )
            self.barrels[(x, y)] = barrel
    
    def init_beds(self, bed_defs):
        """Initialize beds from configuration list."""
        self.beds = {}
        for bed_def in bed_defs:
            x, y = bed_def["position"]
            bed = Bed(
                name=bed_def["name"],
                x=x, y=y,
                home=bed_def.get("home")
            )
            self.beds[(x, y)] = bed
    
    def init_stoves(self, stove_defs):
        """Initialize stoves from configuration list."""
        self.stoves = {}
        for stove_def in stove_defs:
            x, y = stove_def["position"]
            stove = Stove(
                name=stove_def["name"],
                x=x, y=y,
                home=stove_def.get("home")
            )
            self.stoves[(x, y)] = stove
    
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
    
    def get_barrel_at(self, x, y):
        """Get barrel at position, if any."""
        return self.barrels.get((x, y))
    
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
    
    def get_bed_at(self, x, y):
        """Get bed at position, if any."""
        return self.beds.get((x, y))
    
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
    
    def get_stove_at(self, x, y):
        """Get stove at position, if any."""
        return self.stoves.get((x, y))
    
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
        """Get all stoves this character can use (home matches)."""
        return [(stove.position, stove) for stove in self.stoves.values()
                if stove.can_use(char)]
    
    # =========================================================================
    # CAMPFIRE METHODS
    # =========================================================================
    
    def add_campfire(self, x, y, owner_name=None):
        """Create a new campfire at position."""
        campfire = Campfire(x, y, owner_name)
        self.campfires[(x, y)] = campfire
        return campfire
    
    def get_campfire_at(self, x, y):
        """Get campfire at position, if any."""
        return self.campfires.get((x, y))
    
    def remove_campfire(self, x, y):
        """Remove campfire at position."""
        if (x, y) in self.campfires:
            del self.campfires[(x, y)]
    
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
