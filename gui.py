# gui.py - Pure GUI: rendering and input handling only (Pygame version)
"""
This module contains ONLY:
- Pygame setup and rendering
- Input handling

It does NOT contain:
- Game logic (that's in game_logic.py)
- Game state (that's in game_state.py)
"""

# IMPORTANT: Set multiprocessing start method BEFORE any other imports
# This is required on macOS to avoid pygame/tkinter conflicts
import multiprocessing
import sys
if sys.platform == 'darwin':
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        pass  # Already set

import time
import math
import pygame
import pygame.freetype
from constants import (
    CELL_SIZE, UPDATE_INTERVAL,
    FARM_CELL_COLORS, JOB_TIERS,
    BG_COLOR, GRID_COLOR, ROAD_COLOR,
    TICKS_PER_DAY, TICKS_PER_YEAR, SLEEP_START_FRACTION,
    MOVEMENT_SPEED, CHARACTER_WIDTH, CHARACTER_HEIGHT,
    DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, ZOOM_SPEED, SPRINT_SPEED,
    SOUND_RADIUS, VISION_RANGE, VISION_CONE_ANGLE, SHOW_PERCEPTION_DEBUG
)
from scenario_world import AREAS, BARRELS, BEDS, VILLAGE_NAME, SIZE, ROADS
from game_state import GameState
from game_logic import GameLogic
from player_controller import PlayerController
from debug_window import DebugWindow
from sprites import get_sprite_manager
import os


def hex_to_rgb(hex_color):
    """Convert hex color string to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))



class BoardGUI:
    """
    Pure GUI class - handles only rendering and input.
    
    This class:
    - Creates and manages Pygame display
    - Renders the game state
    - Handles keyboard/mouse input
    - Delegates all game logic to GameLogic
    - Does NOT modify game state directly
    """
    
    # Color constants (converted to RGB)
    BG_COLOR_RGB = hex_to_rgb(BG_COLOR)
    GRID_COLOR_RGB = hex_to_rgb(GRID_COLOR)
    
    def __init__(self, root=None):
        """Initialize pygame and game components. root parameter kept for compatibility but ignored."""
        pygame.init()
        pygame.freetype.init()
        
        # Create game state and logic
        self.state = GameState()
        self.logic = GameLogic(self.state)
        self.player_controller = PlayerController(self.state, self.logic)
        
        # Create debug window (separate Tkinter window) - pass logic for skip year
        self.debug_window = DebugWindow(self.state, self.logic)
        
        # Get screen dimensions and calculate window size
        # Window is half screen width with 16:9 aspect ratio
        display_info = pygame.display.Info()
        screen_width = display_info.current_w
        screen_height = display_info.current_h
        
        self.window_width = screen_width // 2
        self.window_height = int(self.window_width * 9 / 16)
        
        # Ensure window fits on screen
        if self.window_height > screen_height - 100:  # Leave room for taskbar
            self.window_height = screen_height - 100
            self.window_width = int(self.window_height * 16 / 9)
        
        self.canvas_width = self.window_width
        self.canvas_height = self.window_height
        
        # Create resizable window
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height),
            pygame.RESIZABLE
        )
        pygame.display.set_caption(f"{VILLAGE_NAME} - Village Simulation")
        
        # Load fonts
        self.font_tiny = pygame.freetype.SysFont('Arial', 7)
        self.font_barrel = pygame.freetype.SysFont('Arial', 14, bold=True)
        
        # Initialize sprite manager - look for sprites in same directory as gui.py
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.sprite_manager = get_sprite_manager(script_dir)
        self.sprite_manager.load_sprites()
        
        # Load world sprites (trees, roads, barrels, campfires, houses)
        self._load_world_sprites(script_dir)
        
        # Timing
        self.clock = pygame.time.Clock()
        self.last_tick_time = pygame.time.get_ticks()
        self.last_frame_time = pygame.time.get_ticks()  # For delta time calculation
        
        # Player movement state - which keys are currently held
        self.player_moving = False
        
        # Camera state - center on player if exists
        if self.state.player:
            self.camera_x = self.state.player['x']
            self.camera_y = self.state.player['y']
        else:
            self.camera_x = SIZE / 2
            self.camera_y = SIZE / 2
        self.zoom = DEFAULT_ZOOM
        self.camera_following_player = True  # Whether camera follows player
        self.camera_dragging = False  # True while actively dragging
        self.drag_start_mouse = None  # Mouse position when drag started
        self.drag_start_camera = None  # Camera position when drag started
        
        # Pre-compute road set for fast lookup
        self._road_set = set(tuple(r) for r in ROADS)
        
        # Running state
        self.running = True
    
    def _load_world_sprites(self, sprite_dir):
        """Load world sprites (trees, roads, barrels, campfires, houses)."""
        self.world_sprites = {}
        
        sprite_files = {
            'tree': 'Tree.png',
            'road': 'Road.png',
            'barrel': 'Barrel.png',
            'campfire': 'Campfire.png',
            'house_s': 'House_S.png',
            'house_m': 'House_M.png',
            'grass': 'Grass_BG.png',
        }
        
        for name, filename in sprite_files.items():
            filepath = os.path.join(sprite_dir, 'sprites', filename)
            if os.path.exists(filepath):
                img = pygame.image.load(filepath)
                if pygame.display.get_surface() is not None:
                    img = img.convert_alpha()
                self.world_sprites[name] = img
            else:
                print(f"Warning: World sprite not found: {filepath}")
                self.world_sprites[name] = None
        
        # Extract campfire frames (192x32 = 6 frames of 32x32)
        campfire_sheet = self.world_sprites.get('campfire')
        if campfire_sheet:
            self.campfire_frames = []
            frame_width = 32
            frame_height = 32
            num_frames = campfire_sheet.get_width() // frame_width
            for i in range(num_frames):
                frame = pygame.Surface((frame_width, frame_height), pygame.SRCALPHA)
                frame.blit(campfire_sheet, (0, 0), (i * frame_width, 0, frame_width, frame_height))
                self.campfire_frames.append(frame)
        else:
            self.campfire_frames = []
    
    def run(self):
        """Main game loop"""
        while self.running:
            self._handle_events()
            self._game_loop()
            self._render_frame()
            
            # Update debug window (Tkinter) with status info
            if self.debug_window.is_open():
                # Build status string for debug window
                player = self.state.player
                if player:
                    player_food = player.get_item('wheat')
                    player_money = player.get_item('money')
                    status = f"Pos:({player.x:.1f},{player.y:.1f}) Wheat:{player_food} ${player_money} HP:{player.health} | Zoom:{self.zoom:.1f}x | {'Follow' if self.camera_following_player else 'Free'}"
                else:
                    status = f"No player | Zoom:{self.zoom:.1f}x"
                self.debug_window.set_status(status)
                self.debug_window.update()
            
            self.clock.tick(60)  # Cap at 60 FPS
        
        # Cleanup
        self.debug_window.close()
        pygame.quit()
    
    def _handle_events(self):
        """Handle all pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_click(event)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_release(event)
            
            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event)
            
            elif event.type == pygame.MOUSEWHEEL:
                self._handle_mouse_wheel(event)
            
            elif event.type == pygame.VIDEORESIZE:
                self._handle_resize(event)
        
        # Handle continuous player movement (check held keys every frame)
        self._handle_continuous_movement()
    
    def _handle_continuous_movement(self):
        """Handle continuous player movement (WASD) and camera panning (arrow keys)"""
        keys = pygame.key.get_pressed()
        
        # === UPDATE PLAYER FACING BASED ON MOUSE ===
        self._update_player_facing_to_mouse()
        
        # === PLAYER MOVEMENT (WASD only) ===
        dx = 0
        dy = 0
        
        # Vertical
        if keys[pygame.K_w]:
            dy = -1
        elif keys[pygame.K_s]:
            dy = 1
        
        # Horizontal
        if keys[pygame.K_a]:
            dx = -1
        elif keys[pygame.K_d]:
            dx = 1
        
        # Check if sprinting (shift held)
        sprinting = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        
        if dx != 0 or dy != 0:
            # Check if backpedaling (moving opposite to facing direction)
            movement_dot = self._update_backpedal_state(dx, dy)
            # Set player velocity via controller (don't update facing - mouse controls that)
            self._handle_movement_no_facing(dx, dy, sprinting, movement_dot)
            self.player_moving = True
        else:
            # No movement keys held - stop player
            if self.player_moving:
                self.player_controller.stop_movement()
                self.player_moving = False
            # Clear backpedal state
            player = self.state.player
            if player:
                player['is_backpedaling'] = False
        
        # === CAMERA PANNING (Arrow keys) ===
        pan_dx = 0
        pan_dy = 0
        
        if keys[pygame.K_UP]:
            pan_dy = -1
        elif keys[pygame.K_DOWN]:
            pan_dy = 1
        
        if keys[pygame.K_LEFT]:
            pan_dx = -1
        elif keys[pygame.K_RIGHT]:
            pan_dx = 1
        
        if pan_dx != 0 or pan_dy != 0:
            # Stop following player when manually panning
            self.camera_following_player = False
            # Pan speed in world units per frame
            pan_speed = 0.15 / self.zoom  # Slower when zoomed in
            self.camera_x += pan_dx * pan_speed
            self.camera_y += pan_dy * pan_speed
    
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
        
        # Get mouse position in screen coords
        mouse_x, mouse_y = pygame.mouse.get_pos()
        
        # Convert to world coords
        world_x, world_y = self._screen_to_world(mouse_x, mouse_y)
        
        # Calculate direction from player to mouse
        dx = world_x - player.x
        dy = world_y - player.y
        
        # Determine 8-direction facing
        angle = math.atan2(dy, dx)  # -PI to PI, 0 = right
        
        # Convert to 8 directions
        # Angle ranges: each direction covers 45 degrees (PI/4)
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
        """Check if player is backpedaling (moving opposite to facing).
        Returns the dot product for speed calculations."""
        player = self.state.player
        if not player:
            return 0
        
        facing = player.get('facing', 'down')
        
        # Map facing to direction vector
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
        
        # Normalize movement vector for accurate dot product
        move_mag = math.sqrt(move_dx * move_dx + move_dy * move_dy)
        if move_mag > 0:
            move_dx_norm = move_dx / move_mag
            move_dy_norm = move_dy / move_mag
        else:
            move_dx_norm, move_dy_norm = 0, 0
        
        # Normalize facing vector (diagonals need normalization)
        face_mag = math.sqrt(face_dx * face_dx + face_dy * face_dy)
        if face_mag > 0:
            face_dx_norm = face_dx / face_mag
            face_dy_norm = face_dy / face_mag
        else:
            face_dx_norm, face_dy_norm = 0, 1
        
        # Dot product: 1 = same direction, 0 = perpendicular, -1 = opposite
        dot = move_dx_norm * face_dx_norm + move_dy_norm * face_dy_norm
        
        # Backpedaling if dot product is negative (moving opposite to facing)
        player['is_backpedaling'] = dot < 0
        
        return dot
    
    def _handle_movement_no_facing(self, dx, dy, sprinting=False, movement_dot=0):
        """Handle movement input without changing facing direction.
        
        Args:
            dx, dy: Movement direction
            sprinting: Whether sprint key is held
            movement_dot: Dot product of movement vs facing direction
        """
        player = self.state.player
        if not player:
            return False
        
        # Can't move while frozen
        if player.is_frozen:
            player.vx = 0.0
            player.vy = 0.0
            return False
        
        # Calculate speed based on movement direction relative to facing
        # dot > 0 means moving forward-ish, dot <= 0 means moving backward-ish
        if movement_dot > 0:
            # Moving forward - normal speed, can sprint
            speed = SPRINT_SPEED if sprinting else MOVEMENT_SPEED
            player.is_sprinting = sprinting
        else:
            # Moving sideways or backward - 10% slower, no sprint
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
    
    def _handle_keydown(self, event):
        """Handle keyboard input (non-movement actions)"""
        key = event.key
        
        # Actions (these are still on keydown, not continuous)
        if key == pygame.K_e:
            self._handle_eat()
        elif key == pygame.K_t:
            self._handle_trade()
        elif key == pygame.K_c:
            self._handle_make_camp()
        elif key == pygame.K_r:
            # Recenter camera on player and resume following
            self.camera_following_player = True
            if self.state.player:
                self.camera_x = self.state.player['x']
                self.camera_y = self.state.player['y']
        elif key == pygame.K_EQUALS or key == pygame.K_PLUS:
            # Zoom in
            self.zoom = min(MAX_ZOOM, self.zoom + ZOOM_SPEED)
            # Maintain centering on player if following
            if self.camera_following_player and self.state.player:
                self.camera_x = self.state.player['x']
                self.camera_y = self.state.player['y']
        elif key == pygame.K_MINUS:
            # Zoom out
            self.zoom = max(MIN_ZOOM, self.zoom - ZOOM_SPEED)
            # Maintain centering on player if following
            if self.camera_following_player and self.state.player:
                self.camera_x = self.state.player['x']
                self.camera_y = self.state.player['y']
        elif key == pygame.K_b:
            self._handle_bake()
    
    def _handle_mouse_click(self, event):
        """Handle mouse clicks"""
        if event.button == 1:  # Left click - Attack
            pos = event.pos
            # Only attack if clicking on canvas area
            canvas_rect = pygame.Rect(0, 0, self.canvas_width, self.canvas_height)
            if canvas_rect.collidepoint(pos):
                self._handle_attack()
    
    def _handle_mouse_release(self, event):
        """Handle mouse button release"""
        pass  # No drag functionality
    
    def _handle_mouse_motion(self, event):
        """Handle mouse movement"""
        pass  # No drag panning - use arrow keys instead
    
    def _handle_mouse_wheel(self, event):
        """Handle mouse wheel for zooming"""
        old_zoom = self.zoom
        
        # Adjust zoom
        if event.y > 0:  # Scroll up - zoom in
            self.zoom = min(MAX_ZOOM, self.zoom + ZOOM_SPEED)
        elif event.y < 0:  # Scroll down - zoom out
            self.zoom = max(MIN_ZOOM, self.zoom - ZOOM_SPEED)
        
        # If following player, ensure camera stays centered on player after zoom
        if self.camera_following_player and self.state.player:
            self.camera_x = self.state.player['x']
            self.camera_y = self.state.player['y']
    
    def _handle_resize(self, event):
        """Handle window resize event"""
        self.window_width = event.w
        self.window_height = event.h
        self.canvas_width = self.window_width
        self.canvas_height = self.window_height
        
        # Recreate the display surface with new size
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height),
            pygame.RESIZABLE
        )
    
    # =========================================================================
    # INPUT HANDLERS (delegate to logic)
    # =========================================================================
    
    def _handle_eat(self):
        """Handle player eat input"""
        self.player_controller.handle_eat_input()
    
    def _handle_trade(self):
        """Handle player trade input"""
        self.player_controller.handle_trade_input()
    
    def _handle_attack(self):
        """Handle player attack input"""
        self.player_controller.handle_attack_input()
    
    def _handle_bake(self):
        """Handle player bake input"""
        self.player_controller.handle_bake_input()
    
    def _handle_make_camp(self):
        """Handle player camp creation - only one camp allowed"""
        player = self.state.player
        if not player:
            return
        
        name = player.get_display_name()
        
        # Check if player already has a camp
        if player.get('camp_position'):
            self.state.log_action(f"{name} already has a camp")
            return
        
        # Try to make camp at current position
        cell_x = int(player.x)
        cell_y = int(player.y)
        
        if not self.logic.can_make_camp_at(cell_x, cell_y):
            self.state.log_action(f"{name} can't make a camp here (must be outside village)")
            return
        
        # Make the camp
        if self.logic.make_camp(player):
            # Camp created successfully - log is handled by make_camp
            pass
    
    # =========================================================================
    # GAME LOOP
    # =========================================================================
    
    def _game_loop(self):
        """Main game loop - called every frame, processes ticks and updates positions"""
        current_time = pygame.time.get_ticks()
        
        # Calculate delta time (in seconds)
        dt = (current_time - self.last_frame_time) / 1000.0
        self.last_frame_time = current_time
        
        # Cap delta time to prevent huge jumps after lag
        dt = min(dt, 0.1)  # Max 100ms per frame
        
        if self.state.paused:
            return
        
        # Calculate how much game time has passed
        game_dt = dt * self.state.game_speed
        
        # Time per tick in game seconds
        tick_duration = UPDATE_INTERVAL / 1000.0  # 0.1 seconds per tick
        
        # Accumulate time and process ticks with interleaved movement
        # This ensures velocities get updated as NPCs reach goals
        self._accumulated_time = getattr(self, '_accumulated_time', 0.0) + game_dt
        
        # Cap accumulated time to prevent spiral of death at extreme speeds
        max_ticks_per_frame = 200
        self._accumulated_time = min(self._accumulated_time, tick_duration * max_ticks_per_frame)
        
        # Process simulation in tick-sized chunks
        while self._accumulated_time >= tick_duration:
            # Process game logic (sets velocities based on goals)
            self.logic.process_tick()
            
            # Move characters for this tick's worth of time
            # Use small steps to prevent overshooting
            remaining = tick_duration
            while remaining > 0:
                step = min(remaining, 0.05)
                self.player_controller.update_position(step)
                self.logic.update_npc_positions(step)
                remaining -= step
            
            self._accumulated_time -= tick_duration
        
        # Handle any remaining fractional time for smooth rendering
        if self._accumulated_time > 0:
            step = min(self._accumulated_time, 0.05)
            self.player_controller.update_position(step)
            self.logic.update_npc_positions(step)
        
        # Center camera on player (if following)
        if self.camera_following_player and self.state.player:
            self.camera_x = self.state.player.x
            self.camera_y = self.state.player.y
    
    # =========================================================================
    # RENDERING
    # =========================================================================
    
    def _render_frame(self):
        """Render the current game state"""
        # Fill background
        self.screen.fill(self.BG_COLOR_RGB)
        
        # Draw the game canvas
        self._draw_canvas()
        
        pygame.display.flip()
    
    def _draw_canvas(self):
        """Draw the game canvas with camera (zoom and pan)"""
        # Canvas viewport on screen (full window)
        canvas_width = self.canvas_width
        canvas_height = self.canvas_height
        canvas_center_x = canvas_width / 2
        canvas_center_y = canvas_height / 2
        
        # Create clipping rect for canvas area
        clip_rect = pygame.Rect(0, 0, canvas_width, canvas_height)
        self.screen.set_clip(clip_rect)
        
        # Fill canvas background
        pygame.draw.rect(self.screen, self.BG_COLOR_RGB, clip_rect)
        
        # Calculate effective cell size with zoom
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
        
        # Draw grid cells (only visible ones)
        road_sprite = self.world_sprites.get('road')
        grass_sprite = self.world_sprites.get('grass')
        
        # Pre-scale sprites for current zoom level
        tile_size = int(cell_size) + 1
        scaled_road = pygame.transform.scale(road_sprite, (tile_size, tile_size)) if road_sprite else None
        scaled_grass = pygame.transform.scale(grass_sprite, (tile_size, tile_size)) if grass_sprite else None
        
        for y in range(min_visible_y, max_visible_y):
            for x in range(min_visible_x, max_visible_x):
                # Transform world to screen coordinates
                screen_x = canvas_center_x + (x - self.camera_x) * cell_size
                screen_y = canvas_center_y + (y - self.camera_y) * cell_size
                
                # Check if road tile
                is_road = (x, y) in self._road_set
                
                # Always draw grass as base layer first
                if scaled_grass:
                    self.screen.blit(scaled_grass, (int(screen_x), int(screen_y)))
                else:
                    # Fallback to solid color
                    rect = pygame.Rect(screen_x, screen_y, cell_size + 1, cell_size + 1)
                    pygame.draw.rect(self.screen, self.BG_COLOR_RGB, rect)
                
                # Then draw road or area colors on top
                if is_road and scaled_road:
                    self.screen.blit(scaled_road, (int(screen_x), int(screen_y)))
                else:
                    # Check for special area colors (farm, market, barracks, etc.)
                    color = self._get_cell_color(x, y)
                    # Only draw overlay if it's not the default background color
                    if color != BG_COLOR:
                        color_rgb = hex_to_rgb(color)
                        rect = pygame.Rect(screen_x, screen_y, cell_size + 1, cell_size + 1)
                        pygame.draw.rect(self.screen, color_rgb, rect)
        
        # Store camera transform info for other draw methods
        self._cam_center_x = canvas_center_x
        self._cam_center_y = canvas_center_y
        self._cam_cell_size = cell_size
        
        # Draw houses (below other objects)
        self._draw_houses()
        
        # Draw trees
        self._draw_trees()
        
        # Draw barrels
        self._draw_barrels()
        
        # Draw beds
        self._draw_beds()
        
        # Draw stoves
        self._draw_stoves()
        
        # Draw camps
        self._draw_camps()
        
        # Draw perception debug (sound radii and vision cones) - under characters
        if SHOW_PERCEPTION_DEBUG:
            self._draw_perception_debug()
        
        # Draw characters
        self._draw_characters()
        
        # Draw death animations (visual only - characters already removed from game logic)
        self._draw_death_animations()
        
        # Remove clipping
        self.screen.set_clip(None)
    
    def _world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates"""
        screen_x = self._cam_center_x + (world_x - self.camera_x) * self._cam_cell_size
        screen_y = self._cam_center_y + (world_y - self.camera_y) * self._cam_cell_size
        return screen_x, screen_y
    
    def _draw_barrels(self):
        """Draw all barrels using barrel sprite"""
        cell_size = self._cam_cell_size
        barrel_sprite = self.world_sprites.get('barrel')
        
        for pos, barrel in self.state.interactables.barrels.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            if barrel_sprite:
                # Scale barrel to fit nicely in cell (with some padding)
                barrel_size = int(cell_size * 0.8)
                scaled_barrel = pygame.transform.scale(barrel_sprite, (barrel_size, barrel_size))
                
                # Center in cell
                blit_x = int(screen_x + (cell_size - barrel_size) / 2)
                blit_y = int(screen_y + (cell_size - barrel_size) / 2)
                self.screen.blit(scaled_barrel, (blit_x, blit_y))
            else:
                # Fallback to rectangle
                padding = 5 * self.zoom
                barrel_rect = pygame.Rect(screen_x + padding, screen_y + padding, 
                                           cell_size - 2*padding, cell_size - 2*padding)
                pygame.draw.rect(self.screen, hex_to_rgb("#8B4513"), barrel_rect)
    
    def _draw_beds(self):
        """Draw all beds"""
        cell_size = self._cam_cell_size
        for pos, bed in self.state.interactables.beds.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            # Draw bed as blue rectangle with pillow
            padding = 4 * self.zoom
            bed_rect = pygame.Rect(screen_x + padding, screen_y + padding,
                                    cell_size - 2*padding, cell_size - 2*padding)
            pygame.draw.rect(self.screen, hex_to_rgb("#4169E1"), bed_rect)
            pygame.draw.rect(self.screen, hex_to_rgb("#2a4494"), bed_rect, max(1, int(2 * self.zoom)))
            
            # Draw pillow (small white rectangle at top)
            pillow_height = 8 * self.zoom
            pillow_rect = pygame.Rect(screen_x + padding + 3*self.zoom, screen_y + padding + 2*self.zoom,
                                       cell_size - 2*padding - 6*self.zoom, pillow_height)
            pygame.draw.rect(self.screen, (255, 255, 255), pillow_rect)
            pygame.draw.rect(self.screen, (200, 200, 200), pillow_rect, 1)
    
    def _draw_stoves(self):
        """Draw all stoves"""
        cell_size = self._cam_cell_size
        for pos, stove in self.state.interactables.stoves.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            # Draw stove as dark gray rectangle with "S"
            padding = 4 * self.zoom
            stove_rect = pygame.Rect(screen_x + padding, screen_y + padding,
                                      cell_size - 2*padding, cell_size - 2*padding)
            pygame.draw.rect(self.screen, hex_to_rgb("#444444"), stove_rect)
            pygame.draw.rect(self.screen, hex_to_rgb("#222222"), stove_rect, max(1, int(2 * self.zoom)))
            
            # Draw "S" text
            text_surface, text_rect = self.font_barrel.render("S", (255, 150, 50))
            text_x = screen_x + cell_size / 2 - text_rect.width / 2
            text_y = screen_y + cell_size / 2 - text_rect.height / 2
            self.screen.blit(text_surface, (int(text_x), int(text_y)))
    
    def _draw_camps(self):
        """Draw all camps using animated campfire sprite"""
        cell_size = self._cam_cell_size
        current_time = time.time()
        
        # Animation: cycle through frames
        if self.campfire_frames:
            frame_duration = 0.15  # 150ms per frame
            frame_idx = int(current_time / frame_duration) % len(self.campfire_frames)
            campfire_frame = self.campfire_frames[frame_idx]
        else:
            campfire_frame = None
        
        for char in self.state.characters:
            camp_pos = char.get('camp_position')
            if camp_pos:
                x, y = camp_pos
                screen_x, screen_y = self._world_to_screen(x, y)
                
                if campfire_frame:
                    # Scale campfire to fit in cell
                    campfire_size = int(cell_size * 1.2)
                    scaled_campfire = pygame.transform.scale(campfire_frame, (campfire_size, campfire_size))
                    
                    # Center on cell
                    blit_x = int(screen_x + cell_size / 2 - campfire_size / 2)
                    blit_y = int(screen_y + cell_size - campfire_size)
                    self.screen.blit(scaled_campfire, (blit_x, blit_y))
                else:
                    # Fallback to circles
                    fire_cx = int(screen_x + cell_size / 2)
                    fire_cy = int(screen_y + cell_size / 2)
                    r1, r2, r3 = int(8 * self.zoom), int(5 * self.zoom), int(2 * self.zoom)
                    pygame.draw.circle(self.screen, (255, 100, 0), (fire_cx, fire_cy), r1)
                    pygame.draw.circle(self.screen, (255, 200, 0), (fire_cx, fire_cy), r2)
                    pygame.draw.circle(self.screen, (255, 255, 100), (fire_cx, fire_cy), r3)
    
    def _draw_trees(self):
        """Draw all trees using tree sprite"""
        cell_size = self._cam_cell_size
        tree_sprite = self.world_sprites.get('tree')
        
        if not tree_sprite:
            return
        
        # Tree sprite is 66x77, we want it to span roughly 1.5-2 cells and be centered
        # Scale based on cell size
        tree_height = int(cell_size * 2.5)  # Tree is about 2.2 cells tall
        tree_width = int(tree_height * 66 / 77)  # Maintain aspect ratio
        
        scaled_tree = pygame.transform.scale(tree_sprite, (tree_width, tree_height))
        
        for pos, tree in self.state.interactables.trees.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            # Center the tree on the cell, with bottom of tree at bottom of cell
            blit_x = int(screen_x + cell_size / 2 - tree_width / 2)
            blit_y = int(screen_y + cell_size - tree_height)
            
            self.screen.blit(scaled_tree, (blit_x, blit_y))
    
    def _draw_houses(self):
        """Draw all houses using house sprites"""
        cell_size = self._cam_cell_size
        
        house_s_sprite = self.world_sprites.get('house_s')  # 98x102 for 4x4
        house_m_sprite = self.world_sprites.get('house_m')  # 146x138 for 5x5
        
        for house in self.state.interactables.houses.values():
            bounds = house.bounds
            y_start, x_start, y_end, x_end = bounds
            
            house_width_cells = x_end - x_start
            house_height_cells = y_end - y_start
            
            # Convert to screen coordinates
            screen_x, screen_y = self._world_to_screen(x_start, y_start)
            width = house_width_cells * cell_size
            height = house_height_cells * cell_size
            
            # Select sprite based on house size (4x4 = small, 5x5 = medium)
            if house_width_cells <= 4 and house_s_sprite:
                sprite = house_s_sprite
            elif house_m_sprite:
                sprite = house_m_sprite
            else:
                sprite = house_s_sprite  # Fallback
            
            if sprite:
                # Scale sprite to fit the house bounds
                scaled_sprite = pygame.transform.scale(sprite, (int(width), int(height)))
                self.screen.blit(scaled_sprite, (int(screen_x), int(screen_y)))
            else:
                # Fallback to rectangle if no sprite
                wall_color = hex_to_rgb("#C4813D")
                house_rect = pygame.Rect(screen_x, screen_y, width, height)
                pygame.draw.rect(self.screen, wall_color, house_rect)

    def _draw_characters(self):
        """Draw all characters using sprites at their float positions (ALTTP-style)"""
        cell_size = self._cam_cell_size
        current_time = time.time()
        
        for char in self.state.characters:
            # Use float position directly - positions are already continuous
            vis_x = char['x']
            vis_y = char['y']
            
            # Transform world position to screen position
            pixel_cx, pixel_cy = self._world_to_screen(vis_x, vis_y)
            
            # Sprite dimensions scaled by zoom (CHARACTER_HEIGHT tiles tall)
            sprite_height = int(CHARACTER_HEIGHT * cell_size)
            sprite_width = int(CHARACTER_WIDTH * cell_size)
            
            # Get the appropriate sprite frame
            frame, should_flip = self.sprite_manager.get_frame(char, current_time)
            
            # Get the character's color (based on job or morality)
            char_color = self._get_character_color(char)
            
            # Recolor the red clothing to the character's color
            recolored_frame = self.sprite_manager.recolor_red_to_color(frame, char_color)
            
            # Scale the frame to match character size
            scaled_frame = self.sprite_manager.scale_frame(recolored_frame, sprite_width, sprite_height)
            
            # Flip horizontally if needed (for right-facing)
            if should_flip:
                scaled_frame = pygame.transform.flip(scaled_frame, True, False)
            
            # Calculate blit position (sprite centered on character position)
            blit_x = int(pixel_cx - sprite_width / 2)
            blit_y = int(pixel_cy - sprite_height / 2)
            
            # Draw the sprite
            self.screen.blit(scaled_frame, (blit_x, blit_y))
            
            # Draw first name below sprite
            first_name = char['name'].split()[0]
            text_surface, text_rect = self.font_tiny.render(first_name, (255, 255, 255))
            text_x = pixel_cx - text_rect.width / 2
            text_y = int(pixel_cy + sprite_height / 3.2) 
            self.screen.blit(text_surface, (int(text_x), int(text_y)))
            
            # Draw HP bar below name only when health < 100
            health = char.get('health', 100)
            if health < 100:
                hp_bar_y = int(text_y + text_rect.height + 2)
                hp_bar_width = sprite_width
                hp_bar_height = max(3, int(4 * self.zoom))
                hp_bar_x = int(pixel_cx - hp_bar_width / 2)
                
                # Background (dark red)
                pygame.draw.rect(self.screen, (80, 0, 0),
                               (hp_bar_x, hp_bar_y, hp_bar_width, hp_bar_height))
                
                # Foreground (green to red based on health)
                hp_ratio = max(0, health) / 100.0
                fill_width = int(hp_bar_width * hp_ratio)
                if fill_width > 0:
                    # Color gradient: green (high health) -> yellow -> red (low health)
                    if hp_ratio > 0.5:
                        # Green to yellow
                        r = int(255 * (1 - hp_ratio) * 2)
                        g = 255
                    else:
                        # Yellow to red
                        r = 255
                        g = int(255 * hp_ratio * 2)
                    pygame.draw.rect(self.screen, (r, g, 0),
                                   (hp_bar_x, hp_bar_y, fill_width, hp_bar_height))
                
                # Border
                pygame.draw.rect(self.screen, (0, 0, 0),
                               (hp_bar_x, hp_bar_y, hp_bar_width, hp_bar_height), 1)
    
    def _draw_perception_debug(self):
        """Draw perception debug visualization - sound radii and vision cones.
        
        Shows transparent red overlays for:
        - Sound radius: circle around each character
        - Vision cone: pie slice in facing direction
        """
        cell_size = self._cam_cell_size
        
        # Create a transparent surface for drawing
        # We'll draw to main screen with alpha blending
        
        for char in self.state.characters:
            # Skip dead characters
            if char.get('health', 100) <= 0:
                continue
            
            # Get character screen position
            screen_x, screen_y = self._world_to_screen(char.x, char.y)
            
            # === Draw Sound Radius (circle) ===
            sound_radius_pixels = int(SOUND_RADIUS * cell_size)
            
            # Create a surface with per-pixel alpha for the circle
            circle_surface = pygame.Surface((sound_radius_pixels * 2, sound_radius_pixels * 2), pygame.SRCALPHA)
            # Draw filled circle with transparency (RGBA - red with alpha)
            pygame.draw.circle(circle_surface, (255, 0, 0, 40), 
                             (sound_radius_pixels, sound_radius_pixels), sound_radius_pixels)
            # Draw circle outline
            pygame.draw.circle(circle_surface, (255, 0, 0, 80), 
                             (sound_radius_pixels, sound_radius_pixels), sound_radius_pixels, 1)
            
            # Blit the circle centered on character
            self.screen.blit(circle_surface, 
                           (int(screen_x - sound_radius_pixels), int(screen_y - sound_radius_pixels)))
            
            # === Draw Vision Cone ===
            vision_radius_pixels = int(VISION_RANGE * cell_size)
            
            # Get facing direction
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
            
            # Calculate the angle of facing direction (in radians, 0 = right, counter-clockwise)
            facing_angle = math.atan2(-face_y, face_x)  # Negative y because screen y is inverted
            
            # Half angle of the cone
            half_angle = math.radians(VISION_CONE_ANGLE / 2)
            
            # Calculate the two edge points of the cone
            angle1 = facing_angle - half_angle
            angle2 = facing_angle + half_angle
            
            # Create points for the pie slice (vision cone)
            # Start at character position, go to two arc endpoints
            num_arc_points = 20  # Smoothness of the arc
            points = [(int(screen_x), int(screen_y))]  # Center point
            
            for i in range(num_arc_points + 1):
                t = i / num_arc_points
                angle = angle1 + t * (angle2 - angle1)
                px = screen_x + math.cos(angle) * vision_radius_pixels
                py = screen_y - math.sin(angle) * vision_radius_pixels  # Negative because screen y is inverted
                points.append((int(px), int(py)))
            
            # Draw the vision cone if we have enough points
            if len(points) >= 3:
                # Create a surface for the cone
                # Need to find bounding box
                min_x = min(p[0] for p in points)
                max_x = max(p[0] for p in points)
                min_y = min(p[1] for p in points)
                max_y = max(p[1] for p in points)
                
                width = max_x - min_x + 1
                height = max_y - min_y + 1
                
                if width > 0 and height > 0:
                    cone_surface = pygame.Surface((width, height), pygame.SRCALPHA)
                    
                    # Offset points to surface coordinates
                    offset_points = [(p[0] - min_x, p[1] - min_y) for p in points]
                    
                    # Draw filled polygon with transparency
                    pygame.draw.polygon(cone_surface, (255, 100, 100, 30), offset_points)
                    # Draw outline
                    pygame.draw.polygon(cone_surface, (255, 50, 50, 60), offset_points, 1)
                    
                    self.screen.blit(cone_surface, (min_x, min_y))

    def _draw_death_animations(self):
        """Draw death animations for characters that have died.
        
        Death animations are purely visual - the characters have already been
        removed from game logic. This renders the death sprite at their last position.
        """
        DEATH_ANIMATION_DURATION = 0.9  # 6 frames at 150ms each
        current_time = time.time()
        cell_size = self._cam_cell_size
        
        # Remove expired animations
        self.state.death_animations = [
            anim for anim in self.state.death_animations
            if current_time - anim['start_time'] < DEATH_ANIMATION_DURATION
        ]
        
        for anim in self.state.death_animations:
            # Transform world position to screen position
            pixel_cx, pixel_cy = self._world_to_screen(anim['x'], anim['y'])
            
            # Sprite dimensions scaled by zoom
            sprite_height = int(CHARACTER_HEIGHT * cell_size)
            sprite_width = int(CHARACTER_WIDTH * cell_size)
            
            # Create a fake char dict for the sprite manager
            fake_char = {
                'name': anim['name'],
                'facing': anim['facing'],
                'health': 0,  # Marks as dead for death animation
                'death_animation_start': anim['start_time'],
                'vx': 0, 'vy': 0
            }
            
            # Get the death animation frame
            frame, should_flip = self.sprite_manager.get_frame(fake_char, current_time)
            
            # Get color based on job/morality (same logic as _get_character_color)
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
            
            # Recolor and scale the frame
            recolored_frame = self.sprite_manager.recolor_red_to_color(frame, color)
            scaled_frame = self.sprite_manager.scale_frame(recolored_frame, sprite_width, sprite_height)
            
            if should_flip:
                scaled_frame = pygame.transform.flip(scaled_frame, True, False)
            
            # Calculate blit position
            blit_x = int(pixel_cx - sprite_width / 2)
            blit_y = int(pixel_cy - sprite_height / 2)
            
            # Draw the death animation sprite
            self.screen.blit(scaled_frame, (blit_x, blit_y))
    
    def _get_cell_color(self, x, y):
        """Get the background color for a cell"""
        # Check if it's a road cell first
        if (x, y) in self._road_set:
            return ROAD_COLOR
        
        # Check if it's a farm cell
        farm_cell = self.state.get_farm_cell_state(x, y)
        if farm_cell:
            return FARM_CELL_COLORS.get(farm_cell['state'], BG_COLOR)
        
        # Get area color (but skip village areas - they use background)
        area = self.state.get_area_at(x, y)
        if area:
            for area_def in AREAS:
                if area_def["name"] == area:
                    # Village areas use background color, not their defined color
                    if area_def.get("role") == "village":
                        return BG_COLOR
                    return area_def.get("color", BG_COLOR)
        
        return BG_COLOR
    
    def _get_character_color(self, char):
        """Get the display color for a character"""
        # Frozen characters (starving + health <= 20) shown in red
        if char.get('is_frozen', False):
            return "#FF0000"
        
        # Starving but not frozen shown in orange
        if char.get('is_starving', False):
            return "#FF8C00"
        
        # Job colors take priority (if defined for this job)
        job = char.get('job')
        if job in JOB_TIERS and "color" in JOB_TIERS[job]:
            return JOB_TIERS[job]["color"]
        
        # Fall back to morality-based color
        morality = char.get('morality', 5)
        t = (morality - 1) / 9.0
        r = int(0 + t * 173)
        g = int(0 + t * 216)
        b = int(139 + t * (230 - 139))
        return f"#{r:02x}{g:02x}{b:02x}"