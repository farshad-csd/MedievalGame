# gui.py - Pure GUI: rendering and input handling (Raylib)
"""
Raylib-based GUI for cross-platform support:
- Windows, Mac, Linux
- Android (Retroid/Anbernic devices)
- Full gamepad/controller support
- Designed for future Rust migration (raylib-rs)

This module contains ONLY:
- Raylib setup and rendering
- Input handling (keyboard, mouse, gamepad)

It does NOT contain:
- Game logic (that's in game_logic.py)
- Game state (that's in game_state.py)
"""

import pyray as rl
import time
import math
import os
from constants import (
    CELL_SIZE, UPDATE_INTERVAL,
    FARM_CELL_COLORS, JOB_TIERS,
    BG_COLOR, GRID_COLOR, ROAD_COLOR,
    TICKS_PER_DAY, TICKS_PER_YEAR, SLEEP_START_FRACTION,
    MOVEMENT_SPEED, CHARACTER_WIDTH, CHARACTER_HEIGHT,
    DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, ZOOM_SPEED, SPRINT_SPEED,
    SOUND_RADIUS, VISION_RANGE, VISION_CONE_ANGLE, SHOW_PERCEPTION_DEBUG,
    ADJACENCY_DISTANCE, SKILLS
)
from scenario_world import AREAS, BARRELS, BEDS, VILLAGE_NAME, SIZE, ROADS
from game_state import GameState
from game_logic import GameLogic
from player_controller import PlayerController
from sprites import get_sprite_manager


# =============================================================================
# HUD CONFIGURATION
# =============================================================================

HUD_FONT_SIZE_SMALL = 10
HUD_FONT_SIZE_MEDIUM = 13
HUD_FONT_SIZE_LARGE = 16
HUD_FONT_SIZE_TITLE = 22

HUD_MARGIN = 30
HUD_BAR_WIDTH = 150
HUD_BAR_HEIGHT = 4

# Stat bar colors (RGBA)
COLOR_HEALTH = rl.Color(201, 76, 76, 255)      # Red
COLOR_STAMINA = rl.Color(92, 184, 92, 255)     # Green  
COLOR_FATIGUE = rl.Color(91, 192, 222, 255)    # Cyan
COLOR_HUNGER = rl.Color(217, 164, 65, 255)     # Gold/Orange

# UI colors
COLOR_TEXT_BRIGHT = rl.Color(255, 255, 255, 230)
COLOR_TEXT_DIM = rl.Color(255, 255, 255, 128)
COLOR_TEXT_FAINT = rl.Color(255, 255, 255, 64)
COLOR_BG_PANEL = rl.Color(0, 0, 0, 100)
COLOR_BG_SLOT = rl.Color(255, 255, 255, 20)
COLOR_BG_SLOT_ACTIVE = rl.Color(255, 255, 255, 50)
COLOR_BORDER = rl.Color(255, 255, 255, 60)


def hex_to_rgb(hex_color):
    """Convert hex color string to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def hex_to_color(hex_color, alpha=255):
    """Convert hex color string to Raylib Color"""
    r, g, b = hex_to_rgb(hex_color)
    return rl.Color(r, g, b, alpha)


class InputState:
    """Tracks input state from all sources (keyboard, gamepad, mouse)"""
    
    def __init__(self):
        # Movement
        self.move_x = 0.0  # -1 to 1
        self.move_y = 0.0  # -1 to 1
        self.sprint = False
        
        # Actions
        self.attack = False
        self.eat = False
        self.trade = False
        self.bake = False
        self.make_camp = False
        self.recenter = False
        
        # Camera
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.zoom_in = False
        self.zoom_out = False
        
        # Menu/UI
        self.pause = False
        self.menu = False
        self.inventory_toggle = False
        
        # Mouse state
        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_left_click = False
        self.mouse_right_click = False
        self.mouse_wheel = 0.0
        
        # Gamepad state
        self.gamepad_connected = False
        self.gamepad_id = 0


class BoardGUI:
    """
    Raylib-based GUI class - handles rendering and input.
    
    Features:
    - Cross-platform (Windows, Mac, Linux, Android)
    - Full gamepad/controller support
    - Sprite layering like Terraria
    - Designed for Rust migration compatibility
    """
    
    # Color constants
    BG_COLOR_RGB = hex_to_rgb(BG_COLOR)
    GRID_COLOR_RGB = hex_to_rgb(GRID_COLOR)
    
    def __init__(self):
        """Initialize Raylib and game components."""
        # Create game state and logic first (before graphics)
        self.state = GameState()
        self.logic = GameLogic(self.state)
        self.player_controller = PlayerController(self.state, self.logic)
        
        # Input state
        self.input = InputState()
        
        # Get script directory for resource loading
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Initialize Raylib window
        self._init_window()
        
        # Load resources
        self._load_resources()
        
        # Camera state
        if self.state.player:
            self.camera_x = self.state.player['x']
            self.camera_y = self.state.player['y']
        else:
            self.camera_x = SIZE / 2
            self.camera_y = SIZE / 2
        self.zoom = DEFAULT_ZOOM
        self.camera_following_player = True
        
        # Pre-compute road set for fast lookup
        self._road_set = set(tuple(r) for r in ROADS)
        
        # Timing
        self.last_frame_time = time.time()
        self._accumulated_time = 0.0
        
        # Movement state
        self.player_moving = False
        
        # Running state
        self.running = True
        
        # UI state
        self.inventory_open = False
        self.inventory_tab = 0  # 0=world, 1=status, 2=map
        
        # Debug window (optional - can be disabled for mobile)
        self.debug_window = None
        try:
            from debug_window import DebugWindow
            self.debug_window = DebugWindow(self.state, self.logic)
        except ImportError:
            pass
    
    def _init_window(self):
        """Initialize Raylib window with appropriate size."""
        # Set config flags before window creation
        rl.set_config_flags(rl.FLAG_WINDOW_RESIZABLE | rl.FLAG_VSYNC_HINT)
        
        # Get monitor size for initial window dimensions
        # Note: This must be called after SetConfigFlags but before InitWindow
        # So we use default values and resize after
        initial_width = 960
        initial_height = 540
        
        rl.init_window(initial_width, initial_height, f"{VILLAGE_NAME} - Village Simulation")
        rl.set_target_fps(60)
        
        # Disable ESC key from closing window (we use it for pause)
        rl.set_exit_key(0)
        
        # Now get actual monitor size and resize
        monitor = rl.get_current_monitor()
        screen_width = rl.get_monitor_width(monitor)
        screen_height = rl.get_monitor_height(monitor)
        
        # Window is half screen width with 16:9 aspect ratio
        self.window_width = screen_width // 2
        self.window_height = int(self.window_width * 9 / 16)
        
        # Ensure window fits on screen
        if self.window_height > screen_height - 100:
            self.window_height = screen_height - 100
            self.window_width = int(self.window_height * 16 / 9)
        
        rl.set_window_size(self.window_width, self.window_height)
        
        self.canvas_width = self.window_width
        self.canvas_height = self.window_height
        
        # Initialize audio
        rl.init_audio_device()
        
        # Load and play background music
        music_path = os.path.join(self.script_dir, "Forest__8-Bit_Music_.mp3")
        self.music = None
        if os.path.exists(music_path):
            self.music = rl.load_music_stream(music_path)
            rl.set_music_volume(self.music, 0.3)
            rl.play_music_stream(self.music)
    
    def _load_resources(self):
        """Load all game resources (sprites, textures, fonts)."""
        # Initialize sprite manager
        self.sprite_manager = get_sprite_manager(self.script_dir)
        self.sprite_manager.load_sprites()
        
        # Load world sprites
        self.world_textures = {}
        sprite_files = {
            'tree': 'sprites/Tree.png',
            'road': 'sprites/Road.png',
            'barrel': 'sprites/Barrel.png',
            'campfire': 'sprites/Campfire.png',
            'house_s': 'sprites/House_S.png',
            'house_m': 'sprites/House_M.png',
            'grass': 'sprites/Grass_BG.png',
        }
        
        for name, filename in sprite_files.items():
            filepath = os.path.join(self.script_dir, filename)
            if os.path.exists(filepath):
                self.world_textures[name] = rl.load_texture(filepath)
            else:
                print(f"Warning: World sprite not found: {filepath}")
                self.world_textures[name] = None
        
        # Extract campfire frames
        self.campfire_frames = []
        campfire_tex = self.world_textures.get('campfire')
        if campfire_tex:
            frame_width = 32
            frame_height = 32
            num_frames = campfire_tex.width // frame_width
            for i in range(num_frames):
                self.campfire_frames.append(rl.Rectangle(
                    i * frame_width, 0, frame_width, frame_height
                ))
        
        # Load fonts
        self.font_default = rl.get_font_default()
    
    def run(self):
        """Main game loop"""
        while self.running and not rl.window_should_close():
            # Update music stream
            if self.music:
                rl.update_music_stream(self.music)
            
            self._handle_input()
            self._game_loop()
            self._render_frame()
            
            # Update debug window if present
            if self.debug_window and self.debug_window.is_open():
                player = self.state.player
                if player:
                    player_food = player.get_item('wheat')
                    player_money = player.get_item('money')
                    status = f"Pos:({player.x:.1f},{player.y:.1f}) Wheat:{player_food} ${player_money} HP:{player.health} | Zoom:{self.zoom:.1f}x | {'Follow' if self.camera_following_player else 'Free'}"
                else:
                    status = f"No player | Zoom:{self.zoom:.1f}x"
                self.debug_window.set_status(status)
                self.debug_window.update()
        
        # Cleanup
        self._cleanup()
    
    def _cleanup(self):
        """Clean up resources"""
        if self.debug_window:
            self.debug_window.close()
        
        # Unload textures
        for tex in self.world_textures.values():
            if tex:
                rl.unload_texture(tex)
        
        # Unload music
        if self.music:
            rl.unload_music_stream(self.music)
        
        rl.close_audio_device()
        rl.close_window()
    
    # =========================================================================
    # INPUT HANDLING
    # =========================================================================
    
    def _handle_input(self):
        """Handle all input sources (keyboard, mouse, gamepad)"""
        # Reset per-frame input state
        self.input.attack = False
        self.input.eat = False
        self.input.trade = False
        self.input.bake = False
        self.input.make_camp = False
        self.input.recenter = False
        self.input.pause = False
        self.input.inventory_toggle = False
        self.input.zoom_in = False
        self.input.zoom_out = False
        self.input.mouse_left_click = False
        self.input.mouse_right_click = False
        
        # Handle resize
        if rl.is_window_resized():
            self.window_width = rl.get_screen_width()
            self.window_height = rl.get_screen_height()
            self.canvas_width = self.window_width
            self.canvas_height = self.window_height
        
        # Gather input from all sources
        self._handle_keyboard_input()
        self._handle_mouse_input()
        self._handle_gamepad_input()
        
        # Apply UI input first (pause, inventory)
        self._apply_ui_input()
        
        # Apply all game input (even when inventory is open)
        self._apply_movement_input()
        self._apply_action_input()
        self._apply_camera_input()
    
    def _handle_keyboard_input(self):
        """Handle keyboard input"""
        # Movement (WASD)
        move_x = 0.0
        move_y = 0.0
        
        if rl.is_key_down(rl.KEY_W):
            move_y = -1.0
        elif rl.is_key_down(rl.KEY_S):
            move_y = 1.0
        
        if rl.is_key_down(rl.KEY_A):
            move_x = -1.0
        elif rl.is_key_down(rl.KEY_D):
            move_x = 1.0
        
        # Only update if keyboard is providing movement
        if move_x != 0 or move_y != 0:
            self.input.move_x = move_x
            self.input.move_y = move_y
        
        # Sprint (Shift)
        self.input.sprint = rl.is_key_down(rl.KEY_LEFT_SHIFT) or rl.is_key_down(rl.KEY_RIGHT_SHIFT)
        
        # Camera panning (Arrow keys)
        pan_x = 0.0
        pan_y = 0.0
        
        if rl.is_key_down(rl.KEY_UP):
            pan_y = -1.0
        elif rl.is_key_down(rl.KEY_DOWN):
            pan_y = 1.0
        
        if rl.is_key_down(rl.KEY_LEFT):
            pan_x = -1.0
        elif rl.is_key_down(rl.KEY_RIGHT):
            pan_x = 1.0
        
        self.input.pan_x = pan_x
        self.input.pan_y = pan_y
        
        # Actions (key pressed, not held)
        if rl.is_key_pressed(rl.KEY_E):
            self.input.eat = True
        if rl.is_key_pressed(rl.KEY_T):
            self.input.trade = True
        if rl.is_key_pressed(rl.KEY_B):
            self.input.bake = True
        if rl.is_key_pressed(rl.KEY_C):
            self.input.make_camp = True
        if rl.is_key_pressed(rl.KEY_R):
            self.input.recenter = True
        if rl.is_key_pressed(rl.KEY_ESCAPE):
            self.input.pause = True
        
        # Inventory toggle (I or Tab)
        if rl.is_key_pressed(rl.KEY_I) or rl.is_key_pressed(rl.KEY_TAB):
            self.input.inventory_toggle = True
        
        # Zoom
        if rl.is_key_pressed(rl.KEY_EQUAL) or rl.is_key_pressed(rl.KEY_KP_ADD):
            self.input.zoom_in = True
        if rl.is_key_pressed(rl.KEY_MINUS) or rl.is_key_pressed(rl.KEY_KP_SUBTRACT):
            self.input.zoom_out = True
    
    def _handle_mouse_input(self):
        """Handle mouse input"""
        self.input.mouse_x = rl.get_mouse_x()
        self.input.mouse_y = rl.get_mouse_y()
        
        if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            self.input.mouse_left_click = True
            self.input.attack = True
        
        if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_RIGHT):
            self.input.mouse_right_click = True
        
        # Mouse wheel for zoom
        wheel = rl.get_mouse_wheel_move()
        if wheel != 0:
            self.input.mouse_wheel = wheel
            if wheel > 0:
                self.input.zoom_in = True
            else:
                self.input.zoom_out = True
    
    def _handle_gamepad_input(self):
        """Handle gamepad/controller input"""
        # Check for connected gamepad
        gamepad_id = -1
        for i in range(4):  # Check up to 4 gamepads
            if rl.is_gamepad_available(i):
                gamepad_id = i
                break
        
        if gamepad_id < 0:
            self.input.gamepad_connected = False
            return
        
        self.input.gamepad_connected = True
        self.input.gamepad_id = gamepad_id
        
        # Left stick for movement
        left_x = rl.get_gamepad_axis_movement(gamepad_id, rl.GAMEPAD_AXIS_LEFT_X)
        left_y = rl.get_gamepad_axis_movement(gamepad_id, rl.GAMEPAD_AXIS_LEFT_Y)
        
        # Apply deadzone
        deadzone = 0.15
        if abs(left_x) > deadzone:
            self.input.move_x = left_x
        if abs(left_y) > deadzone:
            self.input.move_y = left_y
        
        # Right stick for camera panning
        right_x = rl.get_gamepad_axis_movement(gamepad_id, rl.GAMEPAD_AXIS_RIGHT_X)
        right_y = rl.get_gamepad_axis_movement(gamepad_id, rl.GAMEPAD_AXIS_RIGHT_Y)
        
        if abs(right_x) > deadzone:
            self.input.pan_x = right_x
        if abs(right_y) > deadzone:
            self.input.pan_y = right_y
        
        # Triggers for zoom
        left_trigger = rl.get_gamepad_axis_movement(gamepad_id, rl.GAMEPAD_AXIS_LEFT_TRIGGER)
        right_trigger = rl.get_gamepad_axis_movement(gamepad_id, rl.GAMEPAD_AXIS_RIGHT_TRIGGER)
        
        if left_trigger > 0.5:
            self.input.zoom_out = True
        if right_trigger > 0.5:
            self.input.zoom_in = True
        
        # Face buttons
        # A/Cross - Attack
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_DOWN):
            self.input.attack = True
        
        # B/Circle - Make camp
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_RIGHT):
            self.input.make_camp = True
        
        # X/Square - Trade
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_LEFT):
            self.input.trade = True
        
        # Y/Triangle - Eat
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_UP):
            self.input.eat = True
        
        # Bumpers
        # Left bumper - Bake
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_LEFT_TRIGGER_1):
            self.input.bake = True
        
        # Right bumper - Sprint (hold)
        self.input.sprint = self.input.sprint or rl.is_gamepad_button_down(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_TRIGGER_1)
        
        # Start - Pause
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_MIDDLE_RIGHT):
            self.input.pause = True
        
        # Select/Back - Inventory toggle
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_MIDDLE_LEFT):
            self.input.inventory_toggle = True
    
    def _apply_movement_input(self):
        """Apply movement input to player"""
        player = self.state.player
        if not player:
            return
        
        # Block movement and facing changes when inventory is open
        if self.inventory_open:
            if self.player_moving:
                self.player_controller.stop_movement()
                self.player_moving = False
            return
        
        # Update player facing based on mouse (when using keyboard/mouse)
        if not self.input.gamepad_connected or (self.input.move_x == 0 and self.input.move_y == 0):
            self._update_player_facing_to_mouse()
        
        dx = self.input.move_x
        dy = self.input.move_y
        
        if dx != 0 or dy != 0:
            # Normalize diagonal movement
            magnitude = math.sqrt(dx * dx + dy * dy)
            if magnitude > 1.0:
                dx /= magnitude
                dy /= magnitude
            
            # Calculate backpedal state
            movement_dot = self._update_backpedal_state(dx, dy)
            
            # Apply movement
            self._handle_movement_no_facing(dx, dy, self.input.sprint, movement_dot)
            self.player_moving = True
        else:
            if self.player_moving:
                self.player_controller.stop_movement()
                self.player_moving = False
            if player:
                player['is_backpedaling'] = False
        
        # Reset movement input for next frame
        self.input.move_x = 0.0
        self.input.move_y = 0.0
    
    def _apply_action_input(self):
        """Apply action input"""
        # Block actions when inventory is open
        if self.inventory_open:
            return
        
        if self.input.attack:
            self.player_controller.handle_attack_input()
        
        if self.input.eat:
            self.player_controller.handle_eat_input()
        
        if self.input.trade:
            self.player_controller.handle_trade_input()
        
        if self.input.bake:
            self.player_controller.handle_bake_input()
        
        if self.input.make_camp:
            self._handle_make_camp()
    
    def _apply_camera_input(self):
        """Apply camera control input"""
        # Recenter on player
        if self.input.recenter:
            self.camera_following_player = True
            if self.state.player:
                self.camera_x = self.state.player['x']
                self.camera_y = self.state.player['y']
        
        # Manual panning
        if self.input.pan_x != 0 or self.input.pan_y != 0:
            self.camera_following_player = False
            pan_speed = 0.15 / self.zoom
            self.camera_x += self.input.pan_x * pan_speed
            self.camera_y += self.input.pan_y * pan_speed
        
        # Zoom
        if self.input.zoom_in:
            self.zoom = min(MAX_ZOOM, self.zoom + ZOOM_SPEED)
        if self.input.zoom_out:
            self.zoom = max(MIN_ZOOM, self.zoom - ZOOM_SPEED)
        
        # Maintain centering on player if following
        if self.camera_following_player and self.state.player:
            self.camera_x = self.state.player['x']
            self.camera_y = self.state.player['y']
    
    def _apply_ui_input(self):
        """Apply UI input (pause, inventory)"""
        # Escape = toggle pause (always, regardless of inventory state)
        if self.input.pause:
            self.state.paused = not self.state.paused
        
        # Inventory toggle (I/Tab or Select button)
        if self.input.inventory_toggle:
            self.inventory_open = not self.inventory_open
        
        # Tab switching in inventory (Q/E or bumpers)
        if self.inventory_open:
            if rl.is_key_pressed(rl.KEY_Q) or rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_LEFT_TRIGGER_1):
                self.inventory_tab = (self.inventory_tab - 1) % 3
            if rl.is_key_pressed(rl.KEY_E) or rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_TRIGGER_1):
                self.inventory_tab = (self.inventory_tab + 1) % 3
    
    def _screen_to_world(self, screen_x, screen_y):
        """Convert screen coordinates to world coordinates."""
        canvas_center_x = self.canvas_width / 2
        canvas_center_y = self.canvas_height / 2
        cell_size = CELL_SIZE * self.zoom
        
        world_x = (screen_x - canvas_center_x) / cell_size + self.camera_x
        world_y = (screen_y - canvas_center_y) / cell_size + self.camera_y
        return world_x, world_y
    
    def _update_player_facing_to_mouse(self):
        """Update player facing direction to face the mouse cursor."""
        player = self.state.player
        if not player:
            return
        
        # Convert mouse position to world coords
        world_x, world_y = self._screen_to_world(self.input.mouse_x, self.input.mouse_y)
        
        # Calculate direction from player to mouse
        dx = world_x - player.x
        dy = world_y - player.y
        
        # Determine 8-direction facing
        angle = math.atan2(dy, dx)
        
        # Convert to 8 directions
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
    
    def _update_backpedal_state(self, move_dx, move_dy):
        """Check if player is backpedaling (moving opposite to facing)."""
        player = self.state.player
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
    
    def _handle_movement_no_facing(self, dx, dy, sprinting=False, movement_dot=0):
        """Handle movement input without changing facing direction."""
        player = self.state.player
        if not player:
            return False
        
        if player.is_frozen:
            player.vx = 0.0
            player.vy = 0.0
            return False
        
        if movement_dot > 0:
            speed = SPRINT_SPEED if sprinting else MOVEMENT_SPEED
            player.is_sprinting = sprinting
        else:
            speed = MOVEMENT_SPEED * 0.9
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
    
    def _handle_make_camp(self):
        """Handle player camp creation"""
        player = self.state.player
        if not player:
            return
        
        name = player.get_display_name()
        
        if player.get('camp_position'):
            self.state.log_action(f"{name} already has a camp")
            return
        
        cell_x = int(player.x)
        cell_y = int(player.y)
        
        if not self.logic.can_make_camp_at(cell_x, cell_y):
            self.state.log_action(f"{name} can't make a camp here (must be outside village)")
            return
        
        self.logic.make_camp(player)
    
    # =========================================================================
    # GAME LOOP
    # =========================================================================
    
    def _game_loop(self):
        """Main game loop - process ticks and update positions"""
        current_time = time.time()
        dt = current_time - self.last_frame_time
        self.last_frame_time = current_time
        
        # Cap delta time
        dt = min(dt, 0.1)
        
        if self.state.paused:
            return
        
        game_dt = dt * self.state.game_speed
        tick_duration = UPDATE_INTERVAL / 1000.0
        
        self._accumulated_time += game_dt
        
        # Cap accumulated time
        max_ticks_per_frame = 200
        self._accumulated_time = min(self._accumulated_time, tick_duration * max_ticks_per_frame)
        
        # Process simulation in tick-sized chunks
        while self._accumulated_time >= tick_duration:
            self.logic.process_tick()
            
            remaining = tick_duration
            while remaining > 0:
                step = min(remaining, 0.05)
                self.player_controller.update_position(step)
                self.logic.update_npc_positions(step)
                remaining -= step
            
            self._accumulated_time -= tick_duration
        
        # Handle remaining fractional time
        if self._accumulated_time > 0:
            step = min(self._accumulated_time, 0.05)
            self.player_controller.update_position(step)
            self.logic.update_npc_positions(step)
        
        # Center camera on player if following
        if self.camera_following_player and self.state.player:
            self.camera_x = self.state.player.x
            self.camera_y = self.state.player.y
    
    # =========================================================================
    # RENDERING
    # =========================================================================
    
    def _render_frame(self):
        """Render the current game state"""
        rl.begin_drawing()
        rl.clear_background(hex_to_color(BG_COLOR))
        
        self._draw_canvas()
        
        # Draw HUD overlay or inventory screen
        if self.inventory_open:
            self._draw_inventory_screen()
        else:
            self._draw_hud()
        
        rl.end_drawing()
    
    def _draw_canvas(self):
        """Draw the game canvas with camera (zoom and pan)"""
        canvas_width = self.canvas_width
        canvas_height = self.canvas_height
        canvas_center_x = canvas_width / 2
        canvas_center_y = canvas_height / 2
        
        cell_size = CELL_SIZE * self.zoom
        
        # Calculate visible world bounds
        half_view_width = canvas_width / 2 / cell_size
        half_view_height = canvas_height / 2 / cell_size
        
        min_visible_x = int(self.camera_x - half_view_width) - 1
        max_visible_x = int(self.camera_x + half_view_width) + 2
        min_visible_y = int(self.camera_y - half_view_height) - 1
        max_visible_y = int(self.camera_y + half_view_height) + 2
        
        # Clamp to world bounds
        min_visible_x = max(0, min_visible_x)
        max_visible_x = min(SIZE, max_visible_x)
        min_visible_y = max(0, min_visible_y)
        max_visible_y = min(SIZE, max_visible_y)
        
        # Store camera transform info
        self._cam_center_x = canvas_center_x
        self._cam_center_y = canvas_center_y
        self._cam_cell_size = cell_size
        
        # Draw grid cells
        self._draw_grid(min_visible_x, max_visible_x, min_visible_y, max_visible_y)
        
        # Draw world objects (layered)
        self._draw_houses()
        self._draw_barrels()
        self._draw_beds()
        self._draw_stoves()
        self._draw_camps()
        
        # Draw perception debug if enabled
        if SHOW_PERCEPTION_DEBUG:
            self._draw_perception_debug()
        
        # Draw trees and characters together, Y-sorted for proper depth
        self._draw_trees_and_characters()
        
        # Draw death animations
        self._draw_death_animations()
    
    def _world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates"""
        screen_x = self._cam_center_x + (world_x - self.camera_x) * self._cam_cell_size
        screen_y = self._cam_center_y + (world_y - self.camera_y) * self._cam_cell_size
        return screen_x, screen_y
    
    def _draw_grid(self, min_x, max_x, min_y, max_y):
        """Draw grid cells"""
        cell_size = self._cam_cell_size
        
        road_tex = self.world_textures.get('road')
        grass_tex = self.world_textures.get('grass')
        
        tile_size = int(cell_size) + 1
        
        for y in range(min_y, max_y):
            for x in range(min_x, max_x):
                screen_x, screen_y = self._world_to_screen(x, y)
                
                is_road = (x, y) in self._road_set
                
                # Draw grass as base layer
                if grass_tex:
                    source = rl.Rectangle(0, 0, grass_tex.width, grass_tex.height)
                    dest = rl.Rectangle(screen_x, screen_y, tile_size, tile_size)
                    rl.draw_texture_pro(grass_tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
                else:
                    rl.draw_rectangle(int(screen_x), int(screen_y), tile_size, tile_size, hex_to_color(BG_COLOR))
                
                # Draw road or area colors on top
                if is_road and road_tex:
                    source = rl.Rectangle(0, 0, road_tex.width, road_tex.height)
                    dest = rl.Rectangle(screen_x, screen_y, tile_size, tile_size)
                    rl.draw_texture_pro(road_tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
                else:
                    color = self._get_cell_color(x, y)
                    if color != BG_COLOR:
                        rl.draw_rectangle(int(screen_x), int(screen_y), tile_size, tile_size, hex_to_color(color))
    
    def _get_cell_color(self, x, y):
        """Get the background color for a cell"""
        if (x, y) in self._road_set:
            return ROAD_COLOR
        
        farm_cell = self.state.get_farm_cell_state(x, y)
        if farm_cell:
            return FARM_CELL_COLORS.get(farm_cell['state'], BG_COLOR)
        
        area = self.state.get_area_at(x, y)
        if area:
            for area_def in AREAS:
                if area_def["name"] == area:
                    if area_def.get("role") == "village":
                        return BG_COLOR
                    return area_def.get("color", BG_COLOR)
        
        return BG_COLOR
    
    def _draw_houses(self):
        """Draw all houses"""
        cell_size = self._cam_cell_size
        
        house_s_tex = self.world_textures.get('house_s')
        house_m_tex = self.world_textures.get('house_m')
        
        for house in self.state.interactables.houses.values():
            bounds = house.bounds
            y_start, x_start, y_end, x_end = bounds
            
            house_width_cells = x_end - x_start
            house_height_cells = y_end - y_start
            
            screen_x, screen_y = self._world_to_screen(x_start, y_start)
            width = house_width_cells * cell_size
            height = house_height_cells * cell_size
            
            if house_width_cells <= 4 and house_s_tex:
                tex = house_s_tex
            elif house_m_tex:
                tex = house_m_tex
            else:
                tex = house_s_tex
            
            if tex:
                source = rl.Rectangle(0, 0, tex.width, tex.height)
                dest = rl.Rectangle(screen_x, screen_y, width, height)
                rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                rl.draw_rectangle(int(screen_x), int(screen_y), int(width), int(height), hex_to_color("#C4813D"))
    
    def _draw_trees_and_characters(self):
        """Draw trees and characters together, sorted by Y position for proper depth.
        Objects with smaller Y (higher on screen) are drawn first, so objects
        with larger Y (lower on screen) appear in front.
        """
        # Collect all drawable entities with their sort key (Y position)
        drawables = []
        
        # Add trees - use middle of tree cell as sort position
        # This ensures characters in front of the trunk appear in front
        for pos, tree in self.state.interactables.trees.items():
            x, y = pos
            sort_y = y + 0.5  # Middle of tree cell (where trunk is)
            drawables.append(('tree', sort_y, tree, pos))
        
        # Add characters - use their Y position
        for char in self.state.characters:
            sort_y = char['y']
            drawables.append(('character', sort_y, char, None))
        
        # Sort by Y position (smaller Y drawn first = behind)
        drawables.sort(key=lambda d: d[1])
        
        # Reset player frame cache (will be set during character drawing)
        self._player_frame_cache = None
        
        # Draw in sorted order
        for dtype, sort_y, entity, extra in drawables:
            if dtype == 'tree':
                self._draw_single_tree(entity, extra)
            elif dtype == 'character':
                self._draw_single_character(entity)
        
        # Draw player outline AFTER everything if occluded (so it's on top)
        if self._is_player_occluded():
            self._draw_player_outline_shader()
    
    def _is_player_occluded(self):
        """Check if player is behind any tree."""
        player = self.state.player
        if not player:
            return False
        
        player_y = player['y']
        player_x = player['x']
        
        for pos, tree in self.state.interactables.trees.items():
            tree_x, tree_y = pos
            tree_center_x = tree_x + 0.5
            tree_sort_y = tree_y + 0.5
            
            # Player is behind tree if player's Y < tree's sort Y
            # AND player is within the tree's visual height (not way above it)
            # Tree sprite is ~2.5 cells tall, so check if player is within that range
            if player_y < tree_sort_y and player_y > tree_y - 2.0:
                # Check if horizontally overlapping
                tree_half_width = 0.8
                if abs(player_x - tree_center_x) < tree_half_width:
                    return True
        return False
    
    def _init_outline_shader(self):
        """Initialize the outline shader if not already done."""
        if hasattr(self, '_outline_shader'):
            return self._outline_shader
        
        # Fragment shader that draws white outline around opaque pixels
        fragment_shader = """
#version 330
in vec2 fragTexCoord;
in vec4 fragColor;
uniform sampler2D texture0;
uniform vec2 textureSize;
uniform float outlineWidth;
out vec4 finalColor;

void main() {
    vec4 texel = texture(texture0, fragTexCoord);
    
    // If this pixel is transparent, check if neighbors are opaque
    if (texel.a < 0.1) {
        vec2 pixelSize = vec2(1.0 / textureSize.x, 1.0 / textureSize.y) * outlineWidth;
        
        // Sample in 8 directions
        float neighborAlpha = 0.0;
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(pixelSize.x, 0)).a);
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(-pixelSize.x, 0)).a);
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(0, pixelSize.y)).a);
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(0, -pixelSize.y)).a);
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(pixelSize.x, pixelSize.y)).a);
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(-pixelSize.x, pixelSize.y)).a);
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(pixelSize.x, -pixelSize.y)).a);
        neighborAlpha = max(neighborAlpha, texture(texture0, fragTexCoord + vec2(-pixelSize.x, -pixelSize.y)).a);
        
        // If any neighbor is opaque, draw white outline
        if (neighborAlpha > 0.5) {
            finalColor = vec4(1.0, 1.0, 1.0, 0.8);
        } else {
            finalColor = vec4(0.0, 0.0, 0.0, 0.0);
        }
    } else {
        // Opaque pixel - draw as semi-transparent white silhouette
        finalColor = vec4(1.0, 1.0, 1.0, texel.a * 0.3);
    }
}
"""
        
        # Default vertex shader
        vertex_shader = """
#version 330
in vec3 vertexPosition;
in vec2 vertexTexCoord;
in vec4 vertexColor;
uniform mat4 mvp;
out vec2 fragTexCoord;
out vec4 fragColor;

void main() {
    fragTexCoord = vertexTexCoord;
    fragColor = vertexColor;
    gl_Position = mvp * vec4(vertexPosition, 1.0);
}
"""
        
        self._outline_shader = rl.load_shader_from_memory(vertex_shader, fragment_shader)
        self._outline_texture_size_loc = rl.get_shader_location(self._outline_shader, "textureSize")
        self._outline_width_loc = rl.get_shader_location(self._outline_shader, "outlineWidth")
        
        return self._outline_shader
    
    def _draw_player_outline_shader(self):
        """Draw a white outline of the player sprite using a shader."""
        # Use cached frame info from character drawing to ensure same animation frame
        if not hasattr(self, '_player_frame_cache') or self._player_frame_cache is None:
            return
        
        cache = self._player_frame_cache
        frame_info = cache.get('frame_info')
        
        if not frame_info:
            return
        
        # Get recolored texture from the cached frame_info
        char_color = cache.get('char_color')
        recolored_texture = self.sprite_manager.recolor_red_to_color(frame_info, char_color)
        
        if not recolored_texture:
            return
        
        should_flip = cache['should_flip']
        pixel_cx = cache['pixel_cx']
        pixel_cy = cache['pixel_cy']
        sprite_width = cache['sprite_width']
        sprite_height = cache['sprite_height']
        
        blit_x = pixel_cx - sprite_width / 2
        blit_y = pixel_cy - sprite_height / 2
        
        # Prepare source rectangle (handle flipping)
        if should_flip:
            source = rl.Rectangle(recolored_texture.width, 0, 
                                 -recolored_texture.width, recolored_texture.height)
        else:
            source = rl.Rectangle(0, 0, recolored_texture.width, recolored_texture.height)
        
        dest = rl.Rectangle(blit_x, blit_y, sprite_width, sprite_height)
        
        # Initialize and use outline shader
        shader = self._init_outline_shader()
        
        # Set shader uniforms
        texture_size = rl.ffi.new("float[2]", [recolored_texture.width, recolored_texture.height])
        outline_width = rl.ffi.new("float *", 1.0)
        
        rl.set_shader_value(shader, self._outline_texture_size_loc, texture_size, rl.SHADER_UNIFORM_VEC2)
        rl.set_shader_value(shader, self._outline_width_loc, outline_width, rl.SHADER_UNIFORM_FLOAT)
        
        # Draw with shader
        rl.begin_shader_mode(shader)
        rl.draw_texture_pro(recolored_texture, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
        rl.end_shader_mode()
    
    def _draw_single_tree(self, tree, pos):
        """Draw a single tree"""
        cell_size = self._cam_cell_size
        tree_tex = self.world_textures.get('tree')
        
        if not tree_tex:
            return
        
        tree_height = int(cell_size * 2.5)
        tree_width = int(tree_height * 66 / 77)
        
        x, y = pos
        screen_x, screen_y = self._world_to_screen(x, y)
        
        blit_x = screen_x + cell_size / 2 - tree_width / 2
        blit_y = screen_y + cell_size - tree_height
        
        source = rl.Rectangle(0, 0, tree_tex.width, tree_tex.height)
        dest = rl.Rectangle(blit_x, blit_y, tree_width, tree_height)
        rl.draw_texture_pro(tree_tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
    
    def _draw_trees(self):
        """Draw all trees (legacy - now handled by _draw_trees_and_characters)"""
        cell_size = self._cam_cell_size
        tree_tex = self.world_textures.get('tree')
        
        if not tree_tex:
            return
        
        tree_height = int(cell_size * 2.5)
        tree_width = int(tree_height * 66 / 77)
        
        for pos, tree in self.state.interactables.trees.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            blit_x = screen_x + cell_size / 2 - tree_width / 2
            blit_y = screen_y + cell_size - tree_height
            
            source = rl.Rectangle(0, 0, tree_tex.width, tree_tex.height)
            dest = rl.Rectangle(blit_x, blit_y, tree_width, tree_height)
            rl.draw_texture_pro(tree_tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
    
    def _draw_barrels(self):
        """Draw all barrels"""
        cell_size = self._cam_cell_size
        barrel_tex = self.world_textures.get('barrel')
        
        for pos, barrel in self.state.interactables.barrels.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            if barrel_tex:
                barrel_size = int(cell_size * 0.8)
                blit_x = screen_x + (cell_size - barrel_size) / 2
                blit_y = screen_y + (cell_size - barrel_size) / 2
                
                source = rl.Rectangle(0, 0, barrel_tex.width, barrel_tex.height)
                dest = rl.Rectangle(blit_x, blit_y, barrel_size, barrel_size)
                rl.draw_texture_pro(barrel_tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                padding = int(5 * self.zoom)
                rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                                 int(cell_size - 2*padding), int(cell_size - 2*padding),
                                 hex_to_color("#8B4513"))
    
    def _draw_beds(self):
        """Draw all beds"""
        cell_size = self._cam_cell_size
        
        for pos, bed in self.state.interactables.beds.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            padding = int(4 * self.zoom)
            bed_size = int(cell_size - 2*padding)
            
            # Bed base (blue)
            rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                             bed_size, bed_size, hex_to_color("#4169E1"))
            rl.draw_rectangle_lines(int(screen_x + padding), int(screen_y + padding),
                                   bed_size, bed_size, hex_to_color("#2a4494"))
            
            # Pillow
            pillow_height = int(8 * self.zoom)
            pillow_margin = int(3 * self.zoom)
            rl.draw_rectangle(int(screen_x + padding + pillow_margin),
                             int(screen_y + padding + 2*self.zoom),
                             bed_size - 2*pillow_margin, pillow_height,
                             rl.WHITE)
    
    def _draw_stoves(self):
        """Draw all stoves"""
        cell_size = self._cam_cell_size
        
        for pos, stove in self.state.interactables.stoves.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            padding = int(4 * self.zoom)
            stove_size = int(cell_size - 2*padding)
            
            # Stove base (dark gray)
            rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                             stove_size, stove_size, hex_to_color("#444444"))
            rl.draw_rectangle_lines(int(screen_x + padding), int(screen_y + padding),
                                   stove_size, stove_size, hex_to_color("#222222"))
            
            # Draw "S" text
            text_x = int(screen_x + cell_size / 2 - 4)
            text_y = int(screen_y + cell_size / 2 - 8)
            rl.draw_text("S", text_x, text_y, 16, rl.Color(255, 150, 50, 255))
    
    def _draw_camps(self):
        """Draw all campfires"""
        cell_size = self._cam_cell_size
        current_time = time.time()
        
        # Animation frame
        if self.campfire_frames:
            frame_duration = 0.15
            frame_idx = int(current_time / frame_duration) % len(self.campfire_frames)
            campfire_source = self.campfire_frames[frame_idx]
        else:
            campfire_source = None
        
        campfire_tex = self.world_textures.get('campfire')
        
        for char in self.state.characters:
            camp_pos = char.get('camp_position')
            if camp_pos:
                x, y = camp_pos
                screen_x, screen_y = self._world_to_screen(x, y)
                
                if campfire_tex and campfire_source:
                    campfire_size = int(cell_size * 1.2)
                    blit_x = screen_x + cell_size / 2 - campfire_size / 2
                    blit_y = screen_y + cell_size - campfire_size
                    
                    dest = rl.Rectangle(blit_x, blit_y, campfire_size, campfire_size)
                    rl.draw_texture_pro(campfire_tex, campfire_source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
                else:
                    # Fallback to circles
                    fire_cx = int(screen_x + cell_size / 2)
                    fire_cy = int(screen_y + cell_size / 2)
                    r1 = int(8 * self.zoom)
                    r2 = int(5 * self.zoom)
                    r3 = int(2 * self.zoom)
                    rl.draw_circle(fire_cx, fire_cy, r1, rl.Color(255, 100, 0, 255))
                    rl.draw_circle(fire_cx, fire_cy, r2, rl.Color(255, 200, 0, 255))
                    rl.draw_circle(fire_cx, fire_cy, r3, rl.Color(255, 255, 100, 255))
    
    def _get_character_color(self, char):
        """Get the display color for a character"""
        if char.get('is_frozen', False):
            return "#FF0000"
        
        if char.get('is_starving', False):
            return "#FF8C00"
        
        job = char.get('job')
        if job in JOB_TIERS and "color" in JOB_TIERS[job]:
            return JOB_TIERS[job]["color"]
        
        morality = char.get('morality', 5)
        t = (morality - 1) / 9.0
        r = int(0 + t * 173)
        g = int(0 + t * 216)
        b = int(139 + t * (230 - 139))
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _draw_single_character(self, char):
        """Draw a single character"""
        cell_size = self._cam_cell_size
        current_time = time.time()
        
        vis_x = char['x']
        vis_y = char['y']
        
        pixel_cx, pixel_cy = self._world_to_screen(vis_x, vis_y)
        
        sprite_height = int(CHARACTER_HEIGHT * cell_size)
        sprite_width = int(CHARACTER_WIDTH * cell_size)
        
        # Get sprite frame info
        frame_info, should_flip = self.sprite_manager.get_frame(char, current_time)
        
        # Cache player frame info for outline drawing
        if char is self.state.player and frame_info:
            self._player_frame_cache = {
                'frame_info': frame_info,
                'should_flip': should_flip,
                'pixel_cx': pixel_cx,
                'pixel_cy': pixel_cy,
                'sprite_width': sprite_width,
                'sprite_height': sprite_height,
                'char_color': self._get_character_color(char)
            }
        
        if frame_info:
            char_color = self._get_character_color(char)
            recolored_texture = self.sprite_manager.recolor_red_to_color(frame_info, char_color)
            
            if recolored_texture:
                # Draw the sprite
                blit_x = pixel_cx - sprite_width / 2
                blit_y = pixel_cy - sprite_height / 2
                
                # Source rectangle - recolored texture is already the extracted frame
                # Use negative width to flip horizontally
                if should_flip:
                    source = rl.Rectangle(recolored_texture.width, 0, -recolored_texture.width, recolored_texture.height)
                else:
                    source = rl.Rectangle(0, 0, recolored_texture.width, recolored_texture.height)
                
                dest = rl.Rectangle(blit_x, blit_y, sprite_width, sprite_height)
                rl.draw_texture_pro(recolored_texture, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                # Fallback if recoloring failed - draw original frame
                texture = frame_info['texture']
                source_rect = frame_info['source']
                blit_x = pixel_cx - sprite_width / 2
                blit_y = pixel_cy - sprite_height / 2
                
                if should_flip:
                    source = rl.Rectangle(source_rect.x + source_rect.width, source_rect.y, -source_rect.width, source_rect.height)
                else:
                    source = source_rect
                
                dest = rl.Rectangle(blit_x, blit_y, sprite_width, sprite_height)
                rl.draw_texture_pro(texture, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
        else:
            # Fallback to colored rectangle
            char_color = self._get_character_color(char)
            blit_x = pixel_cx - sprite_width / 2
            blit_y = pixel_cy - sprite_height / 2
            rl.draw_rectangle(int(blit_x), int(blit_y), sprite_width, sprite_height, hex_to_color(char_color))
        
        # Draw first name below sprite
        first_name = char['name'].split()[0]
        text_width = rl.measure_text(first_name, 10)
        text_x = int(pixel_cx - text_width / 2)
        text_y = int(pixel_cy + sprite_height / 3.2)
        rl.draw_text(first_name, text_x, text_y, 10, rl.WHITE)
        
        # Draw HP and Stamina bars when health < 100
        health = char.get('health', 100)
        if health < 100:
            bar_width = sprite_width
            bar_height = max(3, int(4 * self.zoom))
            bar_x = int(pixel_cx - bar_width / 2)
            bar_gap = max(1, int(2 * self.zoom))
            
            # HP bar
            hp_bar_y = text_y + 12
            
            # Background
            rl.draw_rectangle(bar_x, hp_bar_y, bar_width, bar_height, rl.Color(255, 255, 255, 25))
            
            # Foreground (health color - red)
            hp_ratio = max(0, health) / 100.0
            hp_fill_width = int(bar_width * hp_ratio)
            if hp_fill_width > 0:
                rl.draw_rectangle(bar_x, hp_bar_y, hp_fill_width, bar_height, 
                                 rl.Color(COLOR_HEALTH.r, COLOR_HEALTH.g, COLOR_HEALTH.b, 220))
            
            # Stamina bar (below HP bar)
            stamina = char.get('stamina', 100)
            stamina_bar_y = hp_bar_y + bar_height + bar_gap
            
            # Background
            rl.draw_rectangle(bar_x, stamina_bar_y, bar_width, bar_height, rl.Color(255, 255, 255, 25))
            
            # Foreground (stamina color - green)
            stamina_ratio = max(0, stamina) / 100.0
            stamina_fill_width = int(bar_width * stamina_ratio)
            if stamina_fill_width > 0:
                rl.draw_rectangle(bar_x, stamina_bar_y, stamina_fill_width, bar_height, 
                                 rl.Color(COLOR_STAMINA.r, COLOR_STAMINA.g, COLOR_STAMINA.b, 220))
    
    def _draw_characters(self):
        """Draw all characters (legacy - now handled by _draw_trees_and_characters)"""
        for char in self.state.characters:
            self._draw_single_character(char)
    
    def _draw_death_animations(self):
        """Draw death animations"""
        DEATH_ANIMATION_DURATION = 0.9
        current_time = time.time()
        cell_size = self._cam_cell_size
        
        # Remove expired animations
        self.state.death_animations = [
            anim for anim in self.state.death_animations
            if current_time - anim['start_time'] < DEATH_ANIMATION_DURATION
        ]
        
        for anim in self.state.death_animations:
            pixel_cx, pixel_cy = self._world_to_screen(anim['x'], anim['y'])
            
            sprite_height = int(CHARACTER_HEIGHT * cell_size)
            sprite_width = int(CHARACTER_WIDTH * cell_size)
            
            fake_char = {
                'name': anim['name'],
                'facing': anim['facing'],
                'health': 0,
                'death_animation_start': anim['start_time'],
                'vx': 0, 'vy': 0
            }
            
            frame_info, should_flip = self.sprite_manager.get_frame(fake_char, current_time)
            
            if frame_info:
                job = anim.get('job')
                if job in JOB_TIERS and "color" in JOB_TIERS[job]:
                    color = JOB_TIERS[job]["color"]
                else:
                    morality = anim.get('morality', 5)
                    t = (morality - 1) / 9.0
                    r = int(0 + t * 173)
                    g = int(0 + t * 216)
                    b = int(139 + t * (230 - 139))
                    color = f"#{r:02x}{g:02x}{b:02x}"
                
                recolored_texture = self.sprite_manager.recolor_red_to_color(frame_info, color)
                
                if recolored_texture:
                    blit_x = pixel_cx - sprite_width / 2
                    blit_y = pixel_cy - sprite_height / 2
                    
                    if should_flip:
                        source = rl.Rectangle(recolored_texture.width, 0, -recolored_texture.width, recolored_texture.height)
                    else:
                        source = rl.Rectangle(0, 0, recolored_texture.width, recolored_texture.height)
                    
                    dest = rl.Rectangle(blit_x, blit_y, sprite_width, sprite_height)
                    rl.draw_texture_pro(recolored_texture, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
    
    def _draw_perception_debug(self):
        """Draw perception debug visualization"""
        cell_size = self._cam_cell_size
        
        for char in self.state.characters:
            if char.get('health', 100) <= 0:
                continue
            
            screen_x, screen_y = self._world_to_screen(char.x, char.y)
            
            # Sound radius (circle)
            sound_radius_pixels = int(SOUND_RADIUS * cell_size)
            rl.draw_circle(int(screen_x), int(screen_y), sound_radius_pixels, rl.Color(255, 0, 0, 40))
            rl.draw_circle_lines(int(screen_x), int(screen_y), sound_radius_pixels, rl.Color(255, 0, 0, 80))
            
            # Vision cone
            vision_radius_pixels = int(VISION_RANGE * cell_size)
            facing = char.get('facing', 'down')
            
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
            face_x, face_y = facing_vectors.get(facing, (0, 1))
            
            facing_angle = math.atan2(-face_y, face_x)
            half_angle = math.radians(VISION_CONE_ANGLE / 2)
            
            angle1 = facing_angle - half_angle
            angle2 = facing_angle + half_angle
            
            # Draw vision cone as a series of triangles
            num_segments = 20
            for i in range(num_segments):
                t1 = i / num_segments
                t2 = (i + 1) / num_segments
                a1 = angle1 + t1 * (angle2 - angle1)
                a2 = angle1 + t2 * (angle2 - angle1)
                
                p1_x = screen_x + math.cos(a1) * vision_radius_pixels
                p1_y = screen_y - math.sin(a1) * vision_radius_pixels
                p2_x = screen_x + math.cos(a2) * vision_radius_pixels
                p2_y = screen_y - math.sin(a2) * vision_radius_pixels
                
                rl.draw_triangle(
                    rl.Vector2(screen_x, screen_y),
                    rl.Vector2(p1_x, p1_y),
                    rl.Vector2(p2_x, p2_y),
                    rl.Color(255, 100, 100, 30)
                )

    # =========================================================================
    # HUD RENDERING
    # =========================================================================
    
    def _draw_hud(self):
        """Draw all HUD elements overlay"""
        player = self.state.player
        if not player:
            return
        
        # Bottom-left: Stat bars
        self._draw_stat_bars(player)
        
        # Bottom-left: Item slots (below stat bars)
        self._draw_item_slots(player)
        
        # Top-right: Location and time
        self._draw_location_time()
        
        # Bottom-right: Context actions (what can player interact with)
        self._draw_context_actions(player)
        
        # Top-left: Minimal debug info (optional)
        self._draw_debug_info()
    
    def _draw_stat_bars(self, player):
        """Draw health, stamina, fatigue, hunger bars in top-left"""
        x = HUD_MARGIN
        y = HUD_MARGIN
        
        # Health (HP)
        self._draw_single_stat_bar(
            x, y,
            player.health, 100,
            COLOR_HEALTH, "HP"
        )
        
        # Stamina (S)
        self._draw_single_stat_bar(
            x, y + 20,
            player.stamina, 100,
            COLOR_STAMINA, "S"
        )
        
        # Energy (E) - inverted fatigue
        self._draw_single_stat_bar(
            x, y + 40,
            100 - player.fatigue, 100,
            COLOR_FATIGUE, "E"
        )
        
        # Hunger (H)
        self._draw_single_stat_bar(
            x, y + 60,
            player.hunger, 100,
            COLOR_HUNGER, "H"
        )
    
    def _draw_item_slots(self, player):
        """Draw 8 hotkey slots at bottom-left (d-pad directions or number keys 1-8)"""
        x = HUD_MARGIN
        y = self.canvas_height - HUD_MARGIN
        slot_size = 40
        slot_gap = 3
        
        # D-pad layout hints for controller, number keys for keyboard
        # Slots map to: 1=Up, 2=Up-Right, 3=Right, 4=Down-Right, 5=Down, 6=Down-Left, 7=Left, 8=Up-Left
        is_controller = self.input.gamepad_connected
        
        dpad_hints = ['↑', '↗', '→', '↘', '↓', '↙', '←', '↖']
        key_hints = ['1', '2', '3', '4', '5', '6', '7', '8']
        
        # For now, all slots are empty (no items in game yet)
        # In future, this would read from player.hotbar[0..7]
        
        for i in range(8):
            slot_x = x + i * (slot_size + slot_gap)
            slot_y = y - slot_size
            
            # Slot background
            rl.draw_rectangle(slot_x, slot_y, slot_size, slot_size, COLOR_BG_SLOT)
            rl.draw_rectangle_lines(slot_x, slot_y, slot_size, slot_size, COLOR_BORDER)
            
            # Key/d-pad hint (bottom right, small)
            hint = dpad_hints[i] if is_controller else key_hints[i]
            hint_width = rl.measure_text(hint, HUD_FONT_SIZE_SMALL)
            rl.draw_text(hint, slot_x + slot_size - hint_width - 3, 
                        slot_y + slot_size - 13, HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)
    
    def _draw_single_stat_bar(self, x, y, value, max_val, color, icon):
        """Draw a single stat bar with icon and value"""
        pct = max(0, min(1, value / max_val))
        is_low = pct < 0.25
        is_critical = pct < 0.10
        
        icon_x = x
        bar_x = x + 25
        bar_width = HUD_BAR_WIDTH
        bar_height = HUD_BAR_HEIGHT
        value_x = bar_x + bar_width + 10
        
        # Icon
        icon_color = color if is_low else COLOR_TEXT_DIM
        rl.draw_text(icon, icon_x, y - 2, HUD_FONT_SIZE_MEDIUM, icon_color)
        
        # Bar background
        rl.draw_rectangle(bar_x, y, bar_width, bar_height, rl.Color(255, 255, 255, 25))
        
        # Bar fill
        fill_width = int(bar_width * pct)
        if fill_width > 0:
            # Gradient effect - brighter at left
            fill_color = rl.Color(color.r, color.g, color.b, 220)
            rl.draw_rectangle(bar_x, y, fill_width, bar_height, fill_color)
        
        # Glow effect when low
        if is_low and fill_width > 0:
            glow_color = rl.Color(color.r, color.g, color.b, 60)
            rl.draw_rectangle(bar_x - 2, y - 2, fill_width + 4, bar_height + 4, glow_color)
        
        # Pulsing effect when critical
        if is_critical:
            pulse = (math.sin(time.time() * 6) + 1) / 2  # 0 to 1, 3Hz
            pulse_alpha = int(40 + pulse * 60)
            rl.draw_rectangle(bar_x - 4, y - 4, bar_width + 8, bar_height + 8, 
                             rl.Color(color.r, color.g, color.b, pulse_alpha))
        
        # Value text
        value_str = str(int(value))
        text_color = color if is_low else COLOR_TEXT_DIM
        rl.draw_text(value_str, value_x, y - 2, HUD_FONT_SIZE_SMALL, text_color)
    
    def _draw_location_time(self):
        """Draw compact time info in top-right (debug window style)"""
        # Calculate time values
        ticks = self.state.ticks
        year = (ticks // TICKS_PER_YEAR) + 1
        day = ((ticks % TICKS_PER_YEAR) // TICKS_PER_DAY) + 1
        day_progress = (ticks % TICKS_PER_DAY) / TICKS_PER_DAY * 100
        
        # Format: "Year 1, Day 2 | 45%"
        time_str = f"Year {year}, Day {day} | {day_progress:.0f}%"
        
        # Draw in top-right, small
        x = self.canvas_width - HUD_MARGIN
        y = HUD_MARGIN
        
        time_width = rl.measure_text(time_str, HUD_FONT_SIZE_SMALL)
        rl.draw_text(time_str, x - time_width, y, HUD_FONT_SIZE_SMALL, COLOR_TEXT_DIM)
    
    def _draw_context_actions(self, player):
        """Draw available actions based on what player is near"""
        context = self._get_player_context(player)
        
        x = self.canvas_width - HUD_MARGIN
        y = self.canvas_height - HUD_MARGIN - 140
        
        # Always show self-actions first (eat, etc.)
        self_actions = self._get_self_actions(player)
        if self_actions:
            for action in self_actions:
                self._draw_action_prompt(x, y, action['key'], action['label'])
                y += 28
            y += 10  # Extra gap before context actions
        
        if not context:
            return
        
        # Draw target type (small, dim)
        type_str = context['type'].upper()
        type_width = rl.measure_text(type_str, HUD_FONT_SIZE_SMALL)
        rl.draw_text(type_str, x - type_width, y, HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)
        
        # Draw target name (larger, brighter)
        name = context['name']
        name_width = rl.measure_text(name, HUD_FONT_SIZE_LARGE)
        rl.draw_text(name, x - name_width, y + 14, HUD_FONT_SIZE_LARGE, COLOR_TEXT_BRIGHT)
        
        # Draw available actions
        action_y = y + 40
        for action in context['actions']:
            self._draw_action_prompt(x, action_y, action['key'], action['label'])
            action_y += 28
    
    def _get_self_actions(self, player):
        """Get actions the player can perform on themselves"""
        actions = []
        
        # Eat bread if hungry and has bread
        bread_count = player.get_item('bread')
        if bread_count > 0 and player.hunger < 80:
            actions.append({'key': 'E', 'label': 'Eat Bread'})
        
        # Make camp if outside village and doesn't have one
        if not player.get('camp_position'):
            area = self.state.get_area_at(player.x, player.y)
            if area is None:  # Outside any defined area
                actions.append({'key': 'C', 'label': 'Make Camp'})
        
        return actions
    
    def _draw_action_prompt(self, right_x, y, key, label):
        """Draw a single action prompt like [E] Trade"""
        is_controller = self.input.gamepad_connected
        
        # Map keyboard keys to controller buttons
        controller_map = {
            'E': 'A',
            'T': 'X', 
            'B': 'LB',
            'C': 'B',
            'F': 'Y',
        }
        
        display_key = controller_map.get(key, key) if is_controller else key
        
        # Calculate widths for right-alignment
        label_width = rl.measure_text(label, HUD_FONT_SIZE_MEDIUM)
        key_width = rl.measure_text(display_key, HUD_FONT_SIZE_SMALL)
        box_width = max(22, key_width + 10)
        total_width = box_width + 10 + label_width
        
        start_x = right_x - total_width
        
        # Draw key box
        rl.draw_rectangle(start_x, y - 2, box_width, 20, COLOR_BG_SLOT)
        rl.draw_rectangle_lines(start_x, y - 2, box_width, 20, COLOR_BORDER)
        
        # Draw key text (centered in box)
        key_x = start_x + (box_width - key_width) // 2
        rl.draw_text(display_key, key_x, y + 2, HUD_FONT_SIZE_SMALL, COLOR_TEXT_BRIGHT)
        
        # Draw label
        label_x = start_x + box_width + 10
        rl.draw_text(label, label_x, y, HUD_FONT_SIZE_MEDIUM, COLOR_TEXT_DIM)
    
    def _get_player_context(self, player):
        """Determine what the player can interact with"""
        # Check for adjacent characters (NPCs)
        for char in self.state.characters:
            if char == player:
                continue
            if char.get('health', 100) <= 0:
                continue
            
            dist = math.sqrt((player.x - char.x)**2 + (player.y - char.y)**2)
            if dist <= ADJACENCY_DISTANCE:
                actions = []
                
                # Check if this is a vendor
                job = char.get('job')
                if job in ('Farmer', 'Trader'):
                    actions.append({'key': 'T', 'label': 'Trade'})
                
                # Attack is always available
                actions.append({'key': 'LMB', 'label': 'Attack'})
                
                return {
                    'type': job if job else 'Character',
                    'name': char.get_display_name(),
                    'actions': actions
                }
        
        # Check for adjacent stove
        stove = self.state.interactables.get_adjacent_stove(player)
        if stove and stove.can_use(player):
            return {
                'type': 'Stove',
                'name': stove.name,
                'actions': [{'key': 'B', 'label': 'Bake Bread'}]
            }
        
        # Check for adjacent campfire
        campfire = self.state.interactables.get_adjacent_campfire(player)
        if campfire:
            return {
                'type': 'Campfire',
                'name': 'Campfire',
                'actions': [{'key': 'B', 'label': 'Bake Bread'}]
            }
        
        # Check for adjacent barrel
        for pos, barrel in self.state.interactables.barrels.items():
            if barrel.is_adjacent(player):
                actions = []
                if barrel.can_use(player):
                    wheat_count = barrel.get_wheat()
                    if wheat_count > 0:
                        actions.append({'key': 'T', 'label': f'Take Wheat ({wheat_count})'})
                return {
                    'type': 'Barrel',
                    'name': barrel.name,
                    'actions': actions if actions else [{'key': '-', 'label': 'Empty'}]
                }
        
        # Check for adjacent bed
        for pos, bed in self.state.interactables.beds.items():
            if bed.is_adjacent(player):
                is_owned = bed.is_owned_by(player.name)
                if is_owned or not bed.is_owned():
                    # Could sleep here
                    return {
                        'type': 'Bed',
                        'name': bed.name,
                        'actions': []  # Sleep not implemented yet
                    }
        
        return None
    
    def _draw_debug_info(self):
        """Draw minimal debug info below stat bars"""
        x = HUD_MARGIN
        y = HUD_MARGIN + 90  # Below the 4 stat bars
        
        # FPS
        fps = rl.get_fps()
        rl.draw_text(f"FPS: {fps}", x, y, HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)
        
        # Game speed indicator
        if self.state.game_speed != 1:
            speed_str = f"Speed: {self.state.game_speed}x"
            rl.draw_text(speed_str, x, y + 14, HUD_FONT_SIZE_SMALL, COLOR_TEXT_DIM)
        
        # Paused indicator
        if self.state.paused:
            rl.draw_text("PAUSED", x, y + 28, HUD_FONT_SIZE_MEDIUM, COLOR_TEXT_BRIGHT)
        
        # Controller indicator
        if self.input.gamepad_connected:
            rl.draw_text("Gamepad", 10, self.canvas_height - 20, 
                        HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)

    # =========================================================================
    # INVENTORY SCREEN
    # =========================================================================
    
    def _draw_inventory_screen(self):
        """Draw the full inventory screen overlay"""
        player = self.state.player
        if not player:
            return
        
        # Layout: Left panel (1/3) = inventory, Right panel (2/3) = tabs
        left_width = self.canvas_width // 3
        right_width = self.canvas_width - left_width
        
        # Only draw overlay on non-world tabs
        if self.inventory_tab != 0:
            # Semi-transparent overlay on right side only
            rl.draw_rectangle(left_width, 0, right_width, self.canvas_height, 
                             rl.Color(13, 21, 32, 220))
        
        # Left panel background (always drawn)
        rl.draw_rectangle(0, 0, left_width, self.canvas_height, rl.Color(13, 21, 32, 230))
        rl.draw_line(left_width, 0, left_width, self.canvas_height, COLOR_BORDER)
        
        # Draw left panel content
        self._draw_inventory_left_panel(player, 0, 0, left_width)
        
        # Draw right panel with tabs (handles click detection)
        self._draw_inventory_right_panel(player, left_width, 0, right_width)
        
        # Close hint
        is_controller = self.input.gamepad_connected
        close_hint = "Select to close" if is_controller else "I / Tab to close"
        hint_width = rl.measure_text(close_hint, HUD_FONT_SIZE_SMALL)
        rl.draw_text(close_hint, self.canvas_width - hint_width - 20, 
                    self.canvas_height - 25, HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)
    
    def _draw_inventory_left_panel(self, player, x, y, width):
        """Draw the left inventory panel with equipment and storage"""
        padding = 12
        inner_x = x + padding
        inner_y = y + padding
        inner_width = width - padding * 2
        
        # === STATUS BAR (Health, Hunger, Weight, Gold) ===
        self._draw_inventory_status_bar(player, inner_x, inner_y, inner_width)
        inner_y += 60
        
        # === EQUIPMENT AREA (Head/Body + Accessories) ===
        self._draw_equipment_area(player, inner_x, inner_y, inner_width)
        inner_y += 120  # label + 2 rows of slots + gaps
        
        # === BASE INVENTORY (5 slots) ===
        self._draw_storage_section(player, inner_x, inner_y, inner_width, "Base Inventory", 5)
    
    def _draw_inventory_status_bar(self, player, x, y, width):
        """Draw compact status bar with health, hunger, stamina, fatigue, encumbrance, gold"""
        bar_height = 50
        rl.draw_rectangle(x, y, width, bar_height, rl.Color(255, 255, 255, 8))
        rl.draw_rectangle_lines(x, y, width, bar_height, COLOR_BORDER)
        
        # Stats with consistent HUD-style formatting
        # HP = Health Points, S = Stamina, E = Energy (fatigue inverted), H = Hunger
        stats = [
            ("HP", player.health, 100, COLOR_HEALTH),
            ("S", player.stamina, 100, COLOR_STAMINA),
            ("E", 100 - player.fatigue, 100, COLOR_FATIGUE),
            ("H", player.hunger, 100, COLOR_HUNGER),
        ]
        
        stat_x = x + 8
        stat_y = y + 10
        bar_w = 30
        bar_h = HUD_BAR_HEIGHT
        
        for icon, value, max_val, color in stats:
            pct = max(0, min(1, value / max_val))
            is_low = pct < 0.25
            
            # Icon (letters, consistent with HUD)
            icon_color = color if is_low else COLOR_TEXT_DIM
            icon_width = rl.measure_text(icon, 10)
            rl.draw_text(icon, stat_x, stat_y, 10, icon_color)
            
            # Bar background (consistent with HUD)
            bar_x = stat_x + icon_width + 4
            rl.draw_rectangle(bar_x, stat_y + 3, bar_w, bar_h, rl.Color(255, 255, 255, 25))
            
            # Bar fill (consistent with HUD)
            fill_width = int(bar_w * pct)
            if fill_width > 0:
                rl.draw_rectangle(bar_x, stat_y + 3, fill_width, bar_h, 
                                 rl.Color(color.r, color.g, color.b, 220))
            
            # Value text (consistent with HUD)
            value_str = str(int(value))
            text_color = color if is_low else COLOR_TEXT_DIM
            rl.draw_text(value_str, bar_x + bar_w + 4, stat_y, 9, text_color)
            
            # Move to next stat
            stat_x = bar_x + bar_w + 28
        
        # Encumbrance on second row
        enc_x = x + 8
        enc_y = y + 32
        rl.draw_text("Wt", enc_x, enc_y, 9, COLOR_TEXT_DIM)
        rl.draw_text("0/100", enc_x + 18, enc_y, 9, COLOR_TEXT_FAINT)
        
        # Gold
        gold = player.get_item('money')
        gold_str = f"${gold:,}"
        gold_width = rl.measure_text(gold_str, 12)
        rl.draw_text(gold_str, x + width - gold_width - 10, y + 18, 12, 
                    rl.Color(255, 215, 0, 255))
    
    def _draw_equipment_area(self, player, x, y, width):
        """Draw equipment slots: head and body on left, 8 accessory slots (2x4) on right"""
        slot_size = 36  # Same size as base inventory slots
        slot_gap = 4
        label_height = 14  # Space for labels above slots
        
        # Starting y for slots (after label space)
        slots_y = y
        
        # Left side: Head slot on top, Body slot below (stacked vertically)
        equip_x = x + 8
        
        # Head slot with label
        rl.draw_text("Head", equip_x, slots_y, 9, COLOR_TEXT_FAINT)
        self._draw_equipment_slot_no_label(equip_x, slots_y + label_height, slot_size, None)
        
        # Body slot with label (below head)
        body_y = slots_y + label_height + slot_size + slot_gap + 4
        rl.draw_text("Body", equip_x, body_y, 9, COLOR_TEXT_FAINT)
        self._draw_equipment_slot_no_label(equip_x, body_y + label_height, slot_size, None)
        
        # Right side: 8 accessory slots in 2 rows of 4
        acc_x = equip_x + slot_size + 24  # Gap between equipment and accessories
        
        # Accessories label
        rl.draw_text("Accessories", acc_x, slots_y, 9, COLOR_TEXT_FAINT)
        
        # Accessory slots (2 rows of 4)
        acc_slots_y = slots_y + label_height
        for row in range(2):
            for col in range(4):
                slot_x = acc_x + col * (slot_size + slot_gap)
                slot_y = acc_slots_y + row * (slot_size + slot_gap)
                rl.draw_rectangle(slot_x, slot_y, slot_size, slot_size, COLOR_BG_SLOT)
                rl.draw_rectangle_lines(slot_x, slot_y, slot_size, slot_size, COLOR_BORDER)
    
    def _draw_equipment_slot_no_label(self, x, y, size, item):
        """Draw a single equipment slot without label"""
        has_item = item is not None
        bg_color = COLOR_BG_SLOT_ACTIVE if has_item else COLOR_BG_SLOT
        rl.draw_rectangle(x, y, size, size, bg_color)
        rl.draw_rectangle_lines(x, y, size, size, COLOR_BORDER)
    
    def _draw_storage_section(self, player, x, y, width, label, num_slots):
        """Draw a storage section with label and slots"""
        slot_size = 36
        slot_gap = 4
        
        # Section background
        section_height = slot_size + 24
        rl.draw_rectangle(x, y, width, section_height, rl.Color(255, 255, 255, 5))
        rl.draw_rectangle_lines(x, y, width, section_height, COLOR_BORDER)
        
        # Label
        rl.draw_text(label, x + 8, y + 4, 9, COLOR_TEXT_FAINT)
        
        # Slots
        slots_x = x + 8
        slots_y = y + 18
        
        for i in range(num_slots):
            slot_x = slots_x + i * (slot_size + slot_gap)
            rl.draw_rectangle(slot_x, slots_y, slot_size, slot_size, COLOR_BG_SLOT)
            rl.draw_rectangle_lines(slot_x, slots_y, slot_size, slot_size, COLOR_BORDER)
    
    def _draw_inventory_right_panel(self, player, x, y, width):
        """Draw the right panel with tabs: World, Status, Map"""
        tab_names = ["World", "Status", "Map"]
        tab_height = 40
        
        # Tab bar background (slight tint so tabs are visible on world tab)
        rl.draw_rectangle(x, y, width, tab_height, rl.Color(13, 21, 32, 180))
        
        # Tab bar
        tab_width = width // len(tab_names)
        mouse_x = self.input.mouse_x
        mouse_y = self.input.mouse_y
        
        for i, name in enumerate(tab_names):
            tab_x = x + i * tab_width
            is_active = i == self.inventory_tab
            
            # Check for mouse hover and click
            is_hovered = (tab_x <= mouse_x < tab_x + tab_width and 
                         y <= mouse_y < y + tab_height)
            
            if is_hovered and self.input.mouse_left_click:
                self.inventory_tab = i
                is_active = True
            
            # Tab background
            if is_active:
                rl.draw_rectangle(tab_x, y, tab_width, tab_height, rl.Color(255, 255, 255, 15))
                rl.draw_line(tab_x, y + tab_height - 2, tab_x + tab_width, y + tab_height - 2, 
                            rl.Color(255, 255, 255, 128))
            elif is_hovered:
                rl.draw_rectangle(tab_x, y, tab_width, tab_height, rl.Color(255, 255, 255, 8))
            
            # Tab text
            text_color = COLOR_TEXT_BRIGHT if is_active else (COLOR_TEXT_DIM if is_hovered else COLOR_TEXT_FAINT)
            text_width = rl.measure_text(name, 12)
            rl.draw_text(name, tab_x + (tab_width - text_width) // 2, y + 14, 12, text_color)
        
        # Tab bar border
        rl.draw_line(x, y + tab_height, x + width, y + tab_height, COLOR_BORDER)
        
        # Content area
        content_x = x + 16
        content_y = y + tab_height + 16
        content_width = width - 32
        content_height = self.canvas_height - tab_height - 32
        
        if self.inventory_tab == 0:
            self._draw_world_tab(player, content_x, content_y, content_width, content_height)
        elif self.inventory_tab == 1:
            self._draw_status_tab(player, content_x, content_y, content_width, content_height)
        elif self.inventory_tab == 2:
            self._draw_map_tab(player, content_x, content_y, content_width, content_height)
    
    def _draw_world_tab(self, player, x, y, width, height):
        """Draw the World tab - completely transparent to show game world"""
        # Completely blank - game world shows through
        pass
    
    def _draw_status_tab(self, player, x, y, width, height):
        """Draw the Status tab - shows skills"""
        # Section header
        rl.draw_text("SKILLS", x, y, 11, COLOR_TEXT_DIM)
        rl.draw_line(x, y + 16, x + width, y + 16, COLOR_BORDER)
        
        skill_y = y + 28
        
        # Group skills by category
        combat_skills = []
        benign_skills = []
        both_skills = []
        
        for skill_id, skill_info in SKILLS.items():
            skill_value = player.skills.get(skill_id, 0)
            category = skill_info.get('category', 'benign')
            name = skill_info.get('name', skill_id.title())
            
            entry = (name, skill_value, category)
            if category == 'combat':
                combat_skills.append(entry)
            elif category == 'both':
                both_skills.append(entry)
            else:
                benign_skills.append(entry)
        
        # Sort by value descending
        combat_skills.sort(key=lambda x: -x[1])
        benign_skills.sort(key=lambda x: -x[1])
        both_skills.sort(key=lambda x: -x[1])
        
        # Draw combat skills
        if combat_skills:
            rl.draw_text("Combat", x, skill_y, 9, COLOR_HEALTH)
            skill_y += 14
            for name, value, _ in combat_skills[:6]:
                self._draw_skill_bar(x, skill_y, width - 20, name, value, COLOR_HEALTH)
                skill_y += 18
            skill_y += 10
        
        # Draw benign skills
        if benign_skills:
            rl.draw_text("Trade", x, skill_y, 9, COLOR_FATIGUE)
            skill_y += 14
            for name, value, _ in benign_skills[:8]:
                self._draw_skill_bar(x, skill_y, width - 20, name, value, COLOR_FATIGUE)
                skill_y += 18
            skill_y += 10
        
        # Draw hybrid skills
        if both_skills:
            rl.draw_text("Hybrid", x, skill_y, 9, COLOR_STAMINA)
            skill_y += 14
            for name, value, _ in both_skills[:4]:
                self._draw_skill_bar(x, skill_y, width - 20, name, value, COLOR_STAMINA)
                skill_y += 18
    
    def _draw_skill_bar(self, x, y, width, name, value, color):
        """Draw a single skill bar"""
        name_width = 100
        bar_width = width - name_width - 30
        
        # Skill name
        rl.draw_text(name, x + 10, y, 10, COLOR_TEXT_DIM)
        
        # Bar background
        bar_x = x + name_width
        rl.draw_rectangle(bar_x, y + 2, bar_width, 6, rl.Color(255, 255, 255, 15))
        
        # Bar fill
        fill_width = int(bar_width * value / 100)
        bar_color = rl.Color(color.r, color.g, color.b, 150)
        rl.draw_rectangle(bar_x, y + 2, fill_width, 6, bar_color)
        
        # Value text
        value_str = str(int(value))
        rl.draw_text(value_str, bar_x + bar_width + 6, y, 10, COLOR_TEXT_FAINT)
    
    def _draw_map_tab(self, player, x, y, width, height):
        """Draw the Map tab - shows world map (placeholder)"""
        # Header
        rl.draw_text("WORLD MAP", x, y, 11, COLOR_TEXT_DIM)
        rl.draw_line(x, y + 16, x + width, y + 16, COLOR_BORDER)
        
        # Map placeholder
        map_y = y + 28
        map_height = height - 40
        
        rl.draw_rectangle(x, map_y, width, map_height, rl.Color(45, 74, 62, 50))
        rl.draw_rectangle_lines(x, map_y, width, map_height, COLOR_BORDER)
        
        text = "[ Map ]"
        text_width = rl.measure_text(text, 16)
        rl.draw_text(text, x + (width - text_width) // 2, map_y + map_height // 2, 16, COLOR_TEXT_FAINT)


# Entry point for testing
if __name__ == "__main__":
    app = BoardGUI()
    app.run()