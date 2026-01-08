# character.py - Character class for all game characters
"""
Character class that encapsulates all character state and behavior.

Design:
- All characters (including player) are Character instances
- Jobs are stored as strings (e.g., 'Farmer', 'Soldier'); behavior is in jobs.py
- Player is just a Character with is_player=True (enables input controls)
- Implements dict-like access for backward compatibility with existing code

Memory System:
- Each character has a list of memories (things they've seen, experienced, learned)
- Memories replace scattered flags like robbery_target, flee_from, known_crimes
- Current intent (what to do this tick) is derived from memories

Memory Types:
- 'crime': witnessed someone commit a crime
- 'attacked_by': someone attacked me
- 'helped_by': someone helped me
- 'home_of': I know where someone lives
- 'sighting': I saw someone at a location
- 'location': I know about a place (market, farm, camp, etc.)
- 'object': I know about an object (barrel, bed, etc.) - future use
"""

import time  # Used for attack animation timing (visual only, doesn't scale with game speed)
import math
from constants import (
    MAX_HUNGER, MAX_FATIGUE, MAX_STAMINA, INVENTORY_SLOTS, ITEMS, SKILLS,
    CHARACTER_WIDTH, CHARACTER_HEIGHT,
    BREAD_PER_BITE, STARVATION_THRESHOLD,
    ATTACK_ANIMATION_DURATION, ATTACK_COOLDOWN_TICKS,
    STAMINA_DRAIN_PER_TICK, STAMINA_REGEN_PER_TICK, STAMINA_REGEN_DELAY_TICKS, STAMINA_SPRINT_THRESHOLD,
    DEBUG_TRIPLE_PLAYER_HEALTH
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

        # Position (float-based for smooth movement)
        # _prevailing_x/_prevailing_y store actual position (interior coords when inside, world coords when outside)
        # Characters spawn at CENTER of their starting cell
        self._prevailing_x = float(x) + 0.5
        self._prevailing_y = float(y) + 0.5
        # Velocity for continuous movement (cells per second)
        self.vx = 0.0
        self.vy = 0.0
        # Hitbox dimensions
        self.width = CHARACTER_WIDTH
        self.height = CHARACTER_HEIGHT
        # Visual state
        self.facing = 'down'
        self.is_sprinting = False
        
        # Zone system for interiors
        # None = exterior world, "house_name" = inside that building's interior
        self.zone = None
        
        # Interior projection parameters (set when entering interior)
        # These allow computing world coordinates without needing InteriorManager reference
        self._interior_proj_x = 0      # exterior_x of building
        self._interior_proj_y = 0      # exterior_y of building
        self._interior_scale_x = 1.0   # exterior_width / interior_width
        self._interior_scale_y = 1.0   # exterior_height / interior_height
        # Animation tracking
        self._last_anim_x = self._prevailing_x
        self._last_anim_y = self._prevailing_y
        # Attack animation state
        self.attack_animation_start = None
        self.attack_direction = None
        self.last_attack_tick = 0
        

        
        # Core stats (mutable)
        self.age = template.get('starting_age', 25)
        self.health = 300 if (self._is_player and DEBUG_TRIPLE_PLAYER_HEALTH) else 100
        self.hunger = MAX_HUNGER
        self.fatigue = MAX_FATIGUE
        self.stamina = MAX_STAMINA
        self.morality = template.get('morality', 5)  # Mutable copy
        
        # Stamina system state (Skyrim-style)
        self._last_sprint_tick = 0  # Tick when sprinting last stopped
        self._stamina_depleted = False  # True when stamina hit 0 (must wait for threshold)
        
        # Starvation state
        self.is_starving = False
        self.is_frozen = False  # True when starving + health <= 20
        self.starvation_health_lost = 0
        self.ticks_starving = 0

        # Sleep state
        self.is_sleeping = False
        self.camp_position = None  # (x, y) of camp

        # Static traits (from template, don't change)
        self._attractiveness = template.get('attractiveness', 5)
        self._confidence = template.get('confidence', 5)
        self._cunning = template.get('cunning', 5)

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
        
        # =====================================================================
        # MEMORY SYSTEM
        # =====================================================================
        # List of memory dicts - see add_memory() for structure
        self.memories = []
        
        # Current intent - what this character has decided to do THIS tick
        # Structure: {'action': str, 'target': Any, 'reason': memory or str, 'started_tick': int}
        # Actions: 'attack', 'flee', 'follow', 'goto', 'stay_near', None
        self.intent = None

        # Movement goal - where this character is trying to go
        # Set by job.decide(), used by movement system
        self.goal = None
        self.goal_zone = None  # None = exterior, "interior_name" = inside that building
        
        
        # Theft state (ongoing goal-directed behavior, not a reaction)
        self.theft_target = None  # Farm cell (x,y) being targeted
        self.theft_waiting = False  # Waiting at farm for crops
        self.theft_start_tick = None  # When attempt started
        

        # Idle/wandering state
        self.idle_state = 'choosing'
        self.idle_destination = None
        self.idle_wait_ticks = 0
        self.idle_is_idle = False

        # Squeeze/pathfinding state
        self.blocked_ticks = 0
        self.squeeze_direction = 0

        
        # Patrol state (soldiers)
        self.patrol_target = None
        self.patrol_waypoint_idx = None
        self.patrol_direction = 1
        self.patrol_state = None
        self.patrol_wait_ticks = 0
        self.is_patrolling = False
    
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
    
    def get_display_name(self):
        """Get short display name (first name only)."""
        return self.name.split()[0]
    
    # =========================================================================
    # POSITION PROPERTIES
    # x and y always return world coordinates (projected when in interior)
    # prevailing_x and prevailing_y return actual stored position (interior coords when inside)
    # =========================================================================
    
    @property
    def x(self):
        """Get world X coordinate.
        
        When in exterior: returns local position directly
        When in interior: returns projected world position
        """
        if self.zone is None:
            return self._prevailing_x
        return self._interior_proj_x + (self._prevailing_x * self._interior_scale_x)
    
    @x.setter
    def x(self, value):
        """Set local X position."""
        self._prevailing_x = value
    
    @property
    def y(self):
        """Get world Y coordinate.
        
        When in exterior: returns local position directly
        When in interior: returns projected world position
        """
        if self.zone is None:
            return self._prevailing_y
        return self._interior_proj_y + (self._prevailing_y * self._interior_scale_y)
    
    @y.setter
    def y(self, value):
        """Set local Y position."""
        self._prevailing_y = value
    
    @property
    def prevailing_x(self):
        """Get actual stored X position (interior coords when inside, world coords when outside)."""
        return self._prevailing_x
    
    @prevailing_x.setter
    def prevailing_x(self, value):
        """Set local X position."""
        self._prevailing_x = value
    
    @property
    def prevailing_y(self):
        """Get actual stored Y position (interior coords when inside, world coords when outside)."""
        return self._prevailing_y
    
    @prevailing_y.setter
    def prevailing_y(self, value):
        """Set local Y position."""
        self._prevailing_y = value
    
    def enter_interior(self, interior):
        """
        Move character into a building interior.
        
        Args:
            interior: Interior object to enter
        """
        self.zone = interior.name
        
        # Store projection parameters for on-demand world coordinate calculation
        self._interior_proj_x = interior.exterior_x
        self._interior_proj_y = interior.exterior_y
        self._interior_scale_x = interior.scale_x
        self._interior_scale_y = interior.scale_y
        
        # Move to entry position (door) - sets local position
        entry_x, entry_y = interior.get_entry_position()
        self._prevailing_x = entry_x
        self._prevailing_y = entry_y
    
    def exit_interior(self, interior):
        """
        Move character out of a building interior to exterior.
        
        Args:
            interior: Interior object to exit from
        """
        # Get exit position in world coordinates
        exit_x, exit_y = interior.get_exit_position()
        
        # Clear zone and projection params FIRST
        self.zone = None
        self._interior_proj_x = 0
        self._interior_proj_y = 0
        self._interior_scale_x = 1.0
        self._interior_scale_y = 1.0
        
        # Move to exit position (now zone is None, so this sets world position directly)
        self._prevailing_x = exit_x
        self._prevailing_y = exit_y
    
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
    # MEMORY SYSTEM
    # =========================================================================
    
    def add_memory(self, memory_type, subject, tick, location=None, intensity=5,
                   source='witnessed', reported=False, **details):
        """Add a memory to this character.
        
        Args:
            memory_type: Type of memory ('crime', 'attacked_by', 'helped_by', 
                        'home_of', 'sighting', 'location', 'object')
            subject: What/who this memory is about (Character, position tuple, 
                    object ref, or string)
            tick: Game tick when this was learned
            location: (x, y) where it happened/was learned (optional)
            intensity: How significant (1-20), affects reaction range
            source: How we learned this ('witnessed', 'told_by', 'experienced', 'discovered')
            reported: Whether we've told someone about this (for crimes)
            **details: Type-specific extra data
        
        Returns:
            The created memory dict
        """
        memory = {
            'type': memory_type,
            'subject': subject,
            'tick': tick,
            'location': location,
            'intensity': intensity,
            'source': source,
            'reported': reported,
            'details': details
        }
        self.memories.append(memory)
        return memory
    
    def get_memories(self, memory_type=None, subject=None, source=None, 
                     unreported_only=False, min_intensity=None):
        """Query memories with optional filters.
        
        Args:
            memory_type: Filter by type (str or list of str)
            subject: Filter by subject (exact match)
            source: Filter by source ('witnessed', 'told_by', etc.)
            unreported_only: Only return memories with reported=False
            min_intensity: Only return memories with intensity >= this
        
        Returns:
            List of matching memory dicts
        """
        results = self.memories
        
        if memory_type is not None:
            if isinstance(memory_type, str):
                results = [m for m in results if m['type'] == memory_type]
            else:
                # List of types
                results = [m for m in results if m['type'] in memory_type]
        
        if subject is not None:
            results = [m for m in results if m['subject'] is subject]
        
        if source is not None:
            results = [m for m in results if m.get('source') == source]
        
        if unreported_only:
            results = [m for m in results if not m.get('reported', False)]
        
        if min_intensity is not None:
            results = [m for m in results if m.get('intensity', 0) >= min_intensity]
        
        return results
    
    def has_memory_of(self, memory_type, subject):
        """Check if we have any memory of this type about this subject."""
        return len(self.get_memories(memory_type=memory_type, subject=subject)) > 0
    
    def get_unreported_crimes(self):
        """Get all crime memories that haven't been reported yet."""
        return self.get_memories(memory_type='crime', unreported_only=True)
    
    def get_unreported_crimes_about(self, criminal):
        """Get unreported crime memories about a specific criminal."""
        return self.get_memories(memory_type='crime', subject=criminal, unreported_only=True)
    
    def forget_memories_about(self, subject):
        """Remove all memories about a subject (e.g., when they die)."""
        self.memories = [m for m in self.memories if m['subject'] is not subject]
        
        # Clear intent if it was about this subject
        if self.intent and self.intent.get('target') is subject:
            self.intent = None
    
    def clear_intent(self):
        """Clear current intent."""
        self.intent = None
        self['face_target'] = None  # Also clear face target
    
    def set_intent(self, action, target, reason=None, started_tick=None):
        """Set current intent.
        
        Args:
            action: 'attack', 'flee', 'follow', 'goto', 'stay_near'
            target: Character, position, or other target
            reason: Memory or string explaining why
            started_tick: When this intent started (for timeouts)
        """
        self.intent = {
            'action': action,
            'target': target,
            'reason': reason,
            'started_tick': started_tick
        }
    
    def get_active_attacker(self, current_tick, alive_characters, max_ticks_ago=50, max_distance=8.0):
        """Find someone actively attacking me right now.
        
        Checks for recent attacked_by memories where attacker is still nearby.
        
        Args:
            current_tick: Current game tick
            alive_characters: List of alive characters
            max_ticks_ago: How recent the attack must be
            max_distance: How close attacker must still be
        
        Returns:
            Attacker Character or None
        """
        alive_set = set(alive_characters)
        
        for m in self.get_memories(memory_type='attacked_by'):
            # Recent?
            if current_tick - m['tick'] > max_ticks_ago:
                continue
            
            attacker = m['subject']
            
            # Still alive?
            if attacker not in alive_set:
                continue
            
            # Still nearby?
            dist = math.sqrt((self.x - attacker.x)**2 + (self.y - attacker.y)**2)
            if dist < max_distance:
                return attacker
        
        return None
    
    def has_committed_crime(self, crime_type=None):
        """Check if this character has committed a crime (has crime memory about self).
        
        Note: This checks our OWN memory of committing crimes, not what others know.
        Use this for self-knowledge (e.g., "I know I'm a thief").
        
        For what others know, check their memories.
        """
        # We store self-knowledge of our own crimes as 'committed_crime' type
        memories = self.get_memories(memory_type='committed_crime')
        if crime_type:
            memories = [m for m in memories if m['details'].get('crime_type') == crime_type]
        return len(memories) > 0
    
    # =========================================================================
    # INVENTORY MANAGEMENT
    # =========================================================================
    
    def _build_initial_inventory(self, money, wheat):
        """Build inventory from starting money and wheat amounts."""
        inventory = [None] * INVENTORY_SLOTS
        slot_idx = 0
        
        # Add money slot if any
        if money > 0 and slot_idx < INVENTORY_SLOTS:
            inventory[slot_idx] = {'type': 'gold', 'amount': money}
            slot_idx += 1
        
        # Add wheat slots (stacks of ITEMS["wheat"]["stack_size"])
        remaining_wheat = wheat
        stack_size = ITEMS["wheat"]["stack_size"]
        while remaining_wheat > 0 and slot_idx < INVENTORY_SLOTS:
            stack = min(remaining_wheat, stack_size)
            inventory[slot_idx] = {'type': 'wheat', 'amount': stack}
            remaining_wheat -= stack
            slot_idx += 1
        
        return inventory
    
    def get_item(self, item_type):
        """Get total amount of an item type across all inventory slots."""
        total = 0
        for slot in self.inventory:
            if slot and slot['type'] == item_type:
                total += slot['amount']
        return total
    
    def can_add_item(self, item_type, amount):
        """Check if inventory can hold this amount of an item."""
        return self.get_item_space(item_type) >= amount
    
    def add_item(self, item_type, amount):
        """Add item to inventory. Returns amount actually added."""
        if amount <= 0:
            return 0
        
        # Money handling - unlimited stacking
        if item_type == 'gold':
            for slot in self.inventory:
                if slot and slot['type'] == 'gold':
                    slot['amount'] += amount
                    return amount
            # No money slot exists, create one
            for i, slot in enumerate(self.inventory):
                if slot is None:
                    self.inventory[i] = {'type': 'gold', 'amount': amount}
                    return amount
            return 0  # No space
        
        # Stackable items
        stack_size = ITEMS.get(item_type, {}).get("stack_size", 1)
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
        if item_type == 'gold':
            for slot in self.inventory:
                if slot is None or slot['type'] == 'gold':
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
            if item_type == 'gold':
                continue  # Money slots are never "full"
            stack_size = ITEMS.get(item_type, {}).get("stack_size", 1)
            if slot['amount'] < stack_size:
                return False
        return True
    
    def transfer_all_items_from(self, other):
        """Transfer all items from another character to self (for looting)."""
        for item_type in ['gold', 'wheat', 'bread']:
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
    
    # =========================================================================
    # STAMINA SYSTEM (Skyrim-style sprinting)
    # =========================================================================
    
    def can_start_sprint(self):
        """Check if character can START sprinting.
        
        Requires stamina above threshold. Once sprinting, can continue
        until stamina hits 0 (handled by drain_stamina_sprint).
        
        Returns:
            True if can start sprinting
        """
        # Can't sprint if frozen/dying
        if self.is_frozen or self.health <= 0:
            return False
        
        # If stamina was depleted, must wait for it to recover above threshold
        if self._stamina_depleted:
            if self.stamina >= STAMINA_SPRINT_THRESHOLD:
                self._stamina_depleted = False
            else:
                return False
        
        return self.stamina > 0
    
    def can_continue_sprint(self):
        """Check if character can CONTINUE sprinting.
        
        Can continue as long as stamina > 0.
        
        Returns:
            True if can continue sprinting
        """
        if self.is_frozen or self.health <= 0:
            return False
        return self.stamina > 0
    
    def drain_stamina_sprint(self, current_tick):
        """Drain stamina while sprinting. Called once per tick.
        
        Args:
            current_tick: Current game tick
            
        Returns:
            True if still have stamina, False if depleted
        """
        self.stamina = max(0, self.stamina - STAMINA_DRAIN_PER_TICK)
        
        # Track when we last sprinted (for regen delay)
        self._last_sprint_tick = current_tick
        
        if self.stamina <= 0:
            self._stamina_depleted = True
            return False
        return True
    
    def regenerate_stamina(self, current_tick):
        """Regenerate stamina when not sprinting. Called once per tick.
        
        Only regenerates if enough ticks have passed since last sprint
        (simulates Skyrim's brief pause before regen kicks in).
        
        Args:
            current_tick: Current game tick
            
        Returns:
            Amount regenerated
        """
        # Check if we've waited long enough since sprinting
        ticks_since_sprint = current_tick - self._last_sprint_tick
        if ticks_since_sprint < STAMINA_REGEN_DELAY_TICKS:
            return 0
        
        # Already full
        if self.stamina >= MAX_STAMINA:
            return 0
        
        old_stamina = self.stamina
        self.stamina = min(MAX_STAMINA, self.stamina + STAMINA_REGEN_PER_TICK)
        
        return self.stamina - old_stamina
    
    def get_stamina_fraction(self):
        """Get stamina as a fraction (0-1) for UI display."""
        return self.stamina / MAX_STAMINA
    
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
        """Convert facing direction to attack direction.
        
        Now supports all 8 directions for diagonal attacks.
        """
        valid_directions = ('up', 'down', 'left', 'right', 
                           'up-left', 'up-right', 'down-left', 'down-right')
        if facing in valid_directions:
            return facing
        return 'down'  # Fallback
    
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