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
    MOVEMENT_SPEED, SPRINT_SPEED, BLOCK_MOVEMENT_SPEED, ENCUMBERED_SPEED,
    CHARACTER_WIDTH, CHARACTER_HEIGHT,
    ATTACK_ANIMATION_DURATION,
    BREAD_PER_BITE, ITEMS, MAX_HUNGER, STARVATION_THRESHOLD,
    WHEAT_TO_BREAD_RATIO,
    DIRECTION_TO_FACINGS, OPPOSITE_DIRECTIONS,
    INTERACT_DISTANCE, FISTS,
    ATTACK_CONE_BASE_ANGLE, ATTACK_CONE_ANGLE,
)
from scenario_world import SIZE

# Get bow stats from ITEMS
_BOW = ITEMS["bow"]


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
        
        # Calculate speed (encumbrance overrides all, then blocking overrides sprint)
        if player.is_over_encumbered():
            speed = ENCUMBERED_SPEED
            player.is_sprinting = False
        elif player.is_blocking:
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

    # =========================================================================
    # BOW DRAW (Ranged Attack)
    # =========================================================================
    
    def handle_shoot_button_down(self, current_tick):
        """Handle shoot button being pressed down (start bow draw).
        
        Args:
            current_tick: Current game tick
            
        Returns:
            True if bow draw started
        """
        player = self.player
        if not player:
            return False
        
        # Can't draw bow if already drawing or charging heavy attack
        if player.is_drawing_bow() or player.is_charging_heavy_attack():
            return False
        
        # Start drawing
        player.start_bow_draw(current_tick)
        return True
    
    def handle_shoot_button_held(self, current_tick):
        """Handle shoot button being held down (update bow draw).

        Args:
            current_tick: Current game tick

        Returns:
            True if currently drawing
        """
        player = self.player
        if not player:
            return False

        return player.update_bow_draw(current_tick)

    def handle_bake_input(self):
        """Handle bake key press.

        Returns:
            True if baked successfully
        """
        player = self.player
        if not player:
            return False

        # Game logic handles ALL validation and logging
        amount_baked = self.logic.bake_bread(player, amount=1, log_errors=True)
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

        # Game logic handles ALL validation and logging
        amount_taken = self.logic.take_from_barrel(player, max_amount=50, log_errors=True)
        return amount_taken > 0
    
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
        self.logic.log_zone_transition(player, house.name, entering=True)
        return True

    def _exit_building(self, player, house):
        """Exit a building interior to exterior."""
        interior = house.interior
        if not interior:
            return False

        player.exit_interior(interior)
        self.logic.log_zone_transition(player, house.name, entering=False)
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
        # Get opposite direction - if window faces north, player must face south
        required_direction = OPPOSITE_DIRECTIONS.get(window.facing, 'south')
        return facing in DIRECTION_TO_FACINGS.get(required_direction, ())
    
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

    # =========================================================================
    # INTERACT / E KEY
    # =========================================================================

    def get_facing_npc(self):
        """Get nearest NPC that player is facing within interact distance.

        Returns:
            Character or None
        """
        player = self.player
        if not player:
            return None

        nearest_npc = None
        nearest_dist = float('inf')

        for char in self.state.characters:
            if char == player:
                continue
            if char.get('health', 100) <= 0:
                continue
            if char.zone != player.zone:
                continue

            # Get positions in local coords (prevailing when interior, x/y when exterior)
            if player.zone:
                px, py = player.prevailing_x, player.prevailing_y
                cx, cy = char.prevailing_x, char.prevailing_y
            else:
                px, py = player.x, player.y
                cx, cy = char.x, char.y

            dist = math.sqrt((px - cx)**2 + (py - cy)**2)

            # Must be within interact distance AND player facing them
            if dist <= INTERACT_DISTANCE and dist < nearest_dist:
                if player.is_facing_position(cx, cy):
                    nearest_npc = char
                    nearest_dist = dist

        return nearest_npc

    def get_available_interaction(self, gui_callbacks):
        """Get what interaction is currently available (for hints and execution).

        This is the SINGLE SOURCE OF TRUTH for all E key interactions.

        Returns dict with interaction info, or None if nothing available:
        {
            'type': str,  # 'door', 'npc', 'corpse', 'barrel', etc.
            'name': str,  # Display name
            'label': str, # Action label (e.g., 'Loot', 'Talk', 'Open')
            'target': object,  # The actual object (NPC, corpse, barrel, etc.)
            'can_interact': bool,  # Whether interaction is allowed
            'blocked_reason': str  # If can_interact=False, why (optional)
        }
        """
        player = self.player
        if not player:
            return None

        # Priority 1: If currently window viewing
        if gui_callbacks['is_window_viewing']():
            return {
                'type': 'window_view',
                'name': 'Window View',
                'label': 'Stop Viewing',
                'target': None,
                'can_interact': True
            }

        # Priority 2: Door (allows escaping combat)
        house = self.state.get_adjacent_door(player)
        if house:
            if player.zone is None:
                return {
                    'type': 'door',
                    'name': house.name,
                    'label': 'Enter',
                    'target': house,
                    'can_interact': True
                }
            else:
                return {
                    'type': 'door',
                    'name': 'Exit',
                    'label': 'Exit Building',
                    'target': house,
                    'can_interact': True
                }

        # Priority 3: NPC (must be facing them)
        npc = gui_callbacks['get_facing_npc'](player)
        if npc:
            can_talk = gui_callbacks['can_start_dialogue'](npc)
            return {
                'type': 'npc',
                'name': npc.get_display_name(),
                'label': 'Talk',
                'target': npc,
                'can_interact': can_talk,
                'blocked_reason': f"{npc.get_display_name()} is busy!" if not can_talk else None
            }

        # Priority 4: Window
        window = self.handle_window_input()
        if window:
            return {
                'type': 'window',
                'name': 'Window',
                'label': 'Look Through',
                'target': window,
                'can_interact': True
            }

        # Priority 5: Cooking spot (stove/campfire - must be facing)
        cooking_spot = self.logic.get_adjacent_cooking_spot(player)
        if cooking_spot:
            source = cooking_spot.get('source')
            if cooking_spot['type'] == 'stove':
                target_x, target_y = source.x + 0.5, source.y + 0.5
                spot_name = source.name
                can_use = source.can_use(player)
            else:  # campfire
                target_x, target_y = source[0] + 0.5, source[1] + 0.5
                spot_name = 'Campfire'
                can_use = True

            if player.is_facing_position(target_x, target_y):
                return {
                    'type': 'cooking',
                    'name': spot_name,
                    'label': 'Bake Bread',
                    'target': cooking_spot,
                    'can_interact': can_use,
                    'blocked_reason': 'Not your stove' if not can_use else None
                }

        # Priority 6: Corpse (must be facing)
        for corpse in self.state.corpses:
            if corpse.zone != player.zone:
                continue

            if player.zone is not None:
                px, py = player.prevailing_x, player.prevailing_y
            else:
                px, py = player.x, player.y

            cx, cy = corpse.center

            import math
            dist = math.sqrt((px - cx)**2 + (py - cy)**2)

            if dist <= INTERACT_DISTANCE:
                if player.is_facing_position(cx, cy):
                    return {
                        'type': 'corpse',
                        'name': f"{corpse.character_name}'s Corpse",
                        'label': 'Loot',
                        'target': corpse,
                        'can_interact': True
                    }

        # Priority 7: Barrel (must be facing)
        for barrel in self.state.interactables.barrels.values():
            if barrel.is_adjacent(player):
                if barrel.zone is not None:
                    target_x, target_y = barrel.x + 0.5, barrel.y + 0.5
                else:
                    target_x, target_y = barrel.world_x, barrel.world_y
                if player.is_facing_position(target_x, target_y):
                    can_use = barrel.can_use(player)
                    return {
                        'type': 'barrel',
                        'name': barrel.name,
                        'label': 'Open',
                        'target': barrel,
                        'can_interact': can_use,
                        'blocked_reason': 'Not your barrel' if not can_use else None
                    }

        # Priority 8: Bed (must be facing)
        for bed in self.state.interactables.beds.values():
            if bed.is_adjacent(player):
                if player.is_facing_position(bed.x + 0.5, bed.y + 0.5):
                    is_owned = bed.is_owned_by(player.name)
                    can_use = is_owned or not bed.is_owned()
                    return {
                        'type': 'bed',
                        'name': bed.name,
                        'label': 'Sleep',
                        'target': bed,
                        'can_interact': False,  # Not implemented
                        'blocked_reason': 'Sleep not implemented yet' if can_use else 'Not your bed'
                    }

        # Priority 9: Tree (must be facing)
        for pos, tree in self.state.interactables.trees.items():
            if tree.is_adjacent(player):
                if player.is_facing_position(tree.x + 0.5, tree.y + 0.5):
                    return {
                        'type': 'tree',
                        'name': 'Tree',
                        'label': 'Shake',
                        'target': tree,
                        'can_interact': False,  # Not implemented
                        'blocked_reason': 'Shaking trees not implemented yet'
                    }

        return None

    def handle_interact(self, gui_callbacks):
        """Handle unified interact (E key / A button).

        Uses get_available_interaction() to determine what to interact with.
        This ensures interaction hints and actual interactions never get out of sync.

        Args:
            gui_callbacks: Dict with callbacks for GUI operations

        Returns:
            str describing what was interacted with, or None
        """
        player = self.player
        if not player:
            return None

        # Get what's available to interact with
        interaction = self.get_available_interaction(gui_callbacks)
        if not interaction:
            return None

        # If blocked, show reason and don't interact
        if not interaction.get('can_interact', False):
            if interaction.get('blocked_reason'):
                self.state.log_action(interaction['blocked_reason'])
            return None

        # Execute the interaction based on type
        itype = interaction['type']
        target = interaction['target']

        if itype == 'window_view':
            gui_callbacks['toggle_window_view_off']()
            return 'window_view_off'

        elif itype == 'door':
            if self.handle_door_input():
                gui_callbacks['update_camera'](player.x, player.y)
                return 'door'

        elif itype == 'npc':
            gui_callbacks['start_dialogue'](target)
            return 'npc'

        elif itype == 'window':
            gui_callbacks['start_window_viewing'](target)
            return 'window'

        elif itype == 'cooking':
            self.handle_bake_input()
            return 'cooking_spot'

        elif itype == 'corpse':
            gui_callbacks['open_inventory_with_corpse'](target)
            return 'corpse'

        elif itype == 'barrel':
            gui_callbacks['open_inventory_with_barrel'](target)
            return 'barrel'

        elif itype == 'bed':
            # Not implemented
            return 'bed'

        elif itype == 'tree':
            # Not implemented
            return 'tree'

        return None

    # =========================================================================
    # COMBAT INPUT
    # =========================================================================

    def handle_combat_input(self, attack, attack_held, attack_released, current_tick):
        """Handle all combat input (melee, ranged, fists) based on equipped weapon.

        Args:
            attack: True if attack button pressed this frame
            attack_held: True if attack button is held down
            attack_released: True if attack button released this frame
            current_tick: Current game tick

        Returns:
            dict with 'action' (None, 'melee_attack', 'ranged_shot', 'bow_charging'),
                     'bow_released' (bool), 'draw_progress' (float 0-1)
        """
        player = self.player
        if not player:
            return {'action': None, 'bow_released': False, 'draw_progress': 0.0}

        # Get equipped weapon type to determine attack behavior
        equipped_weapon_type = player.get_equipped_weapon_type()

        result = {'action': None, 'bow_released': False, 'draw_progress': 0.0}

        if equipped_weapon_type == 'ranged':
            # BOW: Click to draw, release to shoot
            # On attack button press, start drawing bow
            if attack:
                self.handle_shoot_button_down(current_tick)

            # While attack button is held, update draw
            if attack_held:
                self.handle_shoot_button_held(current_tick)
                if player.is_drawing_bow():
                    result['action'] = 'bow_charging'

            # On attack button release, fire arrow
            if attack_released:
                if player.is_drawing_bow():
                    # Get draw progress and release
                    draw_progress = player.release_bow_draw(current_tick)
                    result['bow_released'] = True
                    result['draw_progress'] = draw_progress
                    result['action'] = 'ranged_shot'

            # Cancel any melee charging if switching to bow
            if player.is_charging_heavy_attack():
                player.cancel_heavy_attack()

        elif equipped_weapon_type == 'melee' or equipped_weapon_type is None:
            # SWORD or FISTS: Click for quick attack, hold for heavy attack
            # On attack button press, start tracking
            if attack:
                self.handle_attack_button_down(current_tick)

            # While attack button is held, update charge
            if attack_held:
                self.handle_attack_button_held(current_tick)

            # On attack button release, execute attack
            if attack_released:
                self.handle_attack_button_release(current_tick)
                result['action'] = 'melee_attack'

            # Cancel any bow drawing
            if player.is_drawing_bow():
                player.cancel_bow_draw()

        return result

    # =========================================================================
    # PLAYER STATE QUERIES
    # =========================================================================

    def get_weapon_reach(self):
        """Get the weapon reach for player's currently equipped melee weapon.

        Returns weapon reach from equipped melee weapon, or FISTS range if unarmed.

        Returns:
            Float range in cells
        """
        player = self.player
        if not player:
            return FISTS["range"]

        weapon_stats = player.get_weapon_stats()
        return weapon_stats.get('range', FISTS['range'])

    def update_facing_to_mouse(self, mouse_x, mouse_y, screen_to_world_func):
        """Update player facing direction to face the mouse cursor.

        Also stores the precise angle for 360° attack aiming.

        Args:
            mouse_x: Mouse X position in screen coordinates
            mouse_y: Mouse Y position in screen coordinates
            screen_to_world_func: Callback to convert screen to world coords
        """
        player = self.player
        if not player:
            return

        # Convert mouse position to world coords
        world_x, world_y = screen_to_world_func(mouse_x, mouse_y)

        # Calculate direction from player to mouse
        # Use prevailing coords when in interior (camera space matches interior)
        if player.zone:
            dx = world_x - player.prevailing_x
            dy = world_y - player.prevailing_y
        else:
            dx = world_x - player.x
            dy = world_y - player.y

        # Calculate precise angle and store it for 360° aiming
        angle = math.atan2(dy, dx)
        player.attack_angle = angle

        # Determine 8-direction facing (for sprite animation)
        if angle >= -math.pi/8 and angle < math.pi/8:
            player.facing = 'right'
        elif angle >= math.pi/8 and angle < 3*math.pi/8:
            player.facing = 'down-right'
        elif angle >= 3*math.pi/8 and angle < 5*math.pi/8:
            player.facing = 'down'
        elif angle >= 5*math.pi/8 and angle < 7*math.pi/8:
            player.facing = 'down-left'
        elif angle >= 7*math.pi/8 or angle < -7*math.pi/8:
            player.facing = 'left'
        elif angle >= -7*math.pi/8 and angle < -5*math.pi/8:
            player.facing = 'up-left'
        elif angle >= -5*math.pi/8 and angle < -3*math.pi/8:
            player.facing = 'up'
        elif angle >= -3*math.pi/8 and angle < -math.pi/8:
            player.facing = 'up-right'

    def update_backpedal_state(self, move_dx, move_dy):
        """Check if player is backpedaling (moving opposite to facing).

        Args:
            move_dx: Movement direction X
            move_dy: Movement direction Y

        Returns:
            Dot product of movement and facing vectors (negative = backpedaling)
        """
        player = self.player
        if not player:
            return 0

        facing = player.get('facing', 'down')

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

        face_dx, face_dy = facing_vectors.get(facing, (0, 1))

        # Normalize
        move_mag = math.sqrt(move_dx * move_dx + move_dy * move_dy)
        if move_mag > 0:
            move_dx_norm = move_dx / move_mag
            move_dy_norm = move_dy / move_mag
        else:
            move_dx_norm, move_dy_norm = 0, 0

        face_mag = math.sqrt(face_dx * face_dx + face_dy * face_dy)
        if face_mag > 0:
            face_dx_norm = face_dx / face_mag
            face_dy_norm = face_dy / face_mag
        else:
            face_dx_norm, face_dy_norm = 0, 1

        dot = move_dx_norm * face_dx_norm + move_dy_norm * face_dy_norm
        player['is_backpedaling'] = dot < 0

        return dot

    def handle_movement_no_facing(self, dx, dy, sprinting=False, movement_dot=0):
        """Handle movement input without changing facing direction.

        Used in combat mode to allow strafing while maintaining aim.

        Args:
            dx: -1, 0, or 1 for horizontal direction
            dy: -1, 0, or 1 for vertical direction
            sprinting: True if sprint key is held
            movement_dot: Dot product of movement and facing (for backpedaling)

        Returns:
            True if movement was applied
        """
        player = self.player
        if not player:
            return False

        if player.is_frozen:
            player.vx = 0.0
            player.vy = 0.0
            return False

        # Calculate speed (encumbrance overrides all, then blocking)
        if player.is_over_encumbered():
            speed = ENCUMBERED_SPEED
            player.is_sprinting = False
        elif player.is_blocking:
            speed = BLOCK_MOVEMENT_SPEED
            player.is_sprinting = False
        elif sprinting:
            # Only allow sprinting forward (not backpedaling)
            if movement_dot >= 0:
                speed = SPRINT_SPEED
                player.is_sprinting = True
            else:
                speed = MOVEMENT_SPEED
                player.is_sprinting = False
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

        return True

    def is_char_in_attack_cone(self, char):
        """Check if a character is in the player's attack cone.

        Uses 360° angle-based cone detection matching resolve_attack() in game_logic.py.
        Cone interpolates from BASE_ANGLE at player to full ANGLE at weapon reach.

        Args:
            char: Character to check

        Returns:
            True if character is in the attack cone
        """
        player = self.player
        if not player or char is player:
            return False

        # Skip dead characters
        if char.get('health', 100) <= 0:
            return False

        # Must be in same zone
        if char.zone != player.zone:
            return False

        # Get the precise attack angle (360° aiming)
        attack_angle = player.get('attack_angle')
        if attack_angle is None:
            return False

        # Get weapon reach based on equipped weapon
        weapon_reach = self.get_weapon_reach()

        # Calculate relative position using prevailing coords (local when in interior)
        rel_x = char.prevailing_x - player.prevailing_x
        rel_y = char.prevailing_y - player.prevailing_y

        # Calculate distance to target
        distance = math.sqrt(rel_x * rel_x + rel_y * rel_y)

        # Must be within weapon reach and not at same position
        if distance <= 0 or distance > weapon_reach:
            return False

        # Interpolate cone half-angle based on distance (wider at range)
        half_base_rad = math.radians(ATTACK_CONE_BASE_ANGLE / 2)
        half_full_rad = math.radians(ATTACK_CONE_ANGLE / 2)
        t = distance / weapon_reach  # 0 at player, 1 at max range
        half_cone_rad = half_base_rad + t * (half_full_rad - half_base_rad)

        # Calculate angle to target
        angle_to_target = math.atan2(rel_y, rel_x)

        # Calculate angular difference (handle wraparound)
        angle_diff = angle_to_target - attack_angle
        # Normalize to [-pi, pi]
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi

        # Check if within interpolated cone angle
        return abs(angle_diff) <= half_cone_rad

    def get_chars_in_attack_cone(self):
        """Get all characters currently in the player's attack cone.

        Returns:
            Set of character ids that are in the attack cone
        """
        player = self.player
        if not player:
            return set()

        chars_in_cone = set()
        for char in self.state.characters:
            if self.is_char_in_attack_cone(char):
                chars_in_cone.add(id(char))

        return chars_in_cone
