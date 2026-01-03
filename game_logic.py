# game_logic.py - All game logic: AI, combat, trading, movement
"""
This module contains all game logic that operates on GameState.
It does NOT hold any state itself - all state is in GameState.
It does NOT contain any rendering code.
"""

import random
import math
import time
from collections import deque
from constants import (
    DIRECTIONS, ITEMS,
    MAX_HUNGER, HUNGER_DECAY, HUNGER_CRITICAL, HUNGER_CHANCE_THRESHOLD,
    STARVATION_THRESHOLD, STARVATION_DAMAGE, STARVATION_MORALITY_INTERVAL, 
    STARVATION_MORALITY_CHANCE, STARVATION_FREEZE_HEALTH,
    INVENTORY_SLOTS,
    FARM_CELL_YIELD,
    FARM_CELL_HARVEST_INTERVAL, FARM_HARVEST_TIME, FARM_REPLANT_TIME,
    TRADE_COOLDOWN,
    STEWARD_TAX_INTERVAL, STEWARD_TAX_AMOUNT, SOLDIER_WHEAT_PAYMENT, TAX_GRACE_PERIOD,
    ALLEGIANCE_WHEAT_TIMEOUT, TICKS_PER_DAY, TICKS_PER_YEAR,
    CRIME_INTENSITY_MURDER, CRIME_INTENSITY_THEFT,
    THEFT_PATIENCE_TICKS, THEFT_COOLDOWN_TICKS,
    SLEEP_START_FRACTION,
    MOVEMENT_SPEED, SPRINT_SPEED, ADJACENCY_DISTANCE, COMBAT_RANGE,
    CHARACTER_WIDTH, CHARACTER_HEIGHT, CHARACTER_COLLISION_RADIUS,
    UPDATE_INTERVAL, TICK_MULTIPLIER,
    VENDOR_GOODS,
    IDLE_SPEED_MULTIPLIER, IDLE_MIN_WAIT_TICKS, IDLE_MAX_WAIT_TICKS,
    IDLE_PAUSE_CHANCE, IDLE_PAUSE_MIN_TICKS, IDLE_PAUSE_MAX_TICKS,
    SQUEEZE_THRESHOLD_TICKS, SQUEEZE_SLIDE_SPEED,
    ATTACK_ANIMATION_DURATION, ATTACK_COOLDOWN_TICKS,
    WHEAT_TO_BREAD_RATIO,
    BREAD_PER_BITE, BREAD_BUFFER_TARGET,
    PATROL_SPEED_MULTIPLIER, PATROL_CHECK_MIN_TICKS, PATROL_CHECK_MAX_TICKS,
    PATROL_CHECK_CHANCE, PATROL_APPROACH_DISTANCE
)
from scenario_world import SIZE
from scenario_characters import CHARACTER_TEMPLATES
from jobs import get_job


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
    
    def can_attack(self, char):
        """Check if character can attack (not on cooldown).
        Returns True if enough time has passed since last attack.
        """
        last_attack_tick = char.get('last_attack_tick', -ATTACK_COOLDOWN_TICKS)
        return self.state.ticks - last_attack_tick >= ATTACK_COOLDOWN_TICKS
    
    def resolve_attack(self, attacker, attack_direction=None):
        """Resolve an attack from a character.
        
        This is the unified attack resolution used by BOTH player and NPCs.
        Handles: finding targets, dealing damage, witnesses, death, loot.
        
        Args:
            attacker: Character performing the attack
            attack_direction: Optional direction ('up', 'down', 'left', 'right')
                            If None, uses attacker's current facing
        
        Returns:
            List of characters that were hit
        """
        if attack_direction is None:
            attack_direction = attacker.get('facing', 'down')
        
        attacker_name = attacker.get_display_name()
        
        # Get direction vector
        dx, dy = self._get_direction_vector(attack_direction)
        
        # Find targets in attack arc
        targets_hit = []
        for char in self.state.characters:
            if char is attacker:
                continue
            
            # Skip dying characters
            if char.get('health', 100) <= 0:
                continue
            
            # Calculate relative position
            rel_x = char.x - attacker.x
            rel_y = char.y - attacker.y
            
            # Project onto attack direction
            if dx != 0 or dy != 0:
                proj_dist = rel_x * dx + rel_y * dy  # Distance along attack direction
                perp_dist = abs(rel_x * (-dy) + rel_y * dx)  # Perpendicular distance
                
                # Hit if within range in attack direction and within swing width
                if 0 < proj_dist <= COMBAT_RANGE and perp_dist < 0.7:
                    targets_hit.append(char)
        
        # Log miss if no targets
        if not targets_hit:
            self.state.log_action(f"{attacker_name} swings sword (missed)")
            return []
        
        # Determine if attacker is a criminal
        attacker_is_criminal = (
            attacker.get('is_aggressor', False) or 
            attacker.get('is_murderer', False) or 
            attacker.get('is_thief', False)
        )
        
        # Deal damage to all targets
        for target in targets_hit:
            target_name = target.get_display_name()
            
            # Calculate and apply damage
            damage = random.randint(2, 5)
            target.health -= damage
            self.state.log_action(f"{attacker_name} ATTACKS {target_name} for {damage}! HP: {target.health}")
            
            # Set attacker's robbery_target so victim can detect and respond
            # Only set if attacker doesn't already have a target (first hit)
            if attacker.get('robbery_target') is None and target.health > 0:
                attacker.robbery_target = target
            
            # Check if target was a criminal
            target_was_criminal = (
                target.get('is_aggressor', False) or 
                target.get('is_murderer', False) or 
                target.get('is_thief', False)
            )
            
            # If attacking an innocent, mark as aggressor
            if not target_was_criminal and not attacker_is_criminal:
                attacker.is_aggressor = True
                attacker_is_criminal = True
                # Witness non-lethal attack if target survives
                if target.health > 0:
                    self.witness_murder(attacker, target, is_lethal=False)
            
            # Handle death
            if target.health <= 0:
                if target_was_criminal and not attacker_is_criminal:
                    # Justified kill
                    self.state.log_action(f"{attacker_name} killed {target_name} (justified)")
                else:
                    attacker.is_murderer = True
                    self.witness_murder(attacker, target, is_lethal=True)
                
                # Transfer items to attacker
                attacker.transfer_all_items_from(target)
                
                # Clear robbery_target if this was the target
                if attacker.get('robbery_target') == target:
                    attacker.robbery_target = None
        
        return targets_hit
    
    def resolve_melee_attack(self, attacker, target):
        """Resolve a direct melee attack against a specific target.
        
        Used by NPCs who have a specific target (robbery, combat).
        
        Args:
            attacker: Character performing the attack
            target: Character being attacked
            
        Returns:
            dict with 'hit', 'damage', 'killed' keys
        """
        result = {'hit': False, 'damage': 0, 'killed': False}
        
        if target is None or target not in self.state.characters:
            return result
        
        if target.get('health', 100) <= 0:
            return result
        
        attacker_name = attacker.get_display_name()
        target_name = target.get_display_name()
        
        # Check if in range
        if not self.is_adjacent(attacker, target):
            return result
        
        result['hit'] = True
        
        # Apply damage
        damage = random.randint(2, 5)
        result['damage'] = damage
        target.health -= damage
        self.state.log_action(f"{attacker_name} ATTACKS {target_name} for {damage} damage! Health: {target.health + damage} -> {target.health}")
        
        # Check criminal status
        attacker_is_criminal = (
            attacker.get('is_aggressor', False) or 
            attacker.get('is_murderer', False) or 
            attacker.get('is_thief', False)
        )
        target_was_criminal = (
            target.get('is_aggressor', False) or 
            target.get('is_murderer', False) or 
            target.get('is_thief', False)
        )
        
        # Handle death
        if target.health <= 0:
            result['killed'] = True
            
            if not attacker_is_criminal and target_was_criminal:
                self.state.log_action(f"{attacker_name} killed {target_name} (justified)")
            else:
                attacker.is_murderer = True
                self.witness_murder(attacker, target, is_lethal=True)
            
            # Transfer items
            attacker.transfer_all_items_from(target)
        
        return result
    
    def get_adjacent_character(self, char):
        """Get any character adjacent to the given character (within ADJACENCY_DISTANCE)"""
        for other in self.state.characters:
            if other != char and self.is_adjacent(char, other):
                return other
        return None
    
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
    
    def get_sleep_position(self, char):
        """Get the position where this character should sleep.
        Returns bed position if they own one, camp position if they have one, None otherwise.
        """
        # Check for owned bed
        bed = self.state.get_character_bed(char)
        if bed:
            return bed.position
        
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
            name = char.get_display_name()
            self.state.log_action(f"{name} made a camp at ({cell_x}, {cell_y})")
            return True
        return False
    
    # =========================================================================
    # STOVE / CAMPFIRE BAKING SYSTEM
    # =========================================================================
    
    def get_adjacent_camp(self, char):
        """Get any camp adjacent to the character.
        Returns (camp_position, owner_char) tuple or (None, None).
        Note: Camps are stored on characters, not in interactables.
        """
        for other_char in self.state.characters:
            camp_pos = other_char.get('camp_position')
            if camp_pos and self.state.interactables.is_adjacent_to_camp(char, camp_pos):
                return camp_pos, other_char
        return None, None
    
    def get_adjacent_cooking_spot(self, char):
        """Get any adjacent cooking spot (stove the char can use, or any campfire).
        Returns a dict with 'type' ('stove' or 'camp'), 'name', and source object.
        Returns None if no cooking spot is adjacent.
        """
        # Check for stove first - must be one the character can use
        stove = self.state.interactables.get_adjacent_stove(char)
        if stove and stove.can_use(char):
            return {
                'type': 'stove',
                'name': stove.name,
                'source': stove
            }
        
        # Check for any campfire (anyone can use any campfire)
        camp_pos, camp_owner = self.get_adjacent_camp(char)
        if camp_pos:
            owner_name = camp_owner.get_display_name() if camp_owner else 'unknown'
            return {
                'type': 'camp',
                'name': f"{owner_name}'s campfire",
                'source': camp_pos
            }
        
        return None
    
    def can_bake_bread(self, char):
        """Check if character can bake bread right now.
        Requirements: adjacent to a stove (that they can use) or campfire, has wheat, has space for bread.
        """
        # Must be adjacent to a cooking spot (stove or camp)
        cooking_spot = self.get_adjacent_cooking_spot(char)
        if not cooking_spot:
            return False
        
        # Must have wheat to convert
        if char.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
            return False
        
        # Must have space for bread
        if not char.can_add_item('bread', 1):
            return False
        
        return True
    
    def bake_bread(self, char, amount=1):
        """Convert wheat into bread at a stove or campfire.
        Character must be adjacent to a cooking spot they can use.
        Returns the amount of bread actually baked.
        """
        cooking_spot = self.get_adjacent_cooking_spot(char)
        if not cooking_spot:
            return 0
        
        name = char.get_display_name()
        wheat_available = char.get_item('wheat')
        max_from_wheat = wheat_available // WHEAT_TO_BREAD_RATIO
        
        # Calculate how much we can actually bake
        # Limited by: requested amount, available wheat, inventory space
        to_bake = min(amount, max_from_wheat)
        
        # Check inventory space iteratively (in case we can only fit some)
        actually_baked = 0
        for _ in range(to_bake):
            if not char.can_add_item('bread', 1):
                break
            if char.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
                break
            
            # Convert wheat to bread
            char.remove_item('wheat', WHEAT_TO_BREAD_RATIO)
            char.add_item('bread', 1)
            actually_baked += 1
        
        if actually_baked > 0:
            spot_name = cooking_spot['name']
            self.state.log_action(f"{name} baked {actually_baked} bread at {spot_name}")
        
        return actually_baked
    
    def get_nearest_cooking_spot(self, char):
        """Find the nearest cooking spot the character can use (their stoves or any campfire).
        Returns (cooking_spot_dict, position) or (None, None).
        """
        best_spot = None
        best_pos = None
        best_dist = float('inf')
        
        # Check stoves the character can use (home matches)
        for pos, stove in self.state.interactables.stoves.items():
            if not stove.can_use(char):
                continue
            sx, sy = pos
            stove_cx = sx + 0.5
            stove_cy = sy + 0.5
            dist = math.sqrt((char['x'] - stove_cx) ** 2 + (char['y'] - stove_cy) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_spot = {
                    'type': 'stove',
                    'name': stove.name,
                    'source': stove
                }
                best_pos = (stove_cx, stove_cy)
        
        # Check campfires (anyone can use any campfire)
        for other_char in self.state.characters:
            camp_pos = other_char.get('camp_position')
            if camp_pos:
                cx, cy = camp_pos
                camp_center = (cx + 0.5, cy + 0.5)
                dist = math.sqrt((char['x'] - camp_center[0]) ** 2 + (char['y'] - camp_center[1]) ** 2)
                if dist < best_dist:
                    best_dist = dist
                    owner_name = other_char.get_display_name()
                    best_spot = {
                        'type': 'camp',
                        'name': f"{owner_name}'s campfire",
                        'source': camp_pos
                    }
                    best_pos = camp_center
        
        return best_spot, best_pos
    
    def get_nearest_stove(self, char):
        """Find the nearest stove the character can use. Returns (stove, position) or (None, None)."""
        best_stove = None
        best_pos = None
        best_dist = float('inf')
        
        for pos, stove in self.state.interactables.stoves.items():
            if not stove.can_use(char):
                continue
            sx, sy = pos
            stove_cx = sx + 0.5
            stove_cy = sy + 0.5
            dist = math.sqrt((char['x'] - stove_cx) ** 2 + (char['y'] - stove_cy) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_stove = stove
                best_pos = (stove_cx, stove_cy)
        
        return best_stove, best_pos
    
    def has_access_to_cooking(self, char):
        """Check if character has access to any cooking spot (stove they can use or any camp)."""
        # Check for stoves they can use
        if self.state.interactables.get_stoves_for_char(char):
            return True
        
        # Check for any campfire
        for other_char in self.state.characters:
            if other_char.get('camp_position'):
                return True
        
        return False
    
    # =========================================================================
    # STEWARD / TAX SYSTEM
    # =========================================================================
    
    def steward_has_wheat(self):
        """Check if barracks barrel has wheat to pay soldiers"""
        barracks_barrel = self.state.interactables.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
        return barracks_barrel is not None and barracks_barrel.get_item('wheat') > 0
    
    def get_steward_wheat_target(self, steward):
        """Calculate how much wheat steward wants to stockpile.
        Target: enough to feed all villagers for 2 days.
        (~3 wheat per person per day to maintain hunger)
        """
        allegiance = steward.get('allegiance')
        village_mouths = self.state.get_allegiance_count(allegiance) if allegiance else 0
        wheat_per_person_per_day = 3
        days_to_stockpile = 2
        return village_mouths * wheat_per_person_per_day * days_to_stockpile
    
    def steward_needs_to_buy_wheat(self, steward):
        """Check if barracks barrel wheat supply is below target"""
        target = self.get_steward_wheat_target(steward)
        barracks_barrel = self.state.interactables.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
        if not barracks_barrel:
            return True
        return barracks_barrel.get_item('wheat') < target
    
    # =========================================================================
    # TRADING SYSTEM
    # =========================================================================
    # Unified vendor system - all characters buy goods from vendors
    # Vendors are defined by VENDOR_GOODS mapping (job -> [goods_types])
    
    def get_vendors_selling(self, goods_type):
        """Get list of all characters who sell a specific goods type."""
        vendors = []
        for char in self.state.characters:
            job = char.get('job')
            if job and job in VENDOR_GOODS:
                if goods_type in VENDOR_GOODS[job]:
                    vendors.append(char)
        return vendors
    
    def is_vendor_of(self, char, goods_type):
        """Check if a character sells a specific goods type."""
        job = char.get('job')
        if not job or job not in VENDOR_GOODS:
            return False
        return goods_type in VENDOR_GOODS[job]
    
    def find_nearest_vendor(self, char, goods_type):
        """Find the nearest vendor selling a specific goods type."""
        best_vendor = None
        best_dist = float('inf')
        
        for vendor in self.get_vendors_selling(goods_type):
            if vendor == char:  # Can't buy from self
                continue
            dist = self.state.get_distance(char, vendor)
            if dist < best_dist:
                best_dist = dist
                best_vendor = vendor
        
        return best_vendor
    
    def find_adjacent_vendor(self, char, goods_type):
        """Find an adjacent vendor selling a specific goods type."""
        for vendor in self.state.characters:
            if vendor != char and self.is_vendor_of(vendor, goods_type):
                if self.is_adjacent(char, vendor):
                    return vendor
        return None
    
    def find_willing_vendor(self, char, goods_type):
        """Find the nearest vendor willing to trade this goods type."""
        best_vendor = None
        best_dist = float('inf')
        
        for vendor in self.get_vendors_selling(goods_type):
            if vendor == char:
                continue
            if self.vendor_willing_to_trade(vendor, char, goods_type):
                dist = self.state.get_distance(char, vendor)
                if dist < best_dist:
                    best_dist = dist
                    best_vendor = vendor
        
        return best_vendor
    
    def any_valid_vendor_exists(self, char, goods_type):
        """Check if any vendor exists who could potentially sell to this character."""
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
        
        For farmers selling wheat, uses tax-aware calculation.
        For other vendors, returns entire stock.
        """
        job = vendor.get('job')
        
        # Farmers have special tax-aware wheat selling logic
        if job == 'Farmer' and goods_type == 'wheat':
            return self._get_farmer_sellable_wheat(vendor)
        
        # For other vendors, can sell entire stock
        return int(self.get_goods_amount(vendor, goods_type))
    
    def _get_farmer_sellable_wheat(self, farmer):
        """Calculate how much wheat a farmer can sell while staying on track for taxes.
        
        Logic: sellable = current_wheat + expected_future_production - tax_target
        Internal helper - use get_vendor_sellable_goods(vendor, 'wheat') instead.
        """
        # Get current wheat (inventory + barrel)
        farmer_wheat = farmer.get_item('wheat')
        farm_barrel = self.state.interactables.get_barrel_by_home(farmer.get('home'))
        barrel_wheat = farm_barrel.get_item('wheat') if farm_barrel else 0
        current_wheat = int(farmer_wheat + barrel_wheat)
        
        # Calculate expected production before tax is due
        expected_production = self._get_farmer_expected_production(farmer)
        
        # No tax constraint - can sell all wheat
        if expected_production >= 999999:
            return current_wheat
        
        # Tax target with buffer for interruptions (1.5x)
        tax_target = (STEWARD_TAX_AMOUNT * 3) // 2
        
        # Sellable = what we have + what we'll produce - what we need for taxes
        sellable = current_wheat + expected_production - tax_target
        
        # Can't sell more than current stock
        return max(0, min(sellable, current_wheat))
    
    def _get_farmer_expected_production(self, farmer):
        """Estimate how much wheat the farmer can produce before tax is due.
        Internal helper for tax calculations.
        """
        # Only farmers with an allegiance owe tax
        if not farmer.get('allegiance'):
            return 999999  # No allegiance = no tax
        
        tax_due_tick = farmer.get('tax_due_tick')
        if tax_due_tick is None:
            return 999999  # No tax due yet
        
        # If tax is already overdue, no selling allowed
        if self.state.ticks >= tax_due_tick:
            return 0
        
        # Calculate time until tax is due
        ticks_until_tax = tax_due_tick - self.state.ticks
        
        # Count farm cells belonging to this farmer's home
        farmer_home = farmer.get('home')
        num_farm_cells = sum(1 for cell in self.state.farm_cells.values() 
                           if cell.get('home') == farmer_home)
        
        # Rough estimate: 1 wheat per farm cell per day when working half the day
        expected_production = (num_farm_cells * ticks_until_tax) // (TICKS_PER_DAY * 2)
        
        return expected_production
    
    def get_goods_amount(self, char, goods_type):
        """Get total amount of a goods type in character's inventory."""
        if goods_type == 'wheat':
            return char.get_item('wheat')
        elif goods_type == 'money':
            return char.get_item('money')
        # Placeholder for other goods
        return char.get(f'{goods_type}_stock', 0)
    
    def get_goods_price(self, goods_type, amount=1):
        """Get the price for a given amount of goods."""
        unit_price = ITEMS.get(goods_type, {}).get("price", 10)
        return unit_price * amount
    
    def can_afford_goods(self, char, goods_type):
        """Check if character can afford at least 1 unit of goods."""
        unit_price = ITEMS.get(goods_type, {}).get("price", 10)
        return char.get_item('money') >= unit_price
    
    def get_desired_goods_amount(self, char, goods_type):
        """Calculate how much of a goods type a character wants to buy.
        
        For wheat: enough to fill hunger deficit + buffer.
        For other goods: 1 unit (placeholder).
        """
        if goods_type == 'wheat':
            current_wheat = int(char.get_item('wheat'))
            current_bread = int(char.get_item('bread'))
            
            # Want enough wheat to fill hunger deficit (will be converted to bread)
            hunger_deficit = int(MAX_HUNGER - char['hunger'])
            wheat_for_hunger = max(0, hunger_deficit // ITEMS["bread"]["hunger_value"] + 1)
            
            # Account for bread we already have
            wheat_for_hunger = max(0, wheat_for_hunger - current_bread)
            
            # Also want buffer
            buffer_want = max(0, BREAD_BUFFER_TARGET - current_wheat - current_bread)
            
            return wheat_for_hunger + buffer_want
        
        # Default for other goods
        return 1
    
    def vendor_willing_to_trade(self, vendor, buyer, goods_type, amount=None):
        """Check if vendor is willing to trade goods with this buyer.
        
        Checks: trade cooldown, criminal status, allegiance, stock, money space.
        Traders are self-employed and trade with anyone regardless of allegiance.
        """
        if vendor == buyer:
            return False
        
        # Check buyer's trade cooldown
        last_trade = buyer.get('last_trade_tick', -TRADE_COOLDOWN)
        if self.state.ticks - last_trade < TRADE_COOLDOWN:
            return False
        
        # Don't trade with known criminals
        if self.cares_about_criminal(vendor, buyer):
            return False
        
        # Check allegiance compatibility (Traders trade with anyone)
        vendor_job = vendor.get('job')
        if vendor_job != 'Trader':
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
        if not vendor.can_add_item('money'):
            return False
        
        return True
    
    def get_max_vendor_trade_amount(self, vendor, buyer, goods_type):
        """Calculate maximum amount that can be traded.
        
        Considers: vendor stock, buyer money, buyer inventory space, buyer desire.
        """
        sellable = self.get_vendor_sellable_goods(vendor, goods_type)
        if sellable <= 0:
            return 0
        
        # How much can buyer afford?
        buyer_money = int(buyer.get_item('money'))
        unit_price = ITEMS.get(goods_type, {}).get("price", 10)
        affordable = buyer_money // unit_price if unit_price > 0 else 0
        
        # How much space does buyer have?
        if goods_type == 'wheat':
            buyer_space = buyer.get_inventory_space()
        else:
            buyer_space = INVENTORY_SLOTS  # Placeholder
        
        # How much does buyer want?
        desired = self.get_desired_goods_amount(buyer, goods_type)
        
        return max(0, min(sellable, affordable, buyer_space, desired))
    
    def execute_vendor_trade(self, vendor, buyer, goods_type, amount):
        """Execute a trade between vendor and buyer.
        
        For farmers selling wheat, also draws from their barrel if needed.
        """
        if amount <= 0:
            return False
        
        price = self.get_goods_price(goods_type, amount)
        
        # Handle wheat specially - farmers may use barrel
        if goods_type == 'wheat':
            amount_needed = amount
            
            # For farmers, take from inventory first, then barrel
            if vendor.get('job') == 'Farmer':
                vendor_wheat = vendor.get_item('wheat')
                from_inventory = min(vendor_wheat, amount_needed)
                if from_inventory > 0:
                    vendor.remove_item('wheat', from_inventory)
                    amount_needed -= from_inventory
                
                # If still need more, take from barrel
                if amount_needed > 0:
                    farm_barrel = self.state.interactables.get_barrel_by_home(vendor.get('home'))
                    if farm_barrel:
                        farm_barrel.remove_item('wheat', amount_needed)
            else:
                # Non-farmer vendors just use inventory
                vendor.remove_item('wheat', amount)
            
            buyer.add_item('wheat', amount)
        else:
            # Generic goods trade
            vendor_stock_key = f'{goods_type}_stock'
            buyer_stock_key = f'{goods_type}_stock'
            vendor[vendor_stock_key] = vendor.get(vendor_stock_key, 0) - amount
            buyer[buyer_stock_key] = buyer.get(buyer_stock_key, 0) + amount
        
        # Transfer money
        vendor.add_item('money', price)
        buyer.remove_item('money', price)
        
        # Set trade cooldown
        buyer['last_trade_tick'] = self.state.ticks
        
        return True
    
    def try_buy_from_nearest_vendor(self, char, goods_type):
        """Attempt to buy goods from the nearest willing vendor.
        
        Returns True if a purchase was made or if moving toward a vendor.
        """
        name = char.get_display_name()
        
        # Check if we can afford anything
        if not self.can_afford_goods(char, goods_type):
            return False
        
        # First check if adjacent to a willing vendor
        adjacent_vendor = self.find_adjacent_vendor(char, goods_type)
        if adjacent_vendor and self.vendor_willing_to_trade(adjacent_vendor, char, goods_type):
            amount = self.get_max_vendor_trade_amount(adjacent_vendor, char, goods_type)
            if amount > 0:
                price = self.get_goods_price(goods_type, amount)
                vendor_name = adjacent_vendor.get_display_name()
                
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
    # COMBAT / ROBBERY SYSTEM
    # =========================================================================
    
    def get_attacker(self, char):
        """Find anyone who is targeting this character and is close enough"""
        for other in self.state.characters:
            # Skip dying attackers
            if other.get('health', 100) <= 0:
                continue
            if other.get('robbery_target') == char:
                dist = self.state.get_distance(char, other)
                if dist <= 5:
                    return other
        return None
    
    def find_nearby_defender(self, char, max_distance, exclude=None):
        """Find a defender within range.
        
        Logic:
        - Characters with allegiance first look for soldiers of same allegiance
        - If no soldiers found (or no allegiance), look for general defenders
        - General defenders: anyone with morality >= 7 and confidence >= 7
        - Skip anyone the character KNOWS is a criminal (from their own memory)
        
        Args:
            char: The character looking for a defender
            max_distance: Maximum distance to search
            exclude: Character to exclude (e.g., the attacker/threat)
        """
        char_allegiance = char.get('allegiance')
        known_crimes = char.get('known_crimes', {})
        
        best_soldier = None
        best_soldier_dist = float('inf')
        best_general = None
        best_general_dist = float('inf')
        
        for other in self.state.characters:
            if other == char:
                continue
            # Skip the threat/attacker
            if exclude and other == exclude:
                continue
            # Skip dying characters
            if other.get('health', 100) <= 0:
                continue
            # Skip anyone this character knows is a criminal
            if id(other) in known_crimes:
                continue
            
            dist = self.state.get_distance(char, other)
            if dist > max_distance:
                continue
            
            morality = other.get_trait('morality')
            confidence = other.get_trait('confidence')
            is_soldier = other.get('job') == 'Soldier'
            other_allegiance = other.get('allegiance')
            
            # Check if same-allegiance soldier (only if char has allegiance)
            if char_allegiance and is_soldier and other_allegiance == char_allegiance:
                if dist < best_soldier_dist:
                    best_soldier_dist = dist
                    best_soldier = other
            
            # Check if general defender (high morality + high confidence)
            if morality >= 7 and confidence >= 7:
                if dist < best_general_dist:
                    best_general_dist = dist
                    best_general = other
        
        # Characters with allegiance prefer soldiers, fall back to general defenders
        if char_allegiance and best_soldier:
            return best_soldier
        
        # No soldier found (or no allegiance) - use general defender
        return best_general
    
    def is_defender(self, char):
        """Check if a character will defend others from crime.
        General defenders have morality >= 7 and confidence >= 7.
        Note: Soldiers are handled separately based on allegiance in find_nearby_defender.
        """
        morality = char.get_trait('morality')
        confidence = char.get_trait('confidence')
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
        """Get how far to flee from a criminal. Returns intensity / 2."""
        return intensity / 2
    
    def will_care_about_crime(self, responder, crime_allegiance, intensity=None):
        """Does this person care about this crime?
        
        Soldiers: +3 morality bonus for same-allegiance crimes, any intensity
        Others: morality >= 7 required, only for intensity >= 15
        """
        effective_morality = responder.get_trait('morality')
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
            # Skip dying characters - they're no longer a threat
            if other.get('health', 100) <= 0:
                continue
            if other.get('is_aggressor') and other.get('robbery_target'):
                target = other.get('robbery_target')
                if target in self.state.characters:
                    dist = self.state.get_distance(char, other)
                    if dist <= murder_range:
                        # Active aggression - check if we care
                        crime_allegiance = target.get('allegiance')
                        if self.will_care_about_crime(char, crime_allegiance, CRIME_INTENSITY_MURDER):
                            return (other, CRIME_INTENSITY_MURDER)
        
        # Check known crimes
        for other in self.state.characters:
            if other == char:
                continue
            # Skip dying characters
            if other.get('health', 100) <= 0:
                continue
            
            criminal_id = id(other)
            crimes = char.get('known_crimes', {}).get(criminal_id, [])
            
            for crime in crimes:
                intensity = crime['intensity']
                crime_allegiance = crime['allegiance']
                crime_range = intensity  # Range = intensity
                
                dist = self.state.get_distance(char, other)
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
        morality = char.get_trait('morality')
        
        if morality >= 7:
            return False
        
        # Check cooldown from giving up theft (tick-based)
        cooldown_until_tick = char.get('theft_cooldown_until_tick')
        if cooldown_until_tick and self.state.ticks < cooldown_until_tick:
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
        morality = char.get_trait('morality')
        
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
        morality = char.get_trait('morality')
        
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
    
    def get_farm_waiting_position(self, char):
        """Get a position near the farm to wait for crops."""
        # Find any farm cell and return a position adjacent to the farm area
        if not self.state.farm_cells:
            return None
        
        # Get the farm area bounds
        farm_cells = list(self.state.farm_cells.keys())
        min_x = min(c[0] for c in farm_cells)
        max_x = max(c[0] for c in farm_cells)
        min_y = min(c[1] for c in farm_cells)
        max_y = max(c[1] for c in farm_cells)
        
        # Return center of farm area
        return ((min_x + max_x) / 2 + 0.5, (min_y + max_y) / 2 + 0.5)
    
    def try_farm_theft(self, char):
        """Character attempts to steal from a farm. Returns True if action taken."""
        # If already pursuing theft, continue
        if char.get('theft_target') or char.get('theft_waiting'):
            return self.continue_theft(char)
        
        cell = self.find_nearby_ready_farm_cell(char)
        name = char.get_display_name()
        
        if cell:
            # Start pursuing the cell (not a crime yet - just walking to farm)
            char['theft_target'] = cell
            char['theft_start_tick'] = self.state.ticks
            self.state.log_action(f"{name} heading toward farm at {cell}")
        else:
            # No ready cells - go wait at the farm
            char['theft_waiting'] = True
            char['theft_start_tick'] = self.state.ticks
            self.state.log_action(f"{name} heading to farm to steal")
        
        return self.continue_theft(char)
    
    def continue_theft(self, char):
        """Continue theft in progress. Returns True if still stealing."""
        cell = char.get('theft_target')
        name = char.get_display_name()
        
        # Check if we've been trying too long (tick-based, scales with game speed)
        start_tick = char.get('theft_start_tick')
        if start_tick and self.state.ticks - start_tick > THEFT_PATIENCE_TICKS:
            char['theft_target'] = None
            char['theft_waiting'] = False
            char['theft_start_tick'] = None
            char['theft_cooldown_until_tick'] = self.state.ticks + THEFT_COOLDOWN_TICKS
            self.state.log_action(f"{name} gave up waiting to steal from farm")
            return False
        
        if not cell:
            # No specific cell - look for one or wait
            cell = self.find_nearby_ready_farm_cell(char)
            if cell:
                char['theft_target'] = cell
                char['theft_waiting'] = False
                self.state.log_action(f"{name} heading toward farm at {cell}")
            else:
                # No ready cells - mark as waiting
                if not char.get('theft_waiting'):
                    char['theft_waiting'] = True
                    self.state.log_action(f"{name} waiting at farm for crops to grow")
                return True  # Still in theft mode, just waiting
        
        cx, cy = cell
        
        # Check if cell is still ready
        data = self.state.farm_cells.get(cell)
        if not data or data['state'] != 'ready':
            # Cell no longer available - try to find another
            char['theft_target'] = None
            new_cell = self.find_nearby_ready_farm_cell(char)
            if new_cell:
                char['theft_target'] = new_cell
                char['theft_waiting'] = False
                self.state.log_action(f"{name} heading toward farm at {new_cell}")
            else:
                # No ready cells - wait at farm
                if not char.get('theft_waiting'):
                    char['theft_waiting'] = True
                    self.state.log_action(f"{name} waiting at farm for crops to grow")
            return True
        
        # If standing on the cell (character's cell position matches), steal immediately
        # Convert float position to cell coordinates
        char_cell = (int(char['x']), int(char['y']))
        if char_cell == cell:
            # Check if has inventory space
            if not char.can_add_item('wheat', FARM_CELL_YIELD):
                char['theft_target'] = None
                char['theft_waiting'] = False
                char['theft_start_tick'] = None
                return False
            
            # Execute the theft - THE CRIMINAL ACT
            char.add_item('wheat', FARM_CELL_YIELD)
            # Leave cell in replanting state (brown) - only farmers can turn it yellow
            data['state'] = 'replanting'
            data['timer'] = FARM_REPLANT_TIME
            
            # Mark as thief
            char['is_thief'] = True
            char['theft_target'] = None
            char['theft_waiting'] = False
            char['theft_start_tick'] = None
            
            self.state.log_action(f"{name} STOLE {FARM_CELL_YIELD} wheat from farm!")
            self.witness_theft(char, cell)
            return True
        
        # Still in transit - movement handled by _get_goal
        return True
    
    def witness_theft(self, thief, cell):
        """Witnesses within theft range learn about the theft and may react.
        
        Range: CRIME_INTENSITY_THEFT (4 cells)
        """
        thief_name = thief.get_display_name()
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
                witness_name = char.get_display_name()
                
                # Everyone remembers the crime
                self.remember_crime(char, thief, intensity, crime_allegiance)
                
                # Check if this witness cares
                cares = self.will_care_about_crime(char, crime_allegiance, intensity)
                
                # Check if this is the farm owner (always reacts as victim)
                # A farmer owns a cell if the cell's home matches the farmer's home
                cell_data = self.state.farm_cells.get((cx, cy), {})
                is_owner = (char.get('job') == 'Farmer' and 
                           char.get('home') and 
                           cell_data.get('home') == char.get('home'))
                
                if cares or is_owner:
                    confidence = char.get_trait('confidence')
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
    
    def report_crime_to_defender(self, witness, criminal, intensity, defender):
        """Directly report a crime to a specific defender.
        
        Used when a fleeing character reaches a defender for safety.
        The defender will remember the crime and can respond.
        """
        witness_name = witness.get_display_name()
        criminal_name = criminal.get_display_name()
        defender_name = defender.get_display_name()
        
        # Defender learns about the crime
        crime_allegiance = witness.get('allegiance')  # Crime against the witness's allegiance
        self.remember_crime(defender, criminal, intensity, crime_allegiance)
        
        # Remove from witness's unreported crimes if present
        crime_tuple = (id(criminal), intensity, crime_allegiance)
        witness.get('unreported_crimes', set()).discard(crime_tuple)
        
        self.state.log_action(f"{witness_name} reported {criminal_name} to {defender_name}!")
    
    def try_report_crime(self, witness, criminal, intensity, crime_allegiance):
        """Try to report crime to an adjacent soldier. If none adjacent, save for later.
        
        Only reports to soldiers of same allegiance as the crime.
        Requires adjacency (distance 1).
        """
        if crime_allegiance is None:
            return  # Can't report crimes against unaligned
        
        witness_name = witness.get_display_name()
        criminal_name = criminal.get_display_name()
        
        # Look for an adjacent soldier of the same allegiance
        for char in self.state.characters:
            if char == witness or char == criminal:
                continue
            if char.get('job') == 'Soldier' and char.get('allegiance') == crime_allegiance:
                dist = abs(char['x'] - witness['x']) + abs(char['y'] - witness['y'])
                if dist <= 1:  # Must be adjacent
                    # Report to this soldier
                    self.remember_crime(char, criminal, intensity, crime_allegiance)
                    soldier_name = char.get_display_name()
                    self.state.log_action(f"{witness_name} reported {criminal_name} to {soldier_name}!")
                    return  # Reported successfully
        
        # No soldier adjacent - save for later
        witness['unreported_crimes'].add((id(criminal), intensity, crime_allegiance))
    
    def find_richest_target(self, robber):
        """Find the best target to rob"""
        targets = [c for c in self.state.characters if c != robber and (c.get_item('money') > 0 or c.get_item('wheat') > 0)]
        if not targets:
            return None
        return max(targets, key=lambda c: (c.get_item('wheat'), c.get_item('money')))
    
    def try_robbery(self, robber):
        """Character decides to rob someone - sets target and starts pursuit"""
        target = self.find_richest_target(robber)
        if target:
            robber_name = robber.get_display_name()
            target_name = target.get_display_name()
            self.state.log_action(f"{robber_name} DECIDED TO ROB {target_name} (target has ${target.get_item('money')})")
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
        
        # Don't attack dying characters
        if target.get('health', 100) <= 0:
            robber['robbery_target'] = None
            return False
        
        # Movement is handled by velocity system in _get_goal
        # We just check if adjacent and attack if so
        
        if self.is_adjacent(robber, target):
            result = self.resolve_melee_attack(robber, target)
            
            if result['killed']:
                robber['robbery_target'] = None
                robber['is_aggressor'] = False
        
        return True
    
    def witness_murder(self, attacker, victim, is_lethal=False):
        """Witnesses within range learn about the crime and may react.
        
        Args:
            attacker: The character who attacked
            victim: The character who was attacked
            is_lethal: True if this was a killing blow, False if just an attack
        
        For murders (is_lethal=True): witnesses permanently remember the crime
        For assaults (is_lethal=False): triggers immediate reaction but not remembered
        
        Range: CRIME_INTENSITY_MURDER (17 cells)
        """
        attacker_name = attacker.get_display_name()
        victim_name = victim.get_display_name()
        intensity = CRIME_INTENSITY_MURDER
        witness_range = intensity
        
        # Crime allegiance = victim's allegiance
        crime_allegiance = victim.get('allegiance')
        
        # Choose appropriate log message
        crime_verb = "murder" if is_lethal else "attack"
        
        for char in self.state.characters:
            if char == attacker or char == victim:
                continue
            
            dist = abs(char['x'] - victim['x']) + abs(char['y'] - victim['y'])
            if dist <= witness_range:
                witness_name = char.get_display_name()
                
                # Only permanently remember murders, not assaults
                # Assaults trigger immediate reaction via is_aggressor flag
                if is_lethal:
                    self.remember_crime(char, attacker, intensity, crime_allegiance)
                    self.state.log_action(f"{witness_name} WITNESSED {attacker_name} {crime_verb} {victim_name}!")
                    
                    # Try to report if same allegiance
                    if char.get('allegiance') == crime_allegiance and crime_allegiance is not None:
                        self.try_report_crime(char, attacker, intensity, crime_allegiance)
                else:
                    # Just log the assault - immediate reaction handled by is_aggressor check
                    self.state.log_action(f"{witness_name} WITNESSED {attacker_name} {crime_verb} {victim_name}!")
    
    def try_report_crimes_to_soldier(self, char):
        """If character has unreported crimes and is adjacent to a soldier, report to them.
        
        Only reports to soldiers of same allegiance as the crime.
        Requires adjacency (distance 1).
        """
        unreported = char.get('unreported_crimes', set())
        
        if not unreported:
            return
        
        char_name = char.get_display_name()
        
        for other in self.state.characters:
            if other == char:
                continue
            if other.get('job') != 'Soldier':
                continue
            
            dist = abs(char['x'] - other['x']) + abs(char['y'] - other['y'])
            if dist > 1:  # Must be adjacent
                continue
                
            soldier_name = other.get_display_name()
            soldier_allegiance = other.get('allegiance')
            
            # Check each unreported crime
            for crime_tuple in list(unreported):
                criminal_id, intensity, crime_allegiance = crime_tuple
                
                # Only report to soldiers of same allegiance
                if crime_allegiance == soldier_allegiance:
                    # Find the criminal for logging and to pass to remember_crime
                    criminal = next((c for c in self.state.characters if id(c) == criminal_id), None)
                    if criminal:
                        criminal_name = criminal.get_display_name()
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
        """Check if character's food supply (wheat + bread) is below the buffer target.
        Since wheat can be converted to bread, we count both together.
        """
        total_food = char.get_item('wheat') + char.get_item('bread')
        return total_food < BREAD_BUFFER_TARGET
    
    def handle_wheat_need(self, char):
        """Handle a character's hunger needs. Returns True if action was taken."""
        job = char.get('job')
        name = char.get_display_name()
        
        # Option 1: Eat bread from inventory
        if char.get_item('bread') >= BREAD_PER_BITE:
            char.remove_item('bread', BREAD_PER_BITE)
            char['hunger'] = min(MAX_HUNGER, char['hunger'] + ITEMS["bread"]["hunger_value"])
            char['wheat_seek_ticks'] = 0
            self.state.log_action(f"{name} ate bread, hunger now {char['hunger']:.0f}")
            return True
        
        # Option 2: If have wheat but no bread, go cook it
        if char.get_item('wheat') >= WHEAT_TO_BREAD_RATIO:
            # Try to bake if adjacent to cooking spot
            if self.can_bake_bread(char):
                amount_to_bake = min(char.get_item('wheat'), BREAD_BUFFER_TARGET)
                self.bake_bread(char, amount_to_bake)
                return True
            
            # Move toward nearest cooking spot
            cooking_spot, cooking_pos = self.get_nearest_cooking_spot(char)
            if cooking_spot and cooking_pos:
                # Move toward the cooking spot
                char['move_target'] = cooking_pos
                return True
            
            # No cooking spot available - need to make a camp
            if self.can_make_camp_at(char['x'], char['y']):
                self.make_camp(char)
                return True
            else:
                # Move to find a camp spot
                camp_spot = self._find_camp_spot(char)
                if camp_spot:
                    char['move_target'] = camp_spot
                    return True
        
        # Option 3: Soldiers wait for steward to bring wheat (passive)
        # The steward will come to them - soldiers just need to register their request
        if job == 'Soldier':
            # Register request if not already done
            if not char.get('requested_wheat'):
                char['requested_wheat'] = True
                self.state.log_action(f"{name} is waiting for food from the Steward")
            # Soldiers don't actively seek wheat - they wait
            return False
        
        # Option 4: Non-soldiers buy wheat from nearest vendor (Farmer, Innkeeper, etc.)
        # Characters who sell wheat themselves don't buy from others
        if self.can_afford_goods(char, 'wheat') and not self.is_vendor_of(char, 'wheat'):
            # Try to buy from adjacent vendor first
            adjacent_vendor = self.find_adjacent_vendor(char, 'wheat')
            if adjacent_vendor and self.vendor_willing_to_trade(adjacent_vendor, char, 'wheat'):
                amount = self.get_max_vendor_trade_amount(adjacent_vendor, char, 'wheat')
                if amount > 0:
                    price = self.get_goods_price('wheat', amount)
                    vendor_name = adjacent_vendor.get_display_name()
                    
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
        
        # Option 5: Resort to crime (only if can't legitimately buy wheat)
        # Characters with money and access to a willing vendor should NEVER steal
        can_buy_wheat = self.can_afford_goods(char, 'wheat') and self.find_willing_vendor(char, 'wheat') is not None
        
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
        Process all NPC decisions and movement for this tick.
        
        For each NPC:
        1. Call job.decide() which sets char.goal and performs any immediate actions
        2. Update velocity based on char.goal
        
        Position updates happen every frame via update_npc_positions().
        """
        npcs = [c for c in self.state.characters if not c.is_player]
        
        # Each NPC decides what to do (sets goal and/or takes action)
        for char in npcs:
            if char not in self.state.characters:
                continue  # May have been killed
            
            if char.get('is_frozen'):
                char.vx = 0.0
                char.vy = 0.0
                continue
            
            # Skip dying characters
            if char.get('health', 100) <= 0:
                char.vx = 0.0
                char.vy = 0.0
                continue
            
            # Reset idle flag before deciding
            char.idle_is_idle = False
            
            # Get the job and let it decide what to do
            job = get_job(char.get('job'))
            job.decide(char, self.state, self)
            
            # Wake up if not sleep time
            if not self.state.is_sleep_time() and char.get('is_sleeping'):
                char.is_sleeping = False
                name = char.get_display_name()
                self.state.log_action(f"{name} woke up")
        
        # Update velocities based on goals
        for char in npcs:
            if char not in self.state.characters:
                continue
            
            if char.get('is_frozen') or char.get('health', 100) <= 0:
                continue
            
            goal = char.goal
            if goal:
                # Calculate direction to goal
                dx = goal[0] - char.x
                dy = goal[1] - char.y
                dist = math.sqrt(dx * dx + dy * dy)
                
                if dist < 0.35:  # Close enough - prevents overshoot jitter
                    char.vx = 0.0
                    char.vy = 0.0
                else:
                    # Use slower speed if idling or patrolling
                    speed = MOVEMENT_SPEED
                    if char.get('idle_is_idle', False):
                        speed = MOVEMENT_SPEED * IDLE_SPEED_MULTIPLIER
                    elif char.get('is_patrolling', False):
                        speed = MOVEMENT_SPEED * PATROL_SPEED_MULTIPLIER
                    
                    # Normalize and apply speed
                    char.vx = (dx / dist) * speed
                    char.vy = (dy / dist) * speed
                    # Update facing direction
                    self._update_facing_from_velocity(char)
            else:
                char.vx = 0.0
                char.vy = 0.0
            
            # If not idling, reset idle state for next time
            if not char.get('idle_is_idle', False):
                self._reset_idle_state(char)
        
        # Report crimes to nearby soldiers
        for char in self.state.characters:
            self.try_report_crimes_to_soldier(char)
    
    def update_npc_positions(self, dt):
        """Update NPC positions based on velocity. Called every frame for smooth movement.
        
        Implements squeeze behavior: when blocked for more than SQUEEZE_THRESHOLD_TICKS,
        characters will slide perpendicular to their movement direction to squeeze past obstacles.
        """
        npcs = [c for c in self.state.characters if not c.is_player]
        
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
        return char.goal
    
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
        """Get position to move toward for hunger needs. Returns float position.
        
        Priority:
        1. If have wheat but no bread -> go to cooking spot (or make camp)
        2. If no wheat -> go buy wheat
        """
        job = char.get('job')
        
        # If we have wheat but no bread, we need to cook
        if char.get_item('wheat') >= WHEAT_TO_BREAD_RATIO and char.get_item('bread') < BREAD_PER_BITE:
            # Find nearest cooking spot
            cooking_spot, cooking_pos = self.get_nearest_cooking_spot(char)
            if cooking_spot and cooking_pos:
                return cooking_pos
            
            # No cooking spot - need to make a camp
            # If we can camp here, we'll do it in handle_wheat_need
            # Otherwise find a spot to camp
            if not self.can_make_camp_at(char['x'], char['y']):
                camp_spot = self._find_camp_spot(char)
                if camp_spot:
                    return camp_spot
            # Can camp here, return None to let handle_wheat_need make the camp
            return None
        
        # Need to get wheat
        if job == 'Soldier':
            # Go to barracks barrel position
            barracks_barrel = self.state.interactables.get_barrel_by_home(self.state.get_area_by_role('military_housing'))
            if barracks_barrel:
                barrel_pos = barracks_barrel.position
                if barrel_pos:
                    return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            return self._nearest_in_area(char, self.state.get_area_by_role('military_housing'))
        
        # Farmer: go to farm barrel to withdraw wheat
        if job == 'Farmer':
            farm_barrel = self.state.interactables.get_barrel_by_home(char.get('home'))
            if farm_barrel:
                barrel_wheat = farm_barrel.get_item('wheat')
                if barrel_wheat > 0:
                    barrel_pos = farm_barrel.position
                    if barrel_pos:
                        return (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            # No barrel or empty barrel - fall through to buying logic
        
        if self.can_afford_goods(char, 'wheat'):
            farmer = self.find_willing_vendor(char, 'wheat')
            if farmer:
                return (farmer['x'], farmer['y'])
        return None
    
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
        is_village = self.state.is_village_area(area) if area else False
        
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
        char['is_patrolling'] = False

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
    
    def _nearest_ready_farm_cell(self, char, home=None):
        """Find nearest ready farm cell. Returns float position (cell center).
        
        Args:
            char: The character looking for a cell
            home: Filter to only cells owned by this farm area name. If None, searches all.
        """
        from scenario_world import AREAS
        
        # Check if character is already on a farm cell being worked
        char_cell = (int(char['x']), int(char['y']))
        cell = self.state.get_farm_cell_state(char_cell[0], char_cell[1])
        if cell and cell['state'] in ('ready', 'harvesting', 'replanting'):
            return None
        
        # If home is specified, get the farm cells for that specific farm area
        valid_cells = set()
        if home:
            for area in AREAS:
                if area.get('name') == home and area.get('has_farm_cells'):
                    # Get the explicit farm cell list from the area definition
                    for cell_coord in area.get('farm_cells', []):
                        valid_cells.add((cell_coord[0], cell_coord[1]))
                    break
        
        best = None
        best_dist = float('inf')
        for (cx, cy), data in self.state.farm_cells.items():
            if data['state'] == 'ready':
                # Filter by home farm if specified
                if home and (cx, cy) not in valid_cells:
                    continue
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
    
    def _try_frozen_trade(self, char):
        """Frozen character tries to trade with any adjacent wheat vendor.
        Note: They buy wheat but can't eat it - they need bread to recover.
        """
        if self.can_afford_goods(char, 'wheat'):
            vendor = self.find_adjacent_vendor(char, 'wheat')
            if vendor and self.vendor_willing_to_trade(vendor, char, 'wheat'):
                amount = self.get_max_vendor_trade_amount(vendor, char, 'wheat')
                if amount > 0:
                    self.execute_vendor_trade(vendor, char, 'wheat', amount)
                    name = char.get_display_name()
                    self.state.log_action(f"{name} (frozen) bought {amount} wheat!")
                    # They have wheat but can't eat it - need bread to recover
                    if char.get_item('bread') >= BREAD_PER_BITE:
                        char.remove_item('bread', BREAD_PER_BITE)
                        char['hunger'] = min(MAX_HUNGER, char['hunger'] + ITEMS["bread"]["hunger_value"])
                        char['is_starving'] = False
                        char['is_frozen'] = False
                        self.state.log_action(f"{name} ate bread and recovered from starvation!")
    
    def _do_attack(self, attacker, target):
        """Execute an attack. Wrapper around resolve_melee_attack for NPC combat."""
        # Set attack animation direction toward target
        dx = target.x - attacker.x
        dy = target.y - attacker.y
        if abs(dx) > abs(dy):
            attacker.attack_direction = 'right' if dx > 0 else 'left'
        else:
            attacker.attack_direction = 'down' if dy > 0 else 'up'
        attacker.attack_animation_start = time.time()
        
        # Record attack tick for cooldown
        attacker['last_attack_tick'] = self.state.ticks
        
        # Use unified attack resolution
        result = self.resolve_melee_attack(attacker, target)
        
        # Handle post-attack cleanup for NPCs
        if result['killed']:
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
        
        # Handle deaths IMMEDIATELY - remove from game logic, store visual info separately
        # This must happen right after starvation before any other processing
        self._process_deaths()
        
        # Update farm cells
        self._update_farm_cells()
        
        # Age increment
        if self.state.ticks > 0 and self.state.ticks % TICKS_PER_YEAR == 0:
            for char in self.state.characters:
                char['age'] += 1
            self.state.log_action(f"A new year begins! Everyone is one year older.")
        
        # Tax grace period check - steward goes to collect if farmer is late
        steward = self.state.get_steward()
        if steward:
            steward_allegiance = steward.get('allegiance')
            for char in self.state.characters:
                if char.get('job') == 'Farmer' and char.get('allegiance') == steward_allegiance:
                    tax_due_tick = char.get('tax_due_tick')
                    if tax_due_tick is not None and self.state.ticks >= tax_due_tick + TAX_GRACE_PERIOD:
                        if steward.get('tax_collection_target') != char:
                            steward_name = steward.get_display_name()
                            char_name = char.get_display_name()
                            self.state.log_action(f"Steward {steward_name} going to collect tax from {char_name}!")
                            steward['tax_collection_target'] = char
        
        # Move NPCs with swap detection to prevent oscillation
        self._process_npc_movement()
        
        # Process deaths again to catch combat kills
        self._process_deaths()
    
    def _process_deaths(self):
        """Remove dead characters from game and store visual info for death animation"""
        import time
        current_time = time.time()
        
        dead_chars = [char for char in self.state.characters if char['health'] <= 0]
        for char in dead_chars:
            # Log death message
            dead_name = char.get_display_name()
            if char.is_player:
                if char.get('is_starving'):
                    self.state.log_action(f"{dead_name} (PLAYER) DIED from starvation! GAME OVER")
                else:
                    self.state.log_action(f"{dead_name} (PLAYER) DIED! GAME OVER")
            else:
                if char.get('is_starving'):
                    self.state.log_action(f"{dead_name} DIED from starvation!")
                else:
                    self.state.log_action(f"{dead_name} DIED!")
            
            # Store visual info for death animation (GUI concern only)
            self.state.death_animations.append({
                'x': char['x'],
                'y': char['y'],
                'name': char['name'],
                'start_time': current_time,
                'facing': char.get('facing', 'down'),
                'job': char.get('job'),
                'morality': char.get('morality', 5)
            })
            
            # Immediately remove from game - no more processing
            self.state.remove_character(char)
    
    def _process_starvation(self):
        """Process starvation for all characters"""
        for char in self.state.characters:
            # Skip dying characters
            if char.get('health', 100) <= 0:
                continue
            
            name = char.get_display_name()
            
            # Check if character should enter starvation (hunger = 0)
            if char['hunger'] <= STARVATION_THRESHOLD:
                was_starving = char.get('is_starving', False)
                
                if not was_starving:
                    # Just entered starvation
                    char['is_starving'] = True
                    char['starvation_health_lost'] = 0
                    char['ticks_starving'] = 0
                    self.state.log_action(f"{name} is STARVING! Losing health...")
                    
                    # Soldiers quit when they start starving - lose job and home, but keep allegiance
                    # This gives them a chance to buy wheat from a farmer and rejoin
                    # If no farmer will sell to them, wheat timeout will naturally remove allegiance
                    if char.get('job') == 'Soldier':
                        char['job'] = None
                        char['home'] = None
                        # Remove bed ownership
                        self.state.interactables.unassign_bed_owner(char['name'])
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
            # Skip dying characters
            if char.get('health', 100) <= 0:
                continue
            
            # Convert float position to cell coordinates
            cell = (int(char['x']), int(char['y']))
            if cell in self.state.farm_cells and cell not in cells_being_worked:
                data = self.state.farm_cells[cell]
                
                # Only farmers can work farm cells without it being theft
                is_farmer = char.get('job') == 'Farmer'
                is_player = char.is_player
                
                if not is_farmer and not is_player:
                    continue  # Non-farmers/non-players use try_farm_theft via AI
                
                if data['state'] == 'ready':
                    # Check if can carry more wheat
                    if not char.can_add_item('wheat', FARM_CELL_YIELD):
                        continue  # Inventory full, can't harvest
                    data['state'] = 'harvesting'
                    data['timer'] = FARM_HARVEST_TIME
                    data['harvester'] = char  # Track who started harvesting
                    cells_being_worked.add(cell)
                
                elif data['state'] == 'harvesting':
                    data['timer'] -= 1
                    if data['timer'] <= 0:
                        # Check inventory space before adding wheat
                        if char.can_add_item('wheat', FARM_CELL_YIELD):
                            char.add_item('wheat', FARM_CELL_YIELD)
                            data['state'] = 'replanting'
                            data['timer'] = FARM_REPLANT_TIME
                            
                            name = char.get_display_name()
                            
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