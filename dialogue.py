# dialogue.py - Pokemon-style dialogue system for NPC interaction
"""
Dialogue system that provides:
- Pokemon-style dialogue box at the bottom of the screen
- Options menu on the right side
- Typewriter text effect
- Input handling when dialogue is active

Controls:
- E: Skip text animation (if still typing) or select current option
- W/S: Navigate options up/down
- Mouse: Hover to highlight, click to select

Usage:
    dialogue = DialogueSystem(game_state, game_logic)
    
    # In GUI input handling:
    if dialogue.is_active:
        dialogue.handle_input()
    elif input.interact and near_npc:
        dialogue.start_dialogue(npc)
    
    # In GUI rendering:
    dialogue.update(dt)
    dialogue.render(screen_width, screen_height)
"""

import pyray as rl
import time
import math
from constants import (
    ADJACENCY_DISTANCE,
    UI_COLOR_BOX_BG, UI_COLOR_BORDER, UI_COLOR_BORDER_INNER,
    UI_COLOR_TEXT, UI_COLOR_TEXT_DIM, UI_COLOR_CURSOR,
    UI_COLOR_OPTION_SELECTED, UI_COLOR_OPTION_HOVER
)


# =============================================================================
# DIALOGUE UI CONFIGURATION
# =============================================================================

# Colors from shared UI constants
COLOR_BOX_BG = rl.Color(*UI_COLOR_BOX_BG)
COLOR_BOX_BORDER = rl.Color(*UI_COLOR_BORDER)
COLOR_BOX_BORDER_INNER = rl.Color(*UI_COLOR_BORDER_INNER)
COLOR_TEXT = rl.Color(*UI_COLOR_TEXT)
COLOR_TEXT_DIM = rl.Color(*UI_COLOR_TEXT_DIM)
COLOR_SPEAKER = rl.Color(*UI_COLOR_CURSOR)
COLOR_CURSOR = rl.Color(*UI_COLOR_CURSOR)
COLOR_OPTION_SELECTED = rl.Color(*UI_COLOR_OPTION_SELECTED)
COLOR_OPTION_HOVER = rl.Color(*UI_COLOR_OPTION_HOVER)

# Layout
DIALOGUE_BOX_HEIGHT = 100
DIALOGUE_BOX_MARGIN = 16
DIALOGUE_BOX_PADDING = 16
DIALOGUE_BORDER_WIDTH = 3

OPTIONS_BOX_WIDTH = 140
OPTIONS_BOX_MARGIN = 16
OPTIONS_ITEM_HEIGHT = 28
OPTIONS_PADDING = 8

# Typewriter effect
CHARS_PER_SECOND = 40  # How fast text appears
CURSOR_BLINK_RATE = 0.5  # Seconds per blink cycle


# =============================================================================
# DIALOGUE OPTIONS
# =============================================================================

DIALOGUE_OPTIONS = [
    "Ask",
    "Intimidate",
    "Request",
    "Offer",
    "Trade",
    "Exit"
]


class DialogueSystem:
    """
    Handles NPC dialogue interactions with Pokemon-style UI.
    
    When active:
    - Blocks player movement and actions
    - Makes the NPC face the player and stop moving
    - Displays dialogue box with typewriter text effect
    - Shows options menu for player choices
    """
    
    def __init__(self, game_state, game_logic):
        """
        Initialize the dialogue system.
        
        Args:
            game_state: GameState instance
            game_logic: GameLogic instance
        """
        self.state = game_state
        self.logic = game_logic
        
        # Dialogue state
        self._active = False
        self._npc = None  # The NPC being talked to
        self._npc_original_intent = None  # Store NPC's intent to restore later
        self._npc_original_goal = None
        
        # Text display state
        self._full_text = ""
        self._displayed_chars = 0
        self._text_start_time = 0
        
        # Options menu state
        self._selected_option = 0
        self._options = DIALOGUE_OPTIONS.copy()
        
        # Animation state
        self._cursor_visible = True
        self._last_cursor_toggle = 0
    
    # =========================================================================
    # PROPERTIES
    # =========================================================================
    
    @property
    def is_active(self):
        """Whether dialogue is currently active."""
        return self._active
    
    @property
    def current_npc(self):
        """The NPC currently in dialogue, or None."""
        return self._npc
    
    # =========================================================================
    # DIALOGUE CONTROL
    # =========================================================================
    
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
    
    def start_dialogue(self, npc):
        """
        Start a dialogue with an NPC.
        
        Args:
            npc: Character to talk to
            
        Returns:
            True if dialogue started successfully
        """
        if not self.can_start_dialogue(npc):
            return False
        
        self._active = True
        self._npc = npc
        
        # Store NPC's current state to restore later
        self._npc_original_intent = npc.intent
        self._npc_original_goal = npc.goal
        
        # Make NPC face the player and stop moving
        self._make_npc_face_player()
        npc.vx = 0
        npc.vy = 0
        npc.goal = None  # Clear movement goal
        
        # Set up dialogue text
        self._full_text = "Can I help you?"
        self._displayed_chars = 0
        self._text_start_time = time.time()
        
        # Reset options
        self._selected_option = 0
        
        return True
    
    def end_dialogue(self):
        """End the current dialogue and restore NPC state."""
        if not self._active:
            return
        
        # Restore NPC state (only restore goal, let AI decide new intent)
        if self._npc:
            self._npc.goal = self._npc_original_goal
        
        # Clear dialogue state
        self._active = False
        self._npc = None
        self._npc_original_intent = None
        self._npc_original_goal = None
        self._full_text = ""
        self._displayed_chars = 0
    
    def _make_npc_face_player(self):
        """Make the NPC face toward the player (8-directional)."""
        player = self.state.player
        if not player or not self._npc:
            return
        
        npc = self._npc
        
        # Use prevailing coords for same-zone calculation
        if player.zone == npc.zone:
            dx = player.prevailing_x - npc.prevailing_x
            dy = player.prevailing_y - npc.prevailing_y
        else:
            dx = player.x - npc.x
            dy = player.y - npc.y
        
        # Determine 8-direction facing based on angle
        angle = math.atan2(dy, dx)
        
        # Convert to 8 directions (same logic as player facing in gui.py)
        if angle >= -math.pi/8 and angle < math.pi/8:
            npc.facing = 'right'
        elif angle >= math.pi/8 and angle < 3*math.pi/8:
            npc.facing = 'down-right'
        elif angle >= 3*math.pi/8 and angle < 5*math.pi/8:
            npc.facing = 'down'
        elif angle >= 5*math.pi/8 and angle < 7*math.pi/8:
            npc.facing = 'down-left'
        elif angle >= 7*math.pi/8 or angle < -7*math.pi/8:
            npc.facing = 'left'
        elif angle >= -7*math.pi/8 and angle < -5*math.pi/8:
            npc.facing = 'up-left'
        elif angle >= -5*math.pi/8 and angle < -3*math.pi/8:
            npc.facing = 'up'
        elif angle >= -3*math.pi/8 and angle < -math.pi/8:
            npc.facing = 'up-right'
    
    # =========================================================================
    # INPUT HANDLING
    # =========================================================================
    
    def handle_input(self):
        """
        Handle input while dialogue is active.
        
        Returns:
            True if input was consumed, False otherwise
        """
        if not self._active:
            return False
        
        # Check if text is still being revealed
        text_complete = self._displayed_chars >= len(self._full_text)
        
        # E to select current option (only when text is complete)
        if rl.is_key_pressed(rl.KEY_E):
            if not text_complete:
                # Skip to full text
                self._displayed_chars = len(self._full_text)
            else:
                # Confirm current selection
                self._select_option()
            return True
        
        # Only allow option navigation when text is complete
        if text_complete:
            # W/S to navigate options
            if rl.is_key_pressed(rl.KEY_W):
                self._selected_option = (self._selected_option - 1) % len(self._options)
                return True
            
            if rl.is_key_pressed(rl.KEY_S):
                self._selected_option = (self._selected_option + 1) % len(self._options)
                return True
            
            # Mouse selection handled in render (hover) and click
            if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
                # Check if mouse clicked on an option
                if self._handle_mouse_click():
                    return True
        
        # Consume all other input to prevent game actions
        return True
    
    def _handle_mouse_click(self):
        """
        Handle mouse click on options menu.
        
        Returns:
            True if an option was clicked
        """
        mouse_x = rl.get_mouse_x()
        mouse_y = rl.get_mouse_y()
        
        # Check if click is within options menu bounds
        # We need screen dimensions - get from last render
        if not hasattr(self, '_options_menu_bounds'):
            return False
        
        menu_x, menu_y, menu_width, menu_height, options_start_y = self._options_menu_bounds
        
        if menu_x <= mouse_x <= menu_x + menu_width:
            if options_start_y <= mouse_y <= menu_y + menu_height:
                # Calculate which option was clicked
                relative_y = mouse_y - options_start_y
                clicked_option = int(relative_y // OPTIONS_ITEM_HEIGHT)
                
                if 0 <= clicked_option < len(self._options):
                    self._selected_option = clicked_option
                    self._select_option()
                    return True
        
        return False
    
    def _select_option(self):
        """Handle selection of the current option."""
        option = self._options[self._selected_option]
        
        if option == "Exit":
            self.end_dialogue()
        else:
            # For now, other options just show a response and return to Exit
            # This can be expanded later
            self._full_text = f"[{option}] - Not yet implemented."
            self._displayed_chars = 0
            self._text_start_time = time.time()
            # Move selection to Exit
            self._selected_option = len(self._options) - 1
    
    # =========================================================================
    # UPDATE
    # =========================================================================
    
    def update(self, dt):
        """
        Update dialogue state (typewriter effect, cursor blink).
        
        Args:
            dt: Delta time in seconds
        """
        if not self._active:
            return
        
        # Update typewriter effect
        elapsed = time.time() - self._text_start_time
        target_chars = int(elapsed * CHARS_PER_SECOND)
        self._displayed_chars = min(target_chars, len(self._full_text))
        
        # Update cursor blink
        if time.time() - self._last_cursor_toggle > CURSOR_BLINK_RATE:
            self._cursor_visible = not self._cursor_visible
            self._last_cursor_toggle = time.time()
        
        # Keep NPC facing player and stationary
        if self._npc:
            self._npc.vx = 0
            self._npc.vy = 0
            self._make_npc_face_player()
    
    # =========================================================================
    # RENDERING
    # =========================================================================
    
    def render(self, screen_width, screen_height):
        """
        Render the dialogue UI.
        
        Args:
            screen_width: Current screen width
            screen_height: Current screen height
        """
        if not self._active:
            return
        
        self._render_dialogue_box(screen_width, screen_height)
        self._render_options_menu(screen_width, screen_height)
    
    def _render_dialogue_box(self, screen_width, screen_height):
        """Render the main dialogue box at the bottom of the screen."""
        # Calculate box dimensions
        box_x = DIALOGUE_BOX_MARGIN
        box_y = screen_height - DIALOGUE_BOX_HEIGHT - DIALOGUE_BOX_MARGIN
        box_width = screen_width - OPTIONS_BOX_WIDTH - (DIALOGUE_BOX_MARGIN * 3)
        box_height = DIALOGUE_BOX_HEIGHT
        
        # Draw outer border
        rl.draw_rectangle(
            box_x - DIALOGUE_BORDER_WIDTH,
            box_y - DIALOGUE_BORDER_WIDTH,
            box_width + DIALOGUE_BORDER_WIDTH * 2,
            box_height + DIALOGUE_BORDER_WIDTH * 2,
            COLOR_BOX_BORDER
        )
        
        # Draw inner border
        rl.draw_rectangle(
            box_x - 1,
            box_y - 1,
            box_width + 2,
            box_height + 2,
            COLOR_BOX_BORDER_INNER
        )
        
        # Draw background
        rl.draw_rectangle(box_x, box_y, box_width, box_height, COLOR_BOX_BG)
        
        # Draw speaker name
        speaker_name = self._npc.name if self._npc else "???"
        speaker_x = box_x + DIALOGUE_BOX_PADDING
        speaker_y = box_y + 8
        rl.draw_text(speaker_name, speaker_x, speaker_y, 14, COLOR_SPEAKER)
        
        # Draw separator line under speaker name
        line_y = speaker_y + 18
        rl.draw_line(
            box_x + DIALOGUE_BOX_PADDING,
            line_y,
            box_x + box_width - DIALOGUE_BOX_PADDING,
            line_y,
            COLOR_BOX_BORDER_INNER
        )
        
        # Draw dialogue text with typewriter effect
        text_x = box_x + DIALOGUE_BOX_PADDING
        text_y = line_y + 10
        displayed_text = self._full_text[:self._displayed_chars]
        
        # Word wrap the text
        max_width = box_width - (DIALOGUE_BOX_PADDING * 2)
        self._draw_wrapped_text(displayed_text, text_x, text_y, max_width, 16, COLOR_TEXT)
        
        # Draw blinking cursor at end of text if still typing
        if self._displayed_chars < len(self._full_text) and self._cursor_visible:
            # Measure text to find cursor position
            text_width = rl.measure_text(displayed_text, 16)
            cursor_x = text_x + text_width + 2
            cursor_y = text_y
            rl.draw_text("▌", cursor_x, cursor_y, 16, COLOR_CURSOR)
        
        # Draw "press space" hint if text is complete
        if self._displayed_chars >= len(self._full_text):
            hint_text = "▼"
            hint_x = box_x + box_width - DIALOGUE_BOX_PADDING - 10
            hint_y = box_y + box_height - 20
            if self._cursor_visible:
                rl.draw_text(hint_text, hint_x, hint_y, 14, COLOR_TEXT_DIM)
    
    def _render_options_menu(self, screen_width, screen_height):
        """Render the options menu on the right side."""
        # Only show options when text is complete
        if self._displayed_chars < len(self._full_text):
            return
        
        # Calculate menu dimensions
        menu_height = len(self._options) * OPTIONS_ITEM_HEIGHT + OPTIONS_PADDING * 2 + 24
        menu_x = screen_width - OPTIONS_BOX_WIDTH - OPTIONS_BOX_MARGIN
        menu_y = (screen_height - menu_height) // 2  # Vertically centered
        
        # Draw outer border
        rl.draw_rectangle(
            menu_x - DIALOGUE_BORDER_WIDTH,
            menu_y - DIALOGUE_BORDER_WIDTH,
            OPTIONS_BOX_WIDTH + DIALOGUE_BORDER_WIDTH * 2,
            menu_height + DIALOGUE_BORDER_WIDTH * 2,
            COLOR_BOX_BORDER
        )
        
        # Draw inner border
        rl.draw_rectangle(
            menu_x - 1,
            menu_y - 1,
            OPTIONS_BOX_WIDTH + 2,
            menu_height + 2,
            COLOR_BOX_BORDER_INNER
        )
        
        # Draw background
        rl.draw_rectangle(menu_x, menu_y, OPTIONS_BOX_WIDTH, menu_height, COLOR_BOX_BG)
        
        # Draw header
        header_text = "Action"
        header_x = menu_x + (OPTIONS_BOX_WIDTH - rl.measure_text(header_text, 12)) // 2
        header_y = menu_y + 8
        rl.draw_text(header_text, header_x, header_y, 12, COLOR_TEXT_DIM)
        
        # Draw separator
        sep_y = header_y + 16
        rl.draw_line(
            menu_x + OPTIONS_PADDING,
            sep_y,
            menu_x + OPTIONS_BOX_WIDTH - OPTIONS_PADDING,
            sep_y,
            COLOR_BOX_BORDER_INNER
        )
        
        # Draw options
        options_start_y = sep_y + 8
        
        # Store bounds for mouse click detection
        self._options_menu_bounds = (menu_x, menu_y, OPTIONS_BOX_WIDTH, menu_height, options_start_y)
        
        # Get mouse position for hover detection
        mouse_x = rl.get_mouse_x()
        mouse_y = rl.get_mouse_y()
        
        for i, option in enumerate(self._options):
            item_y = options_start_y + i * OPTIONS_ITEM_HEIGHT
            
            # Check if mouse is hovering over this option
            is_hovered = (menu_x + 4 <= mouse_x <= menu_x + OPTIONS_BOX_WIDTH - 4 and
                         item_y <= mouse_y <= item_y + OPTIONS_ITEM_HEIGHT - 2)
            
            # Update selected option on hover
            if is_hovered:
                self._selected_option = i
            
            # Highlight selected option
            if i == self._selected_option:
                rl.draw_rectangle(
                    menu_x + 4,
                    item_y,
                    OPTIONS_BOX_WIDTH - 8,
                    OPTIONS_ITEM_HEIGHT - 2,
                    COLOR_OPTION_SELECTED
                )
                
                # Draw cursor
                cursor_x = menu_x + OPTIONS_PADDING
                cursor_y = item_y + 6
                if self._cursor_visible:
                    rl.draw_text("▶", cursor_x, cursor_y, 12, COLOR_CURSOR)
            
            # Draw option text
            text_x = menu_x + OPTIONS_PADDING + 16
            text_y = item_y + 6
            text_color = COLOR_TEXT if i == self._selected_option else COLOR_TEXT_DIM
            rl.draw_text(option, text_x, text_y, 14, text_color)
    
    def _draw_wrapped_text(self, text, x, y, max_width, font_size, color):
        """Draw text with word wrapping."""
        words = text.split(' ')
        current_line = ""
        line_y = y
        line_height = font_size + 4
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            test_width = rl.measure_text(test_line, font_size)
            
            if test_width > max_width and current_line:
                # Draw current line and start new one
                rl.draw_text(current_line, x, line_y, font_size, color)
                line_y += line_height
                current_line = word
            else:
                current_line = test_line
        
        # Draw remaining text
        if current_line:
            rl.draw_text(current_line, x, line_y, font_size, color)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_nearest_interactable_npc(state, player, max_distance=ADJACENCY_DISTANCE):
    """
    Find the nearest NPC that the player can interact with.
    
    Args:
        state: GameState instance
        player: Player character
        max_distance: Maximum distance to check
        
    Returns:
        Nearest NPC character, or None if none in range
    """
    if not player:
        return None
    
    nearest_npc = None
    nearest_dist = float('inf')
    
    for char in state.characters:
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