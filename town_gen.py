import random
import math
import numpy as np
import json

# Cell type constants (internal use)
GRASS = 0
ROAD = 1
FENCE = 2
HOUSE = 3
FARM = 4
MARKET = 5
STALL = 6
MILITARY_HOUSING = 7
GARDEN = 9
FARMHOUSE = 10
TREE = 11


class TownGenerator:
    def __init__(self, size=50, seed=None, road_entries=None, num_houses=12, 
                 num_farms=3, name=None, tree_density=0.08):
        self.seed = seed if seed else random.randint(1, 99999)
        random.seed(self.seed)
        np.random.seed(self.seed)
        self.size = size
        self.grid = np.zeros((size, size), dtype=int)
        self.buildings = []
        self.road_cells = set()
        self.town_center = None
        self.road_entries = road_entries if road_entries else []
        self.num_houses = num_houses
        self.num_farms = num_farms
        self.name = name if name else "Town"
        self.tree_density = tree_density
        
        # Store data for JSON output
        self.areas = []
        self.farm_cells_map = {}  # farm_id -> list of (x, y) cells
        self.tree_positions = []
        self.road_positions = []
    
    def generate(self):
        """Generate the town and return structured data."""
        # 1. Roads from edge entries to a focal point
        self.generate_roads()
        
        # 2. Major buildings near center
        self.place_market()
        self.place_military_housing()
        
        # 3. Farms on outskirts with farmhouses
        self.place_farms_with_houses(self.num_farms)
        
        # 4. Village houses with optional gardens
        self.place_village_houses()
        
        # 5. Connect all buildings to road network
        self.connect_all_buildings()
        
        # 6. Scatter trees on remaining grass
        self.place_trees()
        
        # 7. Collect all data and return
        return self._build_output()
    
    def _build_output(self):
        """Build the JSON-serializable output structure."""
        # Collect road positions
        self.road_positions = list(self.road_cells)
        
        # Collect tree positions
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y, x] == TREE:
                    self.tree_positions.append((x, y))
        
        # Calculate effective village bounds from structures (not trees/grass/roads)
        # Include: buildings, farms, market
        # Exclude: roads (they extend to map edges as entry/exit paths)
        village_min_x, village_min_y = self.size, self.size
        village_max_x, village_max_y = 0, 0
        
        # Include all buildings
        for btype, bx, by, bw, bh in self.buildings:
            village_min_x = min(village_min_x, bx)
            village_min_y = min(village_min_y, by)
            village_max_x = max(village_max_x, bx + bw)
            village_max_y = max(village_max_y, by + bh)
        
        # Include all farm cells
        for farm_id, farm_cells in self.farm_cells_map.items():
            for fx, fy in farm_cells:
                village_min_x = min(village_min_x, fx)
                village_min_y = min(village_min_y, fy)
                village_max_x = max(village_max_x, fx + 1)
                village_max_y = max(village_max_y, fy + 1)
        
        # Include market/stall cells
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y, x] in [MARKET, STALL]:
                    village_min_x = min(village_min_x, x)
                    village_min_y = min(village_min_y, y)
                    village_max_x = max(village_max_x, x + 1)
                    village_max_y = max(village_max_y, y + 1)
        
        # Add a 2-cell margin around the effective bounds for the village territory
        village_margin = 2
        village_min_x = max(0, village_min_x - village_margin)
        village_min_y = max(0, village_min_y - village_margin)
        village_max_x = min(self.size, village_max_x + village_margin)
        village_max_y = min(self.size, village_max_y + village_margin)
        
        # Build areas list
        output_areas = []
        
        # Add the village itself as the top-level area with effective bounds
        output_areas.append({
            "name": self.name,
            "role": "village",
            "bounds": [village_min_y, village_min_x, village_max_y, village_max_x],
            "color": "#7CB068",  # Grass color
        })
        
        # Process buildings into areas
        house_counter = 0
        farmhouse_counter = 0
        
        for building in self.buildings:
            btype, bx, by, bw, bh = building
            bounds = [by, bx, by + bh, bx + bw]
            
            if btype == 'Market':
                # Get actual market bounds from grid
                market_cells = []
                for y in range(self.size):
                    for x in range(self.size):
                        if self.grid[y, x] in [MARKET, STALL]:
                            market_cells.append((x, y))
                
                if market_cells:
                    min_x = min(c[0] for c in market_cells)
                    max_x = max(c[0] for c in market_cells)
                    min_y = min(c[1] for c in market_cells)
                    max_y = max(c[1] for c in market_cells)
                    bounds = [min_y, min_x, max_y + 1, max_x + 1]
                
                output_areas.append({
                    "name": f"{self.name} Market",
                    "role": "market",
                    "allegiance": self.name,
                    "bounds": bounds,
                    "color": "#D4AA78",
                    "cells": market_cells,
                })
            
            elif btype == 'Military Housing':
                output_areas.append({
                    "name": f"{self.name} Military Housing",
                    "role": "military_housing",
                    "allegiance": self.name,
                    "bounds": bounds,
                    "color": "#6B6B7A",
                })
            
            elif btype == 'House':
                house_counter += 1
                output_areas.append({
                    "name": f"{self.name} House {house_counter}",
                    "role": "house",
                    "allegiance": self.name,
                    "bounds": bounds,
                    "color": "#C4813D",
                })
            
            elif btype == 'Farmhouse':
                farmhouse_counter += 1
                output_areas.append({
                    "name": f"{self.name} Farmhouse {farmhouse_counter}",
                    "role": "farmhouse",
                    "allegiance": self.name,
                    "bounds": bounds,
                    "color": "#C4813D",
                })
        
        # Add farms from farm_cells_map (independent of farmhouses)
        for farm_id, farm_cells in self.farm_cells_map.items():
            farm_number = int(farm_id.split('_')[1])
            
            if farm_cells:
                farm_min_x = min(c[0] for c in farm_cells)
                farm_max_x = max(c[0] for c in farm_cells)
                farm_min_y = min(c[1] for c in farm_cells)
                farm_max_y = max(c[1] for c in farm_cells)
                farm_bounds = [farm_min_y, farm_min_x, farm_max_y + 1, farm_max_x + 1]
            else:
                farm_bounds = [0, 0, 0, 0]
            
            output_areas.append({
                "name": f"{self.name} Farm {farm_number}",
                "role": "farm",
                "allegiance": self.name,
                "bounds": farm_bounds,
                "color": "#7CB068",
                "has_farm_cells": True,
                "farm_cells": farm_cells,
            })
        
        return {
            "seed": self.seed,
            "name": self.name,
            "size": self.size,
            "areas": output_areas,
            "roads": self.road_positions,
            "trees": self.tree_positions,
            "colors": {
                "grass": "#7CB068",
                "road": "#A89880",
                "tree": "#2D5A27",
                "house": "#C4813D",
                "farm": "#A4C26D",
                "market": "#D4AA78",
                "military_housing": "#6B6B7A",
            }
        }
    
    def is_clear(self, x, y, w, h, margin=1, allowed=None):
        if allowed is None:
            allowed = [GRASS]
        for cy in range(y - margin, y + h + margin):
            for cx in range(x - margin, x + w + margin):
                if cx < 0 or cy < 0 or cx >= self.size or cy >= self.size:
                    return False
                if self.grid[cy, cx] not in allowed:
                    return False
        return True
    
    def place(self, x, y, w, h, cell_type):
        for cy in range(y, y + h):
            for cx in range(x, x + w):
                if 0 <= cx < self.size and 0 <= cy < self.size:
                    self.grid[cy, cx] = cell_type
    
    def generate_roads(self):
        """Create roads from specified edge entry points to a focal point."""
        fx = self.size // 2 + random.randint(-8, 8)
        fy = self.size // 2 + random.randint(-8, 8)
        self.town_center = (fx, fy)
        
        plaza_r = random.randint(2, 3)
        for dy in range(-plaza_r, plaza_r + 1):
            for dx in range(-plaza_r, plaza_r + 1):
                px, py = fx + dx, fy + dy
                if 0 <= px < self.size and 0 <= py < self.size:
                    if abs(dx) + abs(dy) <= plaza_r + 1:
                        self.grid[py, px] = ROAD
                        self.road_cells.add((px, py))
        
        if not self.road_entries:
            return
        
        entry_points = []
        for direction in self.road_entries:
            if direction == 'north':
                entry_points.append((random.randint(10, self.size - 10), 0))
            elif direction == 'south':
                entry_points.append((random.randint(10, self.size - 10), self.size - 1))
            elif direction == 'west':
                entry_points.append((0, random.randint(10, self.size - 10)))
            elif direction == 'east':
                entry_points.append((self.size - 1, random.randint(10, self.size - 10)))
            elif direction == 'northeast':
                entry_points.append((self.size - 1, 0))
            elif direction == 'northwest':
                entry_points.append((0, 0))
            elif direction == 'southeast':
                entry_points.append((self.size - 1, self.size - 1))
            elif direction == 'southwest':
                entry_points.append((0, self.size - 1))
        
        for ex, ey in entry_points:
            self.draw_road(ex, ey, fx, fy)
    
    def draw_road(self, x1, y1, x2, y2):
        """Draw smooth road (2 cells thick) between two points using waypoints."""
        num_waypoints = random.randint(1, 3)
        points = [(x1, y1)]
        
        for i in range(num_waypoints):
            t = (i + 1) / (num_waypoints + 1)
            base_x = x1 + t * (x2 - x1)
            base_y = y1 + t * (y2 - y1)
            offset = random.randint(-6, 6)
            dx = x2 - x1
            dy = y2 - y1
            length = max(1, math.sqrt(dx*dx + dy*dy))
            perp_x = -dy / length
            perp_y = dx / length
            wp_x = int(base_x + offset * perp_x)
            wp_y = int(base_y + offset * perp_y)
            wp_x = max(2, min(self.size - 3, wp_x))
            wp_y = max(2, min(self.size - 3, wp_y))
            points.append((wp_x, wp_y))
        
        points.append((x2, y2))
        
        for i in range(len(points) - 1):
            self.draw_smooth_segment(points[i][0], points[i][1], 
                                     points[i+1][0], points[i+1][1])
    
    def draw_smooth_segment(self, x1, y1, x2, y2):
        """Draw a smooth 2-cell wide road segment."""
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        x, y = x1, y1
        
        while True:
            for ox in range(2):
                for oy in range(2):
                    px, py = x + ox, y + oy
                    if 0 <= px < self.size and 0 <= py < self.size:
                        self.grid[py, px] = ROAD
                        self.road_cells.add((px, py))
            
            if x == x2 and y == y2:
                break
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
    
    def distance_to_center(self, x, y):
        cx, cy = self.town_center
        return math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    
    def find_nearest_road(self, x, y):
        """Find nearest road cell to a point."""
        nearest = None
        nearest_dist = float('inf')
        for rx, ry in self.road_cells:
            d = abs(rx - x) + abs(ry - y)
            if d < nearest_dist:
                nearest_dist = d
                nearest = (rx, ry)
        return nearest, nearest_dist
    
    def place_market(self):
        """Place a large organic market area near center."""
        cx, cy = self.town_center
        target_size = random.randint(35, 55)
        
        for _ in range(80):
            sx = cx + random.randint(-8, 8)
            sy = cy + random.randint(-8, 8)
            if 5 <= sx < self.size - 5 and 5 <= sy < self.size - 5:
                if self.grid[sy, sx] in [GRASS, ROAD]:
                    break
        else:
            return
        
        cells = set()
        frontier = [(sx, sy)]
        
        while len(cells) < target_size and frontier:
            idx = random.randint(0, len(frontier) - 1)
            x, y = frontier.pop(idx)
            
            if (x, y) in cells:
                continue
            if not (3 <= x < self.size - 3 and 3 <= y < self.size - 3):
                continue
            if self.grid[y, x] not in [GRASS, ROAD]:
                continue
            
            cells.add((x, y))
            self.grid[y, x] = MARKET
            
            neighbors = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
            random.shuffle(neighbors)
            for nx, ny in neighbors:
                if random.random() < 0.75:
                    frontier.append((nx, ny))
        
        if len(cells) < 20:
            for x, y in cells:
                self.grid[y, x] = GRASS
            return
        
        self.buildings.append(('Market', sx, sy, 1, 1))
    
    def place_military_housing(self):
        cx, cy = self.town_center
        w, h = 6, 5
        
        best_pos = None
        best_dist = 0
        
        for _ in range(100):
            x = random.randint(4, self.size - w - 4)
            y = random.randint(4, self.size - h - 4)
            if self.is_clear(x, y, w, h, margin=1):
                dist = self.distance_to_center(x, y)
                if 10 < dist < 22 and dist > best_dist:
                    best_dist = dist
                    best_pos = (x, y)
        
        if best_pos:
            x, y = best_pos
            self.place(x, y, w, h, MILITARY_HOUSING)
            self.buildings.append(('Military Housing', x, y, w, h))
    
    def place_farms_with_houses(self, num_farms):
        """Place farms on outskirts, each with farmhouse."""
        farms_placed = 0
        
        for _ in range(num_farms * 40):
            if farms_placed >= num_farms:
                break
            
            for _ in range(50):
                x = random.randint(3, self.size - 10)
                y = random.randint(3, self.size - 10)
                
                dist = self.distance_to_center(x, y)
                min_farm_dist = self.size * 0.3  # Scale with map size
                if dist > min_farm_dist and self.grid[y, x] == GRASS:
                    target_size = random.randint(40, 85)
                    farm_cells = self.grow_farm(x, y, target_size)
                    
                    if farm_cells and len(farm_cells) >= 35:
                        if len(farm_cells) > 55:
                            self.add_fence_with_opening(farm_cells)
                        
                        # Store farm cells immediately when farm is created
                        farm_number = farms_placed + 1
                        farm_id = f"farm_{farm_number}"
                        self.farm_cells_map[farm_id] = [(cx, cy) for cx, cy in farm_cells]
                        
                        # Try to place farmhouse, but farm exists regardless
                        self.place_farmhouse_near_farm(farm_cells, farm_number)
                        farms_placed += 1
                        break
        
        return farms_placed
    
    def grow_farm(self, sx, sy, target):
        """Grow organic farm shape."""
        if self.grid[sy, sx] != GRASS:
            return None
        
        cells = set()
        frontier = [(sx, sy)]
        
        bias_dx = random.choice([-1, 0, 0, 1])
        bias_dy = random.choice([-1, 0, 0, 1])
        
        while len(cells) < target and frontier:
            idx = random.randint(0, len(frontier) - 1)
            x, y = frontier.pop(idx)
            
            if (x, y) in cells:
                continue
            if not (2 <= x < self.size - 2 and 2 <= y < self.size - 2):
                continue
            if self.grid[y, x] != GRASS:
                continue
            
            cells.add((x, y))
            self.grid[y, x] = FARM
            
            neighbors = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
            if bias_dx or bias_dy:
                neighbors.append((x + bias_dx, y + bias_dy))
            
            random.shuffle(neighbors)
            for nx, ny in neighbors:
                if random.random() < 0.72:
                    frontier.append((nx, ny))
        
        return cells if len(cells) >= target * 0.6 else None
    
    def add_fence_with_opening(self, cells):
        """Add fence perimeter around farm with openings."""
        border_cells = set()
        for x, y in cells:
            for nx, ny in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.grid[ny, nx] == GRASS and (nx, ny) not in cells:
                        border_cells.add((nx, ny))
        
        if not border_cells:
            return
        
        opening_candidates = []
        for bx, by in border_cells:
            for nx, ny in [(bx-1, by), (bx+1, by), (bx, by-1), (bx, by+1)]:
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.grid[ny, nx] == ROAD:
                        opening_candidates.append((bx, by))
                        break
        
        openings = set()
        if opening_candidates:
            openings.add(random.choice(opening_candidates))
            if len(opening_candidates) > 3 and random.random() < 0.3:
                first = list(openings)[0]
                candidates = [(c, abs(c[0]-first[0]) + abs(c[1]-first[1])) for c in opening_candidates if c != first]
                if candidates:
                    candidates.sort(key=lambda x: -x[1])
                    openings.add(candidates[0][0])
        else:
            openings.add(random.choice(list(border_cells)))
        
        for fx, fy in border_cells:
            if (fx, fy) not in openings:
                self.grid[fy, fx] = FENCE
    
    def place_farmhouse_near_farm(self, farm_cells, farm_number):
        """Place farmhouse adjacent to farm."""
        w, h = 5, 4
        
        adjacent_cells = set()
        for fx, fy in farm_cells:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    nx, ny = fx + dx, fy + dy
                    if (nx, ny) not in farm_cells:
                        adjacent_cells.add((nx, ny))
        
        positions = []
        for ax, ay in adjacent_cells:
            for ox in range(-w + 1, 1):
                for oy in range(-h + 1, 1):
                    px, py = ax + ox, ay + oy
                    positions.append((px, py))
        
        random.shuffle(positions)
        
        for x, y in positions:
            if 2 <= x <= self.size - w - 2 and 2 <= y <= self.size - h - 2:
                if self.is_clear(x, y, w, h, margin=0):
                    is_adjacent = False
                    for hx in range(x, x + w):
                        for hy in range(y, y + h):
                            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (1,-1), (-1,1), (1,1)]:
                                nx, ny = hx + dx, hy + dy
                                if (nx, ny) in farm_cells:
                                    is_adjacent = True
                                    break
                            if is_adjacent:
                                break
                        if is_adjacent:
                            break
                    
                    crosses_road = False
                    for hx in range(x - 1, x + w + 1):
                        for hy in range(y - 1, y + h + 1):
                            if 0 <= hx < self.size and 0 <= hy < self.size:
                                if self.grid[hy, hx] == ROAD:
                                    crosses_road = True
                                    break
                        if crosses_road:
                            break
                    
                    if is_adjacent and not crosses_road:
                        self.place(x, y, w, h, FARMHOUSE)
                        self.buildings.append(('Farmhouse', x, y, w, h))
                        return True
        return False
    
    def place_village_houses(self):
        """Place houses with higher density near town center."""
        house_sizes = [(4, 3), (5, 4), (5, 4), (6, 5), (7, 6)]
        
        existing = sum(1 for b in self.buildings if b[0] == 'House')
        target = self.num_houses
        houses_placed = existing
        
        cx, cy = self.town_center
        road_list = list(self.road_cells)
        road_list.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        
        for rx, ry in road_list:
            if houses_placed >= target:
                break
            
            dist_to_center = math.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)
            if dist_to_center > 15 and houses_placed < target - 2:
                continue
            
            w, h = random.choice(house_sizes)
            has_garden = random.random() < 0.3
            
            offsets = [
                (0, -h - 1),
                (0, 2),
                (-w - 1, 0),
                (2, 0),
            ]
            random.shuffle(offsets)
            
            for ox, oy in offsets:
                hx = rx + ox
                hy = ry + oy
                
                if has_garden and random.random() < 0.5:
                    garden_margin = 1
                    total_w = w + garden_margin * 2
                    total_h = h + garden_margin * 2
                    gx = hx - garden_margin
                    gy = hy - garden_margin
                    
                    if 2 <= gx <= self.size - total_w - 2 and 2 <= gy <= self.size - total_h - 2:
                        if self.is_clear(gx, gy, total_w, total_h, margin=1):
                            self.place(gx, gy, total_w, total_h, GARDEN)
                            self.place(hx, hy, w, h, HOUSE)
                            self.add_property_fence(gx, gy, total_w, total_h)
                            self.buildings.append(('House', hx, hy, w, h))
                            houses_placed += 1
                            break
                else:
                    if 2 <= hx <= self.size - w - 2 and 2 <= hy <= self.size - h - 2:
                        if self.is_clear(hx, hy, w, h, margin=1):
                            self.place(hx, hy, w, h, HOUSE)
                            self.buildings.append(('House', hx, hy, w, h))
                            houses_placed += 1
                            break
        
        attempts = 0
        while houses_placed < target and attempts < 600:
            attempts += 1
            w, h = random.choice(house_sizes)
            
            spread = 10
            x = int(cx + random.gauss(0, spread))
            y = int(cy + random.gauss(0, spread))
            x = max(3, min(self.size - w - 3, x))
            y = max(3, min(self.size - h - 3, y))
            
            if self.is_clear(x, y, w, h, margin=1):
                self.place(x, y, w, h, HOUSE)
                self.buildings.append(('House', x, y, w, h))
                houses_placed += 1
    
    def add_property_fence(self, x, y, w, h):
        """Add fence around property with openings."""
        edge_cells = []
        
        for fx in range(x, x + w):
            if self.grid[y, fx] == GARDEN:
                edge_cells.append((fx, y))
            if self.grid[y + h - 1, fx] == GARDEN:
                edge_cells.append((fx, y + h - 1))
        
        for fy in range(y + 1, y + h - 1):
            if self.grid[fy, x] == GARDEN:
                edge_cells.append((x, fy))
            if self.grid[fy, x + w - 1] == GARDEN:
                edge_cells.append((x + w - 1, fy))
        
        opening_candidates = []
        for ex, ey in edge_cells:
            for nx, ny in [(ex-1, ey), (ex+1, ey), (ex, ey-1), (ex, ey+1)]:
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.grid[ny, nx] == ROAD:
                        opening_candidates.append((ex, ey))
                        break
        
        openings = set()
        if opening_candidates:
            openings.add(random.choice(opening_candidates))
            if len(opening_candidates) > 2 and random.random() < 0.25:
                openings.add(random.choice(opening_candidates))
        else:
            south_edge = [(fx, y + h - 1) for fx in range(x, x + w) if self.grid[y + h - 1, fx] == GARDEN]
            if south_edge:
                openings.add(south_edge[len(south_edge) // 2])
        
        for ex, ey in edge_cells:
            if (ex, ey) not in openings:
                self.grid[ey, ex] = FENCE
    
    def connect_all_buildings(self):
        """Connect every building to the road network."""
        for name, bx, by, bw, bh in self.buildings:
            start_x = bx + bw // 2
            start_y = by + bh
            
            nearest, dist = self.find_nearest_road(start_x, start_y)
            
            if nearest and dist > 0:
                self.draw_connection(start_x, start_y, nearest[0], nearest[1])
        
        self.ensure_full_connectivity()
    
    def ensure_full_connectivity(self):
        """Ensure all houses can reach each other via roads/market."""
        passable = set()
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y, x] in [ROAD, MARKET, STALL]:
                    passable.add((x, y))
        
        if not passable:
            return
        
        main_component = self.flood_fill_passable(self.town_center[0], self.town_center[1], passable)
        
        for name, bx, by, bw, bh in self.buildings:
            if name not in ['House', 'Farmhouse']:
                continue
            
            connected = False
            for x in range(bx - 1, bx + bw + 1):
                for y in range(by - 1, by + bh + 1):
                    if (x, y) in main_component:
                        connected = True
                        break
                if connected:
                    break
            
            if not connected:
                exit_x, exit_y = bx + bw // 2, by + bh
                
                closest = None
                closest_dist = float('inf')
                for px, py in main_component:
                    d = abs(px - exit_x) + abs(py - exit_y)
                    if d < closest_dist:
                        closest_dist = d
                        closest = (px, py)
                
                if closest:
                    self.draw_connection(exit_x, exit_y, closest[0], closest[1])
                    
                    for y in range(self.size):
                        for x in range(self.size):
                            if self.grid[y, x] in [ROAD, MARKET, STALL]:
                                main_component.add((x, y))
    
    def flood_fill_passable(self, start_x, start_y, passable):
        """BFS flood fill to find all connected passable cells."""
        nearest = None
        min_dist = float('inf')
        for px, py in passable:
            d = abs(px - start_x) + abs(py - start_y)
            if d < min_dist:
                min_dist = d
                nearest = (px, py)
        
        if nearest is None:
            return set()
        
        visited = set()
        queue = [nearest]
        visited.add(nearest)
        
        while queue:
            x, y = queue.pop(0)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) in passable and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        
        return visited
    
    def draw_connection(self, x1, y1, x2, y2):
        """Draw smooth road connection between two points."""
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        x, y = x1, y1
        
        while True:
            for ox in range(2):
                for oy in range(2):
                    px, py = x + ox, y + oy
                    if 0 <= px < self.size and 0 <= py < self.size:
                        if self.grid[py, px] in [GRASS, GARDEN]:
                            self.grid[py, px] = ROAD
                            self.road_cells.add((px, py))
                        elif self.grid[py, px] in [ROAD, MARKET, STALL]:
                            self.road_cells.add((px, py))
            
            if x == x2 and y == y2:
                break
            
            if (x, y) in self.road_cells and abs(x - x2) <= 1 and abs(y - y2) <= 1:
                break
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
            
            if not (0 <= x < self.size - 1 and 0 <= y < self.size - 1):
                break
    
    def place_trees(self):
        """Scatter trees realistically on grass."""
        if self.tree_density <= 0:
            return
        
        cx, cy = self.town_center
        
        grass_count = np.sum(self.grid == GRASS)
        target_trees = int(grass_count * self.tree_density)
        
        trees_placed = 0
        attempts = 0
        max_attempts = target_trees * 10
        
        while trees_placed < target_trees and attempts < max_attempts:
            attempts += 1
            
            x = random.randint(1, self.size - 2)
            y = random.randint(1, self.size - 2)
            
            if self.grid[y, x] != GRASS:
                continue
            
            dist_to_center = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            max_dist = self.size * 0.7
            edge_factor = min(1.0, dist_to_center / max_dist)
            
            prob = 0.3 + 0.5 * edge_factor
            
            adjacent_trees = 0
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.grid[ny, nx] == TREE:
                        adjacent_trees += 1
            
            if adjacent_trees > 0:
                prob += 0.3 * adjacent_trees
            
            if adjacent_trees >= 3:
                prob *= 0.2
            
            if random.random() < prob:
                self.grid[y, x] = TREE
                trees_placed += 1


def generate_areas(size, houses, farms, seed, name, trees):
    """Generate town areas and return structured data."""
    generator = TownGenerator(
        name=name,
        size=size,
        seed=seed,
        num_houses=houses,
        num_farms=farms,
        tree_density=trees
    )
    
    data = generator.generate()
    
    return {"name": name, "size": size, "areas": data["areas"]}


if __name__ == "__main__":
    print(json.dumps(generate_areas(25, 0, 1, seed=2, name="Dunmere", trees=0.0), indent=2))