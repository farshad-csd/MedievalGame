# sprites.py - Sprite loading and animation management
"""
Handles loading sprite sheets, extracting frames, and providing the correct
frame for a character's current state and direction.

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

import pygame
import os
import time


# Animation timing
WALK_FRAME_DURATION = 0.1  # 100ms per frame = 600ms per cycle
SPRINT_FRAME_DURATION = 0.07  # 50ms per frame = 300ms per cycle (2x faster)
ATTACK_FRAME_DURATION = 0.042  # ~42ms per frame = 250ms for full attack (matches ATTACK_ANIMATION_DURATION)
DEATH_FRAME_DURATION = 0.15  # 150ms per frame = 900ms for death sequence

FRAMES_PER_SHEET = 6
FRAME_WIDTH = 48
FRAME_HEIGHT = 48


class SpriteManager:
    """Manages sprite loading and frame selection for all characters."""
    
    def __init__(self, sprite_dir="."):
        """Initialize the sprite manager and load all sprites.
        
        Args:
            sprite_dir: Directory containing sprite PNG files
        """
        self.sprite_dir = sprite_dir
        self.sprites = {}  # {direction: {action: [frames]}}
        self.loaded = False
        
    def load_sprites(self):
        """Load all sprite sheets and extract frames."""
        if self.loaded:
            return
            
        directions = ['U', 'S', 'D']
        actions = ['Walk', 'Attack', 'Death']
        
        for direction in directions:
            self.sprites[direction] = {}
            for action in actions:
                filename = f"sprites/{direction}_{action}.png"
                filepath = os.path.join(self.sprite_dir, filename)
                
                if os.path.exists(filepath):
                    # Load the image - use convert_alpha only if display is initialized
                    sheet = pygame.image.load(filepath)
                    if pygame.display.get_surface() is not None:
                        sheet = sheet.convert_alpha()
                    frames = self._extract_frames(sheet)
                    self.sprites[direction][action] = frames
                else:
                    print(f"Warning: Sprite sheet not found: {filepath}")
                    self.sprites[direction][action] = None
        
        self.loaded = True
    
    def _extract_frames(self, sheet):
        """Extract individual frames from a sprite sheet.
        
        Args:
            sheet: Pygame surface containing the sprite sheet
            
        Returns:
            List of pygame surfaces, one per frame
        """
        frames = []
        for i in range(FRAMES_PER_SHEET):
            frame = pygame.Surface((FRAME_WIDTH, FRAME_HEIGHT), pygame.SRCALPHA)
            frame.blit(sheet, (0, 0), (i * FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT))
            frames.append(frame)
        return frames
    
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
            return 'S', False  # Use side sprite for angled down
        elif facing == 'down-right':
            return 'S', True   # Use side sprite flipped for angled down-right
        elif facing == 'left':
            return 'S', False
        elif facing == 'right':
            return 'S', True  # Flip the side sprite
        else:
            return 'D', False  # Default to down
    
    def get_frame(self, char, current_time=None):
        """Get the appropriate sprite frame for a character.
        
        Args:
            char: Character dictionary with state info
            current_time: Current time (defaults to time.time())
            
        Returns:
            Tuple of (pygame.Surface, should_flip) or (None, False) if no sprite
        """
        if not self.loaded:
            self.load_sprites()
            
        if current_time is None:
            current_time = time.time()
        
        facing = char.get('facing', 'down')
        sprite_dir, should_flip = self.get_sprite_direction(facing)
        
        # Determine animation state
        action, frame_idx = self._get_animation_state(char, current_time)
        
        frames = self.sprites.get(sprite_dir, {}).get(action)
        if frames is None:
            return None, False
        
        # Clamp frame index
        frame_idx = min(frame_idx, len(frames) - 1)
        frame = frames[frame_idx]
        
        return frame, should_flip
    
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
                # Death animation holds on last frame
                frame_idx = min(frame_idx, FRAMES_PER_SHEET - 1)
                return 'Death', frame_idx
            # No death start time, show last frame
            return 'Death', FRAMES_PER_SHEET - 1
        
        # Check for attack animation
        attack_start = char.get('attack_animation_start')
        if attack_start:
            elapsed = current_time - attack_start
            if elapsed < ATTACK_FRAME_DURATION * FRAMES_PER_SHEET:
                frame_idx = int(elapsed / ATTACK_FRAME_DURATION)
                return 'Attack', frame_idx
            # Attack finished, fall through to walk/idle
        
        # Detect movement by comparing current position to last known position
        current_x = char.get('x', 0)
        current_y = char.get('y', 0)
        last_x = char.get('_last_anim_x', current_x)
        last_y = char.get('_last_anim_y', current_y)
        
        # Calculate distance moved since last check
        dx = current_x - last_x
        dy = current_y - last_y
        is_moving = abs(dx) > 0.001 or abs(dy) > 0.001
        
        # Update last position
        char['_last_anim_x'] = current_x
        char['_last_anim_y'] = current_y
        
        if is_moving:
            # Walk animation - continuous loop based on current time
            # Use faster animation when sprinting
            is_sprinting = char.get('is_sprinting', False)
            frame_duration = SPRINT_FRAME_DURATION if is_sprinting else WALK_FRAME_DURATION
            elapsed = current_time % (frame_duration * FRAMES_PER_SHEET)
            frame_idx = int(elapsed / frame_duration)
            return 'Walk', frame_idx
        else:
            # Idle - use first frame of walk
            return 'Walk', 0
    
    def scale_frame(self, frame, target_width, target_height):
        """Scale a frame to target dimensions.
        
        Args:
            frame: Pygame surface to scale
            target_width: Target width in pixels
            target_height: Target height in pixels
            
        Returns:
            Scaled pygame surface
        """
        return pygame.transform.scale(frame, (int(target_width), int(target_height)))


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
