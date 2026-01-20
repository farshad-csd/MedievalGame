# world_objects - Physical objects and spaces in the game world
"""
This module contains classes representing physical things in the game world:
- static_interactables: Buildings, containers, furniture, resources
- interiors: Interior spaces for buildings
- ground_items: Items dropped on the ground

These are purely representational - they describe what exists in the world,
not the logic of how things work (that's in game_logic.py).
"""

from .static_interactables import (
    Interactable,
    Ownable,
    Container,
    House,
    Barrel,
    Bed,
    Stove,
    Campfire,
    Tree,
    Corpse,
    InteractableManager,
)

from .interiors import (
    Interior,
    Window,
    InteriorManager,
)

from .ground_items import (
    GroundItem,
    GroundItemManager,
    find_valid_drop_position,
)

__all__ = [
    # static_interactables
    'Interactable',
    'Ownable',
    'Container',
    'House',
    'Barrel',
    'Bed',
    'Stove',
    'Campfire',
    'Tree',
    'Corpse',
    'InteractableManager',
    # interiors
    'Interior',
    'Window',
    'InteriorManager',
    # ground_items
    'GroundItem',
    'GroundItemManager',
    'find_valid_drop_position',
]
