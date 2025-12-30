# scenario_world.py - World layout: regions, objects, and structures
# Edit this file to create a new map within the same simulation structure

# =============================================================================
# SCENARIO NAME
# =============================================================================
VILLAGE_NAME = "Poopy"

# =============================================================================
# MAP SIZE
# =============================================================================
SIZE = 20  # Map dimensions (SIZE x SIZE grid)

# =============================================================================
# AREA DEFINITIONS (JSON-serializable)
# =============================================================================
# Each area has: name, bounds (start_y, start_x, end_y, end_x), color, and optional properties
# The "role" field links areas to game mechanics (see AREA_ROLES in constants.py)
AREAS = [
    {
        "name": "Dunmere",
        "role": "village", # a village constitues an allegiance
        "bounds": [6, 6, 12, 12],  # start_y, start_x, end_y, end_x
        "color": "#fffacd",
    },
    {
        "name": "Town Market",
        "allegiance": "Dunmere",
        "role": "market",
        "bounds": [6, 7, 8, 11],
        "color": "#ADD8E6",
    },
    {
        "name": "Dunmere Storehouse",
        "role": "military_housing",
        "bounds": [10, 7, 12, 11],
        "color": "#DEB887",
        "allegiance": "Dunmere"
    },
    {
        "name": "Dunmere Farm",
        "role": "farm",
        "bounds": [2, 15, 19, 20],
        "allegiance": "Dunmere",
        "color": "#90EE90",
        "has_farm_cells": True,
        "farm_cell_bounds": [2, 15, 19, 20],  # y_start, x_start, y_end, x_end for harvestable cells
    },
    {
        "name": "Eagle Rock",
        "role": "encampment",
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
        "home": "Dunmere Farm"
    },
    {
        "name": "Barracks Barrel",
        "position": [7, 10],  # x, y - in barracks
        "home": "Dunmere Storehouse"
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
        "home": "Dunmere Storehouse"
    },
    {
        "name": "Barracks Bed 1",
        "position": [9, 10],  # x, y - in barracks
        "home": "Dunmere Storehouse"
    },
    {
        "name": "Barracks Bed 2",
        "position": [10, 10],  # x, y - in barracks
        "home": "Dunmere Storehouse"
    },
    {
        "name": "Farm Bed",
        "position": [16, 2],  # x, y - on farm
        "home": "Dunmere Farm"
    }
]

# =============================================================================
# STOVE DEFINITIONS (JSON-serializable)
# =============================================================================
# Stoves have: name, position (x, y), home area
# Used to convert wheat into bread
STOVES = [
    {
        "name": "Barracks Stove",
        "position": [10, 11],  # x, y - in barracks
        "home": "Dunmere Storehouse"
    },
    {
        "name": "Farm Stove",
        "position": [19, 2],  # x, y - corner of farm
        "home": "Dunmere Farm"
    }
]
