import os
import pyray as rl
from constants import (
    SKILLS, ITEMS, MAX_ENCUMBRANCE,
    UI_COLOR_BOX_BG, UI_COLOR_BOX_BG_MEDIUM, UI_COLOR_BOX_BG_LIGHT,
    UI_COLOR_BORDER, UI_COLOR_BORDER_INNER,
    UI_COLOR_TEXT, UI_COLOR_TEXT_DIM, UI_COLOR_TEXT_FAINT,
    UI_COLOR_SLOT_BG, UI_COLOR_SLOT_ACTIVE, UI_COLOR_SLOT_SELECTED,
    UI_COLOR_SLOT_BORDER, UI_COLOR_SLOT_BORDER_SELECTED,
    UI_COLOR_OPTION_SELECTED
)
from ground_items import GroundItem, find_valid_drop_position


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
        return os.path.join('ui', 'sprites', 'Items', sprite_name)
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
    
    def __init__(self, game_state, game_logic):
        """
        Initialize the inventory menu.

        Args:
            game_state: GameState instance
            game_logic: GameLogic instance
        """
        self.state = game_state
        self.logic = game_logic
        self._active = False
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
        # Sections: 'equipment_head', 'equipment_body', 'accessories', 'inventory', 'ground'
        self.selected_section = 'inventory'  # Start in inventory section
        self.selected_slot = 0  # Index within current section
        
        # Held item state (Minecraft-style cursor item)
        self.held_item = None  # {'type': str, 'amount': int} or None
        self._held_was_equipped = False  # Track if held item was equipped weapon
        
        # Slot geometry cache (populated during render for hit detection)
        self._slot_rects = {}  # {('section', index): (x, y, w, h)}
        
        # Ground items state - cached nearby items for current frame
        self._nearby_ground_items = []  # List of GroundItem objects within range
        self._ground_pickup_radius = 1.0  # How close player must be to pick up
        
        # Barrel/Corpse viewing state - when player interacts with a barrel or corpse
        self._viewing_barrel = None  # Barrel object being viewed, or None
        self._viewing_corpse = None  # Corpse object being viewed, or None
        
        # Context menu state
        self.context_menu_open = False
        self.context_menu_slot = None  # Index of slot the menu is for
        self.context_menu_options = []  # List of available options
        self.context_menu_selected = 0  # Currently highlighted option
        self.context_menu_rect = (0, 0, 0, 0)  # x, y, w, h for rendering
        
        # Confirmation popup state (for destructive actions like Burn)
        self._confirm_popup_open = False
        self._confirm_popup_action = None  # 'burn', etc.
        self._confirm_popup_slot = None  # Slot index for the action
        self._confirm_popup_selected = 1  # 0=Yes, 1=No (default to No for safety)
        self._confirm_popup_item_type = None
        self._confirm_popup_item_amount = 0
        
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

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def is_active(self):
        """Whether the menu is currently active."""
        return self._active

    @property
    def _viewing_container(self):
        """Get the current viewing container (barrel or corpse), or None."""
        return self._viewing_corpse if self._viewing_corpse else self._viewing_barrel

    # =========================================================================
    # MENU CONTROL
    # =========================================================================

    def open(self, barrel=None, corpse=None):
        """Open the inventory menu.

        Args:
            barrel: Optional Barrel object to view. If provided, barrel inventory
                   is shown instead of Ground section.
            corpse: Optional Corpse object to view. If provided, corpse inventory
                   is shown instead of Ground section.
        """
        self._active = True
        self._viewing_barrel = barrel if not corpse else None
        self._viewing_corpse = corpse
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
        # Close confirmation popup if open
        self._close_confirm_popup()
        # Return held item to inventory if any
        if self.held_item and self.state.player:
            self._return_held_item_to_inventory()
        self.held_item = None
        self._held_was_equipped = False
        self._viewing_barrel = None
        self._viewing_corpse = None
        self._active = False
    
    def _return_held_item_to_inventory(self):
        """Return held item to first available inventory slot, or drop to ground if full."""
        if not self.held_item or not self.state.player:
            return
        
        player = self.state.player
        inventory = player.inventory
        held_type = self.held_item['type']
        stack_limit = get_stack_limit(held_type)
        was_equipped = getattr(self, '_held_was_equipped', False)
        
        # First try to stack with existing items of same type
        for i, slot in enumerate(inventory):
            if slot and slot.get('type') == held_type:
                if stack_limit is None:
                    # Unlimited stacking - combine everything
                    slot['amount'] = slot.get('amount', 0) + self.held_item['amount']
                    self.held_item = None
                    self._held_was_equipped = False
                    return
                else:
                    space = stack_limit - slot.get('amount', 0)
                    if space > 0:
                        transfer = min(space, self.held_item['amount'])
                        slot['amount'] = slot.get('amount', 0) + transfer
                        self.held_item['amount'] -= transfer
                        if self.held_item['amount'] <= 0:
                            self.held_item = None
                            self._held_was_equipped = False
                            return
        
        # Then try empty slots
        for i, slot in enumerate(inventory):
            if slot is None:
                inventory[i] = self.held_item.copy()
                # If this was an equipped weapon, re-equip it in new slot
                if was_equipped:
                    player.equipped_weapon = i
                self.held_item = None
                self._held_was_equipped = False
                return
        
        # If still holding item, drop to ground (inventory full)
        if self.held_item:
            self._drop_held_item_to_ground(player)
            self._held_was_equipped = False
    
    def toggle(self):
        """Toggle the inventory menu open/closed."""
        if self._active:
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
        
        # Handle shift+click for quick-move (all sections)
        if self._active and not self.context_menu_open and not self._confirm_popup_open and mouse_left_click and shift_held:
            clicked_slot = self._get_slot_at_mouse()
            if clicked_slot:
                section, index = clicked_slot
                if section == 'ground':
                    self._quick_move_ground_to_inventory(index)
                    return  # Don't process normal click
                elif section == 'barrel':
                    self._quick_move_barrel_to_inventory(index)
                    return  # Don't process normal click
                elif section == 'inventory':
                    # Quick-move to barrel/corpse if viewing one, otherwise to ground
                    if self._viewing_container is not None:
                        self._quick_move_inventory_to_barrel(index)
                    else:
                        self._quick_move_inventory_to_ground(index)
                    return  # Don't process normal click
        
        # Handle mouse clicks on slots (but not if shift is held or popup is open)
        if self._active and not self.context_menu_open and not self._confirm_popup_open and (mouse_left_click or mouse_right_click) and not shift_held:
            clicked_slot = self._get_slot_at_mouse()
            if clicked_slot:
                section, index = clicked_slot
                if section == 'inventory':
                    if mouse_left_click:
                        self._interact_slot_full(index)
                    elif mouse_right_click:
                        # Right-click behavior depends on whether holding an item:
                        # - Holding item: drop 1 into slot (if empty or compatible)
                        # - Not holding: context menu (handled in gui.py)
                        if self.held_item is not None:
                            self._interact_slot_single(index)
                        # Context menu opening is handled in gui.py (when not holding)
                elif section == 'ground':
                    if mouse_left_click:
                        self._interact_ground_slot_full(index)
                    elif mouse_right_click:
                        # Right-click on ground: if holding item and slot empty, drop single; else pick up half
                        self._interact_ground_slot_single(index)
                elif section == 'barrel':
                    if mouse_left_click:
                        self._interact_barrel_slot_full(index)
                    elif mouse_right_click:
                        # Right-click on barrel: if holding item and slot empty, drop single; else pick up half
                        self._interact_barrel_slot_single(index)
    
    def update_scroll(self):
        """Handle scroll input - call this every frame when menu is open.
        
        Handles:
        - Mouse wheel scrolling
        - Scroll bar dragging
        - Gamepad right stick scrolling
        - Keyboard Page Up/Down
        """
        if not self._active:
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
                # Track if we're picking up the equipped weapon
                self._held_was_equipped = (player.equipped_weapon == slot_index)
                if self._held_was_equipped:
                    player.equipped_weapon = None
                inventory[slot_index] = None
        else:
            # We're holding something
            if slot_item is None:
                # Place entire held stack in empty slot
                inventory[slot_index] = self.held_item.copy()
                # If we were holding an equipped weapon, update the slot reference
                if getattr(self, '_held_was_equipped', False):
                    player.equipped_weapon = slot_index
                    self._held_was_equipped = False
                self.held_item = None
            elif slot_item.get('type') == self.held_item.get('type'):
                # Same type - try to stack
                stack_limit = get_stack_limit(slot_item.get('type'))
                if stack_limit is None:
                    # Unlimited stacking - combine everything
                    slot_item['amount'] = slot_item.get('amount', 0) + self.held_item['amount']
                    self._held_was_equipped = False
                    self.held_item = None
                else:
                    space = stack_limit - slot_item.get('amount', 0)
                    if space > 0:
                        transfer = min(space, self.held_item['amount'])
                        slot_item['amount'] = slot_item.get('amount', 0) + transfer
                        self.held_item['amount'] -= transfer
                        if self.held_item['amount'] <= 0:
                            self._held_was_equipped = False
                            self.held_item = None
                    else:
                        # Stack full - swap
                        inventory[slot_index] = self.held_item.copy()
                        old_slot_was_equipped = (player.equipped_weapon == slot_index)
                        # If we were holding equipped weapon, it goes to this slot
                        if getattr(self, '_held_was_equipped', False):
                            player.equipped_weapon = slot_index
                        elif old_slot_was_equipped:
                            player.equipped_weapon = None  # Old equipped is now held
                        self._held_was_equipped = old_slot_was_equipped
                        self.held_item = slot_item.copy()
            else:
                # Different type - swap
                inventory[slot_index] = self.held_item.copy()
                old_slot_was_equipped = (player.equipped_weapon == slot_index)
                # If we were holding equipped weapon, it goes to this slot
                if getattr(self, '_held_was_equipped', False):
                    player.equipped_weapon = slot_index
                elif old_slot_was_equipped:
                    player.equipped_weapon = None  # Old equipped is now held
                self._held_was_equipped = old_slot_was_equipped
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
                    # Weapon stays equipped if there's still items in the slot
                else:
                    # Track if we're picking up the equipped weapon
                    self._held_was_equipped = (player.equipped_weapon == slot_index)
                    if self._held_was_equipped:
                        player.equipped_weapon = None
                    inventory[slot_index] = None
        else:
            # We're holding something - place single item
            if slot_item is None:
                # Place 1 item in empty slot
                inventory[slot_index] = {'type': self.held_item['type'], 'amount': 1}
                self.held_item['amount'] -= 1
                if self.held_item['amount'] <= 0:
                    # If placing the last of an equipped weapon, equip it in new slot
                    if getattr(self, '_held_was_equipped', False):
                        player.equipped_weapon = slot_index
                        self._held_was_equipped = False
                    self.held_item = None
            elif slot_item.get('type') == self.held_item.get('type'):
                # Same type - place 1 if room
                stack_limit = get_stack_limit(slot_item.get('type'))
                # None means unlimited, so always allow; otherwise check limit
                if stack_limit is None or slot_item.get('amount', 0) < stack_limit:
                    slot_item['amount'] = slot_item.get('amount', 0) + 1
                    self.held_item['amount'] -= 1
                    if self.held_item['amount'] <= 0:
                        self._held_was_equipped = False
                        self.held_item = None
            # Different type - do nothing (can't place)
    
    def handle_item_interaction(self, full_interact=False, single_interact=False, quick_move=False):
        """
        Handle gamepad item interactions on the currently selected slot.
        
        Args:
            full_interact: A button pressed - pick up/place full stack
            single_interact: X button pressed - pick up half/place single
            quick_move: LB + A pressed - quick move to other container
        """
        if not self._active:
            return
        
        # Handle quick move (LB + A)
        if quick_move:
            if self.selected_section == 'inventory':
                # Always drop to ground (use context menu for Move to Barrel)
                self._quick_move_inventory_to_ground(self.selected_slot)
            elif self.selected_section == 'ground':
                self._quick_move_ground_to_inventory(self.selected_slot)
            elif self.selected_section == 'barrel':
                self._quick_move_barrel_to_inventory(self.selected_slot)
            return
        
        # Handle inventory slots
        if self.selected_section == 'inventory':
            if full_interact:
                self._interact_slot_full(self.selected_slot)
            elif single_interact:
                self._interact_slot_single(self.selected_slot)
        # Handle ground slots
        elif self.selected_section == 'ground':
            if full_interact:
                self._interact_ground_slot_full(self.selected_slot)
            elif single_interact:
                self._interact_ground_slot_single(self.selected_slot)
        # Handle barrel slots
        elif self.selected_section == 'barrel':
            if full_interact:
                self._interact_barrel_slot_full(self.selected_slot)
            elif single_interact:
                self._interact_barrel_slot_single(self.selected_slot)
    
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
        options = self._get_context_options(item, slot_index)
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
    
    def _get_context_options(self, item, slot_index=None):
        """
        Get available context menu options for an item.
        
        Args:
            item: Item dict with 'type' and 'amount'
            slot_index: Inventory slot index (needed for equip check)
            
        Returns:
            List of option strings
        """
        options = []
        item_type = item.get('type', '')
        item_info = ITEMS.get(item_type, {})
        amount = item.get('amount', 1)
        

        
        # Bread can be eaten
        if item_type == 'bread':
            options.append('Use')
        
        # Weapons can be equipped/unequipped
        if item_info.get('category') == 'weapon':
            player = self.state.player
            if player and slot_index is not None:
                if player.equipped_weapon == slot_index:
                    options.append('Unequip')
                else:
                    options.append('Equip')
        
        # Move to Barrel/Corpse option when viewing a container
        if self._viewing_container:
            container_name = 'Corpse' if self._viewing_corpse else 'Barrel'
            options.append(f'Move to {container_name}')
        

        # Pick Up Half option for stackable items with more than 1
        if amount > 1:
            options.append('Pick Up Half')

        # All items can be dropped
        options.append('Drop')
        
        # Burn option if adjacent to usable stove or campfire
        if self._can_burn_items():
            options.append('Burn')
        
        options.append('Cancel')
        
        return options
    
    def _can_burn_items(self):
        """Check if player is adjacent to a usable stove or campfire."""
        player = self.state.player
        if not player:
            return False

        return self.logic.can_burn_items(player)
    
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
        elif action == 'Pick Up Half':
            self._pick_up_half(slot_index)
        elif action == 'Equip':
            self._equip_weapon(slot_index, item)
        elif action == 'Unequip':
            self._unequip_weapon(slot_index)
        elif action == 'Move to Barrel':
            self._quick_move_inventory_to_barrel(slot_index)
        elif action == 'Drop':
            self._quick_move_inventory_to_ground(slot_index)
        elif action == 'Burn':
            # Open confirmation popup instead of immediately burning
            self._open_burn_confirmation(slot_index, item)
            return  # Don't close context menu yet - popup handles it
        
        self.close_context_menu()
    
    def _use_item(self, slot_index, item):
        """
        Use/consume an item from a specific inventory slot.

        Args:
            slot_index: Inventory slot index
            item: Item dict
        """
        player = self.state.player
        self.logic.use_item(player, slot_index)
    
    def _pick_up_half(self, slot_index):
        """
        Pick up half of a stack from an inventory slot (like right-click in Minecraft).
        
        Args:
            slot_index: Inventory slot index
        """
        player = self.state.player
        if not player or self.held_item is not None:
            return  # Can't pick up if already holding something
        
        inventory = player.inventory
        if slot_index < 0 or slot_index >= len(inventory):
            return
        
        item = inventory[slot_index]
        if item is None:
            return
        
        amount = item.get('amount', 1)
        if amount <= 1:
            # Just pick up the whole thing
            self.held_item = item
            inventory[slot_index] = None
        else:
            # Pick up half (rounded up)
            half = (amount + 1) // 2
            self.held_item = {'type': item['type'], 'amount': half}
            item['amount'] = amount - half
            if item['amount'] <= 0:
                inventory[slot_index] = None
    
    def _equip_weapon(self, slot_index, item):
        """
        Equip a weapon from a specific inventory slot.

        Args:
            slot_index: Inventory slot index
            item: Item dict
        """
        player = self.state.player
        if not player:
            return

        self.logic.equip_weapon(player, slot_index)
    
    def _unequip_weapon(self, slot_index):
        """
        Unequip the weapon in a specific inventory slot.

        Args:
            slot_index: Inventory slot index
        """
        player = self.state.player
        if not player:
            return

        self.logic.unequip_weapon(player, slot_index)

    # =========================================================================
    # CONFIRMATION POPUP METHODS
    # =========================================================================
    
    def _open_burn_confirmation(self, slot_index, item):
        """Open the burn confirmation popup."""
        self.close_context_menu()
        
        self._confirm_popup_open = True
        self._confirm_popup_action = 'burn'
        self._confirm_popup_slot = slot_index
        self._confirm_popup_selected = 1  # Default to No for safety
        self._confirm_popup_item_type = item.get('type', 'item')
        self._confirm_popup_item_amount = item.get('amount', 1)
    
    def _close_confirm_popup(self):
        """Close the confirmation popup."""
        self._confirm_popup_open = False
        self._confirm_popup_action = None
        self._confirm_popup_slot = None
        self._confirm_popup_selected = 1
        self._confirm_popup_item_type = None
        self._confirm_popup_item_amount = 0
    
    def handle_confirm_popup_input(self, nav_left=False, nav_right=False, select=False, cancel=False):
        """
        Handle input for the confirmation popup.
        
        Args:
            nav_left: Navigate left pressed
            nav_right: Navigate right pressed
            select: Select/confirm pressed
            cancel: Cancel/back pressed
            
        Returns:
            True if input was consumed
        """
        if not self._confirm_popup_open:
            return False
        
        if cancel:
            self._close_confirm_popup()
            return True
        
        if nav_left or nav_right:
            # Toggle between Yes (0) and No (1)
            self._confirm_popup_selected = 1 - self._confirm_popup_selected
            return True
        
        if select:
            if self._confirm_popup_selected == 0:  # Yes
                self._execute_confirm_action()
            self._close_confirm_popup()
            return True
        
        return False
    
    def _execute_confirm_action(self):
        """Execute the confirmed action."""
        if self._confirm_popup_action == 'burn':
            self._burn_item(self._confirm_popup_slot)
    
    def _burn_item(self, slot_index):
        """Burn/destroy an item from inventory."""
        if not self.state.player:
            return

        player = self.state.player
        self.logic.burn_item(player, slot_index)
    
    def _draw_confirm_popup(self):
        """Draw the confirmation popup if open."""
        if not self._confirm_popup_open:
            return
        
        # Get item display name
        item_info = ITEMS.get(self._confirm_popup_item_type, {})
        display_name = item_info.get('name', self._confirm_popup_item_type.capitalize())
        
        # Popup dimensions - mobile friendly (larger touch targets)
        popup_width = min(280, self.canvas_width - 40)
        popup_height = 120
        
        # Center on screen
        popup_x = (self.canvas_width - popup_width) // 2
        popup_y = (self.canvas_height - popup_height) // 2
        
        # Draw darkened background overlay
        rl.draw_rectangle(0, 0, self.canvas_width, self.canvas_height, rl.Color(0, 0, 0, 150))
        
        # Draw popup background
        rl.draw_rectangle(popup_x, popup_y, popup_width, popup_height, COLOR_BOX_BG)
        rl.draw_rectangle_lines(popup_x, popup_y, popup_width, popup_height, rl.Color(200, 100, 100, 255))
        rl.draw_rectangle_lines(popup_x + 1, popup_y + 1, popup_width - 2, popup_height - 2, rl.Color(150, 75, 75, 255))
        
        # Title
        title = "Burn Item?"
        title_width = rl.measure_text(title, 14)
        rl.draw_text(title, popup_x + (popup_width - title_width) // 2, popup_y + 12, 14, rl.Color(255, 150, 150, 255))
        
        # Message
        msg = f"Destroy {self._confirm_popup_item_amount} {display_name}?"
        msg_width = rl.measure_text(msg, 11)
        rl.draw_text(msg, popup_x + (popup_width - msg_width) // 2, popup_y + 38, 11, COLOR_TEXT_BRIGHT)
        
        # Warning
        warning = "This cannot be undone!"
        warning_width = rl.measure_text(warning, 10)
        rl.draw_text(warning, popup_x + (popup_width - warning_width) // 2, popup_y + 55, 10, rl.Color(255, 100, 100, 200))
        
        # Buttons - large touch targets
        button_width = 80
        button_height = 32
        button_gap = 20
        buttons_y = popup_y + popup_height - button_height - 15
        
        # Center the two buttons
        total_buttons_width = button_width * 2 + button_gap
        buttons_start_x = popup_x + (popup_width - total_buttons_width) // 2
        
        yes_x = buttons_start_x
        no_x = buttons_start_x + button_width + button_gap
        
        # Yes button
        yes_selected = self._confirm_popup_selected == 0
        yes_bg = rl.Color(150, 60, 60, 255) if yes_selected else rl.Color(80, 40, 40, 200)
        yes_border = rl.Color(255, 100, 100, 255) if yes_selected else rl.Color(120, 80, 80, 200)
        rl.draw_rectangle(yes_x, buttons_y, button_width, button_height, yes_bg)
        rl.draw_rectangle_lines(yes_x, buttons_y, button_width, button_height, yes_border)
        yes_text = "Yes"
        yes_text_width = rl.measure_text(yes_text, 12)
        rl.draw_text(yes_text, yes_x + (button_width - yes_text_width) // 2, buttons_y + 10, 12, 
                    COLOR_TEXT_BRIGHT if yes_selected else COLOR_TEXT_DIM)
        
        # No button
        no_selected = self._confirm_popup_selected == 1
        no_bg = rl.Color(60, 80, 60, 255) if no_selected else rl.Color(40, 50, 40, 200)
        no_border = rl.Color(100, 180, 100, 255) if no_selected else rl.Color(80, 100, 80, 200)
        rl.draw_rectangle(no_x, buttons_y, button_width, button_height, no_bg)
        rl.draw_rectangle_lines(no_x, buttons_y, button_width, button_height, no_border)
        no_text = "No"
        no_text_width = rl.measure_text(no_text, 12)
        rl.draw_text(no_text, no_x + (button_width - no_text_width) // 2, buttons_y + 10, 12,
                    COLOR_TEXT_BRIGHT if no_selected else COLOR_TEXT_DIM)
        
        # Handle mouse hover/click on buttons
        if self.mouse_left_click:
            if yes_x <= self.mouse_x < yes_x + button_width and buttons_y <= self.mouse_y < buttons_y + button_height:
                self._confirm_popup_selected = 0
                self._execute_confirm_action()
                self._close_confirm_popup()
            elif no_x <= self.mouse_x < no_x + button_width and buttons_y <= self.mouse_y < buttons_y + button_height:
                self._close_confirm_popup()
        else:
            # Update hover state
            if yes_x <= self.mouse_x < yes_x + button_width and buttons_y <= self.mouse_y < buttons_y + button_height:
                self._confirm_popup_selected = 0
            elif no_x <= self.mouse_x < no_x + button_width and buttons_y <= self.mouse_y < buttons_y + button_height:
                self._confirm_popup_selected = 1
    
    def handle_input(self, dt=None):
        """
        Handle navigation input for the inventory menu (gamepad only).
        
        Args:
            dt: Delta time in seconds (if None, uses rl.get_frame_time())
            
        Returns:
            True if input was consumed, False otherwise
        """
        if not self._active:
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
        # - barrel OR ground (dynamic rows of 5)
        
        # Determine bottom section name
        bottom_section = 'barrel' if self._viewing_container else 'ground'
        
        if section == 'barrel':
            # Barrel/Corpse navigation
            barrel_slots = len(self._viewing_container.inventory) if self._viewing_container else 0
            barrel_rows = (barrel_slots + 4) // 5
            row = slot // 5
            col = slot % 5
            
            if dx != 0:
                col = (col + dx) % 5
                slot = row * 5 + col
                # Clamp to valid slot
                slot = min(slot, barrel_slots - 1)
            
            if dy > 0:  # Down within barrel
                new_row = row + 1
                if new_row < barrel_rows:
                    new_slot = new_row * 5 + col
                    if new_slot < barrel_slots:
                        slot = new_slot
                # Else stay at current position
            elif dy < 0:  # Up
                if row > 0:
                    slot = (row - 1) * 5 + col
                else:
                    # Go up to inventory
                    section = 'inventory'
                    slot = min(col, 4)
        
        elif section == 'ground':
            ground_rows = self._calculate_ground_rows()
            total_ground_slots = ground_rows * 5
            row = slot // 5
            col = slot % 5
            
            if dx != 0:
                col = (col + dx) % 5
                slot = row * 5 + col
            
            if dy > 0:  # Down within ground
                new_row = row + 1
                if new_row < ground_rows:
                    slot = new_row * 5 + col
                # Else stay at bottom
            elif dy < 0:  # Up
                if row > 0:
                    slot = (row - 1) * 5 + col
                else:
                    # Go up to inventory
                    section = 'inventory'
                    slot = min(col, 4)
        
        elif section == 'inventory':
            if dx != 0:
                slot = (slot + dx) % 5
            if dy < 0:  # Up to accessories
                section = 'accessories'
                slot = min(4 + min(slot, 3), 7)
            elif dy > 0:  # Down to barrel or ground
                section = bottom_section
                slot = min(slot, 4)
        
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
        if not self._active:
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
        
        # Draw confirmation popup on top of everything (including context menu)
        self._draw_confirm_popup()
    
    def _draw_left_panel(self, player, x, y, width):
        """Draw the left inventory panel with equipment, storage, and ground."""
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
        
        # Calculate bottom section height (barrel/corpse or ground)
        barrel_rows = 0  # Initialize for corpse case
        if self._viewing_container:
            if self._viewing_corpse:
                # Corpse has complex layout: equipment + accessories + inventory
                acc_slot_size = slot_size - 4
                bottom_section_height = (
                    24 +  # Top label
                    12 + slot_size + 8 +  # Equipment section
                    12 + (2 * (acc_slot_size + slot_gap)) + 8 +  # Accessories section
                    12 + slot_size + 20  # Inventory section + padding
                )
                barrel_rows = 0  # Not used for corpses, but needs to be defined
            else:
                # Regular barrel has simple grid (typically 30 = 6 rows of 5)
                barrel_slots = len(self._viewing_container.inventory)
                barrel_rows = (barrel_slots + 4) // 5  # Ceiling division
                bottom_section_height = 24 + barrel_rows * (slot_size + slot_gap)
        else:
            # Update nearby ground items cache
            self._update_nearby_ground_items(player)
            # Calculate ground section height (dynamic rows)
            ground_rows = self._calculate_ground_rows()
            bottom_section_height = 24 + ground_rows * (slot_size + slot_gap)
        
        # Calculate total content height to determine if scrolling is needed
        # Status bar: ~50-70px, Equipment area: ~100-140px, Inventory: ~60px, Bottom: dynamic
        status_height = 70 if compact_mode else 50
        equip_height = 140 if compact_mode else 100
        inventory_height = slot_size + 24
        total_content_height = padding + status_height + 8 + equip_height + 8 + inventory_height + 8 + bottom_section_height + padding
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
        inner_y += inventory_height + 8

        # === BARREL/CORPSE or GROUND (bottom section) ===
        if self._viewing_container:
            self._draw_barrel_section(player, inner_x, inner_y, inner_width, slot_size, barrel_rows)
        else:
            self._draw_ground_section(player, inner_x, inner_y, inner_width, slot_size, ground_rows)
        
        # End scissor mode
        rl.end_scissor_mode()
        
        # Note: Left panel scroll bar intentionally hidden - scrolling still works via mouse wheel/trackpad
        # Clear the scroll bar rect since we're not drawing it
        self._left_scroll_bar_rect = None
    
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
            current_enc = player.get_encumbrance()
            is_over_encumbered = current_enc >= MAX_ENCUMBRANCE
            enc_color = rl.Color(255, 100, 100, 255) if is_over_encumbered else COLOR_TEXT_FAINT
            rl.draw_text("Wt", x + 8, bottom_y, 9, COLOR_TEXT_DIM)
            enc_str = f"{current_enc:.1f}/{MAX_ENCUMBRANCE:.0f}"
            rl.draw_text(enc_str, x + 24, bottom_y, 9, enc_color)
            
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
            current_enc = player.get_encumbrance()
            is_over_encumbered = current_enc >= MAX_ENCUMBRANCE
            enc_color = rl.Color(255, 100, 100, 255) if is_over_encumbered else COLOR_TEXT_FAINT
            rl.draw_text("Wt", x + 8, enc_y, 9, COLOR_TEXT_DIM)
            enc_str = f"{current_enc:.1f}/{MAX_ENCUMBRANCE:.0f}"
            rl.draw_text(enc_str, x + 24, enc_y, 9, enc_color)
            
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
    
    def _draw_storage_section(self, character, x, y, width, label, num_slots, slot_size=36,
                              section_key='inventory', bg_color=None, border_color=None,
                              label_color=None, slot_bg_color=None, slot_border_color=None):
        """Draw a storage section with label and slots showing actual inventory.

        Args:
            character: Player, NPC, or Corpse object with .inventory attribute
            section_key: Key for slot rect tracking (e.g., 'inventory', 'barrel')
        """
        slot_gap = 4
        left_padding = 6  # Padding from left edge

        # Default colors
        bg_color = bg_color or rl.Color(255, 255, 255, 5)
        border_color = border_color or COLOR_BORDER
        label_color = label_color or COLOR_TEXT_FAINT
        slot_bg_color = slot_bg_color or COLOR_BG_SLOT
        slot_border_color = slot_border_color or COLOR_BORDER

        # Section background
        section_height = slot_size + 24
        rl.draw_rectangle(x, y, width, section_height, bg_color)
        rl.draw_rectangle_lines(x, y, width, section_height, border_color)

        # Label
        rl.draw_text(label, x + 4, y + 4, 9, label_color)
        
        # Slots - with left padding
        slots_x = x + left_padding
        slots_y = y + 18

        # Get character inventory
        inventory = character.inventory if hasattr(character, 'inventory') else [None] * num_slots

        # Get equipped weapon slot (only for players)
        equipped_slot = getattr(character, 'equipped_weapon', None)

        # Adapt text sizes based on slot size
        icon_size = 14 if slot_size >= 32 else 11
        amount_size = 10 if slot_size >= 32 else 8

        # Color for equipped border (golden/yellow)
        equipped_border_color = rl.Color(255, 200, 80, 255)

        for i in range(num_slots):
            slot_x = slots_x + i * (slot_size + slot_gap)

            # Store slot rect for hit detection
            self._slot_rects[(section_key, i)] = (slot_x, slots_y, slot_size, slot_size)

            # Check if this slot is selected (only show on gamepad)
            is_selected = (self.gamepad_connected and
                          self.selected_section == section_key and
                          self.selected_slot == i)

            # Check if this slot has the equipped weapon
            is_equipped = (equipped_slot == i)

            # Draw slot background with selection highlight
            slot_bg = COLOR_BG_SLOT_SELECTED if is_selected else slot_bg_color
            slot_border = COLOR_BORDER_SELECTED if is_selected else slot_border_color
            
            rl.draw_rectangle(slot_x, slots_y, slot_size, slot_size, slot_bg)
            rl.draw_rectangle_lines(slot_x, slots_y, slot_size, slot_size, slot_border)

            # Draw thicker border if selected
            if is_selected:
                rl.draw_rectangle_lines(slot_x - 1, slots_y - 1, slot_size + 2, slot_size + 2, slot_border)
            
            # Draw equipped indicator (golden border)
            if is_equipped:
                rl.draw_rectangle_lines(slot_x - 2, slots_y - 2, slot_size + 4, slot_size + 4, equipped_border_color)
                rl.draw_rectangle_lines(slot_x - 1, slots_y - 1, slot_size + 2, slot_size + 2, equipped_border_color)
                # Draw "E" indicator in top-left corner
                rl.draw_text("E", slot_x + 2, slots_y + 1, 8, equipped_border_color)
            
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
    
    def _update_nearby_ground_items(self, player):
        """Update the cache of ground items near the player."""
        if not player or not hasattr(self.state, 'ground_items'):
            self._nearby_ground_items = []
            return
        
        # Get player position and zone
        if player.zone:
            # Inside an interior - use prevailing coords
            px, py = player.prevailing_x, player.prevailing_y
        else:
            # Exterior - use world coords
            px, py = player.x, player.y
        
        # Get nearby items
        self._nearby_ground_items = self.state.ground_items.get_items_near(
            px, py, self._ground_pickup_radius, player.zone
        )
    
    def _calculate_ground_rows(self):
        """Calculate how many rows the ground section needs.
        
        Starts with 2 rows minimum, adds rows as needed to have spare space.
        """
        num_items = len(self._nearby_ground_items)
        slots_per_row = 5
        
        # Minimum 2 rows
        min_rows = 2
        
        # Calculate rows needed (always keep at least one spare row)
        items_rows = (num_items + slots_per_row - 1) // slots_per_row  # Ceiling division
        needed_rows = max(min_rows, items_rows + 1)  # +1 for spare row
        
        return needed_rows
    
    def _draw_ground_section(self, player, x, y, width, slot_size, num_rows):
        """Draw the Ground section showing nearby dropped items."""
        slot_gap = 4
        left_padding = 6
        slots_per_row = 5
        
        # Section height
        section_height = 24 + num_rows * (slot_size + slot_gap)
        
        # Section background with distinct border
        rl.draw_rectangle(x, y, width, section_height, rl.Color(60, 50, 40, 100))
        rl.draw_rectangle_lines(x, y, width, section_height, rl.Color(139, 119, 101, 200))
        
        # Label
        rl.draw_text("Ground", x + 4, y + 4, 9, rl.Color(180, 160, 140, 255))
        
        # Slots
        slots_x = x + left_padding
        slots_y = y + 18
        
        # Adapt text sizes based on slot size
        amount_size = 10 if slot_size >= 32 else 8
        
        # Calculate total slots to draw
        total_slots = num_rows * slots_per_row
        
        for i in range(total_slots):
            row = i // slots_per_row
            col = i % slots_per_row
            
            slot_x = slots_x + col * (slot_size + slot_gap)
            slot_y = slots_y + row * (slot_size + slot_gap)
            
            # Store slot rect for hit detection
            self._slot_rects[('ground', i)] = (slot_x, slot_y, slot_size, slot_size)
            
            # Check if this slot is selected (only show on gamepad)
            is_selected = (self.gamepad_connected and 
                          self.selected_section == 'ground' and 
                          self.selected_slot == i)
            
            # Draw slot background
            bg_color = COLOR_BG_SLOT_SELECTED if is_selected else rl.Color(40, 35, 30, 150)
            border_color = COLOR_BORDER_SELECTED if is_selected else rl.Color(100, 90, 80, 150)
            
            rl.draw_rectangle(slot_x, slot_y, slot_size, slot_size, bg_color)
            rl.draw_rectangle_lines(slot_x, slot_y, slot_size, slot_size, border_color)
            
            # Draw thicker border if selected
            if is_selected:
                rl.draw_rectangle_lines(slot_x - 1, slot_y - 1, slot_size + 2, slot_size + 2, border_color)
            
            # Draw item if present in this slot
            if i < len(self._nearby_ground_items):
                ground_item = self._nearby_ground_items[i]
                item_type = ground_item.item_type
                amount = ground_item.amount
                
                # Draw item sprite (centered in slot)
                inset = 3 if slot_size < 32 else 4
                sprite_area_size = slot_size - inset * 2
                self._draw_item_sprite(item_type, slot_x + inset, slot_y + inset, sprite_area_size)
                
                # Draw amount at bottom of slot
                amount_str = str(amount)
                amount_x = slot_x + (slot_size - rl.measure_text(amount_str, amount_size)) // 2
                amount_y = slot_y + slot_size - amount_size - 2
                # Dark outline for readability
                rl.draw_text(amount_str, amount_x + 1, amount_y + 1, amount_size, rl.Color(0, 0, 0, 200))
                rl.draw_text(amount_str, amount_x, amount_y, amount_size, COLOR_TEXT_BRIGHT)

    def _draw_corpse_section(self, player, x, y, width, slot_size):
        """Draw corpse inventory as full character layout (equipment + accessories + inventory) in red box."""
        corpse = self._viewing_corpse
        slot_gap = 4
        left_padding = 6

        # Calculate total height needed (match the calculation in content height)
        acc_slot_size = slot_size - 4
        total_height = (
            24 +  # Top label
            12 + slot_size + 8 +  # Equipment section
            12 + (2 * (acc_slot_size + slot_gap)) + 8 +  # Accessories section
            12 + slot_size + 20  # Inventory section + padding
        )

        # Red background for corpse
        rl.draw_rectangle(x, y, width, total_height, rl.Color(80, 40, 40, 120))
        rl.draw_rectangle_lines(x, y, width, total_height, rl.Color(180, 80, 80, 200))

        # Label
        label = f"{corpse.character_name}'s Corpse"
        rl.draw_text(label, x + 4, y + 4, 9, rl.Color(220, 100, 100, 255))

        current_y = y + 20

        # Equipment row (Head + Body side by side) - empty for now
        rl.draw_text("Equipment", x + left_padding, current_y, 8, rl.Color(180, 80, 80, 200))
        current_y += 12

        head_selected = (self.gamepad_connected and self.selected_section == 'equipment_head' and self.selected_slot == 0)
        body_selected = (self.gamepad_connected and self.selected_section == 'equipment_body' and self.selected_slot == 0)

        # Head slot
        self._draw_equipment_slot(x + left_padding, current_y, slot_size, None, head_selected)
        rl.draw_text("H", x + left_padding + slot_size // 2 - 3, current_y + slot_size // 2 - 5, 10, rl.Color(120, 60, 60, 200))

        # Body slot
        body_x = x + left_padding + slot_size + slot_gap
        self._draw_equipment_slot(body_x, current_y, slot_size, None, body_selected)
        rl.draw_text("B", body_x + slot_size // 2 - 3, current_y + slot_size // 2 - 5, 10, rl.Color(120, 60, 60, 200))

        current_y += slot_size + 8

        # Accessories (2 rows of 4) - empty for now
        rl.draw_text("Accessories", x + left_padding, current_y, 8, rl.Color(180, 80, 80, 200))
        current_y += 12

        for row in range(2):
            for col in range(4):
                i = row * 4 + col
                is_selected = (self.gamepad_connected and self.selected_section == 'accessories' and self.selected_slot == i)
                slot_x = x + left_padding + col * (acc_slot_size + slot_gap)
                slot_y = current_y + row * (acc_slot_size + slot_gap)
                self._draw_equipment_slot(slot_x, slot_y, acc_slot_size, None, is_selected)

        current_y += 2 * (acc_slot_size + slot_gap) + 8

        # Base Inventory (5 slots) - use the reusable storage section method
        # Red theme for corpse
        self._draw_storage_section(
            corpse, x, current_y, width, "Base Inventory", 5, slot_size,
            section_key='barrel',  # Still use 'barrel' key for hit detection compatibility
            bg_color=rl.Color(0, 0, 0, 0),  # Transparent - already within red box
            border_color=rl.Color(0, 0, 0, 0),  # No border - already within red box
            label_color=rl.Color(180, 80, 80, 200),  # Red label
            slot_bg_color=rl.Color(60, 30, 30, 150),  # Dark red slot background
            slot_border_color=rl.Color(140, 70, 70, 150)  # Red slot border
        )

    def _draw_barrel_section(self, player, x, y, width, slot_size, num_rows):
        """Draw the Barrel/Corpse section showing container inventory."""
        if not self._viewing_container:
            return

        # Corpses show full character layout (equipment + accessories + inventory)
        if self._viewing_corpse:
            self._draw_corpse_section(player, x, y, width, slot_size)
            return

        # Regular barrel display
        slot_gap = 4
        left_padding = 6
        slots_per_row = 5

        # Section height
        section_height = 24 + num_rows * (slot_size + slot_gap)

        # Section background with wooden barrel color
        rl.draw_rectangle(x, y, width, section_height, rl.Color(80, 60, 40, 120))
        rl.draw_rectangle_lines(x, y, width, section_height, rl.Color(160, 120, 80, 200))

        # Label with container name
        label = self._viewing_container.name
        label_color = rl.Color(200, 180, 140, 255)
        rl.draw_text(label, x + 4, y + 4, 9, label_color)

        # Slots
        slots_x = x + left_padding
        slots_y = y + 18
        
        # Adapt text sizes based on slot size
        amount_size = 10 if slot_size >= 32 else 8
        
        # Get container inventory
        barrel_inventory = self._viewing_container.inventory
        total_slots = len(barrel_inventory)
        
        for i in range(total_slots):
            row = i // slots_per_row
            col = i % slots_per_row
            
            slot_x = slots_x + col * (slot_size + slot_gap)
            slot_y = slots_y + row * (slot_size + slot_gap)
            
            # Store slot rect for hit detection
            self._slot_rects[('barrel', i)] = (slot_x, slot_y, slot_size, slot_size)
            
            # Check if this slot is selected (only show on gamepad)
            is_selected = (self.gamepad_connected and 
                          self.selected_section == 'barrel' and 
                          self.selected_slot == i)
            
            # Draw slot background
            bg_color = COLOR_BG_SLOT_SELECTED if is_selected else rl.Color(50, 40, 30, 150)
            border_color = COLOR_BORDER_SELECTED if is_selected else rl.Color(120, 100, 70, 150)
            
            rl.draw_rectangle(slot_x, slot_y, slot_size, slot_size, bg_color)
            rl.draw_rectangle_lines(slot_x, slot_y, slot_size, slot_size, border_color)
            
            # Draw thicker border if selected
            if is_selected:
                rl.draw_rectangle_lines(slot_x - 1, slot_y - 1, slot_size + 2, slot_size + 2, border_color)
            
            # Draw item if present in this slot
            if barrel_inventory[i] is not None:
                item = barrel_inventory[i]
                item_type = item.get('type', '')
                amount = item.get('amount', 0)
                
                # Draw item sprite (centered in slot)
                inset = 3 if slot_size < 32 else 4
                sprite_area_size = slot_size - inset * 2
                self._draw_item_sprite(item_type, slot_x + inset, slot_y + inset, sprite_area_size)
                
                # Draw amount at bottom of slot
                amount_str = str(amount)
                amount_x = slot_x + (slot_size - rl.measure_text(amount_str, amount_size)) // 2
                amount_y = slot_y + slot_size - amount_size - 2
                # Dark outline for readability
                rl.draw_text(amount_str, amount_x + 1, amount_y + 1, amount_size, rl.Color(0, 0, 0, 200))
                rl.draw_text(amount_str, amount_x, amount_y, amount_size, COLOR_TEXT_BRIGHT)
    
    def _interact_ground_slot_full(self, slot_index):
        """Handle left-click on a ground slot - pick up / place / swap full stack."""
        if not self.state.player:
            return
        
        player = self.state.player
        
        # Get the ground item at this slot (if any)
        ground_item = None
        if slot_index < len(self._nearby_ground_items):
            ground_item = self._nearby_ground_items[slot_index]
        
        if self.held_item is None:
            # Pick up item from ground
            if ground_item:
                self.held_item = {'type': ground_item.item_type, 'amount': ground_item.amount}
                self.state.ground_items.remove_item(ground_item)
                self._update_nearby_ground_items(player)
        else:
            # We're holding something
            if ground_item is None:
                # Drop held item to ground
                self._drop_held_item_to_ground(player)
            elif ground_item.item_type == self.held_item.get('type'):
                # Same type - try to stack
                stack_limit = get_stack_limit(ground_item.item_type)
                if stack_limit is None:
                    # Unlimited stacking
                    ground_item.amount += self.held_item['amount']
                    self.held_item = None
                else:
                    space = stack_limit - ground_item.amount
                    if space > 0:
                        transfer = min(space, self.held_item['amount'])
                        ground_item.amount += transfer
                        self.held_item['amount'] -= transfer
                        if self.held_item['amount'] <= 0:
                            self.held_item = None
                    else:
                        # Stack full - swap
                        old_type = ground_item.item_type
                        old_amount = ground_item.amount
                        ground_item.item_type = self.held_item['type']
                        ground_item.amount = self.held_item['amount']
                        self.held_item = {'type': old_type, 'amount': old_amount}
            else:
                # Different type - swap
                old_type = ground_item.item_type
                old_amount = ground_item.amount
                ground_item.item_type = self.held_item['type']
                ground_item.amount = self.held_item['amount']
                self.held_item = {'type': old_type, 'amount': old_amount}
    
    def _interact_ground_slot_single(self, slot_index):
        """Handle right-click on a ground slot - pick up half / place single."""
        if not self.state.player:
            return
        
        player = self.state.player
        
        # Get the ground item at this slot (if any)
        ground_item = None
        if slot_index < len(self._nearby_ground_items):
            ground_item = self._nearby_ground_items[slot_index]
        
        if self.held_item is None:
            # Pick up half of stack from ground
            if ground_item:
                total = ground_item.amount
                take = (total + 1) // 2  # Ceiling division - take the larger half
                leave = total - take
                
                self.held_item = {'type': ground_item.item_type, 'amount': take}
                
                if leave > 0:
                    ground_item.amount = leave
                else:
                    self.state.ground_items.remove_item(ground_item)
                    self._update_nearby_ground_items(player)
        else:
            # We're holding something - place single item
            if ground_item is None:
                # Drop 1 item to ground
                self._drop_single_item_to_ground(player)
            elif ground_item.item_type == self.held_item.get('type'):
                # Same type - place 1 if room
                stack_limit = get_stack_limit(ground_item.item_type)
                if stack_limit is None or ground_item.amount < stack_limit:
                    ground_item.amount += 1
                    self.held_item['amount'] -= 1
                    if self.held_item['amount'] <= 0:
                        self.held_item = None
            # Different type - do nothing
    
    def _drop_held_item_to_ground(self, player):
        """Drop the entire held item stack to the ground."""
        if not self.held_item:
            return
        
        # Find valid drop position
        if player.zone:
            px, py = player.prevailing_x, player.prevailing_y
        else:
            px, py = player.x, player.y
        
        # Create blocking check function
        def is_blocked(x, y, zone):
            return self.state.is_position_blocked(x, y, exclude_char=player, zone=zone)
        
        drop_pos = find_valid_drop_position(px, py, player.zone, is_blocked)
        if drop_pos:
            self.state.ground_items.add_item(
                self.held_item['type'],
                self.held_item['amount'],
                drop_pos[0],
                drop_pos[1],
                player.zone
            )
            self.held_item = None
            self._update_nearby_ground_items(player)
    
    def _drop_single_item_to_ground(self, player):
        """Drop a single item from the held stack to the ground."""
        if not self.held_item or self.held_item['amount'] < 1:
            return
        
        # Find valid drop position
        if player.zone:
            px, py = player.prevailing_x, player.prevailing_y
        else:
            px, py = player.x, player.y
        
        # Create blocking check function
        def is_blocked(x, y, zone):
            return self.state.is_position_blocked(x, y, exclude_char=player, zone=zone)
        
        drop_pos = find_valid_drop_position(px, py, player.zone, is_blocked)
        if drop_pos:
            self.state.ground_items.add_item(
                self.held_item['type'],
                1,
                drop_pos[0],
                drop_pos[1],
                player.zone
            )
            self.held_item['amount'] -= 1
            if self.held_item['amount'] <= 0:
                self.held_item = None
            self._update_nearby_ground_items(player)
    
    def _quick_move_ground_to_inventory(self, slot_index):
        """Shift+click: Quick-move item from ground to inventory (Minecraft style)."""
        if not self.state.player:
            return

        player = self.state.player
        inventory = player.inventory

        if slot_index >= len(self._nearby_ground_items):
            return

        ground_item = self._nearby_ground_items[slot_index]
        item_type = ground_item.item_type
        amount_to_move = ground_item.amount
        stack_limit = get_stack_limit(item_type)

        amount_remaining = self.logic.transfer_item_to_inventory(item_type, amount_to_move, inventory, stack_limit)

        if amount_remaining <= 0:
            self.state.ground_items.remove_item(ground_item)
        else:
            ground_item.amount = amount_remaining

        self._update_nearby_ground_items(player)
    
    def _quick_move_inventory_to_ground(self, slot_index):
        """Shift+click: Quick-move item from inventory to ground."""
        if not self.state.player:
            return
        
        player = self.state.player
        inventory = player.inventory
        
        if slot_index < 0 or slot_index >= len(inventory):
            return
        
        slot_item = inventory[slot_index]
        if slot_item is None:
            return
        
        # Unequip if this was the equipped weapon
        if player.equipped_weapon == slot_index:
            player.equipped_weapon = None
        
        # Find valid drop position
        if player.zone:
            px, py = player.prevailing_x, player.prevailing_y
        else:
            px, py = player.x, player.y
        
        def is_blocked(x, y, zone):
            return self.state.is_position_blocked(x, y, exclude_char=player, zone=zone)
        
        drop_pos = find_valid_drop_position(px, py, player.zone, is_blocked)
        if drop_pos:
            self.state.ground_items.add_item(
                slot_item['type'],
                slot_item['amount'],
                drop_pos[0],
                drop_pos[1],
                player.zone
            )
            inventory[slot_index] = None
            self._update_nearby_ground_items(player)
    
    # =========================================================================
    # BARREL SLOT INTERACTION METHODS
    # =========================================================================
    
    def _interact_barrel_slot_full(self, slot_index):
        """Handle left-click on a barrel/corpse slot - pick up / place / swap full stack."""
        if not self.state.player or not self._viewing_container:
            return

        barrel = self._viewing_container
        barrel_inventory = barrel.inventory
        
        if slot_index < 0 or slot_index >= len(barrel_inventory):
            return
        
        barrel_item = barrel_inventory[slot_index]
        
        if self.held_item is None:
            # Pick up item from barrel
            if barrel_item:
                self.held_item = {'type': barrel_item['type'], 'amount': barrel_item['amount']}
                barrel_inventory[slot_index] = None
        else:
            # We're holding something
            if barrel_item is None:
                # Place held item in barrel
                barrel_inventory[slot_index] = {'type': self.held_item['type'], 'amount': self.held_item['amount']}
                self.held_item = None
            elif barrel_item['type'] == self.held_item.get('type'):
                # Same type - try to stack
                stack_limit = get_stack_limit(barrel_item['type'])
                if stack_limit is None:
                    # Unlimited stacking
                    barrel_item['amount'] += self.held_item['amount']
                    self.held_item = None
                else:
                    space = stack_limit - barrel_item['amount']
                    if space > 0:
                        transfer = min(space, self.held_item['amount'])
                        barrel_item['amount'] += transfer
                        self.held_item['amount'] -= transfer
                        if self.held_item['amount'] <= 0:
                            self.held_item = None
                    else:
                        # Stack full - swap
                        old_type = barrel_item['type']
                        old_amount = barrel_item['amount']
                        barrel_item['type'] = self.held_item['type']
                        barrel_item['amount'] = self.held_item['amount']
                        self.held_item = {'type': old_type, 'amount': old_amount}
            else:
                # Different type - swap
                old_type = barrel_item['type']
                old_amount = barrel_item['amount']
                barrel_item['type'] = self.held_item['type']
                barrel_item['amount'] = self.held_item['amount']
                self.held_item = {'type': old_type, 'amount': old_amount}
    
    def _interact_barrel_slot_single(self, slot_index):
        """Handle right-click on a barrel/corpse slot - pick up half / place single."""
        if not self.state.player or not self._viewing_container:
            return

        barrel = self._viewing_container
        barrel_inventory = barrel.inventory
        
        if slot_index < 0 or slot_index >= len(barrel_inventory):
            return
        
        barrel_item = barrel_inventory[slot_index]
        
        if self.held_item is None:
            # Pick up half of stack from barrel
            if barrel_item:
                total = barrel_item['amount']
                take = (total + 1) // 2  # Ceiling division - take the larger half
                leave = total - take
                
                self.held_item = {'type': barrel_item['type'], 'amount': take}
                
                if leave > 0:
                    barrel_item['amount'] = leave
                else:
                    barrel_inventory[slot_index] = None
        else:
            # We're holding something - place single item
            if barrel_item is None:
                # Place 1 item in barrel
                barrel_inventory[slot_index] = {'type': self.held_item['type'], 'amount': 1}
                self.held_item['amount'] -= 1
                if self.held_item['amount'] <= 0:
                    self.held_item = None
            elif barrel_item['type'] == self.held_item.get('type'):
                # Same type - place 1 if room
                stack_limit = get_stack_limit(barrel_item['type'])
                if stack_limit is None or barrel_item['amount'] < stack_limit:
                    barrel_item['amount'] += 1
                    self.held_item['amount'] -= 1
                    if self.held_item['amount'] <= 0:
                        self.held_item = None
            # Different type - do nothing
    
    def _quick_move_barrel_to_inventory(self, slot_index):
        """Shift+click: Quick-move item from barrel/corpse to player inventory."""
        if not self.state.player or not self._viewing_container:
            return

        player = self.state.player
        inventory = player.inventory
        barrel = self._viewing_container
        barrel_inventory = barrel.inventory

        if slot_index < 0 or slot_index >= len(barrel_inventory):
            return

        barrel_item = barrel_inventory[slot_index]
        if barrel_item is None:
            return

        item_type = barrel_item['type']
        amount_to_move = barrel_item['amount']
        stack_limit = get_stack_limit(item_type)

        amount_remaining = self.logic.transfer_item_to_inventory(item_type, amount_to_move, inventory, stack_limit)

        if amount_remaining <= 0:
            barrel_inventory[slot_index] = None
        else:
            barrel_item['amount'] = amount_remaining
    
    def _quick_move_inventory_to_barrel(self, slot_index):
        """Shift+click: Quick-move item from player inventory to barrel/corpse."""
        if not self.state.player or not self._viewing_container:
            return

        player = self.state.player
        inventory = player.inventory
        barrel = self._viewing_container
        barrel_inventory = barrel.inventory

        if slot_index < 0 or slot_index >= len(inventory):
            return

        slot_item = inventory[slot_index]
        if slot_item is None:
            return

        if player.equipped_weapon == slot_index:
            player.equipped_weapon = None

        item_type = slot_item['type']
        amount_to_move = slot_item['amount']
        stack_limit = get_stack_limit(item_type)

        amount_remaining = self.logic.transfer_item_to_inventory(item_type, amount_to_move, barrel_inventory, stack_limit)

        if amount_remaining <= 0:
            inventory[slot_index] = None
        else:
            slot_item['amount'] = amount_remaining
    
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

        # Dynamic hints based on current state
        if self.context_menu_open:
            # Context menu is open
            if self.gamepad_connected:
                hints = [
                    ("A", "Select"),
                    ("B", "Cancel"),
                ]
            else:
                hints = [
                    ("Click", "Select"),
                ]
        elif self._confirm_popup_open:
            # Confirmation popup is open
            if self.gamepad_connected:
                hints = [
                    ("D-pad", "Choose"),
                    ("A", "Confirm"),
                    ("B", "Cancel"),
                ]
            else:
                hints = [
                    ("Arrow keys", "Choose"),
                    ("Click", "Confirm"),
                ]
        elif self.held_item:
            # Holding an item
            if self.gamepad_connected:
                hints = [
                    ("A", "Place all"),
                    ("X", "Place one"),
                    ("B", "Cancel"),
                ]
            else:
                hints = [
                    ("Click", "Place all"),
                    ("Right Click", "Place one"),
                ]
        else:
            # Normal state - no item held
            if self.gamepad_connected:
                hints = [
                    ("A", "Pick up"),
                    ("Y", "Item menu"),
                    ("B / Select", "Close"),
                ]
            else:
                hints = [
                    ("Left Click", "Pick up"),
                    ("Right Click", "Item menu"),
                    ("Shift+Click", "Quick-move"),
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