# inventory_menu.py - Inventory, Status, and World Map menu system
"""
Handles the inventory screen overlay with three tabs:
- World: Transparent view of game world with inventory panel
- Status: Character skills and stats
- Map: World map (placeholder)

Extracted from gui.py to reduce file size and improve organization.
All item properties (sprites, colors, stack limits) come from constants.ITEMS.
"""

import os
import pyray as rl
from constants import (
    SKILLS, ITEMS,
    UI_COLOR_BOX_BG, UI_COLOR_BOX_BG_MEDIUM, UI_COLOR_BOX_BG_LIGHT,
    UI_COLOR_BORDER, UI_COLOR_BORDER_INNER,
    UI_COLOR_TEXT, UI_COLOR_TEXT_DIM, UI_COLOR_TEXT_FAINT,
    UI_COLOR_SLOT_BG, UI_COLOR_SLOT_ACTIVE, UI_COLOR_SLOT_SELECTED,
    UI_COLOR_SLOT_BORDER, UI_COLOR_SLOT_BORDER_SELECTED,
    UI_COLOR_OPTION_SELECTED
)


# =============================================================================
# ITEM HELPER FUNCTIONS - All read from constants.ITEMS
# =============================================================================

def get_item_info(item_type):
    """Get item info dict from ITEMS constant."""
    return ITEMS.get(item_type, {})

def get_stack_limit(item_type):
    """Get stack limit for an item type. Returns None for unlimited."""
    info = get_item_info(item_type)
    return info.get('stack_size', 99)  # Default to 99 if not defined

def get_item_sprite_path(item_type):
    """Get the sprite file path for an item type."""
    info = get_item_info(item_type)
    sprite_name = info.get('sprite')
    if sprite_name:
        return os.path.join('sprites', 'items', sprite_name)
    return None

def get_item_color(item_type):
    """Get the fallback color for an item type as rl.Color."""
    info = get_item_info(item_type)
    color_tuple = info.get('color', (128, 128, 128, 200))  # Gray default
    return rl.Color(*color_tuple)

def get_item_icon(item_type):
    """Get the fallback text icon for an item type."""
    info = get_item_info(item_type)
    return info.get('icon', '?')

# =============================================================================
# HUD STYLING CONSTANTS (shared with gui.py)
# =============================================================================
HUD_FONT_SIZE_SMALL = 10
HUD_FONT_SIZE_MEDIUM = 13
HUD_FONT_SIZE_LARGE = 16
HUD_BAR_HEIGHT = 4

# Colors - stat bars
COLOR_HEALTH = rl.Color(201, 76, 76, 255)      # Red
COLOR_STAMINA = rl.Color(92, 184, 92, 255)     # Green  
COLOR_FATIGUE = rl.Color(91, 192, 222, 255)    # Cyan
COLOR_HUNGER = rl.Color(217, 164, 65, 255)     # Gold/Orange

# Colors - UI from shared constants
COLOR_BOX_BG = rl.Color(*UI_COLOR_BOX_BG)
COLOR_BOX_BG_MEDIUM = rl.Color(*UI_COLOR_BOX_BG_MEDIUM)
COLOR_BOX_BG_LIGHT = rl.Color(*UI_COLOR_BOX_BG_LIGHT)
COLOR_TEXT_BRIGHT = rl.Color(*UI_COLOR_TEXT)
COLOR_TEXT_DIM = rl.Color(*UI_COLOR_TEXT_DIM)
COLOR_TEXT_FAINT = rl.Color(*UI_COLOR_TEXT_FAINT)

COLOR_BG_SLOT = rl.Color(*UI_COLOR_SLOT_BG)
COLOR_BG_SLOT_ACTIVE = rl.Color(*UI_COLOR_SLOT_ACTIVE)
COLOR_BG_SLOT_SELECTED = rl.Color(*UI_COLOR_SLOT_SELECTED)
COLOR_BORDER = rl.Color(*UI_COLOR_SLOT_BORDER)
COLOR_BORDER_SELECTED = rl.Color(*UI_COLOR_SLOT_BORDER_SELECTED)
COLOR_OPTION_SELECTED = rl.Color(*UI_COLOR_OPTION_SELECTED)


class InventoryMenu:
    """
    Manages the inventory screen overlay with tabs for World, Status, and Map.
    """
    
    def __init__(self, state):
        """
        Initialize the inventory menu.
        
        Args:
            state: GameState object for accessing player and game data
        """
        self.state = state
        self.is_open = False
        self.current_tab = 0  # 0=World, 1=Status, 2=Map
        
        # Canvas dimensions (set by GUI before rendering)
        self.canvas_width = 800
        self.canvas_height = 600
        
        # Input state (updated by GUI each frame)
        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_left_click = False
        self.mouse_right_click = False
        self.gamepad_connected = False
        
        # Navigation state for inventory slots
        # Sections: 'equipment_head', 'equipment_body', 'accessories', 'inventory'
        self.selected_section = 'inventory'  # Start in inventory section
        self.selected_slot = 0  # Index within current section
        
        # Held item state (Minecraft-style cursor item)
        self.held_item = None  # {'type': str, 'amount': int} or None
        
        # Slot geometry cache (populated during render for hit detection)
        self._slot_rects = {}  # {('section', index): (x, y, w, h)}
        
        # Context menu state
        self.context_menu_open = False
        self.context_menu_slot = None  # Index of slot the menu is for
        self.context_menu_options = []  # List of available options
        self.context_menu_selected = 0  # Currently highlighted option
        self.context_menu_rect = (0, 0, 0, 0)  # x, y, w, h for rendering
        
        # Input repeat delay for smooth navigation
        self._input_delay = 0.0
        self._input_repeat_delay = 0.15  # Seconds between repeated inputs when held
        self._input_initial_delay = 0.25  # Initial delay before repeat starts
        self._input_held_time = 0.0
        self._last_input_dir = None  # Track which direction is held
        
        # Gamepad deadzone
        self._stick_deadzone = 0.5
        
        # Layout mode (updated during render)
        self._compact_mode = False
        
        # Item sprites - loaded lazily on first use
        self._item_textures = {}  # {item_type: Texture2D}
        self._sprites_loaded = False
        
        # Scroll state for panels
        self._left_panel_scroll = 0.0  # Scroll offset for left inventory panel
        self._status_tab_scroll = 0.0  # Scroll offset for status/skills tab
        self._left_panel_content_height = 300  # Total content height (default, calculated during render)
        self._status_tab_content_height = 400  # Total content height for status tab (default)
        self._scroll_speed = 40  # Pixels per scroll tick
        
        # Scroll bar geometry (for click/drag detection)
        self._left_scroll_bar_rect = None  # (x, y, w, h) of left panel scroll bar
        self._status_scroll_bar_rect = None  # (x, y, w, h) of status tab scroll bar
        
        # Scroll bar dragging state
        self._dragging_left_scroll = False
        self._dragging_status_scroll = False
        self._drag_start_y = 0
        self._drag_start_scroll = 0
    
    def open(self):
        """Open the inventory menu."""
        self.is_open = True
        # Reset selection to inventory section
        self.selected_section = 'inventory'
        self.selected_slot = 0
        self._input_delay = 0.0
        self._last_input_dir = None
        # Reset scroll positions
        self._left_panel_scroll = 0.0
        self._status_tab_scroll = 0.0
        # Reset scroll bar state
        self._left_scroll_bar_rect = None
        self._status_scroll_bar_rect = None
        self._dragging_left_scroll = False
        self._dragging_status_scroll = False
    
    def close(self):
        """Close the inventory menu."""
        # Close context menu if open
        self.close_context_menu()
        # Return held item to inventory if any
        if self.held_item and self.state.player:
            self._return_held_item_to_inventory()
        self.held_item = None
        self.is_open = False
    
    def _return_held_item_to_inventory(self):
        """Return held item to first available inventory slot."""
        if not self.held_item or not self.state.player:
            return
        
        player = self.state.player
        inventory = player.inventory
        held_type = self.held_item['type']
        stack_limit = get_stack_limit(held_type)
        
        # First try to stack with existing items of same type
        for i, slot in enumerate(inventory):
            if slot and slot.get('type') == held_type:
                if stack_limit is None:
                    # Unlimited stacking - combine everything
                    slot['amount'] = slot.get('amount', 0) + self.held_item['amount']
                    self.held_item = None
                    return
                else:
                    space = stack_limit - slot.get('amount', 0)
                    if space > 0:
                        transfer = min(space, self.held_item['amount'])
                        slot['amount'] = slot.get('amount', 0) + transfer
                        self.held_item['amount'] -= transfer
                        if self.held_item['amount'] <= 0:
                            self.held_item = None
                            return
        
        # Then try empty slots
        for i, slot in enumerate(inventory):
            if slot is None:
                inventory[i] = self.held_item.copy()
                self.held_item = None
                return
        
        # If still holding item, it's lost (inventory full) - shouldn't happen normally
    
    def toggle(self):
        """Toggle the inventory menu open/closed."""
        if self.is_open:
            self.close()
        else:
            self.open()
    
    def next_tab(self):
        """Switch to the next tab."""
        self.current_tab = (self.current_tab + 1) % 3
        # Reset scroll for the new tab
        if self.current_tab == 1:
            self._status_tab_scroll = 0.0
    
    def prev_tab(self):
        """Switch to the previous tab."""
        self.current_tab = (self.current_tab - 1) % 3
        # Reset scroll for the new tab
        if self.current_tab == 1:
            self._status_tab_scroll = 0.0
    
    def update_input(self, mouse_x, mouse_y, mouse_left_click, gamepad_connected, mouse_right_click=False, shift_held=False):
        """Update input state from GUI."""
        self.mouse_x = mouse_x
        self.mouse_y = mouse_y
        self.mouse_left_click = mouse_left_click
        self.mouse_right_click = mouse_right_click
        self.gamepad_connected = gamepad_connected
        
        # Handle mouse clicks on inventory slots (but not if shift is held - that opens context menu)
        if self.is_open and not self.context_menu_open and (mouse_left_click or mouse_right_click) and not shift_held:
            clicked_slot = self._get_slot_at_mouse()
            if clicked_slot:
                section, index = clicked_slot
                if section == 'inventory':
                    if mouse_left_click:
                        self._interact_slot_full(index)
                    elif mouse_right_click:
                        self._interact_slot_single(index)
    
    def update_scroll(self):
        """Handle scroll input - call this every frame when menu is open.
        
        Handles:
        - Mouse wheel scrolling
        - Scroll bar dragging
        - Gamepad right stick scrolling
        - Keyboard Page Up/Down
        """
        if not self.is_open:
            return
        
        # Calculate panel boundaries
        min_width = 200
        max_width = min(320, int(self.canvas_width * 0.4))
        left_width = max(min_width, min(max_width, self.canvas_width // 3))
        
        # Determine which panel mouse is over
        mouse_over_left = self.mouse_x < left_width
        mouse_over_right = self.mouse_x >= left_width
        
        # === MOUSE WHEEL SCROLLING ===
        wheel_move = rl.get_mouse_wheel_move()
        if wheel_move != 0:
            scroll_amount = wheel_move * self._scroll_speed
            if mouse_over_left:
                self._apply_left_panel_scroll(-scroll_amount)
            elif mouse_over_right and self.current_tab == 1:
                self._apply_status_tab_scroll(-scroll_amount)
        
        # === SCROLL BAR DRAGGING ===
        mouse_down = rl.is_mouse_button_down(rl.MOUSE_BUTTON_LEFT)
        mouse_pressed = rl.is_mouse_button_pressed(rl.MOUSE_BUTTON_LEFT)
        
        # Check for scroll bar interaction
        if mouse_pressed:
            # Check if clicking on left panel scroll bar
            if self._left_scroll_bar_rect:
                bx, by, bw, bh = self._left_scroll_bar_rect
                if bx <= self.mouse_x <= bx + bw and by <= self.mouse_y <= by + bh:
                    self._dragging_left_scroll = True
                    self._drag_start_y = self.mouse_y
                    self._drag_start_scroll = self._left_panel_scroll
            
            # Check if clicking on status tab scroll bar
            if self._status_scroll_bar_rect and self.current_tab == 1:
                bx, by, bw, bh = self._status_scroll_bar_rect
                if bx <= self.mouse_x <= bx + bw and by <= self.mouse_y <= by + bh:
                    self._dragging_status_scroll = True
                    self._drag_start_y = self.mouse_y
                    self._drag_start_scroll = self._status_tab_scroll
        
        if not mouse_down:
            self._dragging_left_scroll = False
            self._dragging_status_scroll = False
        
        # Handle active dragging
        if self._dragging_left_scroll and self._left_panel_content_height > 0:
            available_height = self.canvas_height
            max_scroll = max(0, self._left_panel_content_height - available_height)
            if max_scroll > 0:
                drag_delta = self.mouse_y - self._drag_start_y
                # Convert pixel drag to scroll amount (scroll bar track is ~canvas_height)
                scroll_ratio = drag_delta / (available_height - 40)  # 40 = approximate thumb height
                new_scroll = self._drag_start_scroll + scroll_ratio * max_scroll
                self._left_panel_scroll = max(0, min(max_scroll, new_scroll))
        
        if self._dragging_status_scroll and self._status_tab_content_height > 0:
            tab_height = 40
            content_height = self.canvas_height - tab_height - 48
            max_scroll = max(0, self._status_tab_content_height - content_height)
            if max_scroll > 0:
                drag_delta = self.mouse_y - self._drag_start_y
                scroll_ratio = drag_delta / (content_height - 40)
                new_scroll = self._drag_start_scroll + scroll_ratio * max_scroll
                self._status_tab_scroll = max(0, min(max_scroll, new_scroll))
        
        # === KEYBOARD SCROLLING ===
        if rl.is_key_pressed(rl.KEY_PAGE_DOWN) or rl.is_key_pressed(rl.KEY_PAGE_UP):
            scroll_amount = self._scroll_speed * 5  # Page = 5x normal scroll
            if rl.is_key_pressed(rl.KEY_PAGE_UP):
                scroll_amount = -scroll_amount
            
            if self.current_tab == 1:
                self._apply_status_tab_scroll(scroll_amount)
            else:
                self._apply_left_panel_scroll(scroll_amount)
        
        # === GAMEPAD SCROLLING (Right Stick) ===
        if self.gamepad_connected:
            for i in range(4):
                if rl.is_gamepad_available(i):
                    # Right stick Y axis for scrolling
                    right_y = rl.get_gamepad_axis_movement(i, rl.GAMEPAD_AXIS_RIGHT_Y)
                    if abs(right_y) > 0.2:  # Deadzone
                        scroll_amount = right_y * self._scroll_speed * 0.8
                        if self.current_tab == 1:
                            self._apply_status_tab_scroll(scroll_amount)
                        else:
                            self._apply_left_panel_scroll(scroll_amount)
                    break
    
    def _apply_left_panel_scroll(self, delta):
        """Apply scroll delta to left panel with bounds checking."""
        available_height = self.canvas_height - 16
        max_scroll = max(0, self._left_panel_content_height - available_height)
        self._left_panel_scroll = max(0, min(max_scroll, self._left_panel_scroll + delta))
    
    def _apply_status_tab_scroll(self, delta):
        """Apply scroll delta to status tab with bounds checking."""
        tab_height = 40
        content_height = self.canvas_height - tab_height - 48
        max_scroll = max(0, self._status_tab_content_height - content_height)
        self._status_tab_scroll = max(0, min(max_scroll, self._status_tab_scroll + delta))
    
    def _get_slot_at_mouse(self):
        """Get the slot (section, index) under the mouse cursor, or None."""
        for (section, index), (x, y, w, h) in self._slot_rects.items():
            if x <= self.mouse_x < x + w and y <= self.mouse_y < y + h:
                return (section, index)
        return None
    
    def _interact_slot_full(self, slot_index):
        """
        Left click interaction - pick up / place / swap full stack.
        Minecraft-style: pick up entire stack, or place entire held stack.
        """
        if not self.state.player:
            return
        
        player = self.state.player
        inventory = player.inventory
        
        if slot_index < 0 or slot_index >= len(inventory):
            return
        
        slot_item = inventory[slot_index]
        
        if self.held_item is None:
            # Pick up entire stack from slot
            if slot_item is not None:
                self.held_item = slot_item.copy()
                inventory[slot_index] = None
        else:
            # We're holding something
            if slot_item is None:
                # Place entire held stack in empty slot
                inventory[slot_index] = self.held_item.copy()
                self.held_item = None
            elif slot_item.get('type') == self.held_item.get('type'):
                # Same type - try to stack
                stack_limit = get_stack_limit(slot_item.get('type'))
                if stack_limit is None:
                    # Unlimited stacking - combine everything
                    slot_item['amount'] = slot_item.get('amount', 0) + self.held_item['amount']
                    self.held_item = None
                else:
                    space = stack_limit - slot_item.get('amount', 0)
                    if space > 0:
                        transfer = min(space, self.held_item['amount'])
                        slot_item['amount'] = slot_item.get('amount', 0) + transfer
                        self.held_item['amount'] -= transfer
                        if self.held_item['amount'] <= 0:
                            self.held_item = None
                    else:
                        # Stack full - swap
                        inventory[slot_index] = self.held_item.copy()
                        self.held_item = slot_item.copy()
            else:
                # Different type - swap
                inventory[slot_index] = self.held_item.copy()
                self.held_item = slot_item.copy()
    
    def _interact_slot_single(self, slot_index):
        """
        Right click interaction - pick up half / place single.
        Minecraft-style: pick up half stack, or place single item.
        """
        if not self.state.player:
            return
        
        player = self.state.player
        inventory = player.inventory
        
        if slot_index < 0 or slot_index >= len(inventory):
            return
        
        slot_item = inventory[slot_index]
        
        if self.held_item is None:
            # Pick up half of stack from slot
            if slot_item is not None:
                total = slot_item.get('amount', 1)
                take = (total + 1) // 2  # Ceiling division - take the larger half
                leave = total - take
                
                self.held_item = {'type': slot_item['type'], 'amount': take}
                
                if leave > 0:
                    slot_item['amount'] = leave
                else:
                    inventory[slot_index] = None
        else:
            # We're holding something - place single item
            if slot_item is None:
                # Place 1 item in empty slot
                inventory[slot_index] = {'type': self.held_item['type'], 'amount': 1}
                self.held_item['amount'] -= 1
                if self.held_item['amount'] <= 0:
                    self.held_item = None
            elif slot_item.get('type') == self.held_item.get('type'):
                # Same type - place 1 if room
                stack_limit = get_stack_limit(slot_item.get('type'))
                # None means unlimited, so always allow; otherwise check limit
                if stack_limit is None or slot_item.get('amount', 0) < stack_limit:
                    slot_item['amount'] = slot_item.get('amount', 0) + 1
                    self.held_item['amount'] -= 1
                    if self.held_item['amount'] <= 0:
                        self.held_item = None
            # Different type - do nothing (can't place)
    
    def handle_item_interaction(self, full_interact=False, single_interact=False):
        """
        Handle gamepad item interactions on the currently selected slot.
        
        Args:
            full_interact: A button pressed - pick up/place full stack
            single_interact: X button pressed - pick up half/place single
        """
        if not self.is_open:
            return
        
        # Only interact with inventory slots for now
        if self.selected_section == 'inventory':
            if full_interact:
                self._interact_slot_full(self.selected_slot)
            elif single_interact:
                self._interact_slot_single(self.selected_slot)
    
    # =========================================================================
    # CONTEXT MENU METHODS
    # =========================================================================
    
    def open_context_menu(self, slot_index=None):
        """
        Open context menu for the specified slot or currently selected slot.
        
        Args:
            slot_index: Slot to open menu for, or None to use selected slot
        """
        if slot_index is None:
            slot_index = self.selected_slot
        
        # Can only open for inventory slots
        if self.selected_section != 'inventory':
            return
        
        # Get item in slot
        if not self.state.player:
            return
        
        inventory = self.state.player.inventory
        if slot_index < 0 or slot_index >= len(inventory):
            return
        
        item = inventory[slot_index]
        if item is None:
            return  # No item, no menu
        
        # Get available options for this item
        options = self._get_context_options(item)
        if not options:
            return  # No options available
        
        self.context_menu_open = True
        self.context_menu_slot = slot_index
        self.context_menu_options = options
        self.context_menu_selected = 0
    
    def close_context_menu(self):
        """Close the context menu."""
        self.context_menu_open = False
        self.context_menu_slot = None
        self.context_menu_options = []
        self.context_menu_selected = 0
    
    def _get_context_options(self, item):
        """
        Get available context menu options for an item.
        
        Args:
            item: Item dict with 'type' and 'amount'
            
        Returns:
            List of option strings
        """
        options = []
        item_type = item.get('type', '')
        
        # Bread can be eaten
        if item_type == 'bread':
            options.append('Use')
        
        # Only show menu if there are options
        if options:
            options.append('Cancel')
        
        return options
    
    def handle_context_menu_input(self, nav_up=False, nav_down=False, select=False, cancel=False):
        """
        Handle input for the context menu.
        
        Args:
            nav_up: Navigate up pressed
            nav_down: Navigate down pressed  
            select: Select/confirm pressed
            cancel: Cancel/back pressed
            
        Returns:
            True if input was consumed
        """
        if not self.context_menu_open:
            return False
        
        if cancel:
            self.close_context_menu()
            return True
        
        if nav_up:
            self.context_menu_selected = (self.context_menu_selected - 1) % len(self.context_menu_options)
            return True
        
        if nav_down:
            self.context_menu_selected = (self.context_menu_selected + 1) % len(self.context_menu_options)
            return True
        
        if select:
            self._execute_context_action()
            return True
        
        return False
    
    def _execute_context_action(self):
        """Execute the currently selected context menu action."""
        if not self.context_menu_open or not self.context_menu_options:
            return
        
        action = self.context_menu_options[self.context_menu_selected]
        slot_index = self.context_menu_slot
        
        if action == 'Cancel':
            self.close_context_menu()
            return
        
        if not self.state.player:
            self.close_context_menu()
            return
        
        player = self.state.player
        inventory = player.inventory
        if slot_index < 0 or slot_index >= len(inventory):
            self.close_context_menu()
            return
        
        item = inventory[slot_index]
        if item is None:
            self.close_context_menu()
            return
        
        if action == 'Use':
            self._use_item(slot_index, item)
        
        self.close_context_menu()
    
    def _use_item(self, slot_index, item):
        """
        Use/consume an item from a specific inventory slot.
        
        Args:
            slot_index: Inventory slot index
            item: Item dict
        """
        player = self.state.player
        item_type = item.get('type', '')
        
        # For bread, call the character's eat() method
        if item_type == 'bread':
            result = player.eat()
            if result['success']:
                msg = f"{player.get_display_name()} ate bread, hunger now {player.hunger:.0f}"
                if result.get('recovered_from_starvation'):
                    msg = f"{player.get_display_name()} ate bread and recovered from starvation! Hunger: {player.hunger:.0f}"
                self.state.log_action(msg)
    
    def handle_input(self, dt=None):
        """
        Handle navigation input for the inventory menu (gamepad only).
        
        Args:
            dt: Delta time in seconds (if None, uses rl.get_frame_time())
            
        Returns:
            True if input was consumed, False otherwise
        """
        if not self.is_open:
            return False
        
        # Only handle gamepad navigation
        if not self.gamepad_connected:
            return False
        
        # Use Raylib's frame time if not provided
        if dt is None:
            dt = rl.get_frame_time()
        
        # Get directional input from gamepad only
        dx, dy = 0, 0
        
        # Gamepad input (left stick)
        for i in range(4):
            if rl.is_gamepad_available(i):
                stick_x = rl.get_gamepad_axis_movement(i, rl.GAMEPAD_AXIS_LEFT_X)
                stick_y = rl.get_gamepad_axis_movement(i, rl.GAMEPAD_AXIS_LEFT_Y)
                
                if abs(stick_x) > self._stick_deadzone:
                    dx = 1 if stick_x > 0 else -1
                if abs(stick_y) > self._stick_deadzone:
                    dy = 1 if stick_y > 0 else -1
                
                # Also check D-pad
                if rl.is_gamepad_button_down(i, rl.GAMEPAD_BUTTON_LEFT_FACE_LEFT):
                    dx = -1
                elif rl.is_gamepad_button_down(i, rl.GAMEPAD_BUTTON_LEFT_FACE_RIGHT):
                    dx = 1
                if rl.is_gamepad_button_down(i, rl.GAMEPAD_BUTTON_LEFT_FACE_UP):
                    dy = -1
                elif rl.is_gamepad_button_down(i, rl.GAMEPAD_BUTTON_LEFT_FACE_DOWN):
                    dy = 1
                break
        
        # Handle input with repeat delay
        current_dir = (dx, dy)
        
        if dx == 0 and dy == 0:
            # No input - reset
            self._input_delay = 0.0
            self._input_held_time = 0.0
            self._last_input_dir = None
            return False
        
        # Check if this is a new direction or continuing the same
        if current_dir != self._last_input_dir:
            # New direction - process immediately
            self._last_input_dir = current_dir
            self._input_held_time = 0.0
            self._input_delay = self._input_initial_delay
            self._navigate(dx, dy)
            return True
        else:
            # Same direction held - use repeat delay
            self._input_held_time += dt
            self._input_delay -= dt
            
            if self._input_delay <= 0:
                self._input_delay = self._input_repeat_delay
                self._navigate(dx, dy)
                return True
        
        return True  # Input is being processed (held)
    
    def _navigate(self, dx, dy):
        """
        Navigate within the inventory based on direction.
        
        Args:
            dx: Horizontal direction (-1, 0, 1)
            dy: Vertical direction (-1, 0, 1)
        """
        section = self.selected_section
        slot = self.selected_slot
        
        # Layout (top to bottom):
        # - equipment (Head and Body side by side)
        # - accessories (2 rows of 4)
        # - inventory (5 slots in 1 row)
        
        if section == 'inventory':
            if dx != 0:
                slot = (slot + dx) % 5
            if dy < 0:  # Up to accessories
                section = 'accessories'
                slot = min(4 + min(slot, 3), 7)
        
        elif section == 'accessories':
            row = slot // 4
            col = slot % 4
            
            if dx != 0:
                col = (col + dx) % 4
                slot = row * 4 + col
            
            if dy > 0:  # Down
                if row == 0:
                    slot = 4 + col
                else:
                    section = 'inventory'
                    slot = min(col, 4)
            elif dy < 0:  # Up
                if row == 1:
                    slot = col
                else:
                    # Go to equipment (head or body based on column)
                    if col < 2:
                        section = 'equipment_head'
                    else:
                        section = 'equipment_body'
                    slot = 0
        
        elif section == 'equipment_head':
            if dx > 0:  # Right to body
                section = 'equipment_body'
                slot = 0
            elif dx < 0:  # Wrap to body
                section = 'equipment_body'
                slot = 0
            if dy > 0:  # Down to accessories
                section = 'accessories'
                slot = 0
        
        elif section == 'equipment_body':
            if dx < 0:  # Left to head
                section = 'equipment_head'
                slot = 0
            elif dx > 0:  # Wrap to head
                section = 'equipment_head'
                slot = 0
            if dy > 0:  # Down to accessories
                section = 'accessories'
                slot = 2
        
        self.selected_section = section
        self.selected_slot = slot
    
    def set_canvas_size(self, width, height):
        """Set canvas dimensions for rendering."""
        self.canvas_width = width
        self.canvas_height = height
    
    def render(self):
        """Render the inventory screen overlay."""
        if not self.is_open:
            return
        
        player = self.state.player
        if not player:
            return
        
        # Clear slot rects for fresh hit detection
        self._slot_rects.clear()
        
        # Responsive left panel width
        # Minimum: 200px, Maximum: 320px or 40% of screen (whichever is smaller)
        min_width = 200
        max_width = min(320, int(self.canvas_width * 0.4))
        left_width = max(min_width, min(max_width, self.canvas_width // 3))
        right_width = self.canvas_width - left_width
        
        # Only draw overlay on non-world tabs
        if self.current_tab != 0:
            # Semi-transparent overlay on right side only
            rl.draw_rectangle(left_width, 0, right_width, self.canvas_height, 
                             COLOR_BOX_BG_MEDIUM)
        
        # Left panel background (always drawn)
        rl.draw_rectangle(0, 0, left_width, self.canvas_height, COLOR_BOX_BG)
        rl.draw_line(left_width, 0, left_width, self.canvas_height, COLOR_BORDER)
        
        # Draw left panel content
        self._draw_left_panel(player, 0, 0, left_width)
        
        # Draw right panel with tabs (handles click detection)
        self._draw_right_panel(player, left_width, 0, right_width)
        
        # Draw held item at cursor/center
        self._draw_held_item()
        
        # Draw control hints in bottom right of right panel (only on World tab)
        if self.current_tab == 0:
            self._draw_control_hints(left_width, right_width)
        
        # Draw context menu on top of everything
        self._draw_context_menu()
    
    def _draw_left_panel(self, player, x, y, width):
        """Draw the left inventory panel with equipment and storage."""
        padding = 8
        inner_x = x + padding
        inner_width = width - padding * 2
        
        # Determine layout mode based on available width
        # Compact mode: < 240px inner width
        compact_mode = inner_width < 240
        self._compact_mode = compact_mode  # Store for navigation
        
        # Calculate slot size to fit 5 inventory slots
        max_slot_size = 36
        min_slot_size = 28
        slot_gap = 4
        available_for_slots = inner_width - (slot_gap * 4)
        calculated_slot_size = available_for_slots // 5
        slot_size = max(min_slot_size, min(max_slot_size, calculated_slot_size))
        
        # Calculate total content height to determine if scrolling is needed
        # Status bar: ~50-70px, Equipment area: ~100-140px, Inventory: ~60px
        status_height = 70 if compact_mode else 50
        equip_height = 140 if compact_mode else 100
        inventory_height = slot_size + 24
        total_content_height = padding + status_height + 8 + equip_height + 8 + inventory_height + padding
        self._left_panel_content_height = total_content_height
        
        # Available height for content
        available_height = self.canvas_height
        needs_scroll = total_content_height > available_height
        
        # Clamp scroll offset
        if needs_scroll:
            max_scroll = total_content_height - available_height
            self._left_panel_scroll = max(0, min(max_scroll, self._left_panel_scroll))
        else:
            self._left_panel_scroll = 0
        
        # Apply scroll offset
        scroll_y = -int(self._left_panel_scroll)
        inner_y = y + padding + scroll_y
        
        # Enable scissor mode for clipping
        rl.begin_scissor_mode(x, y, width, self.canvas_height)
        
        # === STATUS BAR (Health, Hunger, Weight, Gold) ===
        actual_status_height = self._draw_status_bar(player, inner_x, inner_y, inner_width, compact_mode)
        inner_y += actual_status_height + 8
        
        # === EQUIPMENT AREA (Head/Body + Accessories) ===
        actual_equip_height = self._draw_equipment_area(player, inner_x, inner_y, inner_width, slot_size, compact_mode)
        inner_y += actual_equip_height + 8
        
        # === BASE INVENTORY (5 slots) ===
        self._draw_storage_section(player, inner_x, inner_y, inner_width, "Base Inventory", 5, slot_size)
        
        # End scissor mode
        rl.end_scissor_mode()
        
        # Draw scroll indicator if needed
        if needs_scroll:
            self._draw_scroll_indicator(x + width - 12, y, 10, self.canvas_height, 
                                       self._left_panel_scroll, total_content_height, available_height)
    
    def _draw_status_bar(self, player, x, y, width, compact_mode=False):
        """Draw compact status bar with health, hunger, stamina, fatigue, encumbrance, gold.
        
        Returns:
            Height of the status bar drawn
        """
        # Stats with consistent HUD-style formatting
        stats = [
            ("HP", player.health, 100, COLOR_HEALTH),
            ("S", player.stamina, 100, COLOR_STAMINA),
            ("E", 100 - player.fatigue, 100, COLOR_FATIGUE),
            ("H", player.hunger, 100, COLOR_HUNGER),
        ]
        
        if compact_mode:
            # 2x2 grid layout for narrow screens
            bar_height = 70
            rl.draw_rectangle(x, y, width, bar_height, rl.Color(255, 255, 255, 8))
            rl.draw_rectangle_lines(x, y, width, bar_height, COLOR_BORDER)
            
            # Calculate cell width for 2 columns
            cell_width = (width - 16) // 2
            bar_w = min(30, cell_width - 45)
            
            for i, (icon, value, max_val, color) in enumerate(stats):
                col = i % 2
                row = i // 2
                stat_x = x + 8 + col * (cell_width + 4)
                stat_y = y + 8 + row * 22
                
                pct = max(0, min(1, value / max_val))
                is_low = pct < 0.25
                
                # Icon
                icon_color = color if is_low else COLOR_TEXT_DIM
                icon_w = rl.measure_text(icon, 10)
                rl.draw_text(icon, stat_x, stat_y, 10, icon_color)
                
                # Bar
                bar_x = stat_x + icon_w + 4
                rl.draw_rectangle(bar_x, stat_y + 3, bar_w, HUD_BAR_HEIGHT, rl.Color(255, 255, 255, 25))
                fill_width = int(bar_w * pct)
                if fill_width > 0:
                    rl.draw_rectangle(bar_x, stat_y + 3, fill_width, HUD_BAR_HEIGHT,
                                     rl.Color(color.r, color.g, color.b, 220))
                
                # Value
                value_str = str(int(value))
                text_color = color if is_low else COLOR_TEXT_DIM
                rl.draw_text(value_str, bar_x + bar_w + 4, stat_y, 9, text_color)
            
            # Encumbrance and Gold on bottom row
            bottom_y = y + 52
            rl.draw_text("Wt", x + 8, bottom_y, 9, COLOR_TEXT_DIM)
            rl.draw_text("0/100", x + 24, bottom_y, 9, COLOR_TEXT_FAINT)
            
            gold = player.get_item('gold')
            gold_str = f"${gold:,}"
            gold_width = rl.measure_text(gold_str, 11)
            rl.draw_text(gold_str, x + width - gold_width - 8, bottom_y, 11, 
                        rl.Color(255, 215, 0, 255))
            
            return bar_height
        else:
            # Row layout for wider screens
            bar_height = 50
            rl.draw_rectangle(x, y, width, bar_height, rl.Color(255, 255, 255, 8))
            rl.draw_rectangle_lines(x, y, width, bar_height, COLOR_BORDER)
            
            # Calculate bar width based on available space
            # Each stat needs: icon + bar + value + gap
            available = width - 16  # padding
            stat_width = available // 4
            bar_w = max(20, min(30, stat_width - 40))
            
            stat_x = x + 8
            stat_y = y + 10
            
            for icon, value, max_val, color in stats:
                pct = max(0, min(1, value / max_val))
                is_low = pct < 0.25
                
                icon_color = color if is_low else COLOR_TEXT_DIM
                icon_width = rl.measure_text(icon, 10)
                rl.draw_text(icon, stat_x, stat_y, 10, icon_color)
                
                bar_x = stat_x + icon_width + 4
                rl.draw_rectangle(bar_x, stat_y + 3, bar_w, HUD_BAR_HEIGHT, rl.Color(255, 255, 255, 25))
                
                fill_width = int(bar_w * pct)
                if fill_width > 0:
                    rl.draw_rectangle(bar_x, stat_y + 3, fill_width, HUD_BAR_HEIGHT, 
                                     rl.Color(color.r, color.g, color.b, 220))
                
                value_str = str(int(value))
                text_color = color if is_low else COLOR_TEXT_DIM
                rl.draw_text(value_str, bar_x + bar_w + 4, stat_y, 9, text_color)
                
                stat_x += stat_width
            
            # Encumbrance on second row
            enc_y = y + 32
            rl.draw_text("Wt", x + 8, enc_y, 9, COLOR_TEXT_DIM)
            rl.draw_text("0/100", x + 24, enc_y, 9, COLOR_TEXT_FAINT)
            
            # Gold - align with encumbrance row
            gold = player.get_item('gold')
            gold_str = f"${gold:,}"
            gold_width = rl.measure_text(gold_str, 11)
            rl.draw_text(gold_str, x + width - gold_width - 8, enc_y, 11, 
                        rl.Color(255, 215, 0, 255))
            
            return bar_height
    
    def _draw_equipment_area(self, player, x, y, width, slot_size=36, compact_mode=False):
        """Draw equipment slots: Head and Body side by side, then accessories below.
        
        Returns:
            Height of the equipment area drawn
        """
        slot_gap = 4
        label_height = 14
        
        # Stacked layout: Equipment row on top, then accessories below
        current_y = y
        
        # Equipment row (Head + Body side by side)
        rl.draw_text("Equipment", x, current_y, 9, COLOR_TEXT_FAINT)
        current_y += label_height
        
        # Only show selection on gamepad
        head_selected = (self.gamepad_connected and 
                        self.selected_section == 'equipment_head' and 
                        self.selected_slot == 0)
        body_selected = (self.gamepad_connected and 
                        self.selected_section == 'equipment_body' and 
                        self.selected_slot == 0)
        
        # Head slot
        self._draw_equipment_slot(x, current_y, slot_size, None, head_selected)
        rl.draw_text("H", x + slot_size // 2 - 3, current_y + slot_size // 2 - 5, 10, COLOR_TEXT_FAINT)
        
        # Body slot next to head
        body_x = x + slot_size + slot_gap
        self._draw_equipment_slot(body_x, current_y, slot_size, None, body_selected)
        rl.draw_text("B", body_x + slot_size // 2 - 3, current_y + slot_size // 2 - 5, 10, COLOR_TEXT_FAINT)
        
        current_y += slot_size + 8
        
        # Accessories (2 rows of 4)
        rl.draw_text("Accessories", x, current_y, 9, COLOR_TEXT_FAINT)
        current_y += label_height
        
        # Use smaller slot size if needed to fit 4 columns
        acc_slot_size = min(slot_size, (width - 3 * slot_gap) // 4)
        
        for row in range(2):
            for col in range(4):
                i = row * 4 + col
                is_selected = (self.gamepad_connected and 
                              self.selected_section == 'accessories' and 
                              self.selected_slot == i)
                
                slot_x = x + col * (acc_slot_size + slot_gap)
                slot_y = current_y + row * (acc_slot_size + slot_gap)
                
                bg_color = COLOR_BG_SLOT_SELECTED if is_selected else COLOR_BG_SLOT
                border_color = COLOR_BORDER_SELECTED if is_selected else COLOR_BORDER
                
                rl.draw_rectangle(slot_x, slot_y, acc_slot_size, acc_slot_size, bg_color)
                rl.draw_rectangle_lines(slot_x, slot_y, acc_slot_size, acc_slot_size, border_color)
                
                if is_selected:
                    rl.draw_rectangle_lines(slot_x - 1, slot_y - 1, acc_slot_size + 2, acc_slot_size + 2, border_color)
        
        total_height = current_y + 2 * (acc_slot_size + slot_gap) - y
        return total_height
    
    def _draw_equipment_slot(self, x, y, size, item, is_selected=False):
        """Draw a single equipment slot."""
        has_item = item is not None
        
        if is_selected:
            bg_color = COLOR_BG_SLOT_SELECTED
            border_color = COLOR_BORDER_SELECTED
        elif has_item:
            bg_color = COLOR_BG_SLOT_ACTIVE
            border_color = COLOR_BORDER
        else:
            bg_color = COLOR_BG_SLOT
            border_color = COLOR_BORDER
        
        rl.draw_rectangle(x, y, size, size, bg_color)
        rl.draw_rectangle_lines(x, y, size, size, border_color)
        
        # Draw thicker border if selected
        if is_selected:
            rl.draw_rectangle_lines(x - 1, y - 1, size + 2, size + 2, border_color)
    
    def _draw_storage_section(self, player, x, y, width, label, num_slots, slot_size=36):
        """Draw a storage section with label and slots showing actual inventory."""
        slot_gap = 4
        left_padding = 6  # Padding from left edge
        
        # Section background
        section_height = slot_size + 24
        rl.draw_rectangle(x, y, width, section_height, rl.Color(255, 255, 255, 5))
        rl.draw_rectangle_lines(x, y, width, section_height, COLOR_BORDER)
        
        # Label
        rl.draw_text(label, x + 4, y + 4, 9, COLOR_TEXT_FAINT)
        
        # Slots - with left padding
        slots_x = x + left_padding
        slots_y = y + 18
        
        # Get player inventory
        inventory = player.inventory if hasattr(player, 'inventory') else [None] * num_slots
        
        # Adapt text sizes based on slot size
        icon_size = 14 if slot_size >= 32 else 11
        amount_size = 10 if slot_size >= 32 else 8
        
        for i in range(num_slots):
            slot_x = slots_x + i * (slot_size + slot_gap)
            
            # Store slot rect for hit detection
            self._slot_rects[('inventory', i)] = (slot_x, slots_y, slot_size, slot_size)
            
            # Check if this slot is selected (only show on gamepad)
            is_selected = (self.gamepad_connected and 
                          self.selected_section == 'inventory' and 
                          self.selected_slot == i)
            
            # Draw slot background with selection highlight
            bg_color = COLOR_BG_SLOT_SELECTED if is_selected else COLOR_BG_SLOT
            border_color = COLOR_BORDER_SELECTED if is_selected else COLOR_BORDER
            
            rl.draw_rectangle(slot_x, slots_y, slot_size, slot_size, bg_color)
            rl.draw_rectangle_lines(slot_x, slots_y, slot_size, slot_size, border_color)
            
            # Draw thicker border if selected
            if is_selected:
                rl.draw_rectangle_lines(slot_x - 1, slots_y - 1, slot_size + 2, slot_size + 2, border_color)
            
            # Draw item if present
            if i < len(inventory) and inventory[i] is not None:
                item = inventory[i]
                item_type = item.get('type', '')
                amount = item.get('amount', 0)
                
                # Draw item sprite (centered in slot)
                inset = 3 if slot_size < 32 else 4
                sprite_area_size = slot_size - inset * 2
                self._draw_item_sprite(item_type, slot_x + inset, slots_y + inset, sprite_area_size)
                
                # Draw amount at bottom of slot
                amount_str = str(amount)
                amount_x = slot_x + (slot_size - rl.measure_text(amount_str, amount_size)) // 2
                amount_y = slots_y + slot_size - amount_size - 2
                # Dark outline for readability
                rl.draw_text(amount_str, amount_x + 1, amount_y + 1, amount_size, rl.Color(0, 0, 0, 200))
                rl.draw_text(amount_str, amount_x, amount_y, amount_size, COLOR_TEXT_BRIGHT)
    
    def _load_item_sprites(self):
        """Load all item sprites defined in constants.ITEMS."""
        if self._sprites_loaded:
            return
        
        for item_type, item_info in ITEMS.items():
            sprite_path = get_item_sprite_path(item_type)
            if sprite_path and os.path.exists(sprite_path):
                texture = rl.load_texture(sprite_path)
                self._item_textures[item_type] = texture
        
        self._sprites_loaded = True
    
    def _get_item_texture(self, item_type):
        """Get the texture for an item type, loading if necessary.
        
        Returns:
            Texture2D or None if no sprite available
        """
        if not self._sprites_loaded:
            self._load_item_sprites()
        return self._item_textures.get(item_type)
    
    def _draw_item_sprite(self, item_type, x, y, size):
        """Draw an item sprite scaled to fit within the given size.
        
        Args:
            item_type: Type of item (e.g., 'wheat', 'bread', 'gold')
            x: X position to draw at
            y: Y position to draw at
            size: Size of the area to draw in (square)
        """
        texture = self._get_item_texture(item_type)
        
        if texture and texture.id > 0:
            # Calculate scale to fit the sprite in the slot with some padding
            padding = 2
            target_size = size - padding * 2
            scale = min(target_size / texture.width, target_size / texture.height)
            
            # Center the sprite in the slot
            draw_width = int(texture.width * scale)
            draw_height = int(texture.height * scale)
            draw_x = x + (size - draw_width) // 2
            draw_y = y + (size - draw_height) // 2
            
            # Draw the scaled texture
            source_rect = rl.Rectangle(0, 0, texture.width, texture.height)
            dest_rect = rl.Rectangle(draw_x, draw_y, draw_width, draw_height)
            rl.draw_texture_pro(texture, source_rect, dest_rect, rl.Vector2(0, 0), 0, rl.WHITE)
        else:
            # Fallback to text icon if no sprite
            icon = get_item_icon(item_type)
            icon_size = 14 if size >= 32 else 11
            icon_x = x + (size - rl.measure_text(icon, icon_size)) // 2
            icon_y = y + (size - icon_size) // 2
            rl.draw_text(icon, icon_x, icon_y, icon_size, COLOR_TEXT_BRIGHT)
    
    def unload_sprites(self):
        """Unload all item sprites. Call when closing the game."""
        for texture in self._item_textures.values():
            if texture and texture.id > 0:
                rl.unload_texture(texture)
        self._item_textures = {}
        self._sprites_loaded = False
    
    def _draw_right_panel(self, player, x, y, width):
        """Draw the right panel with tabs: World, Status, Map."""
        tab_names = ["World", "Status", "Map"]
        tab_height = 40
        
        # Tab bar background (slight tint so tabs are visible on world tab)
        rl.draw_rectangle(x, y, width, tab_height, COLOR_BOX_BG_LIGHT)
        
        # Tab bar
        tab_width = width // len(tab_names)
        
        for i, name in enumerate(tab_names):
            tab_x = x + i * tab_width
            is_active = i == self.current_tab
            
            # Check for mouse hover and click
            is_hovered = (tab_x <= self.mouse_x < tab_x + tab_width and 
                         y <= self.mouse_y < y + tab_height)
            
            if is_hovered and self.mouse_left_click:
                self.current_tab = i
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
        
        if self.current_tab == 0:
            self._draw_world_tab(player, content_x, content_y, content_width, content_height)
        elif self.current_tab == 1:
            self._draw_status_tab(player, content_x, content_y, content_width, content_height)
        elif self.current_tab == 2:
            self._draw_map_tab(player, content_x, content_y, content_width, content_height)
    
    def _draw_world_tab(self, player, x, y, width, height):
        """Draw the World tab - completely transparent to show game world."""
        # Completely blank - game world shows through
        pass
    
    def _draw_status_tab(self, player, x, y, width, height):
        """Draw the Status tab - shows skills with scrolling support."""
        # Header (fixed, not scrolled)
        rl.draw_text("SKILLS", x, y, 11, COLOR_TEXT_DIM)
        rl.draw_line(x, y + 16, x + width, y + 16, COLOR_BORDER)
        
        # Content area starts after header
        content_y = y + 28
        content_height = height - 28
        
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
        
        # Calculate total content height (show ALL skills now)
        total_content_height = 0
        if combat_skills:
            total_content_height += 14 + len(combat_skills) * 18 + 10  # Header + skills + padding
        if benign_skills:
            total_content_height += 14 + len(benign_skills) * 18 + 10
        if both_skills:
            total_content_height += 14 + len(both_skills) * 18 + 10
        
        self._status_tab_content_height = total_content_height
        
        # Determine if scrolling is needed
        needs_scroll = total_content_height > content_height
        
        # Clamp scroll offset
        if needs_scroll:
            max_scroll = total_content_height - content_height
            self._status_tab_scroll = max(0, min(max_scroll, self._status_tab_scroll))
        else:
            self._status_tab_scroll = 0
        
        # Apply scroll offset
        scroll_y = -int(self._status_tab_scroll)
        skill_y = content_y + scroll_y
        
        # Enable scissor mode for clipping
        rl.begin_scissor_mode(x - 4, content_y, width + 8, content_height)
        
        # Draw combat skills (all of them)
        if combat_skills:
            rl.draw_text("Combat", x, skill_y, 9, COLOR_HEALTH)
            skill_y += 14
            for name, value, _ in combat_skills:
                self._draw_skill_bar(x, skill_y, width - 20, name, value, COLOR_HEALTH)
                skill_y += 18
            skill_y += 10
        
        # Draw benign skills (all of them)
        if benign_skills:
            rl.draw_text("Trade", x, skill_y, 9, COLOR_FATIGUE)
            skill_y += 14
            for name, value, _ in benign_skills:
                self._draw_skill_bar(x, skill_y, width - 20, name, value, COLOR_FATIGUE)
                skill_y += 18
            skill_y += 10
        
        # Draw hybrid skills (all of them)
        if both_skills:
            rl.draw_text("Hybrid", x, skill_y, 9, COLOR_STAMINA)
            skill_y += 14
            for name, value, _ in both_skills:
                self._draw_skill_bar(x, skill_y, width - 20, name, value, COLOR_STAMINA)
                skill_y += 18
        
        # End scissor mode
        rl.end_scissor_mode()
        
        # Draw scroll indicator if needed
        if needs_scroll:
            self._draw_scroll_indicator(x + width - 8, content_y, 10, content_height,
                                       self._status_tab_scroll, total_content_height, content_height,
                                       is_left_panel=False)
    
    def _draw_skill_bar(self, x, y, width, name, value, color):
        """Draw a single skill bar."""
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
    
    def _draw_scroll_indicator(self, x, y, width, height, scroll_offset, content_height, visible_height, is_left_panel=True):
        """Draw a scroll bar/indicator showing current scroll position.
        
        Args:
            x: X position for the scroll bar
            y: Y position (top of scroll area)
            width: Width of the scroll bar
            height: Height of the scroll area
            scroll_offset: Current scroll position
            content_height: Total height of scrollable content
            visible_height: Height of visible area
            is_left_panel: True if this is the left panel scroll bar (for rect storage)
        """
        if content_height <= visible_height:
            # No scrolling needed - clear the rect
            if is_left_panel:
                self._left_scroll_bar_rect = None
            else:
                self._status_scroll_bar_rect = None
            return
        
        # Draw track background
        track_color = rl.Color(255, 255, 255, 30)
        rl.draw_rectangle(x, y, width, height, track_color)
        rl.draw_rectangle_lines(x, y, width, height, rl.Color(255, 255, 255, 50))
        
        # Calculate thumb size and position
        thumb_height = max(30, int(height * (visible_height / content_height)))
        max_scroll = content_height - visible_height
        scroll_ratio = scroll_offset / max_scroll if max_scroll > 0 else 0
        thumb_y = y + int((height - thumb_height) * scroll_ratio)
        
        # Store the scroll bar rect for hit detection (entire track area)
        bar_rect = (x, y, width, height)
        if is_left_panel:
            self._left_scroll_bar_rect = bar_rect
        else:
            self._status_scroll_bar_rect = bar_rect
        
        # Determine if mouse is hovering over scroll bar
        is_hovered = (x <= self.mouse_x <= x + width and y <= self.mouse_y <= y + height)
        is_dragging = (self._dragging_left_scroll if is_left_panel else self._dragging_status_scroll)
        
        # Draw thumb with hover/drag highlight
        if is_dragging:
            thumb_color = rl.Color(255, 255, 255, 180)
        elif is_hovered:
            thumb_color = rl.Color(255, 255, 255, 140)
        else:
            thumb_color = rl.Color(255, 255, 255, 100)
        
        rl.draw_rectangle(x, thumb_y, width, thumb_height, thumb_color)
        
        # Draw thumb border
        rl.draw_rectangle_lines(x, thumb_y, width, thumb_height, rl.Color(255, 255, 255, 180))
        
        # Draw scroll position indicator text
        if is_hovered or is_dragging:
            pct = int(scroll_ratio * 100)
            pct_text = f"{pct}%"
            text_x = x - rl.measure_text(pct_text, 9) - 4
            text_y = thumb_y + thumb_height // 2 - 4
            rl.draw_text(pct_text, text_x, text_y, 9, rl.Color(255, 255, 255, 150))
    
    def _draw_map_tab(self, player, x, y, width, height):
        """Draw the Map tab - shows world map (placeholder)."""
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
    
    def _draw_held_item(self):
        """Draw the item currently held by the cursor."""
        if not self.held_item:
            return
        
        item_type = self.held_item.get('type', '')
        amount = self.held_item.get('amount', 0)
        
        # Get draw position - at mouse for mouse, at selected slot for gamepad
        if self.gamepad_connected:
            # Draw near selected slot
            slot_key = (self.selected_section, self.selected_slot)
            if slot_key in self._slot_rects:
                sx, sy, sw, sh = self._slot_rects[slot_key]
                draw_x = sx + sw + 4
                draw_y = sy
            else:
                draw_x = self.canvas_width // 4
                draw_y = self.canvas_height // 2
        else:
            # Draw at mouse cursor with offset
            draw_x = self.mouse_x + 8
            draw_y = self.mouse_y + 8
        
        # Draw item
        slot_size = 32
        
        # Background with border
        bg_color = rl.Color(40, 40, 40, 220)
        rl.draw_rectangle(draw_x, draw_y, slot_size, slot_size, bg_color)
        rl.draw_rectangle_lines(draw_x, draw_y, slot_size, slot_size, rl.Color(255, 255, 255, 200))
        
        # Draw sprite
        self._draw_item_sprite(item_type, draw_x, draw_y, slot_size)
        
        # Amount
        amount_str = str(amount)
        amount_x = draw_x + (slot_size - rl.measure_text(amount_str, 10)) // 2
        amount_y = draw_y + slot_size - 12
        rl.draw_text(amount_str, amount_x + 1, amount_y + 1, 10, rl.Color(0, 0, 0, 200))
        rl.draw_text(amount_str, amount_x, amount_y, 10, COLOR_TEXT_BRIGHT)
    
    def _draw_control_hints(self, left_width, right_width):
        """Draw control hints in the bottom right of the right panel."""
        hint_x = left_width + 16
        hint_y = self.canvas_height - 95
        line_height = 14
        
        if self.gamepad_connected:
            hints = [
                ("A", "Pick up / Place"),
                ("X", "Place one"),
                ("Y", "Item menu"),
                ("B / Select", "Close"),
            ]
        else:
            hints = [
                ("Click", "Pick up / Place"),
                ("Right Click", "Place one"),
                ("Shift+Click", "Item menu"),
                ("Tab", "Close"),
            ]
        
        for i, (key, action) in enumerate(hints):
            y = hint_y + i * line_height
            
            # Key/button
            key_width = rl.measure_text(key, HUD_FONT_SIZE_SMALL)
            rl.draw_text(key, hint_x, y, HUD_FONT_SIZE_SMALL, COLOR_TEXT_DIM)
            
            # Action
            rl.draw_text(f": {action}", hint_x + key_width, y, HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)
    
    def _draw_context_menu(self):
        """Draw the context menu if open."""
        if not self.context_menu_open or not self.context_menu_options:
            return
        
        # Get position from slot rect
        slot_key = ('inventory', self.context_menu_slot)
        if slot_key not in self._slot_rects:
            return
        
        sx, sy, sw, sh = self._slot_rects[slot_key]
        
        # Menu dimensions
        padding = 6
        item_height = 20
        menu_width = 100
        menu_height = padding * 2 + len(self.context_menu_options) * item_height
        
        # Position menu to the right of the slot, or left if it would go off screen
        menu_x = sx + sw + 4
        if menu_x + menu_width > self.canvas_width:
            menu_x = sx - menu_width - 4
        
        menu_y = sy
        if menu_y + menu_height > self.canvas_height:
            menu_y = self.canvas_height - menu_height - 4
        
        # Store rect for potential mouse interaction
        self.context_menu_rect = (menu_x, menu_y, menu_width, menu_height)
        
        # Draw background
        rl.draw_rectangle(menu_x, menu_y, menu_width, menu_height, COLOR_BOX_BG)
        rl.draw_rectangle_lines(menu_x, menu_y, menu_width, menu_height, COLOR_BORDER)
        
        # Draw options
        for i, option in enumerate(self.context_menu_options):
            option_y = menu_y + padding + i * item_height
            
            # Highlight selected option
            if i == self.context_menu_selected:
                rl.draw_rectangle(menu_x + 2, option_y, menu_width - 4, item_height, COLOR_OPTION_SELECTED)
            
            # Check mouse hover
            if (menu_x <= self.mouse_x < menu_x + menu_width and
                option_y <= self.mouse_y < option_y + item_height):
                self.context_menu_selected = i
                if not (i == self.context_menu_selected):
                    rl.draw_rectangle(menu_x + 2, option_y, menu_width - 4, item_height, 
                                     rl.Color(255, 255, 255, 10))
            
            # Draw option text
            text_color = COLOR_TEXT_BRIGHT if i == self.context_menu_selected else COLOR_TEXT_DIM
            rl.draw_text(option, menu_x + padding, option_y + 4, 11, text_color)