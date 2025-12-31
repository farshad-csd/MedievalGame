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
import pygame
import pygame.freetype
from constants import (
    CELL_SIZE, UPDATE_INTERVAL,
    FARM_CELL_COLORS, JOB_TIERS,
    BG_COLOR, GRID_COLOR, ROAD_COLOR,
    TICKS_PER_DAY, TICKS_PER_YEAR, SLEEP_START_FRACTION,
    MOVEMENT_SPEED, CHARACTER_WIDTH, CHARACTER_HEIGHT,
    DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, ZOOM_SPEED, SPRINT_SPEED
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
        
        self.canvas_width = self.window_width - 20
        self.canvas_height = self.window_height - 20
        
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
        """Handle continuous player movement while keys are held - ALTTP style"""
        keys = pygame.key.get_pressed()
        
        # Calculate movement direction
        dx = 0
        dy = 0
        
        # Vertical
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy = -1
        elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy = 1
        
        # Horizontal
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx = -1
        elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx = 1
        
        # Check if sprinting (shift held)
        sprinting = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        
        if dx != 0 or dy != 0:
            # Set player velocity via controller
            self.player_controller.handle_movement_input(dx, dy, sprinting)
            self.player_moving = True
        else:
            # No movement keys held - stop player
            if self.player_moving:
                self.player_controller.stop_movement()
                self.player_moving = False
    
    def _handle_keydown(self, event):
        """Handle keyboard input (non-movement actions)"""
        key = event.key
        
        # Actions (these are still on keydown, not continuous)
        if key == pygame.K_e:
            self._handle_eat()
        elif key == pygame.K_t:
            self._handle_trade()
        elif key == pygame.K_f:
            self._handle_attack()
        elif key == pygame.K_c:
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
        if event.button == 1:  # Left click
            pos = event.pos
            
            # Check if click is on canvas area - start dragging
            canvas_left = 10
            canvas_top = 10
            canvas_rect = pygame.Rect(canvas_left, canvas_top, self.canvas_width, self.canvas_height)
            if canvas_rect.collidepoint(pos):
                self.camera_dragging = True
                self.camera_following_player = False  # Stop following player
                self.drag_start_mouse = pos
                self.drag_start_camera = (self.camera_x, self.camera_y)
    
    def _handle_mouse_release(self, event):
        """Handle mouse button release"""
        if event.button == 1:  # Left click released
            self.camera_dragging = False
    
    def _handle_mouse_motion(self, event):
        """Handle mouse movement for panning"""
        if self.camera_dragging and self.drag_start_mouse:
            # Calculate how much mouse moved in screen pixels
            dx = event.pos[0] - self.drag_start_mouse[0]
            dy = event.pos[1] - self.drag_start_mouse[1]
            
            # Convert to world units (inverse because dragging moves view opposite direction)
            world_dx = -dx / (self.zoom * CELL_SIZE)
            world_dy = -dy / (self.zoom * CELL_SIZE)
            
            # Update camera position
            self.camera_x = self.drag_start_camera[0] + world_dx
            self.camera_y = self.drag_start_camera[1] + world_dy
    
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
        self.canvas_width = self.window_width - 20
        self.canvas_height = self.window_height - 20
        
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
        # Canvas viewport on screen
        canvas_left = 10
        canvas_top = 10
        canvas_width = self.canvas_width
        canvas_height = self.canvas_height
        canvas_center_x = canvas_left + canvas_width / 2
        canvas_center_y = canvas_top + canvas_height / 2
        
        # Create clipping rect for canvas area
        clip_rect = pygame.Rect(canvas_left, canvas_top, canvas_width, canvas_height)
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
        for y in range(min_visible_y, max_visible_y):
            for x in range(min_visible_x, max_visible_x):
                # Transform world to screen coordinates
                screen_x = canvas_center_x + (x - self.camera_x) * cell_size
                screen_y = canvas_center_y + (y - self.camera_y) * cell_size
                
                # Get cell color
                color = self._get_cell_color(x, y)
                color_rgb = hex_to_rgb(color)
                
                # Draw cell
                rect = pygame.Rect(screen_x, screen_y, cell_size + 1, cell_size + 1)
                pygame.draw.rect(self.screen, color_rgb, rect)
                pygame.draw.rect(self.screen, self.GRID_COLOR_RGB, rect, 1)
        
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
        """Draw all barrels"""
        cell_size = self._cam_cell_size
        for pos, barrel in self.state.interactables.barrels.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            # Draw barrel as brown rectangle with "B"
            padding = 5 * self.zoom
            barrel_rect = pygame.Rect(screen_x + padding, screen_y + padding, 
                                       cell_size - 2*padding, cell_size - 2*padding)
            pygame.draw.rect(self.screen, hex_to_rgb("#8B4513"), barrel_rect)
            pygame.draw.rect(self.screen, hex_to_rgb("#4a2500"), barrel_rect, max(1, int(2 * self.zoom)))
            
            # Draw "B" text
            text_surface, text_rect = self.font_barrel.render("B", (255, 255, 255))
            text_x = screen_x + cell_size / 2 - text_rect.width / 2
            text_y = screen_y + cell_size / 2 - text_rect.height / 2
            self.screen.blit(text_surface, (int(text_x), int(text_y)))
    
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
        """Draw all camps"""
        cell_size = self._cam_cell_size
        for char in self.state.characters:
            camp_pos = char.get('camp_position')
            if camp_pos:
                x, y = camp_pos
                screen_x, screen_y = self._world_to_screen(x, y)
                
                # Draw campfire (orange/red circle)
                fire_cx = int(screen_x + cell_size / 2)
                fire_cy = int(screen_y + cell_size / 2)
                r1, r2, r3 = int(8 * self.zoom), int(5 * self.zoom), int(2 * self.zoom)
                pygame.draw.circle(self.screen, (255, 100, 0), (fire_cx, fire_cy), r1)
                pygame.draw.circle(self.screen, (255, 200, 0), (fire_cx, fire_cy), r2)
                pygame.draw.circle(self.screen, (255, 255, 100), (fire_cx, fire_cy), r3)
                
                # Draw bedroll next to fire
                bedroll_x = fire_cx + int(10 * self.zoom)
                pygame.draw.ellipse(self.screen, (100, 80, 60),
                                   (bedroll_x - int(3*self.zoom), fire_cy - int(6*self.zoom), 
                                    int(8*self.zoom), int(12*self.zoom)))
    
    def _draw_trees(self):
        """Draw all trees as simple green circles with brown trunks"""
        cell_size = self._cam_cell_size
        
        # Tree colors
        trunk_color = hex_to_rgb("#5D4037")  # Brown trunk
        leaves_color = hex_to_rgb("#2D5A27")  # Dark green leaves
        leaves_highlight = hex_to_rgb("#4A7C42")  # Lighter green highlight
        
        for pos, tree in self.state.interactables.trees.items():
            x, y = pos
            screen_x, screen_y = self._world_to_screen(x, y)
            
            # Center of cell
            cx = int(screen_x + cell_size / 2)
            cy = int(screen_y + cell_size / 2)
            
            # Tree dimensions scaled by zoom
            trunk_width = max(2, int(4 * self.zoom))
            trunk_height = max(3, int(8 * self.zoom))
            canopy_radius = max(4, int(cell_size * 0.4))
            
            # Draw trunk (small rectangle at bottom center)
            trunk_rect = pygame.Rect(
                cx - trunk_width // 2,
                cy + canopy_radius // 2 - trunk_height // 2,
                trunk_width,
                trunk_height
            )
            pygame.draw.rect(self.screen, trunk_color, trunk_rect)
            
            # Draw canopy (circle above trunk)
            canopy_cy = cy - int(canopy_radius * 0.2)
            pygame.draw.circle(self.screen, leaves_color, (cx, canopy_cy), canopy_radius)
            
            # Draw highlight circle (smaller, offset up-left)
            highlight_radius = max(2, int(canopy_radius * 0.5))
            highlight_offset = max(1, int(canopy_radius * 0.2))
            pygame.draw.circle(self.screen, leaves_highlight, 
                             (cx - highlight_offset, canopy_cy - highlight_offset), 
                             highlight_radius)
    
    def _draw_houses(self):
        """Draw all houses as colored rectangles with roofs"""
        cell_size = self._cam_cell_size
        
        # House colors
        wall_color = hex_to_rgb("#C4813D")  # Brown/tan walls
        roof_color = hex_to_rgb("#8B4513")  # Darker brown roof
        outline_color = hex_to_rgb("#5D4037")  # Dark brown outline
        
        for house in self.state.interactables.houses.values():
            bounds = house.bounds
            y_start, x_start, y_end, x_end = bounds
            
            # Convert to screen coordinates
            screen_x, screen_y = self._world_to_screen(x_start, y_start)
            width = (x_end - x_start) * cell_size
            height = (y_end - y_start) * cell_size
            
            # Draw house body
            house_rect = pygame.Rect(screen_x, screen_y, width, height)
            pygame.draw.rect(self.screen, wall_color, house_rect)
            pygame.draw.rect(self.screen, outline_color, house_rect, max(1, int(2 * self.zoom)))
            
            # Draw simple roof indicator (darker strip at top)
            roof_height = max(2, int(cell_size * 0.3))
            roof_rect = pygame.Rect(screen_x, screen_y, width, roof_height)
            pygame.draw.rect(self.screen, roof_color, roof_rect)

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
            text_surface, text_rect = self.font_tiny.render(first_name, (0, 0, 0))
            text_x = pixel_cx - text_rect.width / 2
            text_y = int(pixel_cy + sprite_height / 2) + 2
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