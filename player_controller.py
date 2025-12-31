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
    MOVEMENT_SPEED, SPRINT_SPEED, 
    CHARACTER_WIDTH, CHARACTER_HEIGHT,
    ATTACK_ANIMATION_DURATION, COMBAT_RANGE,
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
        
        # Calculate speed
        speed = SPRINT_SPEED if sprinting else MOVEMENT_SPEED
        player.is_sprinting = sprinting
        
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
        
        vx = player.vx
        vy = player.vy
        
        if vx == 0.0 and vy == 0.0:
            return
        
        # Calculate new position
        new_x = player.x + vx * dt
        new_y = player.y + vy * dt
        
        # Keep within bounds
        half_width = player.width / 2
        half_height = player.height / 2
        new_x = max(half_width, min(SIZE - half_width, new_x))
        new_y = max(half_height, min(SIZE - half_height, new_y))
        
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
        """Handle attack key press.
        
        Returns:
            True if attack was initiated
        """
        player = self.player
        if not player:
            return False
        
        # Check if can attack (not already animating)
        if not player.can_attack():
            return False
        
        # Start attack animation on character
        attack_dir = player.start_attack()
        
        # Find targets and resolve damage through game logic
        # This is the same resolution path NPCs use
        targets_hit = self.logic.resolve_attack(player, attack_dir)
        
        return True
    
    def handle_eat_input(self):
        """Handle eat key press.
        
        Returns:
            True if ate successfully
        """
        player = self.player
        if not player:
            return False
        
        # Use character's eat method
        result = player.eat()
        
        if result['success']:
            msg = f"{player.get_display_name()} ate bread, hunger now {player.hunger:.0f}"
            if result.get('recovered_from_starvation'):
                msg = f"{player.get_display_name()} ate bread and recovered from starvation! Hunger: {player.hunger:.0f}"
            self.state.log_action(msg)
        
        return result['success']
    
    def handle_trade_input(self):
        """Handle trade key press.
        
        Returns:
            True if traded successfully
        """
        player = self.player
        if not player:
            return False
        
        name = player.get_display_name()
        
        # Find adjacent vendor - this requires world knowledge
        vendor = self.logic.find_adjacent_vendor(player, 'wheat')
        
        if not vendor:
            return False
        
        if not player.can_add_item('wheat', 1):
            self.state.log_action(f"{name}'s inventory is full")
            return False
        
        if not self.logic.can_afford_goods(player, 'wheat'):
            self.state.log_action(f"{name} can't afford any wheat")
            return False
        
        vendor_name = vendor.get_display_name()
        
        if not self.logic.vendor_willing_to_trade(vendor, player, 'wheat'):
            self.state.log_action(f"{name} tried to trade but {vendor_name} refused")
            return False
        
        # Execute trade through game logic
        amount = self.logic.get_max_vendor_trade_amount(vendor, player, 'wheat')
        if amount > 0:
            price = self.logic.get_goods_price('wheat', amount)
            self.logic.execute_vendor_trade(vendor, player, 'wheat', amount)
            self.state.log_action(f"{name} bought {amount} wheat for ${price} from {vendor_name}")
            
            # Auto-eat if starving and have bread
            if player.is_starving or player.is_frozen:
                if player.get_item('bread') >= BREAD_PER_BITE:
                    result = player.eat()
                    if result.get('recovered_from_starvation'):
                        self.state.log_action(f"{name} ate bread and recovered from starvation! Hunger: {player.hunger:.0f}")
            
            return True
        
        return False
    
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
