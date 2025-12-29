# gui.py - Pure GUI: rendering and input handling only (Pygame version)
"""
This module contains ONLY:
- Pygame setup and rendering
- Input handling

It does NOT contain:
- Game logic (that's in game_logic.py)
- Game state (that's in game_state.py)
"""

import pygame
import pygame.freetype
from constants import (
    SIZE, CELL_SIZE, UPDATE_INTERVAL, SPEED_OPTIONS,
    FARM_CELL_COLORS, JOB_COLORS, SKILLS,
    BG_COLOR, GRID_COLOR, TEXT_COLOR,
    TICKS_PER_DAY, TICKS_PER_YEAR, SLEEP_START_FRACTION,
    PLAYER_MOVE_INTERVAL_MS, NPC_MOVE_DURATION_MS, PLAYER_MOVE_DURATION_MS
)
from scenario_world import AREAS, BARRELS, BEDS, VILLAGE_NAME
from scenario_characters import CHARACTER_TEMPLATES
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
    
    # Debug panel colors (for status bar)
    DEBUG_BG = (44, 62, 80)  # #2c3e50
    DEBUG_TEXT = (236, 240, 241)  # #ecf0f1
    DEBUG_YELLOW = (241, 196, 15)  # #f1c40f
    
    # Button colors
    BUTTON_BG = (100, 100, 100)
    BUTTON_HOVER = (120, 120, 120)
    BUTTON_TEXT = (255, 255, 255)
    
    def __init__(self, root=None):
        """Initialize pygame and game components. root parameter kept for compatibility but ignored."""
        pygame.init()
        pygame.freetype.init()
        
        # Create game state and logic
        self.state = GameState()
        self.logic = GameLogic(self.state)
        
        # Create debug window (separate Tkinter window)
        self.debug_window = DebugWindow(self.state)
        
        # Speed index for cycling through SPEED_OPTIONS
        self.speed_index = 0
        
        # Calculate window dimensions (no debug panel - it's in separate window)
        self.canvas_width = SIZE * CELL_SIZE
        self.canvas_height = SIZE * CELL_SIZE
        self.info_bar_height = 40
        self.control_bar_height = 50
        self.status_bar_height = 25
        self.window_width = self.canvas_width + 20
        self.window_height = self.canvas_height + self.info_bar_height + self.control_bar_height + self.status_bar_height + 20
        
        # Create window
        self.screen = pygame.display.set_mode((self.window_width, self.window_height))
        pygame.display.set_caption(f"{VILLAGE_NAME} - Village Simulation")
        
        # Load fonts
        self.font_large = pygame.freetype.SysFont('Arial', 12)
        self.font_medium = pygame.freetype.SysFont('Arial', 11)
        self.font_small = pygame.freetype.SysFont('Courier', 9)
        self.font_tiny = pygame.freetype.SysFont('Arial', 7)
        self.font_char = pygame.freetype.SysFont('Arial', 18, bold=True)
        self.font_barrel = pygame.freetype.SysFont('Arial', 14, bold=True)
        self.font_title = pygame.freetype.SysFont('Courier', 12, bold=True)
        
        # Button definitions
        self.buttons = {}
        self._setup_buttons()
        
        # Timing
        self.clock = pygame.time.Clock()
        self.last_tick_time = pygame.time.get_ticks()
        
        # Smooth movement interpolation - using REAL TIME, not game ticks
        # Each character tracks: previous position, current position, and when movement started
        self.char_anim = {}  # name -> {'prev_x', 'prev_y', 'curr_x', 'curr_y', 'move_start_time'}
        self._init_char_positions()
        
        # Player continuous movement
        self.last_player_move_time = 0
        
        # Running state
        self.running = True
    
    def _init_char_positions(self):
        """Initialize character position tracking for smooth interpolation"""
        current_time = pygame.time.get_ticks()
        for char in self.state.characters:
            self.char_anim[char['name']] = {
                'prev_x': float(char['x']),
                'prev_y': float(char['y']),
                'curr_x': float(char['x']),
                'curr_y': float(char['y']),
                'move_start_time': current_time,
                'is_player': self.logic.is_player(char)
            }
    
    def _setup_buttons(self):
        """Setup button positions and sizes"""
        button_y = self.info_bar_height + 10
        button_width = 100
        button_height = 30
        button_spacing = 10
        start_x = 10
        
        self.buttons['speed'] = pygame.Rect(start_x, button_y, button_width, button_height)
        self.buttons['pause'] = pygame.Rect(start_x + button_width + button_spacing, button_y, button_width, button_height)
        self.buttons['skip_year'] = pygame.Rect(start_x + 2 * (button_width + button_spacing), button_y, button_width, button_height)
    
    def run(self):
        """Main game loop"""
        while self.running:
            self._handle_events()
            self._game_loop()
            self._render_frame()
            
            # Update debug window (Tkinter)
            if self.debug_window.is_open():
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
        
        # Handle continuous player movement (check held keys every frame)
        self._handle_continuous_movement()
    
    def _handle_continuous_movement(self):
        """Handle continuous player movement while keys are held"""
        current_time = pygame.time.get_ticks()
        
        # Scale movement interval with game speed (faster game = can move more frequently)
        move_interval = PLAYER_MOVE_INTERVAL_MS / self.state.game_speed
        
        # Only move if enough time has passed since last move
        if current_time - self.last_player_move_time < move_interval:
            return
        
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
        
        if dx != 0 or dy != 0:
            if self._do_player_move(dx, dy):
                self.last_player_move_time = current_time
    
    def _do_player_move(self, dx, dy):
        """Execute player movement and trigger animation"""
        player = self.state.player
        if not player:
            return False
        
        # Get current visual position before move (for seamless animation)
        vis_x, vis_y = self._get_interpolated_position(player)
        
        # Try to move
        moved = self.logic.move_player(dx, dy)
        
        if moved:
            # Update animation tracking - start from VISUAL position, not grid
            name = player['name']
            current_time = pygame.time.get_ticks()
            
            if name in self.char_anim:
                self.char_anim[name]['prev_x'] = vis_x
                self.char_anim[name]['prev_y'] = vis_y
                self.char_anim[name]['curr_x'] = float(player['x'])
                self.char_anim[name]['curr_y'] = float(player['y'])
                self.char_anim[name]['move_start_time'] = current_time
        
        return moved
    
    def _handle_keydown(self, event):
        """Handle keyboard input (non-movement actions)"""
        key = event.key
        
        # Actions (these are still on keydown, not continuous)
        if key == pygame.K_e:
            self._handle_eat()
        elif key == pygame.K_t:
            self._handle_trade()
    
    def _handle_mouse_click(self, event):
        """Handle mouse clicks"""
        if event.button == 1:  # Left click
            pos = event.pos
            
            # Check buttons
            if self.buttons['speed'].collidepoint(pos):
                self._toggle_speed()
            elif self.buttons['pause'].collidepoint(pos):
                self._toggle_pause()
            elif self.buttons['skip_year'].collidepoint(pos):
                self._skip_one_year()
    
    # =========================================================================
    # INPUT HANDLERS (delegate to logic)
    # =========================================================================
    
    def _handle_eat(self):
        """Handle player eat input"""
        self.logic.player_eat()
    
    def _handle_trade(self):
        """Handle player trade input"""
        self.logic.player_trade()
    
    def _toggle_speed(self):
        """Cycle through speed options"""
        self.speed_index = (self.speed_index + 1) % len(SPEED_OPTIONS)
        self.state.game_speed = SPEED_OPTIONS[self.speed_index]
    
    def _toggle_pause(self):
        """Toggle pause state"""
        self.state.paused = not self.state.paused
    
    def _skip_one_year(self):
        """Skip forward one year"""
        self.state.log_action("=== SKIPPING 1 YEAR ===")
        
        for _ in range(TICKS_PER_YEAR):
            self.logic.process_tick()
        
        # Reset position tracking after skip
        self._init_char_positions()
        
        self.state.log_action("=== SKIP COMPLETE ===")
    
    # =========================================================================
    # GAME LOOP
    # =========================================================================
    
    def _game_loop(self):
        """Main game loop - called every frame, processes ticks as needed"""
        current_time = pygame.time.get_ticks()
        interval = UPDATE_INTERVAL // self.state.game_speed
        
        if not self.state.paused and current_time - self.last_tick_time >= interval:
            # Snapshot NPC positions before processing tick
            npc_positions_before = {}
            for char in self.state.characters:
                if not self.logic.is_player(char):
                    npc_positions_before[char['name']] = (char['x'], char['y'])
            
            # Process game logic
            self.logic.process_tick()
            self.last_tick_time = current_time
            
            # Check for NPC movement and update animation
            self._update_npc_animations(npc_positions_before, current_time)
    
    def _update_npc_animations(self, positions_before, current_time):
        """Update NPC animation state after a game tick"""
        for char in self.state.characters:
            name = char['name']
            if self.logic.is_player(char):
                continue  # Player handled separately
            
            # Ensure animation entry exists
            if name not in self.char_anim:
                self.char_anim[name] = {
                    'prev_x': float(char['x']),
                    'prev_y': float(char['y']),
                    'curr_x': float(char['x']),
                    'curr_y': float(char['y']),
                    'move_start_time': current_time,
                    'is_player': False
                }
                continue
            
            # Check if NPC moved
            old_pos = positions_before.get(name)
            if old_pos:
                old_x, old_y = old_pos
                new_x, new_y = char['x'], char['y']
                
                if old_x != new_x or old_y != new_y:
                    # NPC moved - start animation from CURRENT VISUAL position (not grid)
                    # This creates seamless motion when interrupting mid-animation
                    vis_x, vis_y = self._get_interpolated_position(char)
                    self.char_anim[name]['prev_x'] = vis_x
                    self.char_anim[name]['prev_y'] = vis_y
                    self.char_anim[name]['curr_x'] = float(new_x)
                    self.char_anim[name]['curr_y'] = float(new_y)
                    self.char_anim[name]['move_start_time'] = current_time
        
        # Clean up removed characters
        active_names = {char['name'] for char in self.state.characters}
        to_remove = [name for name in self.char_anim if name not in active_names]
        for name in to_remove:
            del self.char_anim[name]
    
    def _get_interpolated_position(self, char):
        """Get smoothly interpolated position for rendering using real time"""
        name = char['name']
        current_time = pygame.time.get_ticks()
        
        if name not in self.char_anim:
            return float(char['x']), float(char['y'])
        
        anim = self.char_anim[name]
        
        # Check for teleportation (large distance) - no interpolation
        dx = anim['curr_x'] - anim['prev_x']
        dy = anim['curr_y'] - anim['prev_y']
        if abs(dx) > 2 or abs(dy) > 2:
            return anim['curr_x'], anim['curr_y']
        
        # Calculate interpolation based on real elapsed time
        elapsed = current_time - anim['move_start_time']
        base_duration = PLAYER_MOVE_DURATION_MS if anim.get('is_player', False) else NPC_MOVE_DURATION_MS
        
        # Scale animation duration with game speed (faster speed = faster animation)
        duration = base_duration / self.state.game_speed
        
        # Calculate progress (0.0 to 1.0) - LINEAR for constant speed
        t = min(1.0, elapsed / duration) if duration > 0 else 1.0
        
        # Interpolate between previous and current
        x = anim['prev_x'] + (anim['curr_x'] - anim['prev_x']) * t
        y = anim['prev_y'] + (anim['curr_y'] - anim['prev_y']) * t
        
        return x, y
    
    # =========================================================================
    # RENDERING
    # =========================================================================
    
    def _render_frame(self):
        """Render the current game state"""
        # Fill background
        self.screen.fill(self.BG_COLOR_RGB)
        
        # Draw components
        self._draw_info_bar()
        self._draw_control_buttons()
        self._draw_canvas()
        self._draw_status_bar()
        
        pygame.display.flip()
    
    def _draw_status_bar(self):
        """Draw a compact status bar at the bottom of the window"""
        bar_y = self.window_height - self.status_bar_height - 5
        bar_rect = pygame.Rect(10, bar_y, self.canvas_width, self.status_bar_height)
        pygame.draw.rect(self.screen, self.DEBUG_BG, bar_rect)
        
        # Time info
        year = (self.state.ticks // TICKS_PER_YEAR) + 1
        day = ((self.state.ticks % TICKS_PER_YEAR) // TICKS_PER_DAY) + 1
        day_progress = (self.state.ticks % TICKS_PER_DAY) / TICKS_PER_DAY * 100
        
        # Player info
        player = self.state.player
        if player:
            player_food = self.state.get_food(player)
            player_money = self.state.get_money(player)
            player_info = f"Pos:({player['x']},{player['y']}) Food:{player_food} ${player_money} HP:{player['health']}"
        else:
            player_info = "No player"
        
        paused_str = " [PAUSED]" if self.state.paused else ""
        status_text = f"Year {year} Day {day} ({day_progress:.0f}%){paused_str} | {player_info} | Pop: {len(self.state.characters)}"
        
        self.font_small.render_to(self.screen, (bar_rect.x + 5, bar_rect.y + 7), status_text, self.DEBUG_TEXT)
    
    def _draw_info_bar(self):
        """Draw the info bar at the top"""
        info_text = f"WASD to move | E to eat | T to trade | {VILLAGE_NAME}: VILLAGE (yellow), FARM (green), RUIN (gray)"
        self.font_large.render_to(self.screen, (10, 15), info_text, (0, 0, 0))
    
    def _draw_control_buttons(self):
        """Draw control buttons"""
        mouse_pos = pygame.mouse.get_pos()
        
        for name, rect in self.buttons.items():
            # Determine color based on hover
            color = self.BUTTON_HOVER if rect.collidepoint(mouse_pos) else self.BUTTON_BG
            pygame.draw.rect(self.screen, color, rect, border_radius=5)
            pygame.draw.rect(self.screen, (50, 50, 50), rect, 2, border_radius=5)
            
            # Draw button text
            if name == 'speed':
                text = f"Speed: {self.state.game_speed}x"
            elif name == 'pause':
                text = "Resume" if self.state.paused else "Pause"
            else:
                text = "Skip 1 Year"
            
            text_surface, text_rect = self.font_medium.render(text, self.BUTTON_TEXT)
            text_x = rect.centerx - text_rect.width // 2
            text_y = rect.centery - text_rect.height // 2
            self.screen.blit(text_surface, (text_x, text_y))
    
    def _draw_canvas(self):
        """Draw the game canvas"""
        canvas_x = 10
        canvas_y = self.info_bar_height + self.control_bar_height + 10
        
        # Draw grid cells
        for y in range(SIZE):
            for x in range(SIZE):
                cell_x = canvas_x + x * CELL_SIZE
                cell_y = canvas_y + y * CELL_SIZE
                
                # Get cell color
                color = self._get_cell_color(x, y)
                color_rgb = hex_to_rgb(color)
                
                # Draw cell
                pygame.draw.rect(self.screen, color_rgb, (cell_x, cell_y, CELL_SIZE, CELL_SIZE))
                pygame.draw.rect(self.screen, self.GRID_COLOR_RGB, (cell_x, cell_y, CELL_SIZE, CELL_SIZE), 1)
        
        # Draw barrels
        self._draw_barrels(canvas_x, canvas_y)
        
        # Draw beds
        self._draw_beds(canvas_x, canvas_y)
        
        # Draw camps
        self._draw_camps(canvas_x, canvas_y)
        
        # Draw characters
        self._draw_characters(canvas_x, canvas_y)
    
    def _draw_barrels(self, canvas_x, canvas_y):
        """Draw all barrels"""
        for pos, barrel in self.state.barrels.items():
            x, y = pos
            cell_x = canvas_x + x * CELL_SIZE
            cell_y = canvas_y + y * CELL_SIZE
            
            # Draw barrel as brown rectangle with "B"
            padding = 5
            barrel_rect = pygame.Rect(cell_x + padding, cell_y + padding, 
                                       CELL_SIZE - 2*padding, CELL_SIZE - 2*padding)
            pygame.draw.rect(self.screen, hex_to_rgb("#8B4513"), barrel_rect)
            pygame.draw.rect(self.screen, hex_to_rgb("#4a2500"), barrel_rect, 2)
            
            # Draw "B" text
            text_surface, text_rect = self.font_barrel.render("B", (255, 255, 255))
            text_x = cell_x + CELL_SIZE // 2 - text_rect.width // 2
            text_y = cell_y + CELL_SIZE // 2 - text_rect.height // 2
            self.screen.blit(text_surface, (text_x, text_y))
    
    def _draw_beds(self, canvas_x, canvas_y):
        """Draw all beds"""
        for pos, bed in self.state.beds.items():
            x, y = pos
            cell_x = canvas_x + x * CELL_SIZE
            cell_y = canvas_y + y * CELL_SIZE
            
            # Draw bed as blue rectangle with pillow
            padding = 4
            bed_rect = pygame.Rect(cell_x + padding, cell_y + padding,
                                    CELL_SIZE - 2*padding, CELL_SIZE - 2*padding)
            pygame.draw.rect(self.screen, hex_to_rgb("#4169E1"), bed_rect)
            pygame.draw.rect(self.screen, hex_to_rgb("#2a4494"), bed_rect, 2)
            
            # Draw pillow (small white rectangle at top)
            pillow_height = 8
            pillow_rect = pygame.Rect(cell_x + padding + 3, cell_y + padding + 2,
                                       CELL_SIZE - 2*padding - 6, pillow_height)
            pygame.draw.rect(self.screen, (255, 255, 255), pillow_rect)
            pygame.draw.rect(self.screen, (200, 200, 200), pillow_rect, 1)
    
    def _draw_camps(self, canvas_x, canvas_y):
        """Draw all camps"""
        for char in self.state.characters:
            camp_pos = char.get('camp_position')
            if camp_pos:
                x, y = camp_pos
                cell_x = canvas_x + x * CELL_SIZE
                cell_y = canvas_y + y * CELL_SIZE
                
                # Draw campfire (orange/red circle)
                fire_cx = cell_x + CELL_SIZE // 2
                fire_cy = cell_y + CELL_SIZE // 2
                pygame.draw.circle(self.screen, (255, 100, 0), (fire_cx, fire_cy), 8)
                pygame.draw.circle(self.screen, (255, 200, 0), (fire_cx, fire_cy), 5)
                pygame.draw.circle(self.screen, (255, 255, 100), (fire_cx, fire_cy), 2)
                
                # Draw bedroll next to fire
                bedroll_x = fire_cx + 10
                pygame.draw.ellipse(self.screen, (100, 80, 60),
                                   (bedroll_x - 3, fire_cy - 6, 8, 12))
    
    def _draw_characters(self, canvas_x, canvas_y):
        """Draw all characters with smooth interpolated positions"""
        for char in self.state.characters:
            # Get interpolated position for smooth movement
            vis_x, vis_y = self._get_interpolated_position(char)
            
            color = self._get_character_color(char)
            color_rgb = hex_to_rgb(color)
            
            # Calculate pixel position from interpolated grid position
            cell_x = canvas_x + vis_x * CELL_SIZE
            cell_y = canvas_y + vis_y * CELL_SIZE
            
            # Circle bounds (leaving room for name below)
            padding = 3
            circle_top = cell_y + padding
            circle_bottom = cell_y + CELL_SIZE - padding - 8
            circle_left = cell_x + padding
            circle_right = cell_x + CELL_SIZE - padding
            circle_cx = int((circle_left + circle_right) / 2)
            circle_cy = int((circle_top + circle_bottom) / 2)
            
            # Draw filled circle
            pygame.draw.ellipse(self.screen, color_rgb, 
                              (circle_left, circle_top, circle_right - circle_left, circle_bottom - circle_top))
            pygame.draw.ellipse(self.screen, (0, 0, 0),
                              (circle_left, circle_top, circle_right - circle_left, circle_bottom - circle_top), 1)
            
            # Draw eyes based on facing direction
            self._draw_character_eyes(char, circle_cx, circle_cy)
            
            # Draw first name below circle
            first_name = char['name'].split()[0]
            text_surface, text_rect = self.font_tiny.render(first_name, (0, 0, 0))
            text_x = cell_x + CELL_SIZE / 2 - text_rect.width / 2
            text_y = cell_y + CELL_SIZE - 12
            self.screen.blit(text_surface, (int(text_x), int(text_y)))
    
    def _draw_character_eyes(self, char, cx, cy):
        """Draw eyes based on facing direction"""
        facing = char.get('facing', 'down')
        eye_radius = 2
        eye_color = (255, 255, 255)
        pupil_color = (0, 0, 0)
        
        if facing == 'down':
            # Eyes on bottom half, looking down
            left_eye_x = cx - 5
            right_eye_x = cx + 5
            eye_y = cy + 3
            pupil_offset_x, pupil_offset_y = 0, 1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y, 
                                          eye_radius, eye_color, pupil_color, 
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'up':
            # Eyes on top half, looking up
            left_eye_x = cx - 5
            right_eye_x = cx + 5
            eye_y = cy - 3
            pupil_offset_x, pupil_offset_y = 0, -1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'left':
            # Eyes on left side, looking left
            eye_x = cx - 4
            top_eye_y = cy - 3
            bottom_eye_y = cy + 3
            pupil_offset_x, pupil_offset_y = -1, 0
            self._draw_eye_pair_vertical(eye_x, top_eye_y, bottom_eye_y,
                                        eye_radius, eye_color, pupil_color,
                                        pupil_offset_x, pupil_offset_y)
        
        elif facing == 'right':
            # Eyes on right side, looking right
            eye_x = cx + 4
            top_eye_y = cy - 3
            bottom_eye_y = cy + 3
            pupil_offset_x, pupil_offset_y = 1, 0
            self._draw_eye_pair_vertical(eye_x, top_eye_y, bottom_eye_y,
                                        eye_radius, eye_color, pupil_color,
                                        pupil_offset_x, pupil_offset_y)
        
        elif facing == 'up-left':
            # Eyes looking up-left (diagonal)
            left_eye_x = cx - 4
            right_eye_x = cx + 2
            eye_y = cy - 2
            pupil_offset_x, pupil_offset_y = -1, -1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'up-right':
            # Eyes looking up-right (diagonal)
            left_eye_x = cx - 2
            right_eye_x = cx + 4
            eye_y = cy - 2
            pupil_offset_x, pupil_offset_y = 1, -1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'down-left':
            # Eyes looking down-left (diagonal)
            left_eye_x = cx - 4
            right_eye_x = cx + 2
            eye_y = cy + 2
            pupil_offset_x, pupil_offset_y = -1, 1
            self._draw_eye_pair_horizontal(left_eye_x, right_eye_x, eye_y,
                                          eye_radius, eye_color, pupil_color,
                                          pupil_offset_x, pupil_offset_y)
        
        elif facing == 'down-right':
            # Eyes looking down-right (diagonal)
            left_eye_x = cx - 2
            right_eye_x = cx + 4
            eye_y = cy + 2
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
