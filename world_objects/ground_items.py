# ground_items.py - Ground item management for dropped items
"""
Handles items dropped on the ground in the game world.
Items can be dropped in exteriors or interiors and persist with the game state.

Ground items:
- Have float coordinates (not tied to cells)
- Are zone-specific (None for exterior, interior name for inside)
- Have a small visual offset for natural appearance when multiple items nearby
- Can be picked up via inventory Ground UI (not environment menu)
"""

import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple


@dataclass
class GroundItem:
    """A single item stack on the ground."""
    item_type: str  # e.g., 'wheat', 'gold', 'bread'
    amount: int
    x: float  # World coords for exterior, interior coords for interior
    y: float
    zone: Optional[str] = None  # None for exterior, interior name for inside
    
    # Small random offset for visual variety (set on creation)
    visual_offset_x: float = field(default_factory=lambda: random.uniform(-0.15, 0.15))
    visual_offset_y: float = field(default_factory=lambda: random.uniform(-0.15, 0.15))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for saving."""
        return {
            'item_type': self.item_type,
            'amount': self.amount,
            'x': self.x,
            'y': self.y,
            'zone': self.zone,
            'visual_offset_x': self.visual_offset_x,
            'visual_offset_y': self.visual_offset_y,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GroundItem':
        """Create from dictionary (for loading)."""
        item = cls(
            item_type=data['item_type'],
            amount=data['amount'],
            x=data['x'],
            y=data['y'],
            zone=data.get('zone'),
        )
        item.visual_offset_x = data.get('visual_offset_x', random.uniform(-0.15, 0.15))
        item.visual_offset_y = data.get('visual_offset_y', random.uniform(-0.15, 0.15))
        return item


class GroundItemManager:
    """
    Manages all ground items in the game world.
    
    Items are stored in a flat list and filtered by zone/distance when needed.
    """
    
    def __init__(self):
        self.items: List[GroundItem] = []
    
    def add_item(self, item_type: str, amount: int, x: float, y: float, 
                 zone: Optional[str] = None) -> GroundItem:
        """
        Add a new item to the ground.
        
        Args:
            item_type: Type of item ('wheat', 'gold', etc.)
            amount: Stack amount
            x, y: Position (world coords for exterior, interior coords for interior)
            zone: None for exterior, interior name for inside
            
        Returns:
            The created GroundItem
        """
        item = GroundItem(
            item_type=item_type,
            amount=amount,
            x=x,
            y=y,
            zone=zone,
        )
        self.items.append(item)
        return item
    
    def remove_item(self, item: GroundItem) -> bool:
        """
        Remove an item from the ground.
        
        Returns:
            True if item was found and removed, False otherwise
        """
        if item in self.items:
            self.items.remove(item)
            return True
        return False
    
    def get_items_in_zone(self, zone: Optional[str]) -> List[GroundItem]:
        """Get all ground items in a specific zone."""
        return [item for item in self.items if item.zone == zone]
    
    def get_items_near(self, x: float, y: float, radius: float, 
                       zone: Optional[str]) -> List[GroundItem]:
        """
        Get all ground items within radius of a position in the same zone.
        
        Args:
            x, y: Center position
            radius: Search radius
            zone: Zone to search in (None for exterior)
            
        Returns:
            List of nearby GroundItems
        """
        nearby = []
        for item in self.items:
            if item.zone != zone:
                continue
            dx = item.x - x
            dy = item.y - y
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= radius:
                nearby.append(item)
        return nearby
    
    def get_all_items(self) -> List[GroundItem]:
        """Get all ground items."""
        return self.items.copy()
    
    def clear(self):
        """Remove all ground items."""
        self.items.clear()
    
    def to_list(self) -> List[dict]:
        """Convert all items to list of dicts for saving."""
        return [item.to_dict() for item in self.items]
    
    def load_from_list(self, data: List[dict]):
        """Load items from list of dicts (from save file)."""
        self.items.clear()
        for item_data in data:
            self.items.append(GroundItem.from_dict(item_data))
    
    def __len__(self) -> int:
        return len(self.items)


def find_valid_drop_position(player_x: float, player_y: float, zone: Optional[str],
                              is_blocked_func, max_attempts: int = 20) -> Optional[Tuple[float, float]]:
    """
    Find a valid position to drop an item near the player.
    
    Args:
        player_x, player_y: Player's current position
        zone: Player's current zone
        is_blocked_func: Function(x, y, zone) -> bool that checks if position is blocked
        max_attempts: Maximum random positions to try
        
    Returns:
        (x, y) tuple of valid position, or None if no valid position found
    """
    # Try random positions within 0.3 to 0.8 cells of player
    for _ in range(max_attempts):
        angle = random.uniform(0, 2 * 3.14159)
        distance = random.uniform(0.3, 0.8)
        
        test_x = player_x + distance * (1 if random.random() > 0.5 else -1) * random.uniform(0.5, 1.0)
        test_y = player_y + distance * (1 if random.random() > 0.5 else -1) * random.uniform(0.5, 1.0)
        
        # Check if position is valid (not blocked)
        if not is_blocked_func(test_x, test_y, zone):
            return (test_x, test_y)
    
    # Fallback: try at player's feet with small offset
    offsets = [(0.2, 0.2), (-0.2, 0.2), (0.2, -0.2), (-0.2, -0.2), (0, 0.3), (0, -0.3)]
    for dx, dy in offsets:
        test_x = player_x + dx
        test_y = player_y + dy
        if not is_blocked_func(test_x, test_y, zone):
            return (test_x, test_y)
    
    # Last resort: drop at player position
    return (player_x, player_y)
