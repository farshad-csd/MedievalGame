# sprites.py - Sprite loading and animation management (Raylib)
"""
Raylib-based sprite management for cross-platform compatibility.
Handles loading sprite sheets, extracting frames, and providing the correct
frame for a character's current state and direction.

Designed for compatibility with eventual Rust migration (raylib-rs).

Sprite Directions:
- U (Up): Used for 'up', 'up-left', 'up-right'
- S (Side): Used for 'left', 'right' (flipped horizontally for right)
- D (Down): Used for 'down', 'down-left', 'down-right'

Animation States:
- Walk: 6 frames, loops continuously while moving
- Attack: 6 frames, plays once when attacking
- Death: 6 frames, plays once when dying, holds last frame
- Idle: Uses first frame of Walk
"""

import pyray as rl
import os
import time


# Animation timing
WALK_FRAME_DURATION = 0.1  # 100ms per frame = 600ms per cycle
SPRINT_FRAME_DURATION = 0.07  # 70ms per frame = 420ms per cycle
ATTACK_FRAME_DURATION = 0.042  # ~42ms per frame = 250ms for full attack
DEATH_FRAME_DURATION = 0.15  # 150ms per frame = 900ms for death sequence

FRAMES_PER_SHEET = 6
FRAME_WIDTH = 48
FRAME_HEIGHT = 48


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
        self.textures = {}  # {direction: {action: Texture2D}}
        self.frames = {}    # {direction: {action: [Rectangle]}} - source rects for each frame
        self.loaded = False
        self._recolor_cache = {}  # Cache for recolored textures: (texture_id, color_hex) -> Texture2D
        
    def load_sprites(self):
        """Load all sprite sheets and extract frame rectangles."""
        if self.loaded:
            return
            
        directions = ['U', 'S', 'D']
        actions = ['Walk', 'Attack', 'Death']
        
        for direction in directions:
            self.textures[direction] = {}
            self.frames[direction] = {}
            
            for action in actions:
                filename = f"sprites/{direction}_{action}.png"
                filepath = os.path.join(self.sprite_dir, filename)
                
                if os.path.exists(filepath):
                    # Load texture
                    texture = rl.load_texture(filepath)
                    self.textures[direction][action] = texture
                    
                    # Create frame rectangles
                    frame_rects = []
                    for i in range(FRAMES_PER_SHEET):
                        rect = rl.Rectangle(
                            i * FRAME_WIDTH, 0,
                            FRAME_WIDTH, FRAME_HEIGHT
                        )
                        frame_rects.append(rect)
                    self.frames[direction][action] = frame_rects
                else:
                    print(f"Warning: Sprite sheet not found: {filepath}")
                    self.textures[direction][action] = None
                    self.frames[direction][action] = None
        
        self.loaded = True
    
    def unload_sprites(self):
        """Unload all loaded textures."""
        for direction in self.textures.values():
            for texture in direction.values():
                if texture:
                    rl.unload_texture(texture)
        
        # Unload cached recolored textures
        for texture in self._recolor_cache.values():
            if texture:
                rl.unload_texture(texture)
        
        self.textures = {}
        self.frames = {}
        self._recolor_cache = {}
        self.loaded = False
    
    def get_sprite_direction(self, facing):
        """Map 8-direction facing to 3 sprite directions.
        
        Args:
            facing: One of 'up', 'down', 'left', 'right', 'up-left', 'up-right', 
                   'down-left', 'down-right'
                   
        Returns:
            Tuple of (sprite_direction, should_flip)
            - sprite_direction: 'U', 'S', or 'D'
            - should_flip: True if sprite should be horizontally flipped
        """
        facing = facing.lower() if facing else 'down'
        
        if facing == 'up':
            return 'U', False
        elif facing == 'up-left':
            return 'U', False
        elif facing == 'up-right':
            return 'U', False
        elif facing == 'down':
            return 'D', False
        elif facing == 'down-left':
            return 'S', False
        elif facing == 'down-right':
            return 'S', True
        elif facing == 'left':
            return 'S', False
        elif facing == 'right':
            return 'S', True
        else:
            return 'D', False
    
    def get_frame(self, char, current_time=None):
        """Get the appropriate sprite frame for a character.
        
        Args:
            char: Character dictionary with state info
            current_time: Current time (defaults to time.time())
            
        Returns:
            Tuple of (Texture2D, should_flip) or (None, False) if no sprite
        """
        if not self.loaded:
            self.load_sprites()
            
        if current_time is None:
            current_time = time.time()
        
        facing = char.get('facing', 'down')
        sprite_dir, should_flip = self.get_sprite_direction(facing)
        
        # Determine animation state
        action, frame_idx = self._get_animation_state(char, current_time)
        
        texture = self.textures.get(sprite_dir, {}).get(action)
        frame_rects = self.frames.get(sprite_dir, {}).get(action)
        
        if texture is None or frame_rects is None:
            return None, False
        
        # Clamp frame index
        frame_idx = min(frame_idx, len(frame_rects) - 1)
        
        # Return the texture and frame info
        # We'll return a dict with texture and source rect for drawing
        return {'texture': texture, 'source': frame_rects[frame_idx]}, should_flip
    
    def _get_animation_state(self, char, current_time):
        """Determine which animation and frame to show.
        
        Args:
            char: Character dictionary
            current_time: Current time
            
        Returns:
            Tuple of (action_name, frame_index)
        """
        # Check for death animation
        if char.get('is_dying') or char.get('health', 100) <= 0:
            death_start = char.get('death_animation_start')
            if death_start:
                elapsed = current_time - death_start
                frame_idx = int(elapsed / DEATH_FRAME_DURATION)
                frame_idx = min(frame_idx, FRAMES_PER_SHEET - 1)
                return 'Death', frame_idx
            return 'Death', FRAMES_PER_SHEET - 1
        
        # Check for attack animation
        attack_start = char.get('attack_animation_start')
        if attack_start:
            elapsed = current_time - attack_start
            if elapsed < ATTACK_FRAME_DURATION * FRAMES_PER_SHEET:
                frame_idx = int(elapsed / ATTACK_FRAME_DURATION)
                return 'Attack', frame_idx
        
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
        
        if is_moving:
            is_sprinting = char.get('is_sprinting', False)
            is_backpedaling = char.get('is_backpedaling', False)
            frame_duration = SPRINT_FRAME_DURATION if is_sprinting else WALK_FRAME_DURATION
            elapsed = current_time % (frame_duration * FRAMES_PER_SHEET)
            frame_idx = int(elapsed / frame_duration)
            
            if is_backpedaling:
                frame_idx = (FRAMES_PER_SHEET - 1) - frame_idx
            
            return 'Walk', frame_idx
        else:
            return 'Walk', 0
    
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
