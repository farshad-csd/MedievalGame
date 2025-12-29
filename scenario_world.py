# scenario_world.py - World layout: regions, objects, and structures
# Edit this file to create a new map within the same simulation structure

# =============================================================================
# SCENARIO NAME
# =============================================================================
VILLAGE_NAME = "Dunmere"

# =============================================================================
# AREA DEFINITIONS (JSON-serializable)
# =============================================================================
# Each area has: name, bounds (start_y, start_x, end_y, end_x), color, and optional properties
# The "role" field links areas to game mechanics (see AREA_ROLES in constants.py)
AREAS = [
    {
        "name": "VILLAGE",
        "role": "residential",
        "bounds": [6, 6, 12, 12],  # start_y, start_x, end_y, end_x
        "color": "#fffacd",
        "is_village_part": True
    },
    {
        "name": "MARKET",
        "role": "market",
        "bounds": [6, 7, 8, 11],
        "color": "#ADD8E6",
        "is_village_part": True
    },
    {
        "name": "BARRACKS",
        "role": "military_housing",
        "bounds": [10, 7, 12, 11],
        "color": "#DEB887",
        "is_village_part": True
    },
    {
        "name": "FARM",
        "role": "farm",
        "bounds": [2, 15, 19, 20],
        "color": "#90EE90",
        "has_farm_cells": True,
        "farm_cell_bounds": [2, 15, 19, 20],  # y_start, x_start, y_end, x_end for harvestable cells
        "allegiance": "VILLAGE"  # This farm belongs to the village
    },
    {
        "name": "RUIN",
        "bounds": [17, 0, 19, 3],
        "color": "#f0e6e6"
    }
]

# =============================================================================
# BARREL DEFINITIONS (JSON-serializable)
# =============================================================================
# Barrels have: name, position (x, y), home area
# Ownership is assigned at runtime based on jobs
BARRELS = [
    {
        "name": "Farm Barrel",
        "position": [15, 2],  # x, y - top-left corner of farm
        "home": "FARM"
    },
    {
        "name": "Barracks Barrel",
        "position": [7, 10],  # x, y - in barracks
        "home": "BARRACKS"
    }
]

# =============================================================================
# BED DEFINITIONS (JSON-serializable)
# =============================================================================
# Beds have: name, position (x, y), home area
# Ownership is assigned at runtime based on jobs
BEDS = [
    {
        "name": "Steward Bed",
        "position": [8, 10],  # x, y - in barracks
        "home": "BARRACKS"
    },
    {
        "name": "Barracks Bed 1",
        "position": [9, 10],  # x, y - in barracks
        "home": "BARRACKS"
    },
    {
        "name": "Barracks Bed 2",
        "position": [10, 10],  # x, y - in barracks
        "home": "BARRACKS"
    },
    {
        "name": "Farm Bed",
        "position": [16, 2],  # x, y - on farm
        "home": "FARM"
    }
]
