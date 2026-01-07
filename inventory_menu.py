# inventory_menu.py - Inventory, Status, and World Map menu system
"""
Handles the inventory screen overlay with three tabs:
- World: Transparent view of game world with inventory panel
- Status: Character skills and stats
- Map: World map (placeholder)

Extracted from gui.py to reduce file size and improve organization.
"""

import pyray as rl
from constants import SKILLS

# =============================================================================
# HUD STYLING CONSTANTS (shared with gui.py)
# =============================================================================
HUD_FONT_SIZE_SMALL = 10
HUD_FONT_SIZE_MEDIUM = 13
HUD_FONT_SIZE_LARGE = 16
HUD_BAR_HEIGHT = 4

# Colors
COLOR_HEALTH = rl.Color(201, 76, 76, 255)      # Red
COLOR_STAMINA = rl.Color(92, 184, 92, 255)     # Green  
COLOR_FATIGUE = rl.Color(91, 192, 222, 255)    # Cyan
COLOR_HUNGER = rl.Color(217, 164, 65, 255)     # Gold/Orange

COLOR_TEXT_BRIGHT = rl.Color(255, 255, 255, 230)
COLOR_TEXT_DIM = rl.Color(255, 255, 255, 128)
COLOR_TEXT_FAINT = rl.Color(255, 255, 255, 64)

COLOR_BG_SLOT = rl.Color(255, 255, 255, 20)
COLOR_BG_SLOT_ACTIVE = rl.Color(255, 255, 255, 50)
COLOR_BORDER = rl.Color(255, 255, 255, 60)


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
        self.gamepad_connected = False
    
    def open(self):
        """Open the inventory menu."""
        self.is_open = True
    
    def close(self):
        """Close the inventory menu."""
        self.is_open = False
    
    def toggle(self):
        """Toggle the inventory menu open/closed."""
        self.is_open = not self.is_open
    
    def next_tab(self):
        """Switch to the next tab."""
        self.current_tab = (self.current_tab + 1) % 3
    
    def prev_tab(self):
        """Switch to the previous tab."""
        self.current_tab = (self.current_tab - 1) % 3
    
    def update_input(self, mouse_x, mouse_y, mouse_left_click, gamepad_connected):
        """Update input state from GUI."""
        self.mouse_x = mouse_x
        self.mouse_y = mouse_y
        self.mouse_left_click = mouse_left_click
        self.gamepad_connected = gamepad_connected
    
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
        
        # Layout: Left panel (1/3) = inventory, Right panel (2/3) = tabs
        left_width = self.canvas_width // 3
        right_width = self.canvas_width - left_width
        
        # Only draw overlay on non-world tabs
        if self.current_tab != 0:
            # Semi-transparent overlay on right side only
            rl.draw_rectangle(left_width, 0, right_width, self.canvas_height, 
                             rl.Color(13, 21, 32, 220))
        
        # Left panel background (always drawn)
        rl.draw_rectangle(0, 0, left_width, self.canvas_height, rl.Color(13, 21, 32, 230))
        rl.draw_line(left_width, 0, left_width, self.canvas_height, COLOR_BORDER)
        
        # Draw left panel content
        self._draw_left_panel(player, 0, 0, left_width)
        
        # Draw right panel with tabs (handles click detection)
        self._draw_right_panel(player, left_width, 0, right_width)
        
        # Close hint
        close_hint = "Select to close" if self.gamepad_connected else "I / Tab to close"
        hint_width = rl.measure_text(close_hint, HUD_FONT_SIZE_SMALL)
        rl.draw_text(close_hint, self.canvas_width - hint_width - 20, 
                    self.canvas_height - 25, HUD_FONT_SIZE_SMALL, COLOR_TEXT_FAINT)
    
    def _draw_left_panel(self, player, x, y, width):
        """Draw the left inventory panel with equipment and storage."""
        padding = 12
        inner_x = x + padding
        inner_y = y + padding
        inner_width = width - padding * 2
        
        # === STATUS BAR (Health, Hunger, Weight, Gold) ===
        self._draw_status_bar(player, inner_x, inner_y, inner_width)
        inner_y += 60
        
        # === EQUIPMENT AREA (Head/Body + Accessories) ===
        self._draw_equipment_area(player, inner_x, inner_y, inner_width)
        inner_y += 120  # label + 2 rows of slots + gaps
        
        # === BASE INVENTORY (5 slots) ===
        self._draw_storage_section(player, inner_x, inner_y, inner_width, "Base Inventory", 5)
    
    def _draw_status_bar(self, player, x, y, width):
        """Draw compact status bar with health, hunger, stamina, fatigue, encumbrance, gold."""
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
        """Draw equipment slots: head and body on left, 8 accessory slots (2x4) on right."""
        slot_size = 36  # Same size as base inventory slots
        slot_gap = 4
        label_height = 14  # Space for labels above slots
        
        # Starting y for slots (after label space)
        slots_y = y
        
        # Left side: Head slot on top, Body slot below (stacked vertically)
        equip_x = x + 8
        
        # Head slot with label
        rl.draw_text("Head", equip_x, slots_y, 9, COLOR_TEXT_FAINT)
        self._draw_equipment_slot(equip_x, slots_y + label_height, slot_size, None)
        
        # Body slot with label (below head)
        body_y = slots_y + label_height + slot_size + slot_gap + 4
        rl.draw_text("Body", equip_x, body_y, 9, COLOR_TEXT_FAINT)
        self._draw_equipment_slot(equip_x, body_y + label_height, slot_size, None)
        
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
    
    def _draw_equipment_slot(self, x, y, size, item):
        """Draw a single equipment slot."""
        has_item = item is not None
        bg_color = COLOR_BG_SLOT_ACTIVE if has_item else COLOR_BG_SLOT
        rl.draw_rectangle(x, y, size, size, bg_color)
        rl.draw_rectangle_lines(x, y, size, size, COLOR_BORDER)
    
    def _draw_storage_section(self, player, x, y, width, label, num_slots):
        """Draw a storage section with label and slots."""
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
    
    def _draw_right_panel(self, player, x, y, width):
        """Draw the right panel with tabs: World, Status, Map."""
        tab_names = ["World", "Status", "Map"]
        tab_height = 40
        
        # Tab bar background (slight tint so tabs are visible on world tab)
        rl.draw_rectangle(x, y, width, tab_height, rl.Color(13, 21, 32, 180))
        
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
        """Draw the Status tab - shows skills."""
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
