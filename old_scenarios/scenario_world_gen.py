# scenario_world.py - World layout: regions, objects, and structures
# Edit this file to create a new map within the same simulation structure
# Objects (barrels, beds, stoves) are generated programmatically from area data

from town_gen import generate_areas
import json


# =============================================================================
# RAW WORLD DATA (JSON-serializable)
# =============================================================================
WORLD_DATA = generate_areas(30, 20, 1, seed=2, name="Dunmere", trees=0.0)
print(json.dumps(WORLD_DATA, indent=2))

# =============================================================================
# DERIVED CONSTANTS
# =============================================================================
VILLAGE_NAME = WORLD_DATA["name"]
SIZE = WORLD_DATA["size"]
AREAS = WORLD_DATA["areas"]

# =============================================================================
# OBJECT GENERATION RULES
# =============================================================================
# Which area roles get which objects:
#   barracks/military_housing: 1 barrel, 3 beds (Steward + 2 soldiers), 1 stove
#   farm: 1 barrel, 1 bed, 1 stove
#   market, village, encampment: nothing
#
# Positioning within bounds [y_start, x_start, y_end, x_end]:
#   Barracks: Objects along bottom-left interior
#     - Barrel at (x_start, y_end - 1)
#     - Beds in row: (x_start + 1, y_end - 1), (x_start + 2, y_end - 1), ...
#     - Stove at (x_end - 1, y_end - 1)
#   Farm: Objects in top-left corner
#     - Barrel at (x_start, y_start)
#     - Bed at (x_start + 1, y_start)
#     - Stove at (x_start + 2, y_start)

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
            beds.append({
                "name": f"{name} Steward Bed",
                "position": [x_start + 1, y_end - 1],
                "home": name
            })
            beds.append({
                "name": f"{name} Bed 1",
                "position": [x_start + 2, y_end - 1],
                "home": name
            })
            beds.append({
                "name": f"{name} Bed 2",
                "position": [x_start + 3, y_end - 1],
                "home": name
            })
            
            # Stove at bottom-right interior
            stoves.append({
                "name": f"{name} Stove",
                "position": [x_end - 1, y_end - 1],
                "home": name
            })
            
        elif role == "farm":
            # Objects in top-left corner of farm
            barrels.append({
                "name": f"{name} Barrel",
                "position": [x_start, y_start],
                "home": name
            })
            
            beds.append({
                "name": f"{name} Bed",
                "position": [x_start + 1, y_start],
                "home": name
            })
            
            stoves.append({
                "name": f"{name} Stove",
                "position": [x_start + 2, y_start],
                "home": name
            })
    
    return barrels, beds, stoves

# =============================================================================
# GENERATED OBJECT DEFINITIONS
# =============================================================================
BARRELS, BEDS, STOVES = _generate_objects()