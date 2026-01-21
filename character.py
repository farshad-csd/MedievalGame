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
    ATTACK_ANIMATION_DURATION, ATTACK_DAMAGE_TICKS_BEFORE_END,
    UPDATE_INTERVAL,
    STAMINA_DRAIN_PER_TICK, STAMINA_REGEN_PER_TICK, STAMINA_REGEN_DELAY_TICKS, STAMINA_SPRINT_THRESHOLD,
    DEBUG_TRIPLE_PLAYER_HEALTH,
    HEAVY_ATTACK_THRESHOLD_TICKS, HEAVY_ATTACK_CHARGE_TICKS,
    HEAVY_ATTACK_MIN_MULTIPLIER, HEAVY_ATTACK_MAX_MULTIPLIER,
)
from scenario.scenario_characters import CHARACTER_TEMPLATES

# Get bow stats from ITEMS
_BOW = ITEMS["bow"]


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
        self.attack_angle = None  # Precise angle in radians for 360° aiming (player only)
        self.last_attack_tick = 0
        
        # Block state (player only)
        self.is_blocking = False
        
        # Heavy attack state (player only)
        self.heavy_attack_start_tick = None  # Tick when attack button was pressed
        self.heavy_attack_charging = False   # True when past threshold, actively charging

        # Bow draw state (player only)
        self.bow_draw_start_tick = None  # Tick when shoot button was pressed
        self.bow_drawing = False          # True while drawing bow

        # Pending attack state (for delayed damage at animation end)
        # All attacks store their info here, damage is dealt when animation completes
        self.pending_attack = None  # Dict with: {angle, direction, multiplier, target}

        
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
        
        # Inventory - use starting_inventory if provided, else build from money/wheat (legacy)
        starting_inv = template.get('starting_inventory')
        if starting_inv is not None:
            self.inventory = self._build_inventory_from_list(starting_inv)
        else:
            # Legacy fallback for old-style templates
            self.inventory = self._build_initial_inventory(
                template.get('starting_money', 0),
                template.get('starting_wheat', 0)
            )
        
        # Equipment - currently equipped weapon (only one at a time)
        # Stores the inventory slot index of the equipped weapon, or None if nothing equipped
        self.equipped_weapon = None  # int (slot index) or None
        
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
        
        # Ongoing action state (player only - timed actions like harvesting)
        # Structure: {'action': str, 'start_time': float, 'duration': float, 'data': dict}
        # Actions: 'harvest', 'plant', 'chop'
        self.ongoing_action = None
    
    # =========================================================================
    # PROPERTIES AND GETTERS
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
    # SPATIAL QUERIES
    # =========================================================================

    def is_facing_position(self, target_x, target_y):
        """Check if character is roughly facing toward a target position.

        Uses a generous ~53-degree cone in the facing direction.
        Automatically uses correct coordinate system (prevailing for interiors, x/y for exterior).

        Args:
            target_x: Target X in local coords
            target_y: Target Y in local coords

        Returns:
            True if facing toward the target
        """
        # Use zone to determine coordinate system
        if self.zone is not None:
            # Interior - use local/prevailing coords
            px, py = self.prevailing_x, self.prevailing_y
        else:
            # Exterior - use world coords
            px, py = self.x, self.y

        # Direction to target
        dx = target_x - px
        dy = target_y - py

        if abs(dx) < 0.01 and abs(dy) < 0.01:
            return True  # On top of target, always valid

        # Get facing direction vector
        facing_vectors = {
            'up': (0, -1),
            'down': (0, 1),
            'left': (-1, 0),
            'right': (1, 0),
            'up-left': (-0.707, -0.707),
            'up-right': (0.707, -0.707),
            'down-left': (-0.707, 0.707),
            'down-right': (0.707, 0.707),
        }
        fx, fy = facing_vectors.get(self.facing, (0, 1))

        # Normalize direction to target
        dist = math.sqrt(dx*dx + dy*dy)
        dx /= dist
        dy /= dist

        # Dot product gives cosine of angle between vectors
        # cos(45°) ≈ 0.707, cos(53°) ≈ 0.6, cos(60°) = 0.5, cos(90°) = 0
        dot = dx * fx + dy * fy

        # Require ~53 degree cone (dot > 0.6) for tighter targeting
        return dot > 0.6

    # =========================================================================
    # COORDINATE SYSTEM & POSITION
    #
    # Two coordinate systems are supported:
    # 1. World coordinates (x, y properties) - projected position on the world map
    #    - In exterior: same as prevailing coords
    #    - In interior: projected to building's world position
    #
    # 2. Prevailing coordinates (prevailing_x, prevailing_y) - actual position
    #    - In exterior: world coordinates
    #    - In interior: local coordinates within building
    #
    # Usage:
    # - Use x/y GETTERS for cross-zone vision, distance checks, rendering
    # - Use x/y SETTERS only when in exterior (player movement in exterior)
    # - Use prevailing_x/y for all interior movement and NPC movement
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
        """Set X position directly in current coordinate space.

        WARNING: Only use when character is in exterior (zone is None).
        For interior movement, use prevailing_x instead.
        """
        if self.zone is not None:
            # Safety check - catch misuse during development
            import warnings
            warnings.warn(
                f"Setting char.x while in interior '{self.zone}'. "
                f"Use char.prevailing_x instead for interior movement.",
                RuntimeWarning,
                stacklevel=2
            )
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
        """Set Y position directly in current coordinate space.

        WARNING: Only use when character is in exterior (zone is None).
        For interior movement, use prevailing_y instead.
        """
        if self.zone is not None:
            # Safety check - catch misuse during development
            import warnings
            warnings.warn(
                f"Setting char.y while in interior '{self.zone}'. "
                f"Use char.prevailing_y instead for interior movement.",
                RuntimeWarning,
                stacklevel=2
            )
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
    # MOVEMENT MECHANICS (for both player and NPCs)
    # =========================================================================

    def calculate_movement_speed(self, wants_sprint=False, is_blocking=False):
        """Calculate movement speed based on character state.

        Priority: encumbered > blocking > sprint > walk

        Args:
            wants_sprint: Whether trying to sprint
            is_blocking: Whether blocking with shield

        Returns:
            Tuple of (speed, is_actually_sprinting)
        """
        from constants import ENCUMBERED_SPEED, BLOCK_MOVEMENT_SPEED, SPRINT_SPEED, MOVEMENT_SPEED

        # Encumbered overrides everything
        if self.is_over_encumbered():
            return (ENCUMBERED_SPEED, False)

        # Blocking prevents sprinting
        if is_blocking:
            return (BLOCK_MOVEMENT_SPEED, False)

        # Sprint if requested and able
        if wants_sprint:
            return (SPRINT_SPEED, True)

        # Default walk speed
        return (MOVEMENT_SPEED, False)

    def update_backpedal_state(self, move_dx, move_dy):
        """Check if character is backpedaling (moving opposite to facing).

        Updates self['is_backpedaling'] flag based on dot product of movement vs facing.

        Args:
            move_dx: Movement direction X
            move_dy: Movement direction Y

        Returns:
            Dot product of movement and facing vectors (negative = backpedaling)
        """
        import math

        facing_vectors = {
            'right': (1, 0),
            'left': (-1, 0),
            'up': (0, -1),
            'down': (0, 1),
            'up-right': (1, -1),
            'up-left': (-1, -1),
            'down-right': (1, 1),
            'down-left': (-1, 1),
        }

        face_dx, face_dy = facing_vectors.get(self.facing, (0, 1))

        # Normalize movement vector
        move_mag = math.sqrt(move_dx * move_dx + move_dy * move_dy)
        if move_mag > 0:
            move_dx_norm = move_dx / move_mag
            move_dy_norm = move_dy / move_mag
        else:
            move_dx_norm, move_dy_norm = 0, 0

        # Normalize facing vector
        face_mag = math.sqrt(face_dx * face_dx + face_dy * face_dy)
        if face_mag > 0:
            face_dx_norm = face_dx / face_mag
            face_dy_norm = face_dy / face_mag
        else:
            face_dx_norm, face_dy_norm = 0, 1

        # Dot product
        dot = move_dx_norm * face_dx_norm + move_dy_norm * face_dy_norm
        self['is_backpedaling'] = dot < 0

        return dot

    def set_facing_from_angle(self, angle_radians):
        """Set character facing based on an angle in radians.

        Converts precise angle to 8-direction facing (right, down-right, down, etc.).

        Args:
            angle_radians: Angle in radians (0 = right, pi/2 = down)
        """
        import math

        # Convert angle to degrees
        angle_deg = math.degrees(angle_radians)

        # Normalize to [0, 360)
        while angle_deg < 0:
            angle_deg += 360
        while angle_deg >= 360:
            angle_deg -= 360

        # Map to 8 directions (each direction is 45°, centered on angle)
        # Right: -22.5 to 22.5
        # Down-right: 22.5 to 67.5
        # Down: 67.5 to 112.5
        # Down-left: 112.5 to 157.5
        # Left: 157.5 to 202.5
        # Up-left: 202.5 to 247.5
        # Up: 247.5 to 292.5
        # Up-right: 292.5 to 337.5

        if angle_deg < 22.5 or angle_deg >= 337.5:
            self.facing = 'right'
        elif angle_deg < 67.5:
            self.facing = 'down-right'
        elif angle_deg < 112.5:
            self.facing = 'down'
        elif angle_deg < 157.5:
            self.facing = 'down-left'
        elif angle_deg < 202.5:
            self.facing = 'left'
        elif angle_deg < 247.5:
            self.facing = 'up-left'
        elif angle_deg < 292.5:
            self.facing = 'up'
        else:
            self.facing = 'up-right'

    # =========================================================================
    # INVENTORY MANAGEMENT
    # =========================================================================
    
    def _build_initial_inventory(self, money, wheat):
        """Build inventory from starting money and wheat amounts (legacy method)."""
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
    
    def _build_inventory_from_list(self, inv_list):
        """Build inventory from a list of item dicts.
        
        Args:
            inv_list: List of item dicts like [{'type': 'gold', 'amount': 50}, None, ...]
                     Can be shorter than INVENTORY_SLOTS (remaining slots will be None)
        
        Returns:
            List of INVENTORY_SLOTS length with items copied from inv_list
        """
        inventory = [None] * INVENTORY_SLOTS
        
        for i, item in enumerate(inv_list):
            if i >= INVENTORY_SLOTS:
                break
            if item is not None:
                # Copy the dict so we don't share references with the template
                inventory[i] = {'type': item['type'], 'amount': item['amount']}
        
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
    
    def get_encumbrance(self):
        """Calculate total weight of all carried items.
        
        Returns:
            Float representing total weight of inventory
        """
        total_weight = 0.0
        for slot in self.inventory:
            if slot is None:
                continue
            item_type = slot.get('type', '')
            amount = slot.get('amount', 0)
            item_info = ITEMS.get(item_type, {})
            weight_per_unit = item_info.get('weight', 0)
            total_weight += weight_per_unit * amount
        return total_weight
    
    def is_over_encumbered(self):
        """Check if character is at or over max encumbrance.
        
        Returns:
            True if encumbrance >= MAX_ENCUMBRANCE
        """
        from constants import MAX_ENCUMBRANCE
        return self.get_encumbrance() >= MAX_ENCUMBRANCE
    
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

    # =========================================================================
    # BASIC ACTIONS (used by both player and NPCs)
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

    def start_ongoing_action(self, action_type, duration, data=None):
        """Start an ongoing action (freezes player until complete or cancelled).
        
        Args:
            action_type: Type of action ('harvest', 'plant', 'chop')
            duration: Duration in seconds (real-time)
            data: Optional dict with action-specific data (e.g., cell coords)
            
        Returns:
            True if action started, False if already doing an action
        """
        if self.ongoing_action is not None:
            return False
        
        self.ongoing_action = {
            'action': action_type,
            'start_time': time.time(),
            'duration': duration,
            'data': data or {}
        }
        return True
    
    def cancel_ongoing_action(self):
        """Cancel the current ongoing action.
        
        Returns:
            The action that was cancelled, or None if no action was in progress
        """
        if self.ongoing_action is None:
            return None
        
        cancelled = self.ongoing_action
        self.ongoing_action = None
        return cancelled
    
    def get_ongoing_action_progress(self):
        """Get the progress of the current ongoing action.
        
        Returns:
            Float from 0.0 to 1.0 representing progress, or None if no action
        """
        if self.ongoing_action is None:
            return None
        
        elapsed = time.time() - self.ongoing_action['start_time']
        progress = elapsed / self.ongoing_action['duration']
        return min(1.0, max(0.0, progress))
    
    def is_ongoing_action_complete(self):
        """Check if the current ongoing action is complete.
        
        Returns:
            True if complete (progress >= 1.0), False otherwise or if no action
        """
        progress = self.get_ongoing_action_progress()
        if progress is None:
            return False
        return progress >= 1.0
    
    def has_ongoing_action(self):
        """Check if player has an ongoing action in progress.

        Returns:
            True if an ongoing action is in progress
        """
        return self.ongoing_action is not None


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
    # COMBAT SYSTEM (basic attacks)
    # =========================================================================

    def get_strongest_weapon_slot(self):
        """Find the inventory slot with the strongest weapon (melee or ranged).

        Returns:
            Slot index of strongest weapon, or None if no weapons in inventory
        """
        best_slot = None
        best_damage = -1

        for i, slot in enumerate(self.inventory):
            if slot is None:
                continue

            item_type = slot.get('type', '')
            item_info = ITEMS.get(item_type, {})

            # Consider both melee and ranged weapons
            weapon_type = item_info.get('weapon_type')
            if weapon_type not in ('melee', 'ranged'):
                continue

            # Calculate average damage for this weapon
            damage_min = item_info.get('base_damage_min', 0)
            damage_max = item_info.get('base_damage_max', 0)
            avg_damage = (damage_min + damage_max) / 2.0

            if avg_damage > best_damage:
                best_damage = avg_damage
                best_slot = i

        return best_slot

    def equip_strongest_weapon(self):
        """Equip the strongest weapon (melee or ranged) in inventory.

        Returns:
            True if a weapon was equipped, False if no weapons available
        """
        slot = self.get_strongest_weapon_slot()
        if slot is not None:
            self.equipped_weapon = slot
            return True
        else:
            self.equipped_weapon = None
            return False

    def get_equipped_weapon_type(self):
        """Get the weapon type of the currently equipped weapon.

        Returns:
            'melee', 'ranged', or None if no weapon equipped
        """
        if self.equipped_weapon is None:
            return None

        if self.equipped_weapon < 0 or self.equipped_weapon >= len(self.inventory):
            return None

        item = self.inventory[self.equipped_weapon]
        if item is None:
            return None

        item_type = item.get('type', '')
        item_info = ITEMS.get(item_type, {})
        return item_info.get('weapon_type')

    def get_weapon_stats(self):
        """Get the weapon stats for this character's equipped weapon.

        Returns weapon stats dict from equipped melee weapon, or FISTS if unarmed.

        Returns:
            Dict with weapon stats (from ITEMS entry or FISTS constant)
        """
        from constants import FISTS

        if self.equipped_weapon is not None:
            if 0 <= self.equipped_weapon < len(self.inventory):
                item = self.inventory[self.equipped_weapon]
                if item is not None:
                    item_type = item.get('type', '')
                    item_info = ITEMS.get(item_type, {})
                    # Only use if it's a melee weapon
                    if item_info.get('weapon_type') == 'melee':
                        return item_info

        # Fall back to fists (unarmed combat)
        return FISTS

    def get_weapon_expected_damage(self, weapon_type):
        """Calculate the expected average damage for a weapon type.

        For melee weapons: returns average base damage (or fists if no melee weapon equipped).
        For ranged weapons: returns average base damage (or 0 if no ranged weapon equipped).
        For fists: returns fist damage.

        Args:
            weapon_type: 'melee', 'ranged', or None for fists

        Returns:
            Expected damage value
        """
        from constants import FISTS

        if weapon_type is None:
            # Fists
            return (FISTS['base_damage_min'] + FISTS['base_damage_max']) / 2.0

        # Check if we have an equipped weapon of this type
        if self.equipped_weapon is not None:
            if 0 <= self.equipped_weapon < len(self.inventory):
                item = self.inventory[self.equipped_weapon]
                if item is not None:
                    item_type = item.get('type', '')
                    item_info = ITEMS.get(item_type, {})

                    # If equipped weapon matches the requested type, return its damage
                    if item_info.get('weapon_type') == weapon_type:
                        damage_min = item_info.get('base_damage_min', 0)
                        damage_max = item_info.get('base_damage_max', 0)
                        return (damage_min + damage_max) / 2.0

        # No weapon of this type equipped
        if weapon_type == 'melee':
            # Fall back to fists for melee
            return (FISTS['base_damage_min'] + FISTS['base_damage_max']) / 2.0
        else:
            # No ranged weapon available
            return 0.0

    def can_attack(self):
        """Check if character can attack (animation not in progress, not blocking).
        
        Returns:
            True if can attack
        """
        # Can't attack while blocking
        if self.is_blocking:
            return False
        
        anim_start = self.attack_animation_start
        if anim_start is not None:
            elapsed = time.time() - anim_start
            if elapsed < ATTACK_ANIMATION_DURATION:
                return False
        return True
    
    def start_attack(self, angle=None, damage_multiplier=1.0, target=None):
        """Begin attack animation and store pending attack info.
        
        The attack damage will be dealt when the animation completes.
        
        Args:
            angle: Optional precise attack angle in radians (for 360° aiming).
                   If None, uses 8-direction facing (for NPCs).
            damage_multiplier: Damage multiplier for heavy attacks (default 1.0)
            target: Optional specific target for NPC melee attacks
        
        Returns:
            Attack direction string ('up', 'down', 'left', 'right', etc.)
        """
        self.attack_animation_start = time.time()
        attack_dir = self._facing_to_attack_direction(self.facing)
        self.attack_direction = attack_dir
        self.attack_angle = angle  # None for NPCs, radians for player
        
        # Store pending attack info - damage dealt when animation completes
        self.pending_attack = {
            'angle': angle,
            'direction': attack_dir,
            'multiplier': damage_multiplier,
            'target': target,  # None for player AOE, Character for NPC targeted
        }
        
        return attack_dir
    
    def has_pending_attack(self):
        """Check if there's a pending attack waiting for animation to complete."""
        return self.pending_attack is not None
    
    def is_attack_animation_complete(self):
        """Check if the attack animation has reached the damage point.
        
        Damage registers ATTACK_DAMAGE_TICKS_BEFORE_END ticks before the
        animation visually completes. This allows fine-tuning when the
        hit registers relative to the swing animation.
        
        Returns:
            True if animation has reached damage point (or no animation in progress)
        """
        if self.attack_animation_start is None:
            return True
        elapsed = time.time() - self.attack_animation_start
        # Convert ticks to seconds: ticks * (ms_per_tick / 1000)
        damage_offset = ATTACK_DAMAGE_TICKS_BEFORE_END * (UPDATE_INTERVAL / 1000.0)
        damage_time = ATTACK_ANIMATION_DURATION - damage_offset
        return elapsed >= damage_time
    
    def get_and_clear_pending_attack(self):
        """Get pending attack info and clear it.
        
        Returns:
            Dict with {angle, direction, multiplier, target} or None
        """
        attack = self.pending_attack
        self.pending_attack = None
        return attack
    
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
    # HEAVY ATTACK SYSTEM (Player melee charged attacks)
    # =========================================================================

    def start_heavy_attack_hold(self, current_tick):
        """Called when attack button is first pressed. Records the tick.
        
        Args:
            current_tick: Current game tick
        """
        if self.heavy_attack_start_tick is None:
            self.heavy_attack_start_tick = current_tick
            self.heavy_attack_charging = False
    
    def update_heavy_attack(self, current_tick):
        """Update heavy attack state based on how long button has been held.
        
        Args:
            current_tick: Current game tick
            
        Returns:
            True if now in charging state (past threshold)
        """
        if self.heavy_attack_start_tick is None:
            return False
        
        ticks_held = current_tick - self.heavy_attack_start_tick
        
        # Check if past threshold
        if ticks_held >= HEAVY_ATTACK_THRESHOLD_TICKS:
            self.heavy_attack_charging = True
            return True
        
        return False
    
    def get_heavy_attack_progress(self, current_tick):
        """Get the charge progress as a fraction (0.0 to 1.0).
        
        Only returns a value if past the threshold and actively charging.
        
        Args:
            current_tick: Current game tick
            
        Returns:
            Float from 0.0 to 1.0, or None if not charging
        """
        if not self.heavy_attack_charging or self.heavy_attack_start_tick is None:
            return None
        
        ticks_held = current_tick - self.heavy_attack_start_tick
        charge_ticks = ticks_held - HEAVY_ATTACK_THRESHOLD_TICKS
        
        if charge_ticks < 0:
            return 0.0
        
        progress = charge_ticks / HEAVY_ATTACK_CHARGE_TICKS
        return min(1.0, max(0.0, progress))
    
    def get_heavy_attack_multiplier(self, current_tick):
        """Get the damage multiplier based on charge progress.
        
        Args:
            current_tick: Current game tick
            
        Returns:
            Damage multiplier (1.001 to 2.0), or 1.0 if not charging
        """
        progress = self.get_heavy_attack_progress(current_tick)
        if progress is None:
            return 1.0
        
        # Linear interpolation from MIN to MAX
        return HEAVY_ATTACK_MIN_MULTIPLIER + progress * (HEAVY_ATTACK_MAX_MULTIPLIER - HEAVY_ATTACK_MIN_MULTIPLIER)
    
    def release_heavy_attack(self, current_tick):
        """Called when attack button is released.
        
        Args:
            current_tick: Current game tick
            
        Returns:
            Tuple of (was_heavy_attack, damage_multiplier)
            was_heavy_attack is True if this was a charged attack (past threshold)
        """
        if self.heavy_attack_start_tick is None:
            return (False, 1.0)
        
        ticks_held = current_tick - self.heavy_attack_start_tick
        was_charging = self.heavy_attack_charging
        multiplier = self.get_heavy_attack_multiplier(current_tick)
        
        # Reset state
        self.heavy_attack_start_tick = None
        self.heavy_attack_charging = False
        
        # If we were past threshold, this was a heavy attack
        if was_charging:
            return (True, multiplier)
        else:
            # Quick tap - normal attack
            return (False, 1.0)
    
    def cancel_heavy_attack(self):
        """Cancel heavy attack charge without attacking.
        
        Returns:
            True if there was an attack to cancel
        """
        was_charging = self.heavy_attack_start_tick is not None
        self.heavy_attack_start_tick = None
        self.heavy_attack_charging = False
        return was_charging
    
    def is_charging_heavy_attack(self):
        """Check if currently charging a heavy attack.
        
        Returns:
            True if charging (past threshold)
        """
        return self.heavy_attack_charging
    
    # =========================================================================
    # BOW DRAW SYSTEM (Player ranged attacks)
    # =========================================================================

    def start_bow_draw(self, current_tick):
        """Called when shoot button is first pressed. Records the tick.
        
        Args:
            current_tick: Current game tick
        """
        if self.bow_draw_start_tick is None:
            self.bow_draw_start_tick = current_tick
            self.bow_drawing = True
    
    def update_bow_draw(self, current_tick):
        """Update bow draw state (called each frame while button held).
        
        Args:
            current_tick: Current game tick
            
        Returns:
            True if currently drawing
        """
        return self.bow_drawing
    
    def get_bow_draw_progress(self, current_tick):
        """Get the draw progress as a fraction (0.0 to 1.0).
        
        Unlike heavy attack, bow draw starts filling immediately (no threshold).
        
        Args:
            current_tick: Current game tick
            
        Returns:
            Float from 0.0 to 1.0, or None if not drawing
        """
        if not self.bow_drawing or self.bow_draw_start_tick is None:
            return None
        
        ticks_held = current_tick - self.bow_draw_start_tick
        progress = ticks_held / _BOW["draw_time_ticks"]
        return min(1.0, max(0.0, progress))
    
    def release_bow_draw(self, current_tick):
        """Called when shoot button is released.
        
        Args:
            current_tick: Current game tick
            
        Returns:
            Draw progress (0.0 to 1.0) at time of release
        """
        if self.bow_draw_start_tick is None:
            return 0.0
        
        progress = self.get_bow_draw_progress(current_tick)
        if progress is None:
            progress = 0.0
        
        # Reset state
        self.bow_draw_start_tick = None
        self.bow_drawing = False
        
        return progress
    
    def cancel_bow_draw(self):
        """Cancel bow draw without firing.
        
        Returns:
            True if there was a draw to cancel
        """
        was_drawing = self.bow_draw_start_tick is not None
        self.bow_draw_start_tick = None
        self.bow_drawing = False
        return was_drawing
    
    def is_drawing_bow(self):
        """Check if currently drawing bow.
        
        Returns:
            True if drawing
        """
        return self.bow_drawing
    
    def get_bow_spread_degrees(self, current_tick):
        """Get the current accuracy spread angle based on draw progress.
        
        At zero draw, spread is max (spread_max_degrees from bow stats).
        At full draw, spread is min (spread_min_degrees from bow stats).
        Spread decreases linearly with draw progress.
        
        Args:
            current_tick: Current game tick
            
        Returns:
            Spread angle in degrees (one side of center), or None if not drawing
        """
        progress = self.get_bow_draw_progress(current_tick)
        if progress is None:
            return None
        
        # Linear interpolation from max to min spread
        spread_max = _BOW["spread_max_degrees"]
        spread_min = _BOW["spread_min_degrees"]
        spread = spread_max - progress * (spread_max - spread_min)
        return spread
    

    # =========================================================================
    # STAMINA SYSTEM (Skyrim-style sprint mechanics)
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
