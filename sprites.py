# sprites.py - Sprite loading and animation management (Raylib)
"""
Raylib-based sprite management for cross-platform compatibility.
Handles loading sprite sheets, extracting frames, and providing the correct
frame for a character's current state and direction.

Designed for compatibility with eventual Rust migration (raylib-rs).

Sprite Sheet Layout:
- Civilian1_Move.png: 4 frames × 8 directions (208x416, walking animation - unarmed/bow/fists)
- Civilian1_Move_swordsword.png: 4 frames × 8 directions (208x416, walking with sword in combat mode)
- Civilian1_Attack.png: 4 frames × 8 directions (208x416, attack animation - unarmed/fists)
- Civilian1_Attack_longsword.png: 4 frames × 8 directions (208x416, attack with sword)
- Civilian1_Faint.png: 1 frame (52x52, death pose)

Direction Row Mapping (rows 0-7, clockwise from down):
- Row 0: Down (front view)
- Row 1: Down-Right
- Row 2: Right
- Row 3: Up-Right
- Row 4: Up (back view)
- Row 5: Up-Left
- Row 6: Left
- Row 7: Down-Left

Animation States:
- Walk: 4 frames, loops continuously while moving (unarmed, bow, fists, or not in combat)
- WalkSword: 4 frames, loops continuously while moving (combat mode with sword equipped)
- Attack: 4 frames, plays once when attacking (unarmed/fists)
- AttackSword: 4 frames, plays once when attacking (sword equipped)
- Death: 1 frame, shown when dead
- Idle: Uses first frame of appropriate walk animation
"""

import pyray as rl
import os
import time


# Animation timing
WALK_FRAME_DURATION = 0.12  # 120ms per frame = 480ms per cycle (4 frames)
SPRINT_FRAME_DURATION = 0.08  # 80ms per frame = 320ms per cycle
ATTACK_FRAME_DURATION = 0.06  # 60ms per frame = 240ms for full attack (4 frames)
DEATH_FRAME_DURATION = 0.15  # Not used much with 1 frame

# Sprite sheet configuration
FRAMES_PER_ROW = 4  # 4 frames per animation
DIRECTIONS_PER_SHEET = 8  # 8 directions
FRAME_WIDTH = 52  # Width of each frame
FRAME_HEIGHT = 52  # Height of each frame

# Direction name to row index mapping
DIRECTION_TO_ROW = {
    'down': 0,
    'down-right': 1,
    'right': 2,
    'up-right': 3,
    'up': 4,
    'up-left': 5,
    'left': 6,
    'down-left': 7,
}


def hex_to_rgb(hex_color):
    """Convert hex color string to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


class SpriteManager:
    """Manages sprite loading and frame selection for all characters using Raylib."""
    
    def __init__(self, sprite_dir="."):
        """Initialize the sprite manager.
        
        Args:
            sprite_dir: Directory containing sprite PNG files
        """
        self.sprite_dir = sprite_dir
        self.textures = {}  # {action: Texture2D}
        self.loaded = False
        self._recolor_cache = {}  # Cache for recolored textures
        
    def load_sprites(self):
        """Load all sprite sheets."""
        if self.loaded:
            return
        
        # Map action names to filenames
        # Base sprites (unarmed / bow - no visible weapon)
        sprite_files = {
            'Walk': 'sprites/Civilian1_Move.png',
            'Attack': 'sprites/Civilian1_Attack.png',
            'Death': 'sprites/Civilian1_Faint.png',
            # Sword-specific sprites (longsword equipped)
            'WalkSword': 'sprites/Civilian1_Move_swordsword.png',
            'AttackSword': 'sprites/Civilian1_Attack_longsword.png',
        }
        
        for action, filename in sprite_files.items():
            filepath = os.path.join(self.sprite_dir, filename)
            
            if os.path.exists(filepath):
                texture = rl.load_texture(filepath)
                self.textures[action] = texture
            else:
                print(f"Warning: Sprite sheet not found: {filepath}")
                self.textures[action] = None
        
        self.loaded = True
    
    def unload_sprites(self):
        """Unload all loaded textures."""
        for texture in self.textures.values():
            if texture:
                rl.unload_texture(texture)
        
        # Unload cached recolored textures
        for texture in self._recolor_cache.values():
            if texture:
                rl.unload_texture(texture)
        
        self.textures = {}
        self._recolor_cache = {}
        self.loaded = False
    
    def get_direction_row(self, facing):
        """Map facing direction to sprite sheet row.
        
        Args:
            facing: One of 'up', 'down', 'left', 'right', 'up-left', 'up-right', 
                   'down-left', 'down-right'
                   
        Returns:
            Row index (0-7)
        """
        facing = facing.lower() if facing else 'down'
        return DIRECTION_TO_ROW.get(facing, 0)  # Default to 'down' (row 0)
    
    def get_frame_rect(self, action, direction_row, frame_idx):
        """Get the source rectangle for a specific frame.
        
        Args:
            action: 'Walk', 'WalkCombat', 'Attack', or 'Death'
            direction_row: Row index (0-7) for direction
            frame_idx: Frame index (0-3) for animation
            
        Returns:
            Rectangle for the frame source
        """
        if action == 'Death':
            # Death sprite is a single frame, no direction rows
            return rl.Rectangle(0, 0, FRAME_WIDTH, FRAME_HEIGHT)
        
        # For Walk, WalkCombat, and Attack: 4 columns × 8 rows
        x = frame_idx * FRAME_WIDTH
        y = direction_row * FRAME_HEIGHT
        return rl.Rectangle(x, y, FRAME_WIDTH, FRAME_HEIGHT)
    
    def get_frame(self, char, current_time=None):
        """Get the appropriate sprite frame for a character.
        
        Args:
            char: Character dictionary with state info
            current_time: Current time (defaults to time.time())
            
        Returns:
            Tuple of (frame_info_dict, should_flip) or (None, False) if no sprite
            frame_info_dict contains 'texture' and 'source' Rectangle
        """
        if not self.loaded:
            self.load_sprites()
            
        if current_time is None:
            current_time = time.time()
        
        facing = char.get('facing', 'down')
        direction_row = self.get_direction_row(facing)
        
        # Determine equipped weapon type for sprite selection
        equipped_weapon_type = self._get_equipped_weapon_type(char)
        
        # Determine animation state
        action, frame_idx = self._get_animation_state(char, current_time, equipped_weapon_type)
        
        texture = self.textures.get(action)
        if texture is None:
            # Fallback to base sprites if weapon-specific not found
            fallback_action = action.replace('Sword', '')
            texture = self.textures.get(fallback_action)
            if texture is None:
                return None, False
        
        # Get source rectangle
        source_rect = self.get_frame_rect(action, direction_row, frame_idx)
        
        # No flipping needed - we have all 8 directions
        return {'texture': texture, 'source': source_rect}, False
    
    def _get_equipped_weapon_type(self, char):
        """Get the weapon type equipped by a character.
        
        Args:
            char: Character object
            
        Returns:
            'melee', 'ranged', or None
        """
        # Import here to avoid circular imports
        from constants import ITEMS
        
        equipped_slot = getattr(char, 'equipped_weapon', None)
        if equipped_slot is None:
            return None
        
        inventory = getattr(char, 'inventory', [])
        if equipped_slot < 0 or equipped_slot >= len(inventory):
            return None
        
        item = inventory[equipped_slot]
        if item is None:
            return None
        
        item_type = item.get('type', '')
        item_info = ITEMS.get(item_type, {})
        return item_info.get('weapon_type')
    
    def _get_animation_state(self, char, current_time, equipped_weapon_type=None):
        """Determine which animation and frame to show.
        
        Args:
            char: Character dictionary
            current_time: Current time
            equipped_weapon_type: 'melee', 'ranged', or None
            
        Returns:
            Tuple of (action_name, frame_index)
        """
        # Check for death animation
        if char.get('is_dying') or char.get('health', 100) <= 0:
            # Death is now just 1 frame
            return 'Death', 0
        
        # Determine if using sword sprites (melee weapon equipped)
        use_sword_sprites = (equipped_weapon_type == 'melee')
        
        # Check for heavy attack charging (player only) - show first attack frame
        if char.get('heavy_attack_charging', False):
            action = 'AttackSword' if use_sword_sprites else 'Attack'
            return action, 0
        
        # Check for attack animation
        attack_start = char.get('attack_animation_start')
        if attack_start:
            elapsed = current_time - attack_start
            if elapsed < ATTACK_FRAME_DURATION * FRAMES_PER_ROW:
                frame_idx = int(elapsed / ATTACK_FRAME_DURATION)
                frame_idx = min(frame_idx, FRAMES_PER_ROW - 1)
                action = 'AttackSword' if use_sword_sprites else 'Attack'
                return action, frame_idx
        
        # Detect movement
        current_x = char.get('x', 0)
        current_y = char.get('y', 0)
        last_x = char.get('_last_anim_x', current_x)
        last_y = char.get('_last_anim_y', current_y)
        
        dx = current_x - last_x
        dy = current_y - last_y
        is_moving = abs(dx) > 0.001 or abs(dy) > 0.001
        
        char['_last_anim_x'] = current_x
        char['_last_anim_y'] = current_y
        
        # Check if in combat mode
        in_combat_mode = char.get('combat_mode', False)
        
        # Determine walk action based on combat mode and equipped weapon
        # Sword equipped in combat mode: use sword walk sprite
        # Otherwise (fists, bow, or not in combat): use regular walk sprite
        if in_combat_mode and use_sword_sprites:
            walk_action = 'WalkSword'
        else:
            walk_action = 'Walk'
        
        if is_moving:
            is_sprinting = char.get('is_sprinting', False)
            is_backpedaling = char.get('is_backpedaling', False)
            frame_duration = SPRINT_FRAME_DURATION if is_sprinting else WALK_FRAME_DURATION
            elapsed = current_time % (frame_duration * FRAMES_PER_ROW)
            frame_idx = int(elapsed / frame_duration)
            
            # Backpedaling reverses the animation frames
            if is_backpedaling:
                frame_idx = (FRAMES_PER_ROW - 1) - frame_idx
            
            return walk_action, frame_idx
        else:
            # Idle - first frame of walk
            return walk_action, 0
    
    def recolor_red_to_color(self, frame_info, target_color, red_threshold=0.3):
        """Replace red-ish pixels in a frame with a target color.
        
        This creates a new texture with the recolored pixels.
        Results are cached for performance.
        
        Args:
            frame_info: Dict with 'texture' and 'source' Rectangle
            target_color: Target color as (R, G, B) tuple or hex string "#RRGGBB"
            red_threshold: How dominant red must be (0.0-1.0, higher = more selective)
            
        Returns:
            Raylib Texture2D with recolored pixels
        """
        if frame_info is None:
            return None
        
        texture = frame_info['texture']
        source_rect = frame_info['source']
        
        # Convert hex color to RGB if needed
        if isinstance(target_color, str):
            color_hex = target_color.lstrip('#').upper()
            target_color = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
        else:
            color_hex = f"{target_color[0]:02X}{target_color[1]:02X}{target_color[2]:02X}"
        
        # Create cache key using texture id, source rect, and color
        cache_key = (id(texture), int(source_rect.x), int(source_rect.y), color_hex)
        
        if cache_key in self._recolor_cache:
            return self._recolor_cache[cache_key]
        
        # Load image from texture for pixel manipulation
        image = rl.load_image_from_texture(texture)
        
        # Crop to the frame we want
        cropped = rl.image_from_image(image, source_rect)
        rl.unload_image(image)
        
        # Get pixel data
        width = int(source_rect.width)
        height = int(source_rect.height)
        
        # Process pixels
        for y in range(height):
            for x in range(width):
                pixel = rl.get_image_color(cropped, x, y)
                r, g, b, a = pixel.r, pixel.g, pixel.b, pixel.a
                
                # Skip transparent pixels
                if a == 0:
                    continue
                
                # Skip very dark pixels
                brightness = (r + g + b) / 3
                if brightness < 30:
                    continue
                
                # Skip very light/white pixels
                if brightness > 240 and max(abs(r-g), abs(r-b), abs(g-b)) < 20:
                    continue
                
                # Check if red is dominant
                max_channel = max(r, g, b)
                if max_channel == 0:
                    continue
                
                r_norm = r / 255.0
                g_norm = g / 255.0
                b_norm = b / 255.0
                
                red_dominance = r_norm - max(g_norm, b_norm)
                is_reddish = (r > g * 1.2 and r > b * 1.2 and red_dominance > red_threshold)
                
                if is_reddish:
                    # Calculate luminosity
                    luminosity = 0.299 * r + 0.587 * g + 0.114 * b
                    target_lum = 0.299 * target_color[0] + 0.587 * target_color[1] + 0.114 * target_color[2]
                    
                    if target_lum > 0:
                        scale = luminosity / target_lum
                        scale = min(scale, 2.0)
                        new_r = min(255, int(target_color[0] * scale))
                        new_g = min(255, int(target_color[1] * scale))
                        new_b = min(255, int(target_color[2] * scale))
                    else:
                        new_r = new_g = new_b = int(luminosity)
                    
                    rl.image_draw_pixel(cropped, x, y, rl.Color(new_r, new_g, new_b, a))
        
        # Create texture from modified image
        result_texture = rl.load_texture_from_image(cropped)
        rl.unload_image(cropped)
        
        # Cache and return
        self._recolor_cache[cache_key] = result_texture
        
        return result_texture


# Global sprite manager instance
_sprite_manager = None


def get_sprite_manager(sprite_dir="."):
    """Get the global sprite manager instance.
    
    Args:
        sprite_dir: Directory containing sprites (only used on first call)
        
    Returns:
        SpriteManager instance
    """
    global _sprite_manager
    if _sprite_manager is None:
        _sprite_manager = SpriteManager(sprite_dir)
    return _sprite_manager