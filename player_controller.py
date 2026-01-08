# player_controller.py - Handles player input and translates to character actions
"""
PlayerController handles the player-specific input layer.

Responsibilities:
- Input mapping (keys → intents)
- UI state (menus, inventory screens - future)
- Movement input → Character.set_velocity()
- Action input → Character methods + world resolution

This class does NOT:
- Contain game rules (that's in game_logic.py)
- Handle NPC behavior (that's in jobs.py)
- Know about other characters (passes to game for resolution)
"""

import math
import time
from constants import (
    MOVEMENT_SPEED, SPRINT_SPEED, BLOCK_MOVEMENT_SPEED,
    CHARACTER_WIDTH, CHARACTER_HEIGHT,
    ATTACK_ANIMATION_DURATION, WEAPON_REACH,
    BREAD_PER_BITE, ITEMS, MAX_HUNGER, STARVATION_THRESHOLD,
    WHEAT_TO_BREAD_RATIO
)
from scenario_world import SIZE


class PlayerController:
    """
    Translates player input into character actions.
    
    The GUI calls methods here when keys are pressed.
    This controller then calls Character methods and/or
    requests the game to resolve effects.
    """
    
    def __init__(self, game_state, game_logic):
        """
        Args:
            game_state: GameState instance (for collision checks, world queries)
            game_logic: GameLogic instance (for resolving world effects)
        """
        self.state = game_state
        self.logic = game_logic
        
        # UI state (for future expansion)
        self.menu_open = False
        self.inventory_open = False
        
        # Movement state
        self.moving = False
    
    @property
    def player(self):
        """Get the player character, if any."""
        return self.state.player
    
    # =========================================================================
    # MOVEMENT
    # =========================================================================
    
    def handle_movement_input(self, dx, dy, sprinting=False):
        """Handle movement input from held keys.
        
        Args:
            dx: -1, 0, or 1 for horizontal direction
            dy: -1, 0, or 1 for vertical direction  
            sprinting: True if sprint key is held
            
        Returns:
            True if movement was applied
        """
        player = self.player
        if not player:
            return False
        
        # Can't move while frozen
        if player.is_frozen:
            if self.moving:
                self.state.log_action(f"{player.get_display_name()} is too weak to move!")
            player.vx = 0.0
            player.vy = 0.0
            self.moving = False
            return False
        
        # Update facing based on input
        self._update_facing(player, dx, dy)
        
        # Calculate speed (blocking overrides sprint)
        if player.is_blocking:
            speed = BLOCK_MOVEMENT_SPEED
            player.is_sprinting = False
        elif sprinting:
            speed = SPRINT_SPEED
            player.is_sprinting = True
        else:
            speed = MOVEMENT_SPEED
            player.is_sprinting = False
        
        # Normalize diagonal movement
        if dx != 0 and dy != 0:
            diagonal_factor = 1.0 / math.sqrt(2)
            player.vx = dx * speed * diagonal_factor
            player.vy = dy * speed * diagonal_factor
        else:
            player.vx = dx * speed
            player.vy = dy * speed
        
        self.moving = True
        return True
    
    def stop_movement(self):
        """Stop player movement (no movement keys held)."""
        player = self.player
        if player:
            player.vx = 0.0
            player.vy = 0.0
            player.is_sprinting = False
        self.moving = False
    
    def update_position(self, dt):
        """Update player position based on velocity.
        Called every frame by GUI.
        
        Args:
            dt: Delta time in seconds
        """
        player = self.player
        if not player:
            return
        
        # Check if player is in an interior
        if player.zone is not None:
            self.update_position_interior(dt)
            return
        
        vx = player.vx
        vy = player.vy
        
        if vx == 0.0 and vy == 0.0:
            return
        
        # Calculate new position
        new_x = player.x + vx * dt
        new_y = player.y + vy * dt
        
        # Keep within bounds (allow touching edges)
        new_x = max(0, min(SIZE, new_x))
        new_y = max(0, min(SIZE, new_y))
        
        # Try to move, handling collisions
        self._apply_movement_with_collision(player, new_x, new_y, vx, vy, dt)
    
    def _update_facing(self, player, dx, dy):
        """Update character facing direction based on movement input."""
        if dx > 0 and dy < 0:
            player.facing = 'up-right'
        elif dx > 0 and dy > 0:
            player.facing = 'down-right'
        elif dx < 0 and dy < 0:
            player.facing = 'up-left'
        elif dx < 0 and dy > 0:
            player.facing = 'down-left'
        elif dx > 0:
            player.facing = 'right'
        elif dx < 0:
            player.facing = 'left'
        elif dy > 0:
            player.facing = 'down'
        elif dy < 0:
            player.facing = 'up'
    
    def _apply_movement_with_collision(self, player, new_x, new_y, vx, vy, dt):
        """Apply movement with ALTTP-style collision sliding."""
        # Try full movement first
        if not self.state.is_position_blocked(new_x, new_y, exclude_char=player):
            player.x = new_x
            player.y = new_y
            return
        
        # Blocked - try sliding along axes
        moved = False
        
        if abs(vx) > abs(vy):
            # Moving mostly horizontal - try X first, then Y
            if not self.state.is_position_blocked(new_x, player.y, exclude_char=player):
                player.x = new_x
                moved = True
            elif not self.state.is_position_blocked(player.x, new_y, exclude_char=player):
                player.y = new_y
                moved = True
        else:
            # Moving mostly vertical - try Y first, then X
            if not self.state.is_position_blocked(player.x, new_y, exclude_char=player):
                player.y = new_y
                moved = True
            elif not self.state.is_position_blocked(new_x, player.y, exclude_char=player):
                player.x = new_x
                moved = True
        
        # If still blocked, try perpendicular jostling
        if not moved:
            jostle_amount = MOVEMENT_SPEED * dt * 0.3
            if abs(vx) > abs(vy):
                # Moving horizontal, jostle vertical
                for jostle_dir in [1, -1]:
                    jostle_y = player.y + jostle_dir * jostle_amount
                    if not self.state.is_position_blocked(player.x, jostle_y, exclude_char=player):
                        player.y = jostle_y
                        break
            else:
                # Moving vertical, jostle horizontal
                for jostle_dir in [1, -1]:
                    jostle_x = player.x + jostle_dir * jostle_amount
                    if not self.state.is_position_blocked(jostle_x, player.y, exclude_char=player):
                        player.x = jostle_x
                        break
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def handle_attack_input(self):
        """Handle attack key press (quick attack, no heavy charge).
        
        Returns:
            True if attack was initiated
        """
        player = self.player
        if not player:
            return False
        
        # Check if can attack (not already animating)
        if not player.can_attack():
            return False
        
        # Get the precise attack angle for 360° aiming (set by GUI from mouse position)
        attack_angle = player.get('attack_angle')
        
        # Start attack animation - damage will be dealt when animation completes
        # (processed by game_logic._process_pending_attacks)
        attack_dir = player.start_attack(angle=attack_angle, damage_multiplier=1.0)
        
        return True

    def handle_attack_button_down(self, current_tick):
        """Handle attack button being pressed down (start of potential heavy attack).
        
        Args:
            current_tick: Current game tick
            
        Returns:
            True if heavy attack tracking started
        """
        player = self.player
        if not player:
            return False
        
        # Can't start heavy attack if already animating an attack
        if not player.can_attack():
            return False
        
        # Start tracking the hold
        player.start_heavy_attack_hold(current_tick)
        return True
    
    def handle_attack_button_held(self, current_tick):
        """Handle attack button being held down (update heavy attack charge).
        
        Args:
            current_tick: Current game tick
            
        Returns:
            True if now in charging state (past threshold)
        """
        player = self.player
        if not player:
            return False
        
        return player.update_heavy_attack(current_tick)
    
    def handle_attack_button_release(self, current_tick):
        """Handle attack button being released (execute attack).
        
        Args:
            current_tick: Current game tick
            
        Returns:
            True if attack was executed
        """
        player = self.player
        if not player:
            return False
        
        # Check if can attack (not already animating)
        if not player.can_attack():
            player.cancel_heavy_attack()
            return False
        
        # Get heavy attack result
        was_heavy, multiplier = player.release_heavy_attack(current_tick)
        
        # Get the precise attack angle for 360° aiming
        attack_angle = player.get('attack_angle')
        
        # Start attack animation with multiplier stored - damage dealt when animation completes
        # (processed by game_logic._process_pending_attacks)
        attack_dir = player.start_attack(angle=attack_angle, damage_multiplier=multiplier)
        
        return True

    def handle_bake_input(self):
        """Handle bake key press.
        
        Returns:
            True if baked successfully
        """
        player = self.player
        if not player:
            return False
        
        name = player.get_display_name()
        
        # Check for adjacent cooking spot (requires world knowledge)
        cooking_spot = self.logic.get_adjacent_cooking_spot(player)
        
        if not cooking_spot:
            # Give helpful feedback
            stove = self.state.interactables.get_adjacent_stove(player)
            if stove and not stove.can_use(player):
                self.state.log_action(f"{name} can't use this stove (not your home)")
            else:
                self.state.log_action(f"{name} needs to be near a stove or campfire to bake")
            return False
        
        if player.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
            self.state.log_action(f"{name} needs wheat to bake bread")
            return False
        
        if not player.can_add_item('bread', 1):
            self.state.log_action(f"{name}'s inventory is full")
            return False
        
        # Bake through game logic (handles the actual conversion)
        amount_baked = self.logic.bake_bread(player, 1)
        return amount_baked > 0
    
    def handle_barrel_input(self):
        """Handle barrel interaction key press.
        
        Takes wheat from an adjacent barrel if possible.
        
        Returns:
            True if successfully took wheat
        """
        player = self.player
        if not player:
            return False
        
        name = player.get_display_name()
        
        # Find adjacent barrel
        for barrel in self.state.interactables.barrels.values():
            if barrel.is_adjacent(player):
                if not barrel.can_use(player):
                    self.state.log_action(f"{name} can't use this barrel (not your home)")
                    return False
                
                wheat_count = barrel.get_wheat()
                if wheat_count <= 0:
                    self.state.log_action(f"{barrel.name} is empty")
                    return False
                
                # Take as much wheat as player can carry
                can_take = min(wheat_count, 50)  # Take up to 50 at a time
                if not player.can_add_item('wheat', 1):
                    self.state.log_action(f"{name}'s inventory is full")
                    return False
                
                # Calculate how much we can actually take
                taken = 0
                for _ in range(can_take):
                    if not player.can_add_item('wheat', 1):
                        break
                    if barrel.get_wheat() <= 0:
                        break
                    barrel.remove_wheat(1)
                    player.add_item('wheat', 1)
                    taken += 1
                
                if taken > 0:
                    self.state.log_action(f"{name} took {taken} wheat from {barrel.name}")
                    return True
                
                return False
        
        return False
    
    # =========================================================================
    # DOOR/BUILDING INTERACTION
    # =========================================================================
    
    def handle_door_input(self):
        """Handle door interaction key press.
        
        If at a door, enters or exits the building.
        
        Returns:
            True if successfully entered/exited
        """
        player = self.player
        if not player:
            return False
        
        name = player.get_display_name()
        
        # Check if we're at a door
        house = self.state.get_adjacent_door(player)
        
        if not house:
            return False
        
        if player.zone is None:
            # Currently outside - try to enter
            return self._enter_building(player, house)
        else:
            # Currently inside - try to exit
            return self._exit_building(player, house)
    
    def _enter_building(self, player, house):
        """Enter a building interior."""
        interior = house.interior
        if not interior:
            self.state.log_action(f"{player.get_display_name()} can't enter {house.name}")
            return False
        
        player.enter_interior(interior)
        self.state.log_action(f"{player.get_display_name()} entered {house.name}")
        return True
    
    def _exit_building(self, player, house):
        """Exit a building interior to exterior."""
        interior = house.interior
        if not interior:
            return False
        
        player.exit_interior(interior)
        self.state.log_action(f"{player.get_display_name()} exited {house.name}")
        return True
    
    # =========================================================================
    # WINDOW "SECURITY CAMERA" VIEW
    # =========================================================================
    
    def handle_window_input(self):
        """Handle window interaction key press.
        
        If at a window, toggles "security camera" view to look outside/inside.
        Works from both inside (looking out) and outside (looking in).
        
        Returns:
            Window object if activating view, None if deactivating or not at window
        """
        player = self.player
        if not player:
            return None
        
        if player.zone is not None:
            # Player is inside - check interior windows to look out
            interior = self.state.interiors.get_interior(player.zone)
            if not interior:
                return None
            
            for window in interior.windows:
                if window.is_character_near(player.prevailing_x, player.prevailing_y, threshold=1.0):
                    return window
        else:
            # Player is outside - check all house windows to look in
            # Must be near window AND facing toward it
            for house in self.state.interactables.get_all_houses():
                interior = house.interior
                if not interior:
                    continue
                
                for window in interior.windows:
                    if window.is_character_near_exterior(player.x, player.y, threshold=1.0):
                        # Must be facing toward the window (opposite of window's facing)
                        if self._is_facing_toward_window(player, window):
                            return window
        
        return None
    
    def _is_facing_toward_window(self, player, window):
        """Check if player is facing toward a window from outside.
        
        The player must face the opposite direction of the window's facing.
        e.g., a north-facing window requires facing south to look in.
        """
        facing = player.get('facing', 'down')
        
        # Map window facing to required player facings
        required_facings = {
            'north': ('down', 'down-left', 'down-right'),
            'south': ('up', 'up-left', 'up-right'),
            'east': ('left', 'up-left', 'down-left'),
            'west': ('right', 'up-right', 'down-right'),
        }
        
        return facing in required_facings.get(window.facing, ())
    
    def get_window_camera_position(self, window):
        """
        Get the world position the camera should move to for window viewing.
        
        Args:
            window: Window object
            
        Returns:
            (world_x, world_y) tuple for camera position
        """
        return window.get_exterior_look_position()
    
    # =========================================================================
    # INTERIOR MOVEMENT
    # =========================================================================
    
    def update_position_interior(self, dt):
        """Update player position when inside an interior.
        Called every frame by GUI when player is in an interior.
        
        Args:
            dt: Delta time in seconds
        """
        player = self.player
        if not player or player.zone is None:
            return
        
        interior = self.state.interiors.get_interior(player.zone)
        if not interior:
            return
        
        vx = player.vx
        vy = player.vy
        
        if vx == 0.0 and vy == 0.0:
            return
        
        # Calculate new position using local coords (interior space)
        new_x = player.prevailing_x + vx * dt
        new_y = player.prevailing_y + vy * dt
        
        # Keep within interior bounds (allow touching edges)
        new_x = max(0, min(interior.width, new_x))
        new_y = max(0, min(interior.height, new_y))
        
        # Check collision using unified system (same as exterior)
        zone = interior.name
        if not self.state.is_position_blocked(new_x, new_y, exclude_char=player, zone=zone):
            player.prevailing_x = new_x
            player.prevailing_y = new_y
        else:
            # Try sliding along axes
            if not self.state.is_position_blocked(new_x, player.prevailing_y, exclude_char=player, zone=zone):
                player.prevailing_x = new_x
            elif not self.state.is_position_blocked(player.prevailing_x, new_y, exclude_char=player, zone=zone):
                player.prevailing_y = new_y
