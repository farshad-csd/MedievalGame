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
#=print(json.dumps(WORLD_DATA, indent=2))
# WORLD_DATA  = {
#     "name": "Dunmere",
#     "size": 30,
#     "areas": [
#         {
#             "name": "Dunmere",
#             "role": "village",
#             "bounds": [0, 0, 25, 29],
#             "color": "#7CB068"
#         },
#         {
#             "name": "Dunmere Market",
#             "role": "market",
#             "allegiance": "Dunmere",
#             "bounds": [9, 18, 18, 27],
#             "color": "#D4AA78",
#             "cells": [
#                 [21, 9], [22, 9], [23, 9], [24, 9], [19, 10], [20, 10], [21, 10], [22, 10],
#                 [23, 10], [24, 10], [26, 10], [19, 11], [20, 11], [21, 11], [22, 11], [23, 11],
#                 [24, 11], [25, 11], [26, 11], [19, 12], [20, 12], [21, 12], [22, 12], [23, 12],
#                 [24, 12], [25, 12], [26, 12], [18, 13], [19, 13], [20, 13], [21, 13], [22, 13],
#                 [23, 13], [20, 14], [21, 14], [22, 14], [23, 14], [24, 14], [19, 15], [20, 15],
#                 [21, 15], [22, 15], [23, 15], [24, 15], [22, 16], [23, 16], [23, 17]
#             ]
#         },
#         {
#             "name": "Dunmere Military Housing",
#             "role": "military_housing",
#             "allegiance": "Dunmere",
#             "bounds": [5, 4, 10, 10],
#             "color": "#6B6B7A"
#         },
#         {
#             "name": "Dunmere Farmhouse 1",
#             "role": "farmhouse",
#             "allegiance": "Dunmere",
#             "bounds": [6, 10, 10, 14],
#             "color": "#C4813D"
#         },
#         {
#             "name": "Dunmere Farmhouse 2",
#             "role": "farmhouse",
#             "allegiance": "Dunmere",
#             "bounds": [11, 7, 15, 11],
#             "color": "#C4813D"
#         },
#         {
#             "name": "Dunmere Farm 1",
#             "role": "farm",
#             "allegiance": "Dunmere",
#             "bounds": [2, 14, 13, 22],
#             "color": "#7CB068",
#             "has_farm_cells": True,
#             "farm_cells": [
#                 [20, 5], [17, 3], [17, 9], [19, 6], [17, 6], [19, 3], [19, 9], [16, 4],
#                 [15, 2], [16, 7], [18, 4], [15, 11], [15, 5], [16, 10], [18, 7], [15, 8],
#                 [20, 4], [17, 5], [19, 2], [17, 11], [17, 8], [19, 5], [19, 8], [16, 3],
#                 [16, 9], [15, 7], [16, 6], [18, 3], [15, 10], [16, 12], [20, 6], [18, 6],
#                 [21, 5], [20, 3], [17, 4], [14, 8], [17, 7], [19, 4], [17, 10], [19, 7],
#                 [16, 2], [16, 5], [15, 3], [15, 9], [18, 2], [16, 8], [18, 5], [21, 4],
#                 [20, 2], [16, 11], [18, 8]
#             ]
#         },
#         {
#             "name": "Dunmere Farm 2",
#             "role": "farm",
#             "allegiance": "Dunmere",
#             "bounds": [10, 2, 23, 9],
#             "color": "#7CB068",
#             "has_farm_cells": True,
#             "farm_cells": [
#                 [6, 18], [6, 15], [3, 16], [4, 15], [3, 13], [3, 19], [5, 16], [4, 18],
#                 [4, 21], [3, 22], [5, 19], [8, 18], [5, 22], [2, 11], [2, 14], [2, 20],
#                 [7, 16], [6, 14], [3, 18], [4, 17], [3, 15], [3, 21], [5, 18], [4, 20],
#                 [5, 15], [5, 21], [2, 10], [2, 13], [2, 19], [6, 16], [7, 15], [6, 19],
#                 [7, 18], [4, 16], [3, 14], [4, 19], [3, 17], [3, 20], [5, 17], [8, 16],
#                 [5, 20], [2, 12], [2, 18], [2, 21]
#             ]
#         }
#     ],
#     "roads": [
#         [20, 14], [21, 13], [12, 10], [12, 16], [22, 14], [12, 13], [14, 16], [17, 15],
#         [16, 14], [11, 14], [13, 11], [18, 14], [10, 15], [13, 14], [16, 16], [15, 14],
#         [13, 17], [7, 10], [15, 17], [20, 13], [18, 13], [22, 13], [12, 12], [12, 15],
#         [14, 18], [14, 15], [17, 14], [9, 16], [19, 14], [11, 16], [11, 13], [13, 10],
#         [13, 16], [13, 13], [15, 16], [16, 15], [18, 15], [21, 14], [12, 11], [12, 14],
#         [12, 17], [14, 14], [14, 17], [8, 10], [9, 15], [19, 13], [11, 12], [10, 16],
#         [11, 15], [13, 12], [13, 18], [13, 15], [15, 18], [16, 17], [15, 15]
#     ],
#     "trees": [
#         [17, 16], [26, 18], [23, 20], [6, 21], [26, 24], [10, 28]
#     ]
# }

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
# Positioning:
#   Barracks (world coords): Objects along bottom-left interior
#     - Barrel at (x_start, y_end - 1)
#     - Beds in row: (x_start + 1, y_end - 1), (x_start + 2, y_end - 1), ...
#     - Stove at (x_end - 1, y_end - 1)
#   House/Farmhouse (interior coords): Objects against back wall
#     - Barrel at (0, 0) - back-left
#     - Bed at (1, 0) - next to barrel
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
            
            # Bed at interior position (1, 0) - next to barrel
            beds.append({
                "name": f"{name} Bed",
                "position": [1, 0],  # Interior coordinates (against back wall)
                "home": name,
                "zone": interior_name
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