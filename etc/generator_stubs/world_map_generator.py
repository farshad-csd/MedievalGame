#!/usr/bin/env python3
"""
World Map Generator - Everything is cells
Controls: Mouse wheel to zoom, click+drag to pan
"""

import pygame
import random
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from enum import Enum
import hashlib

def deterministic_hash(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16) & 0x7FFFFFFF

# World dimensions
MAP_WIDTH = 1680
MAP_HEIGHT = 1080
CELL_SIZE = 2  # pixels per cell
CELLS_X = MAP_WIDTH // CELL_SIZE  # 700
CELLS_Y = MAP_HEIGHT // CELL_SIZE  # 450
BIOME_GRID = 20  # original biome grid size
UI_HEIGHT = 40

class Biome(Enum):
    FOREST = "forest"
    PLAINS = "plains"
    SWAMP = "swamp"

class LocationType(Enum):
    KINGDOM = "kingdom"
    VILLAGE = "village"
    ENCAMPMENT = "encampment"
    FARM = "farm"
    INN = "inn"
    HOUSE = "house"
    VILLAGE_HOUSE = "village_house"
    KINGDOM_HOUSE = "kingdom_house"
    CLEARING = "clearing"
    MINE = "mine"
    CAVE = "cave"

@dataclass
class Location:
    x: int  # world coordinates
    y: int
    loc_type: LocationType
    name: str
    kingdom_id: Optional[int] = None
    farms: List['Location'] = field(default_factory=list)
    size: int = 1

@dataclass
class Road:
    points: List[Tuple[int, int]]
    is_main: bool = False

@dataclass
class WaterBody:
    points: List[Tuple[int, int]]
    is_river: bool = True
    width: int = 3

@dataclass
class Bridge:
    x: int
    y: int
    angle: float  # Direction of bridge
    length: int
    is_stone: bool = True  # Stone for main roads, wood for paths

# Color palette
C = {
    'road': (139, 115, 85),
    'road_edge': (100, 77, 53),
    'water': (74, 144, 217),
    'water_shallow': (90, 160, 230),
    'water_deep': (50, 100, 180),
    'swamp_water': (60, 90, 70),
    'swamp_shallow': (75, 105, 80),
    'tree_1': (27, 77, 27),
    'tree_2': (35, 85, 35),
    'tree_3': (45, 90, 39),
    'tree_4': (30, 70, 30),
    'tree_swamp': (35, 60, 35),
    'roof': (165, 75, 45),
    'roof_dark': (130, 55, 30),
    'roof_peak': (145, 65, 38),
    'wall': (190, 165, 130),
    'wall_shadow': (160, 135, 100),
    'door': (80, 50, 25),
    'window': (150, 200, 230),
    'crop_1': (200, 170, 50),
    'crop_2': (180, 160, 60),
    'crop_3': (170, 150, 40),
    'barn': (120, 60, 25),
    'barn_roof': (90, 45, 20),
    'fence': (140, 110, 70),
    'stone': (130, 130, 130),
    'stone_light': (150, 150, 150),
    'stone_dark': (100, 100, 100),
    'clearing': (140, 180, 100),
    'clearing_grass': (120, 165, 90),
    'clearing_dirt': (150, 130, 90),
    'tent': (200, 160, 110),
    'tent_dark': (170, 130, 80),
    'tent_pole': (100, 70, 40),
    'mine_entrance': (20, 20, 20),
    'mine_frame': (110, 70, 35),
    'mine_rock': (80, 80, 80),
    'cave_dark': (10, 10, 10),
    'cave_mouth': (30, 30, 30),
    'cave_rock': (70, 70, 70),
    'castle_wall': (110, 110, 120),
    'castle_top': (90, 90, 100),
    'banner_red': (180, 40, 40),
    'banner_blue': (40, 80, 180),
    'banner_green': (40, 140, 50),
    'path': (160, 140, 100),
    'territory_red': (160, 60, 60),
    'territory_blue': (60, 60, 160),
    'territory_green': (60, 130, 60),
    'rocky': (135, 130, 120),
    'rocky_dark': (110, 105, 95),
    'rocky_light': (160, 155, 145),
    'market_stone': (165, 160, 150),
    'market_stall': (150, 115, 70),
    'awning_red': (175, 65, 55),
    'awning_blue': (65, 95, 155),
    'bridge_stone': (140, 140, 145),
    'bridge_stone_dark': (110, 110, 115),
    'bridge_wood': (120, 85, 50),
    'bridge_wood_dark': (90, 60, 35),
    'bridge_rail': (100, 70, 40),
}


class WorldMapGenerator:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((MAP_WIDTH, MAP_HEIGHT + UI_HEIGHT))
        pygame.display.set_caption("World Map Generator")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 14)
        self.font_small = pygame.font.SysFont('Arial', 11)
        self.font_label = pygame.font.SysFont('Georgia', 10)
        self.font_label_bold = pygame.font.SysFont('Georgia', 12, bold=True)
        
        self.current_seed = None
        self.locations: List[Location] = []
        self.roads: List[Road] = []
        self.water_bodies: List[WaterBody] = []
        self.bridges: List[Bridge] = []
        self.biome_map: Dict[Tuple[int,int], Biome] = {}
        self.elevation_map: Dict[Tuple[int,int], float] = {}  # 0.0 = low, 1.0 = mountain peak
        self.rocky_map: Dict[Tuple[int,int], float] = {}  # 0.0 = not rocky, 1.0 = very rocky
        self.trees: List[Tuple[int, int, int]] = []  # (x, y, size) in world coords
        self.kingdom_territories: Dict[int, set] = {}
        
        # The cell grid - stores RGB or None (use biome)
        self.cells = [[None for _ in range(CELLS_Y)] for _ in range(CELLS_X)]
        
        # View transformation
        self.view_x = 0
        self.view_y = 0
        self.view_scale = 1.0
        self.dragging = False
        self.drag_start = (0, 0)
        self.drag_view_start = (0, 0)
        
        # Pre-rendered surface
        self.map_surface = None
        
        # UI state
        self.seed_text = ""
        self.seed_input_active = False
        self.hovered_location = None
        self.show_territories = False
        
        # Territory overlay surface (rendered separately for toggle)
        self.territory_surface = None
        
        self.biome_colors = {
            Biome.FOREST: (45, 90, 39),
            Biome.PLAINS: (124, 179, 66),
            Biome.SWAMP: (70, 95, 60),
        }
        
        # Mountain tint applied over biomes
        self.mountain_tint = (130, 130, 130)  # Gray overlay for mountains
        
        self.kingdom_names = ["Valdoria", "Thornwall", "Ironpeak"]
        self.village_names = ["Millbrook", "Greenhollow", "Stonebridge", "Willowmere", "Foxden",
            "Ashford", "Bramblewood", "Clearwater", "Dusthaven", "Elmsworth"]
        self.encampment_names = ["Wolf's Rest", "Eagle's Perch", "Bear's Den", "Hawk's Nest",
            "Deer's Meadow", "Fox's Hollow", "Owl's Watch"]
        self.mine_names = ["Ironvein Mine", "Deeprock Quarry", "Goldhollow Mine", "Silverpit Mine",
            "Copperstone Mine", "Gemcutter's Dig", "Shadowore Mine"]
        self.cave_names = ["Darkhollow Cave", "Whisperwind Cavern", "Dragonmaw Cave",
            "Echoing Depths", "Mistshade Grotto", "Serpent's Lair", "Shadow Cavern",
            "Crystal Hollow", "Gloomfang Cave", "Thornback Grotto", "Moonshade Cavern",
            "Frostbite Cave", "Dreadmaw Depths", "Spider's Den", "Howling Cavern",
            "Blackrock Cave", "Wyrm's Hollow", "Shadowed Crypt", "Murkmoss Grotto"]
        
        self.generate_world()

    # ─── COORDINATE CONVERSION ────────────────────────────────────────────────

    def world_to_cell(self, wx, wy):
        return int(wx // CELL_SIZE), int(wy // CELL_SIZE)

    def screen_to_world(self, sx, sy):
        sy -= UI_HEIGHT
        wx = (sx - self.view_x) / self.view_scale
        wy = (sy - self.view_y) / self.view_scale
        return wx, wy

    def world_to_screen(self, wx, wy):
        sx = wx * self.view_scale + self.view_x
        sy = wy * self.view_scale + self.view_y + UI_HEIGHT
        return sx, sy

    # ─── CELL PAINTING ────────────────────────────────────────────────────────

    def set_cell(self, cx, cy, color):
        if 0 <= cx < CELLS_X and 0 <= cy < CELLS_Y:
            self.cells[cx][cy] = color

    def paint_rect(self, cx, cy, width, height, color):
        for dx in range(width):
            for dy in range(height):
                self.set_cell(cx + dx, cy + dy, color)

    def paint_pattern(self, cx, cy, pattern):
        for dy, row in enumerate(pattern):
            for dx, color in enumerate(row):
                if color is not None:
                    self.set_cell(cx + dx, cy + dy, color)

    def paint_circle(self, cx, cy, radius, color):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx*dx + dy*dy <= radius*radius:
                    self.set_cell(cx + dx, cy + dy, color)

    def paint_line(self, x1, y1, x2, y2, width, color):
        cx1, cy1 = self.world_to_cell(x1, y1)
        cx2, cy2 = self.world_to_cell(x2, y2)
        dx = abs(cx2 - cx1)
        dy = abs(cy2 - cy1)
        steps = max(dx, dy, 1)
        for i in range(steps + 1):
            t = i / steps if steps > 0 else 0
            cx = int(cx1 + (cx2 - cx1) * t)
            cy = int(cy1 + (cy2 - cy1) * t)
            self.paint_circle(cx, cy, width // 2, color)

    def paint_thick_path(self, points, width, color, edge_color=None):
        cell_width = max(1, width // CELL_SIZE)
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            if edge_color:
                self.paint_line(x1, y1, x2, y2, width + 2, edge_color)
            self.paint_line(x1, y1, x2, y2, width, color)

    # ─── STRUCTURE PATTERNS ───────────────────────────────────────────────────

    def make_house_pattern(self, width=5, height=6):
        pattern = []
        pattern.append([None] + [C['roof_peak']] * (width - 2) + [None])
        for _ in range(2):
            pattern.append([C['roof_dark']] + [C['roof']] * (width - 2) + [C['roof_dark']])
        for i in range(height - 3):
            row = [C['wall_shadow']] + [C['wall']] * (width - 2) + [C['wall_shadow']]
            if i == height - 5 and width >= 5:
                row[2] = C['window']
                if width >= 6:
                    row[width - 3] = C['window']
            if i == height - 4:
                row[width // 2] = C['door']
            pattern.append(row)
        return pattern

    def make_large_house_pattern(self):
        return self.make_house_pattern(7, 8)

    def make_farm_pattern(self):
        pattern = []
        for i in range(6):
            pattern.append([C['crop_1'] if i % 2 == 0 else C['crop_2']] * 12)
        pattern.append([None] * 12)
        pattern.append([None, None] + [C['barn_roof']] * 5 + [None] * 5)
        pattern.append([None, None] + [C['barn']] * 5 + [None] * 5)
        pattern.append([None, None] + [C['barn'], C['barn'], C['door'], C['barn'], C['barn']] + [None] * 5)
        return pattern

    def make_inn_pattern(self):
        return [
            [None, C['roof_peak'], C['roof_peak'], C['roof_peak'], C['roof_peak'], C['roof_peak'], None],
            [C['roof_dark'], C['roof'], C['roof'], C['roof'], C['roof'], C['roof'], C['roof_dark']],
            [C['roof_dark'], C['roof'], C['roof'], C['roof'], C['roof'], C['roof'], C['roof_dark']],
            [C['wall_shadow'], C['wall'], C['window'], C['wall'], C['window'], C['wall'], C['wall_shadow']],
            [C['wall_shadow'], C['wall'], C['wall'], C['wall'], C['wall'], C['wall'], C['wall_shadow']],
            [C['wall_shadow'], C['wall'], C['wall'], C['door'], C['wall'], C['wall'], C['wall_shadow']],
            [None, None, None, None, None, None, None, C['fence'], C['crop_1']],
        ]

    def make_tent_pattern(self):
        return [
            [None, None, C['tent_pole'], None, None],
            [None, C['tent_dark'], C['tent'], C['tent_dark'], None],
            [C['tent_dark'], C['tent'], C['tent'], C['tent'], C['tent_dark']],
            [C['tent'], C['tent'], C['door'], C['tent'], C['tent']],
        ]

    def make_mine_pattern(self):
        return [
            [None, C['mine_frame'], C['mine_frame'], C['mine_frame'], C['mine_frame'], C['mine_frame'], None],
            [C['mine_frame'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_frame']],
            [C['mine_frame'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_frame']],
            [C['mine_rock'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_rock']],
            [C['mine_rock'], C['mine_rock'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['mine_rock'], C['mine_rock']],
        ]

    def make_cave_pattern(self):
        return [
            [None, None, C['cave_rock'], C['cave_rock'], C['cave_rock'], None, None],
            [None, C['cave_rock'], C['cave_mouth'], C['cave_dark'], C['cave_mouth'], C['cave_rock'], None],
            [C['cave_rock'], C['cave_mouth'], C['cave_dark'], C['cave_dark'], C['cave_dark'], C['cave_mouth'], C['cave_rock']],
            [C['cave_rock'], C['cave_dark'], C['cave_dark'], C['cave_dark'], C['cave_dark'], C['cave_dark'], C['cave_rock']],
            [None, C['cave_rock'], C['cave_dark'], C['cave_dark'], C['cave_dark'], C['cave_rock'], None],
            [None, None, C['cave_rock'], C['cave_rock'], C['cave_rock'], None, None],
        ]

    def make_castle_pattern(self, banner_color):
        bc = banner_color
        return [
            [C['castle_top'], None, C['castle_top'], None, None, None, None, None, C['castle_top'], None, C['castle_top']],
            [C['castle_wall'], C['castle_top'], C['castle_wall'], C['castle_top'], C['castle_top'], C['castle_top'], C['castle_top'], C['castle_top'], C['castle_wall'], C['castle_top'], C['castle_wall']],
            [C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall']],
            [C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], bc, C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall']],
            [C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall'], C['castle_wall']],
            [C['castle_wall'], C['castle_wall'], C['castle_wall'], C['stone_dark'], C['stone_dark'], C['stone_dark'], C['stone_dark'], C['stone_dark'], C['castle_wall'], C['castle_wall'], C['castle_wall']],
            [C['castle_wall'], C['castle_wall'], C['castle_wall'], C['stone_dark'], C['mine_entrance'], C['mine_entrance'], C['mine_entrance'], C['stone_dark'], C['castle_wall'], C['castle_wall'], C['castle_wall']],
        ]

    def make_tree_pattern(self, size, color):
        if size <= 3:
            return [[color]]
        elif size <= 5:
            return [[None, color, None], [color, color, color], [None, color, None]]
        else:
            c2 = (max(0, color[0]-15), max(0, color[1]-15), max(0, color[2]-15))
            return [[None, color, color, None], [color, c2, c2, color], [color, c2, c2, color], [None, color, color, None]]

    # ─── PAINTING STRUCTURES ──────────────────────────────────────────────────

    def paint_clearing(self, loc):
        """Paint a clearing as an irregular grass patch"""
        cx, cy = self.world_to_cell(loc.x, loc.y)
        base_radius = loc.size // CELL_SIZE
        random.seed(loc.x * 1000 + loc.y)  # Deterministic shape
        
        # Generate irregular boundary using noise
        for dx in range(-base_radius - 5, base_radius + 6):
            for dy in range(-base_radius - 5, base_radius + 6):
                dist = math.sqrt(dx*dx + dy*dy)
                # Add noise to make irregular shape
                angle = math.atan2(dy, dx)
                noise = math.sin(angle * 3) * 4 + math.cos(angle * 5) * 3 + random.uniform(-2, 2)
                threshold = base_radius + noise
                
                if dist <= threshold:
                    # Vary the color for natural look - always grass
                    r = random.random()
                    if r < 0.6:
                        color = C['clearing']
                    elif r < 0.85:
                        color = C['clearing_grass']
                    else:
                        color = C['clearing_dirt']
                    self.set_cell(cx + dx, cy + dy, color)

    def paint_road(self, road):
        """Paint road with smooth curves between waypoints"""
        width = 3 if road.is_main else 2  # Thinner roads
        
        if len(road.points) < 2:
            return
        
        # Create smoothed path using Catmull-Rom-like interpolation
        smooth_points = []
        points = road.points
        
        for i in range(len(points) - 1):
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[i + 1]
            p3 = points[min(len(points) - 1, i + 2)]
            
            # Number of interpolation steps based on distance
            dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            steps = max(2, int(dist / 15))
            
            for t in range(steps):
                tt = t / steps
                # Catmull-Rom spline interpolation
                tt2 = tt * tt
                tt3 = tt2 * tt
                
                x = 0.5 * ((2 * p1[0]) +
                          (-p0[0] + p2[0]) * tt +
                          (2*p0[0] - 5*p1[0] + 4*p2[0] - p3[0]) * tt2 +
                          (-p0[0] + 3*p1[0] - 3*p2[0] + p3[0]) * tt3)
                y = 0.5 * ((2 * p1[1]) +
                          (-p0[1] + p2[1]) * tt +
                          (2*p0[1] - 5*p1[1] + 4*p2[1] - p3[1]) * tt2 +
                          (-p0[1] + 3*p1[1] - 3*p2[1] + p3[1]) * tt3)
                
                smooth_points.append((int(x), int(y)))
        
        smooth_points.append(points[-1])
        
        # Paint the smoothed path
        self.paint_thick_path(smooth_points, width, C['road'], C['road_edge'])

    def paint_bridge(self, bridge):
        """Paint a bridge over water"""
        cx, cy = self.world_to_cell(bridge.x, bridge.y)
        half_len = bridge.length // (2 * CELL_SIZE) + 1
        width = 2 if bridge.is_stone else 1
        
        # Determine colors based on bridge type
        if bridge.is_stone:
            main_color = C['bridge_stone']
            edge_color = C['bridge_stone_dark']
            rail_color = C['stone']
        else:
            main_color = C['bridge_wood']
            edge_color = C['bridge_wood_dark']
            rail_color = C['bridge_rail']
        
        # Paint bridge planks/stones along the angle
        cos_a = math.cos(bridge.angle)
        sin_a = math.sin(bridge.angle)
        
        for t in range(-half_len, half_len + 1):
            px = int(cx + cos_a * t)
            py = int(cy + sin_a * t)
            
            # Main bridge surface
            for w in range(-width, width + 1):
                bx = int(px - sin_a * w)
                by = int(py + cos_a * w)
                self.set_cell(bx, by, main_color)
            
            # Edge/rails
            for side in [-1, 1]:
                rx = int(px - sin_a * (width + 1) * side)
                ry = int(py + cos_a * (width + 1) * side)
                self.set_cell(rx, ry, rail_color)
        
        # Add edge shadows
        for t in range(-half_len, half_len + 1):
            px = int(cx + cos_a * t)
            py = int(cy + sin_a * t)
            for side in [-1, 1]:
                ex = int(px - sin_a * width * side)
                ey = int(py + cos_a * width * side)
                if random.random() < 0.3:
                    self.set_cell(ex, ey, edge_color)

    def paint_river(self, wb):
        for i in range(len(wb.points) - 1):
            x1, y1 = wb.points[i]
            x2, y2 = wb.points[i + 1]
            self.paint_line(x1, y1, x2, y2, wb.width + 4, C['water_deep'])
            self.paint_line(x1, y1, x2, y2, wb.width, C['water'])
            self.paint_line(x1, y1, x2, y2, wb.width // 2, C['water_shallow'])

    def paint_pond(self, wb):
        if len(wb.points) < 3:
            return
        min_x, max_x = min(p[0] for p in wb.points), max(p[0] for p in wb.points)
        min_y, max_y = min(p[1] for p in wb.points), max(p[1] for p in wb.points)
        
        # Check if pond center is in swamp
        center_x, center_y = (min_x + max_x) // 2, (min_y + max_y) // 2
        biome = self.biome_map.get((center_x // BIOME_GRID, center_y // BIOME_GRID), Biome.PLAINS)
        is_swamp = biome == Biome.SWAMP
        
        for wy in range(int(min_y), int(max_y) + 1):
            for wx in range(int(min_x), int(max_x) + 1):
                if self.point_in_polygon(wx, wy, wb.points):
                    cx, cy = self.world_to_cell(wx, wy)
                    edge = any(not self.point_in_polygon(wx + dwx, wy + dwy, wb.points) for dwx, dwy in [(-3,0),(3,0),(0,-3),(0,3)])
                    if is_swamp:
                        self.set_cell(cx, cy, C['swamp_shallow'] if edge else C['swamp_water'])
                    else:
                        self.set_cell(cx, cy, C['water_shallow'] if edge else C['water'])

    def paint_tree(self, tx, ty, size):
        cx, cy = self.world_to_cell(tx, ty)
        biome = self.biome_map.get((tx // BIOME_GRID, ty // BIOME_GRID), Biome.PLAINS)
        elevation = self.elevation_map.get((tx // BIOME_GRID, ty // BIOME_GRID), 0.0)
        
        if biome == Biome.SWAMP:
            colors = [C['tree_swamp'], (40, 65, 40), (45, 70, 45)]
        elif elevation > 0.4:
            # Mountain trees - darker, more muted
            colors = [(35, 60, 35), (40, 55, 40), (30, 50, 30)]
        else:
            colors = [C['tree_1'], C['tree_2'], C['tree_3'], C['tree_4']]
        
        color = colors[(tx + ty) % len(colors)]
        pattern = self.make_tree_pattern(size, color)
        offset = len(pattern) // 2
        self.paint_pattern(cx - offset, cy - offset, pattern)

    def paint_house(self, loc):
        cx, cy = self.world_to_cell(loc.x, loc.y)
        self.paint_pattern(cx - 2, cy - 3, self.make_house_pattern())

    def paint_farm(self, loc):
        cx, cy = self.world_to_cell(loc.x, loc.y)
        self.paint_pattern(cx - 6, cy - 5, self.make_farm_pattern())

    def paint_inn(self, loc):
        cx, cy = self.world_to_cell(loc.x, loc.y)
        self.paint_pattern(cx - 3, cy - 4, self.make_inn_pattern())

    def paint_mine(self, loc):
        cx, cy = self.world_to_cell(loc.x, loc.y)
        self.paint_pattern(cx - 3, cy - 2, self.make_mine_pattern())

    def paint_cave(self, loc):
        cx, cy = self.world_to_cell(loc.x, loc.y)
        self.paint_pattern(cx - 3, cy - 3, self.make_cave_pattern())

    def paint_tent(self, cx, cy):
        self.paint_pattern(cx - 2, cy - 2, self.make_tent_pattern())

    def paint_encampment(self, loc):
        cx, cy = self.world_to_cell(loc.x, loc.y)
        self.paint_tent(cx, cy)
        random.seed(loc.x + loc.y)
        for dx, dy in [(8, 2), (-7, 3), (3, -6), (-5, -5)][:random.randint(2, 4)]:
            self.paint_tent(cx + dx, cy + dy)

    def paint_village(self, loc):
        """Paint village with organic streets and market area"""
        cx, cy = self.world_to_cell(loc.x, loc.y)
        
        # Get layout info
        layout = getattr(loc, 'layout', {'main_angle': 0, 'street_offset': 18})
        main_angle = layout.get('main_angle', 0)
        has_market = layout.get('has_market', True)
        
        # Find all houses belonging to this village
        village_houses = [l for l in self.locations 
                        if l.loc_type == LocationType.VILLAGE_HOUSE and l.name.startswith(loc.name)]
        
        if not village_houses:
            return
        
        # Paint market/town square area at village center
        if has_market:
            market_size = random.randint(4, 6)
            for dx in range(-market_size, market_size + 1):
                for dy in range(-market_size, market_size + 1):
                    if abs(dx) + abs(dy) <= market_size + 1:
                        self.set_cell(cx + dx, cy + dy, C['market_stone'])
            # Add a few market stall markers
            for _ in range(2):
                sx, sy = cx + random.randint(-2, 2), cy + random.randint(-2, 2)
                self.set_cell(sx, sy, C['market_stall'])
                self.set_cell(sx, sy - 1, random.choice([C['awning_red'], C['awning_blue']]))
        
        # Paint main street through village
        perpendicular = main_angle + math.pi / 2
        street_length = 12
        for t in range(-street_length, street_length + 1):
            px = int(cx + math.cos(main_angle) * t)
            py = int(cy + math.sin(main_angle) * t)
            self.set_cell(px, py, C['path'])
            self.set_cell(px + 1, py, C['path'])
        
        # Paint paths from each house to main street/market
        for house in village_houses:
            hcx, hcy = self.world_to_cell(house.x, house.y)
            self._paint_path_between(hcx, hcy, cx, cy)
        
        # Paint paths to farms
        for farm in loc.farms:
            fcx, fcy = self.world_to_cell(farm.x, farm.y)
            self._paint_path_between(fcx, fcy, cx, cy)
    
    def paint_village_house(self, loc):
        """Paint a village house"""
        cx, cy = self.world_to_cell(loc.x, loc.y)
        is_large = loc.size >= 8
        if is_large:
            self.paint_pattern(cx - 3, cy - 4, self.make_large_house_pattern())
        else:
            self.paint_pattern(cx - 2, cy - 3, self.make_house_pattern())
    
    def paint_kingdom_house(self, loc):
        """Paint a kingdom house"""
        cx, cy = self.world_to_cell(loc.x, loc.y)
        is_large = loc.size >= 10
        if is_large:
            self.paint_pattern(cx - 3, cy - 4, self.make_large_house_pattern())
        else:
            self.paint_pattern(cx - 2, cy - 3, self.make_house_pattern())
    
    def _paint_path_between(self, x1, y1, x2, y2):
        """Paint a thin path between two cell positions with slight curve"""
        dx = x2 - x1
        dy = y2 - y1
        dist = max(abs(dx), abs(dy), 1)
        
        # Add a slight curve via midpoint offset (deterministic based on endpoints)
        curve_seed = (x1 * 31 + y1 * 17 + x2 * 13 + y2 * 7) % 5 - 2
        mid_x = (x1 + x2) // 2 + curve_seed
        mid_y = (y1 + y2) // 2 + ((x1 + y1) % 5 - 2)
        
        # Draw first half
        steps1 = max(abs(mid_x - x1), abs(mid_y - y1), 1)
        for t in range(steps1 + 1):
            px = int(x1 + (mid_x - x1) * t / steps1)
            py = int(y1 + (mid_y - y1) * t / steps1)
            self.set_cell(px, py, C['path'])
        
        # Draw second half
        steps2 = max(abs(x2 - mid_x), abs(y2 - mid_y), 1)
        for t in range(steps2 + 1):
            px = int(mid_x + (x2 - mid_x) * t / steps2)
            py = int(mid_y + (y2 - mid_y) * t / steps2)
            self.set_cell(px, py, C['path'])
    
    def _connect_to_nearest_road(self, loc):
        """Paint a path from a location to the nearest road"""
        cx, cy = self.world_to_cell(loc.x, loc.y)
        
        # Find nearest point on any road
        min_dist = float('inf')
        nearest_point = None
        
        for road in self.roads:
            for i in range(len(road.points) - 1):
                p1, p2 = road.points[i], road.points[i + 1]
                # Find closest point on this segment
                px, py = self._closest_point_on_segment(loc.x, loc.y, p1[0], p1[1], p2[0], p2[1])
                dist = math.sqrt((loc.x - px)**2 + (loc.y - py)**2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_point = (px, py)
        
        # Only connect if road is reasonably close
        if nearest_point and min_dist < 150:
            rcx, rcy = self.world_to_cell(nearest_point[0], nearest_point[1])
            self._paint_path_between(cx, cy, rcx, rcy)
    
    def _closest_point_on_segment(self, px, py, x1, y1, x2, y2):
        """Find closest point on line segment to given point"""
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return x1, y1
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return x1 + t * dx, y1 + t * dy

    def paint_kingdom(self, loc):
        """Paint kingdom with courtyard and market area"""
        cx, cy = self.world_to_cell(loc.x, loc.y)
        banners = [C['banner_red'], C['banner_blue'], C['banner_green']]
        banner = banners[loc.kingdom_id % 3] if loc.kingdom_id is not None else C['banner_red']
        
        # Get layout info
        layout = getattr(loc, 'layout', {'inner_ring': 35, 'has_courtyard': True})
        has_courtyard = layout.get('has_courtyard', True)
        has_market = layout.get('has_market', True)
        
        # Find all houses belonging to this kingdom
        kingdom_houses = [l for l in self.locations 
                        if l.loc_type == LocationType.KINGDOM_HOUSE and l.name.startswith(loc.name)]
        
        # Paint courtyard area in front of castle (south side)
        if has_courtyard:
            courtyard_size = 8
            for dx in range(-courtyard_size, courtyard_size + 1):
                for dy in range(2, courtyard_size + 4):  # Below castle
                    dist = abs(dx) * 0.7 + abs(dy - 5) * 0.5
                    if dist <= courtyard_size:
                        self.set_cell(cx + dx, cy + dy, C['market_stone'])
        
        # Paint market stalls on one side of courtyard
        if has_market:
            market_side = random.choice([-1, 1])
            for i in range(3):
                mx = cx + market_side * (4 + i)
                my = cy + 5 + i
                self.set_cell(mx, my, C['market_stall'])
                self.set_cell(mx, my - 1, random.choice([C['awning_red'], C['awning_blue']]))
        
        # Paint castle on top
        self.paint_pattern(cx - 5, cy - 6, self.make_castle_pattern(banner))
        
        # Paint paths from houses to courtyard
        for house in kingdom_houses:
            hcx, hcy = self.world_to_cell(house.x, house.y)
            # Connect to courtyard center
            self._paint_path_between(hcx, hcy, cx, cy + 5)
        
        # Paint paths to farms
        for farm in loc.farms:
            fcx, fcy = self.world_to_cell(farm.x, farm.y)
            # Find nearest house or courtyard
            best_target = (cx, cy + 5)
            best_dist = math.sqrt((fcx - cx)**2 + (fcy - cy - 5)**2)
            for house in kingdom_houses:
                hcx, hcy = self.world_to_cell(house.x, house.y)
                d = math.sqrt((fcx - hcx)**2 + (fcy - hcy)**2)
                if d < best_dist:
                    best_dist = d
                    best_target = (hcx, hcy)
            self._paint_path_between(fcx, fcy, best_target[0], best_target[1])

    def paint_territory_tint(self):
        """Create a separate territory overlay surface for toggling"""
        self.territory_surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
        territory_colors = {
            0: (160, 60, 60, 80),    # Red with alpha
            1: (60, 60, 160, 80),    # Blue with alpha
            2: (60, 130, 60, 80)     # Green with alpha
        }
        cells_per = BIOME_GRID // CELL_SIZE
        for kid, territory in self.kingdom_territories.items():
            tint = territory_colors.get(kid, (160, 60, 60, 80))
            for gx, gy in territory:
                # Draw a rectangle for each territory cell
                rect_x = gx * BIOME_GRID
                rect_y = gy * BIOME_GRID
                pygame.draw.rect(self.territory_surface, tint, 
                               (rect_x, rect_y, BIOME_GRID, BIOME_GRID))

    # ─── GENERATION ───────────────────────────────────────────────────────────

    def generate_world(self):
        self.current_seed = random.randint(0, 2**31 - 1)
        self.seed_text = str(self.current_seed)
        random.seed(self.current_seed)
        self._generate_world_internal()

    def generate_with_seed(self):
        if self.seed_text.strip():
            try:
                seed = int(self.seed_text.strip())
            except ValueError:
                seed = deterministic_hash(self.seed_text.strip())
            self.current_seed = seed
            self.seed_text = str(seed)
            random.seed(seed)
            self._generate_world_internal()
        else:
            self.generate_world()

    def _generate_world_internal(self):
        self.locations.clear()
        self.roads.clear()
        self.water_bodies.clear()
        self.bridges.clear()
        self.trees.clear()
        self.biome_map.clear()
        self.elevation_map.clear()
        self.rocky_map.clear()
        self.kingdom_territories.clear()
        self.cells = [[None for _ in range(CELLS_Y)] for _ in range(CELLS_X)]
        self.map_surface = None
        self.territory_surface = None
        self.view_x, self.view_y, self.view_scale = 0, 0, 1.0
        random.seed(self.current_seed)
        
        self.generate_biomes()
        self.generate_elevation()
        self.generate_water()
        self.generate_kingdoms()
        self.generate_villages()
        self.generate_mines_and_caves()
        self.generate_roads()
        self.generate_bridges()  # After roads and water
        self.generate_encampments()  # After roads so they can avoid them
        self.generate_clearings()  # After roads so we can check distance
        self.generate_inns_and_houses()
        self.generate_trees()
        self.paint_all_cells()
        self.render_map_surface()

    def paint_all_cells(self):
        self.paint_biomes()
        # Territory overlay is now separate - created after biomes
        self.paint_territory_tint()
        for loc in self.locations:
            if loc.loc_type == LocationType.CLEARING:
                self.paint_clearing(loc)
        for road in self.roads:
            self.paint_road(road)
        for wb in self.water_bodies:
            (self.paint_river if wb.is_river else self.paint_pond)(wb)
        
        # Paint bridges over water
        for bridge in self.bridges:
            self.paint_bridge(bridge)
        
        # Paint all paths BEFORE structures
        # Connect off-grid houses and inns to roads
        for loc in self.locations:
            if loc.loc_type in [LocationType.HOUSE, LocationType.INN]:
                self._connect_to_nearest_road(loc)
        
        # Connect houses to their farms
        for loc in self.locations:
            if loc.loc_type == LocationType.HOUSE and loc.farms:
                cx, cy = self.world_to_cell(loc.x, loc.y)
                for farm in loc.farms:
                    fcx, fcy = self.world_to_cell(farm.x, farm.y)
                    self._paint_path_between(cx, cy, fcx, fcy)
        
        for tx, ty, size in self.trees:
            self.paint_tree(tx, ty, size)
        for lt in [LocationType.FARM, LocationType.HOUSE, LocationType.VILLAGE_HOUSE, LocationType.KINGDOM_HOUSE, LocationType.INN, LocationType.MINE, LocationType.CAVE, LocationType.ENCAMPMENT, LocationType.VILLAGE, LocationType.KINGDOM]:
            for loc in self.locations:
                if loc.loc_type == lt:
                    getattr(self, f'paint_{lt.value}')(loc)

    def paint_biomes(self):
        cells_per = BIOME_GRID // CELL_SIZE
        
        for (gx, gy), biome in self.biome_map.items():
            base = self.biome_colors[biome]
            elevation = self.elevation_map.get((gx, gy), 0.0)
            rockiness = self.rocky_map.get((gx, gy), 0.0)
            
            # Use distinct rocky floor for high rockiness
            if rockiness > 0.35:
                # Rocky terrain - use rocky colors
                rocky_strength = min(1.0, (rockiness - 0.35) * 2)
                rocky_base = C['rocky']
                base = (
                    int(base[0] * (1 - rocky_strength) + rocky_base[0] * rocky_strength),
                    int(base[1] * (1 - rocky_strength) + rocky_base[1] * rocky_strength),
                    int(base[2] * (1 - rocky_strength) + rocky_base[2] * rocky_strength),
                )
            
            # Apply mountain tint on top for high elevation
            if elevation > 0.3:
                tint_strength = min(0.6, (elevation - 0.3) * 1.0)
                mt = self.mountain_tint
                base = (
                    int(base[0] * (1 - tint_strength) + mt[0] * tint_strength),
                    int(base[1] * (1 - tint_strength) + mt[1] * tint_strength),
                    int(base[2] * (1 - tint_strength) + mt[2] * tint_strength),
                )
            
            neighbors = {(dx, dy): self.biome_colors[self.biome_map[(gx+dx, gy+dy)]]
                        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)] if (gx+dx, gy+dy) in self.biome_map and self.biome_map[(gx+dx, gy+dy)] != biome}
            for sub_x in range(cells_per):
                for sub_y in range(cells_per):
                    r, g, b = base
                    for (dx, dy), nc in neighbors.items():
                        blend = 3
                        if (dx == -1 and sub_x < blend) or (dx == 1 and sub_x >= cells_per - blend) or \
                           (dy == -1 and sub_y < blend) or (dy == 1 and sub_y >= cells_per - blend):
                            t = 0.5 * ((blend - sub_x if dx == -1 else sub_x - cells_per + blend + 1 if dx == 1 else blend - sub_y if dy == -1 else sub_y - cells_per + blend + 1) / blend)
                            r, g, b = int(r*(1-t)+nc[0]*t), int(g*(1-t)+nc[1]*t), int(b*(1-t)+nc[2]*t)
                    noise = random.randint(-12, 12)
                    # Add extra noise variation for mountainous or rocky areas
                    if elevation > 0.3 or rockiness > 0.35:
                        noise += random.randint(-12, 12)
                        # Add rocky texture with light/dark variation
                        if random.random() < 0.15:
                            rocky_var = random.choice([C['rocky_dark'], C['rocky_light']])
                            r = int(r * 0.7 + rocky_var[0] * 0.3)
                            g = int(g * 0.7 + rocky_var[1] * 0.3)
                            b = int(b * 0.7 + rocky_var[2] * 0.3)
                    self.set_cell(gx * cells_per + sub_x, gy * cells_per + sub_y,
                        (max(0,min(255,r+noise)), max(0,min(255,g+noise+random.randint(-4,4))), max(0,min(255,b+noise+random.randint(-4,4)))))

    def generate_biomes(self):
        # =========================================================================
        # FOREST IS KEY - MUST BE AT LEAST 40% OF THE MAP
        # Other biomes (plains, swamp) are present but secondary
        # =========================================================================
        
        # Generate initial biome seeds with forest priority
        seeds = []
        for _ in range(random.randint(18, 28)):
            x, y = random.randint(0, MAP_WIDTH), random.randint(0, MAP_HEIGHT)
            r = random.random()
            if r < 0.55:  # 55% chance forest seed
                biome = Biome.FOREST
            elif r < 0.88:  # 33% chance plains seed
                biome = Biome.PLAINS
            else:  # 12% chance swamp seed
                biome = Biome.SWAMP
            seeds.append((x, y, biome))
        
        # Assign biomes based on nearest seed
        for gx in range(0, MAP_WIDTH, BIOME_GRID):
            for gy in range(0, MAP_HEIGHT, BIOME_GRID):
                self.biome_map[(gx // BIOME_GRID, gy // BIOME_GRID)] = min(seeds, key=lambda s: math.sqrt((gx-s[0])**2+(gy-s[1])**2)+random.uniform(-30,30))[2]
        
        # Count forest coverage
        total_cells = len(self.biome_map)
        forest_cells = sum(1 for b in self.biome_map.values() if b == Biome.FOREST)
        forest_percent = forest_cells / total_cells if total_cells > 0 else 0
        
        # If forest is below 40%, convert some plains/swamp to forest
        if forest_percent < 0.40:
            target_forest = int(total_cells * 0.42)  # Aim for 42% to have buffer
            cells_to_convert = target_forest - forest_cells
            
            # Find non-forest cells adjacent to forest (natural expansion)
            non_forest = [(k, v) for k, v in self.biome_map.items() if v != Biome.FOREST]
            random.shuffle(non_forest)
            
            converted = 0
            for (gx, gy), biome in non_forest:
                if converted >= cells_to_convert:
                    break
                # Check if adjacent to forest
                adjacent_forest = any(
                    self.biome_map.get((gx + dx, gy + dy)) == Biome.FOREST
                    for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]
                )
                if adjacent_forest or random.random() < 0.3:  # Convert adjacent or 30% random
                    self.biome_map[(gx, gy)] = Biome.FOREST
                    converted += 1
    
    def generate_elevation(self):
        """Generate elevation map - mountains as long range streaks"""
        # Create mountain RANGES as lines/curves across the map
        mountain_ranges = []
        for _ in range(random.randint(2, 4)):
            # Start point
            x1, y1 = random.randint(0, MAP_WIDTH), random.randint(0, MAP_HEIGHT)
            # Direction and length
            angle = random.uniform(0, 2 * math.pi)
            length = random.randint(300, 600)
            x2 = x1 + int(math.cos(angle) * length)
            y2 = y1 + int(math.sin(angle) * length)
            width = random.uniform(80, 150)  # Width of the mountain range
            mountain_ranges.append((x1, y1, x2, y2, width))
        
        # Create rocky STREAKS as thinner lines
        rocky_streaks = []
        for _ in range(random.randint(4, 8)):
            x1, y1 = random.randint(0, MAP_WIDTH), random.randint(0, MAP_HEIGHT)
            angle = random.uniform(0, 2 * math.pi)
            length = random.randint(150, 400)
            x2 = x1 + int(math.cos(angle) * length)
            y2 = y1 + int(math.sin(angle) * length)
            width = random.uniform(40, 90)
            rocky_streaks.append((x1, y1, x2, y2, width))
        
        def dist_to_line(px, py, x1, y1, x2, y2):
            """Distance from point to line segment"""
            dx, dy = x2 - x1, y2 - y1
            if dx == 0 and dy == 0:
                return math.sqrt((px - x1)**2 + (py - y1)**2)
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy
            return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)
        
        # Generate elevation and rockiness for each grid cell
        for gx in range(MAP_WIDTH // BIOME_GRID):
            for gy in range(MAP_HEIGHT // BIOME_GRID):
                wx, wy = gx * BIOME_GRID + BIOME_GRID // 2, gy * BIOME_GRID + BIOME_GRID // 2
                
                # Swamps are always low elevation, not rocky
                biome = self.biome_map.get((gx, gy), Biome.PLAINS)
                if biome == Biome.SWAMP:
                    self.elevation_map[(gx, gy)] = 0.0
                    self.rocky_map[(gx, gy)] = 0.0
                    continue
                
                # Calculate elevation based on distance to mountain ranges
                max_elevation = 0.0
                for x1, y1, x2, y2, width in mountain_ranges:
                    dist = dist_to_line(wx, wy, x1, y1, x2, y2)
                    if dist < width:
                        elevation = 1.0 - (dist / width)
                        elevation = elevation ** 0.6  # Make ridges sharper
                        max_elevation = max(max_elevation, elevation)
                
                self.elevation_map[(gx, gy)] = max_elevation
                
                # Calculate rockiness - from rocky streaks AND from mountains
                max_rocky = 0.0
                # Mountains are also rocky
                if max_elevation > 0.25:
                    max_rocky = max_elevation * 0.9
                
                # Rocky streaks
                for x1, y1, x2, y2, width in rocky_streaks:
                    dist = dist_to_line(wx, wy, x1, y1, x2, y2)
                    if dist < width:
                        rocky = (1.0 - (dist / width)) * 0.7
                        max_rocky = max(max_rocky, rocky)
                
                self.rocky_map[(gx, gy)] = max_rocky
    
    def is_mountainous(self, x, y, threshold=0.4):
        """Check if a position is mountainous (high elevation)"""
        gx, gy = x // BIOME_GRID, y // BIOME_GRID
        return self.elevation_map.get((gx, gy), 0.0) >= threshold
    
    def is_rocky(self, x, y, threshold=0.3):
        """Check if a position is rocky"""
        gx, gy = x // BIOME_GRID, y // BIOME_GRID
        return self.rocky_map.get((gx, gy), 0.0) >= threshold

    def generate_water(self):
        # Main rivers
        for _ in range(random.randint(2, 4)):
            edge = random.choice(['top', 'left', 'bottom', 'right'])
            x, y = (random.randint(100, MAP_WIDTH-100), 0) if edge == 'top' else (random.randint(100, MAP_WIDTH-100), MAP_HEIGHT) if edge == 'bottom' else (0, random.randint(100, MAP_HEIGHT-100)) if edge == 'left' else (MAP_WIDTH, random.randint(100, MAP_HEIGHT-100))
            points, d = [(x, y)], random.uniform(0, 2*math.pi)
            for _ in range(random.randint(15, 30)):
                d += random.uniform(-0.5, 0.5)
                x, y = max(-50, min(MAP_WIDTH+50, x+int(math.cos(d)*random.randint(40,80)))), max(-50, min(MAP_HEIGHT+50, y+int(math.sin(d)*random.randint(40,80))))
                points.append((x, y))
                if x < -50 or x > MAP_WIDTH+50 or y < -50 or y > MAP_HEIGHT+50: break
            self.water_bodies.append(WaterBody(points, True, random.randint(8, 15)))
        
        # Streams (thinner rivers)
        for _ in range(random.randint(4, 8)):
            # Start from random point or edge
            if random.random() < 0.5:
                edge = random.choice(['top', 'left', 'bottom', 'right'])
                x, y = (random.randint(50, MAP_WIDTH-50), 0) if edge == 'top' else (random.randint(50, MAP_WIDTH-50), MAP_HEIGHT) if edge == 'bottom' else (0, random.randint(50, MAP_HEIGHT-50)) if edge == 'left' else (MAP_WIDTH, random.randint(50, MAP_HEIGHT-50))
            else:
                x, y = random.randint(100, MAP_WIDTH-100), random.randint(100, MAP_HEIGHT-100)
            
            points, d = [(x, y)], random.uniform(0, 2*math.pi)
            for _ in range(random.randint(8, 20)):
                d += random.uniform(-0.6, 0.6)
                x, y = max(-20, min(MAP_WIDTH+20, x+int(math.cos(d)*random.randint(25,50)))), max(-20, min(MAP_HEIGHT+20, y+int(math.sin(d)*random.randint(25,50))))
                points.append((x, y))
                if x < -20 or x > MAP_WIDTH+20 or y < -20 or y > MAP_HEIGHT+20: break
            self.water_bodies.append(WaterBody(points, True, random.randint(3, 6)))  # Thinner
        
        # Regular ponds
        for _ in range(random.randint(3, 6)):
            cx, cy, r, n = random.randint(100, MAP_WIDTH-100), random.randint(100, MAP_HEIGHT-100), random.randint(30, 70), random.randint(8, 12)
            pts = [(cx+int(math.cos(2*math.pi*i/n)*(r+random.randint(-15,15))), cy+int(math.sin(2*math.pi*i/n)*(r+random.randint(-15,15)))) for i in range(n)]
            self.water_bodies.append(WaterBody(pts + [pts[0]], False, 0))
        
        # Swamp pools - find swamp areas and add small pools
        swamp_cells = [(gx, gy) for (gx, gy), biome in self.biome_map.items() if biome == Biome.SWAMP]
        num_swamp_pools = min(len(swamp_cells) // 3, random.randint(5, 12))
        for _ in range(num_swamp_pools):
            if not swamp_cells:
                break
            gx, gy = random.choice(swamp_cells)
            cx = gx * BIOME_GRID + random.randint(0, BIOME_GRID)
            cy = gy * BIOME_GRID + random.randint(0, BIOME_GRID)
            r = random.randint(15, 40)
            n = random.randint(6, 10)
            pts = [(cx+int(math.cos(2*math.pi*i/n)*(r+random.randint(-8,8))), cy+int(math.sin(2*math.pi*i/n)*(r+random.randint(-8,8)))) for i in range(n)]
            self.water_bodies.append(WaterBody(pts + [pts[0]], False, 0))

    def generate_kingdoms(self):
        # =========================================================================
        # KINGDOMS MUST BE WELL SPREAD APART - minimum 450 pixels between them
        # Villages will buffer the space between kingdoms
        # =========================================================================
        regions = []
        
        # Generate 3 random kingdom positions with LARGE spacing
        for _ in range(3):
            for attempt in range(100):
                x = random.randint(int(MAP_WIDTH * 0.12), int(MAP_WIDTH * 0.88))
                y = random.randint(int(MAP_HEIGHT * 0.12), int(MAP_HEIGHT * 0.88))
                
                # Kingdoms must be FAR apart - at least 450 pixels
                if all(math.sqrt((x - rx)**2 + (y - ry)**2) >= 450 for rx, ry in regions):
                    regions.append((x, y))
                    break
        
        # Fallback if we couldn't place 3 kingdoms
        while len(regions) < 3:
            x = random.randint(150, MAP_WIDTH - 150)
            y = random.randint(150, MAP_HEIGHT - 150)
            if all(math.sqrt((x - rx)**2 + (y - ry)**2) >= 350 for rx, ry in regions):
                regions.append((x, y))
        
        for i, (rx, ry) in enumerate(regions):
            # Find valid position not in water, mountains, or swamp
            x, y = int(rx + random.randint(-80, 80)), int(ry + random.randint(-80, 80))
            for _ in range(50):
                biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
                if not self.is_in_water(x, y) and biome != Biome.SWAMP and not self.is_mountainous(x, y):
                    break
                x, y = int(rx + random.randint(-150, 150)), int(ry + random.randint(-120, 120))
            
            k = Location(x, y, LocationType.KINGDOM, self.kingdom_names[i], i, size=40)
            self.locations.append(k)
            
            # =========================================================================
            # IMPORTANT: EVERY KINGDOM MUST HAVE AT LEAST 15 HOUSES (excluding castle, courtyard, farms)
            # DO NOT CHANGE THIS - MINIMUM 15 HOUSES PER KINGDOM
            # =========================================================================
            min_houses = 15
            target_houses = random.randint(15, 18)
            
            # Tighter spacing
            inner_ring = random.randint(32, 42)  # Distance for inner houses
            outer_ring = random.randint(55, 75)  # Distance for outer houses
            third_ring = random.randint(80, 100)  # Third ring for more houses
            
            # Place houses in rings around castle - GUARANTEE placement
            houses_placed = 0
            
            # Inner ring - 5-6 houses forming courtyard
            for j in range(6):
                if houses_placed >= target_houses:
                    break
                placed = False
                for attempt in range(100):
                    angle = (2 * math.pi * j / 6) + random.uniform(-0.4, 0.4)
                    dist = inner_ring + random.randint(-5, 8)
                    hx = x + int(math.cos(angle) * dist)
                    hy = y + int(math.sin(angle) * dist) + 8
                    
                    if self.is_in_water(hx, hy):
                        continue
                    biome = self.biome_map.get((hx // BIOME_GRID, hy // BIOME_GRID), Biome.PLAINS)
                    if biome == Biome.SWAMP:
                        continue
                    if not all(math.sqrt((hx-l.x)**2+(hy-l.y)**2) >= 16 for l in self.locations):
                        continue
                    
                    house = Location(hx, hy, LocationType.KINGDOM_HOUSE, f"{k.name} House", i, size=10)
                    self.locations.append(house)
                    houses_placed += 1
                    placed = True
                    break
                
                # Force place if needed
                if not placed:
                    angle = (2 * math.pi * j / 6)
                    hx = x + int(math.cos(angle) * inner_ring)
                    hy = y + int(math.sin(angle) * inner_ring) + 8
                    house = Location(hx, hy, LocationType.KINGDOM_HOUSE, f"{k.name} House", i, size=10)
                    self.locations.append(house)
                    houses_placed += 1
            
            # Outer ring - 6-8 houses
            for j in range(8):
                if houses_placed >= target_houses:
                    break
                placed = False
                for attempt in range(100):
                    angle = (2 * math.pi * j / 8) + random.uniform(-0.4, 0.4)
                    dist = outer_ring + random.randint(-8, 12)
                    hx = x + int(math.cos(angle) * dist)
                    hy = y + int(math.sin(angle) * dist)
                    
                    if self.is_in_water(hx, hy):
                        continue
                    biome = self.biome_map.get((hx // BIOME_GRID, hy // BIOME_GRID), Biome.PLAINS)
                    if biome == Biome.SWAMP:
                        continue
                    if not all(math.sqrt((hx-l.x)**2+(hy-l.y)**2) >= 16 for l in self.locations):
                        continue
                    
                    house = Location(hx, hy, LocationType.KINGDOM_HOUSE, f"{k.name} House", i, size=8)
                    self.locations.append(house)
                    houses_placed += 1
                    placed = True
                    break
                
                if not placed:
                    angle = (2 * math.pi * j / 8)
                    hx = x + int(math.cos(angle) * outer_ring)
                    hy = y + int(math.sin(angle) * outer_ring)
                    house = Location(hx, hy, LocationType.KINGDOM_HOUSE, f"{k.name} House", i, size=8)
                    self.locations.append(house)
                    houses_placed += 1
            
            # Third ring if we need more houses to reach minimum
            while houses_placed < min_houses:
                placed = False
                for attempt in range(100):
                    angle = random.uniform(0, 2 * math.pi)
                    dist = third_ring + random.randint(-10, 20)
                    hx = x + int(math.cos(angle) * dist)
                    hy = y + int(math.sin(angle) * dist)
                    
                    if self.is_in_water(hx, hy):
                        continue
                    biome = self.biome_map.get((hx // BIOME_GRID, hy // BIOME_GRID), Biome.PLAINS)
                    if biome == Biome.SWAMP:
                        continue
                    if not all(math.sqrt((hx-l.x)**2+(hy-l.y)**2) >= 16 for l in self.locations):
                        continue
                    
                    house = Location(hx, hy, LocationType.KINGDOM_HOUSE, f"{k.name} House", i, size=8)
                    self.locations.append(house)
                    houses_placed += 1
                    placed = True
                    break
                
                if not placed:
                    # Force place
                    angle = random.uniform(0, 2 * math.pi)
                    hx = x + int(math.cos(angle) * third_ring)
                    hy = y + int(math.sin(angle) * third_ring)
                    house = Location(hx, hy, LocationType.KINGDOM_HOUSE, f"{k.name} House", i, size=8)
                    self.locations.append(house)
                    houses_placed += 1
            
            # Store layout info - has courtyard
            k.layout = {'inner_ring': inner_ring, 'outer_ring': outer_ring, 'has_courtyard': True, 'has_market': True}
            
            # =========================================================================
            # IMPORTANT: EVERY KINGDOM MUST HAVE EXACTLY 5 FARMS IN CLOSE PROXIMITY
            # DO NOT CHANGE THIS - 5 FARMS PER KINGDOM, CLOSE TO THE KINGDOM
            # =========================================================================
            farms_placed = 0
            for farm_idx in range(5):  # We WILL place 5 farms
                placed = False
                for attempt in range(200):  # 200 attempts per farm
                    # Vary the angle on EVERY attempt, not just successful ones
                    angle = (2 * math.pi * farm_idx) / 5 + random.uniform(-0.8, 0.8)
                    d = random.randint(45, 85)  # Wider range for placement
                    fx = x + int(math.cos(angle) * d)
                    fy = y + int(math.sin(angle) * d)
                    fx = max(30, min(MAP_WIDTH - 30, fx))
                    fy = max(30, min(MAP_HEIGHT - 30, fy))
                    
                    # Skip water check - farms can't be in water
                    if self.is_in_water(fx, fy):
                        continue
                    
                    biome = self.biome_map.get((fx // BIOME_GRID, fy // BIOME_GRID), Biome.PLAINS)
                    if biome == Biome.SWAMP:
                        continue
                    
                    # Relax mountain/rocky check after many attempts
                    if attempt < 100:
                        if self.is_mountainous(fx, fy) or self.is_rocky(fx, fy):
                            continue
                    
                    # Check no overlap with existing locations
                    if all(math.sqrt((fx-l.x)**2+(fy-l.y)**2) >= 18 for l in self.locations):
                        f = Location(fx, fy, LocationType.FARM, f"{k.name} Farm {farm_idx+1}", i, size=15)
                        k.farms.append(f)
                        self.locations.append(f)
                        farms_placed += 1
                        placed = True
                        break
                
                # If still not placed after 200 attempts, force place it
                if not placed:
                    angle = (2 * math.pi * farm_idx) / 5
                    d = 60
                    fx = x + int(math.cos(angle) * d)
                    fy = y + int(math.sin(angle) * d)
                    fx = max(30, min(MAP_WIDTH - 30, fx))
                    fy = max(30, min(MAP_HEIGHT - 30, fy))
                    f = Location(fx, fy, LocationType.FARM, f"{k.name} Farm {farm_idx+1}", i, size=15)
                    k.farms.append(f)
                    self.locations.append(f)
                    farms_placed += 1
            
            self.generate_territory(k, i)

    def generate_territory(self, kingdom, kid):
        territory, frontier = {(kingdom.x // BIOME_GRID, kingdom.y // BIOME_GRID)}, [(kingdom.x // BIOME_GRID, kingdom.y // BIOME_GRID)]
        target = int((MAP_WIDTH // BIOME_GRID) * (MAP_HEIGHT // BIOME_GRID) * 0.18)
        while len(territory) < target and frontier:
            gx, gy = frontier.pop(random.randint(0, len(frontier)-1))
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,1),(-1,1),(1,-1)]:
                nx, ny = gx+dx, gy+dy
                if (nx, ny) in territory:
                    continue
                if nx < 0 or nx >= MAP_WIDTH//BIOME_GRID or ny < 0 or ny >= MAP_HEIGHT//BIOME_GRID:
                    continue
                if any((nx,ny) in t for t in self.kingdom_territories.values()):
                    continue
                # Don't expand into mountainous areas
                elevation = self.elevation_map.get((nx, ny), 0.0)
                if elevation > 0.5:
                    continue
                if random.random() < max(0.1, 1 - math.sqrt((nx-kingdom.x//BIOME_GRID)**2+(ny-kingdom.y//BIOME_GRID)**2)/40):
                    territory.add((nx, ny))
                    frontier.append((nx, ny))
        self.kingdom_territories[kid] = territory

    def generate_villages(self):
        # =========================================================================
        # VILLAGE DISTRIBUTION:
        # - 1-3 villages per kingdom (randomly distributed) - with LARGE buffer from kingdom
        # - Remaining villages placed as buffers between kingdoms
        # - GUARANTEED: 3 villages will be FREE (not belonging to any kingdom)
        # VILLAGES MUST BE FAR APART FROM EACH OTHER - 400px MINIMUM
        # VILLAGES MUST NOT TOUCH KINGDOMS - 400px MINIMUM
        # =========================================================================
        kingdoms = [l for l in self.locations if l.loc_type == LocationType.KINGDOM]
        village_idx = 0
        
        # Decide how many villages each kingdom gets (1-3 each, total ~6)
        kingdom_village_counts = []
        remaining = 6
        for i, k in enumerate(kingdoms):
            if i == len(kingdoms) - 1:
                # Last kingdom gets whatever is left
                count = remaining
            else:
                count = random.randint(1, min(3, remaining - (len(kingdoms) - i - 1)))
            kingdom_village_counts.append(count)
            remaining -= count
        
        # Track villages placed in each phase
        kingdom_villages = []  # Villages assigned to kingdoms
        buffer_villages = []   # Villages in buffer zones (candidates for free)
        
        # PHASE 1: Place villages for each kingdom with MASSIVE buffer
        for k_idx, kingdom in enumerate(kingdoms):
            num_villages = kingdom_village_counts[k_idx]
            
            for v_num in range(num_villages):
                best_pos = None
                best_dist = float('inf')
                
                for attempt in range(400):
                    # Place 400-650 pixels from kingdom - HUGE buffer zone
                    angle = random.uniform(0, 2 * math.pi)
                    dist = random.randint(400, 650)
                    x = kingdom.x + int(math.cos(angle) * dist)
                    y = kingdom.y + int(math.sin(angle) * dist)
                    
                    # Clamp to map bounds
                    x = max(150, min(MAP_WIDTH - 150, x))
                    y = max(150, min(MAP_HEIGHT - 150, y))
                    
                    biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
                    if biome == Biome.SWAMP:
                        continue
                    if self.is_in_water(x, y):
                        continue
                    if self.is_mountainous(x, y):
                        continue
                    
                    # Must be VERY far from ALL kingdoms (400px minimum)
                    if not all(math.sqrt((x-k.x)**2+(y-k.y)**2) >= 400 for k in kingdoms):
                        continue
                    
                    # Must be VERY far from other villages (400px minimum!!)
                    if not all(math.sqrt((x-l.x)**2+(y-l.y)**2) >= 400 for l in self.locations if l.loc_type == LocationType.VILLAGE):
                        continue
                    
                    # Track best position
                    d = math.sqrt((x - kingdom.x)**2 + (y - kingdom.y)**2)
                    if d < best_dist:
                        best_dist = d
                        best_pos = (x, y)
                
                if best_pos:
                    x, y = best_pos
                else:
                    # Fallback - force a position with huge buffer
                    for fallback_attempt in range(150):
                        angle = random.uniform(0, 2 * math.pi)
                        dist = 500 + random.randint(0, 150)
                        x = kingdom.x + int(math.cos(angle) * dist)
                        y = kingdom.y + int(math.sin(angle) * dist)
                        x = max(150, min(MAP_WIDTH - 150, x))
                        y = max(150, min(MAP_HEIGHT - 150, y))
                        
                        # Check village distance in fallback too
                        village_ok = all(math.sqrt((x-l.x)**2+(y-l.y)**2) >= 350 for l in self.locations if l.loc_type == LocationType.VILLAGE)
                        if not self.is_in_water(x, y) and village_ok:
                            break
                
                # Assign to this kingdom explicitly
                v = Location(x, y, LocationType.VILLAGE, self.village_names[village_idx], kingdom.kingdom_id, size=25)
                self.locations.append(v)
                kingdom_villages.append(v)
                village_idx += 1
        
        # PHASE 2: Place remaining villages as buffers (4 more for 10 total)
        remaining_villages = 10 - village_idx
        for i in range(remaining_villages):
            best_pos = None
            best_score = -1
            
            for attempt in range(350):
                x, y = random.randint(150, MAP_WIDTH-150), random.randint(150, MAP_HEIGHT-150)
                biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
                if biome == Biome.SWAMP:
                    continue
                if self.is_in_water(x, y):
                    continue
                if self.is_mountainous(x, y):
                    continue
                
                # Must be VERY far from ALL kingdoms (400px buffer)
                if not all(math.sqrt((x-k.x)**2+(y-k.y)**2) >= 400 for k in kingdoms):
                    continue
                
                # Must be VERY far from other villages (400px!!)
                if not all(math.sqrt((x-l.x)**2+(y-l.y)**2) >= 400 for l in self.locations if l.loc_type == LocationType.VILLAGE):
                    continue
                
                # Score based on being between kingdoms (buffer zones)
                if kingdoms:
                    dists_to_kingdoms = [math.sqrt((x-k.x)**2 + (y-k.y)**2) for k in kingdoms]
                    min_dist = min(dists_to_kingdoms)
                    
                    sorted_dists = sorted(dists_to_kingdoms)
                    if len(sorted_dists) >= 2:
                        dist_ratio = sorted_dists[0] / sorted_dists[1] if sorted_dists[1] > 0 else 0
                        score = dist_ratio * 100 + min_dist * 0.2
                    else:
                        score = min_dist
                    
                    if score > best_score:
                        best_score = score
                        best_pos = (x, y)
            
            if best_pos:
                x, y = best_pos
            else:
                # Fallback - still enforce distance
                for _ in range(150):
                    x, y = random.randint(200, MAP_WIDTH-200), random.randint(200, MAP_HEIGHT-200)
                    village_ok = all(math.sqrt((x-l.x)**2+(y-l.y)**2) >= 350 for l in self.locations if l.loc_type == LocationType.VILLAGE)
                    if not self.is_in_water(x, y) and not self.is_mountainous(x, y) and village_ok:
                        break
            
            # Initially assign based on territory, but this may be overridden below
            v = Location(x, y, LocationType.VILLAGE, self.village_names[village_idx], self.get_kingdom_at(x, y), size=25)
            self.locations.append(v)
            buffer_villages.append(v)
            village_idx += 1
        
        # =========================================================================
        # GUARANTEE 3 FREE VILLAGES
        # Select the 3 villages that are most "neutral" (furthest from all kingdoms)
        # =========================================================================
        all_villages = kingdom_villages + buffer_villages
        
        # Calculate "neutrality score" for each village (sum of distances to all kingdoms)
        def neutrality_score(village):
            return sum(math.sqrt((village.x - k.x)**2 + (village.y - k.y)**2) for k in kingdoms)
        
        # Sort villages by neutrality (most neutral first)
        sorted_by_neutrality = sorted(all_villages, key=neutrality_score, reverse=True)
        
        # Make the top 3 most neutral villages FREE
        for i, v in enumerate(sorted_by_neutrality[:3]):
            v.kingdom_id = None
        
        # Now add houses and farms to ALL villages
        villages = [l for l in self.locations if l.loc_type == LocationType.VILLAGE]
        for v in villages:
            x, y = v.x, v.y  # Use village coordinates
            
            # Create organic village layout with some grid influence
            num_houses = random.randint(5, 8)
            
            # Main street orientation with variation
            main_angle = random.uniform(0, math.pi)  # Random orientation
            perpendicular = main_angle + math.pi / 2
            
            # House spacing (tighter)
            house_spacing = random.randint(18, 24)
            street_offset = random.randint(14, 20)
            
            # Place houses with organic variation
            for h in range(num_houses):
                # Position along main street with jitter
                street_pos = (h // 2 - num_houses // 4) * house_spacing + random.randint(-6, 6)
                side = 1 if h % 2 == 0 else -1
                side_dist = street_offset + random.randint(-4, 4)
                
                hx = x + int(math.cos(main_angle) * street_pos + math.cos(perpendicular) * side * side_dist)
                hy = y + int(math.sin(main_angle) * street_pos + math.sin(perpendicular) * side * side_dist)
                
                # Validate position
                if self.is_in_water(hx, hy):
                    continue
                biome = self.biome_map.get((hx // BIOME_GRID, hy // BIOME_GRID), Biome.PLAINS)
                if biome == Biome.SWAMP:
                    continue
                # Check no overlap with existing locations
                if not all(math.sqrt((hx-l.x)**2+(hy-l.y)**2) >= 15 for l in self.locations):
                    continue
                
                is_large = h == 0
                house = Location(hx, hy, LocationType.VILLAGE_HOUSE, f"{v.name} House", v.kingdom_id, size=8 if is_large else 6)
                self.locations.append(house)
            
            # Store layout info for path painting
            v.layout = {'main_angle': main_angle, 'street_offset': street_offset, 'has_market': True}
            
            # =========================================================================
            # IMPORTANT: EVERY VILLAGE MUST HAVE 2-3 FARMS IN CLOSE PROXIMITY
            # DO NOT CHANGE THIS - 2-3 FARMS PER VILLAGE, CLOSE TO THE VILLAGE
            # =========================================================================
            target_farms = random.randint(2, 3)
            for farm_idx in range(target_farms):  # We WILL place these farms
                placed = False
                for attempt in range(150):  # 150 attempts per farm
                    farm_angle = random.uniform(0, 2 * math.pi)
                    d = random.randint(28, 55)  # Close to village
                    fx = x + int(math.cos(farm_angle) * d)
                    fy = y + int(math.sin(farm_angle) * d)
                    fx = max(30, min(MAP_WIDTH - 30, fx))
                    fy = max(30, min(MAP_HEIGHT - 30, fy))
                    
                    if self.is_in_water(fx, fy):
                        continue
                    
                    biome = self.biome_map.get((fx // BIOME_GRID, fy // BIOME_GRID), Biome.PLAINS)
                    if biome == Biome.SWAMP:
                        continue
                    
                    # Relax mountain/rocky check after many attempts
                    if attempt < 80:
                        if self.is_mountainous(fx, fy) or self.is_rocky(fx, fy):
                            continue
                    
                    # Check no overlap with existing locations
                    if all(math.sqrt((fx-l.x)**2+(fy-l.y)**2) >= 15 for l in self.locations):
                        f = Location(fx, fy, LocationType.FARM, f"{v.name} Farm", v.kingdom_id, size=15)
                        v.farms.append(f)
                        self.locations.append(f)
                        placed = True
                        break
                
                # Force place if still not placed
                if not placed:
                    farm_angle = (2 * math.pi * farm_idx) / target_farms
                    d = 40
                    fx = x + int(math.cos(farm_angle) * d)
                    fy = y + int(math.sin(farm_angle) * d)
                    fx = max(30, min(MAP_WIDTH - 30, fx))
                    fy = max(30, min(MAP_HEIGHT - 30, fy))
                    f = Location(fx, fy, LocationType.FARM, f"{v.name} Farm", v.kingdom_id, size=15)
                    v.farms.append(f)
                    self.locations.append(f)

    def generate_encampments(self):
        # =========================================================================
        # GUARANTEED 10-12 ENCAMPMENTS spread across the map
        # =========================================================================
        target_encampments = random.randint(10, 12)
        
        for i in range(target_encampments):
            placed = False
            for attempt in range(200):
                x, y = random.randint(120, MAP_WIDTH-120), random.randint(120, MAP_HEIGHT-120)
                # Must be away from kingdoms and villages
                if any(math.sqrt((x-l.x)**2+(y-l.y)**2) < 180 for l in self.locations if l.loc_type in [LocationType.KINGDOM, LocationType.VILLAGE]):
                    continue
                # Must be away from other encampments
                if any(math.sqrt((x-l.x)**2+(y-l.y)**2) < 120 for l in self.locations if l.loc_type == LocationType.ENCAMPMENT):
                    continue
                # Must not be in water or swamp
                if self.is_in_water(x, y):
                    continue
                biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
                if biome == Biome.SWAMP:
                    continue
                # Encampments should NOT be on roads - they're hidden camps
                if self.is_on_road(x, y, buffer=35):
                    continue
                
                placed = True
                break
            
            # Force place if needed
            if not placed:
                for _ in range(50):
                    x, y = random.randint(100, MAP_WIDTH-100), random.randint(100, MAP_HEIGHT-100)
                    if not self.is_in_water(x, y):
                        break
            
            name = self.encampment_names[i % len(self.encampment_names)]
            e = Location(x, y, LocationType.ENCAMPMENT, name, self.get_kingdom_at(x, y), size=20)
            self.locations.append(e)
            
            # Encampments rarely have farms - they're temporary camps
            if random.random() < 0.25:
                a, d = random.uniform(0, 2*math.pi), random.randint(50, 80)
                fx, fy = x + int(math.cos(a)*d), y + int(math.sin(a)*d)
                biome = self.biome_map.get((fx // BIOME_GRID, fy // BIOME_GRID), Biome.PLAINS)
                if not self.is_in_water(fx, fy) and biome != Biome.SWAMP and not self.is_mountainous(fx, fy):
                    f = Location(fx, fy, LocationType.FARM, f"{e.name} Farm", e.kingdom_id, size=15)
                    e.farms.append(f)
                    self.locations.append(f)

    def generate_mines_and_caves(self):
        # Mines and caves - more caves!
        num_mines = random.randint(4, 6)
        num_caves = random.randint(12, 18)  # GUARANTEED 12-18 caves - DO NOT REDUCE
        
        for num, lt, names, sz in [(num_mines, LocationType.MINE, self.mine_names, 18), (num_caves, LocationType.CAVE, self.cave_names, 22)]:
            placed = []
            for i in range(num):
                best_pos = None
                best_score = -1
                
                for _ in range(80):
                    x, y = random.randint(120, MAP_WIDTH-120), random.randint(120, MAP_HEIGHT-120)
                    
                    if self.is_in_water(x, y):
                        continue
                    if not all(math.sqrt((x-l.x)**2+(y-l.y)**2) >= (100 if l.loc_type in [LocationType.KINGDOM, LocationType.VILLAGE] else 60) for l in self.locations):
                        continue
                    
                    min_dist_to_same = min([math.sqrt((x-px)**2+(y-py)**2) for px, py in placed], default=999)
                    
                    # Rocky and mountainous areas get bonus
                    is_mountain = self.is_mountainous(x, y, threshold=0.3)
                    is_rocky_area = self.is_rocky(x, y, threshold=0.25)
                    
                    terrain_bonus = 1.0
                    if is_mountain:
                        terrain_bonus = 1.8
                    elif is_rocky_area:
                        terrain_bonus = 1.5
                    
                    biome = self.biome_map.get((x//BIOME_GRID, y//BIOME_GRID), Biome.PLAINS)
                    if lt == LocationType.CAVE and biome == Biome.FOREST:
                        terrain_bonus = max(terrain_bonus, 1.3)
                    
                    score = min_dist_to_same * terrain_bonus
                    
                    if score > best_score:
                        best_score = score
                        best_pos = (x, y)
                
                if best_pos:
                    x, y = best_pos
                    placed.append((x, y))
                    self.locations.append(Location(x, y, lt, names[i % len(names)], self.get_kingdom_at(x, y), size=sz))

    def generate_clearings(self):
        for i in range(random.randint(6, 10)):
            for _ in range(150):
                x, y = random.randint(120, MAP_WIDTH-120), random.randint(120, MAP_HEIGHT-120)
                # Must be away from all buildings (increased spacing)
                if any(math.sqrt((x-l.x)**2+(y-l.y)**2) < 280 for l in self.locations if l.loc_type in [LocationType.KINGDOM, LocationType.VILLAGE, LocationType.ENCAMPMENT, LocationType.HOUSE, LocationType.INN, LocationType.FARM]):
                    continue
                # Must be away from other clearings (increased spacing)
                if any(math.sqrt((x-l.x)**2+(y-l.y)**2) < 180 for l in self.locations if l.loc_type == LocationType.CLEARING):
                    continue
                # Must not be in water
                if self.is_in_water(x, y):
                    continue
                # Must be away from roads (wider buffer)
                if self.is_on_road(x, y, buffer=60):
                    continue
                break
            self.locations.append(Location(x, y, LocationType.CLEARING, f"Clearing {i+1}", size=random.randint(35, 60)))

    def generate_roads(self):
        """Generate roads - main roads between kingdoms, villages connect via short spurs"""
        kingdoms = [l for l in self.locations if l.loc_type == LocationType.KINGDOM]
        villages = [l for l in self.locations if l.loc_type == LocationType.VILLAGE]
        
        # Step 1: Create main roads between all kingdoms
        for i, k1 in enumerate(kingdoms):
            for k2 in kingdoms[i+1:]:
                self.roads.append(self.create_road(k1, k2, True))
        
        # Step 2: Each village connects to nearest road via SHORT PERPENDICULAR spur
        # This prevents parallel roads - villages tap into existing roads
        for village in villages:
            # Find closest point on any existing road
            best_dist = float('inf')
            best_point = None
            
            for road in self.roads:
                for i in range(len(road.points) - 1):
                    p1, p2 = road.points[i], road.points[i + 1]
                    
                    # Calculate closest point on this segment
                    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                    seg_len_sq = dx * dx + dy * dy
                    
                    if seg_len_sq == 0:
                        closest = p1
                    else:
                        t = max(0, min(1, ((village.x - p1[0]) * dx + (village.y - p1[1]) * dy) / seg_len_sq))
                        closest = (int(p1[0] + t * dx), int(p1[1] + t * dy))
                    
                    dist = math.sqrt((village.x - closest[0])**2 + (village.y - closest[1])**2)
                    if dist < best_dist:
                        best_dist = dist
                        best_point = closest
            
            # Create spur road from village to nearest road point
            if best_point and best_dist < 400:
                # Simple straight spur with one midpoint for slight curve
                mid_x = (village.x + best_point[0]) // 2 + random.randint(-10, 10)
                mid_y = (village.y + best_point[1]) // 2 + random.randint(-10, 10)
                spur = Road([(village.x, village.y), (mid_x, mid_y), best_point], False)
                self.roads.append(spur)
            elif best_point:
                # Village is far - create a longer road but try to angle toward existing infrastructure
                self.roads.append(self.create_road(village, 
                    Location(best_point[0], best_point[1], LocationType.VILLAGE, "temp", 0), False))

    def create_road(self, l1, l2, main):
        """Create a road that follows compass directions with natural curves"""
        pts = [(l1.x, l1.y)]
        
        current_x, current_y = float(l1.x), float(l1.y)
        target_x, target_y = float(l2.x), float(l2.y)
        
        # Determine general direction and plan route
        dx_total = target_x - current_x
        dy_total = target_y - current_y
        total_dist = math.sqrt(dx_total**2 + dy_total**2)
        
        # For short distances, just go direct with one midpoint
        if total_dist < 150:
            mid_x = (l1.x + l2.x) // 2 + random.randint(-15, 15)
            mid_y = (l1.y + l2.y) // 2 + random.randint(-15, 15)
            if not self.is_in_water(mid_x, mid_y):
                pts.append((mid_x, mid_y))
            pts.append((l2.x, l2.y))
            return Road(pts, main)
        
        # For longer roads, use compass-direction segments
        # Decide if we go mostly horizontal-then-vertical or vice versa
        go_horizontal_first = abs(dx_total) > abs(dy_total)
        if random.random() < 0.3:
            go_horizontal_first = not go_horizontal_first
        
        segments = random.randint(2, 4)
        
        for seg in range(segments):
            # Calculate intermediate target
            if go_horizontal_first:
                if seg % 2 == 0:
                    # Horizontal segment
                    next_x = current_x + (target_x - current_x) * random.uniform(0.3, 0.5)
                    next_y = current_y + random.uniform(-25, 25)
                else:
                    # Vertical segment  
                    next_x = current_x + random.uniform(-25, 25)
                    next_y = current_y + (target_y - current_y) * random.uniform(0.3, 0.5)
            else:
                if seg % 2 == 0:
                    # Vertical segment
                    next_x = current_x + random.uniform(-25, 25)
                    next_y = current_y + (target_y - current_y) * random.uniform(0.3, 0.5)
                else:
                    # Horizontal segment
                    next_x = current_x + (target_x - current_x) * random.uniform(0.3, 0.5)
                    next_y = current_y + random.uniform(-25, 25)
            
            # Clamp to map
            next_x = max(30, min(MAP_WIDTH - 30, next_x))
            next_y = max(30, min(MAP_HEIGHT - 30, next_y))
            
            # Avoid water
            attempts = 0
            while self.is_in_water(int(next_x), int(next_y)) and attempts < 10:
                next_x += random.uniform(-40, 40)
                next_y += random.uniform(-40, 40)
                next_x = max(30, min(MAP_WIDTH - 30, next_x))
                next_y = max(30, min(MAP_HEIGHT - 30, next_y))
                attempts += 1
            
            # Only add point if it makes progress toward target
            dist_to_target = math.sqrt((next_x - target_x)**2 + (next_y - target_y)**2)
            if dist_to_target < total_dist * 0.9:
                pts.append((int(next_x), int(next_y)))
                current_x, current_y = next_x, next_y
                total_dist = dist_to_target  # Update remaining distance
        
        pts.append((l2.x, l2.y))
        return Road(pts, main)

    def generate_bridges(self):
        """Generate bridges where roads cross water and standalone bridges on long rivers"""
        
        # First, find all road-water crossings
        for road in self.roads:
            smooth_points = self._get_smooth_road_points(road)
            
            for i in range(len(smooth_points) - 1):
                p1 = smooth_points[i]
                p2 = smooth_points[i + 1]
                mid_x = (p1[0] + p2[0]) // 2
                mid_y = (p1[1] + p2[1]) // 2
                
                # Check if this segment crosses water
                if self.is_in_water(mid_x, mid_y):
                    # Calculate road angle at this point
                    angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                    
                    # Estimate bridge length based on water body width
                    bridge_length = self._estimate_water_width(mid_x, mid_y, angle)
                    
                    # Check if bridge already exists nearby
                    too_close = any(math.sqrt((mid_x - b.x)**2 + (mid_y - b.y)**2) < 30 for b in self.bridges)
                    if not too_close:
                        self.bridges.append(Bridge(mid_x, mid_y, angle, bridge_length, is_stone=road.is_main))
        
        # Second, add standalone bridges on long rivers without road crossings
        for wb in self.water_bodies:
            if not wb.is_river or wb.width < 6:  # Only for substantial rivers
                continue
            
            # Check if river has enough length
            total_length = 0
            for i in range(len(wb.points) - 1):
                p1, p2 = wb.points[i], wb.points[i + 1]
                total_length += math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
            
            if total_length < 200:
                continue
            
            # Count existing bridges on this river
            existing_bridges = 0
            for b in self.bridges:
                for i in range(len(wb.points) - 1):
                    if self.point_to_segment_dist(b.x, b.y, *wb.points[i], *wb.points[i + 1]) < wb.width + 20:
                        existing_bridges += 1
                        break
            
            # Add standalone bridges if needed (1 per 300 pixels of river)
            target_bridges = max(1, int(total_length / 300))
            bridges_to_add = target_bridges - existing_bridges
            
            if bridges_to_add > 0:
                # Find points along river to add bridges
                for _ in range(bridges_to_add):
                    if len(wb.points) < 2:
                        break
                    
                    # Pick random segment
                    seg_idx = random.randint(0, len(wb.points) - 2)
                    p1, p2 = wb.points[seg_idx], wb.points[seg_idx + 1]
                    t = random.uniform(0.3, 0.7)
                    bx = int(p1[0] + (p2[0] - p1[0]) * t)
                    by = int(p1[1] + (p2[1] - p1[1]) * t)
                    
                    # Bridge perpendicular to river
                    river_angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                    bridge_angle = river_angle + math.pi / 2
                    
                    # Check not too close to existing bridges
                    too_close = any(math.sqrt((bx - b.x)**2 + (by - b.y)**2) < 80 for b in self.bridges)
                    if not too_close:
                        self.bridges.append(Bridge(bx, by, bridge_angle, wb.width + 12, is_stone=False))
    
    def _get_smooth_road_points(self, road):
        """Get interpolated points along a road"""
        if len(road.points) < 2:
            return road.points
        
        smooth_points = []
        points = road.points
        
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            steps = max(2, int(dist / 20))
            
            for t in range(steps):
                tt = t / steps
                x = int(p1[0] + (p2[0] - p1[0]) * tt)
                y = int(p1[1] + (p2[1] - p1[1]) * tt)
                smooth_points.append((x, y))
        
        smooth_points.append(points[-1])
        return smooth_points
    
    def _estimate_water_width(self, x, y, angle):
        """Estimate width of water body at given point perpendicular to angle"""
        perp_angle = angle + math.pi / 2
        
        # Search outward in perpendicular direction
        width = 0
        for dist in range(5, 60, 3):
            px1 = x + int(math.cos(perp_angle) * dist)
            py1 = y + int(math.sin(perp_angle) * dist)
            px2 = x - int(math.cos(perp_angle) * dist)
            py2 = y - int(math.sin(perp_angle) * dist)
            
            in_water1 = self.is_in_water(px1, py1)
            in_water2 = self.is_in_water(px2, py2)
            
            if in_water1 or in_water2:
                width = dist * 2
            else:
                break
        
        return max(15, min(width + 8, 50))  # Clamp bridge length

    def generate_inns_and_houses(self):
        # Generate fewer inns along roads
        inn_count = 0
        target_inns = random.randint(3, 5)  # Reduced from 6-10
        attempts = 0
        while inn_count < target_inns and attempts < 200:
            attempts += 1
            if not self.roads:
                break
            road = random.choice(self.roads)
            if len(road.points) < 2:
                continue
            idx = random.randint(0, len(road.points) - 2)
            p1, p2 = road.points[idx], road.points[idx + 1]
            t = random.uniform(0.3, 0.7)
            x = int(p1[0] + (p2[0] - p1[0]) * t + random.randint(-15, 15))
            y = int(p1[1] + (p2[1] - p1[1]) * t + random.randint(-15, 15))
            
            if self.is_in_water(x, y):
                continue
            if not self.is_valid_position(x, y, 100):  # More spread out
                continue
            
            biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
            if biome == Biome.SWAMP:
                continue
                
            inn_names = ["The Wanderer's Rest", "The Golden Tankard", "The Prancing Pony", 
                        "The Sleeping Giant", "The Green Dragon"]
            self.locations.append(Location(x, y, LocationType.INN, inn_names[inn_count % len(inn_names)], size=18))
            inn_count += 1
        
        # Generate fewer houses along roads
        road_houses = random.randint(4, 8)  # Reduced from 8-14
        for _ in range(road_houses):
            for attempt in range(50):
                if not self.roads:
                    break
                road = random.choice(self.roads)
                if len(road.points) < 2:
                    continue
                idx = random.randint(0, len(road.points) - 2)
                p1, p2 = road.points[idx], road.points[idx + 1]
                x = int(p1[0] + (p2[0] - p1[0]) * random.uniform(0, 1) + random.randint(-35, 35))
                y = int(p1[1] + (p2[1] - p1[1]) * random.uniform(0, 1) + random.randint(-35, 35))
                
                if self.is_in_water(x, y):
                    continue
                    
                biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
                if biome == Biome.SWAMP:
                    continue
                    
                if self.is_valid_position(x, y, 50):
                    h = Location(x, y, LocationType.HOUSE, "House", size=12)
                    self.locations.append(h)
                    
                    if random.random() < 0.3:
                        a, d = random.uniform(0, 2 * math.pi), random.randint(35, 55)
                        fx, fy = x + int(math.cos(a) * d), y + int(math.sin(a) * d)
                        farm_biome = self.biome_map.get((fx // BIOME_GRID, fy // BIOME_GRID), Biome.PLAINS)
                        if not self.is_in_water(fx, fy) and farm_biome != Biome.SWAMP and not self.is_mountainous(fx, fy) and not self.is_rocky(fx, fy):
                            f = Location(fx, fy, LocationType.FARM, "Homestead Farm", size=15)
                            h.farms.append(f)
                            self.locations.append(f)
                    break
        
        # =========================================================================
        # OFF-GRID: Equal number of houses and farms scattered in remote areas
        # =========================================================================
        offgrid_count = random.randint(12, 18)  # This many houses AND this many farms
        
        # Generate off-grid houses
        houses_placed = 0
        for _ in range(offgrid_count * 2):  # Extra attempts
            if houses_placed >= offgrid_count:
                break
            for attempt in range(80):
                x, y = random.randint(100, MAP_WIDTH - 100), random.randint(100, MAP_HEIGHT - 100)
                
                if self.is_in_water(x, y):
                    continue
                
                biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
                if biome == Biome.SWAMP:
                    continue
                
                # Must be far from roads (truly off-grid)
                if self.is_on_road(x, y, buffer=60):
                    continue
                    
                if self.is_valid_position(x, y, 45):
                    h = Location(x, y, LocationType.HOUSE, "Farmstead", size=12)
                    self.locations.append(h)
                    houses_placed += 1
                    break
        
        # Generate off-grid farms (equal to houses)
        farms_placed = 0
        for _ in range(offgrid_count * 2):  # Extra attempts
            if farms_placed >= offgrid_count:
                break
            for attempt in range(80):
                x, y = random.randint(100, MAP_WIDTH - 100), random.randint(100, MAP_HEIGHT - 100)
                
                if self.is_in_water(x, y):
                    continue
                
                biome = self.biome_map.get((x // BIOME_GRID, y // BIOME_GRID), Biome.PLAINS)
                if biome == Biome.SWAMP:
                    continue
                if self.is_mountainous(x, y) or self.is_rocky(x, y):
                    continue
                
                # Must be far from roads
                if self.is_on_road(x, y, buffer=50):
                    continue
                    
                if self.is_valid_position(x, y, 45):
                    f = Location(x, y, LocationType.FARM, "Farm", size=15)  # Normal size farms
                    self.locations.append(f)
                    farms_placed += 1
                    break

    def generate_trees(self):
        # Store clearing positions for tree density reduction
        clearing_positions = [(l.x, l.y, l.size) for l in self.locations if l.loc_type == LocationType.CLEARING]
        
        for gx in range(0, MAP_WIDTH, BIOME_GRID):
            for gy in range(0, MAP_HEIGHT, BIOME_GRID):
                biome = self.biome_map.get((gx // BIOME_GRID, gy // BIOME_GRID), Biome.PLAINS)
                elevation = self.elevation_map.get((gx // BIOME_GRID, gy // BIOME_GRID), 0.0)
                rockiness = self.rocky_map.get((gx // BIOME_GRID, gy // BIOME_GRID), 0.0)
                
                if self.is_in_water(gx + BIOME_GRID//2, gy + BIOME_GRID//2): continue
                
                # Check if in or near clearing - reduce density significantly
                in_clearing = any(math.sqrt((gx-cx)**2+(gy-cy)**2) < sz + 30 for cx, cy, sz in clearing_positions)
                near_clearing = any(math.sqrt((gx-cx)**2+(gy-cy)**2) < sz + 60 for cx, cy, sz in clearing_positions)
                
                if in_clearing:
                    continue  # No trees inside clearings
                
                near_settlement = any(math.sqrt((gx-l.x)**2+(gy-l.y)**2) < l.size + 35 for l in self.locations if l.loc_type in [LocationType.KINGDOM, LocationType.VILLAGE, LocationType.ENCAMPMENT])
                
                # Set density based on biome - INCREASED SIGNIFICANTLY
                if biome == Biome.FOREST:
                    base_density = 0.95
                    density = 0.4 if near_settlement else (0.6 if near_clearing else base_density)
                    sz = (4, 9)
                    trees_per_cell = random.randint(6, 12)  # More trees per cell
                elif biome == Biome.SWAMP:
                    base_density = 0.85
                    density = 0.3 if near_settlement else (0.5 if near_clearing else base_density)
                    sz = (3, 7)
                    trees_per_cell = random.randint(5, 9)
                elif biome == Biome.PLAINS:
                    base_density = 0.45  # More trees in plains
                    density = 0.15 if near_settlement else (0.25 if near_clearing else base_density)
                    sz = (3, 6)
                    trees_per_cell = random.randint(1, 3)  # Sometimes clusters
                else:
                    continue
                
                # Reduce trees in mountainous/rocky areas
                if elevation > 0.3:
                    density *= (1.0 - elevation * 0.6)
                    trees_per_cell = max(1, int(trees_per_cell * (1.0 - elevation * 0.5)))
                if rockiness > 0.4:
                    density *= (1.0 - rockiness * 0.5)
                    trees_per_cell = max(1, int(trees_per_cell * 0.6))
                
                if random.random() < density:
                    for _ in range(trees_per_cell):
                        tx, ty = gx + random.randint(0, BIOME_GRID-1), gy + random.randint(0, BIOME_GRID-1)
                        if not self.is_in_water(tx, ty) and not self.is_on_road(tx, ty, buffer=0):
                            self.trees.append((tx, ty, random.randint(*sz)))

    # ─── HELPERS ──────────────────────────────────────────────────────────────

    def is_in_water(self, x, y):
        for wb in self.water_bodies:
            if wb.is_river:
                for i in range(len(wb.points) - 1):
                    if self.point_to_segment_dist(x, y, *wb.points[i], *wb.points[i+1]) < wb.width + 5: return True
            elif self.point_in_polygon(x, y, wb.points): return True
        return False

    def is_on_road(self, x, y, buffer=0):
        for r in self.roads:
            for i in range(len(r.points) - 1):
                base_dist = 3 if r.is_main else 2  # Thinner roads
                if self.point_to_segment_dist(x, y, *r.points[i], *r.points[i+1]) < base_dist + buffer:
                    return True
        return False

    def is_valid_position(self, x, y, min_dist):
        """Check if position is valid - not too close to other locations and not on roads"""
        # Check distance from other locations
        if not all(math.sqrt((x-l.x)**2+(y-l.y)**2) >= min_dist for l in self.locations):
            return False
        # Check not directly on a road
        if self.is_on_road(x, y, buffer=8):
            return False
        return True

    def get_kingdom_at(self, x, y):
        gx, gy = x // BIOME_GRID, y // BIOME_GRID
        for kid, t in self.kingdom_territories.items():
            if (gx, gy) in t: return kid
        return None

    def point_to_segment_dist(self, px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0: return math.sqrt((px-x1)**2+(py-y1)**2)
        t = max(0, min(1, ((px-x1)*dx+(py-y1)*dy)/(dx*dx+dy*dy)))
        return math.sqrt((px-(x1+t*dx))**2+(py-(y1+t*dy))**2)

    def point_in_polygon(self, x, y, poly):
        inside, j = False, len(poly) - 1
        for i in range(len(poly)):
            if ((poly[i][1] > y) != (poly[j][1] > y)) and (x < (poly[j][0]-poly[i][0])*(y-poly[i][1])/(poly[j][1]-poly[i][1])+poly[i][0]):
                inside = not inside
            j = i
        return inside

    # ─── RENDERING ────────────────────────────────────────────────────────────

    def render_map_surface(self):
        self.map_surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
        for cx in range(CELLS_X):
            for cy in range(CELLS_Y):
                if self.cells[cx][cy]:
                    pygame.draw.rect(self.map_surface, self.cells[cx][cy], (cx * CELL_SIZE, cy * CELL_SIZE, CELL_SIZE, CELL_SIZE))

    def draw(self):
        self.screen.fill((26, 26, 46))
        pygame.draw.rect(self.screen, (42, 42, 42), (0, 0, MAP_WIDTH, UI_HEIGHT))
        self.screen.blit(self.font.render("Seed:", True, (170, 170, 170)), (10, 12))
        input_rect = pygame.Rect(60, 8, 180, 24)
        pygame.draw.rect(self.screen, (80, 80, 80) if self.seed_input_active else (58, 58, 58), input_rect)
        pygame.draw.rect(self.screen, (100, 100, 100), input_rect, 1)
        self.screen.blit(self.font.render(self.seed_text, True, (255, 255, 255)), (65, 11))
        for rect, text in [((250, 8, 80, 24), "Generate"), ((340, 8, 90, 24), "Randomize")]:
            pygame.draw.rect(self.screen, (74, 74, 74), rect)
            self.screen.blit(self.font.render(text, True, (255, 255, 255)), (rect[0] + 8, rect[1] + 4))
        
        # Territories toggle button
        territories_rect = (450, 8, 100, 24)
        btn_color = (60, 100, 60) if self.show_territories else (74, 74, 74)
        pygame.draw.rect(self.screen, btn_color, territories_rect)
        pygame.draw.rect(self.screen, (100, 150, 100) if self.show_territories else (100, 100, 100), territories_rect, 1)
        self.screen.blit(self.font.render("Territories", True, (255, 255, 255)), (territories_rect[0] + 8, territories_rect[1] + 4))
        
        if self.map_surface:
            sz = (int(MAP_WIDTH * self.view_scale), int(MAP_HEIGHT * self.view_scale))
            if sz[0] > 0 and sz[1] > 0:
                self.screen.blit(pygame.transform.scale(self.map_surface, sz), (self.view_x, self.view_y + UI_HEIGHT))
                
                # Draw territory overlay if enabled
                if self.show_territories and self.territory_surface:
                    scaled_territory = pygame.transform.scale(self.territory_surface, sz)
                    self.screen.blit(scaled_territory, (self.view_x, self.view_y + UI_HEIGHT))
        for loc in self.locations:
            if loc.loc_type in [LocationType.KINGDOM, LocationType.VILLAGE, LocationType.ENCAMPMENT, LocationType.INN, LocationType.MINE, LocationType.CAVE]:
                sx, sy = self.world_to_screen(loc.x, loc.y)
                sy += (25 if loc.loc_type == LocationType.KINGDOM else 15) * self.view_scale
                font = self.font_label_bold if loc.loc_type == LocationType.KINGDOM else self.font_label
                color = (255, 215, 0) if loc.loc_type == LocationType.KINGDOM else (255, 255, 255)
                text = font.render(loc.name, True, color)
                rect = text.get_rect(center=(sx, sy))
                for dx, dy in [(-1,-1),(-1,1),(1,-1),(1,1)]:
                    self.screen.blit(font.render(loc.name, True, (0,0,0)), (rect.x+dx, rect.y+dy))
                self.screen.blit(text, rect)
        if self.hovered_location:
            loc, mx, my = self.hovered_location, *pygame.mouse.get_pos()
            lines = [loc.name, loc.loc_type.value.title()]
            if loc.loc_type == LocationType.KINGDOM: lines.append(f"Farms: {len(loc.farms)}")
            elif loc.loc_type in [LocationType.VILLAGE, LocationType.ENCAMPMENT]:
                lines += [f"Kingdom: {self.kingdom_names[loc.kingdom_id] if loc.kingdom_id is not None else 'Free Territory'}", f"Farms: {len(loc.farms)}"]
            w, h = max(self.font_small.size(l)[0] for l in lines) + 10, len(lines) * 16 + 10
            tx = mx - w - 5 if mx + 15 + w > MAP_WIDTH else mx + 15
            pygame.draw.rect(self.screen, (26, 26, 46), (tx, my - 10, w, h))
            pygame.draw.rect(self.screen, (201, 162, 39), (tx, my - 10, w, h), 1)
            for i, line in enumerate(lines):
                self.screen.blit(self.font_small.render(line, True, (255, 215, 0)), (tx + 5, my - 5 + i * 16))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if my < UI_HEIGHT:
                    self.seed_input_active = pygame.Rect(60, 8, 180, 24).collidepoint(mx, my)
                    if not self.seed_input_active:
                        if pygame.Rect(250, 8, 80, 24).collidepoint(mx, my): self.generate_with_seed()
                        elif pygame.Rect(340, 8, 90, 24).collidepoint(mx, my): self.generate_world()
                        elif pygame.Rect(450, 8, 100, 24).collidepoint(mx, my): self.show_territories = not self.show_territories
                else:
                    self.seed_input_active = False
                    if event.button == 1: self.dragging, self.drag_start, self.drag_view_start = True, event.pos, (self.view_x, self.view_y)
                    elif event.button in [4, 5]: self.zoom_at(event.pos, 1.25 if event.button == 4 else 0.8)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1: self.dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if self.dragging: self.view_x, self.view_y = self.drag_view_start[0] + event.pos[0] - self.drag_start[0], self.drag_view_start[1] + event.pos[1] - self.drag_start[1]
                elif event.pos[1] > UI_HEIGHT:
                    wx, wy = self.screen_to_world(*event.pos)
                    self.hovered_location = next((l for l in self.locations if math.sqrt((wx-l.x)**2+(wy-l.y)**2) < l.size + 15), None)
                else: self.hovered_location = None
            elif event.type == pygame.MOUSEWHEEL and pygame.mouse.get_pos()[1] > UI_HEIGHT:
                self.zoom_at(pygame.mouse.get_pos(), 1.25 if event.y > 0 else 0.8)
            elif event.type == pygame.KEYDOWN and self.seed_input_active:
                if event.key == pygame.K_RETURN: self.generate_with_seed(); self.seed_input_active = False
                elif event.key == pygame.K_BACKSPACE: self.seed_text = self.seed_text[:-1]
                elif event.unicode.isprintable(): self.seed_text += event.unicode
        return True

    def zoom_at(self, pos, factor):
        mx, my = pos
        wx, wy = self.screen_to_world(mx, my)
        new = self.view_scale * factor
        if 0.2 < new < 10:
            self.view_scale = new
            self.view_x, self.view_y = mx - wx * new, (my - UI_HEIGHT) - wy * new

    def run(self):
        while self.handle_events():
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()


if __name__ == "__main__":
    WorldMapGenerator().run()