#!/usr/bin/env python3
import argparse
import json
import matplotlib.pyplot as plt
import numpy as np

from town_gen import TownGenerator


def render_town(data, filename='town.png'):
    """Render the town image from JSON data."""
    size = data['size']
    colors = data['colors']
    
    # Create RGB grid, starting with grass
    grass_color = colors['grass']
    rgb = np.zeros((size, size, 3))
    for y in range(size):
        for x in range(size):
            rgb[y, x] = hex_to_rgb(grass_color)
    
    # Draw farms first (so other things draw on top)
    for area in data['areas']:
        if area['role'] == 'farm' and area.get('has_farm_cells'):
            for x, y in area['farm_cells']:
                if 0 <= x < size and 0 <= y < size:
                    rgb[y, x] = hex_to_rgb(area['color'])
    
    # Draw roads
    road_color = hex_to_rgb(colors['road'])
    for x, y in data['roads']:
        if 0 <= x < size and 0 <= y < size:
            rgb[y, x] = road_color
    
    # Draw market cells
    for area in data['areas']:
        if area['role'] == 'market' and 'cells' in area:
            for x, y in area['cells']:
                if 0 <= x < size and 0 <= y < size:
                    rgb[y, x] = hex_to_rgb(area['color'])
    
    # Draw buildings (houses, farmhouses, military_housing)
    for area in data['areas']:
        if area['role'] in ['house', 'farmhouse', 'military_housing']:
            y_start, x_start, y_end, x_end = area['bounds']
            color = hex_to_rgb(area['color'])
            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    if 0 <= x < size and 0 <= y < size:
                        rgb[y, x] = color
    
    # Draw trees last
    tree_color = hex_to_rgb(colors['tree'])
    for x, y in data['trees']:
        if 0 <= x < size and 0 <= y < size:
            rgb[y, x] = tree_color
    
    # Create figure
    fig, ax = plt.subplots(figsize=(12, 12))
    ax.imshow(rgb)
    ax.set_xticks(np.arange(-0.5, size, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, size, 1), minor=True)
    ax.grid(which='minor', color='#555', linewidth=0.2, alpha=0.3)
    
    # Title
    ax.set_title(f"{data['name']} (seed: {data['seed']})")
    
    # Build legend - fixed order
    legend_items = [
        ('Road', colors['road']),
        ('Tree', colors['tree']),
    ]
    
    # Check what areas exist and add in consistent order
    name = data['name']
    roles_present = set(area['role'] for area in data['areas'])
    
    if 'house' in roles_present or 'farmhouse' in roles_present:
        legend_items.append((f'{name} House', colors['house']))
    if 'farm' in roles_present:
        legend_items.append((f'{name} Farm', colors['farm']))
    if 'market' in roles_present:
        legend_items.append((f'{name} Market', colors['market']))
    if 'military_housing' in roles_present:
        legend_items.append((f'{name} Military Housing', colors['military_housing']))
    
    # Draw legend
    for i, (label, color) in enumerate(legend_items):
        ax.add_patch(plt.Rectangle((size + 2, i * 3), 2, 2, color=color))
        ax.text(size + 5, i * 3 + 1, label, va='center', fontsize=8)
    
    ax.set_xlim(-1, size + 20)
    ax.set_ylim(size, -1)
    
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple (0-1 range)."""
    return [int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5)]


def main():
    parser = argparse.ArgumentParser(description='Generate a procedural town map')
    
    # Road entry arguments
    parser.add_argument('--nroad', action='store_true', help='Road enters from north')
    parser.add_argument('--sroad', action='store_true', help='Road enters from south')
    parser.add_argument('--eroad', action='store_true', help='Road enters from east')
    parser.add_argument('--wroad', action='store_true', help='Road enters from west')
    parser.add_argument('--neroad', action='store_true', help='Road enters from northeast')
    parser.add_argument('--nwroad', action='store_true', help='Road enters from northwest')
    parser.add_argument('--seroad', action='store_true', help='Road enters from southeast')
    parser.add_argument('--swroad', action='store_true', help='Road enters from southwest')
    
    # Generation parameters
    parser.add_argument('--seed', type=int, default=None, help='Random seed for generation')
    parser.add_argument('--size', type=int, default=50, help='Size of the map grid')
    parser.add_argument('--houses', type=int, default=12, help='Number of regular houses (not farmhouses)')
    parser.add_argument('--farms', type=int, default=3, help='Number of farms (each with a farmhouse)')
    parser.add_argument('--name', type=str, default=None, help='Town name')
    parser.add_argument('--trees', type=float, default=0.08, help='Tree density (0.0-1.0)')
    
    # Output options
    parser.add_argument('--output', type=str, default='town.png', help='Output image filename')
    parser.add_argument('--json', action='store_true', help='Also output JSON data')
    
    args = parser.parse_args()
    
    # Collect road entries
    road_entries = []
    if args.nroad:
        road_entries.append('north')
    if args.sroad:
        road_entries.append('south')
    if args.eroad:
        road_entries.append('east')
    if args.wroad:
        road_entries.append('west')
    if args.neroad:
        road_entries.append('northeast')
    if args.nwroad:
        road_entries.append('northwest')
    if args.seroad:
        road_entries.append('southeast')
    if args.swroad:
        road_entries.append('southwest')
    
    # Create generator and generate town
    generator = TownGenerator(
        size=args.size,
        seed=args.seed,
        road_entries=road_entries,
        num_houses=args.houses,
        num_farms=args.farms,
        name=args.name,
        tree_density=args.trees
    )
    
    # Generate and get data
    data = generator.generate()
    
    # Output JSON if requested
    if args.json:
        json_filename = args.output.rsplit('.', 1)[0] + '.json'
        with open(json_filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"JSON saved to: {json_filename}")
    
    # Render image
    render_town(data, args.output)
    
    # Print stats
    houses = sum(1 for a in data['areas'] if a['role'] == 'house')
    farmhouses = sum(1 for a in data['areas'] if a['role'] == 'farmhouse')
    farms = sum(1 for a in data['areas'] if a['role'] == 'farm')
    trees = len(data['trees'])
    
    print(f"Seed: {data['seed']} | Houses: {houses}, Farmhouses: {farmhouses}, Farms: {farms}, Trees: {trees}")
    print(f"Image saved to: {args.output}")


if __name__ == "__main__":
    main()
