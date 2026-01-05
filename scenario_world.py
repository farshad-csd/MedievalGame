# scenario_world.py - World layout: regions, objects, and structures
# Edit this file to create a new map within the same simulation structure
# Objects (barrels, beds, stoves) are generated programmatically from area data

from town_gen import generate_areas
import json


# =============================================================================
# RAW WORLD DATA (JSON-serializable)
# =============================================================================
#WORLD_DATA = generate_areas(60, 10, 2, seed=None, name="Dunmere", trees=0.05)
WORLD_DATA = generate_areas(30, 0, 2, seed=4, name="Dunmere", trees=0.03)
#WORLD_DATA = generate_areas(350, 20, 4, seed=4, name="Dunmere", trees=0.08)

# =============================================================================
# DERIVED CONSTANTS
# =============================================================================
VILLAGE_NAME = WORLD_DATA["name"]
SIZE = WORLD_DATA["size"]
AREAS = WORLD_DATA["areas"]
ROADS = WORLD_DATA.get("roads", [])
TREES = WORLD_DATA.get("trees", [])

# =============================================================================
# HOUSE DEFINITIONS
# =============================================================================
# Houses and farmhouses are extracted for the interactable system
def _generate_houses():
    """Generate house definitions from areas with role='house' or 'farmhouse'."""
    houses = []
    for area in AREAS:
        role = area.get("role", "")
        if role in ("house", "farmhouse"):
            houses.append({
                "name": area["name"],
                "bounds": area["bounds"],
                "allegiance": area.get("allegiance")
            })
    return houses

HOUSES = _generate_houses()

# =============================================================================
# OBJECT GENERATION RULES
# =============================================================================
# Which area roles get which objects:
#   barracks/military_housing: 1 barrel, 3 beds (Steward + 2 soldiers), 1 stove
#       - Objects in WORLD coordinates (exterior)
#   house/farmhouse: 1 barrel, 1 bed, 1 stove
#       - Objects in INTERIOR coordinates with zone set to interior name
#       - Interior layout: back wall at y=-1, floor from y=0 to y=height-1
#       - Objects placed at y=0 (against back wall)
#   market, village, encampment, farm: nothing
#
# Positioning (beds are 2 cells tall visually, with expanded collision bounds):
#   Barracks (world coords): Objects along bottom-left interior
#     - Barrel at (x_start, y_end - 1)
#     - Beds in row at y_end - 2: (x_start + 1), (x_start + 2), (x_start + 3)
#     - Stove at (x_end - 1, y_end - 1)
#   House/Farmhouse (interior coords): Objects against back wall
#     - Barrel at (0, 0) - back-left
#     - Bed at (1, 0) - next to barrel (2 cells tall, spans y=0 and y=1)
#     - Stove at (2, 0) - next to bed

def _generate_objects():
    """Generate barrels, beds, and stoves based on area roles and bounds."""
    barrels = []
    beds = []
    stoves = []
    
    for area in AREAS:
        role = area.get("role", "")
        name = area["name"]
        bounds = area["bounds"]  # [y_start, x_start, y_end, x_end]
        y_start, x_start, y_end, x_end = bounds
        
        if role in ("barracks", "military_housing"):
            # Barrel at bottom-left interior
            barrels.append({
                "name": f"{name} Barrel",
                "position": [x_start, y_end - 1],  # [x, y]
                "home": name
            })
            
            # 3 beds in a row (Steward bed + 2 soldier beds)
            # Beds are 1 cell wide, 2 cells tall visually (with expanded collision)
            beds.append({
                "name": f"{name} Steward Bed",
                "position": [x_start + 1, y_end - 2],  # y-2 because bed is 2 cells tall
                "home": name,
                "height": 2
            })
            beds.append({
                "name": f"{name} Bed 1",
                "position": [x_start + 2, y_end - 2],
                "home": name,
                "height": 2
            })
            beds.append({
                "name": f"{name} Bed 2",
                "position": [x_start + 3, y_end - 2],
                "home": name,
                "height": 2
            })
            
            # Stove at bottom-right interior
            stoves.append({
                "name": f"{name} Stove",
                "position": [x_end - 1, y_end - 1],
                "home": name
            })
            
        elif role in ("house", "farmhouse"):
            # Objects inside the house interior (not world coordinates)
            # Interior is typically 4x4, objects placed in interior coordinate space
            # Zone is set to the house name (which matches interior name)
            # y=0 is the floor row against the back wall (back wall is at y=-1)
            interior_name = name  # Interior uses same name as house
            
            # Barrel at interior position (0, 0) - back-left corner
            barrels.append({
                "name": f"{name} Barrel",
                "position": [0, 0],  # Interior coordinates (against back wall)
                "home": name,
                "zone": interior_name
            })
            
            # Bed at interior position (1, 0) - next to barrel (2 cells tall, spans y=0 and y=1)
            beds.append({
                "name": f"{name} Bed",
                "position": [1, 0],  # Interior coordinates (against back wall)
                "home": name,
                "zone": interior_name,
                "height": 2
            })
            
            # Stove at interior position (2, 0) - next to bed
            stoves.append({
                "name": f"{name} Stove",
                "position": [2, 0],  # Interior coordinates (against back wall)
                "home": name,
                "zone": interior_name
            })
    
    return barrels, beds, stoves

# =============================================================================
# GENERATED OBJECT DEFINITIONS
# =============================================================================
BARRELS, BEDS, STOVES = _generate_objects()