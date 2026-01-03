# character.py - Character class for all game characters
"""
Character class that encapsulates all character state and behavior.

Design:
- All characters (including player) are Character instances
- Jobs are stored as strings (e.g., 'Farmer', 'Soldier'); behavior is in jobs.py
- Player is just a Character with is_player=True (enables input controls)
- Implements dict-like access for backward compatibility with existing code
"""

import time  # Used for attack animation timing (visual only, doesn't scale with game speed)
import math
from constants import (
    MAX_HUNGER, INVENTORY_SLOTS, ITEMS, SKILLS,
    CHARACTER_WIDTH, CHARACTER_HEIGHT,
    BREAD_PER_BITE, STARVATION_THRESHOLD,
    ATTACK_ANIMATION_DURATION, ATTACK_COOLDOWN_TICKS
)
from scenario_characters import CHARACTER_TEMPLATES


class Character:
    """
    Represents a character in the game world.
    
    All state is held here. Job behavior is defined in jobs.py and looked up
    by job name string. Implements __getitem__/__setitem__ for backward 
    compatibility with code that treats characters as dicts.
    """
    
    def __init__(self, name, template, x, y, home_area=None):
        """
        Create a character from a template.
        
        Args:
            name: Character's full name (key in CHARACTER_TEMPLATES)
            template: Dict from CHARACTER_TEMPLATES with static traits
            x: Starting x cell coordinate
            y: Starting y cell coordinate  
            home_area: Starting home area name (determined by job usually)
        """
        # Identity
        self.name = name
        self._is_player = template.get('is_player', False)
        
        # Static traits (from template, don't change)
        self._attractiveness = template.get('attractiveness', 5)
        self._confidence = template.get('confidence', 5)
        self._cunning = template.get('cunning', 5)
        
        # Position (float-based for smooth movement)
        # Characters spawn at CENTER of their starting cell
        self.x = float(x) + 0.5
        self.y = float(y) + 0.5
        
        # Velocity for continuous movement (cells per second)
        self.vx = 0.0
        self.vy = 0.0
        
        # Hitbox dimensions
        self.width = CHARACTER_WIDTH
        self.height = CHARACTER_HEIGHT
        
        # Core stats (mutable)
        self.age = template.get('starting_age', 25)
        self.health = 100
        self.hunger = MAX_HUNGER
        self.morality = template.get('morality', 5)  # Mutable copy
        
        # Skills (0-100 for each)
        self.skills = {skill_id: 0 for skill_id in SKILLS}
        for skill_id, value in template.get('starting_skills', {}).items():
            self.skills[skill_id] = value
        
        # Inventory
        self.inventory = self._build_initial_inventory(
            template.get('starting_money', 0),
            template.get('starting_wheat', 0)
        )
        
        # Current state
        self._job_name = template.get('starting_job')  # String name, not Job object
        self.allegiance = template.get('starting_allegiance')
        self.home = home_area
        
        # Combat/social state
        self.robbery_target = None
        self.theft_target = None  # Farm cell being targeted for theft
        self.theft_waiting = False  # Waiting at farm for crops to grow
        self.flee_from = None
        self.flee_start_tick = None  # When fleeing started (for timeout)
        self.reported_criminal_to = set()  # Track defenders we've reported current threat to
        self.is_murderer = False
        self.is_thief = False
        self.is_aggressor = False
        
        # Crime knowledge
        self.known_crimes = {}  # {criminal_name: [{'intensity': int, 'allegiance': str/None}, ...]}
        self.unreported_crimes = set()  # {(criminal_name, intensity, crime_allegiance), ...}
        
        # Starvation state
        self.is_starving = False
        self.is_frozen = False  # True when starving + health <= 20
        self.starvation_health_lost = 0
        self.ticks_starving = 0
        
        # Sleep state
        self.is_sleeping = False
        self.camp_position = None  # (x, y) of camp
        
        # Job-specific state
        self.tax_due_tick = None
        self.tax_late_ticks = 0
        self.tax_collection_target = None
        self.tax_paid_this_cycle = False
        self.paid_this_cycle = False
        self.soldier_stopped = False
        self.asked_steward_for_wheat = False
        self.requested_wheat = False
        self.wheat_seek_ticks = 0
        
        # Patrol state (soldiers)
        self.patrol_target = None
        self.patrol_waypoint_idx = None
        self.patrol_direction = 1
        self.patrol_state = None
        self.patrol_wait_ticks = 0
        self.is_patrolling = False
        
        # Movement goal - where this character is trying to go
        # Set by job.decide(), used by movement system
        self.goal = None
        
        # Idle/wandering state
        self.idle_state = 'choosing'
        self.idle_destination = None
        self.idle_wait_ticks = 0
        self.idle_is_idle = False
        
        # Squeeze/pathfinding state
        self.blocked_ticks = 0
        self.squeeze_direction = 0
        
        # Attack animation state
        self.attack_animation_start = None
        self.attack_direction = None
        self.last_attack_tick = 0
        
        # Visual state
        self.facing = 'down'
        self.is_sprinting = False
        
        # Animation tracking
        self._last_anim_x = self.x
        self._last_anim_y = self.y
        
        # Logging flags
        self._idle_logged = False
        self._work_logged = False
    
    # =========================================================================
    # PROPERTIES
    # =========================================================================
    
    @property
    def is_player(self):
        """Whether this character is player-controlled."""
        return self._is_player
    
    @property
    def job(self):
        """Get job name (string)."""
        return self._job_name
    
    @job.setter
    def job(self, value):
        """Set job name (string or None)."""
        self._job_name = value
    
    @property
    def confidence(self):
        """Get confidence trait (static)."""
        return self._confidence
    
    @property
    def cunning(self):
        """Get cunning trait (static)."""
        return self._cunning
    
    @property
    def attractiveness(self):
        """Get attractiveness trait (static)."""
        return self._attractiveness
    
    # =========================================================================
    # DISPLAY HELPERS
    # =========================================================================
    
    def get_display_name(self):
        """Get short display name (first name only)."""
        return self.name.split()[0]
    
    def get_trait(self, trait_name):
        """Get a trait value. Morality is mutable, others are static."""
        if trait_name == 'morality':
            return self.morality
        elif trait_name == 'confidence':
            return self._confidence
        elif trait_name == 'cunning':
            return self._cunning
        elif trait_name == 'attractiveness':
            return self._attractiveness
        return 0
    
    # =========================================================================
    # INVENTORY MANAGEMENT
    # =========================================================================
    
    def _build_initial_inventory(self, money, wheat):
        """Build inventory from starting money and wheat amounts."""
        inventory = [None] * INVENTORY_SLOTS
        slot_idx = 0
        
        # Add money slot if any
        if money > 0 and slot_idx < INVENTORY_SLOTS:
            inventory[slot_idx] = {'type': 'money', 'amount': money}
            slot_idx += 1
        
        # Add wheat slots (stacks of ITEMS["wheat"]["stack_size"])
        remaining_wheat = wheat
        while remaining_wheat > 0 and slot_idx < INVENTORY_SLOTS:
            stack_amount = min(remaining_wheat, ITEMS["wheat"]["stack_size"])
            inventory[slot_idx] = {'type': 'wheat', 'amount': stack_amount}
            remaining_wheat -= stack_amount
            slot_idx += 1
        
        return inventory
    
    def get_item(self, item_type):
        """Get total amount of an item type in inventory."""
        total = 0
        for slot in self.inventory:
            if slot and slot['type'] == item_type:
                total += slot['amount']
        return total
    
    def can_add_item(self, item_type, amount=1):
        """Check if can add this much of an item.
        
        Money: just needs any slot (existing money slot or empty).
        Stackable items (wheat, bread): checks stack space.
        """
        # Money is special - unlimited per slot
        if item_type == 'money':
            for slot in self.inventory:
                if slot is None or slot['type'] == 'money':
                    return True
            return False
        
        # Stackable items
        stack_size = ITEMS.get(item_type, {}).get("stack_size", 1)
        space = 0
        for slot in self.inventory:
            if slot is None:
                space += stack_size
            elif slot['type'] == item_type and slot['amount'] < stack_size:
                space += stack_size - slot['amount']
        return space >= amount
    
    def add_item(self, item_type, amount):
        """Add item to inventory. Returns amount actually added.
        
        Money: adds to existing money slot or creates one.
        Stackable items: fills existing stacks first, then empty slots.
        """
        if amount <= 0:
            return 0
        
        # Money is special - unlimited per slot
        if item_type == 'money':
            # Find existing money slot
            for slot in self.inventory:
                if slot and slot['type'] == 'money':
                    slot['amount'] += amount
                    return amount
            # Find empty slot
            for i, slot in enumerate(self.inventory):
                if slot is None:
                    self.inventory[i] = {'type': 'money', 'amount': amount}
                    return amount
            return 0
        
        # Stackable items
        stack_size = ITEMS.get(item_type, {}).get("stack_size", 1)
        remaining = amount
        
        # First, fill existing stacks of this type
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
        """Remove item from inventory. Returns amount actually removed.
        
        For stackable items, prefers removing from smaller stacks first.
        """
        if amount <= 0:
            return 0
        
        remaining = amount
        
        # Find all slots of this type, sorted by amount (smallest first)
        item_slots = [(i, slot) for i, slot in enumerate(self.inventory) 
                      if slot and slot['type'] == item_type]
        item_slots.sort(key=lambda x: x[1]['amount'])
        
        for i, slot in item_slots:
            to_remove = min(remaining, slot['amount'])
            slot['amount'] -= to_remove
            remaining -= to_remove
            
            if slot['amount'] <= 0:
                self.inventory[i] = None
            
            if remaining <= 0:
                return amount
        
        return amount - remaining
    
    def get_item_space(self, item_type):
        """Get remaining capacity for an item type."""
        # Money has unlimited space if there's any slot
        if item_type == 'money':
            for slot in self.inventory:
                if slot is None or slot['type'] == 'money':
                    return 999999
            return 0
        
        # Stackable items
        stack_size = ITEMS.get(item_type, {}).get("stack_size", 1)
        space = 0
        for slot in self.inventory:
            if slot is None:
                space += stack_size
            elif slot['type'] == item_type and slot['amount'] < stack_size:
                space += stack_size - slot['amount']
        return space
    
    def get_inventory_space(self):
        """Get remaining wheat capacity (for backward compatibility)."""
        return self.get_item_space('wheat')
    
    def is_inventory_full(self):
        """Check if inventory is completely full (no empty slots, all stacks maxed)."""
        for slot in self.inventory:
            if slot is None:
                return False
            item_type = slot['type']
            if item_type == 'money':
                continue  # Money slots are never "full"
            stack_size = ITEMS.get(item_type, {}).get("stack_size", 1)
            if slot['amount'] < stack_size:
                return False
        return True
    
    def transfer_all_items_from(self, other):
        """Transfer all items from another character to self (for looting)."""
        for item_type in ['money', 'wheat', 'bread']:
            amount = other.get_item(item_type)
            if amount > 0:
                other.remove_item(item_type, amount)
                self.add_item(item_type, amount)

    # =========================================================================
    # ACTIONS (used by both player and NPCs)
    # =========================================================================
    
    def eat(self):
        """Consume bread to restore hunger.
        
        Returns:
            dict with 'success' bool and optionally 'recovered_from_starvation'
        """
        result = {'success': False}
        
        if self.get_item('bread') < BREAD_PER_BITE:
            return result
        
        self.remove_item('bread', BREAD_PER_BITE)
        self.hunger = min(MAX_HUNGER, self.hunger + ITEMS["bread"]["hunger_value"])
        result['success'] = True
        
        # Check if recovered from starvation
        if self.hunger > STARVATION_THRESHOLD:
            if self.is_starving or self.is_frozen:
                self.is_starving = False
                self.is_frozen = False
                self.starvation_health_lost = 0
                self.ticks_starving = 0
                result['recovered_from_starvation'] = True
        
        return result
    
    def can_attack(self):
        """Check if character can attack (animation not in progress).
        
        Returns:
            True if can attack
        """
        anim_start = self.attack_animation_start
        if anim_start is not None:
            elapsed = time.time() - anim_start
            if elapsed < ATTACK_ANIMATION_DURATION:
                return False
        return True
    
    def start_attack(self):
        """Begin attack animation.
        
        Returns:
            Attack direction string ('up', 'down', 'left', 'right')
        """
        self.attack_animation_start = time.time()
        attack_dir = self._facing_to_attack_direction(self.facing)
        self.attack_direction = attack_dir
        return attack_dir
    
    def _facing_to_attack_direction(self, facing):
        """Convert facing direction to cardinal attack direction."""
        if facing in ('up', 'up-left', 'up-right'):
            return 'up'
        elif facing in ('down', 'down-left', 'down-right'):
            return 'down'
        elif facing == 'left':
            return 'left'
        elif facing == 'right':
            return 'right'
        # Handle diagonal facings
        if 'left' in facing:
            return 'left'
        if 'right' in facing:
            return 'right'
        return 'down'
    
    def get_attack_direction_vector(self):
        """Get unit direction vector for current facing.
        
        Returns:
            (dx, dy) tuple
        """
        vectors = {
            'up': (0, -1),
            'down': (0, 1),
            'left': (-1, 0),
            'right': (1, 0),
            'up-left': (-0.707, -0.707),
            'up-right': (0.707, -0.707),
            'down-left': (-0.707, 0.707),
            'down-right': (0.707, 0.707),
        }
        return vectors.get(self.facing, (0, 1))
    
    # =========================================================================
    # DICT-LIKE ACCESS (backward compatibility)
    # =========================================================================
    
    def __getitem__(self, key):
        """Allow dict-like read access: char['x'] -> char.x"""
        # Handle special mappings
        if key == 'job':
            return self._job_name
        
        # Try attribute access
        if hasattr(self, key):
            return getattr(self, key)
        
        raise KeyError(f"Character has no attribute '{key}'")
    
    def __setitem__(self, key, value):
        """Allow dict-like write access: char['x'] = 5 -> char.x = 5"""
        if key == 'job':
            self._job_name = value
        elif hasattr(self, key):
            setattr(self, key, value)
        else:
            # Allow setting new attributes for flexibility
            setattr(self, key, value)
    
    def __contains__(self, key):
        """Support 'key in char' checks."""
        if key == 'job':
            return True
        return hasattr(self, key)
    
    def get(self, key, default=None):
        """Dict-like get with default."""
        try:
            return self[key]
        except KeyError:
            return default
    
    def __repr__(self):
        return f"<Character '{self.name}' at ({self.x:.1f}, {self.y:.1f}) job={self._job_name}>"


# =========================================================================
# FACTORY FUNCTION
# =========================================================================

def create_character(name, x, y, home_area=None):
    """
    Create a character from CHARACTER_TEMPLATES.
    
    Args:
        name: Character name (must be key in CHARACTER_TEMPLATES)
        x: Starting x cell coordinate
        y: Starting y cell coordinate
        home_area: Home area name (optional, usually determined by job)
    
    Returns:
        Character instance
    """
    template = CHARACTER_TEMPLATES.get(name)
    if not template:
        raise ValueError(f"Unknown character template: {name}")
    
    return Character(name, template, x, y, home_area)
