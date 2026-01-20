# game_logic.py - All game logic: AI, combat, trading, movement
"""
This module contains all game logic that operates on GameState.
It does NOT hold any state itself - all state is in GameState.
It does NOT contain any rendering code.
"""

import random
import math
import time
from collections import deque
from constants import (
    DIRECTIONS, ITEMS, FISTS,
    MAX_HUNGER, HUNGER_DECAY, HUNGER_CRITICAL, HUNGER_CHANCE_THRESHOLD,
    STARVATION_THRESHOLD, STARVATION_DAMAGE, STARVATION_MORALITY_INTERVAL,
    STARVATION_MORALITY_CHANCE, STARVATION_FREEZE_HEALTH,
    INVENTORY_SLOTS,
    FARM_CELL_YIELD,
    FARM_CELL_HARVEST_INTERVAL, FARM_HARVEST_TIME, FARM_REPLANT_TIME,
    TRADE_COOLDOWN,
    STEWARD_TAX_INTERVAL, STEWARD_TAX_AMOUNT, SOLDIER_WHEAT_PAYMENT, TAX_GRACE_PERIOD,
    ALLEGIANCE_WHEAT_TIMEOUT, TICKS_PER_DAY, TICKS_PER_YEAR,
    CRIME_INTENSITY_MURDER, CRIME_INTENSITY_ASSAULT, CRIME_INTENSITY_THEFT,
    THEFT_PATIENCE_TICKS, THEFT_COOLDOWN_TICKS,
    FLEE_DISTANCE_DIVISOR,
    SLEEP_START_FRACTION,
    MOVEMENT_SPEED, SPRINT_SPEED, ADJACENCY_DISTANCE, MELEE_ATTACK_DISTANCE, COMBAT_SPACE, COMBAT_SPRINT_DISTANCE,
    CHARACTER_WIDTH, CHARACTER_HEIGHT, CHARACTER_COLLISION_RADIUS,
    UPDATE_INTERVAL, TICK_MULTIPLIER,
    VENDOR_GOODS,
    DIRECTION_TO_FACINGS, OPPOSITE_DIRECTIONS,
    IDLE_SPEED_MULTIPLIER, IDLE_MIN_WAIT_TICKS, IDLE_MAX_WAIT_TICKS,
    IDLE_PAUSE_CHANCE, IDLE_PAUSE_MIN_TICKS, IDLE_PAUSE_MAX_TICKS,
    SQUEEZE_THRESHOLD_TICKS, SQUEEZE_SLIDE_SPEED,
    ATTACK_ANIMATION_DURATION, ATTACK_CONE_ANGLE, ATTACK_CONE_BASE_ANGLE,
    WHEAT_TO_BREAD_RATIO,
    BREAD_PER_BITE, BREAD_BUFFER_TARGET,
    PATROL_SPEED_MULTIPLIER, PATROL_CHECK_MIN_TICKS, PATROL_CHECK_MAX_TICKS,
    PATROL_CHECK_CHANCE, PATROL_APPROACH_DISTANCE,
    SOUND_RADIUS, VISION_RANGE, VISION_CONE_ANGLE,
    DOOR_THRESHOLD
)
from scenario.scenario_world import SIZE
from scenario.scenario_characters import CHARACTER_TEMPLATES
from jobs import get_job
from combat_system import CombatSystem
from world_objects import find_valid_drop_position


class GameLogic:
    """
    Contains all game logic that operates on a GameState instance.
    
    This class:
    - Takes a GameState and modifies it
    - Contains all AI decision making
    - Contains all combat, trading, movement logic
    - Does NOT hold persistent state (that's in GameState)
    - Does NOT contain rendering code (that's in gui.py)
    """
    

    # =============================================================================
    # INITIALIZATION & STATE MANAGEMENT
    # =============================================================================
    # Core initialization and state reset methods
    # =============================================================================

    def __init__(self, state):
        """
        Args:
            state: GameState instance to operate on
        """
        self.state = state
        # Initialize combat system
        self.combat_system = CombatSystem(self)
    
    

    # =============================================================================
    # STATE & GOAL MANAGEMENT
    # =============================================================================
    # Goal setting and state management helpers
    # =============================================================================

    def set_goal_to_character(self, char, target):
        """Set goal to another character's position (cross-zone capable).
        
        Args:
            char: Character whose goal to set
            target: Target character to move toward
        """
        char.goal = (target.x, target.y)  # x,y are always world coords
        char.goal_zone = target.zone
    

    def set_goal_to_object(self, char, obj):
        """Set goal to an object's position (cross-zone capable).
        
        Args:
            char: Character whose goal to set
            obj: Target object (Bed, Stove, Barrel, etc.) with world_x/world_y
        """
        char.goal = (obj.world_x, obj.world_y)
        char.goal_zone = obj.zone
    

    def set_goal_to_position(self, char, x, y, zone=None):
        """Set goal to explicit world position in a specific zone.
        
        Args:
            char: Character whose goal to set
            x, y: World coordinates
            zone: Zone the position is in (None for exterior)
        """
        char.goal = (x, y)
        char.goal_zone = zone
    

    def clear_goal(self, char):
        """Clear character's goal."""
        char.goal = None
        char.goal_zone = None
    
    

    # =============================================================================
    # ZONE & POSITION MANAGEMENT
    # =============================================================================
    # Zone queries, accessibility checks, and position validation
    # =============================================================================

    def set_goal_same_zone(self, char, x, y):
        """Set goal to a position in char's current zone.
        
        Args:
            char: Character whose goal to set
            x, y: World coordinates
        """
        char.goal = (x, y)
        char.goal_zone = char.zone
    

    def is_position_accessible_same_zone(self, x, y, from_zone):
        """
        Check if a world position is accessible from the given zone WITHOUT zone transitions.
        
        Use this for behaviors that should NOT cross zones (wandering, bystander flee,
        farm theft, camping, etc.).
        
        Returns False if:
        - Position would require entering/exiting a building
        - Position is blocked by obstacles (buildings, trees) in exterior
        - Position is blocked by furniture/walls in interior
        - Position is out of bounds
        
        Args:
            x, y: World coordinates
            from_zone: The zone the character is currently in (None for exterior)
        
        Returns:
            True if position is reachable without zone change
        """
        if from_zone is None:
            # Character is in exterior
            cell_x, cell_y = int(x), int(y)
            
            # Check world bounds
            if not self.state.is_position_valid(cell_x, cell_y):
                return False
            
            # Check if position is on any building footprint
            for house in self.state.interactables.get_all_houses():
                if house.contains_point(x, y):
                    return False  # Can't walk on buildings from exterior
            
            # Check obstacles (trees, rocks, etc.)
            if self.state.is_obstacle_at(cell_x, cell_y):
                return False
            
            return True
        else:
            # Character is in an interior
            interior = self.state.interiors.get_interior(from_zone)
            if not interior:
                return False
            
            # Convert world position to interior local coords
            local_x, local_y = interior.world_to_interior(x, y)
            
            # Must be within interior floor bounds (not walls/black area)
            if not interior.is_inside_bounds(int(local_x), int(local_y)):
                return False
            
            # Must not be blocked by furniture
            if interior.is_position_blocked(int(local_x), int(local_y)):
                return False
            
            return True
    

    def get_zone_at_world_position(self, world_x, world_y):
        """
        Determine which zone contains a world position.
        
        Returns:
            Interior name if position is within a building footprint, None for exterior
        """
        for interior in self.state.interiors.get_all_interiors():
            if interior.house.contains_point(world_x, world_y):
                return interior.name
        return None

    # CENTRALIZED ACTION LOGGING
    # These methods provide consistent logging for actions by both player and NPCs


    def get_window_for_cross_zone_vision(self, observer, target):
        """Check if observer can see target through a window.
        
        Args:
            observer: Character doing the looking
            target: Character being looked at
            
        Returns:
            (window, looking_in) tuple, or (None, None) if no valid window
            looking_in: True if observer is outside looking in, False if inside looking out
        """
        # Must be in different zones
        if observer.zone == target.zone:
            return (None, None)
        
        observer_interior = self.state.interiors.get_interior(observer.zone) if observer.zone else None
        target_interior = self.state.interiors.get_interior(target.zone) if target.zone else None
        
        if observer_interior and target.zone is None:
            # Observer inside, target outside
            # Check if observer is near a window and facing outward
            for window in observer_interior.windows:
                if window.is_character_near(observer.prevailing_x, observer.prevailing_y):
                    # Must be facing the window's direction (outward)
                    if self._is_facing_direction(observer, window.facing):
                        return (window, False)  # looking out
        
        if target_interior and observer.zone is None:
            # Observer outside, target inside
            # Check if observer is near window's exterior AND facing toward building
            for window in target_interior.windows:
                if window.is_character_near_exterior(observer.x, observer.y):
                    # Must be facing opposite of window direction (into building)
                    inward_dir = self._get_opposite_direction(window.facing)
                    if self._is_facing_direction(observer, inward_dir):
                        return (window, True)  # looking in
        
        return (None, None)
    

    # =============================================================================
    # CENTRALIZED ACTION LOGGING
    # =============================================================================
    # Unified logging for player and NPC actions
    # =============================================================================

    def log_combat_mode_change(self, char, entering):
        """Log combat mode toggle (same for player and NPCs).

        Args:
            char: Character toggling combat mode
            entering: True if entering combat mode, False if exiting
        """
        name = char.get_display_name()
        mode_str = "COMBAT MODE" if entering else "normal mode"
        self.state.log_action(f"{name} entered {mode_str}")


    def log_zone_transition(self, char, interior_name, entering):
        """Log entering/exiting buildings (same for player and NPCs).

        Args:
            char: Character transitioning
            interior_name: Name of the interior
            entering: True if entering, False if exiting
        """
        name = char.get_display_name()
        if entering:
            self.state.log_action(f"{name} entered {interior_name}")
        else:
            self.state.log_action(f"{name} exited {interior_name}")


    def log_barrel_error(self, char, barrel, error_type):
        """Log barrel interaction errors (same for player and NPCs).

        Args:
            char: Character attempting interaction
            barrel: Barrel object
            error_type: 'not_yours', 'empty', 'inventory_full'
        """
        name = char.get_display_name()
        if error_type == 'not_yours':
            self.state.log_action(f"{name} can't use this barrel (not your home)")
        elif error_type == 'empty':
            self.state.log_action(f"{barrel.name} is empty")
        elif error_type == 'inventory_full':
            self.state.log_action(f"{name}'s inventory is full")


    def log_barrel_take(self, char, barrel, amount):
        """Log taking wheat from barrel (same for player and NPCs).

        Args:
            char: Character taking wheat
            barrel: Barrel object
            amount: Amount of wheat taken
        """
        name = char.get_display_name()
        self.state.log_action(f"{name} took {amount} wheat from {barrel.name}")


    def log_bake_error(self, char, error_type):
        """Log baking errors (same for player and NPCs).

        Args:
            char: Character attempting to bake
            error_type: 'no_stove', 'not_your_stove', 'no_wheat', 'inventory_full'
        """
        name = char.get_display_name()
        if error_type == 'not_your_stove':
            self.state.log_action(f"{name} can't use this stove (not your home)")
        elif error_type == 'no_stove':
            self.state.log_action(f"{name} needs to be near a stove or campfire to bake")
        elif error_type == 'no_wheat':
            self.state.log_action(f"{name} needs wheat to bake bread")
        elif error_type == 'inventory_full':
            self.state.log_action(f"{name}'s inventory is full")


    def log_bed_error(self, char, error_type):
        """Log bed interaction errors (same for player and NPCs).

        Args:
            char: Character attempting to sleep
            error_type: 'not_yours', 'not_implemented'
        """
        name = char.get_display_name()
        if error_type == 'not_yours':
            self.state.log_action(f"{name} can't use this bed (not your home)")
        elif error_type == 'not_implemented':
            self.state.log_action("Sleep not implemented yet")


    def log_harvest_plant_error(self, char, action, error_type):
        """Log harvest/plant errors (same for player and NPCs).

        Args:
            char: Character attempting action
            action: 'harvest' or 'plant'
            error_type: 'cant_here', 'inventory_full', 'cancelled'
        """
        name = char.get_display_name()
        if error_type == 'cant_here':
            self.state.log_action(f"{name} couldn't {action} here.")
        elif error_type == 'inventory_full':
            self.state.log_action(f"{name}'s inventory is full!")
        elif error_type == 'cancelled':
            self.state.log_action(f"{name} couldn't {action} - something changed.")


    def log_harvest_plant_start(self, char, action):
        """Log starting harvest/plant (same for player and NPCs).

        Args:
            char: Character starting action
            action: 'harvest' or 'plant'
        """
        name = char.get_display_name()
        self.state.log_action(f"{name} started {action}ing...")


    def log_harvest_plant_finish(self, char, action):
        """Log finishing harvest/plant (same for player and NPCs).

        Args:
            char: Character finishing action
            action: 'harvest' or 'plant'
        """
        name = char.get_display_name()
        self.state.log_action(f"{name} finished {action}ing!")


    def log_action_cancelled(self, char, action_name):
        """Log action cancellation (same for player and NPCs).

        Args:
            char: Character whose action was cancelled
            action_name: Name of the action (e.g., 'Harvest', 'Plant')
        """
        name = char.get_display_name()
        self.state.log_action(f"{name} cancelled {action_name}")



    # =============================================================================
    # AI & NPC BEHAVIOR HELPERS
    # =============================================================================
    # Distance checks and basic AI decision helpers
    # =============================================================================

    def is_adjacent(self, char1, char2):
        """Check if two characters are adjacent (close enough to interact).
        Uses float-based Euclidean distance with ADJACENCY_DISTANCE threshold.
        Uses prevailing coords (local when in interior) for same-zone checks.
        """
        # Must be in same zone to be adjacent
        if char1.zone != char2.zone:
            return False
        # Use prevailing coords - these are local interior coords when inside,
        # or world coords when in exterior
        dist = math.sqrt((char1.prevailing_x - char2.prevailing_x) ** 2 + 
                        (char1.prevailing_y - char2.prevailing_y) ** 2)
        return dist <= ADJACENCY_DISTANCE and dist > 0  # Must be close but not same position
    

    def is_in_melee_range(self, char1, char2):
        """Check if two characters are close enough for NPC to decide to attack.
        Uses MELEE_ATTACK_DISTANCE - the range at which NPCs will swing.
        Uses prevailing coords (local when in interior) for same-zone checks.
        """
        # Must be in same zone to fight
        if char1.zone != char2.zone:
            return False
        dist = math.sqrt((char1.prevailing_x - char2.prevailing_x) ** 2 + 
                        (char1.prevailing_y - char2.prevailing_y) ** 2)
        return dist <= MELEE_ATTACK_DISTANCE and dist > 0
    

    # =============================================================================
    # COMBAT SYSTEM
    # =============================================================================
    # Attack resolution, damage calculation, and combat mechanics
    # =============================================================================

    def is_in_combat_range(self, char1, char2):
        """Check if two characters are within weapon reach of each other.
        Uses attacker's weapon reach for hit detection range.
        Uses prevailing coords (local when in interior) for same-zone checks.
        """
        # Must be in same zone to fight
        if char1.zone != char2.zone:
            return False
        # Use prevailing coords - these are local interior coords when inside,
        # or world coords when in exterior
        dist = math.sqrt((char1.prevailing_x - char2.prevailing_x) ** 2 + 
                        (char1.prevailing_y - char2.prevailing_y) ** 2)
        weapon_stats = self.get_weapon_stats(char1)
        return dist <= weapon_stats.get('range', FISTS['range'])
    

    def get_weapon_stats(self, char):
        """Get the weapon stats for a character's current melee weapon.
        
        Returns stats dict with: name, weapon_type, base_damage_min, base_damage_max, range
        Falls back to FISTS if no weapon equipped or for NPCs (no equip system yet).
        
        Args:
            char: Character to get weapon stats for
            
        Returns:
            Dict with weapon stats (from ITEMS entry or FISTS constant)
        """
        # Check if character has an equipped weapon
        equipped_slot = getattr(char, 'equipped_weapon', None)
        
        if equipped_slot is not None:
            inventory = getattr(char, 'inventory', [])
            if 0 <= equipped_slot < len(inventory):
                item = inventory[equipped_slot]
                if item is not None:
                    item_type = item.get('type', '')
                    item_info = ITEMS.get(item_type, {})
                    # Only use if it's a melee weapon
                    if item_info.get('weapon_type') == 'melee':
                        return item_info
        
        # Fall back to fists (unarmed combat)
        return FISTS

    

    def can_attack(self, char):
        """Check if character can attack (not on cooldown and in combat mode).
        Returns True if in combat mode and enough time has passed since last attack.

        DELEGATED TO: combat_system.can_attack()
        """
        return self.combat_system.can_attack(char)
    

    def resolve_attack(self, attacker, attack_direction=None, damage_multiplier=1.0):
        """Resolve an attack from a character.
        
        DELEGATED TO: combat_system.resolve_attack()
        
        This is the unified attack resolution used by BOTH player and NPCs.
        Handles: finding targets, dealing damage, witnesses, death, loot.
        
        Args:
            attacker: Character performing the attack
            attack_direction: Optional direction ('up', 'down', 'left', 'right')
                            If None, uses attacker's current facing
            damage_multiplier: Multiplier for damage (1.0 = normal, 2.0 = double)
                              Used for heavy attacks
        
        Returns:
            List of characters that were hit
        """
        return self.combat_system.resolve_attack(attacker, attack_direction, damage_multiplier)
    

    def resolve_melee_attack(self, attacker, target):
        """Resolve a direct melee attack against a specific target.
        
        DELEGATED TO: combat_system.resolve_melee_attack()
        
        Used by NPCs who have a specific target (combat, murder intent).
        
        Args:
            attacker: Character performing the attack
            target: Character being attacked
            
        Returns:
            dict with 'hit', 'damage', 'killed' keys
        """
        return self.combat_system.resolve_melee_attack(attacker, target)
    

    def shoot_arrow(self, char, target_angle, draw_progress):
        """Spawn an arrow projectile for any character (player or NPC).

        Applies accuracy spread based on draw progress - less draw = more deviation.
        Uses Gaussian distribution so most shots are near center, with occasional wild shots.

        Args:
            char: Character shooting the arrow
            target_angle: Angle to shoot in radians (0 = right, π/2 = down)
            draw_progress: Draw power from 0.0 (no draw) to 1.0 (full draw)

        Returns:
            True if arrow was spawned successfully
        """
        import math
        import random

        _bow = ITEMS["bow"]

        # Calculate speed and range based on draw progress
        arrow_speed = _bow["min_speed"] + draw_progress * (_bow["max_speed"] - _bow["min_speed"])
        arrow_range = _bow["min_range"] + draw_progress * (_bow["range"] - _bow["min_range"])

        # Get character position
        if char.zone:
            start_x = char.prevailing_x
            start_y = char.prevailing_y
        else:
            start_x = char.x
            start_y = char.y

        # Calculate accuracy spread based on draw progress
        spread_max = _bow["spread_max_degrees"]
        spread_min = _bow["spread_min_degrees"]
        spread_degrees = spread_max - draw_progress * (spread_max - spread_min)

        # Apply Gaussian deviation if there's any spread
        if spread_degrees > 0:
            # Convert to radians
            spread_radians = math.radians(spread_degrees)
            # Gaussian with std dev = spread_degrees means ~68% of shots within ±spread, ~95% within ±2*spread
            deviation = random.gauss(0, spread_radians)
            target_angle += deviation

        # Calculate direction vector from (possibly deviated) angle
        dx = math.cos(target_angle)
        dy = math.sin(target_angle)

        # Create arrow with speed and range from draw power
        arrow = {
            'x': start_x,
            'y': start_y,
            'dx': dx,
            'dy': dy,
            'distance': 0.0,
            'owner': char,
            'zone': char.zone,
            'speed': arrow_speed,
            'max_range': arrow_range,
        }
        self.state.arrows.append(arrow)

        return True


    def get_adjacent_character(self, char):
        """Get any character adjacent to the given character (within ADJACENCY_DISTANCE)"""
        for other in self.state.characters:
            if other != char and self.is_adjacent(char, other):
                return other
        return None
    

    def remember_attack(self, victim, attacker, damage):
        """Record that victim was attacked by attacker.
        Only stores one memory per attacker - doesn't track each hit.
        """
        # Check if victim already has a memory of being attacked by this attacker
        if victim.has_memory_of('attacked_by', attacker):
            return  # Already remembered, don't duplicate
        
        victim.add_memory('attacked_by', attacker, self.state.ticks,
                         intensity=CRIME_INTENSITY_ASSAULT,
                         source='experienced')
    

    def _face_toward_target(self, char, target):
        """Make character face toward a target."""
        dx = target.prevailing_x - char.prevailing_x
        dy = target.prevailing_y - char.prevailing_y
        
        # Determine facing based on angle
        if abs(dx) > abs(dy) * 2:
            # Mostly horizontal
            char.facing = 'right' if dx > 0 else 'left'
        elif abs(dy) > abs(dx) * 2:
            # Mostly vertical
            char.facing = 'down' if dy > 0 else 'up'
        else:
            # Diagonal
            if dx > 0:
                char.facing = 'down-right' if dy > 0 else 'up-right'
            else:
                char.facing = 'down-left' if dy > 0 else 'up-left'
    

    def broadcast_violence(self, attacker, target):
        """Notify nearby characters of ongoing violence (any fight, justified or not).
        
        Characters who perceive a fight but aren't involved will react:
        - High confidence (>= 7): Watch from current position
        - Low confidence (< 7): Flee from the violence
        
        All bystanders use reason='bystander' - they stop caring once out of perception.
        """
        for char in self.state.characters:
            if char is attacker or char is target:
                continue
            if char.get('health', 100) <= 0:
                continue
            
            # Already reacting to something? Don't interrupt
            if char.intent and char.intent.get('action') in ('attack', 'flee', 'watch'):
                continue
            
            # Can perceive the violence?
            can_perceive, method = self.can_perceive_character(char, attacker)
            if not can_perceive:
                continue
            
            confidence = char.get_trait('confidence')
            if confidence >= 7:
                char.set_intent('watch', attacker, reason='bystander', started_tick=self.state.ticks)
            else:
                char.set_intent('flee', attacker, reason='bystander', started_tick=self.state.ticks)
                self.state.log_action(f"{char.get_display_name()} fleeing from violence!")
    

    def _update_combat_tracking_velocity(self, char, target):
        """Update velocity to track a combat target smoothly.
        
        This bypasses the goal system to provide smooth pursuit of a moving target.
        - If too far: move toward target (to MELEE_ATTACK_DISTANCE), sprint if able
        - If too close: backpedal away (to just outside COMBAT_SPACE)
        - If in sweet spot: hold position
        Always face the target.
        """
        # Calculate distance and direction
        if char.zone == target.zone and char.zone is not None:
            dx = target.prevailing_x - char.prevailing_x
            dy = target.prevailing_y - char.prevailing_y
        else:
            dx = target.x - char.x
            dy = target.y - char.y
        
        dist = math.sqrt(dx * dx + dy * dy)
        
        # Always face the target
        self._face_toward_character(char, target)
        
        # Avoid division by zero
        if dist < 0.01:
            char.vx = 0.0
            char.vy = 0.0
            char.is_sprinting = False
            return
        
        # Normalize direction
        nx = dx / dist
        ny = dy / dist
        
        # Determine movement based on distance
        if dist > MELEE_ATTACK_DISTANCE:
            # Too far - chase the target
            # Only sprint if target is significantly beyond attack range
            sprint_threshold = MELEE_ATTACK_DISTANCE + COMBAT_SPRINT_DISTANCE
            should_sprint = dist > sprint_threshold
            
            if should_sprint:
                can_sprint = char.can_continue_sprint() if char.is_sprinting else char.can_start_sprint()
                should_sprint = can_sprint
            
            char.is_sprinting = should_sprint
            speed = SPRINT_SPEED if should_sprint else MOVEMENT_SPEED
            
            char.vx = nx * speed
            char.vy = ny * speed
        elif dist < COMBAT_SPACE:
            # Too close - backpedal slowly (half speed, away from target)
            char.is_sprinting = False
            char.vx = -nx * MOVEMENT_SPEED * 0.5
            char.vy = -ny * MOVEMENT_SPEED * 0.5
        else:
            # In sweet spot - hold position
            char.vx = 0.0
            char.vy = 0.0
            char.is_sprinting = False
    

    def _do_attack(self, attacker, target):
        """Execute an attack. Starts attack animation, damage dealt when animation completes."""
        # Check if can attack (not already animating)
        if not attacker.can_attack():
            return
        
        # Face the target before attacking
        self._face_toward_target(attacker, target)
        
        # Start attack animation - damage dealt when animation completes
        # (processed by _process_pending_attacks)
        attacker.start_attack(target=target)
        
        # Record attack tick for cooldown
        attacker['last_attack_tick'] = self.state.ticks

    # TICK PROCESSING
    

    def _process_npc_combat_mode(self):
        """Update combat mode for NPCs based on their intent.

        NPCs enter combat mode when:
        - Their intent is 'attack'
        - Their intent is 'flee' (defensive stance)

        NPCs exit combat mode when:
        - They have no intent or a non-combat intent

        When entering combat mode, NPCs auto-equip their strongest weapon.
        When exiting combat mode, NPCs unequip weapons.

        Player combat mode is controlled manually via R key.
        """
        for char in self.state.characters:
            # Skip player - player controls their own combat mode
            if char.is_player:
                continue

            # Skip dead characters
            if char.health <= 0:
                continue

            intent = char.intent
            if intent:
                action = intent.get('action')
                # Enter combat mode for attack or flee intents
                if action in ('attack', 'flee'):
                    if not char.get('combat_mode', False):
                        char['combat_mode'] = True
                        # Auto-equip strongest weapon when entering combat
                        char.equip_strongest_weapon()
                else:
                    # Non-combat intent - exit combat mode
                    if char.get('combat_mode', False):
                        char['combat_mode'] = False
                        # Unequip weapon when leaving combat
                        char.equipped_weapon = None
            else:
                # No intent - exit combat mode
                if char.get('combat_mode', False):
                    char['combat_mode'] = False
                    # Unequip weapon when leaving combat
                    char.equipped_weapon = None
    

    def _process_pending_attacks(self):
        """Process pending attacks when their animations complete.
        
        DELEGATED TO: combat_system.process_pending_attacks()
        
        Called every tick. Checks all characters for pending attacks and
        resolves damage when the attack animation has finished.
        """
        self.combat_system.process_pending_attacks()
    

    def equip_weapon(self, character, slot_index):
        """Equip a weapon from a specific inventory slot.

        Args:
            character: Character equipping the weapon
            slot_index: Inventory slot index

        Returns:
            dict with 'success' key and optional details
        """
        inventory = character.inventory
        if slot_index < 0 or slot_index >= len(inventory):
            return {'success': False, 'reason': 'invalid_slot'}

        item = inventory[slot_index]
        if item is None:
            return {'success': False, 'reason': 'empty_slot'}

        item_type = item.get('type', '')
        item_info = ITEMS.get(item_type, {})

        if item_info.get('category') != 'weapon':
            return {'success': False, 'reason': 'not_weapon'}

        if character.equipped_weapon is not None:
            old_slot = character.equipped_weapon
            old_item = inventory[old_slot] if old_slot < len(inventory) else None
            if old_item:
                old_name = ITEMS.get(old_item.get('type', ''), {}).get('name', 'weapon')
                self.state.log_action(f"{character.get_display_name()} unequipped {old_name}")

        character.equipped_weapon = slot_index
        weapon_name = item_info.get('name', item_type)
        self.state.log_action(f"{character.get_display_name()} equipped {weapon_name}")

        return {'success': True, 'weapon_name': weapon_name}


    def unequip_weapon(self, character, slot_index):
        """Unequip the weapon in a specific inventory slot.

        Args:
            character: Character unequipping the weapon
            slot_index: Inventory slot index

        Returns:
            dict with 'success' key
        """
        if character.equipped_weapon != slot_index:
            return {'success': False, 'reason': 'not_equipped'}

        inventory = character.inventory
        item = inventory[slot_index] if slot_index < len(inventory) else None
        if item:
            item_type = item.get('type', '')
            item_info = ITEMS.get(item_type, {})
            weapon_name = item_info.get('name', item_type)
            self.state.log_action(f"{character.get_display_name()} unequipped {weapon_name}")

        character.equipped_weapon = None
        return {'success': True}


    # =============================================================================
    # INVENTORY SYSTEM - Core Operations
    # =============================================================================
    # Item usage, equipment, and core inventory operations
    # =============================================================================

    def use_item(self, character, slot_index):
        """Use/consume an item from a specific inventory slot.

        Args:
            character: Character using the item
            slot_index: Inventory slot index

        Returns:
            dict with 'success' key and optional message details
        """
        inventory = character.inventory
        if slot_index < 0 or slot_index >= len(inventory):
            return {'success': False, 'reason': 'invalid_slot'}

        item = inventory[slot_index]
        if item is None:
            return {'success': False, 'reason': 'empty_slot'}

        item_type = item.get('type', '')

        if item_type == 'bread':
            result = character.eat()
            if result['success']:
                msg = f"{character.get_display_name()} ate bread, hunger now {character.hunger:.0f}"
                if result.get('recovered_from_starvation'):
                    msg = f"{character.get_display_name()} ate bread and recovered from starvation! Hunger: {character.hunger:.0f}"
                self.state.log_action(msg)
            return result

        return {'success': False, 'reason': 'not_usable'}


    def burn_item(self, character, slot_index):
        """Burn/destroy an item from inventory.

        Args:
            character: Character burning the item
            slot_index: Inventory slot index

        Returns:
            dict with 'success' key and details
        """
        inventory = character.inventory
        if slot_index < 0 or slot_index >= len(inventory):
            return {'success': False, 'reason': 'invalid_slot'}

        item = inventory[slot_index]
        if item is None:
            return {'success': False, 'reason': 'empty_slot'}

        item_type = item.get('type', 'item')
        amount = item.get('amount', 1)

        item_info = ITEMS.get(item_type, {})
        display_name = item_info.get('name', item_type.capitalize())

        inventory[slot_index] = None

        self.state.log_action(f"{character.get_display_name()} burned {amount} {display_name}")

        return {'success': True, 'item_type': item_type, 'amount': amount, 'display_name': display_name}


    def can_burn_items(self, character):
        """Check if character is adjacent to a usable stove or campfire.

        Args:
            character: Character to check

        Returns:
            bool: True if can burn items
        """
        stove = self.state.interactables.get_adjacent_stove(character)
        if stove and stove.can_use(character):
            return True

        if character.zone is None:
            px, py = character.x, character.y
            for char in self.state.characters:
                camp_pos = char.get('camp_position')
                if camp_pos:
                    cx, cy = camp_pos
                    dist = ((px - (cx + 0.5)) ** 2 + (py - (cy + 0.5)) ** 2) ** 0.5
                    if dist <= 1.5:
                        return True

        return False


    def transfer_item_to_inventory(self, item_type, amount, target_inventory, stack_limit):
        """Transfer items to an inventory with stacking logic.

        Args:
            item_type: Type of item to transfer
            amount: Amount to transfer
            target_inventory: List of inventory slots (modified in place)
            stack_limit: Stack limit for the item type (None for unlimited)

        Returns:
            int: Amount remaining (0 if all transferred)
        """
        amount_to_move = amount

        for i, slot in enumerate(target_inventory):
            if slot and slot.get('type') == item_type:
                if stack_limit is None:
                    slot['amount'] = slot.get('amount', 0) + amount_to_move
                    amount_to_move = 0
                    break
                else:
                    space = stack_limit - slot.get('amount', 0)
                    if space > 0:
                        transfer = min(space, amount_to_move)
                        slot['amount'] = slot.get('amount', 0) + transfer
                        amount_to_move -= transfer
                        if amount_to_move <= 0:
                            break

        if amount_to_move > 0:
            for i, slot in enumerate(target_inventory):
                if slot is None:
                    if stack_limit is None:
                        target_inventory[i] = {'type': item_type, 'amount': amount_to_move}
                        amount_to_move = 0
                        break
                    else:
                        transfer = min(stack_limit, amount_to_move)
                        target_inventory[i] = {'type': item_type, 'amount': transfer}
                        amount_to_move -= transfer
                        if amount_to_move <= 0:
                            break

        return amount_to_move



    def get_stack_limit(self, item_type):
        """Get stack limit for an item type. Returns None for unlimited."""
        info = ITEMS.get(item_type, {})
        return info.get('stack_size', 99)  # Default to 99 if not defined



    def return_held_item_to_inventory(self, player, held_item, held_was_equipped):
        """
        Return held item to first available inventory slot, or drop to ground if full.
        Returns: (updated_held_item, updated_held_was_equipped)
        """
        if not held_item or not player:
            return None, False

        inventory = player.inventory
        held_type = held_item['type']
        stack_limit = self.get_stack_limit(held_type)

        # First try to stack with existing items of same type
        for i, slot in enumerate(inventory):
            if slot and slot.get('type') == held_type:
                if stack_limit is None:
                    # Unlimited stacking - combine everything
                    slot['amount'] = slot.get('amount', 0) + held_item['amount']
                    return None, False
                else:
                    space = stack_limit - slot.get('amount', 0)
                    if space > 0:
                        transfer = min(space, held_item['amount'])
                        slot['amount'] = slot.get('amount', 0) + transfer
                        held_item['amount'] -= transfer
                        if held_item['amount'] <= 0:
                            return None, False

        # Then try empty slots
        for i, slot in enumerate(inventory):
            if slot is None:
                inventory[i] = held_item.copy()
                # If this was an equipped weapon, re-equip it in new slot
                if held_was_equipped:
                    player.equipped_weapon = i
                return None, False

        # If still holding item, return it (inventory full - caller should drop to ground)
        return held_item, held_was_equipped


    # =============================================================================
    # INVENTORY SYSTEM - Slot Interactions
    # =============================================================================
    # Inventory slot clicking and quick-move operations
    # =============================================================================

    def interact_inventory_slot_full(self, player, slot_index, held_item, held_was_equipped):
        """
        Left click interaction - pick up / place / swap full stack.
        Returns: dict with 'held_item' and 'held_was_equipped' keys
        """
        inventory = player.inventory

        if slot_index < 0 or slot_index >= len(inventory):
            return {'held_item': held_item, 'held_was_equipped': held_was_equipped}

        slot_item = inventory[slot_index]

        if held_item is None:
            # Pick up entire stack from slot
            if slot_item is not None:
                held_item = slot_item.copy()
                # Track if we're picking up the equipped weapon
                held_was_equipped = (player.equipped_weapon == slot_index)
                if held_was_equipped:
                    player.equipped_weapon = None
                inventory[slot_index] = None
        else:
            # We're holding something
            if slot_item is None:
                # Place entire held stack in empty slot
                inventory[slot_index] = held_item.copy()
                # If we were holding an equipped weapon, update the slot reference
                if held_was_equipped:
                    player.equipped_weapon = slot_index
                    held_was_equipped = False
                held_item = None
            elif slot_item.get('type') == held_item.get('type'):
                # Same type - try to stack
                stack_limit = self.get_stack_limit(slot_item.get('type'))
                if stack_limit is None:
                    # Unlimited stacking - combine everything
                    slot_item['amount'] = slot_item.get('amount', 0) + held_item['amount']
                    held_was_equipped = False
                    held_item = None
                else:
                    space = stack_limit - slot_item.get('amount', 0)
                    if space > 0:
                        transfer = min(space, held_item['amount'])
                        slot_item['amount'] = slot_item.get('amount', 0) + transfer
                        held_item['amount'] -= transfer
                        if held_item['amount'] <= 0:
                            held_was_equipped = False
                            held_item = None
                    else:
                        # Stack full - swap
                        inventory[slot_index] = held_item.copy()
                        old_slot_was_equipped = (player.equipped_weapon == slot_index)
                        # If we were holding equipped weapon, it goes to this slot
                        if held_was_equipped:
                            player.equipped_weapon = slot_index
                        elif old_slot_was_equipped:
                            player.equipped_weapon = None  # Old equipped is now held
                        held_was_equipped = old_slot_was_equipped
                        held_item = slot_item.copy()
            else:
                # Different type - swap
                inventory[slot_index] = held_item.copy()
                old_slot_was_equipped = (player.equipped_weapon == slot_index)
                # If we were holding equipped weapon, it goes to this slot
                if held_was_equipped:
                    player.equipped_weapon = slot_index
                elif old_slot_was_equipped:
                    player.equipped_weapon = None  # Old equipped is now held
                held_was_equipped = old_slot_was_equipped
                held_item = slot_item.copy()

        return {'held_item': held_item, 'held_was_equipped': held_was_equipped}


    def interact_inventory_slot_single(self, player, slot_index, held_item, held_was_equipped):
        """
        Right click interaction - pick up half / place single.
        Returns: dict with 'held_item' and 'held_was_equipped' keys
        """
        inventory = player.inventory

        if slot_index < 0 or slot_index >= len(inventory):
            return {'held_item': held_item, 'held_was_equipped': held_was_equipped}

        slot_item = inventory[slot_index]

        if held_item is None:
            # Pick up half of stack from slot
            if slot_item is not None:
                total = slot_item.get('amount', 1)
                take = (total + 1) // 2  # Ceiling division - take the larger half
                leave = total - take

                held_item = {'type': slot_item['type'], 'amount': take}

                if leave > 0:
                    slot_item['amount'] = leave
                    # Weapon stays equipped if there's still items in the slot
                else:
                    # Track if we're picking up the equipped weapon
                    held_was_equipped = (player.equipped_weapon == slot_index)
                    if held_was_equipped:
                        player.equipped_weapon = None
                    inventory[slot_index] = None
        else:
            # We're holding something - place single item
            if slot_item is None:
                # Place 1 item in empty slot
                inventory[slot_index] = {'type': held_item['type'], 'amount': 1}
                held_item['amount'] -= 1
                if held_item['amount'] <= 0:
                    # If placing the last of an equipped weapon, equip it in new slot
                    if held_was_equipped:
                        player.equipped_weapon = slot_index
                        held_was_equipped = False
                    held_item = None
            elif slot_item.get('type') == held_item.get('type'):
                # Same type - place 1 if room
                stack_limit = self.get_stack_limit(slot_item.get('type'))
                # None means unlimited, so always allow; otherwise check limit
                if stack_limit is None or slot_item.get('amount', 0) < stack_limit:
                    slot_item['amount'] = slot_item.get('amount', 0) + 1
                    held_item['amount'] -= 1
                    if held_item['amount'] <= 0:
                        held_was_equipped = False
                        held_item = None

        return {'held_item': held_item, 'held_was_equipped': held_was_equipped}



    def quick_move_inventory_to_ground(self, player, slot_index, ground_items_manager, is_blocked_fn):
        """Shift+click: Quick-move item from inventory to ground."""
        inventory = player.inventory

        if slot_index < 0 or slot_index >= len(inventory):
            return

        slot_item = inventory[slot_index]
        if slot_item is None:
            return

        # Unequip if this was the equipped weapon
        if player.equipped_weapon == slot_index:
            player.equipped_weapon = None

        # Find valid drop position
        if player.zone:
            px, py = player.prevailing_x, player.prevailing_y
        else:
            px, py = player.x, player.y

        drop_pos = find_valid_drop_position(px, py, player.zone, is_blocked_fn)
        if drop_pos:
            ground_items_manager.add_item(
                slot_item['type'],
                slot_item['amount'],
                drop_pos[0],
                drop_pos[1],
                player.zone
            )
            inventory[slot_index] = None



    def quick_move_inventory_to_barrel(self, player, barrel, slot_index):
        """Shift+click: Quick-move item from player inventory to barrel/corpse."""
        inventory = player.inventory
        barrel_inventory = barrel.inventory

        if slot_index < 0 or slot_index >= len(inventory):
            return

        slot_item = inventory[slot_index]
        if slot_item is None:
            return

        if player.equipped_weapon == slot_index:
            player.equipped_weapon = None

        item_type = slot_item['type']
        amount_to_move = slot_item['amount']
        stack_limit = self.get_stack_limit(item_type)

        amount_remaining = self.transfer_item_to_inventory(item_type, amount_to_move, barrel_inventory, stack_limit)

        if amount_remaining <= 0:
            inventory[slot_index] = None
        else:
            slot_item['amount'] = amount_remaining



    # =============================================================================
    # GROUND ITEMS SYSTEM
    # =============================================================================
    # Ground item interactions and dropping logic
    # =============================================================================

    def interact_ground_slot_full(self, ground_item, held_item, ground_items_manager, nearby_items_list, player):
        """
        Handle left-click on a ground slot - pick up / place / swap full stack.
        Returns: updated held_item
        """
        if held_item is None:
            # Pick up item from ground
            if ground_item:
                held_item = {'type': ground_item.item_type, 'amount': ground_item.amount}
                ground_items_manager.remove_item(ground_item)
        else:
            # We're holding something
            if ground_item is None:
                # Caller should handle drop to ground
                return held_item
            elif ground_item.item_type == held_item.get('type'):
                # Same type - try to stack
                stack_limit = self.get_stack_limit(ground_item.item_type)
                if stack_limit is None:
                    # Unlimited stacking
                    ground_item.amount += held_item['amount']
                    held_item = None
                else:
                    space = stack_limit - ground_item.amount
                    if space > 0:
                        transfer = min(space, held_item['amount'])
                        ground_item.amount += transfer
                        held_item['amount'] -= transfer
                        if held_item['amount'] <= 0:
                            held_item = None
                    else:
                        # Stack full - swap
                        old_type = ground_item.item_type
                        old_amount = ground_item.amount
                        ground_item.item_type = held_item['type']
                        ground_item.amount = held_item['amount']
                        held_item = {'type': old_type, 'amount': old_amount}
            else:
                # Different type - swap
                old_type = ground_item.item_type
                old_amount = ground_item.amount
                ground_item.item_type = held_item['type']
                ground_item.amount = held_item['amount']
                held_item = {'type': old_type, 'amount': old_amount}

        return held_item


    def interact_ground_slot_single(self, ground_item, held_item, ground_items_manager, nearby_items_list, player):
        """
        Handle right-click on a ground slot - pick up half / place single.
        Returns: updated held_item
        """
        if held_item is None:
            # Pick up half of stack from ground
            if ground_item:
                total = ground_item.amount
                take = (total + 1) // 2  # Ceiling division - take the larger half
                leave = total - take

                held_item = {'type': ground_item.item_type, 'amount': take}

                if leave > 0:
                    ground_item.amount = leave
                else:
                    ground_items_manager.remove_item(ground_item)
        else:
            # We're holding something - place single item
            if ground_item is None:
                # Caller should handle drop to ground
                return held_item
            elif ground_item.item_type == held_item.get('type'):
                # Same type - place 1 if room
                stack_limit = self.get_stack_limit(ground_item.item_type)
                if stack_limit is None or ground_item.amount < stack_limit:
                    ground_item.amount += 1
                    held_item['amount'] -= 1
                    if held_item['amount'] <= 0:
                        held_item = None
            # Different type - do nothing

        return held_item


    def drop_held_item_to_ground(self, player, held_item, ground_items_manager, is_blocked_fn):
        """
        Drop the entire held item stack to the ground.
        Returns: None (clears held_item)
        """
        if not held_item:
            return None

        # Find valid drop position
        if player.zone:
            px, py = player.prevailing_x, player.prevailing_y
        else:
            px, py = player.x, player.y

        drop_pos = find_valid_drop_position(px, py, player.zone, is_blocked_fn)
        if drop_pos:
            ground_items_manager.add_item(
                held_item['type'],
                held_item['amount'],
                drop_pos[0],
                drop_pos[1],
                player.zone
            )

        return None


    def drop_single_item_to_ground(self, player, held_item, ground_items_manager, is_blocked_fn):
        """
        Drop a single item from the held stack to the ground.
        Returns: updated held_item
        """
        if not held_item or held_item['amount'] < 1:
            return held_item

        # Find valid drop position
        if player.zone:
            px, py = player.prevailing_x, player.prevailing_y
        else:
            px, py = player.x, player.y

        drop_pos = find_valid_drop_position(px, py, player.zone, is_blocked_fn)
        if drop_pos:
            ground_items_manager.add_item(
                held_item['type'],
                1,
                drop_pos[0],
                drop_pos[1],
                player.zone
            )
            held_item['amount'] -= 1
            if held_item['amount'] <= 0:
                return None

        return held_item


    def quick_move_ground_to_inventory(self, player, ground_item, ground_items_manager, nearby_items_list):
        """Shift+click: Quick-move item from ground to inventory (Minecraft style)."""
        inventory = player.inventory
        item_type = ground_item.item_type
        amount_to_move = ground_item.amount
        stack_limit = self.get_stack_limit(item_type)

        amount_remaining = self.transfer_item_to_inventory(item_type, amount_to_move, inventory, stack_limit)

        if amount_remaining <= 0:
            ground_items_manager.remove_item(ground_item)
        else:
            ground_item.amount = amount_remaining


    # =============================================================================
    # BARREL/CONTAINER SYSTEM
    # =============================================================================
    # Storage container interactions
    # =============================================================================

    def take_from_barrel(self, char, max_amount=50, log_errors=True):
        """Take wheat from an adjacent barrel.

        Performs ALL validation and logging. Single source of truth for barrel interactions.

        Args:
            char: Character taking from barrel
            max_amount: Maximum wheat to take at once (default 50)
            log_errors: If True, log detailed error messages (default True)

        Returns:
            Amount of wheat actually taken (0 if failed)
        """
        # Find adjacent barrel
        for barrel in self.state.interactables.barrels.values():
            if not barrel.is_adjacent(char):
                continue

            # Found adjacent barrel - check permissions
            if not barrel.can_use(char):
                if log_errors:
                    self.log_barrel_error(char, barrel, 'not_yours')
                return 0

            # Check barrel contents
            wheat_count = barrel.get_item('wheat')
            if wheat_count <= 0:
                if log_errors:
                    self.log_barrel_error(char, barrel, 'empty')
                return 0

            # Check inventory space
            if not char.can_add_item('wheat', 1):
                if log_errors:
                    self.log_barrel_error(char, barrel, 'inventory_full')
                return 0

            # Take as much wheat as possible
            can_take = min(wheat_count, max_amount)
            taken = 0
            for _ in range(can_take):
                if not char.can_add_item('wheat', 1):
                    break
                if barrel.get_item('wheat') <= 0:
                    break
                barrel.remove_item('wheat', 1)
                char.add_item('wheat', 1)
                taken += 1

            if taken > 0:
                self.log_barrel_take(char, barrel, taken)

            return taken

        # No adjacent barrel found
        return 0


    def get_nearby_barrel(self, character, max_distance=1.5):
        """
        Find a barrel near the character in the same zone.

        Args:
            character: Character to search from
            max_distance: Maximum distance to search

        Returns:
            Barrel object if one is nearby, None otherwise
        """
        if not character:
            return None

        import math
        char_zone = character.zone

        for barrel in self.state.interactables.barrels.values():
            # Must be in same zone
            if barrel.zone != char_zone:
                continue

            # Calculate distance using appropriate coordinates
            if char_zone is not None:
                # Interior - use prevailing (local) coords
                dx = character.prevailing_x - (barrel.x + 0.5)
                dy = character.prevailing_y - (barrel.y + 0.5)
            else:
                # Exterior - use world coords
                dx = character.x - (barrel.x + 0.5)
                dy = character.y - (barrel.y + 0.5)

            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= max_distance:
                return barrel

        return None


    def interact_barrel_slot_full(self, barrel, slot_index, held_item):
        """
        Handle left-click on a barrel/corpse slot - pick up / place / swap full stack.
        Returns: updated held_item
        """
        barrel_inventory = barrel.inventory

        if slot_index < 0 or slot_index >= len(barrel_inventory):
            return held_item

        barrel_item = barrel_inventory[slot_index]

        if held_item is None:
            # Pick up item from barrel
            if barrel_item:
                held_item = {'type': barrel_item['type'], 'amount': barrel_item['amount']}
                barrel_inventory[slot_index] = None
        else:
            # We're holding something
            if barrel_item is None:
                # Place held item in barrel
                barrel_inventory[slot_index] = {'type': held_item['type'], 'amount': held_item['amount']}
                held_item = None
            elif barrel_item['type'] == held_item.get('type'):
                # Same type - try to stack
                stack_limit = self.get_stack_limit(barrel_item['type'])
                if stack_limit is None:
                    # Unlimited stacking
                    barrel_item['amount'] += held_item['amount']
                    held_item = None
                else:
                    space = stack_limit - barrel_item['amount']
                    if space > 0:
                        transfer = min(space, held_item['amount'])
                        barrel_item['amount'] += transfer
                        held_item['amount'] -= transfer
                        if held_item['amount'] <= 0:
                            held_item = None
                    else:
                        # Stack full - swap
                        old_type = barrel_item['type']
                        old_amount = barrel_item['amount']
                        barrel_item['type'] = held_item['type']
                        barrel_item['amount'] = held_item['amount']
                        held_item = {'type': old_type, 'amount': old_amount}
            else:
                # Different type - swap
                old_type = barrel_item['type']
                old_amount = barrel_item['amount']
                barrel_item['type'] = held_item['type']
                barrel_item['amount'] = held_item['amount']
                held_item = {'type': old_type, 'amount': old_amount}

        return held_item


    def interact_barrel_slot_single(self, barrel, slot_index, held_item):
        """
        Handle right-click on a barrel/corpse slot - pick up half / place single.
        Returns: updated held_item
        """
        barrel_inventory = barrel.inventory

        if slot_index < 0 or slot_index >= len(barrel_inventory):
            return held_item

        barrel_item = barrel_inventory[slot_index]

        if held_item is None:
            # Pick up half of stack from barrel
            if barrel_item:
                total = barrel_item['amount']
                take = (total + 1) // 2  # Ceiling division - take the larger half
                leave = total - take

                held_item = {'type': barrel_item['type'], 'amount': take}

                if leave > 0:
                    barrel_item['amount'] = leave
                else:
                    barrel_inventory[slot_index] = None
        else:
            # We're holding something - place single item
            if barrel_item is None:
                # Place 1 item in barrel
                barrel_inventory[slot_index] = {'type': held_item['type'], 'amount': 1}
                held_item['amount'] -= 1
                if held_item['amount'] <= 0:
                    held_item = None
            elif barrel_item['type'] == held_item.get('type'):
                # Same type - place 1 if room
                stack_limit = self.get_stack_limit(barrel_item['type'])
                if stack_limit is None or barrel_item['amount'] < stack_limit:
                    barrel_item['amount'] += 1
                    held_item['amount'] -= 1
                    if held_item['amount'] <= 0:
                        held_item = None
            # Different type - do nothing

        return held_item


    def quick_move_barrel_to_inventory(self, player, barrel, slot_index):
        """Shift+click: Quick-move item from barrel/corpse to player inventory."""
        inventory = player.inventory
        barrel_inventory = barrel.inventory

        if slot_index < 0 or slot_index >= len(barrel_inventory):
            return

        barrel_item = barrel_inventory[slot_index]
        if barrel_item is None:
            return

        item_type = barrel_item['type']
        amount_to_move = barrel_item['amount']
        stack_limit = self.get_stack_limit(item_type)

        amount_remaining = self.transfer_item_to_inventory(item_type, amount_to_move, inventory, stack_limit)

        if amount_remaining <= 0:
            barrel_inventory[slot_index] = None
        else:
            barrel_item['amount'] = amount_remaining


    # =============================================================================
    # FARMING SYSTEM
    # =============================================================================
    # Crop planting, harvesting, and farm management
    # =============================================================================

    def player_harvest_cell(self, player):
        """Instantly harvest the farm cell the player is standing on.
        
        Returns:
            True if harvest succeeded, False otherwise
        """
        if not player or not player.is_player:
            return False
        
        cell_x = int(player.x)
        cell_y = int(player.y)
        cell = (cell_x, cell_y)
        
        if cell not in self.state.farm_cells:
            return False
        
        data = self.state.farm_cells[cell]
        
        # Can only harvest ready cells
        if data['state'] != 'ready':
            return False
        
        # Check inventory space
        if not player.can_add_item('wheat', FARM_CELL_YIELD):
            name = player.get_display_name()
            self.state.log_action(f"{name}'s inventory is full!")
            return False
        
        # Instant harvest - add wheat and set to replanting
        player.add_item('wheat', FARM_CELL_YIELD)
        data['state'] = 'replanting'
        data['timer'] = FARM_REPLANT_TIME
        
        name = player.get_display_name()
        is_farmer = player.get('job') == 'Farmer'
        
        # If player is not a farmer, this is theft
        if not is_farmer:
            self.state.log_action(f"{name} STOLE {FARM_CELL_YIELD} wheat from farm!")
            # Trigger witness system for theft
            self.witness_theft(player, cell)
        else:
            self.state.log_action(f"{name} harvested {FARM_CELL_YIELD} wheat!")
        
        return True
    

    def player_plant_cell(self, player):
        """Instantly plant/replant the farm cell the player is standing on.
        
        This transitions a 'replanting' cell to 'growing' state instantly.
        
        Returns:
            True if planting succeeded, False otherwise
        """
        if not player or not player.is_player:
            return False
        
        cell_x = int(player.x)
        cell_y = int(player.y)
        cell = (cell_x, cell_y)
        
        if cell not in self.state.farm_cells:
            return False
        
        data = self.state.farm_cells[cell]
        
        # Can only plant cells in replanting state
        if data['state'] != 'replanting':
            return False
        
        # Instant plant - set to growing
        data['state'] = 'growing'
        data['timer'] = FARM_CELL_HARVEST_INTERVAL
        
        name = player.get_display_name()
        self.state.log_action(f"{name} planted seeds.")
        
        return True
    
    

    def _update_farm_cells(self):
        """Update all farm cell states"""
        for cell, data in self.state.farm_cells.items():
            if data['state'] == 'growing':
                data['timer'] -= 1
                if data['timer'] <= 0:
                    data['state'] = 'ready'
                    data['timer'] = 0
        
        # Process characters standing on farm cells
        # Only farmers can legitimately harvest - others commit theft
        # NOTE: Player is skipped here - player uses environment menu for instant harvest/plant
        cells_being_worked = set()
        for char in self.state.characters:
            # Skip dying characters
            if char.get('health', 100) <= 0:
                continue
            
            # Skip player - player harvests via environment menu
            if char.is_player:
                continue
            
            # Convert float position to cell coordinates
            cell = (int(char['x']), int(char['y']))
            if cell in self.state.farm_cells and cell not in cells_being_worked:
                data = self.state.farm_cells[cell]
                
                # Only farmers can work farm cells without it being theft
                is_farmer = char.get('job') == 'Farmer'
                
                if not is_farmer:
                    continue  # Non-farmers use try_farm_theft via AI
                
                if data['state'] == 'ready':
                    # Check if can carry more wheat
                    if not char.can_add_item('wheat', FARM_CELL_YIELD):
                        continue  # Inventory full, can't harvest
                    data['state'] = 'harvesting'
                    data['timer'] = FARM_HARVEST_TIME
                    data['harvester'] = char  # Track who started harvesting
                    cells_being_worked.add(cell)
                
                elif data['state'] == 'harvesting':
                    data['timer'] -= 1
                    if data['timer'] <= 0:
                        # Check inventory space before adding wheat
                        if char.can_add_item('wheat', FARM_CELL_YIELD):
                            char.add_item('wheat', FARM_CELL_YIELD)
                            data['state'] = 'replanting'
                            data['timer'] = FARM_REPLANT_TIME
                            
                            name = char.get_display_name()
                            self.state.log_action(f"{name} harvested {FARM_CELL_YIELD} wheat!")
                        else:
                            # Can't harvest, leave cell ready
                            data['state'] = 'ready'
                    cells_being_worked.add(cell)
                
                elif data['state'] == 'replanting':
                    data['timer'] -= 1
                    if data['timer'] <= 0:
                        data['state'] = 'growing'
                        data['timer'] = FARM_CELL_HARVEST_INTERVAL
                    cells_being_worked.add(cell)
    

    def can_harvest_at(self, player):
        """Check if player can harvest at current position."""
        cell_x = int(player.x)
        cell_y = int(player.y)
        farm_cell = self.state.farm_cells.get((cell_x, cell_y))

        if farm_cell and farm_cell.get('state', '') == 'ready':
            return True
        return False


    def can_plant_at(self, player):
        """Check if player can plant at current position."""
        cell_x = int(player.x)
        cell_y = int(player.y)
        farm_cell = self.state.farm_cells.get((cell_x, cell_y))

        if farm_cell and farm_cell.get('state', '') == 'replanting':
            return True
        return False


    def start_harvest_action(self, player):
        """
        Validate and start harvest action.
        Returns: True if successful, False otherwise
        """
        from constants import ONGOING_ACTION_HARVEST_DURATION, FARM_CELL_YIELD

        cell_x = int(player.x)
        cell_y = int(player.y)
        farm_cell = self.state.farm_cells.get((cell_x, cell_y))

        if not farm_cell or farm_cell.get('state') != 'ready':
            self.log_harvest_plant_error(player, 'harvest', 'cant_here')
            return False

        # Check inventory space
        if not player.can_add_item('wheat', FARM_CELL_YIELD):
            self.log_harvest_plant_error(player, 'harvest', 'inventory_full')
            return False

        # Start ongoing harvest action
        player.start_ongoing_action(
            'harvest',
            ONGOING_ACTION_HARVEST_DURATION,
            {'cell': (cell_x, cell_y)}
        )
        return True


    def start_plant_action(self, player):
        """
        Validate and start plant action.
        Returns: True if successful, False otherwise
        """
        from constants import ONGOING_ACTION_PLANT_DURATION

        cell_x = int(player.x)
        cell_y = int(player.y)
        farm_cell = self.state.farm_cells.get((cell_x, cell_y))

        if not farm_cell or farm_cell.get('state') != 'replanting':
            self.log_harvest_plant_error(player, 'plant', 'cant_here')
            return False

        # Start ongoing plant action
        player.start_ongoing_action(
            'plant',
            ONGOING_ACTION_PLANT_DURATION,
            {'cell': (cell_x, cell_y)}
        )
        return True
    # =============================================================================
    # CRAFTING & COOKING SYSTEM
    # =============================================================================
    # Bread baking and crafting mechanics
    # =============================================================================

    def get_adjacent_cooking_spot(self, char):
        """Get any adjacent cooking spot (stove or campfire).
        Returns a dict with 'type' ('stove' or 'camp'), 'name', and source object.
        Returns None if no cooking spot is adjacent.
        """
        # Check for stove first - return it even if char can't use it
        # (ownership check is handled by caller for proper hint display)
        stove = self.state.interactables.get_adjacent_stove(char)
        if stove:
            return {
                'type': 'stove',
                'name': stove.name,
                'source': stove
            }

        # Check for any campfire (anyone can use any campfire)
        camp_pos, camp_owner = self.get_adjacent_camp(char)
        if camp_pos:
            owner_name = camp_owner.get_display_name() if camp_owner else 'unknown'
            return {
                'type': 'camp',
                'name': f"{owner_name}'s campfire",
                'source': camp_pos
            }

        return None
    

    def can_bake_bread(self, char):
        """Check if character can bake bread right now.
        Requirements: adjacent to a stove (that they can use) or campfire, has wheat, has space for bread.
        """
        # Must be adjacent to a cooking spot (stove or camp)
        cooking_spot = self.get_adjacent_cooking_spot(char)
        if not cooking_spot:
            return False
        
        # Must have wheat to convert
        if char.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
            return False
        
        # Must have space for bread
        if not char.can_add_item('bread', 1):
            return False
        
        return True
    

    def bake_bread(self, char, amount=1, log_errors=True):
        """Convert wheat into bread at a stove or campfire.

        Performs ALL validation and logging. This is the single source of truth for baking.

        Args:
            char: Character attempting to bake
            amount: Number of bread to bake (default 1)
            log_errors: If True, log detailed error messages for failures (default True)

        Returns:
            Amount of bread actually baked (0 if failed)
        """
        # Check for adjacent cooking spot
        cooking_spot = self.get_adjacent_cooking_spot(char)
        if not cooking_spot:
            if log_errors:
                # Give helpful feedback - check if stove exists but can't use it
                stove = self.state.interactables.get_adjacent_stove(char)
                if stove and not stove.can_use(char):
                    self.log_bake_error(char, 'not_your_stove')
                else:
                    self.log_bake_error(char, 'no_stove')
            return 0

        # Check wheat availability
        if char.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
            if log_errors:
                self.log_bake_error(char, 'no_wheat')
            return 0

        # Check inventory space
        if not char.can_add_item('bread', 1):
            if log_errors:
                self.log_bake_error(char, 'inventory_full')
            return 0

        wheat_available = char.get_item('wheat')
        max_from_wheat = wheat_available // WHEAT_TO_BREAD_RATIO

        # Calculate how much we can actually bake
        # Limited by: requested amount, available wheat, inventory space
        to_bake = min(amount, max_from_wheat)

        # Check inventory space iteratively (in case we can only fit some)
        actually_baked = 0
        for _ in range(to_bake):
            if not char.can_add_item('bread', 1):
                break
            if char.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
                break

            # Convert wheat to bread
            char.remove_item('wheat', WHEAT_TO_BREAD_RATIO)
            char.add_item('bread', 1)
            actually_baked += 1

        if actually_baked > 0:
            spot_name = cooking_spot['name']
            self.state.log_action(f"{char.get_display_name()} baked {actually_baked} bread at {spot_name}")

        return actually_baked


    def get_nearest_cooking_spot(self, char):
        """Find the nearest cooking spot the character can use (their stoves or any campfire).
        Returns (cooking_spot_dict, position) or (None, None).
        """
        best_spot = None
        best_pos = None
        best_dist = float('inf')
        
        # Check stoves the character can use (home matches and same zone)
        char_zone = getattr(char, 'zone', None)
        for stove in self.state.interactables.stoves.values():
            if not stove.can_use(char):
                continue
            # Only consider stoves in the same zone
            if stove.zone != char_zone:
                continue
            stove_cx = stove.x + 0.5
            stove_cy = stove.y + 0.5
            dist = math.sqrt((char['x'] - stove_cx) ** 2 + (char['y'] - stove_cy) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_spot = {
                    'type': 'stove',
                    'name': stove.name,
                    'source': stove
                }
                best_pos = (stove_cx, stove_cy)
        
        # Check campfires (anyone can use any campfire)
        for other_char in self.state.characters:
            camp_pos = other_char.get('camp_position')
            if camp_pos:
                cx, cy = camp_pos
                camp_center = (cx + 0.5, cy + 0.5)
                dist = math.sqrt((char['x'] - camp_center[0]) ** 2 + (char['y'] - camp_center[1]) ** 2)
                if dist < best_dist:
                    best_dist = dist
                    owner_name = other_char.get_display_name()
                    best_spot = {
                        'type': 'camp',
                        'name': f"{owner_name}'s campfire",
                        'source': camp_pos
                    }
                    best_pos = camp_center
        
        return best_spot, best_pos
    

    def get_nearest_stove(self, char):
        """Find the nearest stove the character can use. Returns (stove, position) or (None, None)."""
        best_stove = None
        best_pos = None
        best_dist = float('inf')

        char_zone = getattr(char, 'zone', None)
        for stove in self.state.interactables.stoves.values():
            if not stove.can_use(char):
                continue
            # Only consider stoves in the same zone
            if stove.zone != char_zone:
                continue
            stove_cx = stove.x + 0.5
            stove_cy = stove.y + 0.5
            dist = math.sqrt((char['x'] - stove_cx) ** 2 + (char['y'] - stove_cy) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_stove = stove
                best_pos = (stove_cx, stove_cy)

        return best_stove, best_pos


    def has_access_to_cooking(self, char):
        """Check if character has access to any cooking spot (stove they can use or any camp)."""
        # Check for stoves they can use
        if self.state.interactables.get_stoves_for_char(char):
            return True
        
        # Check for any campfire
        for other_char in self.state.characters:
            if other_char.get('camp_position'):
                return True
        
        return False
    

        """Attempt to buy goods from the nearest willing vendor.
        
        Returns True if a purchase was made or if moving toward a vendor.
        """
        name = char.get_display_name()
        
        # Check if we can afford anything
        if not self.can_afford_goods(char, goods_type):
            return False
        
        # First check if adjacent to a willing vendor
        adjacent_vendor = self.find_adjacent_vendor(char, goods_type)
        if adjacent_vendor and self.vendor_willing_to_trade(adjacent_vendor, char, goods_type):
            amount = self.get_max_vendor_trade_amount(adjacent_vendor, char, goods_type)
            if amount > 0:
                price = self.get_goods_price(goods_type, amount)
                vendor_name = adjacent_vendor.get_display_name()
                
                if self.execute_vendor_trade(adjacent_vendor, char, goods_type, amount):
                    self.state.log_action(f"{name} bought {amount} {goods_type} for ${price} from {vendor_name}")
                    char['wheat_seek_ticks'] = 0  # Reset seek timer
                    return True
        
        # Otherwise, move toward nearest willing vendor
        willing_vendor = self.find_willing_vendor(char, goods_type)
        if willing_vendor:
            self.move_toward_character(char, willing_vendor)
            return True
        
        return False

    
    # PERCEPTION SYSTEM (Vision Cones and Sound Radii)
    

    # =============================================================================
    # CAMPFIRE & ENVIRONMENT
    # =============================================================================
    # Camp making and outdoor survival
    # =============================================================================

    def get_sleep_position(self, char):
        """Get the position where this character should sleep.
        Returns bed position if they own one, camp position if they have one, None otherwise.
        """
        # Check for owned bed
        bed = self.state.get_character_bed(char)
        if bed:
            return bed.position
        
        # Check for existing camp
        if char.get('camp_position'):
            return char['camp_position']
        
        return None
    

    def can_make_camp_at(self, x, y):
        """Check if a camp can be made at this position.
        Works with float positions - checks the cell containing the point.
        Cannot make camp on village grounds or on any farm.
        """
        cell_x = int(x)
        cell_y = int(y)
        if not self.state.is_position_valid(cell_x, cell_y):
            return False
        # Cannot camp in village areas
        if self.state.is_in_village(cell_x, cell_y):
            return False
        # Cannot camp on farm cells
        if (cell_x, cell_y) in self.state.farm_cells:
            return False
        return True
    

    def make_camp(self, char):
        """Make a camp at the character's current position if possible.
        Returns True if camp was made. Stores camp position as cell coordinates.
        """
        # Get the cell the character is in
        cell_x = int(char['x'])
        cell_y = int(char['y'])
        if self.can_make_camp_at(cell_x, cell_y):
            char['camp_position'] = (cell_x, cell_y)
            name = char.get_display_name()
            self.state.log_action(f"{name} made a camp at ({cell_x}, {cell_y})")
            return True
        return False
    
    

    def get_adjacent_camp(self, char):
        """Get any camp adjacent to the character.
        Returns (camp_position, owner_char) tuple or (None, None).
        Note: Camps are stored on characters, not in interactables.
        """
        for other_char in self.state.characters:
            camp_pos = other_char.get('camp_position')
            if camp_pos and self.state.interactables.is_adjacent_to_camp(char, camp_pos):
                return camp_pos, other_char
        return None, None
    

    def _find_camp_spot(self, char):
        """Find a nearby position where the character can make a camp (outside village).
        Returns float position (center of cell).
        """
        # Try to find nearest valid camp spot
        best_spot = None
        best_dist = float('inf')
        
        for y in range(SIZE):
            for x in range(SIZE):
                if self.can_make_camp_at(x, y) and not self.state.is_occupied(x, y):
                    # Calculate distance to center of this cell
                    cx, cy = x + 0.5, y + 0.5
                    dist = math.sqrt((cx - char['x']) ** 2 + (cy - char['y']) ** 2)
                    if dist < best_dist:
                        best_dist = dist
                        best_spot = (cx, cy)
        
        return best_spot
    

    def can_build_campfire(self, player):
        """Check if player can build a campfire at current location."""
        if not player:
            return False

        # Can't build campfire in interior
        if player.zone is not None:
            return False

        # Can't build campfire if already has one
        if player.get('camp_position'):
            return False

        return True


    # =============================================================================
    # DIALOGUE SYSTEM
    # =============================================================================
    # NPC conversation management
    # =============================================================================

    def can_start_dialogue(self, npc):
        """
        Check if dialogue can be started with the given NPC.

        Args:
            npc: Character to check

        Returns:
            True if dialogue is possible
        """
        if npc is None:
            return False

        # Can't talk to yourself
        if npc.is_player:
            return False

        # Check NPC's intent - cannot talk if they're attacking
        intent = npc.intent
        if intent and intent.get('action') == 'attack':
            return False

        # Can talk if fleeing (per user request)
        # Can talk in all other states (idle, wandering, working, etc.)

        return True


    def start_dialogue(self, npc, player):
        """
        Start a dialogue between player and NPC.

        Args:
            npc: NPC character to talk to
            player: Player character

        Returns:
            dict with 'success': bool and 'saved_state': dict if successful
        """
        if not self.can_start_dialogue(npc):
            return {'success': False}

        # Save NPC's current state to restore later
        saved_state = {
            'intent': npc.intent,
            'goal': npc.goal
        }

        # Make NPC face the player and stop moving
        if player:
            self.make_character_face_character(npc, player)

        npc.vx = 0
        npc.vy = 0
        npc.goal = None  # Clear movement goal

        return {'success': True, 'saved_state': saved_state}


    def end_dialogue(self, npc, saved_state):
        """
        End a dialogue and restore NPC state.

        Args:
            npc: NPC character
            saved_state: State dict from start_dialogue
        """
        if not npc or not saved_state:
            return

        # Restore NPC state (only restore goal, let AI decide new intent)
        npc.goal = saved_state.get('goal')


    def update_dialogue(self, npc, player):
        """
        Update dialogue state - keeps NPC facing player and stationary.

        Args:
            npc: NPC character in dialogue
            player: Player character
        """
        if not npc or not player:
            return

        # Keep NPC facing player and stationary
        npc.vx = 0
        npc.vy = 0
        self.make_character_face_character(npc, player)


    def make_character_face_character(self, character, target):
        """
        Make a character face toward another character (8-directional).

        Args:
            character: Character to turn
            target: Character to face toward
        """
        if not character or not target:
            return

        import math

        # Use prevailing coords for same-zone calculation
        if character.zone == target.zone:
            dx = target.prevailing_x - character.prevailing_x
            dy = target.prevailing_y - character.prevailing_y
        else:
            dx = target.x - character.x
            dy = target.y - character.y

        # Determine 8-direction facing based on angle
        angle = math.atan2(dy, dx)

        # Convert to 8 directions
        if angle >= -math.pi/8 and angle < math.pi/8:
            character.facing = 'right'
        elif angle >= math.pi/8 and angle < 3*math.pi/8:
            character.facing = 'down-right'
        elif angle >= 3*math.pi/8 and angle < 5*math.pi/8:
            character.facing = 'down'
        elif angle >= 5*math.pi/8 and angle < 7*math.pi/8:
            character.facing = 'down-left'
        elif angle >= 7*math.pi/8 or angle < -7*math.pi/8:
            character.facing = 'left'
        elif angle >= -7*math.pi/8 and angle < -5*math.pi/8:
            character.facing = 'up-left'
        elif angle >= -5*math.pi/8 and angle < -3*math.pi/8:
            character.facing = 'up'
        elif angle >= -3*math.pi/8 and angle < -math.pi/8:
            character.facing = 'up-right'

    # ENVIRONMENT QUERIES


    # =============================================================================
    # ENVIRONMENT QUERIES
    # =============================================================================
    # Finding nearby objects, NPCs, and interactive elements
    # =============================================================================

    def get_nearest_interactable_npc(self, player, max_distance=ADJACENCY_DISTANCE):
        """
        Find the nearest NPC that the player can interact with.

        Args:
            player: Player character
            max_distance: Maximum distance to check

        Returns:
            Nearest NPC character, or None if none in range
        """
        if not player:
            return None

        nearest_npc = None
        nearest_dist = float('inf')

        for char in self.state.characters:
            if char.is_player:
                continue

            # Must be in same zone
            if char.zone != player.zone:
                continue

            # Calculate distance using prevailing coords
            dx = char.prevailing_x - player.prevailing_x
            dy = char.prevailing_y - player.prevailing_y
            dist = (dx * dx + dy * dy) ** 0.5

            if dist <= max_distance and dist < nearest_dist:
                nearest_dist = dist
                nearest_npc = char

        return nearest_npc

    # DIALOGUE SYSTEM


    def get_nearby_corpse(self, character, max_distance=1.5):
        """
        Find a corpse near the character in the same zone.

        Args:
            character: Character to search from
            max_distance: Maximum distance to search

        Returns:
            Corpse object if one is nearby, None otherwise
        """
        if not character:
            return None

        import math
        char_zone = character.zone

        for corpse in self.state.corpses:
            # Must be in same zone
            if corpse.zone != char_zone:
                continue

            # Calculate distance using appropriate coordinates
            if char_zone is not None:
                # Interior - use prevailing (local) coords
                dx = character.prevailing_x - (corpse.x + 0.5)
                dy = character.prevailing_y - (corpse.y + 0.5)
            else:
                # Exterior - use world coords
                dx = character.x - (corpse.x + 0.5)
                dy = character.y - (corpse.y + 0.5)

            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= max_distance:
                return corpse

        return None


    def get_nearby_tree(self, character, max_distance=1.5):
        """
        Find a tree near the character (exterior only).

        Args:
            character: Character to search from
            max_distance: Maximum distance to search

        Returns:
            Tree object if one is nearby, None otherwise
        """
        if not character:
            return None

        # Trees only exist in exterior
        if character.zone is not None:
            return None

        import math

        for tree in self.state.interactables.trees.values():
            dx = character.x - (tree.x + 0.5)
            dy = character.y - (tree.y + 0.5)
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= max_distance:
                return tree

        return None


    # =============================================================================
    # PERCEPTION & VISION SYSTEM
    # =============================================================================
    # Vision cones, line of sight, sound radius, and window viewing
    # =============================================================================

    def _update_facing(self, char, dx, dy):
        """Update character's facing direction based on movement delta.
        Uses magnitude comparison to determine if movement is primarily
        horizontal, vertical, or diagonal.
        """
        # Determine primary direction based on magnitude
        if abs(dx) > abs(dy) * 2:
            # Mostly horizontal
            char['facing'] = 'right' if dx > 0 else 'left'
        elif abs(dy) > abs(dx) * 2:
            # Mostly vertical
            char['facing'] = 'down' if dy > 0 else 'up'
        else:
            # Diagonal
            if dx > 0 and dy < 0:
                char['facing'] = 'up-right'
            elif dx > 0 and dy > 0:
                char['facing'] = 'down-right'
            elif dx < 0 and dy < 0:
                char['facing'] = 'up-left'
            else:
                char['facing'] = 'down-left'
    

    def get_facing_vector(self, char):
        """Get unit vector for character's facing direction."""
        facing = char.get('facing', 'down')
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
        return vectors.get(facing, (0, 1))
    

    def _get_perception_coords(self, char):
        """Get the coordinates to use for perception calculations.
        
        Returns prevailing coords when in interior (correct distance scale),
        world coords when in exterior.
        
        Returns:
            (x, y) tuple
        """
        if char.zone:
            return (char.prevailing_x, char.prevailing_y)
        return (char.x, char.y)
    

    def _is_facing_direction(self, char, direction):
        """Check if character is facing a cardinal direction.

        Args:
            char: Character to check
            direction: 'north', 'south', 'east', or 'west'

        Returns:
            True if character's facing aligns with direction
        """
        facing = char.get('facing', 'down')
        return facing in DIRECTION_TO_FACINGS.get(direction, ())
    

    def _get_opposite_direction(self, direction):
        """Get the opposite cardinal direction."""
        return OPPOSITE_DIRECTIONS.get(direction, 'south')
    

    def can_perceive_character(self, observer, target):
        """Check if observer can perceive target character.
        
        Handles zone checks, window viewing, and coordinate selection.
        
        Args:
            observer: Character doing the perceiving
            target: Character being perceived
            
        Returns:
            Tuple of (can_perceive: bool, method: str or None)
            method is 'vision', 'sound', or None
        """
        # Check if observer is viewing through a window (player only)
        window = getattr(observer, 'viewing_through_window', None)
        if window:
            viewing_interior = getattr(observer, 'viewing_into_interior', None)
            
            if viewing_interior is not None:
                # Looking in from outside - target must be in that interior
                if target.zone != viewing_interior.name:
                    return (False, None)
                # Cone originates from window's interior position
                cone_x = window.interior_x + 0.5
                cone_y = window.interior_y + 0.5
                # Target position in interior coords
                target_x = target.prevailing_x
                target_y = target.prevailing_y
                # Direction is inverted (looking into building)
                invert = True
            else:
                # Looking out from inside - target must be in exterior
                if target.zone is not None:
                    return (False, None)
                # Cone originates from window's world position (on the wall)
                cone_x = window.world_x
                cone_y = window.world_y
                # Target position in world coords
                target_x = target.x
                target_y = target.y
                # Direction is window facing
                invert = False
            
            # Check vision cone only (no sound through windows)
            dx = target_x - cone_x
            dy = target_y - cone_y
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist > VISION_RANGE:
                return (False, None)
            if dist < 1.0:
                return (True, 'vision')
            
            # Get window facing direction
            window_facing_vectors = {
                'north': (0, -1),
                'south': (0, 1),
                'east': (1, 0),
                'west': (-1, 0),
            }
            face_x, face_y = window_facing_vectors.get(window.facing, (0, 1))
            
            if invert:
                face_x = -face_x
                face_y = -face_y
            
            # Normalize direction to target
            dir_x = dx / dist
            dir_y = dy / dist
            dot = face_x * dir_x + face_y * dir_y
            
            half_angle = math.radians(VISION_CONE_ANGLE / 2)
            if dot >= math.cos(half_angle):
                # In cone - check line of sight in the target's zone
                target_zone = viewing_interior.name if viewing_interior else None
                if self._check_line_of_sight(cone_x, cone_y, target_x, target_y, target_zone):
                    return (True, 'vision')
            
            return (False, None)
        
        # Check for NPC window-based vision (different zones)
        if observer.zone != target.zone:
            window, looking_in = self.get_window_for_cross_zone_vision(observer, target)
            if window:
                # Set up cone check based on direction
                if looking_in:
                    # Observer outside looking in
                    cone_x = window.interior_x + 0.5
                    cone_y = window.interior_y + 0.5
                    target_x = target.prevailing_x
                    target_y = target.prevailing_y
                    invert = True
                else:
                    # Observer inside looking out
                    cone_x = window.world_x
                    cone_y = window.world_y
                    target_x = target.x
                    target_y = target.y
                    invert = False
                
                # Check vision cone (no sound through windows)
                dx = target_x - cone_x
                dy = target_y - cone_y
                dist = math.sqrt(dx * dx + dy * dy)
                
                if dist > VISION_RANGE:
                    return (False, None)
                if dist < 1.0:
                    return (True, 'vision')
                
                # Get window facing direction
                window_facing_vectors = {
                    'north': (0, -1),
                    'south': (0, 1),
                    'east': (1, 0),
                    'west': (-1, 0),
                }
                face_x, face_y = window_facing_vectors.get(window.facing, (0, 1))
                
                if invert:
                    face_x = -face_x
                    face_y = -face_y
                
                dir_x = dx / dist
                dir_y = dy / dist
                dot = face_x * dir_x + face_y * dir_y
                
                half_angle = math.radians(VISION_CONE_ANGLE / 2)
                if dot >= math.cos(half_angle):
                    # In cone - check line of sight in the target's zone
                    if self._check_line_of_sight(cone_x, cone_y, target_x, target_y, target.zone):
                        return (True, 'vision')
            
            # No valid window = can't perceive across zones
            return (False, None)
        
        # Get correct coordinates based on zone
        target_x, target_y = self._get_perception_coords(target)
        
        return self.can_perceive_event(observer, target_x, target_y, event_zone=target.zone)
    

    def _get_vision_obstacles(self, zone):
        """Get obstacles that block vision for a given zone.
        
        Args:
            zone: Interior name or None for exterior
            
        Returns:
            List of (x, y, half_width) tuples for obstacles
        """
        obstacles = []
        
        if zone is None:
            # Exterior - trees block vision
            for pos in self.state.interactables.trees:
                x, y = pos
                obstacles.append((x + 0.5, y + 0.5, 0.4))  # Tree center, radius ~0.4
            
            # House walls block vision (use bounds)
            for house in self.state.interactables.houses.values():
                y_start, x_start, y_end, x_end = house.bounds
                # Add wall segments as obstacles
                # For simplicity, treat each cell of the house perimeter as an obstacle
                for hx in range(x_start, x_end):
                    obstacles.append((hx + 0.5, y_start + 0.5, 0.5))  # North wall
                    obstacles.append((hx + 0.5, y_end - 0.5, 0.5))    # South wall
                for hy in range(y_start, y_end):
                    obstacles.append((x_start + 0.5, hy + 0.5, 0.5))  # West wall
                    obstacles.append((x_end - 0.5, hy + 0.5, 0.5))    # East wall
        else:
            # Interior - stoves block vision, beds don't (too low)
            interior = self.state.interiors.get_interior(zone)
            if interior:
                # Check stoves in this interior (zone matches interior name)
                for stove in self.state.interactables.stoves.values():
                    if stove.zone != zone:
                        continue
                    # Stove is in interior coords
                    obstacles.append((stove.x + 0.5, stove.y + 0.5, 0.4))
        
        return obstacles
    

    def _line_intersects_circle(self, x1, y1, x2, y2, cx, cy, radius):
        """Check if line segment from (x1,y1) to (x2,y2) intersects circle at (cx,cy).
        
        Returns:
            Distance to intersection point, or None if no intersection
        """
        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1
        
        # Vector from p1 to circle center
        fx = x1 - cx
        fy = y1 - cy
        
        a = dx * dx + dy * dy
        b = 2 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - radius * radius
        
        discriminant = b * b - 4 * a * c
        
        if discriminant < 0:
            return None  # No intersection
        
        discriminant = math.sqrt(discriminant)
        
        # Two possible intersection points
        t1 = (-b - discriminant) / (2 * a)
        t2 = (-b + discriminant) / (2 * a)
        
        # Check if intersection is within line segment (t in [0, 1])
        if 0 <= t1 <= 1:
            return t1 * math.sqrt(a)  # Return distance
        if 0 <= t2 <= 1:
            return t2 * math.sqrt(a)
        
        return None
    

    def _check_line_of_sight(self, from_x, from_y, to_x, to_y, zone):
        """Check if there's clear line of sight between two points.
        
        Args:
            from_x, from_y: Observer position
            to_x, to_y: Target position
            zone: Interior name or None for exterior
            
        Returns:
            True if line of sight is clear, False if blocked
        """
        obstacles = self._get_vision_obstacles(zone)
        
        for ox, oy, radius in obstacles:
            # Skip if obstacle is at observer or target position
            if abs(ox - from_x) < 0.3 and abs(oy - from_y) < 0.3:
                continue
            if abs(ox - to_x) < 0.3 and abs(oy - to_y) < 0.3:
                continue
            
            if self._line_intersects_circle(from_x, from_y, to_x, to_y, ox, oy, radius):
                return False  # Blocked
        
        return True  # Clear line of sight
    

    def is_point_in_vision_cone(self, observer, target_x, target_y):
        """Check if a specific point is within observer's vision cone.
        
        Args:
            observer: Character doing the looking
            target_x, target_y: Point to check (should be in same coord space as observer)
            
        Returns:
            True if point is within vision cone AND line of sight is clear
        """
        # Get observer position in correct coordinate space
        obs_x, obs_y = self._get_perception_coords(observer)
        
        # Get vector from observer to target
        dx = target_x - obs_x
        dy = target_y - obs_y
        dist = math.sqrt(dx * dx + dy * dy)
        
        # Too far to see
        if dist > VISION_RANGE:
            return False
        
        # Very close - can always see (within 1 cell)
        if dist < 1.0:
            return True
        
        # Normalize
        dx /= dist
        dy /= dist
        
        # Get observer's facing direction
        face_x, face_y = self.get_facing_vector(observer)
        
        # Calculate angle between facing and target direction
        # dot product = cos(angle)
        dot = dx * face_x + dy * face_y
        
        # Convert cone angle to cosine threshold
        # VISION_CONE_ANGLE is total angle, so half for each side
        half_angle_rad = math.radians(VISION_CONE_ANGLE / 2)
        cos_threshold = math.cos(half_angle_rad)
        
        if dot < cos_threshold:
            return False  # Not in cone angle
        
        # In cone - check line of sight
        return self._check_line_of_sight(obs_x, obs_y, target_x, target_y, observer.zone)
    

    def _does_vision_cone_overlap_circle_coords(self, obs_x, obs_y, facing, circle_x, circle_y, circle_radius):
        """Check if vision cone overlaps with a circle using explicit coordinates.
        
        Args:
            obs_x, obs_y: Observer position
            facing: Observer facing direction
            circle_x, circle_y: Center of the circle
            circle_radius: Radius of the circle
            
        Returns:
            True if vision cone overlaps the circle
        """
        # Distance from observer to circle center
        dx = circle_x - obs_x
        dy = circle_y - obs_y
        dist_to_center = math.sqrt(dx * dx + dy * dy)
        
        # If observer is inside the circle, they can see it
        if dist_to_center <= circle_radius:
            return True
        
        # Check if center is in vision cone
        if self._is_point_in_vision_cone_coords(obs_x, obs_y, facing, circle_x, circle_y):
            return True
        
        # Check closest point on circle to observer
        if dist_to_center > 0:
            to_obs_x = -dx / dist_to_center
            to_obs_y = -dy / dist_to_center
            closest_x = circle_x + to_obs_x * circle_radius
            closest_y = circle_y + to_obs_y * circle_radius
            if self._is_point_in_vision_cone_coords(obs_x, obs_y, facing, closest_x, closest_y):
                return True
        
        return False
    

    def _is_point_in_vision_cone_coords(self, obs_x, obs_y, facing, target_x, target_y, zone=None):
        """Check if point is in vision cone using explicit coordinates."""
        dx = target_x - obs_x
        dy = target_y - obs_y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist > VISION_RANGE:
            return False
        if dist < 1.0:
            return True
        
        dx /= dist
        dy /= dist
        
        # Get facing vector
        face_vectors = {
            'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0),
            'up-left': (-0.707, -0.707), 'up-right': (0.707, -0.707),
            'down-left': (-0.707, 0.707), 'down-right': (0.707, 0.707)
        }
        face_x, face_y = face_vectors.get(facing, (0, 1))
        
        dot = dx * face_x + dy * face_y
        half_angle_rad = math.radians(VISION_CONE_ANGLE / 2)
        cos_threshold = math.cos(half_angle_rad)
        
        if dot < cos_threshold:
            return False
        
        return self._check_line_of_sight(obs_x, obs_y, target_x, target_y, zone)
    

    def does_vision_cone_overlap_circle(self, observer, circle_x, circle_y, circle_radius):
        """Check if observer's vision cone overlaps with a circle (sound radius).
        
        We check if any part of the circle is visible:
        - Center of circle in cone, OR
        - Edge of circle (toward observer) in cone
        
        Args:
            observer: Character with vision cone
            circle_x, circle_y: Center of the circle (should be in same coord space as observer)
            circle_radius: Radius of the circle
            
        Returns:
            True if vision cone overlaps the circle
        """
        # Get observer position in correct coordinate space
        obs_x, obs_y = self._get_perception_coords(observer)
        
        # Distance from observer to circle center
        dx = circle_x - obs_x
        dy = circle_y - obs_y
        dist_to_center = math.sqrt(dx * dx + dy * dy)
        
        # If observer is inside the circle, they can see it
        if dist_to_center <= circle_radius:
            return True
        
        # Check if center is in vision cone
        if self.is_point_in_vision_cone(observer, circle_x, circle_y):
            return True
        
        # Check closest point on circle to observer
        # This is along the line from circle center toward observer
        if dist_to_center > 0:
            # Direction from circle to observer
            to_obs_x = -dx / dist_to_center
            to_obs_y = -dy / dist_to_center
            # Closest point on circle edge
            closest_x = circle_x + to_obs_x * circle_radius
            closest_y = circle_y + to_obs_y * circle_radius
            if self.is_point_in_vision_cone(observer, closest_x, closest_y):
                return True
        
        return False
    

    def do_circles_overlap(self, x1, y1, r1, x2, y2, r2):
        """Check if two circles overlap."""
        dx = x2 - x1
        dy = y2 - y1
        dist = math.sqrt(dx * dx + dy * dy)
        return dist <= (r1 + r2)
    

    def can_perceive_event(self, witness, event_x, event_y, sound_radius=None, event_zone=None):
        """Check if witness can perceive an event at a location.
        
        A witness perceives an event if:
        - Their VISION CONE overlaps with the event's SOUND RADIUS, OR
        - Their SOUND RADIUS overlaps with the event's SOUND RADIUS
        
        Args:
            witness: Character who might perceive
            event_x, event_y: Position of the event (world coords or prevailing if same zone)
            sound_radius: Radius of sound emitted by event (default SOUND_RADIUS)
            event_zone: Zone the event is in (for coord conversion)
            
        Returns:
            Tuple of (can_perceive: bool, method: str or None)
            method is 'vision', 'sound', or None
        """
        if sound_radius is None:
            sound_radius = SOUND_RADIUS
        
        # Get coords in correct space - if same zone, use prevailing-style coords
        wit_x, wit_y = self._get_perception_coords(witness)
        
        # If event is in same zone as witness, coords should already be in local space
        # If different zones, use world coords for both
        if event_zone is not None and witness.zone == event_zone:
            # Same interior - event coords should be prevailing (local)
            evt_x, evt_y = event_x, event_y
        elif witness.zone is None and event_zone is None:
            # Both exterior - use world coords
            evt_x, evt_y = event_x, event_y
        else:
            # Different zones - can't perceive across zones
            return (False, None)
        
        # Check if witness's vision cone overlaps event's sound radius
        if self._does_vision_cone_overlap_circle_coords(wit_x, wit_y, witness.get('facing', 'down'), 
                                                         evt_x, evt_y, sound_radius):
            return (True, 'vision')
        
        # Check if witness's hearing radius overlaps event's sound radius
        if self.do_circles_overlap(wit_x, wit_y, SOUND_RADIUS, 
                                   evt_x, evt_y, sound_radius):
            return (True, 'sound')
        
        return (False, None)
    
    # Criminal Status and Memory
    

    def _update_facing_from_velocity(self, char):
        """Update character's facing direction based on velocity.
        
        If char has a 'face_target' set (another character), face them instead
        of the movement direction. This allows backpedaling.
        """
        # Check for face_target override first
        face_target = char.get('face_target')
        if face_target and face_target in self.state.characters:
            self._face_toward_character(char, face_target)
            return
        
        vx = char.get('vx', 0.0)
        vy = char.get('vy', 0.0)
        
        if abs(vx) < 0.01 and abs(vy) < 0.01:
            return  # Not moving
        
        # Determine primary direction
        if abs(vx) > abs(vy) * 2:
            # Mostly horizontal
            char['facing'] = 'right' if vx > 0 else 'left'
        elif abs(vy) > abs(vx) * 2:
            # Mostly vertical
            char['facing'] = 'down' if vy > 0 else 'up'
        else:
            # Diagonal
            if vx > 0 and vy < 0:
                char['facing'] = 'up-right'
            elif vx > 0 and vy > 0:
                char['facing'] = 'down-right'
            elif vx < 0 and vy < 0:
                char['facing'] = 'up-left'
            else:
                char['facing'] = 'down-left'
    

    def _get_window_facing_at(self, interior, local_x, local_y, threshold=1.0):
        """Check if position is near a window and return its facing direction.
        
        Args:
            interior: The interior to check
            local_x, local_y: Position in interior local coords
            threshold: How close to window to count as "at" it
            
        Returns:
            Window facing direction ('north', 'south', 'east', 'west') or None
        """
        if not interior:
            return None
        
        for window in interior.windows:
            # Distance from character to window position
            dx = local_x - (window.interior_x + 0.5)
            dy = local_y - (window.interior_y + 0.5)
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist < threshold:
                return window.facing
        
        return None
    

    # =============================================================================
    # CRIME & MEMORY SYSTEM
    # =============================================================================
    # Criminal status, memories, and defender logic
    # =============================================================================

    def is_known_criminal(self, char):
        """Check if this character is known as a criminal by anyone.
        
        Checks if char has committed a crime (self-knowledge).
        """
        return char.has_committed_crime()
    

    def find_nearby_defender(self, char, max_distance, exclude=None):
        """Find a defender within range.
        
        Logic:
        - Characters with allegiance first look for soldiers of same allegiance
        - If no soldiers found (or no allegiance), look for general defenders
        - General defenders: anyone with morality >= 7 and confidence >= 7
        - Skip anyone the character knows is a criminal (from their memories)
        
        Args:
            char: The character looking for a defender
            max_distance: Maximum distance to search
            exclude: Character to exclude (e.g., the attacker/threat)
        """
        char_allegiance = char.get('allegiance')
        
        best_soldier = None
        best_soldier_dist = float('inf')
        best_general = None
        best_general_dist = float('inf')
        
        for other in self.state.characters:
            if other == char:
                continue
            # Skip the threat/attacker
            if exclude and other == exclude:
                continue
            # Skip dying characters
            if other.get('health', 100) <= 0:
                continue
            # Skip anyone this character knows is a criminal
            if char.has_memory_of('crime', other):
                continue
            
            dist = self.state.get_distance(char, other)
            if dist > max_distance:
                continue
            
            morality = other.get_trait('morality')
            confidence = other.get_trait('confidence')
            is_soldier = other.get('job') == 'Soldier'
            other_allegiance = other.get('allegiance')
            
            # Check if same-allegiance soldier (only if char has allegiance)
            if char_allegiance and is_soldier and other_allegiance == char_allegiance:
                if dist < best_soldier_dist:
                    best_soldier_dist = dist
                    best_soldier = other
            
            # Check if general defender (high morality + high confidence)
            if morality >= 7 and confidence >= 7:
                if dist < best_general_dist:
                    best_general_dist = dist
                    best_general = other
        
        # Characters with allegiance prefer soldiers, fall back to general defenders
        if char_allegiance and best_soldier:
            return best_soldier
        
        # No soldier found (or no allegiance) - use general defender
        return best_general
    

    def is_defender(self, char):
        """Check if a character will defend others from crime.
        General defenders have morality >= 7 and confidence >= 7.
        Note: Soldiers are handled separately based on allegiance in find_nearby_defender.
        """
        morality = char.get_trait('morality')
        confidence = char.get_trait('confidence')
        return morality >= 7 and confidence >= 7
    

    def get_crime_range(self, crime_type):
        """Get the range for a crime type. The intensity IS the range."""
        if crime_type == 'murder':
            return CRIME_INTENSITY_MURDER
        elif crime_type == 'assault':
            return CRIME_INTENSITY_ASSAULT
        elif crime_type == 'theft':
            return CRIME_INTENSITY_THEFT
        else:
            return 5  # default fallback
    

    def get_flee_distance(self, intensity):
        """Get how far to flee from a criminal. Returns intensity / FLEE_DISTANCE_DIVISOR."""
        return intensity / FLEE_DISTANCE_DIVISOR
    

    def will_care_about_crime(self, responder, crime_allegiance, intensity=None):
        """Does this person care about this crime?
        
        Soldiers: +3 morality bonus for same-allegiance crimes, any intensity
        Others: morality >= 7 required, only for intensity >= 15
        """
        effective_morality = responder.get_trait('morality')
        is_same_allegiance_soldier = (responder.get('job') == 'Soldier' and 
                                    responder.get('allegiance') == crime_allegiance)
        
        if is_same_allegiance_soldier:
            effective_morality += 3
            return effective_morality >= 7
        
        # Non-soldiers only care about serious crimes
        if intensity is not None and intensity < 15:
            return False
        
        return effective_morality >= 7
    

    def find_known_criminal_nearby(self, char):
        """Find any known criminal within range that this character cares about.
        
        Only returns criminals this character KNOWS about (has crime memory).
        Uses perception system - must be able to see or hear the criminal.
        
        Returns (criminal, intensity) or (None, None) if none found.
        """
        # Check crime memories - only react to criminals we actually know about
        for m in char.get_memories(memory_type='crime'):
            criminal = m['subject']
            
            # Skip if criminal is dead/gone
            if criminal not in self.state.characters:
                continue
            if criminal.get('health', 100) <= 0:
                continue
            
            intensity = m.get('intensity', 10)
            crime_allegiance = m['details'].get('victim_allegiance')
            
            # Must be able to perceive the criminal to react to them
            can_perceive, method = self.can_perceive_character(char, criminal)
            if can_perceive:
                if self.will_care_about_crime(char, crime_allegiance, intensity):
                    return (criminal, intensity)
        
        return (None, None)
    

    # =============================================================================
    # CRIME ACTIONS
    # =============================================================================
    # Theft, murder, and criminal behavior
    # =============================================================================

    def get_hunger_factor(self, char):
        """Get hunger factor from 0 (not hungry) to 1 (starving).
        Scales from HUNGER_CHANCE_THRESHOLD (60) down to 0.
        """
        if char['hunger'] >= HUNGER_CHANCE_THRESHOLD:
            return 0.0
        return 1.0 - (char['hunger'] / HUNGER_CHANCE_THRESHOLD)
    

    def should_attempt_farm_theft(self, char):
        """Determine if character will attempt to steal from a farm.
        Returns True if they decide to steal.
        
        Morality 7+: Never steals
        Morality 6: 1% -> 10% based on hunger
        Morality 5: 5% -> 20% based on hunger
        Morality 4-1: 50% -> 100% based on hunger
        """
        morality = char.get_trait('morality')
        
        if morality >= 7:
            return False
        
        # Check cooldown from giving up theft (tick-based)
        cooldown_until_tick = char.get('theft_cooldown_until_tick')
        if cooldown_until_tick and self.state.ticks < cooldown_until_tick:
            return False
        
        hunger_factor = self.get_hunger_factor(char)
        
        if morality == 6:
            chance = 0.01 + (0.09 * hunger_factor)  # 1% to 10%
        elif morality == 5:
            chance = 0.05 + (0.15 * hunger_factor)  # 5% to 20%
        else:  # morality 4, 3, 2, 1
            chance = 0.50 + (0.50 * hunger_factor)  # 50% to 100%
        
        return random.random() < chance
    

    def should_attempt_murder(self, char):
        """Determine if character will attempt to kill someone.
        Returns True if they decide to attack with intent to kill.
        
        Morality 5+: Never attempts murder
        Morality 4-3: Only when starving, +10% per tick starving
        Morality 2-1: Same chance as farm theft (50-100% based on hunger)
        """
        morality = char.get_trait('morality')
        
        if morality >= 5:
            return False
        
        if morality >= 3:  # Morality 4-3
            # Only kills when starving
            if not char.get('is_starving', False):
                return False
            # 10% per tick starving
            ticks_starving = char.get('ticks_starving', 0)
            chance = 0.10 * ticks_starving
            return random.random() < min(1.0, chance)
        else:  # Morality 2-1
            # Same chance as farm theft
            hunger_factor = self.get_hunger_factor(char)
            chance = 0.50 + (0.50 * hunger_factor)  # 50% to 100%
            return random.random() < chance
    

    def decide_crime_action(self, char):
        """Decide what crime action (if any) to take.
        Returns: 'theft', 'murder', or None
        
        For morality 2-1, if both theft and murder would trigger,
        randomly choose between them (50/50).
        """
        morality = char.get_trait('morality')
        
        if morality >= 7:
            return None
        
        will_steal = self.should_attempt_farm_theft(char)
        will_kill = self.should_attempt_murder(char)
        
        if morality <= 2:
            # Equal chance between theft and murder if both trigger
            if will_steal and will_kill:
                return random.choice(['theft', 'murder'])
            elif will_steal:
                return 'theft'
            elif will_kill:
                return 'murder'
        else:
            # Morality 3-6: prioritize theft over murder
            if will_steal:
                return 'theft'
            elif will_kill:
                return 'murder'
        
        return None
    

    def find_nearby_ready_farm_cell(self, char):
        """Find a ready farm cell nearby that the character could steal from."""
        best_cell = None
        best_dist = float('inf')
        
        for (cx, cy), data in self.state.farm_cells.items():
            if data['state'] == 'ready':
                dist = abs(cx - char['x']) + abs(cy - char['y'])
                if dist < best_dist:
                    best_dist = dist
                    best_cell = (cx, cy)
        
        return best_cell
    

    def get_farm_waiting_position(self, char):
        """Get a position near the farm to wait for crops."""
        # Find any farm cell and return a position adjacent to the farm area
        if not self.state.farm_cells:
            return None
        
        # Get the farm area bounds
        farm_cells = list(self.state.farm_cells.keys())
        min_x = min(c[0] for c in farm_cells)
        max_x = max(c[0] for c in farm_cells)
        min_y = min(c[1] for c in farm_cells)
        max_y = max(c[1] for c in farm_cells)
        
        # Return center of farm area
        return ((min_x + max_x) / 2 + 0.5, (min_y + max_y) / 2 + 0.5)
    

    def try_farm_theft(self, char):
        """Character attempts to steal from a farm. Returns True if action taken."""
        # If already pursuing theft, continue
        if char.get('theft_target') or char.get('theft_waiting'):
            return self.continue_theft(char)
        
        cell = self.find_nearby_ready_farm_cell(char)
        name = char.get_display_name()
        
        if cell:
            # Start pursuing the cell (not a crime yet - just walking to farm)
            char['theft_target'] = cell
            char['theft_start_tick'] = self.state.ticks
            self.state.log_action(f"{name} heading toward farm at {cell}")
        else:
            # No ready cells - go wait at the farm
            char['theft_waiting'] = True
            char['theft_start_tick'] = self.state.ticks
            self.state.log_action(f"{name} heading to farm to steal")
        
        return self.continue_theft(char)
    

    def continue_theft(self, char):
        """Continue theft in progress. Returns True if still stealing."""
        cell = char.get('theft_target')
        name = char.get_display_name()
        
        # Check if we've been trying too long (tick-based, scales with game speed)
        start_tick = char.get('theft_start_tick')
        if start_tick and self.state.ticks - start_tick > THEFT_PATIENCE_TICKS:
            char['theft_target'] = None
            char['theft_waiting'] = False
            char['theft_start_tick'] = None
            char['theft_cooldown_until_tick'] = self.state.ticks + THEFT_COOLDOWN_TICKS
            self.state.log_action(f"{name} gave up waiting to steal from farm")
            return False
        
        if not cell:
            # No specific cell - look for one or wait
            cell = self.find_nearby_ready_farm_cell(char)
            if cell:
                char['theft_target'] = cell
                char['theft_waiting'] = False
                self.state.log_action(f"{name} heading toward farm at {cell}")
            else:
                # No ready cells - mark as waiting
                if not char.get('theft_waiting'):
                    char['theft_waiting'] = True
                    self.state.log_action(f"{name} waiting at farm for crops to grow")
                return True  # Still in theft mode, just waiting
        
        cx, cy = cell
        
        # Check if cell is still ready
        data = self.state.farm_cells.get(cell)
        if not data or data['state'] != 'ready':
            # Cell no longer available - try to find another
            char['theft_target'] = None
            new_cell = self.find_nearby_ready_farm_cell(char)
            if new_cell:
                char['theft_target'] = new_cell
                char['theft_waiting'] = False
                self.state.log_action(f"{name} heading toward farm at {new_cell}")
            else:
                # No ready cells - wait at farm
                if not char.get('theft_waiting'):
                    char['theft_waiting'] = True
                    self.state.log_action(f"{name} waiting at farm for crops to grow")
            return True
        
        # If standing on the cell (character's cell position matches), steal immediately
        # Convert float position to cell coordinates
        char_cell = (int(char['x']), int(char['y']))
        if char_cell == cell:
            # Check if has inventory space
            if not char.can_add_item('wheat', FARM_CELL_YIELD):
                char['theft_target'] = None
                char['theft_waiting'] = False
                char['theft_start_tick'] = None
                return False
            
            # Execute the theft - THE CRIMINAL ACT
            char.add_item('wheat', FARM_CELL_YIELD)
            # Leave cell in replanting state (brown) - only farmers can turn it yellow
            data['state'] = 'replanting'
            data['timer'] = FARM_REPLANT_TIME
            
            # Clear theft state
            char['theft_target'] = None
            char['theft_waiting'] = False
            char['theft_start_tick'] = None
            
            self.state.log_action(f"{name} STOLE {FARM_CELL_YIELD} wheat from farm!")
            self.witness_theft(char, cell)  # Records crime in memory system
            return True
        
        # Still in transit - movement handled by _get_goal
        return True
    

    def witness_theft(self, thief, cell):
        """Witnesses within perception range learn about the theft and may react.
        
        Uses perception system - witness's vision cone or sound radius must
        overlap with thief's sound radius.
        """
        thief_name = thief.get_display_name()
        cx, cy = cell
        intensity = CRIME_INTENSITY_THEFT
        
        # Sound emanates from the thief - use correct coords for zone
        event_x, event_y = self._get_perception_coords(thief)
        
        # Get the farm's allegiance (this is the crime allegiance)
        crime_allegiance = self.state.get_farm_cell_allegiance(cx, cy)
        
        # Thief records they committed theft (self-knowledge)
        thief.add_memory('committed_crime', thief, self.state.ticks,
                        location=(cx, cy),
                        intensity=intensity,
                        source='self',
                        crime_type='theft',
                        target_location=cell)
        
        for char in self.state.characters:
            if char is thief:
                continue
            
            # Check if can perceive - this handles window viewing and zone checks
            can_perceive, method = self.can_perceive_character(char, thief)
            
            if can_perceive:
                witness_name = char.get_display_name()
                
                # Everyone who perceives it remembers the crime
                char.add_memory('crime', thief, self.state.ticks,
                               location=(cx, cy),
                               intensity=intensity,
                               source='witnessed' if method == 'vision' else 'heard',
                               reported=False,
                               crime_type='theft',
                               victim=None,  # Theft doesn't have a direct victim
                               victim_allegiance=crime_allegiance,
                               perception_method=method)
                
                # Check if this witness cares
                cares = self.will_care_about_crime(char, crime_allegiance, intensity)
                
                # Check if this is the farm owner (always reacts as victim)
                cell_data = self.state.farm_cells.get((cx, cy), {})
                is_owner = (char.get('job') == 'Farmer' and 
                           char.get('home') and 
                           cell_data.get('home') == char.get('home'))
                
                perception_verb = "WITNESSED" if method == 'vision' else "HEARD"
                
                if cares or is_owner:
                    confidence = char.get_trait('confidence')
                    if confidence >= 7:
                        char.set_intent('attack', thief, reason='witnessed_theft', started_tick=self.state.ticks)
                        self.state.log_action(f"{witness_name} {perception_verb} {thief_name} stealing! Attacking!")
                    else:
                        char.set_intent('flee', thief, reason='witnessed_theft', started_tick=self.state.ticks)
                        self.state.log_action(f"{witness_name} {perception_verb} {thief_name} stealing! Fleeing!")
                else:
                    self.state.log_action(f"{witness_name} {perception_verb.lower()} {thief_name} stealing.")
    

    def find_richest_target(self, robber):
        """Find the best target to rob"""
        targets = [c for c in self.state.characters if c != robber and (c.get_item('gold') > 0 or c.get_item('wheat') > 0)]
        if not targets:
            return None
        return max(targets, key=lambda c: (c.get_item('wheat'), c.get_item('gold')))
    

    def try_murder(self, attacker):
        """Character decides to attack someone with intent to kill - sets intent and starts pursuit.
        No crime is committed until actual swing (handled in resolve_melee_attack).
        """
        target = self.find_richest_target(attacker)
        if target:
            attacker_name = attacker.get_display_name()
            target_name = target.get_display_name()
            self.state.log_action(f"{attacker_name} is hunting {target_name}!")
            
            # Set attack intent - no crime until actual swing
            attacker.set_intent('attack', target, reason='murder_intent', started_tick=self.state.ticks)
            
            return self.continue_murder(attacker)
        return False
    

    def continue_murder(self, attacker):
        """Continue murder pursuit - returns True if still pursuing"""
        if attacker.intent is None or attacker.intent.get('action') != 'attack':
            return False
        
        target = attacker.intent.get('target')
        
        if attacker not in self.state.characters:
            return False
        
        if target is None or target not in self.state.characters:
            attacker.clear_intent()
            return False
        
        # Don't attack dying characters
        if target.get('health', 100) <= 0:
            attacker.clear_intent()
            return False
        
        # Movement is handled by velocity system in _get_goal
        # Check weapon type - ranged weapons can attack from distance, melee requires adjacency

        weapon_type = attacker.get_equipped_weapon_type()

        if weapon_type == 'ranged':
            # Bow attack - can attack from range
            # Check if already drawing bow
            if attacker.is_drawing_bow():
                # Continue drawing - check if fully drawn
                if attacker.get_bow_draw_progress(self.state.ticks) >= 1.0:
                    # Fully drawn - fire!
                    # Calculate angle to target
                    import math
                    dx = target.prevailing_x - attacker.prevailing_x
                    dy = target.prevailing_y - attacker.prevailing_y
                    angle = math.atan2(dy, dx)

                    # Release bow and get final draw progress
                    draw_progress = attacker.release_bow_draw(self.state.ticks)

                    # Fire arrow via centralized logic
                    self.shoot_arrow(attacker, angle, draw_progress)
            else:
                # Not drawing - start drawing if can attack
                if attacker.can_attack():
                    # Face the target before drawing
                    self._face_toward_target(attacker, target)

                    # Start bow draw
                    attacker.start_bow_draw(self.state.ticks)
        else:
            # Melee attack - requires adjacency
            if self.is_adjacent(attacker, target):
                # Check if can attack (not already animating)
                if attacker.can_attack():
                    # Face the target before attacking
                    self._face_toward_target(attacker, target)

                    # Start attack animation - damage dealt when animation completes
                    # (processed by _process_pending_attacks)
                    attacker.start_attack(target=target)
                    attacker.last_attack_tick = self.state.ticks

        return True
    

    # =============================================================================
    # WITNESS & CRIME REPORTING
    # =============================================================================
    # Crime witnessing and reporting to authorities
    # =============================================================================

    def witness_crime(self, criminal, victim, crime_type):
        """Witnesses within perception range learn about the crime and may react.
        
        Uses perception system - witnesses must either:
        - Have their VISION CONE overlap the criminal's SOUND RADIUS, OR
        - Have their SOUND RADIUS overlap the criminal's SOUND RADIUS
        
        Args:
            criminal: The character who committed the crime
            victim: The victim of the crime
            crime_type: 'murder', 'assault', or 'theft'
        
        Creates memories for witnesses and triggers reactions.
        """
        criminal_name = criminal.get_display_name()
        victim_name = victim.get_display_name()
        
        # Determine intensity based on crime type
        if crime_type == 'murder':
            intensity = CRIME_INTENSITY_MURDER
        elif crime_type == 'assault':
            intensity = CRIME_INTENSITY_ASSAULT
        else:
            intensity = CRIME_INTENSITY_THEFT
        
        crime_allegiance = victim.get('allegiance')
        
        # Sound emanates from the criminal (attacker) - use correct coords for zone
        event_x, event_y = self._get_perception_coords(criminal)
        
        for char in self.state.characters:
            if char is criminal or char is victim:
                continue
            
            # Check if can perceive - this handles window viewing and zone checks
            can_perceive, method = self.can_perceive_character(char, criminal)
            
            if can_perceive:
                witness_name = char.get_display_name()
                
                # Create memory of the crime
                char.add_memory('crime', criminal, self.state.ticks,
                               location=(victim.x, victim.y),
                               intensity=intensity,
                               source='witnessed' if method == 'vision' else 'heard',
                               reported=False,
                               crime_type=crime_type,
                               victim=victim,
                               victim_allegiance=crime_allegiance,
                               perception_method=method)
                
                perception_verb = "WITNESSED" if method == 'vision' else "HEARD"
                self.state.log_action(f"{witness_name} {perception_verb} {criminal_name} {crime_type} {victim_name}!")
                
                # Evaluate reaction based on personality
                self.evaluate_crime_reaction(char, criminal, intensity, crime_allegiance)
    

    def evaluate_crime_reaction(self, witness, criminal, intensity, crime_allegiance):
        """Evaluate how a witness should react to a crime.
        
        Sets witness intent based on their personality.
        """
        # Check if witness cares about this crime
        if not self.will_care_about_crime(witness, crime_allegiance, intensity):
            return  # Doesn't care, no reaction
        
        confidence = witness.get_trait('confidence')
        
        if confidence >= 7:
            # High confidence - confront/attack
            witness.set_intent('attack', criminal, reason='witnessed_crime', started_tick=self.state.ticks)
            self.state.log_action(f"{witness.get_display_name()} will confront {criminal.get_display_name()}!")
        else:
            # Low confidence - flee
            witness.set_intent('flee', criminal, reason='witnessed_crime', started_tick=self.state.ticks)
            self.state.log_action(f"{witness.get_display_name()} fleeing from {criminal.get_display_name()}!")
    

    def report_crime_to(self, reporter, defender, crime_memory):
        """Reporter tells defender about a crime they know about.
        
        Creates a copy of the memory for the defender.
        """
        reporter_name = reporter.get_display_name()
        criminal = crime_memory['subject']
        criminal_name = criminal.get_display_name()
        defender_name = defender.get_display_name()
        
        # Create a copy of the memory for the defender
        defender.add_memory('crime', criminal, self.state.ticks,
                           location=crime_memory['location'],
                           intensity=crime_memory['intensity'],
                           source='told_by',
                           reported=False,
                           crime_type=crime_memory['details'].get('crime_type'),
                           victim=crime_memory['details'].get('victim'),
                           victim_allegiance=crime_memory['details'].get('victim_allegiance'),
                           informant=reporter,
                           original_tick=crime_memory['tick'])
        
        # Mark reporter's memory as reported
        crime_memory['reported'] = True
        
        self.state.log_action(f"{reporter_name} told {defender_name} about {criminal_name}'s crime!")
        
        # Defender evaluates reaction
        self.evaluate_crime_reaction(defender, criminal, 
                                    crime_memory['intensity'],
                                    crime_memory['details'].get('victim_allegiance'))
    

    def try_report_crimes_to_soldier(self, char):
        """If character has unreported crimes and is adjacent to a soldier, report to them.
        
        Only reports to soldiers of same allegiance as the crime.
        Only reports to soldiers in the same zone.
        """
        unreported = char.get_memories(memory_type='crime', unreported_only=True)
        
        if not unreported:
            return
        
        char_name = char.get_display_name()
        
        for other in self.state.characters:
            if other == char:
                continue
            if other.get('job') != 'Soldier':
                continue
            # Must be in same zone to report
            if other.zone != char.zone:
                continue
            
            # Use prevailing coords if same zone (correct for interiors)
            if char.zone is not None:
                dx = char.prevailing_x - other.prevailing_x
                dy = char.prevailing_y - other.prevailing_y
            else:
                dx = char.x - other.x
                dy = char.y - other.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > SOUND_RADIUS:  # Must be within sound range
                continue
                
            soldier_allegiance = other.get('allegiance')
            
            # Check each unreported crime
            for crime_memory in list(unreported):
                crime_allegiance = crime_memory['details'].get('victim_allegiance')
                
                # Only report to soldiers of same allegiance
                if crime_allegiance == soldier_allegiance:
                    criminal = crime_memory['subject']
                    if criminal in self.state.characters:
                        self.report_crime_to(char, other, crime_memory)



    # =============================================================================
    # ONGOING ACTIONS
    # =============================================================================
    # Timed player actions (harvest, plant, chop)
    # =============================================================================

    def update_ongoing_actions(self):
        """Update ongoing actions and complete them when finished."""
        player = self.state.player
        if not player or not player.has_ongoing_action():
            return

        # Check if action is complete
        if player.is_ongoing_action_complete():
            action = player.ongoing_action
            action_type = action['action']
            action_data = action['data']
            name = player.get_display_name()

            if action_type == 'harvest':
                # Complete the harvest
                cell = action_data.get('cell')
                if cell:
                    success = self.player_harvest_cell(player)
                    if success:
                        self.log_harvest_plant_finish(player, 'harvest')
                    else:
                        self.log_harvest_plant_error(player, 'harvest', 'cancelled')

            elif action_type == 'plant':
                # Complete the planting
                cell = action_data.get('cell')
                if cell:
                    success = self.player_plant_cell(player)
                    if success:
                        self.log_harvest_plant_finish(player, 'plant')
                    else:
                        self.log_harvest_plant_error(player, 'plant', 'cancelled')

            elif action_type == 'chop':
                # Complete tree chopping (future feature)
                self.log_harvest_plant_finish(player, 'chop')

            # Clear the ongoing action
            player.cancel_ongoing_action()

    # MOVEMENT SYSTEM
    

    # =============================================================================
    # MOVEMENT SYSTEM
    # =============================================================================
    # Position updates, velocity, collision, and squeeze behavior
    # =============================================================================

    def _should_npc_sprint(self, char):
        """
        Determine if an NPC should sprint based on their current intent/situation.
        
        NPCs sprint when:
        - Fleeing from danger (being attacked, saw crime, etc.)
        - Chasing/attacking a target (soldiers pursuing criminals, fighting back)
        - Responding urgently (soldier responding to crime report)
        
        NPCs do NOT sprint when:
        - Idling/wandering
        - Patrolling (soldiers walk their routes)
        - Going about normal business (buying food, farming, etc.)
        
        Returns:
            True if NPC should sprint, False otherwise
        """
        intent = char.intent
        if not intent:
            return False
        
        action = intent.get('action')
        reason = intent.get('reason', '')
        
        # Sprint when fleeing from any danger
        if action == 'flee':
            return True
        
        # Sprint when attacking (chasing a target)
        if action == 'attack':
            # Soldiers chasing criminals should sprint
            if reason in ('law_enforcement', 'pursuing_criminal'):
                return True
            # Fighting back against attacker - sprint to engage
            if reason in ('self_defense', 'retaliation'):
                return True
            # High-confidence NPCs confronting criminals
            if reason == 'confronting_criminal':
                return True
        
        # Sprint when actively following an urgent target
        if action == 'follow':
            # Following to help or confront
            if reason in ('help_victim', 'confronting', 'responding'):
                return True
        
        # Default: don't sprint
        return False
    

    def _get_effective_goal_and_transition(self, char, goal_world, goal_zone):
        """
        Convert world-coordinate goal to local coordinates for movement,
        and determine if a zone transition is needed.
        
        Args:
            char: The character moving
            goal_world: (x, y) in world coordinates
            goal_zone: Zone the goal is in (None for exterior)
        
        Returns:
            (effective_goal_local, transition)
            - effective_goal_local: (x, y) in char's current coordinate space
            - transition: None, 'need_to_enter', or 'need_to_exit'
        """
        char_zone = char.zone
        
        # Same zone - move directly (convert to local if needed)
        if char_zone == goal_zone:
            if char_zone is None:
                # Both exterior - world coords are local coords
                return goal_world, None
            else:
                # Both in same interior - convert world to interior local coords
                interior = self.state.interiors.get_interior(char_zone)
                if interior:
                    local_x, local_y = interior.world_to_interior(goal_world[0], goal_world[1])
                    return (local_x, local_y), None
                return goal_world, None
        
        # Character outside, goal inside - path to exterior door first
        if char_zone is None and goal_zone is not None:
            interior = self.state.interiors.get_interior(goal_zone)
            if interior:
                door_pos = interior.get_exit_position()  # world coords of exterior door
                return door_pos, 'need_to_enter'
        
        # Character inside, goal outside or different interior - path to interior door to exit
        if char_zone is not None:
            interior = self.state.interiors.get_interior(char_zone)
            if interior:
                door_local = interior.get_entry_position()  # interior local coords
                return door_local, 'need_to_exit'
        
        # Fallback
        return goal_world, None
    

    def _do_enter_interior(self, char, interior):
        """Handle character entering an interior."""
        char.enter_interior(interior)
        self.log_zone_transition(char, interior.name, entering=True)


    def _do_exit_interior(self, char, interior):
        """Handle character exiting an interior."""
        char.exit_interior(interior)

        # If exit position is blocked (another char just exited), find nearby spot
        if self.state.is_position_blocked(char.prevailing_x, char.prevailing_y, exclude_char=char):
            exit_x, exit_y = interior.get_exit_position()
            # Try offsets around exit point
            for offset in [(0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5), (0.5, 0.5), (-0.5, -0.5)]:
                test_x = exit_x + offset[0]
                test_y = exit_y + offset[1]
                if not self.state.is_position_blocked(test_x, test_y, exclude_char=char):
                    char.prevailing_x = test_x
                    char.prevailing_y = test_y
                    break

        self.log_zone_transition(char, interior.name, entering=False)
    

    def update_npc_positions(self, dt):
        """Update NPC positions based on velocity. Called every frame for smooth movement.
        
        Implements squeeze behavior: when blocked for more than SQUEEZE_THRESHOLD_TICKS,
        characters will slide perpendicular to their movement direction to squeeze past obstacles.
        
        Uses prevailing coords (local when in interior, world when in exterior) since
        velocity is calculated in that coordinate space.
        
        Note: Stamina drain/regen is handled separately in gui._game_loop using real-time
        to ensure consistent feel regardless of game speed.
        """
        npcs = [c for c in self.state.characters if not c.is_player]
        
        for char in npcs:
            vx = char.get('vx', 0.0)
            vy = char.get('vy', 0.0)
            
            if vx == 0.0 and vy == 0.0:
                # Not moving - reset squeeze state
                char['blocked_ticks'] = 0
                char['squeeze_direction'] = 0
                continue
            
            # Use prevailing coords (local when in interior, world when exterior)
            # Velocity is calculated in this space, so movement must be too
            curr_x = char.prevailing_x
            curr_y = char.prevailing_y
            
            # Calculate base new position
            new_x = curr_x + vx * dt
            new_y = curr_y + vy * dt
            
            # Keep within bounds - different for interior vs exterior
            if char.zone is None:
                # Exterior - use world SIZE
                new_x = max(0, min(SIZE, new_x))
                new_y = max(0, min(SIZE, new_y))
            else:
                # Interior - use interior dimensions
                interior = self.state.interiors.get_interior(char.zone)
                if interior:
                    new_x = max(0.3, min(interior.width - 0.3, new_x))
                    new_y = max(0.3, min(interior.height - 0.3, new_y))
            
            # Check for collision with other characters
            # is_position_blocked handles zone-aware collision checking
            if not self.state.is_position_blocked(new_x, new_y, exclude_char=char):
                # Clear path - move normally
                char.prevailing_x = new_x
                char.prevailing_y = new_y
                char['blocked_ticks'] = 0
                char['squeeze_direction'] = 0
            else:
                # Blocked - try to find a way through
                moved = self._try_squeeze_movement(char, vx, vy, new_x, new_y, dt)
    

    def update_arrows(self, dt):
        """Update arrow projectile positions and check for hits.
        
        Args:
            dt: Delta time in seconds
        """
        import time
        from constants import ARROW_STUCK_DURATION
        
        _bow = ITEMS["bow"]
        arrows_to_remove = []
        
        for arrow in self.state.arrows:
            # Handle stuck arrows (waiting to disappear)
            if arrow.get('stuck'):
                if time.time() - arrow['stuck_time'] >= ARROW_STUCK_DURATION:
                    arrows_to_remove.append(arrow)
                continue
            
            # Get per-arrow speed and range (with fallback to bow defaults)
            arrow_speed = arrow.get('speed', _bow["max_speed"])
            arrow_max_range = arrow.get('max_range', _bow["range"])
            
            # Move arrow
            arrow['x'] += arrow['dx'] * arrow_speed * dt
            arrow['y'] += arrow['dy'] * arrow_speed * dt
            arrow['distance'] += arrow_speed * dt
            
            # Check if exceeded max range - mark as stuck instead of removing
            if arrow['distance'] >= arrow_max_range:
                arrow['stuck'] = True
                arrow['stuck_time'] = time.time()
                continue
            
            # Check for collision with obstacles (trees, houses, etc.)
            # Use check_characters=False since we handle character hits separately
            if self.state.is_position_blocked(arrow['x'], arrow['y'], 
                                               zone=arrow['zone'],
                                               check_characters=False):
                arrow['stuck'] = True
                arrow['stuck_time'] = time.time()
                continue
            
            # Check for hits on characters
            hit_char = self._check_arrow_hit(arrow)
            if hit_char:
                # Deal damage
                self._apply_arrow_damage(arrow, hit_char)
                arrows_to_remove.append(arrow)
                continue
        
        # Remove arrows that hit or expired
        for arrow in arrows_to_remove:
            if arrow in self.state.arrows:
                self.state.arrows.remove(arrow)
    

    def _check_arrow_hit(self, arrow):
        """Check if arrow hit any character.
        
        Returns:
            Character that was hit, or None
        """
        for char in self.state.characters:
            # Don't hit the owner
            if char is arrow['owner']:
                continue
            
            # Must be in same zone
            if char.zone != arrow['zone']:
                continue
            
            # Skip dead characters
            if char.get('health', 100) <= 0:
                continue
            
            # Check distance to character center
            if arrow['zone']:
                char_x = char.prevailing_x
                char_y = char.prevailing_y
            else:
                char_x = char.x
                char_y = char.y
            
            dx = arrow['x'] - char_x
            dy = arrow['y'] - char_y
            dist = math.sqrt(dx * dx + dy * dy)
            
            # Hit if within character collision radius (use a slightly larger hitbox)
            if dist < 0.4:
                return char
        
        return None
    

    def _apply_arrow_damage(self, arrow, target):
        """Apply arrow damage to a target character with full aggro/witness logic."""
        owner = arrow['owner']
        owner_name = owner.get_display_name() if owner else "Arrow"
        target_name = target.get_display_name()
        
        # Apply damage (same as melee: 2-5)
        damage = random.randint(2, 5)
        target.health -= damage
        self.state.log_action(f"{owner_name}'s arrow hits {target_name} for {damage}! HP: {target.health}")
        
        # Set hit flash
        target['hit_flash_until'] = self.state.ticks + 2
        
        # Clear face_target and intent - being hit interrupts current behavior
        target['face_target'] = None
        if target.intent and target.intent.get('reason') == 'bystander':
            target.clear_intent()
        
        # Target remembers being attacked (if owner exists)
        if owner:
            self.remember_attack(target, owner, damage)
            
            # Check criminal status via memories
            attacker_is_criminal = self.is_known_criminal(owner)
            target_was_criminal = self.is_known_criminal(target)

            # If attacking an innocent, this is a crime
            if not target_was_criminal:
                # Attacker records they committed a crime (only once)
                if not attacker_is_criminal:
                    owner.add_memory('committed_crime', owner, self.state.ticks,
                                       location=(owner.x, owner.y),
                                       intensity=CRIME_INTENSITY_ASSAULT,
                                       source='self',
                                       crime_type='assault', victim=target)
                    attacker_is_criminal = True

                # Witness EVERY attack against an innocent (not just first)
                if target.health > 0:
                    self.witness_crime(owner, target, 'assault')
            
            # Handle death
            if target.health <= 0:
                if not attacker_is_criminal and target_was_criminal:
                    self.state.log_action(f"{owner_name} killed {target_name} with an arrow (justified)")
                else:
                    # Murder - record and witness
                    owner.add_memory('committed_crime', owner, self.state.ticks,
                                       location=(owner.x, owner.y),
                                       intensity=CRIME_INTENSITY_MURDER,
                                       source='self',
                                       crime_type='murder', victim=target)
                    self.witness_crime(owner, target, 'murder')
                
                # Transfer items
                owner.transfer_all_items_from(target)
            
            # Broadcast violence to nearby characters
            self.broadcast_violence(owner, target)
        else:
            # No owner - just handle death
            if target.health <= 0:
                self.state.log_action(f"{target_name} was killed by an arrow!")
    

    def _try_squeeze_movement(self, char, vx, vy, new_x, new_y, dt):
        """Try to squeeze past an obstacle when blocked.
        
        Strategy:
        1. First, try simple axis-aligned sliding (might work for glancing collisions)
        2. If blocked for 3+ ticks, pick a perpendicular direction and slide that way
        3. Keep sliding in that direction until we make forward progress or get unstuck
        
        Uses prevailing coords (local when in interior, world when in exterior).
        
        Returns True if character moved, False if completely stuck.
        """
        moved = False
        made_forward_progress = False
        
        # Use prevailing coords - match coordinate space of new_x/new_y
        curr_x = char.prevailing_x
        curr_y = char.prevailing_y
        
        # Try simple axis-aligned sliding first (handles glancing collisions)
        # Only try if we're actually moving in that direction
        if abs(vx) >= abs(vy):
            # Moving mostly horizontal - try X only first
            if abs(vx) > 0.01 and not self.state.is_position_blocked(new_x, curr_y, exclude_char=char):
                char.prevailing_x = new_x
                moved = True
                made_forward_progress = True
            # Then try Y if we have Y velocity
            elif abs(vy) > 0.01 and not self.state.is_position_blocked(curr_x, new_y, exclude_char=char):
                char.prevailing_y = new_y
                moved = True
        else:
            # Moving mostly vertical - try Y only first
            if abs(vy) > 0.01 and not self.state.is_position_blocked(curr_x, new_y, exclude_char=char):
                char.prevailing_y = new_y
                moved = True
                made_forward_progress = True
            # Then try X if we have X velocity
            elif abs(vx) > 0.01 and not self.state.is_position_blocked(new_x, curr_y, exclude_char=char):
                char.prevailing_x = new_x
                moved = True
        
        if made_forward_progress:
            # Made actual forward progress - reset squeeze state
            char['blocked_ticks'] = 0
            char['squeeze_direction'] = 0
            return True
        
        # Still blocked on primary axis - increment counter
        char['blocked_ticks'] = char.get('blocked_ticks', 0) + 1
        
        # After threshold OR if already squeezing, continue squeeze behavior
        if char['blocked_ticks'] >= SQUEEZE_THRESHOLD_TICKS or char.get('squeeze_direction', 0) != 0:
            # Pick a squeeze direction if we don't have one
            if char.get('squeeze_direction', 0) == 0:
                # Choose direction based on which way has more space
                # or randomly if equal
                char['squeeze_direction'] = self._choose_squeeze_direction(char, vx, vy)
            
            squeeze_dir = char['squeeze_direction']
            slide_speed = MOVEMENT_SPEED * SQUEEZE_SLIDE_SPEED * dt
            
            # Calculate slide movement perpendicular to travel direction
            if abs(vx) > abs(vy):
                # Moving horizontal, slide vertical
                slide_y = curr_y + squeeze_dir * slide_speed
                # Try to move: slide perpendicular + forward progress
                if not self.state.is_position_blocked(new_x, slide_y, exclude_char=char):
                    char.prevailing_x = new_x
                    char.prevailing_y = slide_y
                    char['blocked_ticks'] = 0
                    char['squeeze_direction'] = 0
                    return True
                # Try just sliding perpendicular
                elif not self.state.is_position_blocked(curr_x, slide_y, exclude_char=char):
                    char.prevailing_y = slide_y
                    return True
                else:
                    # This direction is blocked, try the other way
                    char['squeeze_direction'] = -squeeze_dir
            else:
                # Moving vertical, slide horizontal
                slide_x = curr_x + squeeze_dir * slide_speed
                # Try to move: slide perpendicular + forward progress
                if not self.state.is_position_blocked(slide_x, new_y, exclude_char=char):
                    char.prevailing_x = slide_x
                    char.prevailing_y = new_y
                    char['blocked_ticks'] = 0
                    char['squeeze_direction'] = 0
                    return True
                # Try just sliding perpendicular
                elif not self.state.is_position_blocked(slide_x, curr_y, exclude_char=char):
                    char.prevailing_x = slide_x
                    return True
                else:
                    # This direction is blocked, try the other way
                    char['squeeze_direction'] = -squeeze_dir
        
        return False
    

    def _choose_squeeze_direction(self, char, vx, vy):
        """Choose which direction to squeeze (perpendicular to movement).
        Picks the direction with more open space, or random if equal.
        Returns -1 or 1.
        """
        # Use prevailing coords for interior/exterior compatibility
        curr_x = char.prevailing_x
        curr_y = char.prevailing_y
        
        # Check space in both perpendicular directions
        check_dist = 1.0  # How far to look
        
        if abs(vx) > abs(vy):
            # Moving horizontal, check vertical space
            space_pos = 0
            space_neg = 0
            for d in [0.3, 0.6, 1.0]:
                if not self.state.is_position_blocked(curr_x, curr_y + d, exclude_char=char):
                    space_pos += 1
                if not self.state.is_position_blocked(curr_x, curr_y - d, exclude_char=char):
                    space_neg += 1
        else:
            # Moving vertical, check horizontal space
            space_pos = 0
            space_neg = 0
            for d in [0.3, 0.6, 1.0]:
                if not self.state.is_position_blocked(curr_x + d, curr_y, exclude_char=char):
                    space_pos += 1
                if not self.state.is_position_blocked(curr_x - d, curr_y, exclude_char=char):
                    space_neg += 1
        
        if space_pos > space_neg:
            return 1
        elif space_neg > space_pos:
            return -1
        else:
            # Equal space - pick randomly
            return random.choice([-1, 1])


    # =============================================================================
    # PATHFINDING & NAVIGATION
    # =============================================================================
    # Goal selection, pathfinding, and AI navigation
    # =============================================================================

    def _process_npc_movement(self):
        """
        Process all NPC decisions and movement for this tick.
        
        For each NPC:
        1. Call job.decide() which sets char.goal and performs any immediate actions
        2. Update velocity based on char.goal
        
        Position updates happen every frame via update_npc_positions().
        """
        npcs = [c for c in self.state.characters if not c.is_player]
        
        # Each NPC decides what to do (sets goal and/or takes action)
        for char in npcs:
            if char not in self.state.characters:
                continue  # May have been killed
            
            if char.get('is_frozen'):
                char.vx = 0.0
                char.vy = 0.0
                continue
            
            # Skip dying characters
            if char.get('health', 100) <= 0:
                char.vx = 0.0
                char.vy = 0.0
                continue
            
            # Reset idle flag before deciding
            char.idle_is_idle = False
            
            # Get the job and let it decide what to do
            job = get_job(char.get('job'))
            job.decide(char, self.state, self)
            
            # Wake up if not sleep time
            if not self.state.is_sleep_time() and char.get('is_sleeping'):
                char.is_sleeping = False
                name = char.get_display_name()
                self.state.log_action(f"{name} woke up")
        
        # Update velocities based on goals (with zone transition handling)
        for char in npcs:
            if char not in self.state.characters:
                continue
            
            if char.get('is_frozen') or char.get('health', 100) <= 0:
                continue
            
            # Check for combat tracking (bypasses goal system for smooth pursuit)
            combat_target = char.get('combat_track_target')
            if combat_target and combat_target in self.state.characters:
                self._update_combat_tracking_velocity(char, combat_target)
                continue
            
            goal = char.goal
            goal_zone = getattr(char, 'goal_zone', None)
            
            if goal:
                # Get effective local goal and check for zone transitions
                effective_goal, transition = self._get_effective_goal_and_transition(
                    char, goal, goal_zone
                )
                
                # Handle zone transitions at door thresholds
                if transition == 'need_to_exit':
                    interior = self.state.interiors.get_interior(char.zone)
                    if interior and interior.is_at_door(char.prevailing_x, char.prevailing_y):
                        self._do_exit_interior(char, interior)
                        continue  # Re-evaluate next tick
                
                elif transition == 'need_to_enter':
                    interior = self.state.interiors.get_interior(goal_zone)
                    if interior:
                        door_x, door_y = interior.get_exit_position()
                        dist_to_door = math.sqrt((char.x - door_x)**2 + (char.y - door_y)**2)
                        if dist_to_door < DOOR_THRESHOLD:
                            self._do_enter_interior(char, interior)
                            continue  # Re-evaluate next tick
                
                # Calculate velocity toward effective_goal (in local coords)
                dx = effective_goal[0] - char.prevailing_x
                dy = effective_goal[1] - char.prevailing_y
                dist = math.sqrt(dx * dx + dy * dy)
                
                # Check if in combat (tracking a moving target)
                is_combat_tracking = (char.intent and char.intent.get('action') == 'attack')
                
                # For combat tracking, use tighter threshold to stay responsive
                # For normal movement, use 0.35 to prevent overshoot jitter
                stop_threshold = 0.1 if is_combat_tracking else 0.35
                
                if dist < stop_threshold:
                    char.vx = 0.0
                    char.vy = 0.0
                    char.is_sprinting = False
                    # Even when stopped, face the target if backpedaling
                    face_target = char.get('face_target')
                    if face_target and face_target in self.state.characters:
                        self._face_toward_character(char, face_target)
                else:
                    # Determine if NPC should sprint
                    should_sprint = self._should_npc_sprint(char)
                    
                    # Check stamina before allowing sprint
                    if should_sprint:
                        if char.is_sprinting:
                            if not char.can_continue_sprint():
                                should_sprint = False
                        else:
                            if not char.can_start_sprint():
                                should_sprint = False
                    
                    char.is_sprinting = should_sprint
                    
                    # Use slower speed if idling or patrolling, sprint speed if sprinting
                    if should_sprint:
                        speed = SPRINT_SPEED
                    elif char.get('idle_is_idle', False):
                        speed = MOVEMENT_SPEED * IDLE_SPEED_MULTIPLIER
                    elif char.get('is_patrolling', False):
                        speed = MOVEMENT_SPEED * PATROL_SPEED_MULTIPLIER
                    else:
                        speed = MOVEMENT_SPEED
                    
                    # Normalize and apply speed
                    char.vx = (dx / dist) * speed
                    char.vy = (dy / dist) * speed
                    
                    # Update facing - check face_target first (for backpedaling)
                    face_target = char.get('face_target')
                    if face_target and face_target in self.state.characters:
                        self._face_toward_character(char, face_target)
                    else:
                        self._update_facing_from_velocity(char)
            else:
                char.vx = 0.0
                char.vy = 0.0
                char.is_sprinting = False
            
            # If not idling, reset idle state for next time
            if not char.get('idle_is_idle', False):
                self._reset_idle_state(char)
        
        # Report crimes to nearby soldiers
        for char in self.state.characters:
            self.try_report_crimes_to_soldier(char)
    

    def _get_desired_step(self, char):
        """Calculate the position this NPC wants to move toward.
        Returns the goal position or None if no goal.
        """
        return char.goal
    

    def _get_homeless_idle_goal(self, char):
        """Get idle goal for a homeless character - wanders anywhere except farm cells.
        Uses the same state machine as _get_wander_goal but without area constraints.
        """
        # Mark character as idling (for speed reduction)
        char['idle_is_idle'] = True
        
        idle_state = char.get('idle_state', 'choosing')
        
        # Handle waiting state
        if idle_state == 'waiting' or idle_state == 'paused':
            wait_ticks = char.get('idle_wait_ticks', 0)
            if wait_ticks > 0:
                char['idle_wait_ticks'] = wait_ticks - 1
                return None  # Stay still
            else:
                # Done waiting, choose new destination
                char['idle_state'] = 'choosing'
                idle_state = 'choosing'
        
        # Handle choosing state - pick a new destination
        if idle_state == 'choosing':
            destination = self._choose_homeless_destination(char)
            if destination:
                char['idle_destination'] = destination
                char['idle_state'] = 'moving'
                idle_state = 'moving'
            else:
                # No valid destination, stay put
                return None
        
        # Handle moving state
        if idle_state == 'moving':
            destination = char.get('idle_destination')
            if not destination:
                char['idle_state'] = 'choosing'
                return None
            
            # Check if we've arrived at destination
            dx = destination[0] - char['x']
            dy = destination[1] - char['y']
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist < 0.4:  # Arrived at destination
                # Start waiting
                char['idle_state'] = 'waiting'
                char['idle_wait_ticks'] = random.randint(IDLE_MIN_WAIT_TICKS, IDLE_MAX_WAIT_TICKS)
                char['idle_destination'] = None
                return None
            
            # Maybe pause mid-journey
            if random.random() < IDLE_PAUSE_CHANCE / 100:
                char['idle_state'] = 'paused'
                char['idle_wait_ticks'] = random.randint(IDLE_PAUSE_MIN_TICKS, IDLE_PAUSE_MAX_TICKS)
                return None
            
            return destination
        
        return None
    

    def _choose_homeless_destination(self, char):
        """Choose a destination for homeless wandering.
        Picks a random non-farm cell within moderate distance.
        Uses accessibility check to avoid buildings and trees.
        """
        current_x, current_y = int(char['x']), int(char['y'])
        
        # Find valid cells within a reasonable wander range (not too far)
        valid_cells = []
        wander_range = 8  # Cells to consider
        
        for dy in range(-wander_range, wander_range + 1):
            for dx in range(-wander_range, wander_range + 1):
                nx, ny = current_x + dx, current_y + dy
                world_x, world_y = nx + 0.5, ny + 0.5
                
                # Use accessibility check - excludes buildings, trees, out of bounds
                if not self.is_position_accessible_same_zone(world_x, world_y, None):
                    continue
                
                # Skip farm cells
                if (nx, ny) in self.state.farm_cells:
                    continue
                # Skip current cell
                if dx == 0 and dy == 0:
                    continue
                valid_cells.append((nx, ny))
        
        if not valid_cells:
            return None
        
        # Prefer cells that are at least 2 cells away for more purposeful movement
        far_cells = [c for c in valid_cells if abs(c[0]-current_x) + abs(c[1]-current_y) > 2]
        if far_cells:
            cell = random.choice(far_cells)
        else:
            cell = random.choice(valid_cells)
        
        return (cell[0] + 0.5, cell[1] + 0.5)
    

    def _get_flee_goal(self, char, threat):
        """Get a position away from the threat. Returns float position (world coords)."""
        dx = char['x'] - threat['x']
        dy = char['y'] - threat['y']
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0.01:
            # Normalize and extend
            dx = dx / dist
            dy = dy / dist
        else:
            # Pick random direction if on top of threat
            angle = random.random() * 2 * math.pi
            dx = math.cos(angle)
            dy = math.sin(angle)
        return (char['x'] + dx * 5.0, char['y'] + dy * 5.0)
    

    def _get_interior_flee_goal(self, char, threat, interior):
        """Get a flee position within an interior, respecting walls.
        
        Returns:
            (goal_x, goal_y, goal_zone) - world coords and zone
            goal_zone is None if character should exit, interior.name if staying inside
        """
        # Use prevailing (local) coords for interior calculations
        char_x = char.prevailing_x
        char_y = char.prevailing_y
        threat_x = threat.prevailing_x
        threat_y = threat.prevailing_y
        
        # Door position in local coords (door is at bottom wall)
        door_local_x = interior.door_x + 0.5
        door_local_y = interior.height - 0.5  # Just inside the door
        near_door_threshold = 1.5  # If flee pos is within this of door, just exit
        
        # Calculate flee direction (away from threat)
        dx = char_x - threat_x
        dy = char_y - threat_y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist > 0.01:
            dx = dx / dist
            dy = dy / dist
        else:
            # Random direction if on top of threat
            angle = random.random() * 2 * math.pi
            dx = math.cos(angle)
            dy = math.sin(angle)
        
        # Helper to check if a position is near the door
        def is_near_door(x, y):
            door_dist = math.sqrt((x - door_local_x)**2 + (y - door_local_y)**2)
            return door_dist < near_door_threshold
        
        # Try to find valid flee position within interior
        # Try multiple distances, starting far and working closer
        wall_buffer = 0.5
        for flee_dist in [3.0, 2.0, 1.5, 1.0]:
            target_x = char_x + dx * flee_dist
            target_y = char_y + dy * flee_dist
            
            # Clamp to interior bounds
            target_x = max(wall_buffer, min(interior.width - wall_buffer, target_x))
            target_y = max(wall_buffer, min(interior.height - wall_buffer, target_y))
            
            # Check if this position is valid (not blocked by furniture)
            if not interior.is_position_blocked(int(target_x), int(target_y)):
                # If flee position is near door, just exit instead
                if is_near_door(target_x, target_y):
                    exit_x, exit_y = interior.get_exit_position()
                    return (exit_x, exit_y, None)
                
                # Found valid flee position - convert to world coords
                world_x, world_y = interior.interior_to_world(target_x, target_y)
                return (world_x, world_y, interior.name)
        
        # Try perpendicular directions if straight back is blocked
        for angle_offset in [math.pi/2, -math.pi/2, math.pi/4, -math.pi/4]:
            base_angle = math.atan2(dy, dx)
            new_angle = base_angle + angle_offset
            new_dx = math.cos(new_angle)
            new_dy = math.sin(new_angle)
            
            for flee_dist in [2.0, 1.5, 1.0]:
                target_x = char_x + new_dx * flee_dist
                target_y = char_y + new_dy * flee_dist
                
                target_x = max(wall_buffer, min(interior.width - wall_buffer, target_x))
                target_y = max(wall_buffer, min(interior.height - wall_buffer, target_y))
                
                if not interior.is_position_blocked(int(target_x), int(target_y)):
                    # If flee position is near door, just exit instead
                    if is_near_door(target_x, target_y):
                        exit_x, exit_y = interior.get_exit_position()
                        return (exit_x, exit_y, None)
                    
                    world_x, world_y = interior.interior_to_world(target_x, target_y)
                    return (world_x, world_y, interior.name)
        
        # Cornered - flee to exit
        exit_x, exit_y = interior.get_exit_position()
        return (exit_x, exit_y, None)
    

    def _get_wheat_goal(self, char):
        """Get position to move toward for hunger needs. Returns float position.
        
        Priority:
        1. If have wheat but no bread -> go to cooking spot (or make camp)
        2. If no wheat -> go buy wheat
        """
        job = char.get('job')
        
        # If we have wheat but no bread, we need to cook
        if char.get_item('wheat') >= WHEAT_TO_BREAD_RATIO and char.get_item('bread') < BREAD_PER_BITE:
            # Find nearest cooking spot
            cooking_spot, cooking_pos = self.get_nearest_cooking_spot(char)
            if cooking_spot and cooking_pos:
                return cooking_pos
            
            # No cooking spot - need to make a camp
            # If we can camp here, we'll do it in handle_wheat_need
            # Otherwise find a spot to camp
            if not self.can_make_camp_at(char['x'], char['y']):
                camp_spot = self._find_camp_spot(char)
                if camp_spot:
                    return camp_spot
            # Can camp here, return None to let handle_wheat_need make the camp
            return None
        
        # Need to get wheat
        if job == 'Soldier':
            # Go to barracks barrel position
            barracks_barrel = self.state.interactables.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
            if barracks_barrel:
                barrel_pos = barracks_barrel.position
                if barrel_pos:
                    return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            return self._nearest_in_area(char, self.state.get_area_by_role('military_housing'))
        
        # Farmer: go to farm barrel to withdraw wheat
        if job == 'Farmer':
            farm_barrel = self.state.interactables.get_barrel_by_home(char.get('home'))
            if farm_barrel:
                barrel_wheat = farm_barrel.get_item('wheat')
                if barrel_wheat > 0:
                    barrel_pos = farm_barrel.position
                    if barrel_pos:
                        return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            # No barrel or empty barrel - fall through to buying logic
        
        if self.can_afford_goods(char, 'wheat'):
            farmer = self.find_willing_vendor(char, 'wheat')
            if farmer:
                return (farmer['x'], farmer['y'])
        return None
    

    def _get_soldiers_requesting_wheat(self):
        """Get list of soldiers who have requested wheat from the steward."""
        return [c for c in self.state.characters 
                if c.get('job') == 'Soldier' and c.get('requested_wheat', False)]
    

    def _get_wander_goal(self, char, area):
        """Get the current idle destination for this character within the given area.
        Uses a state machine to create natural wandering behavior:
        - Choose a point of interest or random valid position
        - Move toward it at reduced speed
        - Wait there for a while
        - Sometimes pause mid-journey
        
        Works for both exterior areas and interiors.
        Returns float position or None if waiting/paused.
        """
        is_village = self.state.is_village_area(area) if area else False
        
        # Mark character as idling (for speed reduction)
        char['idle_is_idle'] = True
        
        idle_state = char.get('idle_state', 'choosing')
        
        # Handle waiting state
        if idle_state == 'waiting' or idle_state == 'paused':
            wait_ticks = char.get('idle_wait_ticks', 0)
            if wait_ticks > 0:
                char['idle_wait_ticks'] = wait_ticks - 1
                return None  # Stay still
            else:
                # Done waiting, choose new destination
                char['idle_state'] = 'choosing'
                idle_state = 'choosing'
        
        # Handle choosing state - pick a new destination
        if idle_state == 'choosing':
            destination = self._choose_idle_destination(char, area, is_village)
            if destination:
                char['idle_destination'] = destination
                char['idle_state'] = 'moving'
                idle_state = 'moving'
            else:
                # No valid destination, stay put
                return None
        
        # Handle moving state
        if idle_state == 'moving':
            destination = char.get('idle_destination')
            if not destination:
                char['idle_state'] = 'choosing'
                return None
            
            # Check if we've arrived at destination
            # Destination is in world coords; convert to local if in interior
            if char.zone:
                interior = self.state.interiors.get_interior(char.zone)
                if interior:
                    dest_local_x, dest_local_y = interior.world_to_interior(destination[0], destination[1])
                    dx = dest_local_x - char.prevailing_x
                    dy = dest_local_y - char.prevailing_y
                else:
                    dx = destination[0] - char.x
                    dy = destination[1] - char.y
            else:
                dx = destination[0] - char.x
                dy = destination[1] - char.y
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist < 0.4:  # Arrived at destination
                # Check if arrived at a window - if so, face outward
                if char.zone and interior:
                    window_facing = self._get_window_facing_at(interior, char.prevailing_x, char.prevailing_y)
                    if window_facing:
                        # Convert window facing (north/south/east/west) to character facing (up/down/left/right)
                        facing_map = {'north': 'up', 'south': 'down', 'east': 'right', 'west': 'left'}
                        char['facing'] = facing_map.get(window_facing, 'down')
                
                # Start waiting
                char['idle_state'] = 'waiting'
                char['idle_wait_ticks'] = random.randint(IDLE_MIN_WAIT_TICKS, IDLE_MAX_WAIT_TICKS)
                char['idle_destination'] = None
                return None
            
            # Maybe pause mid-journey (small chance per tick)
            # Only check occasionally to avoid constant rolls
            if random.random() < IDLE_PAUSE_CHANCE / 100:  # Scaled down since called every tick
                char['idle_state'] = 'paused'
                char['idle_wait_ticks'] = random.randint(IDLE_PAUSE_MIN_TICKS, IDLE_PAUSE_MAX_TICKS)
                return None
            
            return destination
        
        return None
    

    def _choose_idle_destination(self, char, area, is_village):
        """Choose a destination for idle wandering.
        70% chance to pick a point of interest (corners, center, edges)
        30% chance to pick a random valid position
        Avoids farm cells and inaccessible positions (buildings, trees).
        Works for both exterior areas and interiors.
        """
        # Get points of interest (world coords)
        poi_list = self.state.get_area_points_of_interest(area, is_village)
        
        # Get valid positions for random wandering (world coords)
        valid_positions = self.state.get_valid_idle_cells(area, is_village)
        
        # Filter POIs for accessibility (can't wander into buildings from exterior)
        accessible_pois = [
            p for p in poi_list 
            if self.is_position_accessible_same_zone(p[0], p[1], char.zone)
        ]
        
        # Filter positions for accessibility
        accessible_positions = [
            p for p in valid_positions
            if self.is_position_accessible_same_zone(p[0], p[1], char.zone)
        ]
        
        if not accessible_pois and not accessible_positions:
            return None
        
        # Get current position in appropriate coord space
        # POIs/positions are in world coords; need to compare in same space
        if char.zone:
            # In interior - use prevailing (local) coords for distance, but POIs are world
            # Convert char position to world for consistent comparison
            current_pos = (char.x, char.y)  # world coords (compressed but consistent with POIs)
            # For interiors, world distances are compressed, so use a smaller threshold
            far_threshold = 0.3  # Compressed world space
        else:
            current_pos = (char.x, char.y)
            far_threshold = 2.0
        
        # 70% chance to go to a point of interest if available
        if accessible_pois and (not accessible_positions or random.random() < 0.7):
            # Pick a POI that's not too close to current position
            far_pois = [p for p in accessible_pois if math.sqrt((p[0]-current_pos[0])**2 + (p[1]-current_pos[1])**2) > far_threshold]
            if far_pois:
                return random.choice(far_pois)
            elif accessible_pois:
                return random.choice(accessible_pois)
        
        # Pick a random valid position
        if accessible_positions:
            # Prefer positions that are at least threshold away
            far_positions = [p for p in accessible_positions 
                           if math.sqrt((p[0]-current_pos[0])**2 + (p[1]-current_pos[1])**2) > far_threshold]
            if far_positions:
                return random.choice(far_positions)
            else:
                return random.choice(accessible_positions)
        
        return None
    

    def _nearest_in_area(self, char, area, is_village=False):
        """Find the nearest unoccupied cell in an area. Returns float position (cell center).
        Falls back to occupied if none free.
        """
        best_free = None
        best_free_dist = float('inf')
        best_any = None
        best_any_dist = float('inf')
        
        for y in range(SIZE):
            for x in range(SIZE):
                if is_village:
                    in_area = self.state.is_in_village(x, y)
                else:
                    in_area = self.state.get_area_at(x, y) == area
                if in_area:
                    # Calculate distance to cell center
                    cx, cy = x + 0.5, y + 0.5
                    dist = math.sqrt((cx - char['x']) ** 2 + (cy - char['y']) ** 2)
                    is_occupied = self.state.is_occupied(x, y)
                    
                    if not is_occupied and dist < best_free_dist:
                        best_free_dist = dist
                        best_free = (cx, cy)
                    if dist < best_any_dist:
                        best_any_dist = dist
                        best_any = (cx, cy)
        
        return best_free if best_free else best_any
    

    def _nearest_ready_farm_cell(self, char, home=None):
        """Find nearest ready farm cell. Returns float position (cell center).
        
        Args:
            char: The character looking for a cell
            home: Filter to only cells owned by this farm area name. If None, searches all.
        """
        from scenario.scenario_world import AREAS
        
        # Check if character is already on a farm cell being worked
        char_cell = (int(char['x']), int(char['y']))
        cell = self.state.get_farm_cell_state(char_cell[0], char_cell[1])
        if cell and cell['state'] in ('ready', 'harvesting', 'replanting'):
            return None
        
        # If home is specified, get the farm cells for that specific farm area
        valid_cells = set()
        if home:
            for area in AREAS:
                if area.get('name') == home and area.get('has_farm_cells'):
                    # Get the explicit farm cell list from the area definition
                    for cell_coord in area.get('farm_cells', []):
                        valid_cells.add((cell_coord[0], cell_coord[1]))
                    break
        
        best = None
        best_dist = float('inf')
        for (cx, cy), data in self.state.farm_cells.items():
            if data['state'] == 'ready':
                # Filter by home farm if specified
                if home and (cx, cy) not in valid_cells:
                    continue
                # Distance to cell center
                center_x, center_y = cx + 0.5, cy + 0.5
                dist = math.sqrt((center_x - char['x']) ** 2 + (center_y - char['y']) ** 2)
                if dist < best_dist:
                    best_dist = dist
                    best = (center_x, center_y)
        return best
    

    def _step_toward(self, char, goal_x, goal_y):
        """
        Calculate the best single step toward a goal.
        Uses direct movement first (including diagonals), BFS if blocked.
        """
        x, y = char['x'], char['y']
        
        if x == goal_x and y == goal_y:
            return None
        
        # Build occupied set (we'll return moves into occupied cells for swap detection)
        occupied = set()
        for c in self.state.characters:
            if c != char:
                occupied.add((c['x'], c['y']))
        
        # Already adjacent to goal (including diagonally)
        if abs(x - goal_x) <= 1 and abs(y - goal_y) <= 1:
            return (goal_x, goal_y)
        
        dx = goal_x - x
        dy = goal_y - y
        
        # Build move priority list - diagonal moves are often the most direct
        moves = []
        
        # Normalize direction
        step_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
        step_y = 1 if dy > 0 else (-1 if dy < 0 else 0)
        
        # If we can move diagonally toward goal, that's usually best
        if step_x != 0 and step_y != 0:
            moves.append((step_x, step_y))  # Diagonal toward goal
        
        # Then try cardinal directions toward goal
        if abs(dx) >= abs(dy):
            if step_x != 0: moves.append((step_x, 0))
            if step_y != 0: moves.append((0, step_y))
        else:
            if step_y != 0: moves.append((0, step_y))
            if step_x != 0: moves.append((step_x, 0))
        
        # Add other diagonal moves as alternatives
        if step_x != 0 and step_y == 0:
            moves.extend([(step_x, 1), (step_x, -1)])
        elif step_y != 0 and step_x == 0:
            moves.extend([(1, step_y), (-1, step_y)])
        
        # Add perpendicular cardinal moves
        if step_x != 0 and step_y == 0:
            moves.extend([(0, 1), (0, -1)])
        elif step_y != 0 and step_x == 0:
            moves.extend([(1, 0), (-1, 0)])
        elif step_x == 0 and step_y == 0:
            # Already at goal - shouldn't happen but handle it
            moves = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        
        # Try direct/diagonal moves first
        for mdx, mdy in moves:
            nx, ny = x + mdx, y + mdy
            if self.state.is_position_valid(nx, ny):
                # Return even if occupied - swap detection handles it
                # But prefer unoccupied cells
                if (nx, ny) not in occupied:
                    return (nx, ny)
        
        # All direct moves blocked by other characters - try BFS to find path around
        parent = {(x, y): None}
        queue = deque([(x, y)])
        goal = (goal_x, goal_y)
        
        while queue:
            cx, cy = queue.popleft()
            
            for ddx, ddy in DIRECTIONS:
                nx, ny = cx + ddx, cy + ddy
                next_pos = (nx, ny)
                
                if not self.state.is_position_valid(nx, ny):
                    continue
                if next_pos in parent:
                    continue
                # Can path through goal, but not through other occupied cells
                if next_pos in occupied and next_pos != goal:
                    continue
                
                parent[next_pos] = (cx, cy)
                
                # Found goal or adjacent to goal (including diagonally)
                if next_pos == goal or (abs(nx - goal_x) <= 1 and abs(ny - goal_y) <= 1):
                    # Backtrack to find first step
                    pos = next_pos
                    while parent[pos] != (x, y):
                        pos = parent[pos]
                    return pos
                
                queue.append(next_pos)
        
        # No path found - try any valid move (for swap detection)
        for mdx, mdy in moves:
            nx, ny = x + mdx, y + mdy
            if self.state.is_position_valid(nx, ny):
                return (nx, ny)
        
        return None
    

    def _move_toward_point(self, char, point):
        """Move character one step toward a point (used for actions outside main loop)."""
        if point is None:
            return
        step = self._step_toward(char, point[0], point[1])
        if step and not self.state.is_occupied(step[0], step[1]):
            char['x'] = step[0]
            char['y'] = step[1]
    

    def move_toward_character(self, char, target):
        """Move character one step toward another character."""
        if target is None or target not in self.state.characters:
            return
        self._move_toward_point(char, (target['x'], target['y']))
    
    

    # =============================================================================
    # TICK PROCESSING
    # =============================================================================
    # Game loop tick processing and updates
    # =============================================================================

    def process_tick(self):
        """Process one game tick - updates all game state"""
        self.state.ticks += 1
        
        # Update hunger for all characters
        for char in self.state.characters:
            char['hunger'] = max(0, char['hunger'] - HUNGER_DECAY)
        
        # Update stamina for all characters (Skyrim-style)
        self._process_stamina()
        
        # Process starvation
        self._process_starvation()
        
        # Update NPC combat mode based on intent
        self._process_npc_combat_mode()
        
        # Process pending attacks (resolve damage when animation completes)
        self._process_pending_attacks()
        
        # Handle deaths IMMEDIATELY - remove from game logic, store visual info separately
        # This must happen right after starvation before any other processing
        self._process_deaths()
        
        # Update farm cells
        self._update_farm_cells()
        
        # Age increment
        if self.state.ticks > 0 and self.state.ticks % TICKS_PER_YEAR == 0:
            for char in self.state.characters:
                char['age'] += 1
            self.state.log_action(f"A new year begins! Everyone is one year older.")
        
        # Tax grace period check - steward goes to collect if farmer is late
        steward = self.state.get_steward()
        if steward:
            steward_allegiance = steward.get('allegiance')
            for char in self.state.characters:
                if char.get('job') == 'Farmer' and char.get('allegiance') == steward_allegiance:
                    tax_due_tick = char.get('tax_due_tick')
                    if tax_due_tick is not None and self.state.ticks >= tax_due_tick + TAX_GRACE_PERIOD:
                        if steward.get('tax_collection_target') != char:
                            steward_name = steward.get_display_name()
                            char_name = char.get_display_name()
                            self.state.log_action(f"Steward {steward_name} going to collect tax from {char_name}!")
                            steward['tax_collection_target'] = char
        
        # Move NPCs with swap detection to prevent oscillation
        self._process_npc_movement()
        
        # Process deaths again to catch combat kills
        self._process_deaths()
    

    def _process_deaths(self):
        """Remove dead characters from game and create corpse interactables"""
        from static_interactables import Corpse

        dead_chars = [char for char in self.state.characters if char['health'] <= 0]
        for char in dead_chars:
            # Log death message
            dead_name = char.get_display_name()
            if char.is_player:
                if char.get('is_starving'):
                    self.state.log_action(f"{dead_name} (PLAYER) DIED from starvation! GAME OVER")
                else:
                    self.state.log_action(f"{dead_name} (PLAYER) DIED! GAME OVER")
            else:
                if char.get('is_starving'):
                    self.state.log_action(f"{dead_name} DIED from starvation!")
                else:
                    self.state.log_action(f"{dead_name} DIED!")

            # Get position (interior coords if in interior, world coords if outside)
            if char.zone:
                corpse_x = char.prevailing_x  # Local coords
                corpse_y = char.prevailing_y
            else:
                corpse_x = char['x']  # World coords
                corpse_y = char['y']

            # Create corpse interactable with character's inventory
            corpse_name = f"{char['name']}'s Corpse"
            corpse = Corpse(
                name=corpse_name,
                character_name=char['name'],
                x=corpse_x,
                y=corpse_y,
                zone=char.zone,
                facing=char.get('facing', 'down'),
                job=char.get('job'),
                morality=char.get('morality', 5)
            )

            # Transfer inventory from character to corpse
            for i, slot in enumerate(char.inventory):
                if slot is not None:
                    corpse.inventory[i] = {'type': slot['type'], 'amount': slot['amount']}

            # Set interior projection params if in interior
            if char.zone and hasattr(self.state, 'interiors'):
                interior = self.state.interiors.get_interior(char.zone)
                if interior:
                    corpse.set_interior_projection(interior)

            # Add corpse to game state
            self.state.corpses.append(corpse)

            # Immediately remove character from game - no more processing
            self.state.remove_character(char)
    

    def _process_stamina(self):
        """Process stamina drain/regeneration for all characters (Skyrim-style)."""
        current_tick = self.state.ticks
        
        for char in self.state.characters:
            # Skip dying characters
            if char.get('health', 100) <= 0:
                continue
            
            if char.is_sprinting:
                # Drain stamina while sprinting
                if not char.drain_stamina_sprint(current_tick):
                    # Stamina depleted - force stop sprinting
                    char.is_sprinting = False
                    # Reduce velocity to walking speed
                    if char.vx != 0 or char.vy != 0:
                        speed_ratio = MOVEMENT_SPEED / SPRINT_SPEED
                        char.vx *= speed_ratio
                        char.vy *= speed_ratio
            else:
                # Regenerate stamina when not sprinting
                char.regenerate_stamina(current_tick)
    

    def _process_starvation(self):
        """Process starvation for all characters"""
        for char in self.state.characters:
            # Skip dying characters
            if char.get('health', 100) <= 0:
                continue
            
            name = char.get_display_name()
            
            # Check if character should enter starvation (hunger = 0)
            if char['hunger'] <= STARVATION_THRESHOLD:
                was_starving = char.get('is_starving', False)
                
                if not was_starving:
                    # Just entered starvation
                    char['is_starving'] = True
                    char['starvation_health_lost'] = 0
                    char['ticks_starving'] = 0
                    self.state.log_action(f"{name} is STARVING! Losing health...")
                    
                    # Soldiers quit when they start starving - lose job and home, but keep allegiance
                    # This gives them a chance to buy wheat from a farmer and rejoin
                    # If no farmer will sell to them, wheat timeout will naturally remove allegiance
                    if char.get('job') == 'Soldier':
                        char['job'] = None
                        char['home'] = None
                        # Remove bed ownership
                        self.state.interactables.unassign_bed_owner(char['name'])
                        self.state.log_action(f"{name} QUIT being a Soldier due to starvation!")
                
                # Increment ticks starving
                char['ticks_starving'] = char.get('ticks_starving', 0) + 1
                
                # Apply starvation damage
                char['health'] -= STARVATION_DAMAGE
                char['starvation_health_lost'] += STARVATION_DAMAGE
                
                # Check if should freeze (health <= 20)
                if char['health'] <= STARVATION_FREEZE_HEALTH:
                    if not char.get('is_frozen', False):
                        char['is_frozen'] = True
                        # Clear any intent when freezing
                        char.clear_intent()
                        self.state.log_action(f"{name} is too weak to move! (health: {char['health']})")
                
                # Check for morality loss every STARVATION_MORALITY_INTERVAL health lost
                if char['starvation_health_lost'] >= STARVATION_MORALITY_INTERVAL:
                    char['starvation_health_lost'] -= STARVATION_MORALITY_INTERVAL
                    if random.random() < STARVATION_MORALITY_CHANCE:
                        old_morality = char.get('morality', 5)
                        if old_morality > 1:
                            char['morality'] = old_morality - 1
                            self.state.log_action(f"{name}'s morality dropped from {old_morality} to {char['morality']} due to starvation!")
            else:
                # Not starving anymore
                if char.get('is_starving', False):
                    char['is_starving'] = False
                    char['is_frozen'] = False
                    char['starvation_health_lost'] = 0
                    char['ticks_starving'] = 0
    

    def _get_direction_vector(self, facing):
        """Get unit direction vector for a facing direction."""
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
        return vectors.get(facing, (0, 1))



    # =============================================================================
    # UTILITY & HELPER METHODS
    # =============================================================================
    # General-purpose helper functions
    # =============================================================================

    def _face_toward_character(self, char, target):
        """Make char face toward target character."""
        if char.zone == target.zone and char.zone is not None:
            dx = target.prevailing_x - char.prevailing_x
            dy = target.prevailing_y - char.prevailing_y
        else:
            dx = target.x - char.x
            dy = target.y - char.y
        
        if abs(dx) > 0.01 or abs(dy) > 0.01:
            self._update_facing(char, dx, dy)
    
    

    def _reset_idle_state(self, char):
        """Reset idle state when character is no longer idling."""
        char['idle_state'] = 'choosing'
        char['idle_destination'] = None
        char['idle_wait_ticks'] = 0
        char['idle_is_idle'] = False
        char['is_patrolling'] = False
    
