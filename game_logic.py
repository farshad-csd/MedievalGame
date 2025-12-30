# game_logic.py - All game logic: AI, combat, trading, movement
"""
This module contains all game logic that operates on GameState.
It does NOT hold any state itself - all state is in GameState.
It does NOT contain any rendering code.
"""

import random
import math
from collections import deque
from constants import (
    SIZE, DIRECTIONS,
    MAX_HUNGER, HUNGER_DECAY, HUNGER_CRITICAL, HUNGER_CHANCE_THRESHOLD,
    STARVATION_THRESHOLD, STARVATION_DAMAGE, STARVATION_MORALITY_INTERVAL, 
    STARVATION_MORALITY_CHANCE, STARVATION_FREEZE_HEALTH,
    INVENTORY_SLOTS, WHEAT_STACK_SIZE,
    WHEAT_PER_BITE, HUNGER_PER_WHEAT, WHEAT_BUFFER_TARGET, FARM_CELL_YIELD,
    FARM_CELL_HARVEST_INTERVAL, FARM_HARVEST_TIME, FARM_REPLANT_TIME,
    WHEAT_PRICE_PER_UNIT, FARMER_PERSONAL_RESERVE, TRADE_COOLDOWN,
    STEWARD_TAX_INTERVAL, STEWARD_TAX_AMOUNT, SOLDIER_WHEAT_PAYMENT, TAX_GRACE_PERIOD,
    ALLEGIANCE_WHEAT_TIMEOUT, TICKS_PER_DAY, TICKS_PER_YEAR,
    CRIME_INTENSITY_MURDER, CRIME_INTENSITY_THEFT,
    SLEEP_START_FRACTION, PRIMARY_ALLEGIANCE,
    MOVEMENT_SPEED, SPRINT_SPEED, ADJACENCY_DISTANCE, COMBAT_RANGE,
    CHARACTER_WIDTH, CHARACTER_HEIGHT, CHARACTER_COLLISION_RADIUS,
    UPDATE_INTERVAL, TICK_MULTIPLIER,
    VENDOR_GOODS, GOODS_PRICES, GOODS_STACK_SIZES, VENDOR_PERSONAL_RESERVE,
    IDLE_SPEED_MULTIPLIER, IDLE_MIN_WAIT_TICKS, IDLE_MAX_WAIT_TICKS,
    IDLE_PAUSE_CHANCE, IDLE_PAUSE_MIN_TICKS, IDLE_PAUSE_MAX_TICKS,
    SQUEEZE_THRESHOLD_TICKS, SQUEEZE_SLIDE_SPEED,
    ATTACK_ANIMATION_DURATION
)
from scenario_characters import CHARACTER_TEMPLATES


class GameLogic:
    """
    Contains all game logic that operates on a GameState instance.
    
    This class:
    - Takes a GameState and modifies it
    - Contains all AI decision making
    - Contains all combat, trading, movement logic
    - Does NOT hold persistent state (that's in GameState)
    - Does NOT contain rendering code (that's in gui.py)
    """
    
    def __init__(self, state):
        """
        Args:
            state: GameState instance to operate on
        """
        self.state = state
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def get_display_name(self, char):
        """Get a short display name for logging (first name only)"""
        return char['name'].split()[0]
    
    def is_player(self, char):
        """Check if a character is player-controlled"""
        template = CHARACTER_TEMPLATES.get(char['name'], {})
        return template.get('is_player', False)
    
    def get_trait(self, char, trait_name):
        """Get a trait value for a character. Morality is mutable, others are static."""
        # Morality is stored on the character and can change
        if trait_name == 'morality':
            return char.get('morality', 5)
        # Other traits are static from template
        template = CHARACTER_TEMPLATES.get(char['name'], {})
        return template.get(trait_name, 0)
    
    def is_adjacent(self, char1, char2):
        """Check if two characters are adjacent (close enough to interact).
        Uses float-based Euclidean distance with ADJACENCY_DISTANCE threshold.
        """
        dist = math.sqrt((char1['x'] - char2['x']) ** 2 + (char1['y'] - char2['y']) ** 2)
        return dist <= ADJACENCY_DISTANCE and dist > 0  # Must be close but not same position
    
    def is_in_combat_range(self, char1, char2):
        """Check if two characters are close enough to attack each other.
        Uses COMBAT_RANGE which is tighter than ADJACENCY_DISTANCE.
        """
        dist = math.sqrt((char1['x'] - char2['x']) ** 2 + (char1['y'] - char2['y']) ** 2)
        return dist <= COMBAT_RANGE
    
    def get_adjacent_character(self, char):
        """Get any character adjacent to the given character (within ADJACENCY_DISTANCE)"""
        for other in self.state.characters:
            if other != char and self.is_adjacent(char, other):
                return other
        return None
    
    def get_distance(self, char1, char2):
        """Euclidean distance between two characters (float-based)."""
        return math.sqrt((char1['x'] - char2['x']) ** 2 + (char1['y'] - char2['y']) ** 2)
    
    def _update_facing(self, char, dx, dy):
        """Update character's facing direction based on movement delta"""
        if dx > 0 and dy < 0:
            char['facing'] = 'up-right'
        elif dx > 0 and dy > 0:
            char['facing'] = 'down-right'
        elif dx < 0 and dy < 0:
            char['facing'] = 'up-left'
        elif dx < 0 and dy > 0:
            char['facing'] = 'down-left'
        elif dx > 0:
            char['facing'] = 'right'
        elif dx < 0:
            char['facing'] = 'left'
        elif dy > 0:
            char['facing'] = 'down'
        elif dy < 0:
            char['facing'] = 'up'
    
    # =========================================================================
    # SLEEP HELPERS
    # =========================================================================
    
    def is_sleep_time(self):
        """Check if it's currently sleep time (latter 1/3 of day)"""
        day_tick = self.state.ticks % TICKS_PER_DAY
        return day_tick >= TICKS_PER_DAY * SLEEP_START_FRACTION
    
    def get_character_bed(self, char):
        """Get the bed owned by this character, if any"""
        return self.state.get_bed_by_owner(char['name'])
    
    def get_sleep_position(self, char):
        """Get the position where this character should sleep.
        Returns bed position if they own one, camp position if they have one, None otherwise.
        """
        # Check for owned bed
        bed = self.get_character_bed(char)
        if bed:
            return self.state.get_bed_position(bed)
        
        # Check for existing camp
        if char.get('camp_position'):
            return char['camp_position']
        
        return None
    
    def can_make_camp_at(self, x, y):
        """Check if a camp can be made at this position.
        Works with float positions - checks the cell containing the point.
        Cannot make camp on village grounds or on any farm.
        """
        cell_x = int(x)
        cell_y = int(y)
        if not self.state.is_position_valid(cell_x, cell_y):
            return False
        # Cannot camp in village areas
        if self.state.is_in_village(cell_x, cell_y):
            return False
        # Cannot camp on farm cells
        if (cell_x, cell_y) in self.state.farm_cells:
            return False
        return True
    
    def make_camp(self, char):
        """Make a camp at the character's current position if possible.
        Returns True if camp was made. Stores camp position as cell coordinates.
        """
        # Get the cell the character is in
        cell_x = int(char['x'])
        cell_y = int(char['y'])
        if self.can_make_camp_at(cell_x, cell_y):
            char['camp_position'] = (cell_x, cell_y)
            name = self.get_display_name(char)
            self.state.log_action(f"{name} made a camp at ({cell_x}, {cell_y})")
            return True
        return False

    # =========================================================================
    # INVENTORY HELPERS (convenience wrappers around state methods)
    # =========================================================================
    
    def get_wheat(self, char):
        """Get total wheat from character's inventory."""
        return self.state.get_wheat(char)
    
    def get_money(self, char):
        """Get total money from character's inventory."""
        return self.state.get_money(char)
    
    def add_wheat(self, char, amount):
        """Add wheat to character's inventory."""
        return self.state.add_wheat(char, amount)
    
    def remove_wheat(self, char, amount):
        """Remove wheat from character's inventory."""
        return self.state.remove_wheat(char, amount)
    
    def add_money(self, char, amount):
        """Add money to character's inventory."""
        return self.state.add_money(char, amount)
    
    def remove_money(self, char, amount):
        """Remove money from character's inventory."""
        return self.state.remove_money(char, amount)
    
    def can_add_wheat(self, char, amount=1):
        """Check if character can add wheat to inventory."""
        return self.state.can_add_wheat(char, amount)
    
    def can_add_money(self, char):
        """Check if character can add money to inventory."""
        return self.state.can_add_money(char)
    
    def has_money_slot(self, char):
        """Check if character has a money slot."""
        return self.state.has_money_slot(char)
    
    def is_inventory_full(self, char):
        """Check if inventory is full."""
        return self.state.is_inventory_full(char)
    
    # =========================================================================
    # STEWARD / TAX SYSTEM
    # =========================================================================
    
    def get_steward(self):
        """Get the steward character"""
        for char in self.state.characters:
            if char.get('job') == 'Steward':
                return char
        return None
    
    def steward_has_wheat(self):
        """Check if barracks barrel has wheat to pay soldiers"""
        barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
        return barracks_barrel is not None and self.state.get_barrel_wheat(barracks_barrel) > 0
    
    def get_village_allegiance_count(self):
        """Count all characters with VILLAGE allegiance"""
        return sum(1 for c in self.state.characters if c.get('allegiance') == PRIMARY_ALLEGIANCE)
    
    def get_steward_wheat_target(self):
        """Calculate how much wheat steward wants to stockpile.
        Target: enough to feed all villagers for 2 days.
        (~3 wheat per person per day to maintain hunger)
        """
        village_mouths = self.get_village_allegiance_count()
        wheat_per_person_per_day = 3
        days_to_stockpile = 2
        return village_mouths * wheat_per_person_per_day * days_to_stockpile
    
    def steward_needs_to_buy_wheat(self, steward):
        """Check if barracks barrel wheat supply is below target"""
        target = self.get_steward_wheat_target()
        barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
        if not barracks_barrel:
            return True
        return self.state.get_barrel_wheat(barracks_barrel) < target
    
    def collect_steward_tax(self):
        """Called every tax interval - resets tax cycle for farmers who paid"""
        steward = self.get_steward()
        if not steward:
            return
        
        farmers = [c for c in self.state.characters 
                   if c.get('job') == 'Farmer' and c.get('allegiance') == PRIMARY_ALLEGIANCE]
        
        for farmer in farmers:
            if farmer.get('tax_paid_this_cycle', False):
                farmer['tax_paid_this_cycle'] = False
                farmer['tax_late_ticks'] = 0
            else:
                if farmer.get('tax_late_ticks', 0) == 0:
                    farmer['tax_late_ticks'] = 1
                    self.state.log_action(f"F not present to pay tax! Late: 1 tick")
    
    # =========================================================================
    # TRADING SYSTEM
    # =========================================================================
    
    def find_adjacent_farmer(self, char):
        """Find a farmer adjacent to this character (within ADJACENCY_DISTANCE)"""
        for other in self.state.characters:
            if other != char and other.get('job') == 'Farmer':
                if self.is_adjacent(char, other):
                    return other
        return None
    
    def find_nearest_farmer(self, char):
        """Find the nearest farmer"""
        best_farmer = None
        best_dist = float('inf')
        
        for other in self.state.characters:
            if other.get('job') == 'Farmer':
                dist = self.get_distance(char, other)
                if dist < best_dist:
                    best_dist = dist
                    best_farmer = other
        
        return best_farmer
    
    def find_willing_farmer(self, char):
        """Find the nearest farmer who is willing to trade with this character"""
        best_farmer = None
        best_dist = float('inf')
        
        for other in self.state.characters:
            if other.get('job') == 'Farmer':
                if self.farmer_willing_to_trade(other, char):
                    dist = self.get_distance(char, other)
                    if dist < best_dist:
                        best_dist = dist
                        best_farmer = other
        
        return best_farmer
    
    def any_valid_wheat_seller_exists(self, char):
        """Check if any farmer exists who could potentially sell to this character"""
        char_allegiance = char.get('allegiance')
        
        for other in self.state.characters:
            if other.get('job') == 'Farmer':
                farmer_allegiance = other.get('allegiance')
                if char_allegiance is None or farmer_allegiance is None:
                    return True
                if char_allegiance == farmer_allegiance:
                    return True
        return False
    
    def get_farmer_expected_production(self, farmer):
        """Estimate how much wheat the farmer can produce before tax is due."""
        # No tax obligation in year 1 - can sell freely
        if self.state.ticks < STEWARD_TAX_INTERVAL:
            return float('inf')
        
        # If already paid tax this cycle, no constraint
        if farmer.get('tax_paid_this_cycle', False):
            return float('inf')
        
        # Only VILLAGE allegiance farmers owe tax
        if farmer.get('allegiance') != PRIMARY_ALLEGIANCE:
            return float('inf')
        
        # Calculate time until tax is due
        ticks_into_cycle = self.state.ticks % STEWARD_TAX_INTERVAL
        ticks_until_tax = STEWARD_TAX_INTERVAL - ticks_into_cycle
        
        # Estimate wheat production capacity
        # Farmer works half the day, farm cells yield 1 wheat per harvest cycle
        # Rough estimate: 1 wheat per farm cell per day when working
        num_farm_cells = len(self.state.farm_cells)
        days_until_tax = ticks_until_tax / TICKS_PER_DAY
        # Farmer works half day, so halve production estimate
        expected_production = (num_farm_cells * days_until_tax) / 2
        
        return expected_production
    
    def get_farmer_sellable_wheat(self, farmer):
        """Calculate how much wheat the farmer can sell while staying on track for taxes.
        
        Logic: sellable = current_wheat + expected_future_production - tax_target
        Where tax_target includes a buffer for interruptions.
        """
        # Get current wheat (inventory + barrel)
        farmer_wheat = self.get_wheat(farmer)
        farm_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('farm'))
        barrel_wheat = self.state.get_barrel_wheat(farm_barrel) if farm_barrel else 0
        current_wheat = farmer_wheat + barrel_wheat
        
        expected_production = self.get_farmer_expected_production(farmer)
        
        # No tax constraint - can sell anything above personal reserve
        if expected_production == float('inf'):
            return max(0, current_wheat - FARMER_PERSONAL_RESERVE)
        
        # Tax target with buffer for interruptions (1.5x tax amount)
        tax_target = STEWARD_TAX_AMOUNT * 1.5
        
        # Sellable = what we have + what we'll produce - what we need
        sellable = current_wheat + expected_production - tax_target
        
        # Also keep personal reserve for eating
        sellable = min(sellable, current_wheat - FARMER_PERSONAL_RESERVE)
        
        return max(0, sellable)
    
    def farmer_willing_to_trade(self, farmer, buyer, amount=None):
        """Check if farmer is willing to trade with this buyer.
        If amount is None, checks if farmer can sell at least 1 wheat.
        If amount is specified, checks if farmer can sell that exact amount.
        """
        # Check buyer's trade cooldown
        last_trade = buyer.get('last_trade_tick', -TRADE_COOLDOWN)
        if self.state.ticks - last_trade < TRADE_COOLDOWN:
            return False
        
        # Don't trade with known criminals the farmer cares about
        if self.cares_about_criminal(farmer, buyer):
            return False
        
        buyer_allegiance = buyer.get('allegiance')
        farmer_allegiance = farmer.get('allegiance')
        
        if buyer_allegiance is not None:
            if farmer_allegiance != buyer_allegiance:
                return False
        
        # Check if farmer can afford to sell this amount
        sellable = self.get_farmer_sellable_wheat(farmer)
        min_amount = amount if amount is not None else 1
        if sellable < min_amount:
            return False
        
        # Check if farmer has space for money
        if not self.can_add_money(farmer):
            return False
        
        # Check if buyer has space for wheat (if amount specified)
        if amount is not None and not self.can_add_wheat(buyer, amount):
            return False
        
        return True
    
    def get_max_trade_amount(self, farmer, buyer):
        """Calculate the maximum wheat that can be traded between farmer and buyer.
        Takes into account: farmer's sellable wheat, buyer's money, buyer's inventory space,
        and how much wheat the buyer actually wants.
        """
        sellable = self.get_farmer_sellable_wheat(farmer)
        if sellable <= 0:
            return 0
        
        # How much can buyer afford?
        buyer_money = self.get_money(buyer)
        affordable = int(buyer_money / WHEAT_PRICE_PER_UNIT)
        
        # How much space does buyer have?
        buyer_space = self.state.get_inventory_space(buyer)
        
        # How much does buyer actually want?
        desired = self.get_desired_wheat_amount(buyer)
        
        return max(0, min(sellable, affordable, buyer_space, desired))
    
    def get_desired_wheat_amount(self, char):
        """Calculate how much wheat a character wants to buy.
        Based on hunger level and wheat buffer target.
        """
        current_wheat = self.get_wheat(char)
        
        # Want enough wheat to fill hunger + buffer
        hunger_deficit = MAX_HUNGER - char['hunger']
        wheat_for_hunger = max(0, int(hunger_deficit / HUNGER_PER_WHEAT) + 1)
        
        # Also want buffer (WHEAT_BUFFER_TARGET days worth)
        buffer_want = max(0, WHEAT_BUFFER_TARGET - current_wheat)
        
        return wheat_for_hunger + buffer_want
    
    def can_afford_any_wheat(self, char):
        """Check if character can afford at least 1 wheat."""
        return self.get_money(char) >= WHEAT_PRICE_PER_UNIT
    
    def execute_trade(self, farmer, buyer, amount):
        """Execute a wheat trade between farmer and buyer.
        Farmer sells from inventory first, then from barrel if needed.
        """
        if amount <= 0:
            return
        
        price = int(amount * WHEAT_PRICE_PER_UNIT)
        amount_needed = amount
        
        # First take from farmer's inventory
        farmer_wheat = self.get_wheat(farmer)
        from_inventory = min(farmer_wheat, amount_needed)
        if from_inventory > 0:
            self.remove_wheat(farmer, from_inventory)
            amount_needed -= from_inventory
        
        # If still need more, take from barrel
        if amount_needed > 0:
            farm_barrel = self.state.get_barrel_by_home(farmer.get('home', self.state.get_area_by_role('farm')))
            if farm_barrel:
                self.state.remove_barrel_wheat(farm_barrel, amount_needed)
        
        self.add_money(farmer, price)
        self.remove_money(buyer, price)
        self.add_wheat(buyer, amount)
        
        # Set buyer's trade cooldown
        buyer['last_trade_tick'] = self.state.ticks
    
    # =========================================================================
    # GENERALIZED VENDOR SYSTEM
    # =========================================================================
    # Characters buy goods from the nearest vendor that sells what they need
    
    def get_vendors_selling(self, goods_type):
        """Get list of all characters who sell a specific goods type"""
        vendors = []
        for char in self.state.characters:
            job = char.get('job')
            if job and job in VENDOR_GOODS:
                if goods_type in VENDOR_GOODS[job]:
                    vendors.append(char)
        return vendors
    
    def is_vendor_of(self, char, goods_type):
        """Check if a character sells a specific goods type"""
        job = char.get('job')
        if not job or job not in VENDOR_GOODS:
            return False
        return goods_type in VENDOR_GOODS[job]
    
    def find_nearest_vendor(self, char, goods_type):
        """Find the nearest vendor selling a specific goods type"""
        best_vendor = None
        best_dist = float('inf')
        
        for vendor in self.get_vendors_selling(goods_type):
            if vendor == char:  # Can't buy from self
                continue
            dist = self.get_distance(char, vendor)
            if dist < best_dist:
                best_dist = dist
                best_vendor = vendor
        
        return best_vendor
    
    def find_adjacent_vendor(self, char, goods_type):
        """Find an adjacent vendor selling a specific goods type (within ADJACENCY_DISTANCE)"""
        for vendor in self.state.characters:
            if vendor != char and self.is_vendor_of(vendor, goods_type):
                if self.is_adjacent(char, vendor):
                    return vendor
        return None
    
    def find_willing_vendor(self, char, goods_type):
        """Find the nearest vendor willing to trade this goods type with this character"""
        best_vendor = None
        best_dist = float('inf')
        
        for vendor in self.get_vendors_selling(goods_type):
            if vendor == char:
                continue
            if self.vendor_willing_to_trade(vendor, char, goods_type):
                dist = self.get_distance(char, vendor)
                if dist < best_dist:
                    best_dist = dist
                    best_vendor = vendor
        
        return best_vendor
    
    def any_valid_vendor_exists(self, char, goods_type):
        """Check if any vendor exists who could potentially sell to this character"""
        char_allegiance = char.get('allegiance')
        
        for vendor in self.get_vendors_selling(goods_type):
            if vendor == char:
                continue
            vendor_allegiance = vendor.get('allegiance')
            # Can trade if either has no allegiance or allegiances match
            if char_allegiance is None or vendor_allegiance is None:
                return True
            if char_allegiance == vendor_allegiance:
                return True
        return False
    
    def get_vendor_sellable_goods(self, vendor, goods_type):
        """Calculate how much of a goods type the vendor can sell.
        For farmers, uses the special tax-aware calculation.
        For other vendors, uses simpler inventory-based calculation.
        """
        job = vendor.get('job')
        
        # Farmers have special tax-aware wheat selling logic
        if job == 'Farmer' and goods_type == 'wheat':
            return self.get_farmer_sellable_wheat(vendor)
        
        # For other vendors, check inventory minus personal reserve
        current_stock = self.get_goods_amount(vendor, goods_type)
        reserve = VENDOR_PERSONAL_RESERVE.get(goods_type, 0)
        return max(0, current_stock - reserve)
    
    def get_goods_amount(self, char, goods_type):
        """Get total amount of a goods type in character's inventory.
        Currently only 'wheat' and 'money' are implemented in inventory.
        Other goods types return 0 (placeholder for future expansion).
        """
        if goods_type == 'wheat':
            return self.get_wheat(char)
        elif goods_type == 'money':
            return self.get_money(char)
        # Placeholder for other goods - would need inventory system expansion
        return char.get(f'{goods_type}_stock', 0)
    
    def get_goods_price(self, goods_type, amount=1):
        """Get the price for a given amount of goods"""
        unit_price = GOODS_PRICES.get(goods_type, 10)  # Default price if not defined
        return unit_price * amount
    
    def vendor_willing_to_trade(self, vendor, buyer, goods_type, amount=None):
        """Check if vendor is willing to trade goods with this buyer.
        If amount is None, checks if vendor can sell at least 1 unit.
        Traders are self-employed and will trade with anyone regardless of allegiance.
        """
        if vendor == buyer:
            return False
        
        # Check buyer's trade cooldown
        last_trade = buyer.get('last_trade_tick', -TRADE_COOLDOWN)
        if self.state.ticks - last_trade < TRADE_COOLDOWN:
            return False
        
        # Don't trade with known criminals the vendor cares about
        if self.cares_about_criminal(vendor, buyer):
            return False
        
        # Check allegiance compatibility (Traders trade with anyone)
        vendor_job = vendor.get('job')
        if vendor_job != 'Trader':
            # Non-traders require allegiance compatibility
            buyer_allegiance = buyer.get('allegiance')
            vendor_allegiance = vendor.get('allegiance')
            
            if buyer_allegiance is not None and vendor_allegiance is not None:
                if vendor_allegiance != buyer_allegiance:
                    return False
        
        # Check if vendor has goods to sell
        sellable = self.get_vendor_sellable_goods(vendor, goods_type)
        min_amount = amount if amount is not None else 1
        if sellable < min_amount:
            return False
        
        # Check if vendor has space for money
        if not self.can_add_money(vendor):
            return False
        
        return True
    
    def get_max_vendor_trade_amount(self, vendor, buyer, goods_type):
        """Calculate maximum amount that can be traded for a goods type.
        Takes into account: vendor's stock, buyer's money, buyer's inventory space.
        """
        sellable = self.get_vendor_sellable_goods(vendor, goods_type)
        if sellable <= 0:
            return 0
        
        # How much can buyer afford?
        buyer_money = self.get_money(buyer)
        unit_price = GOODS_PRICES.get(goods_type, 10)
        affordable = int(buyer_money / unit_price) if unit_price > 0 else 0
        
        # How much space does buyer have? (for wheat, use existing system)
        if goods_type == 'wheat':
            buyer_space = self.state.get_inventory_space(buyer)
        else:
            # For other goods, simplified space check
            buyer_space = INVENTORY_SLOTS  # Placeholder
        
        # How much does buyer want?
        if goods_type == 'wheat':
            desired = self.get_desired_wheat_amount(buyer)
        else:
            desired = 1  # Default to buying 1 unit for other goods
        
        return max(0, min(sellable, affordable, buyer_space, desired))
    
    def execute_vendor_trade(self, vendor, buyer, goods_type, amount):
        """Execute a trade between vendor and buyer for any goods type.
        For wheat from farmers, uses the existing barrel-aware system.
        """
        if amount <= 0:
            return False
        
        price = self.get_goods_price(goods_type, amount)
        
        # Special handling for farmer wheat (uses barrel system)
        if vendor.get('job') == 'Farmer' and goods_type == 'wheat':
            self.execute_trade(vendor, buyer, amount)
            return True
        
        # Generic goods trade
        if goods_type == 'wheat':
            # Remove from vendor, add to buyer
            self.remove_wheat(vendor, amount)
            self.add_wheat(buyer, amount)
        else:
            # For other goods types, adjust stock values
            vendor_stock_key = f'{goods_type}_stock'
            buyer_stock_key = f'{goods_type}_stock'
            vendor[vendor_stock_key] = vendor.get(vendor_stock_key, 0) - amount
            buyer[buyer_stock_key] = buyer.get(buyer_stock_key, 0) + amount
        
        # Transfer money
        self.add_money(vendor, price)
        self.remove_money(buyer, price)
        
        # Set trade cooldown
        buyer['last_trade_tick'] = self.state.ticks
        
        return True
    
    def try_buy_from_nearest_vendor(self, char, goods_type):
        """Attempt to buy goods from the nearest willing vendor.
        Returns True if a purchase was made or if moving toward a vendor.
        """
        name = self.get_display_name(char)
        
        # Check if we can afford anything
        unit_price = GOODS_PRICES.get(goods_type, 10)
        if self.get_money(char) < unit_price:
            return False
        
        # First check if adjacent to a willing vendor
        adjacent_vendor = self.find_adjacent_vendor(char, goods_type)
        if adjacent_vendor and self.vendor_willing_to_trade(adjacent_vendor, char, goods_type):
            amount = self.get_max_vendor_trade_amount(adjacent_vendor, char, goods_type)
            if amount > 0:
                price = self.get_goods_price(goods_type, amount)
                vendor_name = self.get_display_name(adjacent_vendor)
                
                if self.execute_vendor_trade(adjacent_vendor, char, goods_type, amount):
                    self.state.log_action(f"{name} bought {amount} {goods_type} for ${price} from {vendor_name}")
                    char['wheat_seek_ticks'] = 0  # Reset seek timer
                    return True
        
        # Otherwise, move toward nearest willing vendor
        willing_vendor = self.find_willing_vendor(char, goods_type)
        if willing_vendor:
            self.move_toward_character(char, willing_vendor)
            return True
        
        return False
    
    # =========================================================================
    # JOB SEEKING SYSTEM
    # =========================================================================
    # Jobs are sought in tier order: Steward (tier 2), then Trader/Soldier/Farmer (tier 3)
    
    def is_eligible_for_steward(self, char):
        """Check if character is eligible to be Steward.
        Requirements: VILLAGE allegiance + mercantile skill >= 50
        Traders can also be promoted to steward.
        """
        if char.get('allegiance') != PRIMARY_ALLEGIANCE:
            return False
        mercantile_skill = char.get('skills', {}).get('mercantile', 0)
        return mercantile_skill >= 50
    
    def is_steward_job_available(self):
        """Check if steward position is available (vacant)."""
        return self.get_steward() is None
    
    def is_best_steward_candidate(self, char):
        """Check if this character has the highest mercantile among eligible candidates."""
        if not self.is_eligible_for_steward(char):
            return False
        
        char_mercantile = char.get('skills', {}).get('mercantile', 0)
        
        for other in self.state.characters:
            if other == char:
                continue
            if not self.is_eligible_for_steward(other):
                continue
            other_mercantile = other.get('skills', {}).get('mercantile', 0)
            if other_mercantile > char_mercantile:
                return False
        
        return True
    
    def can_become_steward(self, char):
        """Check if character can become steward right now (in barracks + best candidate).
        Works for both unemployed characters and traders seeking promotion.
        """
        if not self.is_steward_job_available():
            return False
        if not self.is_best_steward_candidate(char):
            return False
        military_area = self.state.get_area_by_role('military_housing')
        return self.state.get_area_at(char['x'], char['y']) == military_area
    
    def become_steward(self, char):
        """Promote a character to steward position."""
        old_job = char.get('job')
        
        char['job'] = 'Steward'
        char['home'] = self.state.get_area_by_role('military_housing')
        char['allegiance'] = PRIMARY_ALLEGIANCE
        
        # Assign bed in barracks
        self.state.unassign_bed_owner(char['name'])
        bed = self.state.get_unowned_bed_by_home(self.state.get_area_by_role('military_housing'))
        if bed:
            self.state.assign_bed_owner(bed, char['name'])
        
        # Assign barracks barrel
        barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
        if barracks_barrel:
            barracks_barrel['owner'] = char['name']
        
        name = self.get_display_name(char)
        if old_job:
            self.state.log_action(f"{name} was promoted from {old_job} to STEWARD!")
        else:
            self.state.log_action(f"{name} became the village STEWARD!")
    
    def is_eligible_for_trader(self, char):
        """Check if character has the mercantile skill to become a Trader"""
        mercantile_skill = char.get('skills', {}).get('mercantile', 0)
        return mercantile_skill >= 20
    
    def is_eligible_for_soldier(self, char):
        """Check if character has the right traits to enlist as Soldier"""
        morality = self.get_trait(char, 'morality')
        confidence = self.get_trait(char, 'confidence')
        cunning = self.get_trait(char, 'cunning')
        return morality >= 5 and confidence >= 7 and cunning <= 5
    
    def is_eligible_for_farmer(self, char):
        """Check if character has the farming skill required to enlist as Farmer"""
        farming_skill = char.get('skills', {}).get('farming', 0)
        return farming_skill >= 40
    
    def is_trader_job_available(self):
        """Check if trader job is available. Always True - it's self-employed."""
        return True
    
    def is_soldier_job_available(self):
        """Check if soldier position is available (has bed and wheat)"""
        # Check for available bed
        bed = self.state.get_unowned_bed_by_home(self.state.get_area_by_role('military_housing'))
        if not bed:
            return False
        # Check barracks barrel for wheat
        barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
        if not barracks_barrel or self.state.get_barrel_wheat(barracks_barrel) < SOLDIER_WHEAT_PAYMENT:
            return False
        return True
    
    def is_farmer_job_available(self):
        """Check if farmer position is available (unowned village farm)"""
        return self.get_unowned_village_farm() is not None
    
    def get_best_available_job(self, char):
        """Get the best available job for this character based on tier priority.
        Returns job name or None if no jobs available/eligible.
        Tier order: Steward (2), then Trader/Soldier/Farmer (3) chosen randomly if multiple available.
        """
        if char.get('job') is not None:
            return None
        
        # Tier 2: Steward - only if they're the best candidate
        if self.is_eligible_for_steward(char) and self.is_steward_job_available() and self.is_best_steward_candidate(char):
            return 'Steward'
        
        # Tier 3: Trader, Soldier and Farmer - pick randomly if multiple available
        available_tier3 = []
        if self.is_eligible_for_trader(char) and self.is_trader_job_available():
            available_tier3.append('Trader')
        if self.is_eligible_for_soldier(char) and self.is_soldier_job_available():
            available_tier3.append('Soldier')
        if self.is_eligible_for_farmer(char) and self.is_farmer_job_available():
            available_tier3.append('Farmer')
        
        if available_tier3:
            return random.choice(available_tier3)
        
        return None
    
    def wants_job(self, char):
        """Check if character wants to seek any job"""
        return self.get_best_available_job(char) is not None
    
    def can_enlist_as_soldier(self, char):
        """Check if character can enlist as soldier right now"""
        if char.get('job') is not None:
            return False
        military_area = self.state.get_area_by_role('military_housing')
        if self.state.get_area_at(char['x'], char['y']) != military_area:
            return False
        if not self.is_eligible_for_soldier(char):
            return False
        if not self.is_soldier_job_available():
            return False
        return True
    
    def can_become_trader(self, char):
        """Check if character can become a self-employed trader right now.
        Traders are self-employed - they can start anytime, anywhere.
        """
        if char.get('job') is not None:
            return False
        if not self.is_eligible_for_trader(char):
            return False
        return True
    
    def become_trader(self, char):
        """Character becomes a self-employed trader.
        Traders have no allegiance requirement and can trade with anyone.
        """
        char['job'] = 'Trader'
        # Traders are self-employed - no allegiance, home is wherever they want
        # They keep their current home/camp if they have one
        
        name = self.get_display_name(char)
        self.state.log_action(f"{name} became a self-employed Trader!")
    
    def can_enlist_as_farmer(self, char):
        """Check if character can enlist as a farmer (must be adjacent to steward)"""
        if char.get('job') is not None:
            return False
        if not self.is_eligible_for_farmer(char):
            return False
        # Must be adjacent to steward
        steward = self.get_steward()
        if not steward:
            return False
        if not self.is_adjacent(char, steward):
            return False
        if not self.is_farmer_job_available():
            return False
        return True
    
    def enlist_as_soldier(self, char):
        """Enlist a character as a soldier"""
        old_allegiance = char.get('allegiance')
        char['job'] = 'Soldier'
        char['home'] = self.state.get_area_by_role('military_housing')
        char['allegiance'] = PRIMARY_ALLEGIANCE
        char['soldier_stopped'] = False
        char['asked_steward_for_wheat'] = False
        
        # Assign a bed in barracks
        bed = self.state.get_unowned_bed_by_home(self.state.get_area_by_role('military_housing'))
        if bed:
            self.state.assign_bed_owner(bed, char['name'])
        
        name = self.get_display_name(char)
        if old_allegiance is None:
            self.state.log_action(f"{name} ENLISTED as Soldier! (gained VILLAGE allegiance)")
        elif old_allegiance != PRIMARY_ALLEGIANCE:
            self.state.log_action(f"{name} ENLISTED as Soldier! (allegiance changed from {old_allegiance} to VILLAGE)")
        else:
            self.state.log_action(f"{name} RE-ENLISTED as Soldier!")
    
    def get_unowned_village_farm(self):
        """Find a village-allegiance farm area that has no farmer assigned.
        Returns the area name or None if all farms are owned.
        """
        from scenario_world import AREAS
        
        for area in AREAS:
            if area.get('has_farm_cells') and area.get('allegiance') == PRIMARY_ALLEGIANCE:
                farm_name = area['name']
                # Check if any farmer owns this farm (has it as home)
                farm_has_farmer = False
                for char in self.state.characters:
                    if char.get('job') == 'Farmer' and char.get('home') == farm_name:
                        farm_has_farmer = True
                        break
                if not farm_has_farmer:
                    return farm_name
        return None
    
    def enlist_as_farmer(self, char):
        """Enlist a character as a farmer"""
        # Find the available farm
        farm_name = self.get_unowned_village_farm()
        if not farm_name:
            return  # No farm available
        
        old_allegiance = char.get('allegiance')
        char['job'] = 'Farmer'
        char['home'] = farm_name
        char['allegiance'] = PRIMARY_ALLEGIANCE
        
        # Assign the farm barrel to this farmer
        farm_barrel = self.state.get_barrel_by_home(farm_name)
        if farm_barrel:
            farm_barrel['owner'] = char['name']
        
        # Assign the farm bed to this farmer
        bed = self.state.get_unowned_bed_by_home(farm_name)
        if bed:
            self.state.assign_bed_owner(bed, char['name'])
        
        name = self.get_display_name(char)
        if old_allegiance is None:
            self.state.log_action(f"{name} ENLISTED as Farmer! (gained VILLAGE allegiance)")
        elif old_allegiance != PRIMARY_ALLEGIANCE:
            self.state.log_action(f"{name} ENLISTED as Farmer! (allegiance changed from {old_allegiance} to VILLAGE)")
        else:
            self.state.log_action(f"{name} ENLISTED as Farmer!")

    # =========================================================================
    # COMBAT / ROBBERY SYSTEM
    # =========================================================================
    
    def get_attacker(self, char):
        """Find anyone who is targeting this character and is close enough"""
        for other in self.state.characters:
            if other.get('robbery_target') == char:
                dist = self.get_distance(char, other)
                if dist <= 5:
                    return other
        return None
    
    def find_nearby_defender(self, char, max_distance):
        """Find a defender within range.
        Defenders are: Soldiers with confidence >= 5, or anyone with morality >= 7 and confidence >= 7
        """
        best_defender = None
        best_dist = float('inf')
        
        for other in self.state.characters:
            if other == char:
                continue
            
            morality = self.get_trait(other, 'morality')
            confidence = self.get_trait(other, 'confidence')
            is_soldier = other.get('job') == 'Soldier'
            
            # Soldier with confidence >= 5, or high morality + high confidence
            is_defender = (is_soldier and confidence >= 5) or (morality >= 7 and confidence >= 7)
            
            if is_defender:
                dist = self.get_distance(char, other)
                if dist <= max_distance and dist < best_dist:
                    best_dist = dist
                    best_defender = other
        
        return best_defender
    
    def is_defender(self, char):
        """Check if a character will defend others from crime.
        Soldiers need confidence >= 5, others need morality >= 7 and confidence >= 7
        """
        morality = self.get_trait(char, 'morality')
        confidence = self.get_trait(char, 'confidence')
        is_soldier = char.get('job') == 'Soldier'
        
        if is_soldier:
            return confidence >= 5
        else:
            return morality >= 7 and confidence >= 7
    
    def find_nearby_perpetrator(self, char):
        """Find someone committing a crime nearby (for backwards compatibility).
        Use find_known_criminal_nearby for the unified system.
        """
        return self.find_known_criminal_nearby(char)
    
    def get_crime_range(self, crime_type):
        """Get the range for a crime type. The intensity IS the range."""
        if crime_type == 'murder':
            return CRIME_INTENSITY_MURDER  # 7 cells
        elif crime_type == 'theft':
            return CRIME_INTENSITY_THEFT   # 4 cells
        else:
            return 5  # default fallback
    
    def get_flee_distance(self, intensity):
        """Get how far to flee from a criminal. Returns intensity * 2."""
        return intensity * 2
    
    def will_care_about_crime(self, responder, crime_allegiance, intensity=None):
        """Does this person care about this crime?
        
        Soldiers: +3 morality bonus for same-allegiance crimes, any intensity
        Others: morality >= 7 required, only for intensity >= 15
        """
        effective_morality = self.get_trait(responder, 'morality')
        is_same_allegiance_soldier = (responder.get('job') == 'Soldier' and 
                                    responder.get('allegiance') == crime_allegiance)
        
        if is_same_allegiance_soldier:
            effective_morality += 3
            return effective_morality >= 7
        
        # Non-soldiers only care about serious crimes
        if intensity is not None and intensity < 15:
            return False
        
        return effective_morality >= 7
    
    def remember_crime(self, witness, criminal, intensity, crime_allegiance):
        """Add crime to witness's memory."""
        criminal_id = id(criminal)
        if criminal_id not in witness['known_crimes']:
            witness['known_crimes'][criminal_id] = []
        # Add this crime (could have multiple crimes from same criminal)
        witness['known_crimes'][criminal_id].append({
            'intensity': intensity,
            'allegiance': crime_allegiance
        })
    
    def get_worst_known_crime(self, observer, criminal):
        """Get the most severe crime this observer knows about for this criminal.
        Returns (intensity, allegiance) or None if no known crimes.
        """
        criminal_id = id(criminal)
        crimes = observer.get('known_crimes', {}).get(criminal_id, [])
        if not crimes:
            return None
        # Return highest intensity crime
        return max(crimes, key=lambda c: c['intensity'])
    
    def cares_about_criminal(self, observer, criminal):
        """Check if observer cares about any crime committed by this criminal."""
        criminal_id = id(criminal)
        crimes = observer.get('known_crimes', {}).get(criminal_id, [])
        
        for crime in crimes:
            if self.will_care_about_crime(observer, crime['allegiance'], crime['intensity']):
                return True
        return False
    
    def find_known_criminal_nearby(self, char):
        """Find any known criminal within range that this character cares about.
        
        Uses intensity-based ranges.
        Only returns criminals the character cares about (based on morality/allegiance).
        
        Returns (criminal, intensity) or (None, None) if none found.
        """
        # Check for active robbers (crime in progress - treat as murder intensity)
        murder_range = self.get_crime_range('murder')
        for other in self.state.characters:
            if other == char:
                continue
            if other.get('is_aggressor') and other.get('robbery_target'):
                target = other.get('robbery_target')
                if target in self.state.characters:
                    dist = self.get_distance(char, other)
                    if dist <= murder_range:
                        # Active aggression - check if we care
                        crime_allegiance = target.get('allegiance')
                        if self.will_care_about_crime(char, crime_allegiance, CRIME_INTENSITY_MURDER):
                            return (other, CRIME_INTENSITY_MURDER)
        
        # Check known crimes
        for other in self.state.characters:
            if other == char:
                continue
            
            criminal_id = id(other)
            crimes = char.get('known_crimes', {}).get(criminal_id, [])
            
            for crime in crimes:
                intensity = crime['intensity']
                crime_allegiance = crime['allegiance']
                crime_range = intensity  # Range = intensity
                
                dist = self.get_distance(char, other)
                if dist <= crime_range:
                    if self.will_care_about_crime(char, crime_allegiance, intensity):
                        return (other, intensity)
        
        return (None, None)
    
    def get_hunger_factor(self, char):
        """Get hunger factor from 0 (not hungry) to 1 (starving).
        Scales from HUNGER_CHANCE_THRESHOLD (60) down to 0.
        """
        if char['hunger'] >= HUNGER_CHANCE_THRESHOLD:
            return 0.0
        return 1.0 - (char['hunger'] / HUNGER_CHANCE_THRESHOLD)
    
    def should_attempt_farm_theft(self, char):
        """Determine if character will attempt to steal from a farm.
        Returns True if they decide to steal.
        
        Morality 7+: Never steals
        Morality 6: 1% -> 10% based on hunger
        Morality 5: 5% -> 20% based on hunger
        Morality 4-1: 50% -> 100% based on hunger
        """
        morality = self.get_trait(char, 'morality')
        
        if morality >= 7:
            return False
        
        hunger_factor = self.get_hunger_factor(char)
        
        if morality == 6:
            chance = 0.01 + (0.09 * hunger_factor)  # 1% to 10%
        elif morality == 5:
            chance = 0.05 + (0.15 * hunger_factor)  # 5% to 20%
        else:  # morality 4, 3, 2, 1
            chance = 0.50 + (0.50 * hunger_factor)  # 50% to 100%
        
        return random.random() < chance
    
    def should_attempt_robbery(self, char):
        """Determine if character will attempt robbery.
        Returns True if they decide to rob.
        
        Morality 5+: Never robs
        Morality 4-3: Only when starving, +10% per tick starving
        Morality 2-1: Same chance as farm theft (50-100% based on hunger)
        """
        morality = self.get_trait(char, 'morality')
        
        if morality >= 5:
            return False
        
        if morality >= 3:  # Morality 4-3
            # Only robs when starving
            if not char.get('is_starving', False):
                return False
            # 10% per tick starving
            ticks_starving = char.get('ticks_starving', 0)
            chance = 0.10 * ticks_starving
            return random.random() < min(1.0, chance)
        else:  # Morality 2-1
            # Same chance as farm theft
            hunger_factor = self.get_hunger_factor(char)
            chance = 0.50 + (0.50 * hunger_factor)  # 50% to 100%
            return random.random() < chance
    
    def decide_crime_action(self, char):
        """Decide what crime action (if any) to take.
        Returns: 'theft', 'robbery', or None
        
        For morality 2-1, if both theft and robbery would trigger,
        randomly choose between them (50/50).
        """
        morality = self.get_trait(char, 'morality')
        
        if morality >= 7:
            return None
        
        will_steal = self.should_attempt_farm_theft(char)
        will_rob = self.should_attempt_robbery(char)
        
        if morality <= 2:
            # Equal chance between theft and robbery if both trigger
            if will_steal and will_rob:
                return random.choice(['theft', 'robbery'])
            elif will_steal:
                return 'theft'
            elif will_rob:
                return 'robbery'
        else:
            # Morality 3-6: prioritize theft over robbery
            if will_steal:
                return 'theft'
            elif will_rob:
                return 'robbery'
        
        return None
    
    def find_nearby_ready_farm_cell(self, char):
        """Find a ready farm cell nearby that the character could steal from."""
        best_cell = None
        best_dist = float('inf')
        
        for (cx, cy), data in self.state.farm_cells.items():
            if data['state'] == 'ready':
                dist = abs(cx - char['x']) + abs(cy - char['y'])
                if dist < best_dist:
                    best_dist = dist
                    best_cell = (cx, cy)
        
        return best_cell
    
    def try_farm_theft(self, char):
        """Character attempts to steal from a farm. Returns True if action taken."""
        # If already pursuing a theft target, continue
        if char.get('theft_target'):
            return self.continue_theft(char)
        
        cell = self.find_nearby_ready_farm_cell(char)
        if not cell:
            return False
        
        # Start pursuing the cell (not a crime yet - just walking to farm)
        char['theft_target'] = cell
        name = self.get_display_name(char)
        self.state.log_action(f"{name} heading toward farm at {cell}")
        
        return self.continue_theft(char)
    
    def continue_theft(self, char):
        """Continue theft in progress. Returns True if still stealing."""
        cell = char.get('theft_target')
        if not cell:
            return False
        
        cx, cy = cell
        name = self.get_display_name(char)
        
        # Check if cell is still ready
        data = self.state.farm_cells.get(cell)
        if not data or data['state'] != 'ready':
            # Cell no longer available
            char['theft_target'] = None
            self.state.log_action(f"{name} abandoned theft - crop already taken")
            return False
        
        # If standing on the cell (character's cell position matches), steal immediately
        # Convert float position to cell coordinates
        char_cell = (int(char['x']), int(char['y']))
        if char_cell == cell:
            # Check if has inventory space
            if not self.can_add_wheat(char, FARM_CELL_YIELD):
                char['theft_target'] = None
                return False
            
            # Execute the theft - THE CRIMINAL ACT
            self.add_wheat(char, FARM_CELL_YIELD)
            # Leave cell in replanting state (brown) - only farmers can turn it yellow
            data['state'] = 'replanting'
            data['timer'] = FARM_REPLANT_TIME
            
            # Mark as thief
            char['is_thief'] = True
            char['theft_target'] = None
            
            self.state.log_action(f"{name} STOLE {FARM_CELL_YIELD} wheat from farm!")
            self.witness_theft(char, cell)
            return True
        
        # Still in transit - movement handled by _get_goal
        return True
    
    def witness_theft(self, thief, cell):
        """Witnesses within theft range learn about the theft and may react.
        
        Range: CRIME_INTENSITY_THEFT (4 cells)
        """
        thief_name = self.get_display_name(thief)
        cx, cy = cell
        intensity = CRIME_INTENSITY_THEFT
        witness_range = intensity
        
        # Get the farm's allegiance (this is the crime allegiance)
        crime_allegiance = self.state.get_farm_cell_allegiance(cx, cy)
        
        for char in self.state.characters:
            if char == thief:
                continue
            
            dist = abs(char['x'] - cx) + abs(char['y'] - cy)
            if dist <= witness_range:
                witness_name = self.get_display_name(char)
                
                # Everyone remembers the crime
                self.remember_crime(char, thief, intensity, crime_allegiance)
                
                # Check if this witness cares
                cares = self.will_care_about_crime(char, crime_allegiance, intensity)
                
                # Check if this is the farm owner (always reacts as victim)
                is_owner = char.get('job') == 'Farmer' and char.get('home') == self.state.get_area_by_role('farm')
                
                if cares or is_owner:
                    confidence = self.get_trait(char, 'confidence')
                    if confidence >= 7:
                        char['robbery_target'] = thief
                        self.state.log_action(f"{witness_name} WITNESSED {thief_name} stealing! Attacking!")
                    else:
                        char['flee_from'] = thief
                        self.state.log_action(f"{witness_name} WITNESSED {thief_name} stealing! Fleeing!")
                else:
                    self.state.log_action(f"{witness_name} witnessed {thief_name} stealing.")
                
                # Try to report if same allegiance
                if char.get('allegiance') == crime_allegiance and crime_allegiance is not None:
                    self.try_report_crime(char, thief, intensity, crime_allegiance)
    
    def try_report_crime(self, witness, criminal, intensity, crime_allegiance):
        """Try to report crime to an adjacent soldier. If none adjacent, save for later.
        
        Only reports to soldiers of same allegiance as the crime.
        Requires adjacency (distance 1).
        """
        if crime_allegiance is None:
            return  # Can't report crimes against unaligned
        
        witness_name = self.get_display_name(witness)
        criminal_name = self.get_display_name(criminal)
        
        # Look for an adjacent soldier of the same allegiance
        for char in self.state.characters:
            if char == witness or char == criminal:
                continue
            if char.get('job') == 'Soldier' and char.get('allegiance') == crime_allegiance:
                dist = abs(char['x'] - witness['x']) + abs(char['y'] - witness['y'])
                if dist <= 1:  # Must be adjacent
                    # Report to this soldier
                    self.remember_crime(char, criminal, intensity, crime_allegiance)
                    soldier_name = self.get_display_name(char)
                    self.state.log_action(f"{witness_name} reported {criminal_name} to {soldier_name}!")
                    return  # Reported successfully
        
        # No soldier adjacent - save for later
        witness['unreported_crimes'].add((id(criminal), intensity, crime_allegiance))
    
    def find_richest_target(self, robber):
        """Find the best target to rob"""
        targets = [c for c in self.state.characters if c != robber and (self.get_money(c) > 0 or self.get_wheat(c) > 0)]
        if not targets:
            return None
        return max(targets, key=lambda c: (self.get_wheat(c), self.get_money(c)))
    
    def try_robbery(self, robber):
        """Character decides to rob someone - sets target and starts pursuit"""
        target = self.find_richest_target(robber)
        if target:
            robber_name = self.get_display_name(robber)
            target_name = self.get_display_name(target)
            self.state.log_action(f"{robber_name} DECIDED TO ROB {target_name} (target has ${self.get_money(target)})")
            robber['robbery_target'] = target
            robber['is_aggressor'] = True
            return self.continue_robbery(robber)
        return False
    
    def continue_robbery(self, robber):
        """Continue robbery in progress - returns True if still robbing"""
        target = robber.get('robbery_target')
        
        if robber not in self.state.characters:
            return False
        
        if target is None or target not in self.state.characters:
            robber['robbery_target'] = None
            return False
        
        # Movement is handled by velocity system in _get_goal
        # We just check if adjacent and attack if so
        
        robber_name = self.get_display_name(robber)
        target_name = self.get_display_name(target)
        
        if self.is_adjacent(robber, target):
            damage = random.randint(2, 5)  # Reduced damage (was 10-20)
            target['health'] -= damage
            self.state.log_action(f"{robber_name} ATTACKS {target_name} for {damage} damage! Health: {target['health'] + damage} -> {target['health']}")
            
            if target['health'] <= 0:
                killer_is_defender = not robber.get('is_aggressor', False)
                target_was_criminal = target.get('is_aggressor', False) or target.get('is_murderer', False) or target.get('is_thief', False)
                is_player_death = self.is_player(target)
                
                target_money = self.get_money(target)
                target_wheat = self.get_wheat(target)
                
                if killer_is_defender and target_was_criminal:
                    if is_player_death:
                        self.state.log_action(f"{robber_name} KILLED {target_name} (PLAYER - justified)! GAME OVER")
                    else:
                        self.state.log_action(f"{robber_name} KILLED {target_name} (justified)! Took ${target_money} and {target_wheat} wheat")
                else:
                    robber['is_murderer'] = True
                    if is_player_death:
                        self.state.log_action(f"{robber_name} KILLED {target_name} (PLAYER)! GAME OVER")
                    else:
                        self.state.log_action(f"{robber_name} KILLED {target_name}! Stole ${target_money} and {target_wheat} wheat")
                    self.witness_murder(robber, target)
                
                # Transfer items
                self.state.transfer_all_items(target, robber)
                self.state.remove_character(target)
                robber['robbery_target'] = None
                robber['is_aggressor'] = False
        
        return True
    
    def witness_murder(self, murderer, victim):
        """Witnesses within murder range learn about the murder and may react.
        
        Range: CRIME_INTENSITY_MURDER (7 cells)
        """
        murderer_name = self.get_display_name(murderer)
        victim_name = self.get_display_name(victim)
        intensity = CRIME_INTENSITY_MURDER
        witness_range = intensity
        
        # Crime allegiance = victim's allegiance
        crime_allegiance = victim.get('allegiance')
        
        for char in self.state.characters:
            if char == murderer or char == victim:
                continue
            
            dist = abs(char['x'] - victim['x']) + abs(char['y'] - victim['y'])
            if dist <= witness_range:
                witness_name = self.get_display_name(char)
                
                # Everyone remembers the crime
                self.remember_crime(char, murderer, intensity, crime_allegiance)
                self.state.log_action(f"{witness_name} WITNESSED {murderer_name} murder {victim_name}!")
                
                # Try to report if same allegiance
                if char.get('allegiance') == crime_allegiance and crime_allegiance is not None:
                    self.try_report_crime(char, murderer, intensity, crime_allegiance)
    
    def try_report_crimes_to_soldier(self, char):
        """If character has unreported crimes and is adjacent to a soldier, report to them.
        
        Only reports to soldiers of same allegiance as the crime.
        Requires adjacency (distance 1).
        """
        unreported = char.get('unreported_crimes', set())
        
        if not unreported:
            return
        
        char_name = self.get_display_name(char)
        
        for other in self.state.characters:
            if other == char:
                continue
            if other.get('job') != 'Soldier':
                continue
            
            dist = abs(char['x'] - other['x']) + abs(char['y'] - other['y'])
            if dist > 1:  # Must be adjacent
                continue
                
            soldier_name = self.get_display_name(other)
            soldier_allegiance = other.get('allegiance')
            
            # Check each unreported crime
            for crime_tuple in list(unreported):
                criminal_id, intensity, crime_allegiance = crime_tuple
                
                # Only report to soldiers of same allegiance
                if crime_allegiance == soldier_allegiance:
                    # Find the criminal for logging and to pass to remember_crime
                    criminal = next((c for c in self.state.characters if id(c) == criminal_id), None)
                    if criminal:
                        criminal_name = self.get_display_name(criminal)
                        self.remember_crime(other, criminal, intensity, crime_allegiance)
                        self.state.log_action(f"{char_name} reported {criminal_name} to {soldier_name}")
                    char['unreported_crimes'].discard(crime_tuple)
    
    # =========================================================================
    # WHEAT / HUNGER SYSTEM
    # =========================================================================
    
    def should_seek_wheat(self, char):
        """Determine if NPC should seek wheat based on hunger level"""
        hunger = char['hunger']
        
        if hunger <= HUNGER_CRITICAL:
            return True
        elif hunger <= HUNGER_CHANCE_THRESHOLD:
            chance = (HUNGER_CHANCE_THRESHOLD - hunger) / (HUNGER_CHANCE_THRESHOLD - HUNGER_CRITICAL)
            return random.random() < chance
        else:
            return False
    
    def needs_wheat_buffer(self, char):
        """Check if character's wheat inventory is below the 1-day buffer target."""
        return self.get_wheat(char) < WHEAT_BUFFER_TARGET
    
    def handle_wheat_need(self, char):
        """Handle a character's wheat needs. Returns True if action was taken."""
        job = char.get('job')
        name = self.get_display_name(char)
        
        # Option 1: Eat from inventory
        if self.get_wheat(char) >= WHEAT_PER_BITE:
            self.remove_wheat(char, WHEAT_PER_BITE)
            char['hunger'] = min(MAX_HUNGER, char['hunger'] + HUNGER_PER_WHEAT)
            char['wheat_seek_ticks'] = 0
            self.state.log_action(f"{name} ate from inventory, hunger now {char['hunger']:.0f}")
            return True
        
        # Option 2: Soldiers wait for steward to bring wheat (passive)
        # The steward will come to them - soldiers just need to register their request
        if job == 'Soldier':
            # Register request if not already done
            if not char.get('requested_wheat'):
                char['requested_wheat'] = True
            # Soldiers don't actively seek wheat - they wait
            return False
        
        # Option 3: Non-soldiers buy wheat from nearest vendor (Farmer, Trader, Innkeeper, etc.)
        # Characters who sell wheat themselves don't buy from others
        if self.can_afford_any_wheat(char) and not self.is_vendor_of(char, 'wheat'):
            # Try to buy from adjacent vendor first
            adjacent_vendor = self.find_adjacent_vendor(char, 'wheat')
            if adjacent_vendor and self.vendor_willing_to_trade(adjacent_vendor, char, 'wheat'):
                amount = self.get_max_vendor_trade_amount(adjacent_vendor, char, 'wheat')
                if amount > 0:
                    price = self.get_goods_price('wheat', amount)
                    vendor_name = self.get_display_name(adjacent_vendor)
                    
                    if self.execute_vendor_trade(adjacent_vendor, char, 'wheat', amount):
                        char['wheat_seek_ticks'] = 0
                        self.state.log_action(f"{name} bought {amount} wheat for ${price} from {vendor_name}")
                        return True
            
            # Move toward nearest willing vendor
            willing_vendor = self.find_willing_vendor(char, 'wheat')
            if willing_vendor:
                self.move_toward_character(char, willing_vendor)
                char['wheat_seek_ticks'] += 1
                return True
            
            # No willing vendor - check if allegiance should be dropped
            if char.get('allegiance') is not None:
                if not self.any_valid_vendor_exists(char, 'wheat'):
                    char['wheat_seek_ticks'] += 1
                    if char['wheat_seek_ticks'] >= ALLEGIANCE_WHEAT_TIMEOUT:
                        old_allegiance = char['allegiance']
                        char['allegiance'] = None
                        char['wheat_seek_ticks'] = 0
                        self.state.log_action(f"{name} LOST allegiance to {old_allegiance} - no one will sell wheat!")
                        return True
        
        # Option 4: Resort to crime (only if can't legitimately buy wheat)
        # Characters with money and access to a willing vendor should NEVER steal
        can_buy_wheat = self.can_afford_any_wheat(char) and self.find_willing_vendor(char, 'wheat') is not None
        
        if not can_buy_wheat:
            crime_action = self.decide_crime_action(char)
            if crime_action == 'theft':
                if self.try_farm_theft(char):
                    return True
            elif crime_action == 'robbery':
                if self.try_robbery(char):
                    return True
        
        return False
    

    # =========================================================================
    # MOVEMENT SYSTEM
    # =========================================================================
    
    def _process_npc_movement(self):
        """
        Process all NPC movement for this tick.
        Updates velocities based on goals. Position updates happen every frame via update_npc_positions().
        """
        npcs = [c for c in self.state.characters if not self.is_player(c)]
        
        # Update velocities based on goals (decision-making happens per tick)
        for char in npcs:
            if char.get('is_frozen'):
                char['vx'] = 0.0
                char['vy'] = 0.0
                continue
            
            # Reset idle flag before getting goal (will be set if idling)
            char['idle_is_idle'] = False
            
            goal = self._get_goal(char)
            if goal:
                # Calculate direction to goal
                dx = goal[0] - char['x']
                dy = goal[1] - char['y']
                dist = math.sqrt(dx * dx + dy * dy)
                
                if dist < 0.35:  # Close enough to goal - larger threshold prevents overshoot jitter
                    char['vx'] = 0.0
                    char['vy'] = 0.0
                else:
                    # Use slower speed if idling
                    speed = MOVEMENT_SPEED
                    if char.get('idle_is_idle', False):
                        speed = MOVEMENT_SPEED * IDLE_SPEED_MULTIPLIER
                    
                    # Normalize and apply speed
                    char['vx'] = (dx / dist) * speed
                    char['vy'] = (dy / dist) * speed
                    # Update facing direction
                    self._update_facing_from_velocity(char)
            else:
                char['vx'] = 0.0
                char['vy'] = 0.0
            
            # If character is not idling, reset their idle state for next time
            if not char.get('idle_is_idle', False):
                self._reset_idle_state(char)
        
        # Run actions (combat, trading, eating, etc.)
        for char in npcs:
            if char not in self.state.characters:
                continue  # Skip dead characters
            self._do_npc_actions(char)
        
        # Report crimes to nearby soldiers
        for char in self.state.characters:
            self.try_report_crimes_to_soldier(char)
    
    def update_npc_positions(self, dt):
        """Update NPC positions based on velocity. Called every frame for smooth movement.
        
        Implements squeeze behavior: when blocked for more than SQUEEZE_THRESHOLD_TICKS,
        characters will slide perpendicular to their movement direction to squeeze past obstacles.
        """
        npcs = [c for c in self.state.characters if not self.is_player(c)]
        
        for char in npcs:
            vx = char.get('vx', 0.0)
            vy = char.get('vy', 0.0)
            
            if vx == 0.0 and vy == 0.0:
                # Not moving - reset squeeze state
                char['blocked_ticks'] = 0
                char['squeeze_direction'] = 0
                continue
            
            # Calculate base new position
            new_x = char['x'] + vx * dt
            new_y = char['y'] + vy * dt
            
            # Keep within bounds
            half_width = char.get('width', CHARACTER_WIDTH) / 2
            half_height = char.get('height', CHARACTER_HEIGHT) / 2
            new_x = max(half_width, min(SIZE - half_width, new_x))
            new_y = max(half_height, min(SIZE - half_height, new_y))
            
            # Check for collision with other characters
            if not self.state.is_position_blocked(new_x, new_y, exclude_char=char):
                # Clear path - move normally
                char['x'] = new_x
                char['y'] = new_y
                char['blocked_ticks'] = 0
                char['squeeze_direction'] = 0
            else:
                # Blocked - try to find a way through
                moved = self._try_squeeze_movement(char, vx, vy, new_x, new_y, dt)
    
    def _try_squeeze_movement(self, char, vx, vy, new_x, new_y, dt):
        """Try to squeeze past an obstacle when blocked.
        
        Strategy:
        1. First, try simple axis-aligned sliding (might work for glancing collisions)
        2. If blocked for 3+ ticks, pick a perpendicular direction and slide that way
        3. Keep sliding in that direction until we make forward progress or get unstuck
        
        Returns True if character moved, False if completely stuck.
        """
        moved = False
        made_forward_progress = False
        
        # Try simple axis-aligned sliding first (handles glancing collisions)
        # Only try if we're actually moving in that direction
        if abs(vx) >= abs(vy):
            # Moving mostly horizontal - try X only first
            if abs(vx) > 0.01 and not self.state.is_position_blocked(new_x, char['y'], exclude_char=char):
                char['x'] = new_x
                moved = True
                made_forward_progress = True
            # Then try Y if we have Y velocity
            elif abs(vy) > 0.01 and not self.state.is_position_blocked(char['x'], new_y, exclude_char=char):
                char['y'] = new_y
                moved = True
        else:
            # Moving mostly vertical - try Y only first
            if abs(vy) > 0.01 and not self.state.is_position_blocked(char['x'], new_y, exclude_char=char):
                char['y'] = new_y
                moved = True
                made_forward_progress = True
            # Then try X if we have X velocity
            elif abs(vx) > 0.01 and not self.state.is_position_blocked(new_x, char['y'], exclude_char=char):
                char['x'] = new_x
                moved = True
        
        if made_forward_progress:
            # Made actual forward progress - reset squeeze state
            char['blocked_ticks'] = 0
            char['squeeze_direction'] = 0
            return True
        
        # Still blocked on primary axis - increment counter
        char['blocked_ticks'] = char.get('blocked_ticks', 0) + 1
        
        # After threshold OR if already squeezing, continue squeeze behavior
        if char['blocked_ticks'] >= SQUEEZE_THRESHOLD_TICKS or char.get('squeeze_direction', 0) != 0:
            # Pick a squeeze direction if we don't have one
            if char.get('squeeze_direction', 0) == 0:
                # Choose direction based on which way has more space
                # or randomly if equal
                char['squeeze_direction'] = self._choose_squeeze_direction(char, vx, vy)
            
            squeeze_dir = char['squeeze_direction']
            slide_speed = MOVEMENT_SPEED * SQUEEZE_SLIDE_SPEED * dt
            
            # Calculate slide movement perpendicular to travel direction
            if abs(vx) > abs(vy):
                # Moving horizontal, slide vertical
                slide_y = char['y'] + squeeze_dir * slide_speed
                # Try to move: slide perpendicular + forward progress
                if not self.state.is_position_blocked(new_x, slide_y, exclude_char=char):
                    char['x'] = new_x
                    char['y'] = slide_y
                    char['blocked_ticks'] = 0
                    char['squeeze_direction'] = 0
                    return True
                # Try just sliding perpendicular
                elif not self.state.is_position_blocked(char['x'], slide_y, exclude_char=char):
                    char['y'] = slide_y
                    return True
                else:
                    # This direction is blocked, try the other way
                    char['squeeze_direction'] = -squeeze_dir
            else:
                # Moving vertical, slide horizontal
                slide_x = char['x'] + squeeze_dir * slide_speed
                # Try to move: slide perpendicular + forward progress
                if not self.state.is_position_blocked(slide_x, new_y, exclude_char=char):
                    char['x'] = slide_x
                    char['y'] = new_y
                    char['blocked_ticks'] = 0
                    char['squeeze_direction'] = 0
                    return True
                # Try just sliding perpendicular
                elif not self.state.is_position_blocked(slide_x, char['y'], exclude_char=char):
                    char['x'] = slide_x
                    return True
                else:
                    # This direction is blocked, try the other way
                    char['squeeze_direction'] = -squeeze_dir
        
        return False
    
    def _choose_squeeze_direction(self, char, vx, vy):
        """Choose which direction to squeeze (perpendicular to movement).
        Picks the direction with more open space, or random if equal.
        Returns -1 or 1.
        """
        # Check space in both perpendicular directions
        check_dist = 1.0  # How far to look
        
        if abs(vx) > abs(vy):
            # Moving horizontal, check vertical space
            space_pos = 0
            space_neg = 0
            for d in [0.3, 0.6, 1.0]:
                if not self.state.is_position_blocked(char['x'], char['y'] + d, exclude_char=char):
                    space_pos += 1
                if not self.state.is_position_blocked(char['x'], char['y'] - d, exclude_char=char):
                    space_neg += 1
        else:
            # Moving vertical, check horizontal space
            space_pos = 0
            space_neg = 0
            for d in [0.3, 0.6, 1.0]:
                if not self.state.is_position_blocked(char['x'] + d, char['y'], exclude_char=char):
                    space_pos += 1
                if not self.state.is_position_blocked(char['x'] - d, char['y'], exclude_char=char):
                    space_neg += 1
        
        if space_pos > space_neg:
            return 1
        elif space_neg > space_pos:
            return -1
        else:
            # Equal space - pick randomly
            return random.choice([-1, 1])

    def _update_facing_from_velocity(self, char):
        """Update character's facing direction based on velocity."""
        vx = char.get('vx', 0.0)
        vy = char.get('vy', 0.0)
        
        if abs(vx) < 0.01 and abs(vy) < 0.01:
            return  # Not moving
        
        # Determine primary direction
        if abs(vx) > abs(vy) * 2:
            # Mostly horizontal
            char['facing'] = 'right' if vx > 0 else 'left'
        elif abs(vy) > abs(vx) * 2:
            # Mostly vertical
            char['facing'] = 'down' if vy > 0 else 'up'
        else:
            # Diagonal
            if vx > 0 and vy < 0:
                char['facing'] = 'up-right'
            elif vx > 0 and vy > 0:
                char['facing'] = 'down-right'
            elif vx < 0 and vy < 0:
                char['facing'] = 'up-left'
            else:
                char['facing'] = 'down-left'
    
    def _get_desired_step(self, char):
        """Calculate the position this NPC wants to move toward.
        Returns the goal position or None if no goal.
        """
        return self._get_goal(char)
    
    def _get_goal(self, char):
        """Get the position this character is trying to reach.
        Returns float position (x, y) or None if no goal.
        """
        # Helper to convert cell position to center point
        def cell_to_center(pos):
            if pos is None:
                return None
            return (pos[0] + 0.5, pos[1] + 0.5)
        
        # Helper to check if character is at a position (within threshold)
        def at_position(char, pos, threshold=0.15):
            if pos is None:
                return False
            dx = char['x'] - pos[0]
            dy = char['y'] - pos[1]
            return (dx * dx + dy * dy) < threshold * threshold
        
        # Priority 0: Sleep time - go to bed or camp
        if self.is_sleep_time():
            sleep_pos = self.get_sleep_position(char)
            if sleep_pos:
                sleep_center = cell_to_center(sleep_pos)
                # Have a bed or camp
                if at_position(char, sleep_center):
                    # Already at sleep position - stay still and sleep
                    if not char.get('is_sleeping'):
                        char['is_sleeping'] = True
                        name = self.get_display_name(char)
                        bed = self.get_character_bed(char)
                        if bed:
                            self.state.log_action(f"{name} went to sleep in bed")
                        else:
                            self.state.log_action(f"{name} went to sleep at camp")
                    return None
                else:
                    # Move toward sleep position
                    return sleep_center
            else:
                # No bed or camp - need to find a place to make camp
                if self.can_make_camp_at(char['x'], char['y']):
                    # Can camp here
                    self.make_camp(char)
                    char['is_sleeping'] = True
                    return None
                else:
                    # Move away from village to find camp spot
                    return self._find_camp_spot(char)
        else:
            # Not sleep time - wake up if sleeping
            if char.get('is_sleeping'):
                char['is_sleeping'] = False
                name = self.get_display_name(char)
                self.state.log_action(f"{name} woke up")
        
        # Priority 1: Combat target - stay still if already adjacent
        target = char.get('robbery_target')
        if target and target in self.state.characters:
            if self.is_adjacent(char, target):
                return None  # Stay still, we're in combat range
            return (target['x'], target['y'])
        
        # Priority 2: Respond to attacker - stay still if adjacent and fighting back
        attacker = self.get_attacker(char)
        if attacker:
            confidence = self.get_trait(char, 'confidence')
            if confidence >= 7:
                if self.is_adjacent(char, attacker):
                    return None  # Stay still, we're fighting
                return (attacker['x'], attacker['y'])
            else:
                # Being attacked = murder-level threat
                murder_range = self.get_crime_range('murder')
                defender = self.find_nearby_defender(char, murder_range)
                if defender:
                    return (defender['x'], defender['y'])
                else:
                    return self._get_flee_goal(char, attacker)
        
        # Priority 2.5: Fleeing from witnessed crime
        flee_target = char.get('flee_from')
        if flee_target and flee_target in self.state.characters:
            # Get the worst crime we know about for flee distance
            worst_crime = self.get_worst_known_crime(char, flee_target)
            if worst_crime:
                flee_distance = self.get_flee_distance(worst_crime['intensity'])
            else:
                flee_distance = self.get_flee_distance(CRIME_INTENSITY_MURDER)  # Default to murder
            
            dist = self.get_distance(char, flee_target)
            if dist > flee_distance:
                # Far enough, stop fleeing
                char['flee_from'] = None
            else:
                return self._get_flee_goal(char, flee_target)
        elif flee_target:
            # Target no longer exists
            char['flee_from'] = None
        
        # Priority 2.75: Theft target - move toward farm cell to steal
        theft_target = char.get('theft_target')
        if theft_target:
            # Check if cell is still ready
            data = self.state.farm_cells.get(theft_target)
            if data and data['state'] == 'ready':
                return cell_to_center(theft_target)
            else:
                # Cell no longer available, clear target
                char['theft_target'] = None
        
        # Priority 3: React to known criminals nearby (only if we care)
        criminal, intensity = self.find_known_criminal_nearby(char)
        if criminal:
            confidence = self.get_trait(char, 'confidence')
            char_name = self.get_display_name(char)
            criminal_name = self.get_display_name(criminal)
            
            if confidence >= 7:
                # Attack
                if char.get('robbery_target') != criminal:
                    self.state.log_action(f"{char_name} confronting {criminal_name}!")
                    char['robbery_target'] = criminal
                if self.is_adjacent(char, criminal):
                    return None  # Stay still, we're in combat range
                return (criminal['x'], criminal['y'])
            else:
                # Flee
                if char.get('flee_from') != criminal:
                    self.state.log_action(f"{char_name} fleeing from {criminal_name}!")
                    char['flee_from'] = criminal
                
                # Use intensity-based range for finding defender
                defender_range = intensity
                defender = self.find_nearby_defender(char, defender_range)
                if defender:
                    return (defender['x'], defender['y'])
                else:
                    return self._get_flee_goal(char, criminal)
        
        # Priority 4: Critical hunger
        if char['hunger'] <= HUNGER_CRITICAL and self.get_wheat(char) < WHEAT_PER_BITE:
            wheat_goal = self._get_wheat_goal(char)
            if wheat_goal:
                return wheat_goal
        
        # Priority 5: Job-specific goals
        job = char.get('job')
        if job == 'Farmer':
            return self._get_farmer_goal(char)
        elif job == 'Soldier':
            return self._get_soldier_goal(char)
        elif job == 'Steward':
            return self._get_steward_goal(char)
        elif job == 'Trader':
            # Traders can be promoted to steward - go to barracks if eligible
            if self.is_steward_job_available() and self.is_best_steward_candidate(char):
                military_area = self.state.get_area_by_role('military_housing')
                if self.state.get_area_at(char['x'], char['y']) != military_area:
                    return self._nearest_in_area(char, military_area)
        
        # Priority 6: Job seeking (unified system - seeks best available job by tier)
        if job is None and self.wants_job(char):
            best_job = self.get_best_available_job(char)
            if best_job == 'Steward':
                # Go to barracks to accept steward position
                if self.state.get_area_at(char['x'], char['y']) != self.state.get_area_by_role('military_housing'):
                    return self._nearest_in_area(char, self.state.get_area_by_role('military_housing'))
            elif best_job == 'Trader':
                # Traders are self-employed - can start anywhere, no goal needed
                # They'll become a trader in the action phase
                pass
            elif best_job == 'Soldier':
                # Go to barracks to enlist
                if self.state.get_area_at(char['x'], char['y']) != self.state.get_area_by_role('military_housing'):
                    return self._nearest_in_area(char, self.state.get_area_by_role('military_housing'))
            elif best_job == 'Farmer':
                # Go to steward to enlist
                steward = self.get_steward()
                if steward:
                    return (steward['x'], steward['y'])
        
        # Priority 7: Non-critical hunger OR low wheat buffer
        if (self.should_seek_wheat(char) and self.get_wheat(char) < WHEAT_PER_BITE) or self.needs_wheat_buffer(char):
            wheat_goal = self._get_wheat_goal(char)
            if wheat_goal:
                return wheat_goal
        
        # Priority 8: Go to / wander in home area
        home = char.get('home')
        if home:
            # Check if already in home area
            current_area = self.state.get_area_at(char['x'], char['y'])
            is_village_home = (home == PRIMARY_ALLEGIANCE)
            
            if is_village_home:
                in_home = self.state.is_in_village(char['x'], char['y'])
            else:
                in_home = (current_area == home)
            
            if in_home:
                # Already home - wander within area
                return self._get_wander_goal(char, home)
            else:
                # Not home - move toward home
                return self._nearest_in_area(char, home, is_village=is_village_home)
        
        # No home - use idle wandering system with a null area (wanders anywhere non-farm)
        return self._get_homeless_idle_goal(char)
    
    def _get_homeless_idle_goal(self, char):
        """Get idle goal for a homeless character - wanders anywhere except farm cells.
        Uses the same state machine as _get_wander_goal but without area constraints.
        """
        # Mark character as idling (for speed reduction)
        char['idle_is_idle'] = True
        
        idle_state = char.get('idle_state', 'choosing')
        
        # Handle waiting state
        if idle_state == 'waiting' or idle_state == 'paused':
            wait_ticks = char.get('idle_wait_ticks', 0)
            if wait_ticks > 0:
                char['idle_wait_ticks'] = wait_ticks - 1
                return None  # Stay still
            else:
                # Done waiting, choose new destination
                char['idle_state'] = 'choosing'
                idle_state = 'choosing'
        
        # Handle choosing state - pick a new destination
        if idle_state == 'choosing':
            destination = self._choose_homeless_destination(char)
            if destination:
                char['idle_destination'] = destination
                char['idle_state'] = 'moving'
                idle_state = 'moving'
            else:
                # No valid destination, stay put
                return None
        
        # Handle moving state
        if idle_state == 'moving':
            destination = char.get('idle_destination')
            if not destination:
                char['idle_state'] = 'choosing'
                return None
            
            # Check if we've arrived at destination
            dx = destination[0] - char['x']
            dy = destination[1] - char['y']
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist < 0.4:  # Arrived at destination
                # Start waiting
                char['idle_state'] = 'waiting'
                char['idle_wait_ticks'] = random.randint(IDLE_MIN_WAIT_TICKS, IDLE_MAX_WAIT_TICKS)
                char['idle_destination'] = None
                return None
            
            # Maybe pause mid-journey
            if random.random() < IDLE_PAUSE_CHANCE / 100:
                char['idle_state'] = 'paused'
                char['idle_wait_ticks'] = random.randint(IDLE_PAUSE_MIN_TICKS, IDLE_PAUSE_MAX_TICKS)
                return None
            
            return destination
        
        return None
    
    def _choose_homeless_destination(self, char):
        """Choose a destination for homeless wandering.
        Picks a random non-farm cell within moderate distance.
        """
        current_x, current_y = int(char['x']), int(char['y'])
        
        # Find valid cells within a reasonable wander range (not too far)
        valid_cells = []
        wander_range = 8  # Cells to consider
        
        for dy in range(-wander_range, wander_range + 1):
            for dx in range(-wander_range, wander_range + 1):
                nx, ny = current_x + dx, current_y + dy
                if not self.state.is_position_valid(nx, ny):
                    continue
                # Skip farm cells
                if (nx, ny) in self.state.farm_cells:
                    continue
                # Skip current cell
                if dx == 0 and dy == 0:
                    continue
                valid_cells.append((nx, ny))
        
        if not valid_cells:
            return None
        
        # Prefer cells that are at least 2 cells away for more purposeful movement
        far_cells = [c for c in valid_cells if abs(c[0]-current_x) + abs(c[1]-current_y) > 2]
        if far_cells:
            cell = random.choice(far_cells)
        else:
            cell = random.choice(valid_cells)
        
        return (cell[0] + 0.5, cell[1] + 0.5)
    
    def _get_flee_goal(self, char, threat):
        """Get a position away from the threat. Returns float position."""
        dx = char['x'] - threat['x']
        dy = char['y'] - threat['y']
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0.01:
            # Normalize and extend
            dx = dx / dist
            dy = dy / dist
        else:
            # Pick random direction if on top of threat
            angle = random.random() * 2 * math.pi
            dx = math.cos(angle)
            dy = math.sin(angle)
        return (char['x'] + dx * 5.0, char['y'] + dy * 5.0)
    
    def _find_camp_spot(self, char):
        """Find a nearby position where the character can make a camp (outside village).
        Returns float position (center of cell).
        """
        # Try to find nearest valid camp spot
        best_spot = None
        best_dist = float('inf')
        
        for y in range(SIZE):
            for x in range(SIZE):
                if self.can_make_camp_at(x, y) and not self.state.is_occupied(x, y):
                    # Calculate distance to center of this cell
                    cx, cy = x + 0.5, y + 0.5
                    dist = math.sqrt((cx - char['x']) ** 2 + (cy - char['y']) ** 2)
                    if dist < best_dist:
                        best_dist = dist
                        best_spot = (cx, cy)
        
        return best_spot
    
    def _get_wheat_goal(self, char):
        """Get position to move toward for wheat. Returns float position."""
        job = char.get('job')
        if job == 'Soldier':
            # Go to barracks barrel position
            barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
            if barracks_barrel:
                barrel_pos = self.state.get_barrel_position(barracks_barrel)
                if barrel_pos:
                    return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            return self._nearest_in_area(char, self.state.get_area_by_role('military_housing'))
        if self.can_afford_any_wheat(char):
            farmer = self.find_willing_farmer(char)
            if farmer:
                return (farmer['x'], farmer['y'])
        return None
    
    def _get_farmer_goal(self, char):
        """Get farmer's movement goal. Returns float position."""
        steward = self.get_steward()
        if steward and char.get('allegiance') == PRIMARY_ALLEGIANCE:
            # No taxes due in first year
            if self.state.ticks >= STEWARD_TAX_INTERVAL:
                ticks_until_tax = STEWARD_TAX_INTERVAL - (self.state.ticks % STEWARD_TAX_INTERVAL)
                if ticks_until_tax == STEWARD_TAX_INTERVAL:
                    ticks_until_tax = 0
                if ticks_until_tax <= 5 or char.get('tax_late_ticks', 0) > 0:
                    return (steward['x'], steward['y'])
        
        day_tick = self.state.ticks % TICKS_PER_DAY
        is_work_time = day_tick < TICKS_PER_DAY // 2  # Work first half of day
        is_market_time = TICKS_PER_DAY // 2 <= day_tick < TICKS_PER_DAY * 2 // 3  # Market second quarter (50-67%)
        
        if is_work_time:
            # Check if inventory full - go to barrel to deposit
            if self.is_inventory_full(char):
                farm_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('farm'))
                if farm_barrel:
                    barrel_pos = self.state.get_barrel_position(farm_barrel)
                    if barrel_pos:
                        return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
                # Fallback if no barrel - go idle
                if self.state.is_in_village(char['x'], char['y']):
                    return self._get_wander_goal(char, PRIMARY_ALLEGIANCE)
                return self._nearest_in_area(char, PRIMARY_ALLEGIANCE, is_village=True)
            
            # Check if has a full stack of excess wheat to deposit
            farmer_wheat = self.get_wheat(char)
            if farmer_wheat >= FARMER_PERSONAL_RESERVE + WHEAT_STACK_SIZE:
                farm_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('farm'))
                if farm_barrel and self.state.can_barrel_add_wheat(farm_barrel, 1):
                    barrel_pos = self.state.get_barrel_position(farm_barrel)
                    if barrel_pos and not self.state.is_adjacent_to_barrel(char, farm_barrel):
                        return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            
            # Work on farm
            if self.state.get_area_at(char['x'], char['y']) == self.state.get_area_by_role('farm'):
                return self._nearest_ready_farm_cell(char)
            return self._nearest_in_area(char, self.state.get_area_by_role('farm'))
        elif is_market_time:
            # Market time - go to market stall if has stuff to sell
            sellable = self.get_farmer_sellable_wheat(char)
            if sellable >= 1:
                # Has stuff to sell - go to market and stand still
                if self.state.get_area_at(char['x'], char['y']) == self.state.get_area_by_role('market'):
                    return None  # Already at market - stand still (manning stall)
                return self._nearest_in_area(char, self.state.get_area_by_role('market'))
            else:
                # Nothing to sell - keep farming
                if self.state.get_area_at(char['x'], char['y']) == self.state.get_area_by_role('farm'):
                    return self._nearest_ready_farm_cell(char)
                return self._nearest_in_area(char, self.state.get_area_by_role('farm'))
        else:
            # After market time (67%+) - sleep handles this via Priority 0
            # But if not sleep time yet somehow, go home
            if self.state.get_area_at(char['x'], char['y']) == self.state.get_area_by_role('farm'):
                return None
            return self._nearest_in_area(char, self.state.get_area_by_role('farm'))
    
    def _get_soldier_goal(self, char):
        """Get soldier's movement goal. Returns float position.
        
        Soldiers patrol the village perimeter in clockwise order.
        When blocked, they squeeze past obstacles without losing their patrol progress.
        When hungry, they wait in barracks for the steward to bring them food.
        """
        is_hungry = char['hunger'] <= HUNGER_CHANCE_THRESHOLD and self.get_wheat(char) < WHEAT_PER_BITE
        
        if is_hungry:
            # Going to wait for food - clear patrol target
            char['patrol_target'] = None
            # Register wheat request if not already registered
            if not char.get('requested_wheat'):
                char['requested_wheat'] = True
                name = self.get_display_name(char)
                self.state.log_action(f"{name} is waiting for food from the Steward")
            # Wait in barracks (wander there, not at barrel specifically)
            military_area = self.state.get_area_by_role('military_housing')
            if self.state.get_area_at(char['x'], char['y']) == military_area:
                return self._get_wander_goal(char, military_area)
            return self._nearest_in_area(char, military_area)
        
        perimeter = self.state.get_village_perimeter()  # Clockwise ordered
        if not perimeter:
            return None
            
        current_cell = (int(char['x']), int(char['y']))
        
        # Get positions of other soldiers to avoid
        other_soldier_cells = set()
        for c in self.state.characters:
            if c != char and c.get('job') == 'Soldier':
                other_soldier_cells.add((int(c['x']), int(c['y'])))
        
        # Check if we have an existing patrol target
        patrol_target = char.get('patrol_target')
        
        if patrol_target:
            # Check if we've reached our patrol target
            target_x, target_y = patrol_target
            dist_to_target = math.sqrt((char['x'] - target_x - 0.5)**2 + (char['y'] - target_y - 0.5)**2)
            
            if dist_to_target < 0.5:
                # Reached target - clear it and pick next one below
                char['patrol_target'] = None
                patrol_target = None
            elif patrol_target not in other_soldier_cells:
                # Still heading to target and it's not blocked by another soldier
                return (target_x + 0.5, target_y + 0.5)
            else:
                # Target is now occupied by another soldier - skip it
                char['patrol_target'] = None
                patrol_target = None
        
        # Need to pick a new patrol target
        # Find our position in the perimeter (or nearest point if we're off the path)
        if current_cell in perimeter:
            current_idx = perimeter.index(current_cell)
        else:
            # Off perimeter (maybe squeezed off) - find nearest perimeter point
            # and continue from there in the same direction
            best_idx = 0
            best_dist = float('inf')
            for idx, (px, py) in enumerate(perimeter):
                dist = abs(char['x'] - px - 0.5) + abs(char['y'] - py - 0.5)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx
            current_idx = best_idx
        
        # Find next unoccupied perimeter cell in clockwise order
        for offset in range(1, len(perimeter)):
            next_idx = (current_idx + offset) % len(perimeter)
            next_pos = perimeter[next_idx]
            if next_pos not in other_soldier_cells:
                char['patrol_target'] = next_pos
                return (next_pos[0] + 0.5, next_pos[1] + 0.5)
        
        # All positions occupied - stay still
        return None
    
    def _get_steward_goal(self, char):
        """Get steward's movement goal. Returns float position.
        
        Priority order:
        1. Tax collection target
        2. Feed hungry soldiers (go to them if has wheat, go to barrel if not)
        3. Own hunger needs
        4. Buy wheat from farmers
        5. Deposit excess wheat
        6. Wander in barracks
        """
        # Priority 1: Tax collection
        target = char.get('tax_collection_target')
        if target and target in self.state.characters:
            return (target['x'], target['y'])
        
        # Priority 2: Feed hungry soldiers who have requested wheat
        hungry_soldiers = self._get_soldiers_requesting_wheat()
        if hungry_soldiers:
            steward_wheat = self.get_wheat(char)
            
            if steward_wheat >= SOLDIER_WHEAT_PAYMENT:
                # Have enough for at least one soldier - go to closest requesting soldier
                closest_soldier = min(hungry_soldiers, key=lambda s: self.get_distance(char, s))
                return (closest_soldier['x'], closest_soldier['y'])
            else:
                # Check if barrel has wheat before going there
                barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
                if barracks_barrel and self.state.get_barrel_wheat(barracks_barrel) > 0:
                    barrel_pos = self.state.get_barrel_position(barracks_barrel)
                    if barrel_pos:
                        return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
                # No wheat available - fall through to other priorities
        
        # Priority 3: Go to barrel to eat when hungry and low on personal wheat
        if char['hunger'] <= HUNGER_CHANCE_THRESHOLD and self.get_wheat(char) < WHEAT_PER_BITE:
            barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
            if barracks_barrel and self.state.get_barrel_wheat(barracks_barrel) >= SOLDIER_WHEAT_PAYMENT:
                barrel_pos = self.state.get_barrel_position(barracks_barrel)
                if barrel_pos:
                    return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
        
        # Priority 4: Buy wheat from farmers
        if self.steward_needs_to_buy_wheat(char) and self.can_afford_any_wheat(char):
            farmer = self.find_willing_farmer(char)
            if farmer:
                return (farmer['x'], farmer['y'])
        
        # Priority 5: If has excess wheat, go to barrel to deposit
        personal_wheat = self.get_wheat(char)
        personal_reserve = 3
        if personal_wheat > personal_reserve:
            barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
            if barracks_barrel:
                barrel_pos = self.state.get_barrel_position(barracks_barrel)
                if barrel_pos:
                    return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
        
        # Priority 6: Wander in barracks
        if self.state.get_area_at(char['x'], char['y']) == self.state.get_area_by_role('military_housing'):
            # Already in barracks - wander around naturally
            return self._get_wander_goal(char, self.state.get_area_by_role('military_housing'))
        return self._nearest_in_area(char, self.state.get_area_by_role('military_housing'))
    
    def _get_soldiers_requesting_wheat(self):
        """Get list of soldiers who have requested wheat from the steward."""
        return [c for c in self.state.characters 
                if c.get('job') == 'Soldier' and c.get('requested_wheat', False)]
    
    def _get_wander_goal(self, char, area):
        """Get the current idle destination for this character within the given area.
        Uses a state machine to create natural wandering behavior:
        - Choose a point of interest or random valid cell
        - Move toward it at reduced speed
        - Wait there for a while
        - Sometimes pause mid-journey
        Returns float position or None if waiting/paused.
        """
        is_village = (area == PRIMARY_ALLEGIANCE)
        
        # Mark character as idling (for speed reduction)
        char['idle_is_idle'] = True
        
        idle_state = char.get('idle_state', 'choosing')
        
        # Handle waiting state
        if idle_state == 'waiting' or idle_state == 'paused':
            wait_ticks = char.get('idle_wait_ticks', 0)
            if wait_ticks > 0:
                char['idle_wait_ticks'] = wait_ticks - 1
                return None  # Stay still
            else:
                # Done waiting, choose new destination
                char['idle_state'] = 'choosing'
                idle_state = 'choosing'
        
        # Handle choosing state - pick a new destination
        if idle_state == 'choosing':
            destination = self._choose_idle_destination(char, area, is_village)
            if destination:
                char['idle_destination'] = destination
                char['idle_state'] = 'moving'
                idle_state = 'moving'
            else:
                # No valid destination, stay put
                return None
        
        # Handle moving state
        if idle_state == 'moving':
            destination = char.get('idle_destination')
            if not destination:
                char['idle_state'] = 'choosing'
                return None
            
            # Check if we've arrived at destination
            dx = destination[0] - char['x']
            dy = destination[1] - char['y']
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist < 0.4:  # Arrived at destination
                # Start waiting
                char['idle_state'] = 'waiting'
                char['idle_wait_ticks'] = random.randint(IDLE_MIN_WAIT_TICKS, IDLE_MAX_WAIT_TICKS)
                char['idle_destination'] = None
                return None
            
            # Maybe pause mid-journey (small chance per tick)
            # Only check occasionally to avoid constant rolls
            if random.random() < IDLE_PAUSE_CHANCE / 100:  # Scaled down since called every tick
                char['idle_state'] = 'paused'
                char['idle_wait_ticks'] = random.randint(IDLE_PAUSE_MIN_TICKS, IDLE_PAUSE_MAX_TICKS)
                return None
            
            return destination
        
        return None
    
    def _choose_idle_destination(self, char, area, is_village):
        """Choose a destination for idle wandering.
        70% chance to pick a point of interest (corners, center, edges)
        30% chance to pick a random valid cell
        Avoids farm cells.
        """
        # Get points of interest
        poi_list = self.state.get_area_points_of_interest(area, is_village)
        
        # Get valid cells for random wandering
        valid_cells = self.state.get_valid_idle_cells(area, is_village)
        
        if not poi_list and not valid_cells:
            return None
        
        # 70% chance to go to a point of interest if available
        if poi_list and (not valid_cells or random.random() < 0.7):
            # Pick a POI that's not too close to current position
            current_pos = (char['x'], char['y'])
            far_pois = [p for p in poi_list if math.sqrt((p[0]-current_pos[0])**2 + (p[1]-current_pos[1])**2) > 2.0]
            if far_pois:
                return random.choice(far_pois)
            elif poi_list:
                return random.choice(poi_list)
        
        # Pick a random valid cell
        if valid_cells:
            # Prefer cells that are at least 2 cells away
            current_cell = (int(char['x']), int(char['y']))
            far_cells = [c for c in valid_cells if abs(c[0]-current_cell[0]) + abs(c[1]-current_cell[1]) > 2]
            if far_cells:
                cell = random.choice(far_cells)
            else:
                cell = random.choice(valid_cells)
            return (cell[0] + 0.5, cell[1] + 0.5)
        
        return None
    
    def _reset_idle_state(self, char):
        """Reset idle state when character is no longer idling."""
        char['idle_state'] = 'choosing'
        char['idle_destination'] = None
        char['idle_wait_ticks'] = 0
        char['idle_is_idle'] = False

    def _get_random_neighbor(self, char):
        """Get a random valid position nearby. Returns float position.
        Avoids farm cells.
        """
        # Try several times to find a non-farm cell
        for _ in range(10):
            # Pick a random direction and distance
            angle = random.random() * 2 * math.pi
            distance = random.uniform(1.0, 3.0)
            
            nx = char['x'] + math.cos(angle) * distance
            ny = char['y'] + math.sin(angle) * distance
            
            # Clamp to bounds
            nx = max(0.5, min(SIZE - 0.5, nx))
            ny = max(0.5, min(SIZE - 0.5, ny))
            
            # Check if this is a farm cell
            cell_x, cell_y = int(nx), int(ny)
            if (cell_x, cell_y) not in self.state.farm_cells:
                return (nx, ny)
        
        # Fallback to any position if no non-farm cell found
        return (nx, ny)
    
    def _nearest_in_area(self, char, area, is_village=False):
        """Find the nearest unoccupied cell in an area. Returns float position (cell center).
        Falls back to occupied if none free.
        """
        best_free = None
        best_free_dist = float('inf')
        best_any = None
        best_any_dist = float('inf')
        
        for y in range(SIZE):
            for x in range(SIZE):
                if is_village:
                    in_area = self.state.is_in_village(x, y)
                else:
                    in_area = self.state.get_area_at(x, y) == area
                if in_area:
                    # Calculate distance to cell center
                    cx, cy = x + 0.5, y + 0.5
                    dist = math.sqrt((cx - char['x']) ** 2 + (cy - char['y']) ** 2)
                    is_occupied = self.state.is_occupied(x, y)
                    
                    if not is_occupied and dist < best_free_dist:
                        best_free_dist = dist
                        best_free = (cx, cy)
                    if dist < best_any_dist:
                        best_any_dist = dist
                        best_any = (cx, cy)
        
        return best_free if best_free else best_any
    
    def _nearest_ready_farm_cell(self, char):
        """Find nearest ready farm cell. Returns float position (cell center)."""
        # Check if character is already on a farm cell being worked
        char_cell = (int(char['x']), int(char['y']))
        cell = self.state.get_farm_cell_state(char_cell[0], char_cell[1])
        if cell and cell['state'] in ('ready', 'harvesting', 'replanting'):
            return None
        
        best = None
        best_dist = float('inf')
        for (cx, cy), data in self.state.farm_cells.items():
            if data['state'] == 'ready':
                # Distance to cell center
                center_x, center_y = cx + 0.5, cy + 0.5
                dist = math.sqrt((center_x - char['x']) ** 2 + (center_y - char['y']) ** 2)
                if dist < best_dist:
                    best_dist = dist
                    best = (center_x, center_y)
        return best
    
    def _step_toward(self, char, goal_x, goal_y):
        """
        Calculate the best single step toward a goal.
        Uses direct movement first (including diagonals), BFS if blocked.
        """
        x, y = char['x'], char['y']
        
        if x == goal_x and y == goal_y:
            return None
        
        # Build occupied set (we'll return moves into occupied cells for swap detection)
        occupied = set()
        for c in self.state.characters:
            if c != char:
                occupied.add((c['x'], c['y']))
        
        # Already adjacent to goal (including diagonally)
        if abs(x - goal_x) <= 1 and abs(y - goal_y) <= 1:
            return (goal_x, goal_y)
        
        dx = goal_x - x
        dy = goal_y - y
        
        # Build move priority list - diagonal moves are often the most direct
        moves = []
        
        # Normalize direction
        step_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
        step_y = 1 if dy > 0 else (-1 if dy < 0 else 0)
        
        # If we can move diagonally toward goal, that's usually best
        if step_x != 0 and step_y != 0:
            moves.append((step_x, step_y))  # Diagonal toward goal
        
        # Then try cardinal directions toward goal
        if abs(dx) >= abs(dy):
            if step_x != 0: moves.append((step_x, 0))
            if step_y != 0: moves.append((0, step_y))
        else:
            if step_y != 0: moves.append((0, step_y))
            if step_x != 0: moves.append((step_x, 0))
        
        # Add other diagonal moves as alternatives
        if step_x != 0 and step_y == 0:
            moves.extend([(step_x, 1), (step_x, -1)])
        elif step_y != 0 and step_x == 0:
            moves.extend([(1, step_y), (-1, step_y)])
        
        # Add perpendicular cardinal moves
        if step_x != 0 and step_y == 0:
            moves.extend([(0, 1), (0, -1)])
        elif step_y != 0 and step_x == 0:
            moves.extend([(1, 0), (-1, 0)])
        elif step_x == 0 and step_y == 0:
            # Already at goal - shouldn't happen but handle it
            moves = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        
        # Try direct/diagonal moves first
        for mdx, mdy in moves:
            nx, ny = x + mdx, y + mdy
            if self.state.is_position_valid(nx, ny):
                # Return even if occupied - swap detection handles it
                # But prefer unoccupied cells
                if (nx, ny) not in occupied:
                    return (nx, ny)
        
        # All direct moves blocked by other characters - try BFS to find path around
        parent = {(x, y): None}
        queue = deque([(x, y)])
        goal = (goal_x, goal_y)
        
        while queue:
            cx, cy = queue.popleft()
            
            for ddx, ddy in DIRECTIONS:
                nx, ny = cx + ddx, cy + ddy
                next_pos = (nx, ny)
                
                if not self.state.is_position_valid(nx, ny):
                    continue
                if next_pos in parent:
                    continue
                # Can path through goal, but not through other occupied cells
                if next_pos in occupied and next_pos != goal:
                    continue
                
                parent[next_pos] = (cx, cy)
                
                # Found goal or adjacent to goal (including diagonally)
                if next_pos == goal or (abs(nx - goal_x) <= 1 and abs(ny - goal_y) <= 1):
                    # Backtrack to find first step
                    pos = next_pos
                    while parent[pos] != (x, y):
                        pos = parent[pos]
                    return pos
                
                queue.append(next_pos)
        
        # No path found - try any valid move (for swap detection)
        for mdx, mdy in moves:
            nx, ny = x + mdx, y + mdy
            if self.state.is_position_valid(nx, ny):
                return (nx, ny)
        
        return None
    
    def _move_toward_point(self, char, point):
        """Move character one step toward a point (used for actions outside main loop)."""
        if point is None:
            return
        step = self._step_toward(char, point[0], point[1])
        if step and not self.state.is_occupied(step[0], step[1]):
            char['x'] = step[0]
            char['y'] = step[1]
    
    def move_toward_character(self, char, target):
        """Move character one step toward another character."""
        if target is None or target not in self.state.characters:
            return
        self._move_toward_point(char, (target['x'], target['y']))
    
    # =========================================================================
    # NPC ACTIONS (non-movement)
    # =========================================================================
    
    def _do_npc_actions(self, char):
        """Execute non-movement actions for an NPC."""
        # Check if character is still alive (may have been killed this tick)
        if char not in self.state.characters:
            return
        
        name = self.get_display_name(char)
        job = char.get('job')
        
        if char.get('is_frozen'):
            self._try_frozen_trade(char)
            return
        
        # Combat
        target = char.get('robbery_target')
        if target and target in self.state.characters:
            if self.is_adjacent(char, target):
                self._do_attack(char, target)
                return
        
        # Respond to attacker
        attacker = self.get_attacker(char)
        if attacker and self.is_adjacent(char, attacker):
            confidence = self.get_trait(char, 'confidence')
            if confidence >= 7:
                if not char.get('robbery_target'):
                    self.state.log_action(f"{name} FIGHTING BACK against {self.get_display_name(attacker)}!")
                char['robbery_target'] = attacker
                self._do_attack(char, attacker)
                return
        
        # Eat if hungry
        if char['hunger'] <= HUNGER_CHANCE_THRESHOLD and self.get_wheat(char) >= WHEAT_PER_BITE:
            self.remove_wheat(char, WHEAT_PER_BITE)
            char['hunger'] = min(MAX_HUNGER, char['hunger'] + HUNGER_PER_WHEAT)
            self.state.log_action(f"{name} ate from inventory, hunger now {char['hunger']:.0f}")
            return
        
        # Job-specific actions
        if job == 'Farmer':
            self._do_farmer_actions(char)
        elif job == 'Soldier':
            self._do_soldier_actions(char)
        elif job == 'Steward':
            self._do_steward_actions(char)
        elif job == 'Trader':
            # Traders can be promoted to steward
            if self.can_become_steward(char):
                self.become_steward(char)
            else:
                # Otherwise behave like unemployed
                self._do_unemployed_actions(char)
        else:
            self._do_unemployed_actions(char)
    
    def _do_farmer_actions(self, char):
        """Farmer actions."""
        name = self.get_display_name(char)
        steward = self.get_steward()
        farm_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('farm'))
        
        # Tax payment - only after first year
        if steward and self.is_adjacent(char, steward) and self.state.ticks >= STEWARD_TAX_INTERVAL:
            if not char.get('tax_paid_this_cycle', False) and char.get('allegiance') == PRIMARY_ALLEGIANCE:
                # Calculate total available wheat (inventory + barrel - farmer owns the barrel)
                farmer_wheat = self.get_wheat(char)
                barrel_wheat = self.state.get_barrel_wheat(farm_barrel) if farm_barrel else 0
                total_wheat = farmer_wheat + barrel_wheat
                
                if total_wheat >= STEWARD_TAX_AMOUNT:
                    # Pay tax - take from inventory first, then barrel
                    amount_needed = STEWARD_TAX_AMOUNT
                    from_inventory = min(farmer_wheat, amount_needed)
                    if from_inventory > 0:
                        self.remove_wheat(char, from_inventory)
                        amount_needed -= from_inventory
                    if amount_needed > 0 and farm_barrel:
                        self.state.remove_barrel_wheat(farm_barrel, amount_needed)
                    
                    self.add_wheat(steward, STEWARD_TAX_AMOUNT)
                    char['tax_late_ticks'] = 0
                    char['tax_paid_this_cycle'] = True
                    steward['tax_collection_target'] = None
                    self.state.log_action(f"{name} paid {STEWARD_TAX_AMOUNT} wheat tax")
                else:
                    self.state.log_action(f"{name} FAILED to pay tax! (had {total_wheat}, needed {STEWARD_TAX_AMOUNT})")
                    char['job'] = None
                    char['home'] = None
                    char['tax_late_ticks'] = 0
                    char['tax_paid_this_cycle'] = True
                    steward['tax_collection_target'] = None
                    # Remove bed ownership
                    self.state.unassign_bed_owner(char['name'])
                return
        
        # Deposit excess wheat into farm barrel when adjacent to it (only full stacks)
        if farm_barrel and self.state.is_adjacent_to_barrel(char, farm_barrel):
            farmer_wheat = self.get_wheat(char)
            excess = farmer_wheat - FARMER_PERSONAL_RESERVE
            # Only deposit if we have at least a full stack (15) excess
            if excess >= WHEAT_STACK_SIZE and self.state.can_barrel_add_wheat(farm_barrel, excess):
                self.remove_wheat(char, excess)
                self.state.add_barrel_wheat(farm_barrel, excess)
    
    def _do_soldier_actions(self, char):
        """Soldier actions.
        
        Soldiers no longer get wheat directly from the barrel.
        Instead, they request wheat from the steward and wait for delivery.
        The steward will come to them with food.
        """
        # Soldiers just wait - steward handles feeding them
        # Clear the wheat request flag when no longer hungry
        if char['hunger'] > HUNGER_CHANCE_THRESHOLD or self.get_wheat(char) >= WHEAT_PER_BITE:
            char['requested_wheat'] = False
    
    def _do_steward_actions(self, char):
        """Steward actions.
        
        Priority order:
        1. Feed adjacent hungry soldiers from inventory
        2. Get wheat from barrel for hungry soldiers (if not enough in inventory)
        3. Get wheat from barrel for self when hungry
        4. Tax collection
        5. Deposit excess wheat
        6. Buy wheat from farmers
        """
        name = self.get_display_name(char)
        
        # Priority 1: Feed adjacent hungry soldiers from inventory
        hungry_soldiers = self._get_soldiers_requesting_wheat()
        for soldier in hungry_soldiers:
            if self.is_adjacent(char, soldier):
                if self.get_wheat(char) >= SOLDIER_WHEAT_PAYMENT and self.can_add_wheat(soldier, SOLDIER_WHEAT_PAYMENT):
                    self.remove_wheat(char, SOLDIER_WHEAT_PAYMENT)
                    self.add_wheat(soldier, SOLDIER_WHEAT_PAYMENT)
                    soldier['requested_wheat'] = False
                    soldier_name = self.get_display_name(soldier)
                    self.state.log_action(f"Steward {name} gave {SOLDIER_WHEAT_PAYMENT} wheat to {soldier_name}")
                    return  # One action per tick
        
        # Priority 2: Get wheat from barrel for hungry soldiers (if not enough in inventory)
        if hungry_soldiers:
            total_needed = len(hungry_soldiers) * SOLDIER_WHEAT_PAYMENT
            steward_wheat = self.get_wheat(char)
            wheat_shortfall = total_needed - steward_wheat
            
            if wheat_shortfall > 0:
                barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
                if barracks_barrel and self.state.is_adjacent_to_barrel(char, barracks_barrel):
                    barrel_wheat = self.state.get_barrel_wheat(barracks_barrel)
                    # Take enough for all hungry soldiers (or as much as available)
                    amount_to_take = min(wheat_shortfall, barrel_wheat)
                    if amount_to_take > 0 and self.can_add_wheat(char, amount_to_take):
                        self.state.remove_barrel_wheat(barracks_barrel, amount_to_take)
                        self.add_wheat(char, amount_to_take)
                        self.state.log_action(f"Steward {name} took {amount_to_take} wheat from barrel for soldiers")
                        return  # One action per tick
        
        # Priority 3: Get wheat from barracks barrel when adjacent to it and hungry
        if char['hunger'] <= HUNGER_CHANCE_THRESHOLD and self.get_wheat(char) < WHEAT_PER_BITE:
            barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
            if barracks_barrel and self.state.is_adjacent_to_barrel(char, barracks_barrel):
                if self.state.get_barrel_wheat(barracks_barrel) >= SOLDIER_WHEAT_PAYMENT:
                    if self.can_add_wheat(char, SOLDIER_WHEAT_PAYMENT):
                        self.state.remove_barrel_wheat(barracks_barrel, SOLDIER_WHEAT_PAYMENT)
                        self.add_wheat(char, SOLDIER_WHEAT_PAYMENT)
                        self.state.log_action(f"Steward {name} took {SOLDIER_WHEAT_PAYMENT} wheat from barracks barrel")
                        return
        
        # Priority 4: Tax collection - only after first year
        target = char.get('tax_collection_target')
        if target and target in self.state.characters and self.is_adjacent(char, target) and self.state.ticks >= STEWARD_TAX_INTERVAL:
            target_name = self.get_display_name(target)
            if not target.get('tax_paid_this_cycle', False):
                if self.get_wheat(target) >= STEWARD_TAX_AMOUNT:
                    self.remove_wheat(target, STEWARD_TAX_AMOUNT)
                    self.add_wheat(char, STEWARD_TAX_AMOUNT)
                    target['tax_late_ticks'] = 0
                    target['tax_paid_this_cycle'] = True
                    char['tax_collection_target'] = None
                    self.state.log_action(f"Steward {name} collected tax from {target_name}")
                else:
                    target['job'] = None
                    target['home'] = None
                    target['tax_late_ticks'] = 0
                    target['tax_paid_this_cycle'] = True
                    char['tax_collection_target'] = None
                    # Remove bed ownership
                    self.state.unassign_bed_owner(target['name'])
            return
        
        # Priority 5: Deposit wheat into barracks barrel when adjacent to it (only if no hungry soldiers)
        if not hungry_soldiers:
            barracks_barrel = self.state.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
            if barracks_barrel and self.state.is_adjacent_to_barrel(char, barracks_barrel):
                # Keep some personal wheat (3 wheat = 1 day buffer), deposit the rest
                personal_wheat = self.get_wheat(char)
                personal_reserve = 3  # 1 day of wheat
                excess = personal_wheat - personal_reserve
                if excess > 0 and self.state.can_barrel_add_wheat(barracks_barrel, excess):
                    self.remove_wheat(char, excess)
                    self.state.add_barrel_wheat(barracks_barrel, excess)
                    self.state.log_action(f"Steward {name} deposited {excess} wheat into barracks barrel")
                    return
        
        # Priority 6: Buy wheat from farmers
        if self.steward_needs_to_buy_wheat(char) and self.can_afford_any_wheat(char):
            farmer = self.find_adjacent_farmer(char)
            if farmer and self.farmer_willing_to_trade(farmer, char):
                amount = self.get_max_trade_amount(farmer, char)
                if amount > 0:
                    price = int(amount * WHEAT_PRICE_PER_UNIT)
                    self.execute_trade(farmer, char, amount)
                    self.state.log_action(f"Steward {name} bought {amount} wheat for ${price}")
    
    def _do_unemployed_actions(self, char):
        """Unemployed character actions."""
        name = self.get_display_name(char)
        
        # Try to get a job (unified system picks best available by tier)
        if self.wants_job(char):
            best_job = self.get_best_available_job(char)
            if best_job == 'Steward' and self.can_become_steward(char):
                self.become_steward(char)
                return
            elif best_job == 'Trader' and self.can_become_trader(char):
                self.become_trader(char)
                return
            elif best_job == 'Soldier' and self.can_enlist_as_soldier(char):
                self.enlist_as_soldier(char)
                return
            elif best_job == 'Farmer' and self.can_enlist_as_farmer(char):
                self.enlist_as_farmer(char)
                return
        
        # Seek wheat if hungry OR if wheat buffer is low
        is_hungry = self.should_seek_wheat(char) and self.get_wheat(char) < WHEAT_PER_BITE
        needs_buffer = self.needs_wheat_buffer(char)
        
        if is_hungry or needs_buffer:
            # Try to buy from adjacent vendor (Farmer, Trader, Innkeeper, etc.)
            if self.can_afford_any_wheat(char):
                vendor = self.find_adjacent_vendor(char, 'wheat')
                if vendor and self.vendor_willing_to_trade(vendor, char, 'wheat'):
                    amount = self.get_max_vendor_trade_amount(vendor, char, 'wheat')
                    if amount > 0:
                        price = self.get_goods_price('wheat', amount)
                        self.execute_vendor_trade(vendor, char, 'wheat', amount)
                        char['wheat_seek_ticks'] = 0
                        self.state.log_action(f"{name} bought {amount} wheat for ${price} from {self.get_display_name(vendor)}")
                        return
            
            # Only consider crime if actually hungry (not just buffering) and can't buy
            if is_hungry:
                can_buy = self.can_afford_any_wheat(char) and self.find_willing_vendor(char, 'wheat') is not None
                if not can_buy:
                    # Don't re-roll if already pursuing a crime
                    if char.get('theft_target'):
                        self.continue_theft(char)
                    elif char.get('robbery_target'):
                        self.continue_robbery(char)
                    else:
                        # Decide on new crime
                        crime = self.decide_crime_action(char)
                        if crime == 'theft':
                            self.try_farm_theft(char)
                        elif crime == 'robbery':
                            self.try_robbery(char)
    
    def _try_frozen_trade(self, char):
        """Frozen character tries to trade with any adjacent wheat vendor."""
        if self.can_afford_any_wheat(char):
            vendor = self.find_adjacent_vendor(char, 'wheat')
            if vendor and self.vendor_willing_to_trade(vendor, char, 'wheat'):
                amount = self.get_max_vendor_trade_amount(vendor, char, 'wheat')
                if amount > 0:
                    self.execute_vendor_trade(vendor, char, 'wheat', amount)
                    name = self.get_display_name(char)
                    self.state.log_action(f"{name} (frozen) bought {amount} wheat!")
                    if self.get_wheat(char) >= WHEAT_PER_BITE:
                        self.remove_wheat(char, WHEAT_PER_BITE)
                        char['hunger'] = min(MAX_HUNGER, char['hunger'] + HUNGER_PER_WHEAT)
                        char['is_starving'] = False
                        char['is_frozen'] = False
                        self.state.log_action(f"{name} recovered from starvation!")
    
    def _do_attack(self, attacker, target):
        """Execute an attack."""
        import time
        
        attacker_name = self.get_display_name(attacker)
        target_name = self.get_display_name(target)
        
        # Start attack animation
        attacker['attack_animation_start'] = time.time()
        # Calculate attack direction toward target
        dx = target['x'] - attacker['x']
        dy = target['y'] - attacker['y']
        if abs(dx) > abs(dy):
            attacker['attack_direction'] = 'right' if dx > 0 else 'left'
        else:
            attacker['attack_direction'] = 'down' if dy > 0 else 'up'
        
        damage = random.randint(2, 5)  # Reduced damage (was 10-20)
        target['health'] -= damage
        self.state.log_action(f"{attacker_name} ATTACKS {target_name} for {damage}! HP: {target['health']}")
        
        if target['health'] <= 0:
            attacker_is_defender = not attacker.get('is_aggressor', False)
            target_was_criminal = target.get('is_aggressor', False) or target.get('is_murderer', False) or target.get('is_thief', False)
            
            if attacker_is_defender and target_was_criminal:
                self.state.log_action(f"{attacker_name} KILLED {target_name} (justified)!")
            else:
                attacker['is_murderer'] = True
                self.state.log_action(f"{attacker_name} KILLED {target_name}!")
                self.witness_murder(attacker, target)
            
            # Transfer items
            self.state.transfer_all_items(target, attacker)
            self.state.remove_character(target)
            attacker['robbery_target'] = None
            attacker['is_aggressor'] = False

    
    # =========================================================================
    # TICK PROCESSING
    # =========================================================================
    
    def process_tick(self):
        """Process one game tick - updates all game state"""
        self.state.ticks += 1
        
        # Update hunger for all characters
        for char in self.state.characters:
            char['hunger'] = max(0, char['hunger'] - HUNGER_DECAY)
        
        # Process starvation
        self._process_starvation()
        
        # Update farm cells
        self._update_farm_cells()
        
        # Tax collection check - skip first year (taxes due at end of each year, not start)
        if self.state.ticks > 0 and self.state.ticks % STEWARD_TAX_INTERVAL == 0:
            self.collect_steward_tax()
            for char in self.state.characters:
                if char.get('job') == 'Soldier':
                    char['paid_this_cycle'] = False
        
        # Age increment
        if self.state.ticks > 0 and self.state.ticks % TICKS_PER_YEAR == 0:
            for char in self.state.characters:
                char['age'] += 1
            self.state.log_action(f"A new year begins! Everyone is one year older.")
        
        # Check for late tax payments
        steward = self.get_steward()
        for char in self.state.characters:
            if char.get('job') == 'Farmer' and char.get('allegiance') == PRIMARY_ALLEGIANCE and char.get('tax_late_ticks', 0) > 0:
                if not char.get('tax_paid_this_cycle', False):
                    char['tax_late_ticks'] += 1
                    if char['tax_late_ticks'] >= TAX_GRACE_PERIOD and steward:
                        if steward.get('tax_collection_target') != char:
                            steward_name = self.get_display_name(steward)
                            char_name = self.get_display_name(char)
                            self.state.log_action(f"Steward {steward_name} going to collect from {char_name}! (late {char['tax_late_ticks']} ticks)")
                            steward['tax_collection_target'] = char
        
        # Handle deaths (now health-based, not hunger-based)
        dead_chars = [c for c in self.state.characters if c['health'] <= 0]
        for dead in dead_chars:
            dead_name = self.get_display_name(dead)
            if self.is_player(dead):
                if dead.get('is_starving'):
                    self.state.log_action(f"{dead_name} (PLAYER) DIED from starvation! GAME OVER")
                else:
                    self.state.log_action(f"{dead_name} (PLAYER) DIED! GAME OVER")
            else:
                if dead.get('is_starving'):
                    self.state.log_action(f"{dead_name} DIED from starvation!")
                else:
                    self.state.log_action(f"{dead_name} DIED!")
            self.state.remove_character(dead)
        
        # Move NPCs with swap detection to prevent oscillation
        self._process_npc_movement()
    
    def _process_starvation(self):
        """Process starvation for all characters"""
        for char in self.state.characters:
            name = self.get_display_name(char)
            
            # Check if character should enter starvation (hunger = 0)
            if char['hunger'] <= STARVATION_THRESHOLD:
                was_starving = char.get('is_starving', False)
                
                if not was_starving:
                    # Just entered starvation
                    char['is_starving'] = True
                    char['starvation_health_lost'] = 0
                    char['ticks_starving'] = 0
                    self.state.log_action(f"{name} is STARVING! Losing health...")
                    
                    # Soldiers quit when they start starving - lose job, allegiance, and home
                    if char.get('job') == 'Soldier':
                        char['job'] = None
                        char['allegiance'] = None
                        char['home'] = None
                        # Remove bed ownership
                        self.state.unassign_bed_owner(char['name'])
                        self.state.log_action(f"{name} QUIT being a Soldier due to starvation!")
                
                # Increment ticks starving
                char['ticks_starving'] = char.get('ticks_starving', 0) + 1
                
                # Apply starvation damage
                char['health'] -= STARVATION_DAMAGE
                char['starvation_health_lost'] += STARVATION_DAMAGE
                
                # Check if should freeze (health <= 20)
                if char['health'] <= STARVATION_FREEZE_HEALTH:
                    if not char.get('is_frozen', False):
                        char['is_frozen'] = True
                        # Clear any combat state when freezing
                        char['robbery_target'] = None
                        char['is_aggressor'] = False
                        self.state.log_action(f"{name} is too weak to move! (health: {char['health']})")
                
                # Check for morality loss every STARVATION_MORALITY_INTERVAL health lost
                if char['starvation_health_lost'] >= STARVATION_MORALITY_INTERVAL:
                    char['starvation_health_lost'] -= STARVATION_MORALITY_INTERVAL
                    if random.random() < STARVATION_MORALITY_CHANCE:
                        old_morality = char.get('morality', 5)
                        if old_morality > 1:
                            char['morality'] = old_morality - 1
                            self.state.log_action(f"{name}'s morality dropped from {old_morality} to {char['morality']} due to starvation!")
            else:
                # Not starving anymore
                if char.get('is_starving', False):
                    char['is_starving'] = False
                    char['is_frozen'] = False
                    char['starvation_health_lost'] = 0
                    char['ticks_starving'] = 0
    
    def _update_farm_cells(self):
        """Update all farm cell states"""
        for cell, data in self.state.farm_cells.items():
            if data['state'] == 'growing':
                data['timer'] -= 1
                if data['timer'] <= 0:
                    data['state'] = 'ready'
                    data['timer'] = 0
        
        # Process characters standing on farm cells
        # Only farmers can legitimately harvest - others (including player) commit theft
        cells_being_worked = set()
        for char in self.state.characters:
            # Convert float position to cell coordinates
            cell = (int(char['x']), int(char['y']))
            if cell in self.state.farm_cells and cell not in cells_being_worked:
                data = self.state.farm_cells[cell]
                
                # Only farmers can work farm cells without it being theft
                is_farmer = char.get('job') == 'Farmer'
                is_player = self.is_player(char)
                
                if not is_farmer and not is_player:
                    continue  # Non-farmers/non-players use try_farm_theft via AI
                
                if data['state'] == 'ready':
                    # Check if can carry more wheat
                    if not self.can_add_wheat(char, FARM_CELL_YIELD):
                        continue  # Inventory full, can't harvest
                    data['state'] = 'harvesting'
                    data['timer'] = FARM_HARVEST_TIME
                    data['harvester'] = char  # Track who started harvesting
                    cells_being_worked.add(cell)
                
                elif data['state'] == 'harvesting':
                    data['timer'] -= 1
                    if data['timer'] <= 0:
                        # Check inventory space before adding wheat
                        if self.can_add_wheat(char, FARM_CELL_YIELD):
                            self.add_wheat(char, FARM_CELL_YIELD)
                            data['state'] = 'replanting'
                            data['timer'] = FARM_REPLANT_TIME
                            
                            name = self.get_display_name(char)
                            
                            # If player (and not farmer), this is theft!
                            if is_player and not is_farmer:
                                char['is_thief'] = True
                                self.state.log_action(f"{name} STOLE {FARM_CELL_YIELD} wheat from farm!")
                                # Trigger witness system for theft
                                self.witness_theft(char, cell)
                            elif is_player:
                                self.state.log_action(f"{name} harvested {FARM_CELL_YIELD} wheat!")
                        else:
                            # Can't harvest, leave cell ready
                            data['state'] = 'ready'
                    cells_being_worked.add(cell)
                
                elif data['state'] == 'replanting':
                    data['timer'] -= 1
                    if data['timer'] <= 0:
                        data['state'] = 'growing'
                        data['timer'] = FARM_CELL_HARVEST_INTERVAL
                    cells_being_worked.add(cell)
    
    # =========================================================================
    # PLAYER ACTIONS
    # =========================================================================
    
    def move_player(self, dx, dy, sprinting=False):
        """Set player velocity for ALTTP-style movement.
        Called by GUI when movement keys are held.
        dx, dy should be -1, 0, or 1 indicating direction.
        sprinting: if True, use SPRINT_SPEED instead of MOVEMENT_SPEED.
        Returns True if velocity was set successfully.
        """
        player = self.state.player
        if not player:
            return False
        
        # Update facing direction based on movement attempt (even if blocked)
        if dx > 0 and dy < 0:
            player['facing'] = 'up-right'
        elif dx > 0 and dy > 0:
            player['facing'] = 'down-right'
        elif dx < 0 and dy < 0:
            player['facing'] = 'up-left'
        elif dx < 0 and dy > 0:
            player['facing'] = 'down-left'
        elif dx > 0:
            player['facing'] = 'right'
        elif dx < 0:
            player['facing'] = 'left'
        elif dy > 0:
            player['facing'] = 'down'
        elif dy < 0:
            player['facing'] = 'up'
        
        # Can't move while frozen (starving + health <= 20)
        if player.get('is_frozen', False):
            name = self.get_display_name(player)
            self.state.log_action(f"{name} is too weak to move!")
            player['vx'] = 0.0
            player['vy'] = 0.0
            return False
        
        # Use sprint speed if sprinting
        speed = SPRINT_SPEED if sprinting else MOVEMENT_SPEED
        
        # Normalize diagonal movement to maintain consistent speed (ALTTP style)
        if dx != 0 and dy != 0:
            # Diagonal: multiply by 1/sqrt(2) to maintain same speed as cardinal
            diagonal_factor = 1.0 / math.sqrt(2)
            player['vx'] = dx * speed * diagonal_factor
            player['vy'] = dy * speed * diagonal_factor
        else:
            # Cardinal: full speed
            player['vx'] = dx * speed
            player['vy'] = dy * speed
        
        return True
    
    def stop_player(self):
        """Stop player movement (called when no movement keys are held)."""
        player = self.state.player
        if player:
            player['vx'] = 0.0
            player['vy'] = 0.0
    
    def update_player_position(self, dt):
        """Update player position based on velocity and delta time.
        Called every frame by the GUI.
        
        Args:
            dt: Delta time in seconds
        """
        player = self.state.player
        if not player:
            return
        
        vx = player.get('vx', 0.0)
        vy = player.get('vy', 0.0)
        
        if vx == 0.0 and vy == 0.0:
            return
        
        # Calculate new position
        new_x = player['x'] + vx * dt
        new_y = player['y'] + vy * dt
        
        # Keep within bounds
        half_width = player.get('width', CHARACTER_WIDTH) / 2
        half_height = player.get('height', CHARACTER_HEIGHT) / 2
        new_x = max(half_width, min(SIZE - half_width, new_x))
        new_y = max(half_height, min(SIZE - half_height, new_y))
        
        # Check for collision with other characters
        if not self.state.is_position_blocked(new_x, new_y, exclude_char=player):
            player['x'] = new_x
            player['y'] = new_y
        else:
            # Blocked - try to slide/jostle around (ALTTP style bumping)
            moved = False
            
            # Try sliding along primary movement axis first
            if abs(vx) > abs(vy):
                # Moving mostly horizontal - try X first, then Y
                if not self.state.is_position_blocked(new_x, player['y'], exclude_char=player):
                    player['x'] = new_x
                    moved = True
                elif not self.state.is_position_blocked(player['x'], new_y, exclude_char=player):
                    player['y'] = new_y
                    moved = True
            else:
                # Moving mostly vertical - try Y first, then X
                if not self.state.is_position_blocked(player['x'], new_y, exclude_char=player):
                    player['y'] = new_y
                    moved = True
                elif not self.state.is_position_blocked(new_x, player['y'], exclude_char=player):
                    player['x'] = new_x
                    moved = True
            
            # If still blocked, try perpendicular jostling
            if not moved:
                jostle_amount = MOVEMENT_SPEED * dt * 0.3
                if abs(vx) > abs(vy):
                    # Moving horizontal, jostle vertical
                    for jostle_dir in [1, -1]:
                        jostle_y = player['y'] + jostle_dir * jostle_amount
                        if not self.state.is_position_blocked(player['x'], jostle_y, exclude_char=player):
                            player['y'] = jostle_y
                            break
                else:
                    # Moving vertical, jostle horizontal
                    for jostle_dir in [1, -1]:
                        jostle_x = player['x'] + jostle_dir * jostle_amount
                        if not self.state.is_position_blocked(jostle_x, player['y'], exclude_char=player):
                            player['x'] = jostle_x
                            break
    
    def player_eat(self):
        """Player eats from inventory. Returns True if ate."""
        player = self.state.player
        if not player:
            return False
        
        name = self.get_display_name(player)
        
        if self.get_wheat(player) >= WHEAT_PER_BITE:
            self.remove_wheat(player, WHEAT_PER_BITE)
            player['hunger'] = min(MAX_HUNGER, player['hunger'] + HUNGER_PER_WHEAT)
            
            # Check if this recovered from starvation
            if player['hunger'] > STARVATION_THRESHOLD:
                if player.get('is_starving', False) or player.get('is_frozen', False):
                    player['is_starving'] = False
                    player['is_frozen'] = False
                    player['starvation_health_lost'] = 0
                    player['ticks_starving'] = 0
                    self.state.log_action(f"{name} ate and recovered from starvation! Hunger: {player['hunger']:.0f}")
                else:
                    self.state.log_action(f"{name} ate from inventory, hunger now {player['hunger']:.0f}")
            else:
                self.state.log_action(f"{name} ate from inventory, hunger now {player['hunger']:.0f}")
            return True
        return False
    
    def player_trade(self):
        """Player attempts to trade with adjacent wheat vendor. Returns True if traded."""
        player = self.state.player
        if not player:
            return False
        
        name = self.get_display_name(player)
        
        # Find any adjacent vendor selling wheat
        vendor = self.find_adjacent_vendor(player, 'wheat')
        
        if vendor and self.can_afford_any_wheat(player):
            vendor_name = self.get_display_name(vendor)
            if self.vendor_willing_to_trade(vendor, player, 'wheat'):
                amount = self.get_max_vendor_trade_amount(vendor, player, 'wheat')
                if amount > 0:
                    price = self.get_goods_price('wheat', amount)
                    self.execute_vendor_trade(vendor, player, 'wheat', amount)
                    self.state.log_action(f"{name} bought {amount} wheat for ${price} from {vendor_name}")
                    
                    # If starving/frozen, auto-eat to try to recover
                    if (player.get('is_starving', False) or player.get('is_frozen', False)) and self.get_wheat(player) >= WHEAT_PER_BITE:
                        self.remove_wheat(player, WHEAT_PER_BITE)
                        player['hunger'] = min(MAX_HUNGER, player['hunger'] + HUNGER_PER_WHEAT)
                        if player['hunger'] > STARVATION_THRESHOLD:
                            player['is_starving'] = False
                            player['is_frozen'] = False
                            player['starvation_health_lost'] = 0
                            player['ticks_starving'] = 0
                            self.state.log_action(f"{name} ate and recovered from starvation! Hunger: {player['hunger']:.0f}")
                    
                    return True
            else:
                self.state.log_action(f"{name} tried to trade but {vendor_name} refused")
        return False
    
    def player_attack(self):
        """Player swings sword in facing direction. Returns True if swung."""
        import time
        
        player = self.state.player
        if not player:
            return False
        
        # Check if already attacking (animation in progress)
        anim_start = player.get('attack_animation_start')
        if anim_start is not None:
            elapsed = time.time() - anim_start
            if elapsed < ATTACK_ANIMATION_DURATION:
                return False  # Still animating
        
        name = self.get_display_name(player)
        facing = player.get('facing', 'down')
        
        # Start attack animation
        player['attack_animation_start'] = time.time()
        player['attack_direction'] = self._facing_to_attack_direction(facing)
        
        # Calculate attack hitbox based on facing direction
        attack_range = COMBAT_RANGE
        targets_hit = []
        
        # Get attack direction vector
        dx, dy = self._get_direction_vector(facing)
        
        # Check for targets in the attack area
        for char in self.state.characters:
            if char is player:
                continue
            
            # Calculate distance in the attack direction
            rel_x = char['x'] - player['x']
            rel_y = char['y'] - player['y']
            
            # Project onto attack direction
            if dx != 0 or dy != 0:
                # Distance along attack direction
                proj_dist = rel_x * dx + rel_y * dy
                
                # Perpendicular distance (for width of swing)
                perp_dist = abs(rel_x * (-dy) + rel_y * dx)
                
                # Hit if within range in attack direction and within swing width
                if 0 < proj_dist <= attack_range and perp_dist < 0.7:
                    targets_hit.append(char)
        
        # Deal damage to all targets hit
        if targets_hit:
            for target in targets_hit:
                target_name = self.get_display_name(target)
                damage = random.randint(2, 5)
                target['health'] -= damage
                self.state.log_action(f"{name} ATTACKS {target_name} for {damage}! HP: {target['health']}")
                
                # Check if target was already a criminal before this attack
                target_was_criminal = target.get('is_aggressor', False) or target.get('is_murderer', False) or target.get('is_thief', False)
                
                # If attacking an innocent, mark as aggressor and alert witnesses
                if not target_was_criminal and not player.get('is_aggressor'):
                    player['is_aggressor'] = True
                    self.witness_murder(player, target)
                
                if target['health'] <= 0:
                    if target_was_criminal:
                        self.state.log_action(f"{name} KILLED {target_name} (justified)!")
                    else:
                        player['is_murderer'] = True
                        self.state.log_action(f"{name} KILLED {target_name}!")
                    
                    # Transfer items
                    self.state.transfer_all_items(target, player)
                    self.state.remove_character(target)
            return True
        else:
            self.state.log_action(f"{name} swings sword (missed)")
            return True
    
    def _facing_to_attack_direction(self, facing):
        """Convert facing direction to attack direction."""
        if facing in ('up', 'up-left', 'up-right'):
            return 'up'
        elif facing in ('down', 'down-left', 'down-right'):
            return 'down'
        elif facing in ('left',):
            return 'left'
        elif facing in ('right',):
            return 'right'
        # Handle diagonal facings
        if 'left' in facing:
            return 'left'
        if 'right' in facing:
            return 'right'
        return 'down'
    
    def _get_direction_vector(self, facing):
        """Get unit direction vector for a facing direction."""
        vectors = {
            'up': (0, -1),
            'down': (0, 1),
            'left': (-1, 0),
            'right': (1, 0),
            'up-left': (-0.707, -0.707),
            'up-right': (0.707, -0.707),
            'down-left': (-0.707, 0.707),
            'down-right': (0.707, 0.707),
        }
        return vectors.get(facing, (0, 1))