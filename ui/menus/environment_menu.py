import pyray as rl
import time
from constants import (
    UI_COLOR_BOX_BG, UI_COLOR_BORDER, UI_COLOR_BORDER_INNER,
    UI_COLOR_TEXT, UI_COLOR_TEXT_DIM, UI_COLOR_HEADER_GREEN,
    UI_COLOR_OPTION_SELECTED, UI_COLOR_OPTION_HOVER,
    ENVIRONMENT_MENU_OPTIONS, ENVIRONMENT_BASE_OPTIONS, ENVIRONMENT_INTERACT_DISTANCE
)


# =============================================================================
# MENU UI CONFIGURATION
# =============================================================================

# Colors from shared UI constants
COLOR_BOX_BG = rl.Color(*UI_COLOR_BOX_BG)
COLOR_BOX_BORDER = rl.Color(*UI_COLOR_BORDER)
COLOR_BOX_BORDER_INNER = rl.Color(*UI_COLOR_BORDER_INNER)
COLOR_TEXT = rl.Color(*UI_COLOR_TEXT)
COLOR_TEXT_DIM = rl.Color(*UI_COLOR_TEXT_DIM)
COLOR_HEADER = rl.Color(*UI_COLOR_HEADER_GREEN)  # Greenish for environment
COLOR_CURSOR = rl.Color(*UI_COLOR_HEADER_GREEN)
COLOR_OPTION_SELECTED = rl.Color(*UI_COLOR_OPTION_SELECTED)
COLOR_OPTION_HOVER = rl.Color(*UI_COLOR_OPTION_HOVER)

# Layout
MENU_BOX_WIDTH = 160
MENU_BOX_MARGIN = 16
MENU_ITEM_HEIGHT = 28
MENU_PADDING = 8
MENU_BORDER_WIDTH = 3

# Cursor blink
CURSOR_BLINK_RATE = 0.5


class EnvironmentMenu:
    """
    Context-sensitive menu for environment interactions.
    """
    
    def __init__(self, game_state, game_logic):
        """
        Initialize the environment menu.
        
        Args:
            game_state: GameState instance
            game_logic: GameLogic instance
        """
        self.state = game_state
        self.logic = game_logic
        
        # Menu state
        self._active = False
        self._selected_option = 0
        self._options = []  # Current visible options
        
        # Animation state
        self._cursor_visible = True
        self._last_cursor_toggle = 0
        
        # Store bounds for mouse detection
        self._menu_bounds = None
        self._options_start_y = 0
    
    # =========================================================================
    # PROPERTIES
    # =========================================================================
    
    @property
    def is_active(self):
        """Whether the menu is currently active."""
        return self._active
    
    @property
    def selected_option(self):
        """Currently selected option text."""
        if 0 <= self._selected_option < len(self._options):
            return self._options[self._selected_option]
        return None
    
    # =========================================================================
    # ENVIRONMENT MENU CONTROL
    # =========================================================================
    
    def open(self):
        """Open the environment menu and build context-sensitive options."""
        if self._active:
            return
        
        self._active = True
        self._build_options()
        self._selected_option = 0
    
    def close(self):
        """Close the environment menu."""
        self._active = False
        self._options = []
        self._selected_option = 0
    
    def _build_options(self):
        """Build the list of available options based on player context."""
        self._options = []
        player = self.state.player

        if not player:
            self._options = [ENVIRONMENT_MENU_OPTIONS['EXIT']]
            return

        # Check for nearby barrel (same zone, within distance)
        nearby_barrel = self._get_nearby_barrel()
        if nearby_barrel:
            self._options.append(ENVIRONMENT_MENU_OPTIONS['PICK_UP_BARREL'])

        # Check for nearby corpse (same zone, within distance)
        nearby_corpse = self._get_nearby_corpse()
        if nearby_corpse:
            self._options.append(ENVIRONMENT_MENU_OPTIONS['PICK_UP_CORPSE'])

        # Check for nearby tree (exterior only, within distance)
        nearby_tree = self._get_nearby_tree()
        if nearby_tree:
            self._options.append(ENVIRONMENT_MENU_OPTIONS['CHOP_TREE'])

        # Check farm cell state at player position
        if self.logic.can_harvest_at(player):
            self._options.append(ENVIRONMENT_MENU_OPTIONS['HARVEST'])
        elif self.logic.can_plant_at(player):
            self._options.append(ENVIRONMENT_MENU_OPTIONS['PLANT'])

        # Check if can build campfire (outside village, not in interior)
        if self.logic.can_build_campfire(player) and self.logic.can_make_camp_at(player.x, player.y):
            self._options.append(ENVIRONMENT_MENU_OPTIONS['BUILD_CAMPFIRE'])

        # Always add base options
        self._options.extend(ENVIRONMENT_BASE_OPTIONS)
    
    def _get_nearby_barrel(self):
        """Find a barrel near the player in the same zone."""
        player = self.state.player
        if not player:
            return None
        return self.logic.get_nearby_barrel(player, max_distance=ENVIRONMENT_INTERACT_DISTANCE)

    def _get_nearby_corpse(self):
        """Find a corpse near the player in the same zone."""
        player = self.state.player
        if not player:
            return None
        return self.logic.get_nearby_corpse(player, max_distance=ENVIRONMENT_INTERACT_DISTANCE)

    def _get_nearby_tree(self):
        """Find a tree near the player (exterior only)."""
        player = self.state.player
        if not player:
            return None
        return self.logic.get_nearby_tree(player, max_distance=ENVIRONMENT_INTERACT_DISTANCE)
    
    # =========================================================================
    # INPUT HANDLING
    # =========================================================================
    
    def handle_input(self):
        """Handle input while menu is active. Returns selected action or None."""
        if not self._active:
            return None
        
        # Close on Tab, G, or B/X button (but don't trigger anything else)
        if rl.is_key_pressed(rl.KEY_TAB) or rl.is_key_pressed(rl.KEY_G):
            self.close()
            return "closed"
        
        # Check gamepad for close buttons (B or X)
        for i in range(4):
            if rl.is_gamepad_available(i):
                # B button closes
                if rl.is_gamepad_button_pressed(i, rl.GAMEPAD_BUTTON_RIGHT_FACE_RIGHT):
                    self.close()
                    return "closed"
                # X button closes (same button that opens)
                if rl.is_gamepad_button_pressed(i, rl.GAMEPAD_BUTTON_RIGHT_FACE_LEFT):
                    self.close()
                    return "closed"
                break
        
        # Navigate up
        if rl.is_key_pressed(rl.KEY_W) or rl.is_key_pressed(rl.KEY_UP):
            self._selected_option = (self._selected_option - 1) % len(self._options)
        
        # Navigate down
        if rl.is_key_pressed(rl.KEY_S) or rl.is_key_pressed(rl.KEY_DOWN):
            self._selected_option = (self._selected_option + 1) % len(self._options)
        
        # Gamepad navigation
        for i in range(4):
            if rl.is_gamepad_available(i):
                if rl.is_gamepad_button_pressed(i, rl.GAMEPAD_BUTTON_LEFT_FACE_UP):
                    self._selected_option = (self._selected_option - 1) % len(self._options)
                if rl.is_gamepad_button_pressed(i, rl.GAMEPAD_BUTTON_LEFT_FACE_DOWN):
                    self._selected_option = (self._selected_option + 1) % len(self._options)
                break
        
        # Select option
        selected_action = None
        
        if rl.is_key_pressed(rl.KEY_E) or rl.is_key_pressed(rl.KEY_ENTER):
            selected_action = self._select_current()
        
        # Gamepad A button
        for i in range(4):
            if rl.is_gamepad_available(i):
                if rl.is_gamepad_button_pressed(i, rl.GAMEPAD_BUTTON_RIGHT_FACE_DOWN):
                    selected_action = self._select_current()
                break
        
        # Mouse click
        if rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT):
            mouse_x = rl.get_mouse_x()
            mouse_y = rl.get_mouse_y()
            
            if self._menu_bounds:
                menu_x, menu_y, menu_width, menu_height = self._menu_bounds
                
                # Check if click is in menu
                if menu_x <= mouse_x <= menu_x + menu_width and menu_y <= mouse_y <= menu_y + menu_height:
                    # Find which option was clicked
                    for i in range(len(self._options)):
                        item_y = self._options_start_y + i * MENU_ITEM_HEIGHT
                        if item_y <= mouse_y <= item_y + MENU_ITEM_HEIGHT:
                            self._selected_option = i
                            selected_action = self._select_current()
                            break
        
        return selected_action
    
    def _select_current(self):
        """Select the current option and return the action."""
        if not self._options:
            return None

        option = self._options[self._selected_option]

        if option == ENVIRONMENT_MENU_OPTIONS['EXIT']:
            self.close()
            return "closed"

        # Handle new options with debug logging
        if option == ENVIRONMENT_MENU_OPTIONS['PICK_UP_BARREL']:
            barrel = self._get_nearby_barrel()
            if barrel:
                player_name = self.state.player.get_display_name() if self.state.player else "Player"
                self.state.log_action(f"{player_name} picked up {barrel.name} (not yet implemented)")
            self.close()
            return option

        if option == ENVIRONMENT_MENU_OPTIONS['PICK_UP_CORPSE']:
            corpse = self._get_nearby_corpse()
            if corpse:
                player_name = self.state.player.get_display_name() if self.state.player else "Player"
                self.state.log_action(f"{player_name} picked up corpse (not yet implemented)")
            self.close()
            return option

        if option == ENVIRONMENT_MENU_OPTIONS['CHOP_TREE']:
            tree = self._get_nearby_tree()
            if tree:
                player_name = self.state.player.get_display_name() if self.state.player else "Player"
                self.state.log_action(f"{player_name} chopped tree at ({tree.x}, {tree.y}) (not yet implemented)")
            self.close()
            return option

        # Return the action to be handled by GUI
        self.close()
        return option
    
    # =========================================================================
    # UPDATE
    # =========================================================================
    
    def update(self, dt):
        """Update menu animations."""
        if not self._active:
            return
        
        # Update cursor blink
        current_time = time.time()
        if current_time - self._last_cursor_toggle > CURSOR_BLINK_RATE:
            self._cursor_visible = not self._cursor_visible
            self._last_cursor_toggle = current_time
    
    # =========================================================================
    # RENDERING
    # =========================================================================
    
    def render(self, screen_width, screen_height):
        """
        Render the environment menu.
        
        Args:
            screen_width: Current screen width
            screen_height: Current screen height
        """
        if not self._active or not self._options:
            return
        
        # Calculate menu dimensions
        menu_height = len(self._options) * MENU_ITEM_HEIGHT + MENU_PADDING * 2 + 24
        menu_x = screen_width - MENU_BOX_WIDTH - MENU_BOX_MARGIN
        menu_y = (screen_height - menu_height) // 2  # Vertically centered
        
        # Store bounds for mouse detection
        self._menu_bounds = (menu_x, menu_y, MENU_BOX_WIDTH, menu_height)
        
        # Draw outer border
        rl.draw_rectangle(
            menu_x - MENU_BORDER_WIDTH,
            menu_y - MENU_BORDER_WIDTH,
            MENU_BOX_WIDTH + MENU_BORDER_WIDTH * 2,
            menu_height + MENU_BORDER_WIDTH * 2,
            COLOR_BOX_BORDER
        )
        
        # Draw inner border
        rl.draw_rectangle(
            menu_x - 1,
            menu_y - 1,
            MENU_BOX_WIDTH + 2,
            menu_height + 2,
            COLOR_BOX_BORDER_INNER
        )
        
        # Draw background
        rl.draw_rectangle(menu_x, menu_y, MENU_BOX_WIDTH, menu_height, COLOR_BOX_BG)
        
        # Draw header
        header_text = "Environment"
        header_x = menu_x + (MENU_BOX_WIDTH - rl.measure_text(header_text, 12)) // 2
        header_y = menu_y + 8
        rl.draw_text(header_text, header_x, header_y, 12, COLOR_HEADER)
        
        # Draw separator
        sep_y = header_y + 16
        rl.draw_line(
            menu_x + MENU_PADDING,
            sep_y,
            menu_x + MENU_BOX_WIDTH - MENU_PADDING,
            sep_y,
            COLOR_BOX_BORDER_INNER
        )
        
        # Draw options
        options_start_y = sep_y + 8
        self._options_start_y = options_start_y
        
        # Get mouse position for hover detection
        mouse_x = rl.get_mouse_x()
        mouse_y = rl.get_mouse_y()
        
        for i, option in enumerate(self._options):
            item_y = options_start_y + i * MENU_ITEM_HEIGHT
            
            # Check if mouse is hovering over this option
            is_hovered = (menu_x + 4 <= mouse_x <= menu_x + MENU_BOX_WIDTH - 4 and
                         item_y <= mouse_y <= item_y + MENU_ITEM_HEIGHT - 2)
            
            # Update selected option on hover
            if is_hovered:
                self._selected_option = i
            
            # Highlight selected option
            if i == self._selected_option:
                rl.draw_rectangle(
                    menu_x + 4,
                    item_y,
                    MENU_BOX_WIDTH - 8,
                    MENU_ITEM_HEIGHT - 2,
                    COLOR_OPTION_SELECTED
                )
                
                # Draw cursor
                cursor_x = menu_x + MENU_PADDING
                cursor_y = item_y + 6
                if self._cursor_visible:
                    rl.draw_text("▶", cursor_x, cursor_y, 12, COLOR_CURSOR)
            
            # Draw option text
            text_x = menu_x + MENU_PADDING + 16
            text_y = item_y + 6
            text_color = COLOR_TEXT if i == self._selected_option else COLOR_TEXT_DIM
            rl.draw_text(option, text_x, text_y, 14, text_color)
