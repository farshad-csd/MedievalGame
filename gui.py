# gui.py - Pure GUI: rendering and input handling only (Pygame version)
"""
This module contains ONLY:
- Pygame setup and rendering
- Input handling

It does NOT contain:
- Game logic (that's in game_logic.py)
- Game state (that's in game_state.py)
"""

import time
import math
import pygame
import pygame.freetype
from constants import (
    SIZE, CELL_SIZE, UPDATE_INTERVAL,
    FARM_CELL_COLORS, JOB_COLORS,
    BG_COLOR, GRID_COLOR,
    TICKS_PER_DAY, TICKS_PER_YEAR, SLEEP_START_FRACTION,
    MOVEMENT_SPEED, CHARACTER_WIDTH, CHARACTER_HEIGHT, CHARACTER_EYE_POSITION,
    DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, ZOOM_SPEED, SPRINT_SPEED,
    ATTACK_ANIMATION_DURATION
)
from scenario_world import AREAS, BARRELS, BEDS, VILLAGE_NAME
from game_state import GameState
from game_logic import GameLogic
from debug_window import DebugWindow


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
        
        # Create debug window (separate Tkinter window) - pass logic for skip year
        self.debug_window = DebugWindow(self.state, self.logic)
        
        # Calculate window dimensions - 16:9 aspect ratio
        self.window_height = SIZE * CELL_SIZE + 20
        self.window_width = int(self.window_height * 16 / 9)
        self.canvas_width = self.window_width - 20
        self.canvas_height = self.window_height - 20
        
        # Create window
        self.screen = pygame.display.set_mode((self.window_width, self.window_height))
        pygame.display.set_caption(f"{VILLAGE_NAME} - Village Simulation")
        
        # Load fonts
        self.font_tiny = pygame.freetype.SysFont('Arial', 7)
        self.font_barrel = pygame.freetype.SysFont('Arial', 14, bold=True)
        
        # Timing
        self.clock = pygame.time.Clock()
        self.last_tick_time = pygame.time.get_ticks()
        self.last_frame_time = pygame.time.get_ticks()  # For delta time calculation
        
        # Player movement state - which keys are currently held
        self.player_moving = False
        
        # Camera state
        self.camera_x = SIZE / 2  # Camera center in world coordinates
        self.camera_y = SIZE / 2
        self.zoom = DEFAULT_ZOOM
        self.camera_following_player = True  # Whether camera follows player
        self.camera_dragging = False  # True while actively dragging
        self.drag_start_mouse = None  # Mouse position when drag started
        self.drag_start_camera = None  # Camera position when drag started
        
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
                    player_food = self.state.get_food(player)
                    player_money = self.state.get_money(player)
                    status = f"Pos:({player['x']:.1f},{player['y']:.1f}) Food:{player_food} ${player_money} HP:{player['health']} | Zoom:{self.zoom:.1f}x | {'Follow' if self.camera_following_player else 'Free'}"
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
            # Set player velocity (logic handles normalization for diagonal)
            self.logic.move_player(dx, dy, sprinting)
            self.player_moving = True
        else:
            # No movement keys held - stop player
            if self.player_moving:
                self.logic.stop_player()
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
        elif key == pygame.K_MINUS:
            # Zoom out
            self.zoom = max(MIN_ZOOM, self.zoom - ZOOM_SPEED)
    
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
    
    # =========================================================================
    # INPUT HANDLERS (delegate to logic)
    # =========================================================================
    
    def _handle_eat(self):
        """Handle player eat input"""
        self.logic.player_eat()
    
    def _handle_trade(self):
        """Handle player trade input"""
        self.logic.player_trade()
    
    def _handle_attack(self):
        """Handle player attack input"""
        self.logic.player_attack()
    
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
                self.logic.update_player_position(step)
                self.logic.update_npc_positions(step)
                remaining -= step
            
            self._accumulated_time -= tick_duration
        
        # Handle any remaining fractional time for smooth rendering
        if self._accumulated_time > 0:
            step = min(self._accumulated_time, 0.05)
            self.logic.update_player_position(step)
            self.logic.update_npc_positions(step)
        
        # Center camera on player (if following)
        if self.camera_following_player and self.state.player:
            self.camera_x = self.state.player['x']
            self.camera_y = self.state.player['y']
    
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
        
        # Draw barrels
        self._draw_barrels()
        
        # Draw beds
        self._draw_beds()
        
        # Draw camps
        self._draw_camps()
        
        # Draw characters
        self._draw_characters()
        
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
        for pos, barrel in self.state.barrels.items():
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
        for pos, bed in self.state.beds.items():
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
    
    def _draw_characters(self):
        """Draw all characters as rectangles at their float positions (ALTTP-style)"""
        cell_size = self._cam_cell_size
        for char in self.state.characters:
            # Use float position directly - positions are already continuous
            vis_x = char['x']
            vis_y = char['y']
            
            color = self._get_character_color(char)
            color_rgb = hex_to_rgb(color)
            
            # Transform world position to screen position
            pixel_cx, pixel_cy = self._world_to_screen(vis_x, vis_y)
            
            # Rectangle dimensions from constants (in pixels, scaled by zoom)
            rect_width = int(CHARACTER_WIDTH * cell_size)
            rect_height = int(CHARACTER_HEIGHT * cell_size)
            
            # Calculate rectangle bounds (centered on character position)
            rect_left = int(pixel_cx - rect_width / 2)
            rect_top = int(pixel_cy - rect_height / 2)
            
            # Draw filled rectangle
            pygame.draw.rect(self.screen, color_rgb, 
                           (rect_left, rect_top, rect_width, rect_height))
            pygame.draw.rect(self.screen, (0, 0, 0),
                           (rect_left, rect_top, rect_width, rect_height), 1)
            
            # Draw eyes at configured position from top of rectangle
            eye_y = rect_top + int(rect_height * CHARACTER_EYE_POSITION)
            rect_cx = rect_left + rect_width // 2
            self._draw_character_eyes(char, rect_cx, eye_y, rect_width)
            
            # Draw sword swing animation if active
            self._draw_sword_swing(char, pixel_cx, pixel_cy, rect_width, rect_height)
            
            # Draw first name below rectangle
            first_name = char['name'].split()[0]
            text_surface, text_rect = self.font_tiny.render(first_name, (0, 0, 0))
            text_x = pixel_cx - text_rect.width / 2
            text_y = rect_top + rect_height + 2
            self.screen.blit(text_surface, (int(text_x), int(text_y)))
    
    def _draw_sword_swing(self, char, cx, cy, rect_width, rect_height):
        """Draw sword swing animation arc if character is attacking."""
        anim_start = char.get('attack_animation_start')
        if anim_start is None:
            return
        
        # Calculate animation progress (0.0 to 1.0)
        elapsed = time.time() - anim_start
        if elapsed > ATTACK_ANIMATION_DURATION:
            # Animation finished - clear it
            char['attack_animation_start'] = None
            char['attack_direction'] = None
            return
        
        progress = elapsed / ATTACK_ANIMATION_DURATION
        
        # Sword parameters
        sword_length = int(rect_height * 1.2)  # Sword is slightly longer than character height
        sword_width = max(2, int(3 * self.zoom))
        
        # Attack direction determines swing arc
        attack_dir = char.get('attack_direction', 'right')
        
        # Calculate swing angle based on progress
        # Swing goes from -60 degrees to +60 degrees (120 degree arc)
        # Using eased animation for snappy feel
        ease_progress = 1 - (1 - progress) ** 3  # Ease out cubic
        swing_angle = -60 + (120 * ease_progress)
        
        # Base angle depends on attack direction
        if attack_dir == 'right':
            base_angle = 0
            origin_x = cx + rect_width // 2
            origin_y = cy
        elif attack_dir == 'left':
            base_angle = 180
            origin_x = cx - rect_width // 2
            origin_y = cy
        elif attack_dir == 'down':
            base_angle = 90
            origin_x = cx
            origin_y = cy + rect_height // 2
        else:  # up
            base_angle = -90
            origin_x = cx
            origin_y = cy - rect_height // 2
        
        # Calculate sword endpoint
        total_angle = math.radians(base_angle + swing_angle)
        end_x = origin_x + int(sword_length * math.cos(total_angle))
        end_y = origin_y + int(sword_length * math.sin(total_angle))
        
        # Draw sword blade (silver/gray)
        pygame.draw.line(self.screen, (180, 180, 200), 
                        (int(origin_x), int(origin_y)), 
                        (int(end_x), int(end_y)), 
                        sword_width)
        
        # Draw sword edge highlight
        pygame.draw.line(self.screen, (220, 220, 240),
                        (int(origin_x), int(origin_y)),
                        (int(end_x), int(end_y)),
                        max(1, sword_width // 2))
        
        # Draw swing trail (motion blur effect)
        if progress < 0.8:
            trail_alpha = int(100 * (1 - progress))
            # Draw a few trail lines behind the current position
            for i in range(3):
                trail_progress = max(0, ease_progress - (i + 1) * 0.15)
                trail_angle = math.radians(base_angle + (-60 + 120 * trail_progress))
                trail_end_x = origin_x + int(sword_length * math.cos(trail_angle))
                trail_end_y = origin_y + int(sword_length * math.sin(trail_angle))
                trail_color = (150, 150, 170)
                pygame.draw.line(self.screen, trail_color,
                               (int(origin_x), int(origin_y)),
                               (int(trail_end_x), int(trail_end_y)),
                               max(1, sword_width - i - 1))
    
    def _draw_character_eyes(self, char, cx, eye_y, rect_width):
        """Draw eyes based on facing direction. Eyes are always at eye_y (10% from top)."""
        facing = char.get('facing', 'down')
        eye_radius = 2
        eye_color = (255, 255, 255)
        pupil_color = (0, 0, 0)
        
        # Eye spread based on rectangle width
        eye_spread = rect_width // 4
        
        if facing == 'down':
            left_eye_x = cx - eye_spread
            right_eye_x = cx + eye_spread
            pupil_offset_x, pupil_offset_y = 0, 1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y, 
                                          eye_radius, eye_color, pupil_color, 
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'up':
            left_eye_x = cx - eye_spread
            right_eye_x = cx + eye_spread
            pupil_offset_x, pupil_offset_y = 0, -1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'left':
            eye_x = cx - eye_spread
            top_eye_y = eye_y - 2
            bottom_eye_y = eye_y + 4
            pupil_offset_x, pupil_offset_y = -1, 0
            self._draw_eye_pair_vertical(eye_x, top_eye_y, bottom_eye_y,
                                        eye_radius, eye_color, pupil_color,
                                        pupil_offset_x, pupil_offset_y)
        
        elif facing == 'right':
            eye_x = cx + eye_spread
            top_eye_y = eye_y - 2
            bottom_eye_y = eye_y + 4
            pupil_offset_x, pupil_offset_y = 1, 0
            self._draw_eye_pair_vertical(eye_x, top_eye_y, bottom_eye_y,
                                        eye_radius, eye_color, pupil_color,
                                        pupil_offset_x, pupil_offset_y)
        
        elif facing == 'up-left':
            left_eye_x = cx - eye_spread
            right_eye_x = cx + eye_spread // 2
            pupil_offset_x, pupil_offset_y = -1, -1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'up-right':
            left_eye_x = cx - eye_spread // 2
            right_eye_x = cx + eye_spread
            pupil_offset_x, pupil_offset_y = 1, -1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'down-left':
            left_eye_x = cx - eye_spread
            right_eye_x = cx + eye_spread // 2
            pupil_offset_x, pupil_offset_y = -1, 1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'down-right':
            left_eye_x = cx - eye_spread // 2
            right_eye_x = cx + eye_spread
            pupil_offset_x, pupil_offset_y = 1, 1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
    
    def _draw_eye_pair_horizontal(self, left_x, right_x, y, radius, eye_color, pupil_color, pupil_dx, pupil_dy):
        """Draw horizontally arranged eyes"""
        # Left eye
        pygame.draw.circle(self.screen, eye_color, (left_x, y), radius)
        pygame.draw.circle(self.screen, pupil_color, (left_x + pupil_dx, y + pupil_dy), 1)
        
        # Right eye
        pygame.draw.circle(self.screen, eye_color, (right_x, y), radius)
        pygame.draw.circle(self.screen, pupil_color, (right_x + pupil_dx, y + pupil_dy), 1)
    
    def _draw_eye_pair_vertical(self, x, top_y, bottom_y, radius, eye_color, pupil_color, pupil_dx, pupil_dy):
        """Draw vertically arranged eyes"""
        # Top eye
        pygame.draw.circle(self.screen, eye_color, (x, top_y), radius)
        pygame.draw.circle(self.screen, pupil_color, (x + pupil_dx, top_y + pupil_dy), 1)
        
        # Bottom eye
        pygame.draw.circle(self.screen, eye_color, (x, bottom_y), radius)
        pygame.draw.circle(self.screen, pupil_color, (x + pupil_dx, bottom_y + pupil_dy), 1)
    
    def _get_cell_color(self, x, y):
        """Get the background color for a cell"""
        # Check if it's a farm cell
        farm_cell = self.state.get_farm_cell_state(x, y)
        if farm_cell:
            return FARM_CELL_COLORS.get(farm_cell['state'], BG_COLOR)
        
        # Get area color
        area = self.state.get_area_at(x, y)
        if area:
            for area_def in AREAS:
                if area_def["name"] == area:
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
        
        # Job colors take priority
        job = char.get('job')
        if job in JOB_COLORS:
            return JOB_COLORS[job]
        
        # Fall back to morality-based color
        morality = char.get('morality', 5)
        t = (morality - 1) / 9.0
        r = int(0 + t * 173)
        g = int(0 + t * 216)
        b = int(139 + t * (230 - 139))
        return f"#{r:02x}{g:02x}{b:02x}"
