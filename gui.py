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
    FARM_CELL_COLORS, JOB_TIERS, ITEMS,
    BG_COLOR, GRID_COLOR, ROAD_COLOR,
    TICKS_PER_DAY, TICKS_PER_YEAR, SLEEP_START_FRACTION,
    MOVEMENT_SPEED, CHARACTER_WIDTH, CHARACTER_HEIGHT,
    DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, ZOOM_SPEED, SPRINT_SPEED,
    SOUND_RADIUS, VISION_RANGE, VISION_CONE_ANGLE, SHOW_PERCEPTION_DEBUG,
    ADJACENCY_DISTANCE, INTERACT_DISTANCE, SKILLS, START_MUTED
)
from scenario_world import AREAS, BARRELS, BEDS, VILLAGE_NAME, SIZE, ROADS
from game_state import GameState
from game_logic import GameLogic
from player_controller import PlayerController
from sprites import get_sprite_manager
from dialogue import DialogueSystem
from environment_menu import EnvironmentMenu
from inventory_menu import InventoryMenu


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


# =============================================================================
# OCCLUDER CONFIGURATION - Objects that can hide characters
# =============================================================================
# Each occluder type defines:
# - sort_y_offset: Added to world Y for depth sorting (where the "base" is)
# - occlusion_height: How far above sort_y the object extends (for occlusion check)
# - occlusion_width: Half-width for horizontal overlap check
# - draw_height_mult: Multiplier for cell_size to get draw height
# - draw_aspect: Width/height ratio for drawing
# - texture_key: Key in world_textures dict
# - animated: Whether this occluder uses sprite sheet animation
# - frame_width: Width of each frame (if animated)
# - frame_height: Height of each frame (if animated)
# - frame_duration: Seconds per frame (if animated)

OCCLUDER_CONFIG = {
    'tree': {
        'sort_y_offset': 0.5,      # Middle of cell (trunk base)
        'occlusion_height': 2.0,   # Tree extends ~2 cells above base
        'occlusion_width': 0.8,    # Horizontal overlap threshold
        'draw_height_mult': 2.5,   # Draw height = cell_size * 2.5
        'draw_aspect': 64 / 64,    # Width/height ratio (now 1:1 for 64x64 frames)
        'texture_key': 'tree',
        'animated': True,
        'frame_width': 64,
        'frame_height': 64,
        'frame_duration': 0.15,    # ~6.7 FPS for gentle swaying
    },
    'barrel': {
        'sort_y_offset': 0.5,      # Middle of cell
        'occlusion_height': 0.8,   # Barrel extends slightly above its base
        'occlusion_width': 0.5,    # Narrower than a full cell
        'draw_height_mult': 0.8,   # Draw height = cell_size * 0.8
        'draw_aspect': 1.0,        # Square
        'texture_key': 'barrel',
        'animated': False,
    },
    'bed': {
        'sort_y_offset': 0.5,      # Middle of cell
        'occlusion_height': 0.6,   # Bed is low
        'occlusion_width': 0.5,    # 1 cell wide
        'draw_height_mult': 1.7,   # Draw height = cell_size * 1.7 (2 cells tall)
        'draw_aspect': 0.5,        # Width/height ratio (1 cell wide, 2 cells tall)
        'texture_key': 'bed',
        'animated': False,
        'height': 2,               # Bed spans 2 cells vertically (visual)
    },
    'stove': {
        'sort_y_offset': 0.5,      # Middle of cell
        'occlusion_height': 0.7,   # Stove is medium height
        'occlusion_width': 0.5,    # Narrower than a full cell
        'draw_height_mult': 0.85,  # Draw height = cell_size * 0.85
        'draw_aspect': 1.0,        # Square
        'texture_key': 'stove',
        'animated': False,
    },
    'house': {
        'sort_y_offset': 0.0,      # Use bottom edge of house for sorting (will be adjusted per-house)
        'occlusion_height': 2.0,   # Houses are tall (reduced by 1 cell)
        'occlusion_width': 0,    # Houses are wide (will be adjusted per-house)
        'draw_height_mult': 1.0,   # Calculated per-house
        'draw_aspect': 1.0,        # Calculated per-house
        'texture_key': 'house_s',  # Default, will select based on size
        'animated': False,
        'is_multi_cell': True,     # Special flag for multi-cell objects
    },
}


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
        self.combat_mode_toggle = False
        self.interact = False       # Unified: NPC dialogue, doors, windows, stoves
        
        # Camera
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.zoom_in = False
        self.zoom_out = False
        
        # Menu/UI
        self.pause = False
        self.menu = False
        self.inventory_toggle = False
        self.environment_menu_toggle = False
        
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
        
        # Dialogue system
        self.dialogue = DialogueSystem(self.state, self.logic)
        
        # Environment interaction menu
        self.environment_menu = EnvironmentMenu(self.state, self.logic)
        
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
            self.camera_x = self.state.player.x
            self.camera_y = self.state.player.y
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
        self.inventory_menu = InventoryMenu(self.state)
        
        # Window "security camera" viewing state
        self.window_viewing = False
        self.window_viewing_window = None  # The Window object being looked through
        self.window_viewing_interior = None  # Interior being viewed (when looking in from outside)
        
        # Track last known player zone for death rendering
        self._last_player_zone = None
        
        # Debug window (optional - can be disabled for mobile)
        self.debug_window = None
        try:
            from debug_window import DebugWindow
            self.debug_window = DebugWindow(self.state, self.logic)
        except ImportError:
            pass
        
        # Frame-level rendering cache (cleared each frame for performance)
        self._frame_cache = {}
        self._visible_min_x = 0
        self._visible_max_x = SIZE
        self._visible_min_y = 0
        self._visible_max_y = SIZE
        
        # Spatial hash for trees (built once, massive performance improvement)
        self._tree_spatial_hash = None
        self._tree_spatial_chunk_size = 16  # 16x16 cell chunks
        
        # Track health/stamina for bar visibility
        self._char_prev_health = {}  # char_name -> previous health
        self._char_prev_stamina = {}  # char_name -> previous stamina
        self._char_show_bars_until = {}  # char_name -> time to show bars until
        self._bar_display_duration = 3.0  # Show bars for 3 seconds after change
    
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
        
        # Mute state
        self.is_muted = START_MUTED
        
        # Load and play background music
        music_path = os.path.join(self.script_dir, "Forest__8-Bit_Music_.mp3")
        self.music = None
        if os.path.exists(music_path):
            self.music = rl.load_music_stream(music_path)
            rl.set_music_volume(self.music, 0.0 if self.is_muted else 0.3)
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
            # Interior sprites
            'interior_floor': 'sprites/Interior_Floor.png',
            'interior_back_wall': 'sprites/Interior_BackWall.png',
            'interior_back_wall_window': 'sprites/Interior_BackWallWindow.png',
            'interior_south_wall': 'sprites/Interior_SouthWall.png',
            'interior_east_wall': 'sprites/Interior_EastWall.png',
            'interior_west_wall': 'sprites/Interior_WestWall.png',
            # Object sprites
            'bed': 'sprites/Bed.png',
            'stove': 'sprites/Stove.png',
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
        
        # Extract animated occluder frames
        self.occluder_frames = {}
        for occluder_type, config in OCCLUDER_CONFIG.items():
            if config.get('animated'):
                tex = self.world_textures.get(config['texture_key'])
                if tex:
                    frame_w = config['frame_width']
                    frame_h = config['frame_height']
                    num_frames = tex.width // frame_w
                    frames = []
                    for i in range(num_frames):
                        frames.append(rl.Rectangle(i * frame_w, 0, frame_w, frame_h))
                    self.occluder_frames[occluder_type] = frames
        
        # Load item sprites for ground items (from ITEMS constant)
        self.item_textures = {}
        for item_type, item_info in ITEMS.items():
            sprite_name = item_info.get('sprite')
            if sprite_name:
                filepath = os.path.join(self.script_dir, 'sprites', 'items', sprite_name)
                if os.path.exists(filepath):
                    self.item_textures[item_type] = rl.load_texture(filepath)
                else:
                    self.item_textures[item_type] = None
        
        # Load fonts
        self.font_default = rl.get_font_default()
    
    def run(self):
        """Main game loop"""
        # Profiling setup
        self._profile_times = {'input': 0, 'logic': 0, 'render': 0, 'debug': 0}
        self._profile_frame_count = 0
        self._profile_last_report = time.time()
        
        while self.running and not rl.window_should_close():
            # Update music stream
            if self.music:
                rl.update_music_stream(self.music)
            
            # Profile input handling
            t0 = time.time()
            self._handle_input()
            t1 = time.time()
            self._profile_times['input'] += t1 - t0
            
            # Profile game logic
            self._game_loop()
            t2 = time.time()
            self._profile_times['logic'] += t2 - t1
            
            # Profile rendering
            self._render_frame()
            t3 = time.time()
            self._profile_times['render'] += t3 - t2
            
            # Update debug window if present
            if self.debug_window and self.debug_window.is_open():
                player = self.state.player
                if player:
                    player_food = player.get_item('wheat')
                    player_money = player.get_item('gold')
                    status = f"Pos:({player.x:.1f},{player.y:.1f}) Wheat:{player_food} ${player_money} HP:{player.health} | Zoom:{self.zoom:.1f}x | {'Follow' if self.camera_following_player else 'Free'}"
                else:
                    status = f"No player | Zoom:{self.zoom:.1f}x"
                self.debug_window.set_status(status)
                self.debug_window.update()
            t4 = time.time()
            self._profile_times['debug'] += t4 - t3
            
            self._profile_frame_count += 1
            
            # Report profiling every 2 seconds
            if time.time() - self._profile_last_report > 2.0:
                total = sum(self._profile_times.values())
                if total > 0 and self._profile_frame_count > 0:
                    fps = self._profile_frame_count / 2.0
                    print(f"\n=== PROFILE ({fps:.1f} FPS, {self._profile_frame_count} frames) ===")
                    print(f"  Input:  {self._profile_times['input']*1000/self._profile_frame_count:.2f}ms/frame ({100*self._profile_times['input']/total:.1f}%)")
                    print(f"  Logic:  {self._profile_times['logic']*1000/self._profile_frame_count:.2f}ms/frame ({100*self._profile_times['logic']/total:.1f}%)")
                    print(f"  Render: {self._profile_times['render']*1000/self._profile_frame_count:.2f}ms/frame ({100*self._profile_times['render']/total:.1f}%)")
                    print(f"  Debug:  {self._profile_times['debug']*1000/self._profile_frame_count:.2f}ms/frame ({100*self._profile_times['debug']/total:.1f}%)")
                self._profile_times = {'input': 0, 'logic': 0, 'render': 0, 'debug': 0}
                self._profile_frame_count = 0
                self._profile_last_report = time.time()
        
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
        
        # Unload item textures
        for tex in self.item_textures.values():
            if tex:
                rl.unload_texture(tex)
        
        # Unload music
        if self.music:
            rl.unload_music_stream(self.music)
        
        rl.close_audio_device()
        rl.close_window()
    
    def _toggle_mute(self):
        """Toggle music mute state"""
        self.is_muted = not self.is_muted
        if self.music:
            rl.set_music_volume(self.music, 0.0 if self.is_muted else 0.3)
    
    def _handle_environment_action(self, action):
        """Handle an action selected from the environment menu.
        
        Args:
            action: The action string selected (e.g., "Harvest", "Plant", "Build Campfire", "Build")
        """
        player = self.state.player
        if not player:
            return
        
        name = player.get_display_name()
        
        if action == "Harvest":
            # Instant harvest via game logic (handles theft detection)
            if not self.logic.player_harvest_cell(player):
                self.state.log_action(f"{name} couldn't harvest here.")
        
        elif action == "Plant":
            # Instant plant via game logic
            if not self.logic.player_plant_cell(player):
                self.state.log_action(f"{name} couldn't plant here.")
        
        elif action == "Build Campfire":
            # Build a campfire at current location
            if not self.logic.make_camp(player):
                self.state.log_action(f"{name} can't make a camp here")
        
        elif action == "Build":
            # TODO: Open build menu (future feature)
            self.state.log_action(f"{name} looks around for building materials...")
    
    # =========================================================================
    # INPUT HANDLING
    # =========================================================================
    
    def _handle_input(self):
        """Handle all input sources (keyboard, mouse, gamepad)"""
        # Reset per-frame input state
        self.input.attack = False
        self.input.eat = False
        self.input.combat_mode_toggle = False
        self.input.pause = False
        self.input.inventory_toggle = False
        self.input.environment_menu_toggle = False
        self.input.zoom_in = False
        self.input.zoom_out = False
        self.input.mouse_left_click = False
        self.input.mouse_right_click = False
        self.input.interact = False
        
        # Handle dialogue input first (blocks other input when active)
        if self.dialogue.is_active:
            self.dialogue.handle_input()
            # Still need to handle window resize
            if rl.is_window_resized():
                self.window_width = rl.get_screen_width()
                self.window_height = rl.get_screen_height()
                self.canvas_width = self.window_width
                self.canvas_height = self.window_height
            return
        
        # Handle environment menu input (blocks other input when active)
        if self.environment_menu.is_active:
            action = self.environment_menu.handle_input()
            if action and action != "closed":
                self._handle_environment_action(action)
            # Still need to handle window resize
            if rl.is_window_resized():
                self.window_width = rl.get_screen_width()
                self.window_height = rl.get_screen_height()
                self.canvas_width = self.window_width
                self.canvas_height = self.window_height
            return
        
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
            self.input.interact = True  # E for unified interact (NPC, door, window, stove)
        if rl.is_key_pressed(rl.KEY_Q):
            self.input.eat = True       # Q for eat
        if rl.is_key_pressed(rl.KEY_R):
            self.input.combat_mode_toggle = True  # R for combat mode toggle
        if rl.is_key_pressed(rl.KEY_ESCAPE):
            self.input.pause = True
        if rl.is_key_pressed(rl.KEY_M):
            self._toggle_mute()         # M for mute/unmute music
        if rl.is_key_pressed(rl.KEY_G):
            self.input.environment_menu_toggle = True  # G for environment menu
        
        # Inventory toggle (Tab only)
        if rl.is_key_pressed(rl.KEY_TAB):
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
        
        # Mouse wheel - stored but not used for zoom (zoom is +/- keys only)
        wheel = rl.get_mouse_wheel_move()
        if wheel != 0:
            self.input.mouse_wheel = wheel
    
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
        # A/Cross - Interact (unified: NPC, door, window, stove)
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_DOWN):
            self.input.interact = True
        
        # B/Circle - (unused - closes menus when open)
        
        # X/Square - Environment menu
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_LEFT):
            self.input.environment_menu_toggle = True
        
        # Y/Triangle - Eat
        if rl.is_gamepad_button_pressed(gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_UP):
            self.input.eat = True
        
        # Bumpers
        # Left bumper - (unused)
        
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
        if self.inventory_menu.is_open:
            if self.player_moving:
                self.player_controller.stop_movement()
                self.player_moving = False
            return
        
        # Block movement while viewing through window
        if self.window_viewing:
            if self.player_moving:
                self.player_controller.stop_movement()
                self.player_moving = False
            return
        
        # Block movement during dialogue
        if self.dialogue.is_active:
            if self.player_moving:
                self.player_controller.stop_movement()
                self.player_moving = False
            return
        
        # Block movement when environment menu is open
        if self.environment_menu.is_active:
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
        if self.inventory_menu.is_open:
            return
        
        # Unified interact (E key / A button) - handles NPC, door, window, stove
        if self.input.interact:
            self._handle_unified_interact()
        
        # Attacks require combat mode
        if self.input.attack:
            player = self.state.player
            if player and player.get('combat_mode', False):
                self.player_controller.handle_attack_input()
        
        if self.input.eat:
            self.player_controller.handle_eat_input()
    
    def _handle_unified_interact(self):
        """Handle unified interact (E key / A button).
        
        Checks for interactables in priority order:
        1. If window viewing → toggle off
        2. Door → enter/exit building (first so player can escape combat)
        3. NPC → start dialogue (must be facing them)
        4. Window → start window viewing
        5. Stove/campfire → bake bread
        6. Barrel → take wheat
        7. Bed → sleep (not implemented)
        8. Tree → chop (not implemented)
        """
        player = self.state.player
        if not player:
            return
        
        # Priority 1: If currently window viewing, toggle it off
        if self.window_viewing:
            self._toggle_window_view_off()
            return
        
        # Priority 2: Check for door FIRST (allows escaping combat)
        house = self.state.get_adjacent_door(player)
        if house:
            if self.player_controller.handle_door_input():
                # Successfully entered/exited - update camera
                self.camera_x = player.x
                self.camera_y = player.y
                return
        
        # Priority 3: Check for nearby NPC (must be facing them)
        npc = self._get_facing_npc(player)
        if npc:
            if self.dialogue.can_start_dialogue(npc):
                self.dialogue.start_dialogue(npc)
                return
            else:
                self.state.log_action(f"{npc.get_display_name()} is busy!")
                return
        
        # Priority 4: Check for window
        window = self.player_controller.handle_window_input()
        if window:
            self._start_window_viewing(window)
            return
        
        # Priority 5: Check for stove/campfire (baking) - must be facing
        cooking_spot = self.logic.get_adjacent_cooking_spot(player)
        if cooking_spot:
            # Check if facing the cooking spot
            source = cooking_spot.get('source')
            if cooking_spot['type'] == 'stove':
                # Stoves are interior - use local coords
                target_x, target_y = source.x + 0.5, source.y + 0.5
                target_zone = source.zone
            else:  # campfire
                # Campfires are exterior - use world coords
                target_x, target_y = source[0] + 0.5, source[1] + 0.5
                target_zone = None
            
            if self._is_facing_position(player, target_x, target_y, target_zone):
                self.player_controller.handle_bake_input()
                return
        
        # Priority 6: Check for barrel (must be facing)
        for barrel in self.state.interactables.barrels.values():
            if barrel.is_adjacent(player):
                # Use local coords for interior barrels, world coords for exterior
                if barrel.zone is not None:
                    target_x, target_y = barrel.x + 0.5, barrel.y + 0.5
                else:
                    target_x, target_y = barrel.world_x, barrel.world_y
                if self._is_facing_position(player, target_x, target_y, barrel.zone):
                    self.player_controller.handle_barrel_input()
                    return
        
        # Priority 7: Check for bed (must be facing) - not implemented
        for bed in self.state.interactables.beds.values():
            if bed.is_adjacent(player):
                # Beds are interior - use local coords
                if self._is_facing_position(player, bed.x + 0.5, bed.y + 0.5, bed.zone):
                    is_owned = bed.is_owned_by(player.name)
                    if is_owned or not bed.is_owned():
                        self.state.log_action("Sleep not implemented yet")
                    else:
                        self.state.log_action("Not your bed")
                    return
        
        # Priority 8: Check for tree (must be facing) - not implemented
        for pos, tree in self.state.interactables.trees.items():
            if tree.is_adjacent(player):
                # Trees are exterior - use world coords (zone is None)
                if self._is_facing_position(player, tree.x + 0.5, tree.y + 0.5, None):
                    self.state.log_action("Shaking trees not implemented yet")
                    return
    
    def _get_facing_npc(self, player):
        """Get nearest NPC that player is facing within interact distance."""
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
                # Pass zone so _is_facing_position uses correct player coords
                if self._is_facing_position(player, cx, cy, player.zone):
                    nearest_npc = char
                    nearest_dist = dist
        
        return nearest_npc
    
    def _toggle_window_view_off(self):
        """Stop window viewing and recenter on player."""
        player = self.state.player
        self.window_viewing = False
        self.window_viewing_window = None
        self.window_viewing_interior = None
        self.camera_following_player = True
        if player:
            player.viewing_through_window = None
            player.viewing_into_interior = None
            if player.zone:
                self.camera_x = player.prevailing_x
                self.camera_y = player.prevailing_y
            else:
                self.camera_x = player.x
                self.camera_y = player.y
    
    def _start_window_viewing(self, window):
        """Start viewing through a window."""
        player = self.state.player
        if not player:
            return
        
        if player.zone is not None:
            # Inside looking out - camera goes to exterior position
            look_x, look_y = window.get_exterior_look_position()
            self.camera_x = look_x
            self.camera_y = look_y
            self.window_viewing_interior = None
            player.viewing_through_window = window
            player.viewing_into_interior = None
        else:
            # Outside looking in - camera goes to interior center
            interior = window.interior
            self.camera_x = interior.width / 2
            self.camera_y = interior.height / 2
            self.window_viewing_interior = interior
            player.viewing_through_window = window
            player.viewing_into_interior = interior
        
        self.window_viewing = True
        self.window_viewing_window = window
        self.camera_following_player = False
    
    def _apply_camera_input(self):
        """Apply camera control input"""
        player = self.state.player
        
        # Don't allow camera changes while window viewing
        # Use E (unified interact) to exit window viewing, not R
        if self.window_viewing:
            return
        
        # Toggle combat mode
        if self.input.combat_mode_toggle:
            if player:
                player['combat_mode'] = not player.get('combat_mode', False)
                mode_str = "COMBAT MODE" if player['combat_mode'] else "normal mode"
                self.state.log_action(f"{player.get_display_name()} entered {mode_str}")
        
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
            player = self.state.player
            # Use local coords when inside (so interior renders correctly)
            # Use world coords when outside or window viewing
            if player.zone and not self.window_viewing:
                self.camera_x = player.prevailing_x
                self.camera_y = player.prevailing_y
            else:
                self.camera_x = player.x
                self.camera_y = player.y
    
    def _apply_ui_input(self):
        """Apply UI input (pause, inventory, environment menu)"""
        # Escape = toggle pause (always, regardless of inventory state)
        if self.input.pause:
            self.state.paused = not self.state.paused
        
        # Environment menu toggle (G or X button) - blocked in combat mode
        if self.input.environment_menu_toggle:
            if self.environment_menu.is_active:
                self.environment_menu.close()
            else:
                # Can't open environment menu while in combat mode
                player = self.state.player
                if not player or not player.get('combat_mode', False):
                    self.environment_menu.open()
        
        # Inventory toggle (Tab or Select button) - but not if environment menu is open
        if self.input.inventory_toggle:
            if not self.environment_menu.is_active:
                self.inventory_menu.toggle()
        
        # Tab switching in inventory (gamepad bumpers only)
        if self.inventory_menu.is_open:
            # Check if confirmation popup is open - it takes highest priority
            if self.inventory_menu._confirm_popup_open:
                nav_left = False
                nav_right = False
                select = False
                cancel = rl.is_key_pressed(rl.KEY_ESCAPE)
                
                # Keyboard left/right
                if rl.is_key_pressed(rl.KEY_LEFT) or rl.is_key_pressed(rl.KEY_A):
                    nav_left = True
                if rl.is_key_pressed(rl.KEY_RIGHT) or rl.is_key_pressed(rl.KEY_D):
                    nav_right = True
                if rl.is_key_pressed(rl.KEY_ENTER) or rl.is_key_pressed(rl.KEY_SPACE):
                    select = True
                
                # Gamepad popup input
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_LEFT_FACE_LEFT):
                    nav_left = True
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_LEFT_FACE_RIGHT):
                    nav_right = True
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_DOWN):  # A
                    select = True
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_RIGHT):  # B
                    cancel = True
                
                self.inventory_menu.handle_confirm_popup_input(nav_left, nav_right, select, cancel)
            # Check if context menu is open - it takes priority
            elif self.inventory_menu.context_menu_open:
                # Context menu input - gamepad only for navigation
                nav_up = False
                nav_down = False
                select = False
                cancel = rl.is_key_pressed(rl.KEY_ESCAPE)  # Escape always works to cancel
                
                # Gamepad context menu input
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_LEFT_FACE_UP):
                    nav_up = True
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_LEFT_FACE_DOWN):
                    nav_down = True
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_DOWN):  # A
                    select = True
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_RIGHT):  # B
                    cancel = True
                
                # Mouse click to select option
                if self.input.mouse_left_click:
                    mx, my = self.input.mouse_x, self.input.mouse_y
                    cmx, cmy, cmw, cmh = self.inventory_menu.context_menu_rect
                    if cmx <= mx < cmx + cmw and cmy <= my < cmy + cmh:
                        select = True
                    else:
                        cancel = True  # Click outside closes menu
                
                self.inventory_menu.handle_context_menu_input(nav_up, nav_down, select, cancel)
            else:
                # Normal inventory handling
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_LEFT_TRIGGER_1):
                    self.inventory_menu.prev_tab()
                if rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_TRIGGER_1):
                    self.inventory_menu.next_tab()
                # Handle navigation input (gamepad only)
                self.inventory_menu.handle_input()
                
                # Handle item interactions - gamepad buttons only
                a_pressed = rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_DOWN)
                x_pressed = rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_LEFT)
                y_pressed = rl.is_gamepad_button_pressed(self.input.gamepad_id, rl.GAMEPAD_BUTTON_RIGHT_FACE_UP)
                lb_held = rl.is_gamepad_button_down(self.input.gamepad_id, rl.GAMEPAD_BUTTON_LEFT_TRIGGER_1)
                
                # Shift+Click opens context menu (mouse)
                if self.input.mouse_left_click and rl.is_key_down(rl.KEY_LEFT_SHIFT):
                    clicked_slot = self.inventory_menu._get_slot_at_mouse()
                    if clicked_slot and clicked_slot[0] == 'inventory':
                        self.inventory_menu.open_context_menu(clicked_slot[1])
                elif a_pressed or x_pressed:
                    # LB + A = quick move, otherwise normal interact
                    quick_move = lb_held and a_pressed
                    self.inventory_menu.handle_item_interaction(
                        full_interact=a_pressed and not lb_held, 
                        single_interact=x_pressed,
                        quick_move=quick_move
                    )
                
                # Y button opens context menu (gamepad)
                if y_pressed:
                    self.inventory_menu.open_context_menu()
    
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
        # Use prevailing coords when in interior (camera space matches interior)
        if player.zone:
            dx = world_x - player.prevailing_x
            dy = world_y - player.prevailing_y
        else:
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
        
        # Check stamina for sprinting (Skyrim-style)
        if sprinting:
            # Check if player can sprint (has stamina)
            if player.is_sprinting:
                # Already sprinting - check if can continue
                if not player.can_continue_sprint():
                    sprinting = False
            else:
                # Trying to start sprinting - check if can start
                if not player.can_start_sprint():
                    sprinting = False
        
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
            player = self.state.player
            # Use local coords when inside (so interior renders correctly)
            if player.zone and not self.window_viewing:
                self.camera_x = player.prevailing_x
                self.camera_y = player.prevailing_y
            else:
                self.camera_x = player.x
                self.camera_y = player.y
        
        # Update dialogue system (runs even when game is unpaused)
        self.dialogue.update(dt)
        
        # Update environment menu
        self.environment_menu.update(dt)
    
    # =========================================================================
    # RENDERING
    # =========================================================================
    
    def _render_frame(self):
        """Render the current game state"""
        # Detailed render profiling
        if not hasattr(self, '_render_profile'):
            self._render_profile = {'grid': 0, 'trees_chars': 0, 'hud': 0, 'other': 0}
            self._render_profile_count = 0
        
        rl.begin_drawing()
        rl.clear_background(hex_to_color(BG_COLOR))
        
        t0 = time.time()
        self._draw_canvas()
        t1 = time.time()
        
        # Draw HUD overlay or inventory screen
        if self.inventory_menu.is_open:
            # Update inventory menu state before rendering
            self.inventory_menu.set_canvas_size(self.canvas_width, self.canvas_height)
            self.inventory_menu.update_input(
                self.input.mouse_x, self.input.mouse_y,
                self.input.mouse_left_click, self.input.gamepad_connected,
                self.input.mouse_right_click,
                rl.is_key_down(rl.KEY_LEFT_SHIFT) or rl.is_key_down(rl.KEY_RIGHT_SHIFT)
            )
            # Handle scrolling (mouse wheel, scroll bar drag, gamepad stick)
            self.inventory_menu.update_scroll()
            self.inventory_menu.render()
        else:
            self._draw_hud()
        t2 = time.time()
        
        # Draw dialogue UI (on top of everything)
        self.dialogue.render(self.canvas_width, self.canvas_height)
        
        # Draw environment menu (on top of everything)
        self.environment_menu.render(self.canvas_width, self.canvas_height)
        
        rl.end_drawing()
        
        self._render_profile['grid'] += t1 - t0
        self._render_profile['hud'] += t2 - t1
        self._render_profile_count += 1
        
        # Report every 60 frames
        if self._render_profile_count >= 60:
            print(f"  [Render breakdown] Canvas: {self._render_profile['grid']*1000/60:.2f}ms, HUD: {self._render_profile['hud']*1000/60:.2f}ms")
            self._render_profile = {'grid': 0, 'trees_chars': 0, 'hud': 0, 'other': 0}
            self._render_profile_count = 0
    
    def _draw_canvas(self):
        """Draw the game canvas with camera (zoom and pan)"""
        # Detailed profiling
        if not hasattr(self, '_canvas_profile'):
            self._canvas_profile = {'setup': 0, 'grid': 0, 'trees_chars': 0, 'camps': 0, 'death': 0}
            self._canvas_profile_count = 0
        
        _cp_t0 = time.time()
        
        canvas_width = self.canvas_width
        canvas_height = self.canvas_height
        canvas_center_x = canvas_width / 2
        canvas_center_y = canvas_height / 2
        
        cell_size = CELL_SIZE * self.zoom
        
        # Store camera transform info
        self._cam_center_x = canvas_center_x
        self._cam_center_y = canvas_center_y
        self._cam_cell_size = cell_size
        
        # Clear frame cache at start of each frame (Fix #2: per-frame caching)
        self._frame_cache = {}
        
        # Check if player is in an interior (and not looking through window)
        # OR if we're looking into an interior from outside
        player = self.state.player
        
        # Track last known player zone for death rendering
        if player:
            if player.zone is not None:
                self._last_player_zone = player.zone
            else:
                # Player is alive and in exterior - clear the tracking
                self._last_player_zone = None
        
        in_interior = player and player.zone is not None and not self.window_viewing
        looking_into_interior = self.window_viewing and self.window_viewing_interior is not None
        
        # If player is dead but was in interior, stay in interior view
        player_dead_in_interior = (not player and self._last_player_zone is not None 
                                   and not self.window_viewing)
        
        if in_interior or looking_into_interior or player_dead_in_interior:
            # Render interior instead of exterior
            self._draw_interior_canvas()
            return
        
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
        
        # Store visible bounds for use by other methods (Fix #1: view frustum culling)
        self._visible_min_x = min_visible_x
        self._visible_max_x = max_visible_x
        self._visible_min_y = min_visible_y
        self._visible_max_y = max_visible_y
        
        _cp_t1 = time.time()
        self._canvas_profile['setup'] += _cp_t1 - _cp_t0
        
        # Draw grid cells
        self._draw_grid(min_visible_x, max_visible_x, min_visible_y, max_visible_y)
        _cp_t2 = time.time()
        self._canvas_profile['grid'] += _cp_t2 - _cp_t1
        
        # Draw camps (these stay on ground level, not occluding)
        self._draw_camps()
        _cp_t3 = time.time()
        self._canvas_profile['camps'] += _cp_t3 - _cp_t2
        
        # Draw perception debug if enabled
        if SHOW_PERCEPTION_DEBUG:
            self._draw_perception_debug()
        
        # Draw all occluders (trees, houses, barrels, beds, stoves) and characters together, Y-sorted for proper depth
        self._draw_trees_and_characters()
        _cp_t4 = time.time()
        self._canvas_profile['trees_chars'] += _cp_t4 - _cp_t3
        
        # Draw death animations
        self._draw_death_animations()
        _cp_t5 = time.time()
        self._canvas_profile['death'] += _cp_t5 - _cp_t4
        
        self._canvas_profile_count += 1
        if self._canvas_profile_count >= 60:
            print(f"    [Canvas] setup:{self._canvas_profile['setup']*1000/60:.1f}ms grid:{self._canvas_profile['grid']*1000/60:.1f}ms trees+chars:{self._canvas_profile['trees_chars']*1000/60:.1f}ms camps:{self._canvas_profile['camps']*1000/60:.1f}ms")
            self._canvas_profile = {'setup': 0, 'grid': 0, 'trees_chars': 0, 'camps': 0, 'death': 0}
            self._canvas_profile_count = 0
    
    def _draw_interior_canvas(self):
        """Draw the interior when player is inside a building or looking in from outside.
        
        Interior layout (for width x height walkable floor):
        - Back wall at y=-2 (extra back row)
        - Back wall at y=-1 (with centered window)
        - Left wall at x=-1 (with centered window)
        - Right wall at x=width (with centered window)
        - Front wall at y=height (with door)
        - Floor tiles from (0,0) to (width-1, height-1) - all walkable
        
        Corner priority:
        - Front wall (south) takes priority at y=height corners
        - Side walls (east/west) take priority at y=-1 corners (back wall)
        """
        player = self.state.player
        
        # Determine which interior to render
        if self.window_viewing_interior is not None:
            # Looking into an interior from outside
            interior = self.window_viewing_interior
        elif player and player.zone:
            # Player is inside an interior
            interior = self.state.interiors.get_interior(player.zone)
        elif self._last_player_zone:
            # Player died in interior - use last known zone
            interior = self.state.interiors.get_interior(self._last_player_zone)
        else:
            return
        
        if not interior:
            return
        
        # Set visible bounds for interior (includes walls around the walkable area)
        # Interiors are small, so include everything with margin
        self._visible_min_x = -3
        self._visible_max_x = interior.width + 3
        self._visible_min_y = -3
        self._visible_max_y = interior.height + 3
        
        cell_size = self._cam_cell_size
        tile_size = int(cell_size) + 1
        
        # Fallback colors (used if textures missing)
        floor_color = rl.Color(240, 235, 220, 255)
        wall_color = rl.Color(120, 100, 80, 255)
        window_color = rl.Color(150, 200, 255, 180)
        door_color = rl.Color(0, 0, 0, 255)
        
        # Get textures
        floor_tex = self.world_textures.get('interior_floor')
        back_wall_tex = self.world_textures.get('interior_back_wall')
        back_wall_window_tex = self.world_textures.get('interior_back_wall_window')
        south_wall_tex = self.world_textures.get('interior_south_wall')
        east_wall_tex = self.world_textures.get('interior_east_wall')
        west_wall_tex = self.world_textures.get('interior_west_wall')
        
        # Helper to check if a position has a window
        def has_window_at(x, y):
            return any(w.interior_x == x and w.interior_y == y for w in interior.windows)
        
        # Helper to draw a tile with texture or fallback color
        def draw_tile(screen_x, screen_y, tex, fallback_color):
            if tex:
                source = rl.Rectangle(0, 0, tex.width, tex.height)
                dest = rl.Rectangle(int(screen_x), int(screen_y), tile_size, tile_size)
                rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                rl.draw_rectangle(int(screen_x), int(screen_y), tile_size, tile_size, fallback_color)
        
        # Draw extra back wall row at y=-2 (solid wall, no windows) - excludes corners
        for x in range(interior.width):
            screen_x, screen_y = self._world_to_screen(x, -2)
            draw_tile(screen_x, screen_y, back_wall_tex, wall_color)
        
        # Draw back wall row at y=-1 (may have windows) - excludes corners (side walls handle those)
        for x in range(interior.width):
            screen_x, screen_y = self._world_to_screen(x, -1)
            if has_window_at(x, -1):
                draw_tile(screen_x, screen_y, back_wall_window_tex, window_color)
            else:
                draw_tile(screen_x, screen_y, back_wall_tex, wall_color)
        
        # Draw left wall column at x=-1 (from y=-2 to y=height-1, NOT including front wall row)
        # Side walls take priority at back corners (y=-2, y=-1)
        for y in range(-2, interior.height):
            screen_x, screen_y = self._world_to_screen(-1, y)
            draw_tile(screen_x, screen_y, west_wall_tex, wall_color)
        
        # Draw right wall column at x=width (from y=-2 to y=height-1, NOT including front wall row)
        # Side walls take priority at back corners (y=-2, y=-1)
        for y in range(-2, interior.height):
            screen_x, screen_y = self._world_to_screen(interior.width, y)
            draw_tile(screen_x, screen_y, east_wall_tex, wall_color)
        
        # Draw front wall row at y=height (with door) - INCLUDES corners (south takes priority)
        for x in range(-1, interior.width + 1):
            screen_x, screen_y = self._world_to_screen(x, interior.height)
            is_door = (x == interior.door_x)
            if is_door:
                # Door
                rl.draw_rectangle(int(screen_x), int(screen_y), tile_size, tile_size, door_color)
            else:
                draw_tile(screen_x, screen_y, south_wall_tex, wall_color)
        
        # Draw floor tiles (y=0 to y=height-1, x=0 to x=width-1, all walkable floor)
        for y in range(interior.height):
            for x in range(interior.width):
                screen_x, screen_y = self._world_to_screen(x, y)
                draw_tile(screen_x, screen_y, floor_tex, floor_color)
        
        # Draw characters and objects in interior using the unified rendering function
        # This reuses the same code path as exterior rendering - zone filtering handles the rest
        self._draw_trees_and_characters()
        
        # Draw death animations
        self._draw_death_animations()
        
        # Draw perception debug if enabled
        if SHOW_PERCEPTION_DEBUG:
            self._draw_perception_debug()
    
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
        
        # Only show farm cell colors for actual farmable cells
        farm_cell = self.state.get_farm_cell_state(x, y)
        if farm_cell:
            return FARM_CELL_COLORS.get(farm_cell['state'], BG_COLOR)
        
        area = self.state.get_area_at(x, y)
        if area:
            for area_def in AREAS:
                if area_def["name"] == area:
                    role = area_def.get("role")
                    # Make these area types transparent (just show background)
                    if role in ("village", "house", "farmhouse", "farm"):
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
        """Draw all occluders and characters together, sorted by Y position for proper depth.
        Objects with smaller Y (higher on screen) are drawn first, so objects
        with larger Y (lower on screen) appear in front.
        
        OPTIMIZED: Uses cached visible-only occluders to avoid iterating all world objects.
        """
        # Collect all drawable entities with their sort key (Y position)
        drawables = []
        
        # Determine what zone we're rendering
        player = self.state.player
        if self.window_viewing and self.window_viewing_interior is not None:
            rendering_zone = self.window_viewing_interior.name
        elif self.window_viewing:
            rendering_zone = None  # Looking out from inside = exterior
        elif player and player.zone is not None:
            rendering_zone = player.zone
        elif self._last_player_zone is not None:
            # Player dead - use last known zone to keep interior view
            rendering_zone = self._last_player_zone
        else:
            rendering_zone = None  # Default to exterior
        
        # OPTIMIZATION: Get visible-only occluders (cached per frame)
        # This avoids iterating through ALL trees/objects in the world
        visible_occluders = self._get_visible_occluders(rendering_zone)
        
        # Add visible occluders to drawables
        for occluder_type, pos, data, sort_y in visible_occluders:
            drawables.append(('occluder', sort_y, occluder_type, pos, data))
        
        # Add characters - only those in the same zone we're rendering
        for char in self.state.characters:
            if char.zone != rendering_zone:
                continue
            
            if rendering_zone:
                sort_y = char.prevailing_y
            else:
                sort_y = char.y
            drawables.append(('character', sort_y, char, None, None))
        
        # Add ground items - only those in the same zone we're rendering
        if hasattr(self.state, 'ground_items'):
            for ground_item in self.state.ground_items.get_items_in_zone(rendering_zone):
                # Sort ground items slightly behind things at the same Y
                # by subtracting a small amount from sort_y
                sort_y = ground_item.y - 0.1
                drawables.append(('ground_item', sort_y, ground_item, None, None))
        
        # Sort by Y position (smaller Y drawn first = behind)
        drawables.sort(key=lambda d: d[1])
        
        # Pre-calculate which characters are perceived and occluded
        # OPTIMIZATION: Only check visible occluders for occlusion
        perceived_occluded_chars = set()
        for char in self.state.characters:
            if char.zone != rendering_zone:
                continue
            is_player = char is self.state.player
            is_perceived = is_player or self._is_character_perceived(char)
            if is_perceived:
                if rendering_zone:
                    check_x, check_y = char.prevailing_x, char.prevailing_y
                else:
                    check_x, check_y = char.x, char.y
                # Use fast visible-only occlusion check
                if self._is_occluded_by_visible(check_x, check_y, visible_occluders, rendering_zone):
                    perceived_occluded_chars.add(id(char))
        
        # Reset caches
        self._character_ui_cache = []
        self._deferred_ui_cache = []
        
        # Draw in sorted order
        for dtype, sort_y, entity, pos, data in drawables:
            if dtype == 'occluder':
                self._draw_single_occluder(entity, pos, data)
            elif dtype == 'ground_item':
                self._draw_ground_item(entity)
            elif dtype == 'character':
                self._draw_single_character_sprite(entity)
                ui_info = self._character_ui_cache[-1]
                
                if id(entity) in perceived_occluded_chars:
                    self._deferred_ui_cache.append(ui_info)
                else:
                    self._draw_character_ui(ui_info)
        
        # Draw outlines for perceived occluded characters
        self._draw_perceived_outlines()
        
        # Draw deferred UI on top of everything
        for ui_info in self._deferred_ui_cache:
            self._draw_character_ui(ui_info)
    
    def _get_visible_occluders(self, zone):
        """Get only occluders within the visible area. Cached per frame.
        
        Returns list of (occluder_type, pos, data, sort_y) tuples.
        
        Uses spatial hashing for trees to avoid iterating all trees in the world.
        """
        cache_key = ('visible_occluders', zone)
        if cache_key in self._frame_cache:
            return self._frame_cache[cache_key]
        
        result = []
        
        # Visible bounds with margin for tall objects
        cull_margin = 3
        min_x = self._visible_min_x - cull_margin
        max_x = self._visible_max_x + cull_margin
        min_y = self._visible_min_y - cull_margin
        max_y = self._visible_max_y + cull_margin
        
        for occluder_type, config in OCCLUDER_CONFIG.items():
            sort_y_offset = config['sort_y_offset']
            
            # OPTIMIZED: Use spatial hash for trees
            if occluder_type == 'tree' and zone is None:
                # Build spatial hash if not exists or if trees changed (game reset)
                current_trees = self.state.interactables.trees
                if (self._tree_spatial_hash is None or 
                    getattr(self, '_tree_spatial_hash_source', None) is not current_trees):
                    self._build_tree_spatial_hash()
                
                # Only query chunks that overlap visible area
                chunk_size = self._tree_spatial_chunk_size
                chunk_min_x = int(min_x) // chunk_size
                chunk_max_x = int(max_x) // chunk_size + 1
                chunk_min_y = int(min_y) // chunk_size
                chunk_max_y = int(max_y) // chunk_size + 1
                
                for cx in range(chunk_min_x, chunk_max_x + 1):
                    for cy in range(chunk_min_y, chunk_max_y + 1):
                        chunk_trees = self._tree_spatial_hash.get((cx, cy), [])
                        for pos, data in chunk_trees:
                            x, y = pos
                            if min_x <= x <= max_x and min_y <= y <= max_y:
                                result.append((occluder_type, pos, data, y + sort_y_offset))
                                
            elif occluder_type == 'house' and zone is None:
                for house in self.state.interactables.houses.values():
                    y_start, x_start, y_end, x_end = house.bounds
                    if x_end >= min_x and x_start <= max_x and y_end >= min_y and y_start <= max_y:
                        pos = (x_start, y_end - 1)
                        result.append((occluder_type, pos, house, y_end - 1 + sort_y_offset))
            elif occluder_type == 'barrel':
                for key, obj in self.state.interactables.barrels.items():
                    if obj.zone == zone:
                        x, y = obj.x, obj.y
                        if min_x <= x <= max_x and min_y <= y <= max_y:
                            result.append((occluder_type, (x, y), obj, y + sort_y_offset))
            elif occluder_type == 'bed':
                for key, obj in self.state.interactables.beds.items():
                    if obj.zone == zone:
                        x, y = obj.x, obj.y
                        if min_x <= x <= max_x and min_y <= y <= max_y:
                            result.append((occluder_type, (x, y), obj, y + sort_y_offset))
            elif occluder_type == 'stove':
                for key, obj in self.state.interactables.stoves.items():
                    if obj.zone == zone:
                        x, y = obj.x, obj.y
                        if min_x <= x <= max_x and min_y <= y <= max_y:
                            result.append((occluder_type, (x, y), obj, y + sort_y_offset))
        
        self._frame_cache[cache_key] = result
        return result
    
    def _build_tree_spatial_hash(self):
        """Build spatial hash for trees. Called once, speeds up visible tree queries.
        
        Also stores reference to detect if trees dict changes (game reset).
        """
        self._tree_spatial_hash = {}
        self._tree_spatial_hash_source = self.state.interactables.trees  # Track source for invalidation
        chunk_size = self._tree_spatial_chunk_size
        
        for pos, data in self.state.interactables.trees.items():
            x, y = pos
            chunk_x = int(x) // chunk_size
            chunk_y = int(y) // chunk_size
            chunk_key = (chunk_x, chunk_y)
            
            if chunk_key not in self._tree_spatial_hash:
                self._tree_spatial_hash[chunk_key] = []
            self._tree_spatial_hash[chunk_key].append((pos, data))
    
    def _is_occluded_by_visible(self, char_x, char_y, visible_occluders, zone):
        """Fast occlusion check using only visible occluders.
        
        Returns True if character is occluded by any visible occluder.
        """
        for occluder_type, pos, data, sort_y in visible_occluders:
            config = OCCLUDER_CONFIG.get(occluder_type)
            if not config:
                continue
            
            # Houses need special handling
            if occluder_type == 'house':
                if zone is None:
                    house = data
                    y_start, x_start, y_end, x_end = house.bounds
                    house_center_x = (x_start + x_end) / 2
                    house_width = x_end - x_start
                    if char_y < y_end and char_y > y_start:
                        if abs(char_x - house_center_x) < house_width / 2:
                            return True
                continue
            
            obj_x, obj_y = pos
            occlusion_height = config['occlusion_height']
            occlusion_width = config['occlusion_width']
            
            # Quick distance check first
            if abs(obj_x - char_x) > 2 or abs(obj_y - char_y) > 3:
                continue
            
            obj_center_x = obj_x + 0.5
            obj_sort_y = obj_y + config['sort_y_offset']
            
            if char_y < obj_sort_y and char_y > obj_y - occlusion_height:
                if abs(char_x - obj_center_x) < occlusion_width:
                    return True
        
        return False
    
    def _is_character_perceived(self, char):
        """Check if a character is within the player's perception (vision cone or sound radius).
        
        Delegates to game_logic.can_perceive_character() for centralized perception logic.
        """
        player = self.state.player
        if not player or char is player:
            return False
        
        can_perceive, method = self.logic.can_perceive_character(player, char)
        return can_perceive
    
    def _draw_perceived_outlines(self):
        """Draw outlines for player and all perceived characters that are occluded.
        
        OPTIMIZED: Uses cached visible occluders instead of re-querying all world objects.
        """
        # Use deferred UI cache - these are the perceived+occluded characters
        if not self._deferred_ui_cache:
            return
        
        # Get the cached visible occluders (already computed this frame)
        # Determine rendering zone from first character
        if self._deferred_ui_cache:
            first_char = self._deferred_ui_cache[0]['char']
            rendering_zone = first_char.zone if hasattr(first_char, 'zone') else first_char.get('zone')
        else:
            rendering_zone = None
        
        visible_occluders = self._frame_cache.get(('visible_occluders', rendering_zone), [])
        
        # Collect outline info - find which visible occluders are hiding each character
        characters_to_outline = []
        for ui_info in self._deferred_ui_cache:
            char = ui_info['char']
            char_x = char['x']
            char_y = char['y']
            
            # Find occluders hiding this character (from visible set only)
            occluding_objects = []
            for occluder_type, pos, data, sort_y in visible_occluders:
                config = OCCLUDER_CONFIG.get(occluder_type)
                if not config:
                    continue
                
                if occluder_type == 'house':
                    house = data
                    y_start, x_start, y_end, x_end = house.bounds
                    house_center_x = (x_start + x_end) / 2
                    house_width = x_end - x_start
                    if char_y < y_end and char_y > y_start:
                        if abs(char_x - house_center_x) < house_width / 2:
                            occluding_objects.append((occluder_type, pos, config))
                else:
                    obj_x, obj_y = pos
                    if abs(obj_x - char_x) > 2 or abs(obj_y - char_y) > 3:
                        continue
                    
                    occlusion_height = config['occlusion_height']
                    occlusion_width = config['occlusion_width']
                    obj_center_x = obj_x + 0.5
                    obj_sort_y = obj_y + config['sort_y_offset']
                    
                    if char_y < obj_sort_y and char_y > obj_y - occlusion_height:
                        if abs(char_x - obj_center_x) < occlusion_width:
                            occluding_objects.append((occluder_type, pos, config))
            
            if occluding_objects:
                characters_to_outline.append((ui_info, occluding_objects))
        
        if not characters_to_outline:
            return
        
        # Create/get mask render texture (screen-sized)
        mask_w = self.canvas_width
        mask_h = self.canvas_height
        if not hasattr(self, '_occluder_mask_rt') or self._occluder_mask_rt is None:
            self._occluder_mask_rt = rl.load_render_texture(mask_w, mask_h)
        elif self._occluder_mask_rt.texture.width != mask_w or self._occluder_mask_rt.texture.height != mask_h:
            rl.unload_render_texture(self._occluder_mask_rt)
            self._occluder_mask_rt = rl.load_render_texture(mask_w, mask_h)
        
        if not hasattr(self, '_outline_rt') or self._outline_rt is None:
            self._outline_rt = rl.load_render_texture(mask_w, mask_h)
        elif self._outline_rt.texture.width != mask_w or self._outline_rt.texture.height != mask_h:
            rl.unload_render_texture(self._outline_rt)
            self._outline_rt = rl.load_render_texture(mask_w, mask_h)
        
        cell_size = self._cam_cell_size
        
        # Draw all occluding objects to mask
        rl.begin_texture_mode(self._occluder_mask_rt)
        rl.clear_background(rl.Color(0, 0, 0, 0))
        
        # Collect all unique occluding objects
        all_occluders = set()
        for ui_info, occluding_objects in characters_to_outline:
            for occluder_type, pos, config in occluding_objects:
                all_occluders.add((occluder_type, pos))
        
        for occluder_type, pos in all_occluders:
            config = OCCLUDER_CONFIG.get(occluder_type)
            if not config:
                continue
            
            ox, oy = pos
            
            # Special handling for houses
            if occluder_type == 'house':
                # Find the house at this position
                house = None
                for h in self.state.interactables.houses.values():
                    y_start, x_start, y_end, x_end = h.bounds
                    # Houses use y_end - 1 as position key (front edge)
                    if x_start == ox and y_end - 1 == oy:
                        house = h
                        break
                if not house:
                    continue
                
                bounds = house.bounds
                y_start, x_start, y_end, x_end = bounds
                house_width_cells = x_end - x_start
                house_height_cells = y_end - y_start
                
                screen_x, screen_y = self._world_to_screen(x_start, y_start)
                width = house_width_cells * cell_size
                height = house_height_cells * cell_size
                
                if house_width_cells <= 4:
                    tex = self.world_textures.get('house_s')
                    height = house_height_cells * cell_size
                else:
                    tex = self.world_textures.get('house_m') or self.world_textures.get('house_s')
                
                if tex:
                    source = rl.Rectangle(0, 0, tex.width, tex.height)
                    dest = rl.Rectangle(screen_x, screen_y, width, height)
                    rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
                else:
                    rl.draw_rectangle(int(screen_x), int(screen_y), int(width), int(height), rl.WHITE)
                continue
            
            # Special handling for beds (2 cells tall visually, use texture or solid shape for mask)
            if occluder_type == 'bed':
                screen_x, screen_y = self._world_to_screen(ox, oy)
                tex = self.world_textures.get('bed')
                
                if tex:
                    # Bed is 1 cell wide, 2 cells tall
                    bed_width = int(cell_size * 0.9)
                    bed_height = int(cell_size * 2 * 0.85)
                    blit_x = screen_x + (cell_size - bed_width) / 2
                    blit_y = screen_y + (cell_size * 0.1)
                    source = rl.Rectangle(0, 0, tex.width, tex.height)
                    dest = rl.Rectangle(blit_x, blit_y, bed_width, bed_height)
                    rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
                else:
                    padding = int(4 * self.zoom)
                    bed_width = int(cell_size - 2*padding)
                    bed_height = int(cell_size * 2 - 2*padding)
                    rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                                     bed_width, bed_height, rl.WHITE)
                continue
            
            # Special handling for stoves (use texture or solid shape for mask)
            if occluder_type == 'stove':
                screen_x, screen_y = self._world_to_screen(ox, oy)
                tex = self.world_textures.get('stove')
                
                if tex:
                    stove_size = int(cell_size * 0.8)
                    blit_x = screen_x + (cell_size - stove_size) / 2
                    blit_y = screen_y + (cell_size - stove_size) / 2
                    source = rl.Rectangle(0, 0, tex.width, tex.height)
                    dest = rl.Rectangle(blit_x, blit_y, stove_size, stove_size)
                    rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
                else:
                    padding = int(4 * self.zoom)
                    stove_size = int(cell_size - 2*padding)
                    rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                                     stove_size, stove_size, rl.WHITE)
                continue
            
            # Special handling for barrels
            if occluder_type == 'barrel':
                tex = self.world_textures.get('barrel')
                screen_x, screen_y = self._world_to_screen(ox, oy)
                if tex:
                    barrel_size = int(cell_size * 0.8)
                    blit_x = screen_x + (cell_size - barrel_size) / 2
                    blit_y = screen_y + (cell_size - barrel_size) / 2
                    source = rl.Rectangle(0, 0, tex.width, tex.height)
                    dest = rl.Rectangle(blit_x, blit_y, barrel_size, barrel_size)
                    rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
                else:
                    padding = int(5 * self.zoom)
                    rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                                     int(cell_size - 2*padding), int(cell_size - 2*padding), rl.WHITE)
                continue
            
            # Default handling for trees and other texture-based occluders
            tex = self.world_textures.get(config['texture_key'])
            if not tex:
                continue
            
            draw_height = int(cell_size * config['draw_height_mult'])
            draw_width = int(draw_height * config['draw_aspect'])
            
            screen_x, screen_y = self._world_to_screen(ox, oy)
            obj_blit_x = screen_x + cell_size / 2 - draw_width / 2
            obj_blit_y = screen_y + cell_size - draw_height
            
            # Check if animated
            if config.get('animated') and occluder_type in self.occluder_frames:
                frames = self.occluder_frames[occluder_type]
                frame_duration = config.get('frame_duration', 0.1)
                offset = (ox * 7 + oy * 13) % len(frames)
                frame_time = time.time() + offset * frame_duration
                frame_index = int(frame_time / frame_duration) % len(frames)
                source = frames[frame_index]
            else:
                source = rl.Rectangle(0, 0, tex.width, tex.height)
            
            dest = rl.Rectangle(obj_blit_x, obj_blit_y, draw_width, draw_height)
            rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
        
        rl.end_texture_mode()
        
        # Draw all character outlines to outline render texture
        rl.begin_texture_mode(self._outline_rt)
        rl.clear_background(rl.Color(0, 0, 0, 0))
        
        shader = self._init_outline_shader()
        
        for ui_info, occluding_objects in characters_to_outline:
            char = ui_info['char']
            pixel_cx = ui_info['pixel_cx']
            pixel_cy = ui_info['pixel_cy']
            sprite_width = ui_info['sprite_width']
            sprite_height = ui_info['sprite_height']
            frame_info = ui_info.get('frame_info')
            should_flip = ui_info.get('should_flip', False)
            
            if not frame_info:
                continue
            
            char_color = self._get_character_color(char)
            recolored_texture = self.sprite_manager.recolor_red_to_color(frame_info, char_color)
            if not recolored_texture:
                continue
            
            blit_x = pixel_cx - sprite_width / 2
            blit_y = pixel_cy - sprite_height / 2
            
            if should_flip:
                source = rl.Rectangle(recolored_texture.width, 0, 
                                     -recolored_texture.width, recolored_texture.height)
            else:
                source = rl.Rectangle(0, 0, recolored_texture.width, recolored_texture.height)
            
            dest = rl.Rectangle(blit_x, blit_y, sprite_width, sprite_height)
            
            texture_size = rl.ffi.new("float[2]", [recolored_texture.width, recolored_texture.height])
            outline_width = rl.ffi.new("float *", 1.0)
            rl.set_shader_value(shader, self._outline_texture_size_loc, texture_size, rl.SHADER_UNIFORM_VEC2)
            rl.set_shader_value(shader, self._outline_width_loc, outline_width, rl.SHADER_UNIFORM_FLOAT)
            
            rl.begin_shader_mode(shader)
            rl.draw_texture_pro(recolored_texture, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            rl.end_shader_mode()
        
        rl.end_texture_mode()
        
        # Composite: draw outline masked by occluders
        composite_shader = self._init_composite_shader()
        rl.set_shader_value_texture(composite_shader, self._composite_mask_loc, self._occluder_mask_rt.texture)
        
        rl.begin_shader_mode(composite_shader)
        outline_source = rl.Rectangle(0, mask_h, mask_w, -mask_h)
        outline_dest = rl.Rectangle(0, 0, mask_w, mask_h)
        rl.draw_texture_pro(self._outline_rt.texture, outline_source, outline_dest, rl.Vector2(0, 0), 0, rl.WHITE)
        rl.end_shader_mode()
    
    def _get_occluder_items(self, occluder_type, zone=None):
        """Get all items of a specific occluder type in the given zone.
        Returns dict of {(x, y): data} for the occluder type.
        For houses, returns {(x, y_end): house} using the bottom edge for sorting.
        
        Args:
            occluder_type: Type of occluder ('tree', 'barrel', 'bed', 'stove', 'house')
            zone: None for exterior world, interior name for inside a building
        
        Uses frame-level caching to avoid rebuilding dictionaries multiple times per frame.
        """
        # Fix #2: Frame-level caching - check cache first
        cache_key = (occluder_type, zone)
        if cache_key in self._frame_cache:
            return self._frame_cache[cache_key]
        
        # Build the result
        result = {}
        
        if occluder_type == 'tree':
            # Trees are always exterior (zone=None)
            if zone is None:
                result = self.state.interactables.trees
            # else result stays empty dict
        elif occluder_type == 'barrel':
            # Filter barrels by zone - keys are (x, y, zone)
            result = {(obj.x, obj.y): obj for key, obj in self.state.interactables.barrels.items()
                    if obj.zone == zone}
        elif occluder_type == 'bed':
            # Filter beds by zone - keys are (x, y, zone)
            result = {(obj.x, obj.y): obj for key, obj in self.state.interactables.beds.items()
                    if obj.zone == zone}
        elif occluder_type == 'stove':
            # Filter stoves by zone - keys are (x, y, zone)
            result = {(obj.x, obj.y): obj for key, obj in self.state.interactables.stoves.items()
                    if obj.zone == zone}
        elif occluder_type == 'house':
            # Houses are always exterior (zone=None)
            if zone is None:
                # For houses, use the bottom-left corner as the key for Y-sorting
                # Sort at y_end - 1 (front edge of house)
                houses = {}
                for house in self.state.interactables.houses.values():
                    y_start, x_start, y_end, x_end = house.bounds
                    houses[(x_start, y_end - 1)] = house
                result = houses
            # else result stays empty dict
        
        # Cache and return
        self._frame_cache[cache_key] = result
        return result
    
    def _draw_single_occluder(self, occluder_type, pos, data):
        """Draw a single occluder of any type, with optional animation."""
        config = OCCLUDER_CONFIG.get(occluder_type)
        if not config:
            return
        
        cell_size = self._cam_cell_size
        x, y = pos
        
        # Special handling for houses (multi-cell)
        if occluder_type == 'house':
            house = data
            bounds = house.bounds
            y_start, x_start, y_end, x_end = bounds
            
            house_width_cells = x_end - x_start
            house_height_cells = y_end - y_start
            
            screen_x, screen_y = self._world_to_screen(x_start, y_start)
            width = house_width_cells * cell_size
            height = house_height_cells * cell_size
            
            # Select texture based on size
            if house_width_cells <= 4:
                tex = self.world_textures.get('house_s')
            else:
                tex = self.world_textures.get('house_m') or self.world_textures.get('house_s')
            
            if tex:
                source = rl.Rectangle(0, 0, tex.width, tex.height)
                dest = rl.Rectangle(screen_x, screen_y, width, height)
                rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                rl.draw_rectangle(int(screen_x), int(screen_y), int(width), int(height), hex_to_color("#C4813D"))
            return
        
        # Special handling for beds (use texture, 2 cells tall visually)
        if occluder_type == 'bed':
            screen_x, screen_y = self._world_to_screen(x, y)
            tex = self.world_textures.get('bed')
            
            if tex:
                # Bed is 1 cell wide, 2 cells tall
                bed_width = int(cell_size * 0.9)
                bed_height = int(cell_size * 2 * 0.85)
                
                # Center horizontally in cell
                blit_x = screen_x + (cell_size - bed_width) / 2
                blit_y = screen_y + (cell_size * 0.1)  # Small offset from top
                
                source = rl.Rectangle(0, 0, tex.width, tex.height)
                dest = rl.Rectangle(blit_x, blit_y, bed_width, bed_height)
                rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                # Fallback: draw programmatically
                padding = int(4 * self.zoom)
                bed_width = int(cell_size - 2*padding)
                bed_height = int(cell_size * 2 - 2*padding)
                
                # Bed base (blue)
                rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                                 bed_width, bed_height, hex_to_color("#4169E1"))
                rl.draw_rectangle_lines(int(screen_x + padding), int(screen_y + padding),
                                       bed_width, bed_height, hex_to_color("#2a4494"))
                
                # Pillow at top
                pillow_height = int(8 * self.zoom)
                pillow_margin = int(3 * self.zoom)
                rl.draw_rectangle(int(screen_x + padding + pillow_margin),
                                 int(screen_y + padding + 2*self.zoom),
                                 bed_width - 2*pillow_margin, pillow_height,
                                 rl.WHITE)
            return
        
        # Special handling for stoves (use texture)
        if occluder_type == 'stove':
            screen_x, screen_y = self._world_to_screen(x, y)
            tex = self.world_textures.get('stove')
            
            if tex:
                stove_size = int(cell_size * 0.8)
                blit_x = screen_x + (cell_size - stove_size) / 2
                blit_y = screen_y + (cell_size - stove_size) / 2
                
                source = rl.Rectangle(0, 0, tex.width, tex.height)
                dest = rl.Rectangle(blit_x, blit_y, stove_size, stove_size)
                rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                # Fallback: draw programmatically
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
            return
        
        # Standard occluder drawing (tree, barrel, etc.)
        texture_key = config['texture_key']
        tex = self.world_textures.get(texture_key)
        
        if occluder_type == 'barrel':
            # Barrel uses texture if available, otherwise fallback
            screen_x, screen_y = self._world_to_screen(x, y)
            if tex:
                barrel_size = int(cell_size * 0.8)
                blit_x = screen_x + (cell_size - barrel_size) / 2
                blit_y = screen_y + (cell_size - barrel_size) / 2
                
                source = rl.Rectangle(0, 0, tex.width, tex.height)
                dest = rl.Rectangle(blit_x, blit_y, barrel_size, barrel_size)
                rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
            else:
                padding = int(5 * self.zoom)
                rl.draw_rectangle(int(screen_x + padding), int(screen_y + padding),
                                 int(cell_size - 2*padding), int(cell_size - 2*padding),
                                 hex_to_color("#8B4513"))
            return
        
        # Default handling for tree and other texture-based occluders
        if not tex:
            return
        
        draw_height = int(cell_size * config['draw_height_mult'])
        draw_width = int(draw_height * config['draw_aspect'])
        
        screen_x, screen_y = self._world_to_screen(x, y)
        
        # Center horizontally on cell, align bottom to cell bottom
        blit_x = screen_x + cell_size / 2 - draw_width / 2
        blit_y = screen_y + cell_size - draw_height
        
        # Check if animated
        if config.get('animated') and occluder_type in self.occluder_frames:
            frames = self.occluder_frames[occluder_type]
            frame_duration = config.get('frame_duration', 0.1)
            
            # Add position-based offset so trees don't all sync
            # Use position hash to create variation
            offset = (x * 7 + y * 13) % len(frames)
            frame_time = time.time() + offset * frame_duration
            
            frame_index = int(frame_time / frame_duration) % len(frames)
            source = frames[frame_index]
        else:
            source = rl.Rectangle(0, 0, tex.width, tex.height)
        
        dest = rl.Rectangle(blit_x, blit_y, draw_width, draw_height)
        rl.draw_texture_pro(tex, source, dest, rl.Vector2(0, 0), 0, rl.WHITE)
    
    def _get_occluding_objects(self, char_x, char_y, zone=None):
        """Get all occluders that hide a character at the given position.
        Returns list of (occluder_type, pos, config) tuples.
        
        Args:
            char_x: Character X position
            char_y: Character Y position
            zone: None for exterior, interior name for inside a building
        
        Uses position-based filtering to skip distant occluders early.
        """
        occluding = []
        
        # Maximum distance an occluder can be and still occlude a character
        # Based on max occlusion_height (trees ~2.0) + some margin
        max_occlusion_distance = 4.0
        
        for occluder_type, config in OCCLUDER_CONFIG.items():
            # Special handling for houses (multi-cell) - only in exterior
            if occluder_type == 'house':
                if zone is None:  # Houses only occlude in exterior
                    for house in self.state.interactables.houses.values():
                        y_start, x_start, y_end, x_end = house.bounds
                        house_center_x = (x_start + x_end) / 2
                        house_width = x_end - x_start
                        
                        # Character is behind house if char_y < house's bottom edge (y_end)
                        # AND character is below the walkable "behind" row (y_start)
                        # Using char_y > y_start means the top row is NOT occluded (can walk behind)
                        if char_y < y_end and char_y > y_start:
                            # Check horizontal overlap (using house's full width)
                            if abs(char_x - house_center_x) < house_width / 2:
                                # Use bottom-left as pos for consistency
                                occluding.append((occluder_type, (x_start, y_end - 1), config))
                continue
            
            occluder_items = self._get_occluder_items(occluder_type, zone=zone)
            sort_y_offset = config['sort_y_offset']
            occlusion_height = config['occlusion_height']
            occlusion_width = config['occlusion_width']
            
            for pos, data in occluder_items.items():
                obj_x, obj_y = pos
                
                # Fix #2: Early distance check - skip occluders too far away
                # This is a quick bounding box check before detailed occlusion math
                if abs(obj_x - char_x) > max_occlusion_distance:
                    continue
                if abs(obj_y - char_y) > max_occlusion_distance:
                    continue
                
                obj_center_x = obj_x + 0.5
                obj_sort_y = obj_y + sort_y_offset
                
                # Character is behind object if char_y < object's sort_y
                # AND character is within the object's visual height
                if char_y < obj_sort_y and char_y > obj_y - occlusion_height:
                    # Check horizontal overlap
                    if abs(char_x - obj_center_x) < occlusion_width:
                        occluding.append((occluder_type, pos, config))
        
        return occluding
    
    def _init_composite_shader(self):
        """Initialize shader that composites outline with tree mask."""
        if hasattr(self, '_composite_shader'):
            return self._composite_shader
        
        fragment_shader = """
#version 330
in vec2 fragTexCoord;
in vec4 fragColor;
uniform sampler2D texture0;  // Outline render texture
uniform sampler2D texture1;  // Tree mask
out vec4 finalColor;

void main() {
    vec4 outline = texture(texture0, fragTexCoord);
    // Mask texture is also a render texture, so flip Y
    vec2 maskCoord = vec2(fragTexCoord.x, 1.0 - fragTexCoord.y);
    vec4 mask = texture(texture1, maskCoord);
    
    // Only show outline where mask (tree) is opaque
    if (mask.a < 0.1) {
        discard;
    }
    
    finalColor = outline;
}
"""
        
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
        
        self._composite_shader = rl.load_shader_from_memory(vertex_shader, fragment_shader)
        self._composite_mask_loc = rl.get_shader_location(self._composite_shader, "texture1")
        
        return self._composite_shader
    
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
    
    def _draw_single_tree(self, tree, pos):
        """Draw a single tree (legacy - now use _draw_single_occluder)"""
        self._draw_single_occluder('tree', pos, tree)
    
    def _draw_trees(self):
        """Draw all trees (legacy - now handled by _draw_trees_and_characters)"""
        for pos, tree in self.state.interactables.trees.items():
            self._draw_single_occluder('tree', pos, tree)
    
    def _draw_barrels(self):
        """Draw all barrels (legacy - now handled by _draw_trees_and_characters)"""
        cell_size = self._cam_cell_size
        barrel_tex = self.world_textures.get('barrel')
        
        for barrel in self.state.interactables.barrels.values():
            x, y = barrel.x, barrel.y
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
        """Draw all beds (legacy - now handled by _draw_trees_and_characters)"""
        cell_size = self._cam_cell_size
        
        for bed in self.state.interactables.beds.values():
            x, y = bed.x, bed.y
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
        """Draw all stoves (legacy - now handled by _draw_trees_and_characters)"""
        cell_size = self._cam_cell_size
        
        for stove in self.state.interactables.stoves.values():
            x, y = stove.x, stove.y
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
    
    def _draw_ground_item(self, ground_item):
        """Draw a ground item in the world with its sprite and amount."""
        cell_size = self._cam_cell_size
        
        # Get position with visual offset
        item_x = ground_item.x + ground_item.visual_offset_x
        item_y = ground_item.y + ground_item.visual_offset_y
        
        # Convert to screen position
        screen_x, screen_y = self._world_to_screen(item_x, item_y)
        
        # Item sprite size (smaller than a full cell)
        sprite_size = int(cell_size * 0.5)
        if sprite_size < 8:
            sprite_size = 8  # Minimum size for visibility
        
        # Center the sprite on the position
        draw_x = int(screen_x - sprite_size / 2)
        draw_y = int(screen_y - sprite_size / 2)
        
        # Get texture for this item type
        texture = self.item_textures.get(ground_item.item_type)
        
        if texture and texture.id > 0:
            # Draw the sprite scaled to fit
            source_rect = rl.Rectangle(0, 0, texture.width, texture.height)
            dest_rect = rl.Rectangle(draw_x, draw_y, sprite_size, sprite_size)
            rl.draw_texture_pro(texture, source_rect, dest_rect, rl.Vector2(0, 0), 0, rl.WHITE)
        else:
            # Fallback: draw a colored square with icon
            item_info = ITEMS.get(ground_item.item_type, {})
            color = item_info.get('color', (128, 128, 128, 200))
            icon = item_info.get('icon', '?')
            
            rl.draw_rectangle(draw_x, draw_y, sprite_size, sprite_size, rl.Color(*color))
            
            icon_size = max(8, sprite_size // 2)
            icon_x = draw_x + (sprite_size - rl.measure_text(icon, icon_size)) // 2
            icon_y = draw_y + (sprite_size - icon_size) // 2
            rl.draw_text(icon, icon_x, icon_y, icon_size, rl.WHITE)
        
        # Draw amount below sprite (only if more than 1)
        if ground_item.amount > 1:
            amount_str = str(ground_item.amount)
            amount_size = max(8, int(cell_size * 0.2))
            amount_x = draw_x + (sprite_size - rl.measure_text(amount_str, amount_size)) // 2
            amount_y = draw_y + sprite_size + 1
            
            # Dark outline for readability
            rl.draw_text(amount_str, amount_x + 1, amount_y + 1, amount_size, rl.Color(0, 0, 0, 200))
            rl.draw_text(amount_str, amount_x, amount_y, amount_size, rl.WHITE)
    
    def _draw_single_character_sprite(self, char):
        """Draw a single character's sprite only (UI drawn separately on top)"""
        cell_size = self._cam_cell_size
        current_time = time.time()
        
        # Use local coords when character is in interior and:
        # 1. We're inside that interior (not window viewing), OR
        # 2. We're viewing INTO that interior through a window
        if char.zone:
            if not self.window_viewing:
                # We're inside the interior
                vis_x = char.prevailing_x
                vis_y = char.prevailing_y
            elif self.window_viewing_interior and char.zone == self.window_viewing_interior.name:
                # We're viewing into this character's interior through window
                vis_x = char.prevailing_x
                vis_y = char.prevailing_y
            else:
                vis_x = char.x
                vis_y = char.y
        else:
            vis_x = char.x
            vis_y = char.y
        
        pixel_cx, pixel_cy = self._world_to_screen(vis_x, vis_y)
        
        sprite_height = int(CHARACTER_HEIGHT * cell_size)
        sprite_width = int(CHARACTER_WIDTH * cell_size)
        
        # Check if character should flash red from being hit
        hit_flash_until = char.get('hit_flash_until', 0)
        is_hit_flashing = hit_flash_until > self.state.ticks
        
        # Get sprite frame info
        frame_info, should_flip = self.sprite_manager.get_frame(char, current_time)
        
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
                
                # Apply red tint if hit flashing, otherwise white (normal)
                tint = rl.Color(255, 100, 100, 255) if is_hit_flashing else rl.WHITE
                rl.draw_texture_pro(recolored_texture, source, dest, rl.Vector2(0, 0), 0, tint)
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
                tint = rl.Color(255, 100, 100, 255) if is_hit_flashing else rl.WHITE
                rl.draw_texture_pro(texture, source, dest, rl.Vector2(0, 0), 0, tint)
        else:
            # Fallback to colored rectangle
            char_color = self._get_character_color(char)
            blit_x = pixel_cx - sprite_width / 2
            blit_y = pixel_cy - sprite_height / 2
            if is_hit_flashing:
                rl.draw_rectangle(int(blit_x), int(blit_y), sprite_width, sprite_height, rl.Color(255, 100, 100, 255))
            else:
                rl.draw_rectangle(int(blit_x), int(blit_y), sprite_width, sprite_height, hex_to_color(char_color))
        
        # Cache UI info for drawing on top later
        if not hasattr(self, '_character_ui_cache'):
            self._character_ui_cache = []
        self._character_ui_cache.append({
            'char': char,
            'pixel_cx': pixel_cx,
            'pixel_cy': pixel_cy,
            'sprite_width': sprite_width,
            'sprite_height': sprite_height,
            'frame_info': frame_info,
            'should_flip': should_flip,
        })
    
    def _draw_character_ui(self, ui_info):
        """Draw character name and health/stamina bars (on top of everything)"""
        char = ui_info['char']
        pixel_cx = ui_info['pixel_cx']
        pixel_cy = ui_info['pixel_cy']
        sprite_width = ui_info['sprite_width']
        sprite_height = ui_info['sprite_height']
        
        # Draw first name below sprite
        first_name = char['name'].split()[0]
        text_width = rl.measure_text(first_name, 10)
        text_x = int(pixel_cx - text_width / 2)
        text_y = int(pixel_cy + sprite_height / 3.2)
        rl.draw_text(first_name, text_x, text_y, 10, rl.WHITE)
        
        # Check if we should show HP/Stamina bars
        char_name = char['name']
        health = char.get('health', 100)
        stamina = char.get('stamina', 100)
        is_sprinting = char.get('is_sprinting', False)
        current_time = time.time()
        
        # Get previous values
        prev_health = self._char_prev_health.get(char_name, health)
        prev_stamina = self._char_prev_stamina.get(char_name, stamina)
        
        # Check if values changed
        health_changed = abs(health - prev_health) > 0.1
        stamina_changed = abs(stamina - prev_stamina) > 0.1
        
        # Update previous values
        self._char_prev_health[char_name] = health
        self._char_prev_stamina[char_name] = stamina
        
        # If changed, extend the show timer
        if health_changed or stamina_changed:
            self._char_show_bars_until[char_name] = current_time + self._bar_display_duration
        
        # Determine if we should show bars
        show_bars_timer = self._char_show_bars_until.get(char_name, 0)
        is_player = (char is self.state.player)
        in_combat_mode = self.state.player.get('combat_mode', False) if self.state.player else False
        
        # For player: only show bars in combat mode (HUD shows full stats)
        # For NPCs: show bars when damaged, sprinting, or recently changed
        if is_player:
            should_show_bars = in_combat_mode
        else:
            should_show_bars = (
                is_sprinting or 
                current_time < show_bars_timer or
                health < 100
            )
        
        if should_show_bars:
            # Make bars narrower than sprite (70% of sprite width)
            bar_width = int(sprite_width * 0.7)
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
            stamina_bar_y = hp_bar_y + bar_height + bar_gap
            
            # Background
            rl.draw_rectangle(bar_x, stamina_bar_y, bar_width, bar_height, rl.Color(255, 255, 255, 25))
            
            # Foreground (stamina color - green)
            stamina_ratio = max(0, stamina) / 100.0
            stamina_fill_width = int(bar_width * stamina_ratio)
            if stamina_fill_width > 0:
                rl.draw_rectangle(bar_x, stamina_bar_y, stamina_fill_width, bar_height, 
                                 rl.Color(COLOR_STAMINA.r, COLOR_STAMINA.g, COLOR_STAMINA.b, 220))
    
    def _draw_single_character(self, char):
        """Draw a single character (legacy - calls sprite + UI)"""
        if not hasattr(self, '_character_ui_cache'):
            self._character_ui_cache = []
        self._draw_single_character_sprite(char)
        # For legacy calls, draw UI immediately
        if self._character_ui_cache:
            ui_info = self._character_ui_cache[-1]
            self._draw_character_ui(ui_info)
    
    def _draw_characters(self):
        """Draw all characters (legacy - now handled by _draw_trees_and_characters)"""
        if not hasattr(self, '_character_ui_cache'):
            self._character_ui_cache = []
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
        
        # Determine current rendering zone
        player = self.state.player
        if self.window_viewing and self.window_viewing_interior is not None:
            rendering_zone = self.window_viewing_interior.name
        elif self.window_viewing:
            rendering_zone = None
        elif player and player.zone is not None:
            rendering_zone = player.zone
        elif self._last_player_zone is not None:
            rendering_zone = self._last_player_zone
        else:
            rendering_zone = None
        
        for anim in self.state.death_animations:
            # Only draw death animations in the current rendering zone
            anim_zone = anim.get('zone')
            if anim_zone != rendering_zone:
                continue
            
            # Coords are already in correct space (local for interior, world for exterior)
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
    
    def _get_vision_obstacles_for_rendering(self, zone):
        """Get obstacles that block vision for visualization.
        
        Args:
            zone: Interior name or None for exterior
            
        Returns:
            List of (x, y, radius) tuples for obstacles
        """
        obstacles = []
        
        if zone is None:
            # Exterior - trees block vision
            for pos in self.state.interactables.trees:
                x, y = pos
                obstacles.append((x + 0.5, y + 0.5, 0.4))
            
            # House walls
            for house in self.state.interactables.houses.values():
                y_start, x_start, y_end, x_end = house.bounds
                for hx in range(x_start, x_end):
                    obstacles.append((hx + 0.5, y_start + 0.5, 0.5))
                    obstacles.append((hx + 0.5, y_end - 0.5, 0.5))
                for hy in range(y_start, y_end):
                    obstacles.append((x_start + 0.5, hy + 0.5, 0.5))
                    obstacles.append((x_end - 0.5, hy + 0.5, 0.5))
        else:
            # Interior - stoves block vision
            interior = self.state.interiors.get_interior(zone)
            if interior:
                for stove in self.state.interactables.stoves.values():
                    if stove.zone != zone:
                        continue
                    # Stove is in interior coords
                    obstacles.append((stove.x + 0.5, stove.y + 0.5, 0.4))
        
        return obstacles
    
    def _get_shadow_distance(self, from_x, from_y, angle, max_range, obstacles):
        """Get distance to first obstacle along a ray.
        
        Args:
            from_x, from_y: Ray origin
            angle: Ray angle in radians
            max_range: Maximum ray distance
            obstacles: List of (x, y, radius) tuples
            
        Returns:
            Distance to first obstacle, or max_range if no hit
        """
        # Ray direction
        ray_dx = math.cos(angle)
        ray_dy = -math.sin(angle)  # Negative because screen Y is inverted
        
        # Ray end point
        to_x = from_x + ray_dx * max_range
        to_y = from_y + ray_dy * max_range
        
        min_dist = max_range
        
        for ox, oy, radius in obstacles:
            # Skip if obstacle is at origin
            if abs(ox - from_x) < 0.3 and abs(oy - from_y) < 0.3:
                continue
            
            # Line-circle intersection
            dx = to_x - from_x
            dy = to_y - from_y
            fx = from_x - ox
            fy = from_y - oy
            
            a = dx * dx + dy * dy
            if a < 0.0001:
                continue
            b = 2 * (fx * dx + fy * dy)
            c = fx * fx + fy * fy - radius * radius
            
            discriminant = b * b - 4 * a * c
            
            if discriminant >= 0:
                discriminant = math.sqrt(discriminant)
                t1 = (-b - discriminant) / (2 * a)
                
                if 0 < t1 < 1:
                    hit_dist = t1 * max_range
                    if hit_dist < min_dist:
                        min_dist = hit_dist
        
        return min_dist
    
    def _check_line_of_sight_gui(self, from_x, from_y, to_x, to_y, obstacles):
        """Check if there's clear line of sight between two points.
        
        Args:
            from_x, from_y: Observer position
            to_x, to_y: Target position
            obstacles: List of (x, y, radius) obstacle tuples
            
        Returns:
            True if line of sight is clear, False if blocked
        """
        for ox, oy, radius in obstacles:
            # Skip if obstacle is at observer or target position
            if abs(ox - from_x) < 0.3 and abs(oy - from_y) < 0.3:
                continue
            if abs(ox - to_x) < 0.3 and abs(oy - to_y) < 0.3:
                continue
            
            # Line-circle intersection check
            dx = to_x - from_x
            dy = to_y - from_y
            fx = from_x - ox
            fy = from_y - oy
            
            a = dx * dx + dy * dy
            if a < 0.0001:
                continue
            b = 2 * (fx * dx + fy * dy)
            c = fx * fx + fy * fy - radius * radius
            
            discriminant = b * b - 4 * a * c
            
            if discriminant >= 0:
                discriminant = math.sqrt(discriminant)
                t1 = (-b - discriminant) / (2 * a)
                t2 = (-b + discriminant) / (2 * a)
                
                if 0 < t1 < 1 or 0 < t2 < 1:
                    return False  # Blocked
        
        return True  # Clear line of sight

    def _draw_perception_debug(self):
        """Draw perception debug visualization"""
        cell_size = self._cam_cell_size
        player = self.state.player
        
        # Determine what zone we're rendering
        # If window_viewing into interior: render that interior (local coords)
        # If window_viewing out: render exterior (world coords)
        # If player in interior: render interior (local coords)
        # Otherwise: render exterior (world coords)
        if self.window_viewing and self.window_viewing_interior is not None:
            rendering_zone = self.window_viewing_interior.name
            use_local_coords = True
        elif self.window_viewing:
            rendering_zone = None  # Exterior
            use_local_coords = False
        elif player and player.zone:
            rendering_zone = player.zone  # Same interior as player
            use_local_coords = True
        elif self._last_player_zone is not None:
            # Player dead - use last known zone
            rendering_zone = self._last_player_zone
            use_local_coords = True
        else:
            rendering_zone = None  # Exterior
            use_local_coords = False
        
        for char in self.state.characters:
            if char.get('health', 100) <= 0:
                continue
            
            # Only draw characters in the rendering zone
            if char.zone != rendering_zone:
                continue
            
            # Use local coords when rendering interior, world coords otherwise
            if use_local_coords:
                vis_x = char.prevailing_x
                vis_y = char.prevailing_y
            else:
                vis_x = char.x
                vis_y = char.y
            
            screen_x, screen_y = self._world_to_screen(vis_x, vis_y)
            
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
            
            # Get obstacles for shadow casting
            obstacles = self._get_vision_obstacles_for_rendering(rendering_zone)
            
            # Draw vision cone as a series of triangles with shadow casting
            num_segments = 20
            for i in range(num_segments):
                t1 = i / num_segments
                t2 = (i + 1) / num_segments
                a1 = angle1 + t1 * (angle2 - angle1)
                a2 = angle1 + t2 * (angle2 - angle1)
                
                # Get shadow distances for each edge
                dist1 = self._get_shadow_distance(vis_x, vis_y, a1, VISION_RANGE, obstacles)
                dist2 = self._get_shadow_distance(vis_x, vis_y, a2, VISION_RANGE, obstacles)
                
                r1_pixels = int(dist1 * cell_size)
                r2_pixels = int(dist2 * cell_size)
                
                p1_x = screen_x + math.cos(a1) * r1_pixels
                p1_y = screen_y - math.sin(a1) * r1_pixels
                p2_x = screen_x + math.cos(a2) * r2_pixels
                p2_y = screen_y - math.sin(a2) * r2_pixels
                
                rl.draw_triangle(
                    rl.Vector2(screen_x, screen_y),
                    rl.Vector2(p1_x, p1_y),
                    rl.Vector2(p2_x, p2_y),
                    rl.Color(255, 100, 100, 30)
                )
        
        # Draw player's vision cone through window when window viewing
        if self.window_viewing and self.window_viewing_window and player:
            window = self.window_viewing_window
            
            # Determine cone origin based on viewing direction
            if self.window_viewing_interior is not None:
                # Looking in from outside - cone from window's interior position
                cone_x = window.interior_x + 0.5
                cone_y = window.interior_y + 0.5
            else:
                # Looking out from inside - cone from window's world position (on the wall)
                cone_x = window.world_x
                cone_y = window.world_y
            
            screen_x, screen_y = self._world_to_screen(cone_x, cone_y)
            
            # Vision cone only (no sound through windows)
            vision_radius_pixels = int(VISION_RANGE * cell_size)
            
            # Use window's facing direction
            # When looking OUT: use facing directly
            # When looking IN: invert direction (you're on the outside looking in)
            window_facing_vectors = {
                'north': (0, -1),
                'south': (0, 1),
                'east': (1, 0),
                'west': (-1, 0),
            }
            face_x, face_y = window_facing_vectors.get(window.facing, (0, 1))
            
            # Invert when looking in from outside
            if self.window_viewing_interior is not None:
                face_x = -face_x
                face_y = -face_y
            
            facing_angle = math.atan2(-face_y, face_x)
            half_angle = math.radians(VISION_CONE_ANGLE / 2)
            
            angle1 = facing_angle - half_angle
            angle2 = facing_angle + half_angle
            
            # Get obstacles for shadow casting (in the zone we're viewing into)
            target_zone = self.window_viewing_interior.name if self.window_viewing_interior else None
            window_obstacles = self._get_vision_obstacles_for_rendering(target_zone)
            
            # Draw vision cone as a series of triangles (different color for window view)
            num_segments = 20
            for i in range(num_segments):
                t1 = i / num_segments
                t2 = (i + 1) / num_segments
                a1 = angle1 + t1 * (angle2 - angle1)
                a2 = angle1 + t2 * (angle2 - angle1)
                
                # Get shadow distances
                dist1 = self._get_shadow_distance(cone_x, cone_y, a1, VISION_RANGE, window_obstacles)
                dist2 = self._get_shadow_distance(cone_x, cone_y, a2, VISION_RANGE, window_obstacles)
                
                r1_pixels = int(dist1 * cell_size)
                r2_pixels = int(dist2 * cell_size)
                
                p1_x = screen_x + math.cos(a1) * r1_pixels
                p1_y = screen_y - math.sin(a1) * r1_pixels
                p2_x = screen_x + math.cos(a2) * r2_pixels
                p2_y = screen_y - math.sin(a2) * r2_pixels
                
                rl.draw_triangle(
                    rl.Vector2(screen_x, screen_y),
                    rl.Vector2(p1_x, p1_y),
                    rl.Vector2(p2_x, p2_y),
                    rl.Color(100, 100, 255, 30)  # Blue tint for window vision
                )
        
        # Draw NPC cross-zone window vision cones
        self._draw_cross_zone_window_cones(rendering_zone, use_local_coords, cell_size)

    def _draw_cross_zone_window_cones(self, rendering_zone, use_local_coords, cell_size):
        """Draw vision cones for NPCs looking through windows from the other zone."""
        vision_radius_pixels = int(VISION_RANGE * cell_size)
        
        # Helper to check if character is facing a direction
        def is_facing_direction(char, direction):
            facing = char.get('facing', 'down')
            direction_facings = {
                'north': ('up', 'up-left', 'up-right'),
                'south': ('down', 'down-left', 'down-right'),
                'east': ('right', 'up-right', 'down-right'),
                'west': ('left', 'up-left', 'down-left'),
            }
            return facing in direction_facings.get(direction, ())
        
        opposite_dir = {'north': 'south', 'south': 'north', 'east': 'west', 'west': 'east'}
        window_facing_vectors = {
            'north': (0, -1),
            'south': (0, 1),
            'east': (1, 0),
            'west': (-1, 0),
        }
        
        if rendering_zone is not None:
            # Rendering an interior - draw cones for exterior NPCs looking in
            interior = self.state.interiors.get_interior(rendering_zone)
            if interior:
                for char in self.state.characters:
                    if char.get('health', 100) <= 0:
                        continue
                    if char.zone is not None:  # Only exterior characters
                        continue
                    
                    # Check each window
                    for window in interior.windows:
                        if window.is_character_near_exterior(char.x, char.y):
                            # Must be facing into the building
                            inward_dir = opposite_dir.get(window.facing)
                            if is_facing_direction(char, inward_dir):
                                # Draw cone from window's interior position
                                cone_x = window.interior_x + 0.5
                                cone_y = window.interior_y + 0.5
                                screen_x, screen_y = self._world_to_screen(cone_x, cone_y)
                                
                                # Direction is inverted (looking into building)
                                face_x, face_y = window_facing_vectors.get(window.facing, (0, 1))
                                face_x, face_y = -face_x, -face_y
                                
                                # Get interior obstacles for shadow casting
                                interior_obstacles = self._get_vision_obstacles_for_rendering(rendering_zone)
                                
                                self._draw_vision_cone_triangles(
                                    screen_x, screen_y, face_x, face_y,
                                    vision_radius_pixels, rl.Color(100, 255, 100, 30),
                                    world_x=cone_x, world_y=cone_y, obstacles=interior_obstacles, cell_size=cell_size
                                )
        else:
            # Rendering exterior - draw cones for interior NPCs looking out
            for house in self.state.interactables.get_all_houses():
                interior = house.interior
                if not interior:
                    continue
                
                for char in self.state.characters:
                    if char.get('health', 100) <= 0:
                        continue
                    if char.zone != interior.name:  # Only characters in this interior
                        continue
                    
                    # Check each window
                    for window in interior.windows:
                        if window.is_character_near(char.prevailing_x, char.prevailing_y):
                            # Must be facing outward (same as window direction)
                            if is_facing_direction(char, window.facing):
                                # Draw cone from window's world position
                                cone_x = window.world_x
                                cone_y = window.world_y
                                screen_x, screen_y = self._world_to_screen(cone_x, cone_y)
                                
                                face_x, face_y = window_facing_vectors.get(window.facing, (0, 1))
                                
                                # Get exterior obstacles for shadow casting
                                exterior_obstacles = self._get_vision_obstacles_for_rendering(None)
                                
                                self._draw_vision_cone_triangles(
                                    screen_x, screen_y, face_x, face_y,
                                    vision_radius_pixels, rl.Color(100, 255, 100, 30),
                                    world_x=cone_x, world_y=cone_y, obstacles=exterior_obstacles, cell_size=cell_size
                                )
    
    def _draw_vision_cone_triangles(self, screen_x, screen_y, face_x, face_y, radius_pixels, color, world_x=None, world_y=None, obstacles=None, cell_size=None):
        """Helper to draw a vision cone as triangles with optional shadow casting.
        
        Args:
            screen_x, screen_y: Screen position of cone origin
            face_x, face_y: Facing direction vector
            radius_pixels: Max cone radius in pixels
            color: Fill color
            world_x, world_y: World position for shadow casting (optional)
            obstacles: List of obstacles for shadow casting (optional)
            cell_size: Cell size for converting shadow distances to pixels (optional)
        """
        facing_angle = math.atan2(-face_y, face_x)
        half_angle = math.radians(VISION_CONE_ANGLE / 2)
        
        angle1 = facing_angle - half_angle
        angle2 = facing_angle + half_angle
        
        num_segments = 20
        for i in range(num_segments):
            t1 = i / num_segments
            t2 = (i + 1) / num_segments
            a1 = angle1 + t1 * (angle2 - angle1)
            a2 = angle1 + t2 * (angle2 - angle1)
            
            # Use shadow distances if provided
            if obstacles is not None and world_x is not None and cell_size is not None:
                dist1 = self._get_shadow_distance(world_x, world_y, a1, VISION_RANGE, obstacles)
                dist2 = self._get_shadow_distance(world_x, world_y, a2, VISION_RANGE, obstacles)
                r1_pixels = int(dist1 * cell_size)
                r2_pixels = int(dist2 * cell_size)
            else:
                r1_pixels = radius_pixels
                r2_pixels = radius_pixels
            
            p1_x = screen_x + math.cos(a1) * r1_pixels
            p1_y = screen_y - math.sin(a1) * r1_pixels
            p2_x = screen_x + math.cos(a2) * r2_pixels
            p2_y = screen_y - math.sin(a2) * r2_pixels
            
            rl.draw_triangle(
                rl.Vector2(screen_x, screen_y),
                rl.Vector2(p1_x, p1_y),
                rl.Vector2(p2_x, p2_y),
                color
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
        # TODO: Hotkey slots will be implemented later (requires conditions not yet in game)
        # self._draw_item_slots(player)
        
        # Top-right: Location and time
        self._draw_location_time()
        
        # Bottom-right: Unified E interaction hint
        self._draw_interact_hint(player)
        
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
    
    def _draw_interact_hint(self, player):
        """Draw unified interaction hint based on what player can interact with"""
        x = self.canvas_width - HUD_MARGIN
        y = self.canvas_height - HUD_MARGIN - 100
        
        # If window viewing, show stop viewing action
        if self.window_viewing:
            self._draw_action_prompt(x, y, 'E', 'Stop Viewing')
            return
        
        # Get what player can interact with
        context = self._get_player_context(player)
        
        if not context:
            return
        
        # Get the first action (whether E or -)
        actions = context.get('actions', [])
        if not actions:
            return
        
        action = actions[0]
        
        # Draw target type (small, dim)
        type_str = context['type'].upper()
        type_width = rl.measure_text(type_str, HUD_FONT_SIZE_SMALL)
        rl.draw_text(type_str, x - type_width, y, HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)
        
        # Draw target name (larger, brighter)
        name = context['name']
        name_width = rl.measure_text(name, HUD_FONT_SIZE_LARGE)
        rl.draw_text(name, x - name_width, y + 14, HUD_FONT_SIZE_LARGE, COLOR_TEXT_BRIGHT)
        
        # Draw action prompt (E for interactable, - for info only)
        self._draw_action_prompt(x, y + 40, action['key'], action['label'])
    
    def _draw_action_prompt(self, right_x, y, key, label):
        """Draw a single action prompt like [E] Interact"""
        is_controller = self.input.gamepad_connected
        
        # Map keyboard keys to controller buttons
        controller_map = {
            'E': 'A',     # Primary interact
            'Q': 'Y',     # Eat
            'C': 'B',     # Make camp
            'LMB': 'RT',  # Attack
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
        """Determine what the player can interact with.
        
        Returns the nearest interactable in priority order, with 'E' as the 
        unified interact key for everything. Requires player to be facing
        the target and within INTERACT_DISTANCE.
        
        Priority order (doors first so you can escape combat):
        1. Door (enter/exit) - essential for escaping
        2. NPC (dialogue)
        3. Window (look through)
        4. Stove (bake bread)
        5. Campfire (bake bread)
        6. Barrel (storage access)
        7. Bed (sleep - not implemented)
        8. Tree (chop - not implemented)
        """
        # Check for door FIRST (entering/exiting buildings) - allows escaping combat
        house = self.state.get_adjacent_door(player)
        if house:
            if player.zone is None:
                # Outside - can enter
                return {
                    'type': 'Door',
                    'name': house.name,
                    'actions': [{'key': 'E', 'label': 'Enter'}]
                }
            else:
                # Inside - can exit
                return {
                    'type': 'Door',
                    'name': 'Exit',
                    'actions': [{'key': 'E', 'label': 'Exit Building'}]
                }
        
        # Check for adjacent characters (NPCs) - must be in same zone and facing them
        nearest_npc = None
        nearest_npc_dist = float('inf')
        
        for char in self.state.characters:
            if char == player:
                continue
            if char.get('health', 100) <= 0:
                continue
            # Must be in same zone to interact
            if char.zone != player.zone:
                continue
            
            # Use prevailing coords when in interior
            if player.zone:
                px, py = player.prevailing_x, player.prevailing_y
                cx, cy = char.prevailing_x, char.prevailing_y
            else:
                px, py = player.x, player.y
                cx, cy = char.x, char.y
            
            dist = math.sqrt((px - cx)**2 + (py - cy)**2)
            
            # Must be within interact distance AND player facing them
            if dist <= INTERACT_DISTANCE and dist < nearest_npc_dist:
                if self._is_facing_position(player, cx, cy, player.zone):
                    nearest_npc = char
                    nearest_npc_dist = dist
        
        if nearest_npc:
            job = nearest_npc.get('job')
            return {
                'type': job if job else 'Character',
                'name': nearest_npc.get_display_name(),
                'actions': [{'key': 'E', 'label': 'Talk'}]
            }
        
        # Check for window (inside looking out, or outside looking in)
        if player.zone is not None:
            # Inside - check if near interior window
            interior = self.state.interiors.get_interior(player.zone)
            if interior:
                for window in interior.windows:
                    if window.is_character_near(player.prevailing_x, player.prevailing_y, threshold=1.0):
                        return {
                            'type': 'Window',
                            'name': f'Window ({window.facing})',
                            'actions': [{'key': 'E', 'label': 'Look Outside'}]
                        }
        else:
            # Outside - check if near exterior window AND facing it
            for house in self.state.interactables.get_all_houses():
                interior = house.interior
                if not interior:
                    continue
                for window in interior.windows:
                    if window.is_character_near_exterior(player.x, player.y, threshold=1.0):
                        # Must be facing toward the window
                        if self._is_player_facing_window(player, window):
                            return {
                                'type': 'Window',
                                'name': f'{house.name} Window',
                                'actions': [{'key': 'E', 'label': 'Look Inside'}]
                            }
        
        # Check for adjacent stove (must be facing it)
        stove = self.state.interactables.get_adjacent_stove(player)
        if stove:
            # Check if facing the stove - use local coords for interior
            if self._is_facing_position(player, stove.x + 0.5, stove.y + 0.5, stove.zone):
                if stove.can_use(player):
                    return {
                        'type': 'Stove',
                        'name': stove.name,
                        'actions': [{'key': 'E', 'label': 'Bake Bread'}]
                    }
                else:
                    return {
                        'type': 'Stove',
                        'name': stove.name,
                        'actions': [{'key': '-', 'label': 'Not your stove'}]
                    }
        
        # Check for adjacent campfire (camps are stored on characters as camp_position)
        for other_char in self.state.characters:
            camp_pos = other_char.get('camp_position')
            if camp_pos and self.state.interactables.is_adjacent_to_camp(player, camp_pos):
                # Check if facing the campfire - exterior so no zone
                if self._is_facing_position(player, camp_pos[0] + 0.5, camp_pos[1] + 0.5, None):
                    owner_name = other_char.get_display_name()
                    return {
                        'type': 'Campfire',
                        'name': f"{owner_name}'s Campfire",
                        'actions': [{'key': 'E', 'label': 'Bake Bread'}]
                    }
        
        # Check for adjacent barrel (must be facing it)
        for barrel in self.state.interactables.barrels.values():
            if barrel.is_adjacent(player):
                # Check if facing the barrel - use local coords if interior
                if barrel.zone is not None:
                    target_x, target_y = barrel.x + 0.5, barrel.y + 0.5
                else:
                    target_x, target_y = barrel.x + 0.5, barrel.y + 0.5
                if self._is_facing_position(player, target_x, target_y, barrel.zone):
                    if barrel.can_use(player):
                        wheat_count = barrel.get_wheat()
                        if wheat_count > 0:
                            return {
                                'type': 'Barrel',
                                'name': barrel.name,
                                'actions': [{'key': 'E', 'label': f'Take Wheat ({wheat_count})'}]
                            }
                        else:
                            return {
                                'type': 'Barrel',
                                'name': barrel.name,
                                'actions': [{'key': '-', 'label': 'Empty'}]
                            }
                    else:
                        return {
                            'type': 'Barrel',
                            'name': barrel.name,
                            'actions': [{'key': '-', 'label': 'Not your barrel'}]
                        }
        
        # Check for adjacent bed (must be facing it)
        for bed in self.state.interactables.beds.values():
            if bed.is_adjacent(player):
                # Check if facing the bed - use local coords for interior
                if self._is_facing_position(player, bed.x + 0.5, bed.y + 0.5, bed.zone):
                    is_owned = bed.is_owned_by(player.name)
                    if is_owned or not bed.is_owned():
                        return {
                            'type': 'Bed',
                            'name': bed.name,
                            'actions': [{'key': '-', 'label': 'Sleep (not implemented)'}]
                        }
                    else:
                        return {
                            'type': 'Bed',
                            'name': bed.name,
                            'actions': [{'key': '-', 'label': 'Not your bed'}]
                        }
        
        # Check for adjacent tree (must be facing it)
        for pos, tree in self.state.interactables.trees.items():
            if tree.is_adjacent(player):
                # Check if facing the tree - exterior so no zone
                if self._is_facing_position(player, tree.x + 0.5, tree.y + 0.5, None):
                    return {
                        'type': 'Tree',
                        'name': 'Tree',
                        'actions': [{'key': '-', 'label': 'Shake (not implemented)'}]
                    }
        
        return None
    
    def _is_facing_position(self, player, target_x, target_y, target_zone=None):
        """Check if player is roughly facing toward a target position.
        
        Uses a generous 90-degree cone in the facing direction.
        
        For objects that passed is_adjacent, they're in the same zone as player.
        Just use player.zone to determine coordinate system.
        
        Args:
            player: Player character
            target_x: Target X in local coords (object.x + 0.5)
            target_y: Target Y in local coords (object.y + 0.5)
            target_zone: Unused, kept for compatibility
        """
        # Use player.zone to determine coordinate system
        # Objects that passed is_adjacent are guaranteed to be in same zone
        if player.zone is not None:
            # Interior - use local/prevailing coords
            px, py = player.prevailing_x, player.prevailing_y
        else:
            # Exterior - use world coords
            px, py = player.x, player.y
        
        # Direction to target
        dx = target_x - px
        dy = target_y - py
        
        if abs(dx) < 0.01 and abs(dy) < 0.01:
            return True  # On top of target, always valid
        
        # Get facing direction vector
        facing = player.get('facing', 'down')
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
        fx, fy = facing_vectors.get(facing, (0, 1))
        
        # Normalize direction to target
        dist = math.sqrt(dx*dx + dy*dy)
        dx /= dist
        dy /= dist
        
        # Dot product gives cosine of angle between vectors
        # cos(45°) ≈ 0.707, cos(53°) ≈ 0.6, cos(60°) = 0.5, cos(90°) = 0
        dot = dx * fx + dy * fy
        
        # Require ~53 degree cone (dot > 0.6) for tighter targeting
        return dot > 0.6
    
    def _is_player_facing_window(self, player, window):
        """Check if player is facing toward a window from outside."""
        facing = player.get('facing', 'down')
        required_facings = {
            'north': ('down', 'down-left', 'down-right'),
            'south': ('up', 'up-left', 'up-right'),
            'east': ('left', 'up-left', 'down-left'),
            'west': ('right', 'up-right', 'down-right'),
        }
        return facing in required_facings.get(window.facing, ())
    
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

# Entry point for testing
if __name__ == "__main__":
    app = BoardGUI()
    app.run()