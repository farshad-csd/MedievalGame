# jobs.py - Job behavior classes with unified decide() pattern
"""
Each job defines:
- decide() method: handles ALL character decisions each tick
- Enrollment class methods: is_eligible, is_available, can_enlist, enlist

The decide() method reads top-to-bottom as a priority list.
Base Job class handles unemployed/default behavior.
Subclasses override decide() and enrollment methods for job-specific logic.
"""

import math
import random
from constants import (
    ITEMS, TICKS_PER_DAY, MAX_HUNGER,
    HUNGER_CHANCE_THRESHOLD, HUNGER_CRITICAL,
    STEWARD_TAX_INTERVAL, STEWARD_TAX_AMOUNT, SOLDIER_WHEAT_PAYMENT,
    WHEAT_TO_BREAD_RATIO, BREAD_PER_BITE, BREAD_BUFFER_TARGET,
    PATROL_SPEED_MULTIPLIER, PATROL_CHECK_MIN_TICKS, PATROL_CHECK_MAX_TICKS,
    PATROL_CHECK_CHANCE, PATROL_APPROACH_DISTANCE, CRIME_INTENSITY_MURDER,
    TAX_GRACE_PERIOD, JOB_TIERS, DEFAULT_JOB_TIER
)


class Job:
    """
    Base job - handles unemployed/default character behavior.
    
    The decide() method is called each tick and should:
    1. Set char.goal = (x, y) if the character should move
    2. Execute any immediate actions (eating, attacking, etc.)
    3. Return True if an action was taken (consumes the tick)
    
    Subclasses override decide() to inject job-specific priorities.
    
    Enrollment class methods (override in subclasses):
    - is_eligible(char, state, logic): Can this character do this job?
    - is_available(state, logic): Are there openings?
    - can_enlist(char, state, logic): Can enlist right now? (eligible + available + location)
    - enlist(char, state, logic): Actually assign the job
    """
    
    name = None
    
    @classmethod
    def get_tier(cls):
        """Get job tier from JOB_TIERS constant."""
        if cls.name and cls.name in JOB_TIERS:
            return JOB_TIERS[cls.name]["tier"]
        return DEFAULT_JOB_TIER
    
    @classmethod
    def get_requirements(cls):
        """Get job requirements from JOB_TIERS constant."""
        if cls.name and cls.name in JOB_TIERS:
            return JOB_TIERS[cls.name].get("requires", {})
        return {}
    
    # =========================================================================
    # ENROLLMENT CLASS METHODS (override in subclasses)
    # =========================================================================
    
    @classmethod
    def is_eligible(cls, char, state, logic):
        """Check if character meets requirements for this job (traits, skills, etc.)."""
        return False
    
    @classmethod
    def is_available(cls, state, logic):
        """Check if there's an opening for this job."""
        return False
    
    @classmethod
    def can_enlist(cls, char, state, logic):
        """Check if character can enlist right now (eligible + available + in right place)."""
        return False
    
    @classmethod
    def enlist(cls, char, state, logic):
        """Assign the job to the character. Returns True on success."""
        return False
    
    @classmethod
    def get_enlistment_goal(cls, char, state, logic):
        """Get position character should move to for enlistment, or None."""
        return None
    
    # =========================================================================
    # DECIDE METHOD
    # =========================================================================
    
    def decide(self, char, state, logic):
        """
        Decide what this character should do this tick.
        
        Args:
            char: Character instance
            state: GameState instance
            logic: GameLogic instance
            
        Returns:
            True if an action was taken, False otherwise
        """
        # ===== SURVIVAL (highest priority) =====
        
        # Flee if being attacked and not confident
        if self._should_flee(char, state, logic):
            return self._do_flee(char, state, logic)
        
        # Fight back if being attacked and confident
        if self._should_fight_back(char, state, logic):
            return self._do_fight_back(char, state, logic)
        
        # Continue combat if we have a target
        if self._in_combat(char, state, logic):
            return self._do_combat(char, state, logic)
        
        # Flee from known criminals
        if self._should_flee_criminal(char, state, logic):
            return self._do_flee_criminal(char, state, logic)
        
        # ===== BASIC NEEDS =====
        
        # Eat if hungry and have bread
        if self._should_eat(char):
            return self._do_eat(char, state, logic)
        
        # Cook if hungry, have wheat, need bread
        if self._should_cook(char, state, logic):
            return self._do_cook(char, state, logic)
        
        # Sleep if it's night
        if self._should_sleep(char, state, logic):
            return self._do_sleep(char, state, logic)
        
        # ===== UNEMPLOYED BEHAVIOR =====
        
        # Seek employment
        if self._should_seek_job(char, state, logic):
            return self._do_seek_job(char, state, logic)
        
        # Forage/steal if hungry and no food
        if self._should_forage(char, state, logic):
            return self._do_forage(char, state, logic)
        
        # Wander
        return self._do_wander(char, state, logic)
    
    # =========================================================================
    # CONDITION CHECKS (can be overridden by subclasses)
    # =========================================================================
    
    def _should_flee(self, char, state, logic):
        """Should this character flee from an attacker?"""
        attacker = logic.get_attacker(char)
        if not attacker:
            return False
        confidence = char.get_trait('confidence')
        return confidence < 7  # Low confidence = flee
    
    def _should_fight_back(self, char, state, logic):
        """Should this character fight back against attacker?"""
        attacker = logic.get_attacker(char)
        if not attacker:
            return False
        confidence = char.get_trait('confidence')
        return confidence >= 7  # High confidence = fight
    
    def _in_combat(self, char, state, logic):
        """Is this character actively in combat?"""
        target = char.get('robbery_target')
        return target and target in state.characters
    
    def _should_flee_criminal(self, char, state, logic):
        """Should flee from a known criminal nearby?"""
        # Check if already fleeing
        if char.get('flee_from'):
            return True
        # Check for criminals we know about
        criminal, intensity = logic.find_known_criminal_nearby(char)
        if criminal and char.get_trait('confidence') < 7:
            return True
        return False
    
    def _should_eat(self, char):
        """Should this character eat?"""
        return char.hunger <= HUNGER_CHANCE_THRESHOLD and char.get_item('bread') >= BREAD_PER_BITE
    
    def _should_cook(self, char, state, logic):
        """Should this character cook bread?"""
        if char.hunger > HUNGER_CHANCE_THRESHOLD:
            return False
        if char.get_item('bread') >= BREAD_PER_BITE:
            return False
        if char.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
            return False
        return logic.can_bake_bread(char)
    
    def _should_sleep(self, char, state, logic):
        """Should this character go to sleep?"""
        return state.is_sleep_time()
    
    def _should_seek_job(self, char, state, logic):
        """Should this character look for a job?"""
        from jobs import get_best_available_job as get_best_job
        return get_best_job(char, state, logic) is not None
    
    def _should_forage(self, char, state, logic):
        """Should this character forage/steal for food?"""
        if char.get_item('bread') >= BREAD_PER_BITE:
            return False
        if char.hunger > HUNGER_CRITICAL:
            return False
        return True
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def _do_flee(self, char, state, logic):
        """Flee from attacker."""
        attacker = logic.get_attacker(char)
        if not attacker:
            return False
        
        # Look for a defender to run to
        murder_range = logic.get_crime_range('murder')
        defender = logic.find_nearby_defender(char, murder_range)
        if defender:
            char.goal = (defender.x, defender.y)
        else:
            char.goal = logic._get_flee_goal(char, attacker)
        return False  # Movement, not action
    
    def _do_fight_back(self, char, state, logic):
        """Fight back against attacker."""
        attacker = logic.get_attacker(char)
        if not attacker:
            return False
        
        # Set attacker as our target
        if char.get('robbery_target') != attacker:
            name = char.get_display_name()
            state.log_action(f"{name} FIGHTING BACK against {attacker.get_display_name()}!")
            char.robbery_target = attacker
        
        # Attack if adjacent and can attack
        if logic.is_adjacent(char, attacker) and logic.can_attack(char):
            logic._do_attack(char, attacker)
            return True
        
        # Move toward attacker
        char.goal = (attacker.x, attacker.y)
        return False
    
    def _do_combat(self, char, state, logic):
        """Continue combat with target."""
        target = char.get('robbery_target')
        if not target or target not in state.characters:
            char.robbery_target = None
            return False
        
        if logic.is_adjacent(char, target):
            if logic.can_attack(char):
                logic._do_attack(char, target)
                return True
            char.goal = None  # Stay still, waiting for cooldown
        else:
            char.goal = (target.x, target.y)
        return False
    
    def _do_flee_criminal(self, char, state, logic):
        """Flee from a known criminal."""
        # Check current flee target
        flee_target = char.get('flee_from')
        if flee_target and flee_target in state.characters:
            worst_crime = logic.get_worst_known_crime(char, flee_target)
            if worst_crime:
                flee_distance = logic.get_flee_distance(worst_crime['intensity'])
            else:
                flee_distance = logic.get_flee_distance(CRIME_INTENSITY_MURDER)
            
            dist = state.get_distance(char, flee_target)
            if dist > flee_distance:
                char.flee_from = None
                return False
            
            # Look for defender
            defender = logic.find_nearby_defender(char, worst_crime['intensity'] if worst_crime else CRIME_INTENSITY_MURDER)
            if defender:
                char.goal = (defender.x, defender.y)
            else:
                char.goal = logic._get_flee_goal(char, flee_target)
            return False
        
        # Find new criminal to flee from
        criminal, intensity = logic.find_known_criminal_nearby(char)
        if criminal:
            char_name = char.get_display_name()
            criminal_name = criminal.get_display_name()
            state.log_action(f"{char_name} fleeing from {criminal_name}!")
            char.flee_from = criminal
            
            defender = logic.find_nearby_defender(char, intensity)
            if defender:
                char.goal = (defender.x, defender.y)
            else:
                char.goal = logic._get_flee_goal(char, criminal)
        return False
    
    def _do_eat(self, char, state, logic):
        """Eat bread."""
        result = char.eat()
        if result['success']:
            name = char.get_display_name()
            if result.get('recovered_from_starvation'):
                state.log_action(f"{name} ate bread and recovered from starvation! Hunger: {char.hunger:.0f}")
            else:
                state.log_action(f"{name} ate bread, hunger now {char.hunger:.0f}")
            return True
        return False
    
    def _do_cook(self, char, state, logic):
        """Cook bread at current location."""
        if logic.can_bake_bread(char):
            amount_to_bake = min(char.get_item('wheat') // WHEAT_TO_BREAD_RATIO, BREAD_BUFFER_TARGET)
            logic.bake_bread(char, amount_to_bake)
            return True
        
        # Need to go to cooking spot
        cooking_spot, cooking_pos = logic.get_nearest_cooking_spot(char)
        if cooking_pos:
            char.goal = cooking_pos
        elif logic.can_make_camp_at(char.x, char.y):
            logic.make_camp(char)
            return True
        return False
    
    def _do_sleep(self, char, state, logic):
        """Go to sleep or head to bed."""
        sleep_pos = logic.get_sleep_position(char)
        
        if sleep_pos:
            sleep_center = (sleep_pos[0] + 0.5, sleep_pos[1] + 0.5)
            dist = math.sqrt((char.x - sleep_center[0])**2 + (char.y - sleep_center[1])**2)
            
            if dist < 0.15:
                # At sleep position
                if not char.get('is_sleeping'):
                    char.is_sleeping = True
                    name = char.get_display_name()
                    bed = state.get_character_bed(char)
                    if bed:
                        state.log_action(f"{name} went to sleep in bed")
                    else:
                        state.log_action(f"{name} went to sleep at camp")
                char.goal = None
                return True
            else:
                char.goal = sleep_center
                return False
        else:
            # No bed - find camp spot
            if logic.can_make_camp_at(char.x, char.y):
                logic.make_camp(char)
                char.is_sleeping = True
                return True
            else:
                char.goal = logic._find_camp_spot(char)
                return False
    
    def _do_seek_job(self, char, state, logic):
        """Try to get a job using job class enrollment methods."""
        # Import here to avoid circular import at module level
        # (These are defined later in the file)
        from jobs import get_best_available_job as get_best_job, JOB_CLASSES
        
        best_job = get_best_job(char, state, logic)
        if not best_job:
            return False
        
        job_cls = JOB_CLASSES.get(best_job)
        if not job_cls:
            return False
        
        # Try to enlist
        if job_cls.can_enlist(char, state, logic):
            return job_cls.enlist(char, state, logic)
        
        # Need to go somewhere to enlist
        goal = job_cls.get_enlistment_goal(char, state, logic)
        if goal:
            char.goal = goal
        return False
    
    def _do_forage(self, char, state, logic):
        """Forage or steal food."""
        # Check for theft in progress
        theft_target = char.get('theft_target')
        if theft_target:
            data = state.farm_cells.get(theft_target)
            if data and data['state'] == 'ready':
                char.goal = (theft_target[0] + 0.5, theft_target[1] + 0.5)
                return logic.continue_theft(char)
            else:
                char.theft_target = None
        
        # Waiting at farm
        if char.get('theft_waiting'):
            farm_pos = logic.get_farm_waiting_position(char)
            if farm_pos:
                char.goal = farm_pos
            return logic.continue_theft(char)
        
        # Critical hunger - start stealing
        if char.hunger <= HUNGER_CRITICAL:
            wheat_goal = logic._get_wheat_goal(char)
            if wheat_goal:
                char.goal = wheat_goal
            return logic.continue_theft(char) if char.get('theft_target') else False
        
        return False
    
    def _do_wander(self, char, state, logic):
        """Wander aimlessly."""
        # Get character's home area for wandering
        home = char.get('home')
        if home:
            char.goal = logic._get_wander_goal(char, home)
        else:
            # Homeless - use homeless wandering
            char.goal = logic._get_homeless_idle_goal(char)
        return False


class FarmerJob(Job):
    """Farmer: tends crops, pays taxes, sells at market."""
    
    name = "Farmer"
    
    # =========================================================================
    # ENROLLMENT
    # =========================================================================
    
    @classmethod
    def is_eligible(cls, char, state, logic):
        """Farmers need farming skill requirement from JOB_TIERS."""
        if char.get('job') is not None:
            return False
        reqs = cls.get_requirements()
        min_farming = reqs.get('farming', 0)
        farming_skill = char.get('skills', {}).get('farming', 0)
        return farming_skill >= min_farming
    
    @classmethod
    def is_available(cls, state, logic):
        """Check if there's an unowned farm for the steward's allegiance."""
        steward = state.get_steward()
        if not steward:
            return False
        steward_allegiance = steward.get('allegiance')
        if not steward_allegiance:
            return False
        return cls._get_unowned_farm(state, steward_allegiance) is not None
    
    @classmethod
    def can_enlist(cls, char, state, logic):
        """Must be eligible, available, and adjacent to steward."""
        if not cls.is_eligible(char, state, logic):
            return False
        if not cls.is_available(state, logic):
            return False
        steward = state.get_steward()
        if not steward:
            return False
        return logic.is_adjacent(char, steward)
    
    @classmethod
    def enlist(cls, char, state, logic):
        """Assign farmer job, home, bed, barrel."""
        if not cls.can_enlist(char, state, logic):
            return False
        
        steward = state.get_steward()
        steward_allegiance = steward.get('allegiance')
        
        farm_name = cls._get_unowned_farm(state, steward_allegiance)
        if not farm_name:
            return False
        
        allegiance = state.get_allegiance_of_area(farm_name)
        old_allegiance = char.get('allegiance')
        
        char.job = 'Farmer'
        char.home = farm_name
        char.allegiance = allegiance
        char.tax_due_tick = state.ticks + STEWARD_TAX_INTERVAL  # First tax due after 1 year
        
        # Assign farm barrel
        farm_barrel = state.interactables.get_barrel_by_home(farm_name)
        if farm_barrel:
            farm_barrel.owner = char.name
        
        # Assign farm bed
        bed = state.interactables.get_unowned_bed_by_home(farm_name)
        if bed:
            bed.assign_owner(char.name)
        
        name = char.get_display_name()
        if old_allegiance is None:
            state.log_action(f"{name} ENLISTED as Farmer! (gained {allegiance} allegiance)")
        elif old_allegiance != allegiance:
            state.log_action(f"{name} ENLISTED as Farmer! (allegiance changed from {old_allegiance} to {allegiance})")
        else:
            state.log_action(f"{name} ENLISTED as Farmer!")
        return True
    
    @classmethod
    def get_enlistment_goal(cls, char, state, logic):
        """Go to steward to enlist."""
        steward = state.get_steward()
        if steward:
            return (steward.x, steward.y)
        return None
    
    @classmethod
    def _get_unowned_farm(cls, state, allegiance):
        """Find a farm area belonging to allegiance with no farmer assigned."""
        from scenario_world import AREAS
        
        for area in AREAS:
            if area.get('has_farm_cells') and area.get('allegiance') == allegiance:
                farm_name = area['name']
                # Check if any farmer owns this farm
                farm_has_farmer = False
                for char in state.characters:
                    if char.get('job') == 'Farmer' and char.get('home') == farm_name:
                        farm_has_farmer = True
                        break
                if not farm_has_farmer:
                    return farm_name
        return None
    
    # =========================================================================
    # DECIDE
    # =========================================================================
    
    def decide(self, char, state, logic):
        """Farmer decision logic."""
        
        # ===== SURVIVAL =====
        if self._should_flee(char, state, logic):
            return self._do_flee(char, state, logic)
        
        if self._should_fight_back(char, state, logic):
            return self._do_fight_back(char, state, logic)
        
        if self._in_combat(char, state, logic):
            return self._do_combat(char, state, logic)
        
        if self._should_flee_criminal(char, state, logic):
            return self._do_flee_criminal(char, state, logic)
        
        # Frozen - can only try to trade
        if char.get('is_frozen'):
            logic._try_frozen_trade(char)
            return True
        
        # ===== TAXES (farmer-specific, high priority) =====
        if self._should_pay_tax(char, state, logic):
            return self._do_pay_tax(char, state, logic)
        
        # ===== BASIC NEEDS =====
        if self._should_eat(char):
            return self._do_eat(char, state, logic)
        
        if self._should_cook(char, state, logic):
            return self._do_cook(char, state, logic)
        
        # Need wheat from barrel for cooking
        if self._should_get_wheat_from_barrel(char, state, logic):
            return self._do_get_wheat_from_barrel(char, state, logic)
        
        if self._should_sleep(char, state, logic):
            return self._do_sleep(char, state, logic)
        
        # ===== FARMING =====
        
        # Deposit full stacks to barrel
        if self._should_deposit_wheat(char, state, logic):
            return self._do_deposit_wheat(char, state, logic)
        
        # Market time - sell wheat
        if self._is_market_time(state) and self._should_sell_wheat(char, state, logic):
            return self._do_sell_wheat(char, state, logic)
        
        # Farm - harvest ready crops
        return self._do_farm(char, state, logic)
    
    # ===== FARMER-SPECIFIC CONDITIONS =====
    
    def _should_pay_tax(self, char, state, logic):
        """Is tax due?"""
        tax_due_tick = char.get('tax_due_tick')
        if tax_due_tick is None:
            return False
        return state.ticks >= tax_due_tick
    
    def _should_get_wheat_from_barrel(self, char, state, logic):
        """Need to get wheat from barrel for food?"""
        if char.hunger > HUNGER_CHANCE_THRESHOLD:
            return False
        if char.get_item('bread') >= BREAD_PER_BITE:
            return False
        if char.get_item('wheat') >= WHEAT_TO_BREAD_RATIO:
            return False
        
        farm_barrel = state.interactables.get_barrel_by_home(char.home)
        if not farm_barrel:
            return False
        return farm_barrel.get_item('wheat') > 0
    
    def _should_deposit_wheat(self, char, state, logic):
        """Should deposit wheat to barrel?"""
        farm_barrel = state.interactables.get_barrel_by_home(char.home)
        if not farm_barrel:
            return False
        
        # Deposit if inventory full
        if char.is_inventory_full():
            return True
        
        # Deposit full stacks (keep buffer)
        farmer_wheat = char.get_item('wheat')
        wheat_to_keep = BREAD_BUFFER_TARGET
        if farmer_wheat - wheat_to_keep >= ITEMS["wheat"]["stack_size"]:
            if farm_barrel.can_add_item('wheat', 1):
                return True
        return False
    
    def _is_market_time(self, state):
        """Is it market time?"""
        day_tick = state.ticks % TICKS_PER_DAY
        return TICKS_PER_DAY // 2 <= day_tick < TICKS_PER_DAY * 2 // 3
    
    def _should_sell_wheat(self, char, state, logic):
        """Has wheat to sell?"""
        return logic.get_vendor_sellable_goods(char, 'wheat') >= 1
    
    # ===== FARMER-SPECIFIC ACTIONS =====
    
    def _do_pay_tax(self, char, state, logic):
        """Pay tax to steward."""
        steward = state.get_steward_for_allegiance(char.allegiance)
        if not steward:
            return False
        
        # Go to steward if not adjacent
        if not logic.is_adjacent(char, steward):
            char.goal = (steward.x, steward.y)
            return False
        
        # Pay tax
        name = char.get_display_name()
        farm_barrel = state.interactables.get_barrel_by_home(char.home)
        
        farmer_wheat = char.get_item('wheat')
        barrel_wheat = farm_barrel.get_item('wheat') if farm_barrel else 0
        total_wheat = farmer_wheat + barrel_wheat
        
        if total_wheat >= STEWARD_TAX_AMOUNT:
            # Pay from inventory first, then barrel
            amount_needed = STEWARD_TAX_AMOUNT
            from_inventory = min(farmer_wheat, amount_needed)
            if from_inventory > 0:
                char.remove_item('wheat', from_inventory)
                amount_needed -= from_inventory
            if amount_needed > 0 and farm_barrel:
                farm_barrel.remove_item('wheat', amount_needed)
            
            steward.add_item('wheat', STEWARD_TAX_AMOUNT)
            char.tax_due_tick = state.ticks + STEWARD_TAX_INTERVAL
            steward.tax_collection_target = None
            state.log_action(f"{name} paid {STEWARD_TAX_AMOUNT} wheat tax")
        else:
            # Failed to pay - lose job
            state.log_action(f"{name} FAILED to pay tax! (had {total_wheat}, needed {STEWARD_TAX_AMOUNT})")
            char.job = None
            char.home = None
            char.tax_due_tick = None
            steward.tax_collection_target = None
            state.interactables.unassign_bed_owner(char.name)
        return True
    
    def _do_get_wheat_from_barrel(self, char, state, logic):
        """Get wheat from farm barrel."""
        farm_barrel = state.interactables.get_barrel_by_home(char.home)
        if not farm_barrel:
            return False
        
        # Go to barrel if not adjacent
        if not farm_barrel.is_adjacent(char):
            barrel_pos = farm_barrel.position
            if barrel_pos:
                char.goal = (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            return False
        
        # Withdraw wheat
        barrel_wheat = farm_barrel.get_item('wheat')
        amount_needed = BREAD_BUFFER_TARGET - char.get_item('wheat')
        amount_to_withdraw = min(amount_needed, barrel_wheat)
        if amount_to_withdraw > 0 and char.can_add_item('wheat', amount_to_withdraw):
            farm_barrel.remove_item('wheat', amount_to_withdraw)
            char.add_item('wheat', amount_to_withdraw)
            state.log_action(f"{char.get_display_name()} withdrew {amount_to_withdraw} wheat from barrel for food")
            return True
        return False
    
    def _do_deposit_wheat(self, char, state, logic):
        """Deposit wheat to farm barrel."""
        farm_barrel = state.interactables.get_barrel_by_home(char.home)
        if not farm_barrel:
            return False
        
        # Go to barrel if not adjacent
        if not farm_barrel.is_adjacent(char):
            barrel_pos = farm_barrel.position
            if barrel_pos:
                char.goal = (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            return False
        
        # Deposit wheat
        farmer_wheat = char.get_item('wheat')
        wheat_to_keep = BREAD_BUFFER_TARGET
        excess = farmer_wheat - wheat_to_keep
        if excess > 0 and farm_barrel.can_add_item('wheat', excess):
            char.remove_item('wheat', excess)
            farm_barrel.add_item('wheat', excess)
            state.log_action(f"{char.get_display_name()} deposited {excess} wheat to barrel")
            return True
        return False
    
    def _do_sell_wheat(self, char, state, logic):
        """Go to market and sell wheat."""
        market_area = state.get_area_by_role('market')
        if not market_area:
            return False
        
        # Go to market if not there
        if state.get_area_at(char.x, char.y) != market_area:
            char.goal = logic._nearest_in_area(char, market_area)
            return False
        
        # At market - wait for buyers (steward comes to us)
        char.goal = None
        return False
    
    def _do_farm(self, char, state, logic):
        """Farm - go to ready crops and harvest."""
        # Find nearest ready farm cell for our home
        goal = logic._nearest_ready_farm_cell(char, char.home)
        char.goal = goal
        return False


class SoldierJob(Job):
    """Soldier: patrols, responds to crimes, protects citizens."""
    
    name = "Soldier"
    
    # =========================================================================
    # ENROLLMENT
    # =========================================================================
    
    @classmethod
    def is_eligible(cls, char, state, logic):
        """Soldiers need trait requirements from JOB_TIERS."""
        if char.get('job') is not None:
            return False
        reqs = cls.get_requirements()
        morality = char.get_trait('morality')
        confidence = char.get_trait('confidence')
        cunning = char.get_trait('cunning')
        
        morality_ok = morality >= reqs.get('morality_min', 0)
        confidence_ok = confidence >= reqs.get('confidence_min', 0)
        cunning_ok = cunning <= reqs.get('cunning_max', 10)
        
        return morality_ok and confidence_ok and cunning_ok
    
    @classmethod
    def is_available(cls, state, logic):
        """Check if there's a bed and wheat in barracks."""
        military_area = state.get_area_by_role('military_housing')
        if not military_area:
            return False
        
        # Need available bed
        bed = state.interactables.get_unowned_bed_by_home(military_area)
        if not bed:
            return False
        
        # Need wheat in barracks barrel
        barracks_barrel = state.interactables.get_barrel_by_home(military_area)
        if not barracks_barrel:
            return False
        if barracks_barrel.get_item('wheat') < SOLDIER_WHEAT_PAYMENT:
            return False
        
        return True
    
    @classmethod
    def can_enlist(cls, char, state, logic):
        """Must be eligible, available, and in barracks."""
        if not cls.is_eligible(char, state, logic):
            return False
        if not cls.is_available(state, logic):
            return False
        military_area = state.get_area_by_role('military_housing')
        return state.get_area_at(char.x, char.y) == military_area
    
    @classmethod
    def enlist(cls, char, state, logic):
        """Assign soldier job, home, bed."""
        if not cls.can_enlist(char, state, logic):
            return False
        
        old_allegiance = char.get('allegiance')
        military_area = state.get_area_by_role('military_housing')
        allegiance = state.get_allegiance_of_area(military_area)
        
        char.job = 'Soldier'
        char.home = military_area
        char.allegiance = allegiance
        char.soldier_stopped = False
        char.asked_steward_for_wheat = False
        
        # Assign bed in barracks
        bed = state.interactables.get_unowned_bed_by_home(military_area)
        if bed:
            bed.assign_owner(char.name)
        
        name = char.get_display_name()
        if old_allegiance is None:
            state.log_action(f"{name} ENLISTED as Soldier! (gained {allegiance} allegiance)")
        elif old_allegiance != allegiance:
            state.log_action(f"{name} ENLISTED as Soldier! (allegiance changed from {old_allegiance} to {allegiance})")
        else:
            state.log_action(f"{name} RE-ENLISTED as Soldier!")
        return True
    
    @classmethod
    def get_enlistment_goal(cls, char, state, logic):
        """Go to barracks to enlist."""
        military_area = state.get_area_by_role('military_housing')
        if military_area and state.get_area_at(char.x, char.y) != military_area:
            return logic._nearest_in_area(char, military_area)
        return None
    
    # =========================================================================
    # DECIDE
    # =========================================================================
    
    def decide(self, char, state, logic):
        """Soldier decision logic."""
        
        # ===== SURVIVAL (soldiers flee less readily) =====
        
        # Only flee at very low health
        if char.health < 10:
            attacker = logic.get_attacker(char)
            if attacker:
                return self._do_flee(char, state, logic)
        
        # Fight back (soldiers always fight)
        if self._should_fight_back(char, state, logic):
            return self._do_fight_back(char, state, logic)
        
        if self._in_combat(char, state, logic):
            return self._do_combat(char, state, logic)
        
        # Frozen
        if char.get('is_frozen'):
            logic._try_frozen_trade(char)
            return True
        
        # ===== BASIC NEEDS =====
        if self._should_eat(char):
            return self._do_eat(char, state, logic)
        
        if self._should_cook(char, state, logic):
            return self._do_cook(char, state, logic)
        
        # Request wheat from steward if hungry and low on wheat
        if self._should_request_wheat(char, state, logic):
            char.requested_wheat = True
        
        if self._should_sleep(char, state, logic):
            return self._do_sleep(char, state, logic)
        
        # ===== SOLDIER DUTIES =====
        
        # Respond to criminals (soldiers confront, don't flee)
        criminal, intensity = logic.find_known_criminal_nearby(char)
        if criminal:
            return self._do_confront_criminal(char, criminal, state, logic)
        
        # Patrol
        return self._do_patrol(char, state, logic)
    
    # ===== SOLDIER-SPECIFIC =====
    
    def _should_fight_back(self, char, state, logic):
        """Soldiers always fight back."""
        return logic.get_attacker(char) is not None
    
    def _should_request_wheat(self, char, state, logic):
        """Should request wheat from steward?"""
        if char.get('requested_wheat'):
            return False
        return logic.needs_wheat_buffer(char) and char.get_item('wheat') < BREAD_BUFFER_TARGET
    
    def _do_confront_criminal(self, char, criminal, state, logic):
        """Confront and attack a criminal."""
        if char.get('robbery_target') != criminal:
            state.log_action(f"{char.get_display_name()} confronting {criminal.get_display_name()}!")
            char.robbery_target = criminal
        
        if logic.is_adjacent(char, criminal):
            if logic.can_attack(char):
                logic._do_attack(char, criminal)
                return True
            char.goal = None
        else:
            char.goal = (criminal.x, criminal.y)
        return False
    
    def _do_patrol(self, char, state, logic):
        """Patrol the area."""
        # Get patrol waypoints
        military_area = state.get_area_by_role('military_housing')
        if not military_area:
            return self._do_wander(char, state, logic)
        
        waypoints = state.get_patrol_waypoints()
        if not waypoints:
            return self._do_wander(char, state, logic)
        
        char.is_patrolling = True
        
        # Handle checking state
        if char.get('patrol_state') == 'checking':
            wait_ticks = char.get('patrol_wait_ticks', 0)
            if wait_ticks > 0:
                char.patrol_wait_ticks = wait_ticks - 1
                char.goal = None
                return False
            else:
                char.patrol_state = 'marching'
        
        # Get or initialize waypoint
        waypoint_idx = char.get('patrol_waypoint_idx')
        if waypoint_idx is None:
            name_hash = hash(char.name)
            waypoint_idx = name_hash % len(waypoints)
            char.patrol_direction = 1 if (name_hash // len(waypoints)) % 2 == 0 else -1
            char.patrol_waypoint_idx = waypoint_idx
        
        direction = char.get('patrol_direction', 1)
        target_x, target_y = waypoints[waypoint_idx]
        
        # Check if reached waypoint
        dist = math.sqrt((char.x - target_x)**2 + (char.y - target_y)**2)
        
        if dist < PATROL_APPROACH_DISTANCE:
            # Maybe pause to check
            if random.random() < PATROL_CHECK_CHANCE:
                char.patrol_state = 'checking'
                char.patrol_wait_ticks = random.randint(PATROL_CHECK_MIN_TICKS, PATROL_CHECK_MAX_TICKS)
            
            # Advance to next waypoint
            waypoint_idx = (waypoint_idx + direction) % len(waypoints)
            char.patrol_waypoint_idx = waypoint_idx
            
            if char.get('patrol_state') == 'checking':
                char.goal = None
                return False
            
            target_x, target_y = waypoints[waypoint_idx]
        
        char.goal = (target_x, target_y)
        return False


class StewardJob(Job):
    """Steward: collects taxes, feeds soldiers, manages economy."""
    
    name = "Steward"
    
    # =========================================================================
    # ENROLLMENT
    # =========================================================================
    
    @classmethod
    def is_eligible(cls, char, state, logic):
        """Stewards need allegiance and mercantile skill requirement from JOB_TIERS."""
        # Can be unemployed or Trader (promotion)
        current_job = char.get('job')
        if current_job is not None and current_job != 'Trader':
            return False
        if not char.get('allegiance'):
            return False
        reqs = cls.get_requirements()
        min_mercantile = reqs.get('mercantile', 0)
        mercantile_skill = char.get('skills', {}).get('mercantile', 0)
        return mercantile_skill >= min_mercantile
    
    @classmethod
    def is_available(cls, state, logic):
        """Check if steward position is vacant."""
        return state.get_steward() is None
    
    @classmethod
    def is_best_candidate(cls, char, state, logic):
        """Check if this character has the highest mercantile among eligible."""
        if not cls.is_eligible(char, state, logic):
            return False
        
        char_mercantile = char.get('skills', {}).get('mercantile', 0)
        
        for other in state.characters:
            if other == char:
                continue
            if not cls.is_eligible(other, state, logic):
                continue
            other_mercantile = other.get('skills', {}).get('mercantile', 0)
            if other_mercantile > char_mercantile:
                return False
        
        return True
    
    @classmethod
    def can_enlist(cls, char, state, logic):
        """Must be eligible, available, best candidate, and in barracks."""
        if not cls.is_available(state, logic):
            return False
        if not cls.is_best_candidate(char, state, logic):
            return False
        military_area = state.get_area_by_role('military_housing')
        return state.get_area_at(char.x, char.y) == military_area
    
    @classmethod
    def enlist(cls, char, state, logic):
        """Assign steward job (may be promotion from Trader)."""
        if not cls.can_enlist(char, state, logic):
            return False
        
        old_job = char.get('job')
        military_area = state.get_area_by_role('military_housing')
        allegiance = state.get_allegiance_of_area(military_area)
        
        char.job = 'Steward'
        char.home = military_area
        char.allegiance = allegiance
        
        # Reassign bed to barracks
        state.interactables.unassign_bed_owner(char.name)
        bed = state.interactables.get_unowned_bed_by_home(military_area)
        if bed:
            bed.assign_owner(char.name)
        
        # Assign barracks barrel
        barracks_barrel = state.interactables.get_barrel_by_home(military_area)
        if barracks_barrel:
            barracks_barrel.owner = char.name
        
        name = char.get_display_name()
        if old_job:
            state.log_action(f"{name} was promoted from {old_job} to STEWARD!")
        else:
            state.log_action(f"{name} became the village STEWARD!")
        return True
    
    @classmethod
    def get_enlistment_goal(cls, char, state, logic):
        """Go to barracks to become steward."""
        military_area = state.get_area_by_role('military_housing')
        if military_area and state.get_area_at(char.x, char.y) != military_area:
            return logic._nearest_in_area(char, military_area)
        return None
    
    # =========================================================================
    # DECIDE
    # =========================================================================
    
    def decide(self, char, state, logic):
        """Steward decision logic."""
        
        # ===== SURVIVAL =====
        if self._should_flee(char, state, logic):
            return self._do_flee(char, state, logic)
        
        if self._should_fight_back(char, state, logic):
            return self._do_fight_back(char, state, logic)
        
        if self._in_combat(char, state, logic):
            return self._do_combat(char, state, logic)
        
        if self._should_flee_criminal(char, state, logic):
            return self._do_flee_criminal(char, state, logic)
        
        if char.get('is_frozen'):
            logic._try_frozen_trade(char)
            return True
        
        # ===== TAX COLLECTION (steward-specific, high priority) =====
        if self._should_collect_tax(char, state, logic):
            return self._do_collect_tax(char, state, logic)
        
        # ===== FEED SOLDIERS (before own needs) =====
        if self._should_feed_soldiers(char, state, logic):
            return self._do_feed_soldiers(char, state, logic)
        
        # ===== BASIC NEEDS =====
        if self._should_eat(char):
            return self._do_eat(char, state, logic)
        
        if self._should_cook(char, state, logic):
            return self._do_cook(char, state, logic)
        
        # Get wheat from barrel if hungry
        if self._should_get_wheat_from_barrel(char, state, logic):
            return self._do_get_wheat_from_barrel(char, state, logic)
        
        if self._should_sleep(char, state, logic):
            return self._do_sleep(char, state, logic)
        
        # ===== STEWARD DUTIES =====
        
        # Deposit excess wheat
        if self._should_deposit_wheat(char, state, logic):
            return self._do_deposit_wheat(char, state, logic)
        
        # Buy wheat from farmers
        if self._should_buy_wheat(char, state, logic):
            return self._do_buy_wheat(char, state, logic)
        
        # Wander in barracks
        return self._do_wander_barracks(char, state, logic)
    
    # ===== STEWARD-SPECIFIC CONDITIONS =====
    
    def _should_collect_tax(self, char, state, logic):
        """Has a tax collection target?"""
        target = char.get('tax_collection_target')
        return target and target in state.characters
    
    def _should_feed_soldiers(self, char, state, logic):
        """Are there hungry soldiers requesting wheat?"""
        soldiers = logic._get_soldiers_requesting_wheat()
        return len(soldiers) > 0
    
    def _should_get_wheat_from_barrel(self, char, state, logic):
        """Need to get wheat from barrel?"""
        if char.hunger > HUNGER_CHANCE_THRESHOLD:
            return False
        if char.get_item('bread') >= BREAD_PER_BITE:
            return False
        if char.get_item('wheat') >= WHEAT_TO_BREAD_RATIO:
            return False
        
        barracks_barrel = state.interactables.get_barrel_by_home(state.get_area_by_role('military_housing'))
        return barracks_barrel and barracks_barrel.get_item('wheat') > 0
    
    def _should_deposit_wheat(self, char, state, logic):
        """Should deposit excess wheat?"""
        # Only if no hungry soldiers
        if logic._get_soldiers_requesting_wheat():
            return False
        
        personal_wheat = char.get_item('wheat')
        personal_reserve = 3
        return personal_wheat > personal_reserve
    
    def _should_buy_wheat(self, char, state, logic):
        """Should buy wheat from farmers?"""
        return logic.steward_needs_to_buy_wheat(char) and logic.can_afford_goods(char, 'wheat')
    
    # ===== STEWARD-SPECIFIC ACTIONS =====
    
    def _do_collect_tax(self, char, state, logic):
        """Go collect tax from target."""
        target = char.tax_collection_target
        if not target or target not in state.characters:
            char.tax_collection_target = None
            return False
        
        # Go to target if not adjacent
        if not logic.is_adjacent(char, target):
            char.goal = (target.x, target.y)
            return False
        
        # Adjacent - collect tax
        name = char.get_display_name()
        target_name = target.get_display_name()
        farm_barrel = state.interactables.get_barrel_by_home(target.home)
        
        farmer_wheat = target.get_item('wheat')
        barrel_wheat = farm_barrel.get_item('wheat') if farm_barrel else 0
        total_wheat = farmer_wheat + barrel_wheat
        
        if total_wheat >= STEWARD_TAX_AMOUNT:
            amount_needed = STEWARD_TAX_AMOUNT
            from_inventory = min(farmer_wheat, amount_needed)
            if from_inventory > 0:
                target.remove_item('wheat', from_inventory)
                amount_needed -= from_inventory
            if amount_needed > 0 and farm_barrel:
                farm_barrel.remove_item('wheat', amount_needed)
            
            char.add_item('wheat', STEWARD_TAX_AMOUNT)
            target.tax_due_tick = state.ticks + STEWARD_TAX_INTERVAL
            char.tax_collection_target = None
            state.log_action(f"Steward {name} collected {STEWARD_TAX_AMOUNT} wheat tax from {target_name}")
        else:
            state.log_action(f"{target_name} FAILED to pay tax! (had {total_wheat}, needed {STEWARD_TAX_AMOUNT})")
            target.job = None
            target.home = None
            target.tax_due_tick = None
            char.tax_collection_target = None
            state.interactables.unassign_bed_owner(target.name)
        return True
    
    def _do_feed_soldiers(self, char, state, logic):
        """Feed hungry soldiers."""
        soldiers = logic._get_soldiers_requesting_wheat()
        if not soldiers:
            return False
        
        steward_wheat = char.get_item('wheat')
        
        if steward_wheat >= SOLDIER_WHEAT_PAYMENT:
            # Have wheat - go to closest requesting soldier
            closest = min(soldiers, key=lambda s: state.get_distance(char, s))
            
            if logic.is_adjacent(char, closest):
                # Feed soldier
                if closest.can_add_item('wheat', SOLDIER_WHEAT_PAYMENT):
                    char.remove_item('wheat', SOLDIER_WHEAT_PAYMENT)
                    closest.add_item('wheat', SOLDIER_WHEAT_PAYMENT)
                    closest.requested_wheat = False
                    state.log_action(f"Steward {char.get_display_name()} gave {SOLDIER_WHEAT_PAYMENT} wheat to {closest.get_display_name()}")
                    return True
            else:
                char.goal = (closest.x, closest.y)
                return False
        else:
            # Need wheat from barrel
            barracks_barrel = state.interactables.get_barrel_by_home(state.get_area_by_role('military_housing'))
            if barracks_barrel and barracks_barrel.get_item('wheat') > 0:
                if barracks_barrel.is_adjacent(char):
                    # Withdraw wheat
                    amount = min(SOLDIER_WHEAT_PAYMENT * 2, barracks_barrel.get_item('wheat'))
                    if char.can_add_item('wheat', amount):
                        barracks_barrel.remove_item('wheat', amount)
                        char.add_item('wheat', amount)
                        state.log_action(f"Steward {char.get_display_name()} withdrew {amount} wheat from barrel")
                        return True
                else:
                    barrel_pos = barracks_barrel.position
                    if barrel_pos:
                        char.goal = (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
                    return False
        return False
    
    def _do_get_wheat_from_barrel(self, char, state, logic):
        """Get wheat from barracks barrel."""
        barracks_barrel = state.interactables.get_barrel_by_home(state.get_area_by_role('military_housing'))
        if not barracks_barrel:
            return False
        
        if not barracks_barrel.is_adjacent(char):
            barrel_pos = barracks_barrel.position
            if barrel_pos:
                char.goal = (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            return False
        
        # Withdraw wheat
        amount = min(BREAD_BUFFER_TARGET, barracks_barrel.get_item('wheat'))
        if amount > 0 and char.can_add_item('wheat', amount):
            barracks_barrel.remove_item('wheat', amount)
            char.add_item('wheat', amount)
            state.log_action(f"Steward {char.get_display_name()} withdrew {amount} wheat from barrel")
            return True
        return False
    
    def _do_deposit_wheat(self, char, state, logic):
        """Deposit wheat to barracks barrel."""
        barracks_barrel = state.interactables.get_barrel_by_home(state.get_area_by_role('military_housing'))
        if not barracks_barrel:
            return False
        
        if not barracks_barrel.is_adjacent(char):
            barrel_pos = barracks_barrel.position
            if barrel_pos:
                char.goal = (barrel_pos[0] + 0.5, barrel_pos[1] + 0.5)
            return False
        
        personal_wheat = char.get_item('wheat')
        personal_reserve = 3
        excess = personal_wheat - personal_reserve
        if excess > 0 and barracks_barrel.can_add_item('wheat', excess):
            char.remove_item('wheat', excess)
            barracks_barrel.add_item('wheat', excess)
            state.log_action(f"Steward {char.get_display_name()} deposited {excess} wheat into barracks barrel")
            return True
        return False
    
    def _do_buy_wheat(self, char, state, logic):
        """Buy wheat from farmers at market."""
        # Go to market area
        market_area = state.get_area_by_role('market')
        if market_area and state.get_area_at(char.x, char.y) != market_area:
            char.goal = logic._nearest_in_area(char, market_area)
            return False
        
        # Find adjacent farmer willing to sell
        farmer = logic.find_adjacent_vendor(char, 'wheat')
        if farmer and logic.vendor_willing_to_trade(farmer, char, 'wheat'):
            amount = logic.get_max_vendor_trade_amount(farmer, char, 'wheat')
            if amount > 0:
                price = int(amount * ITEMS["wheat"]["price"])
                logic.execute_vendor_trade(farmer, char, 'wheat', amount)
                state.log_action(f"Steward {char.get_display_name()} bought {amount} wheat for ${price}")
                return True
        
        char.goal = None
        return False
    
    def _do_wander_barracks(self, char, state, logic):
        """Wander in barracks area."""
        military_area = state.get_area_by_role('military_housing')
        if military_area and state.get_area_at(char.x, char.y) != military_area:
            char.goal = logic._nearest_in_area(char, military_area)
        else:
            char.goal = logic._get_wander_goal(char, military_area)
        return False


class TraderJob(Job):
    """Trader: self-employed merchant, can be promoted to steward."""
    
    name = "Trader"
    
    # =========================================================================
    # ENROLLMENT
    # =========================================================================
    
    @classmethod
    def is_eligible(cls, char, state, logic):
        """Traders need mercantile skill requirement from JOB_TIERS."""
        if char.get('job') is not None:
            return False
        reqs = cls.get_requirements()
        min_mercantile = reqs.get('mercantile', 0)
        mercantile_skill = char.get('skills', {}).get('mercantile', 0)
        return mercantile_skill >= min_mercantile
    
    @classmethod
    def is_available(cls, state, logic):
        """Trader is self-employed - always available."""
        return True
    
    @classmethod
    def can_enlist(cls, char, state, logic):
        """Traders can start anytime, anywhere if eligible."""
        return cls.is_eligible(char, state, logic)
    
    @classmethod
    def enlist(cls, char, state, logic):
        """Become a self-employed trader."""
        if not cls.can_enlist(char, state, logic):
            return False
        
        char.job = 'Trader'
        # Traders are self-employed - keep current home/camp if they have one
        
        name = char.get_display_name()
        state.log_action(f"{name} became a self-employed Trader!")
        return True
    
    @classmethod
    def get_enlistment_goal(cls, char, state, logic):
        """Traders don't need to go anywhere to start."""
        return None
    
    # =========================================================================
    # DECIDE
    # =========================================================================
    
    def decide(self, char, state, logic):
        """Trader decision logic - mostly like unemployed but can become steward."""
        
        # ===== SURVIVAL =====
        if self._should_flee(char, state, logic):
            return self._do_flee(char, state, logic)
        
        if self._should_fight_back(char, state, logic):
            return self._do_fight_back(char, state, logic)
        
        if self._in_combat(char, state, logic):
            return self._do_combat(char, state, logic)
        
        if self._should_flee_criminal(char, state, logic):
            return self._do_flee_criminal(char, state, logic)
        
        if char.get('is_frozen'):
            logic._try_frozen_trade(char)
            return True
        
        # ===== PROMOTION TO STEWARD =====
        if self._can_become_steward(char, state, logic):
            return self._do_become_steward(char, state, logic)
        
        # ===== BASIC NEEDS =====
        if self._should_eat(char):
            return self._do_eat(char, state, logic)
        
        if self._should_cook(char, state, logic):
            return self._do_cook(char, state, logic)
        
        if self._should_sleep(char, state, logic):
            return self._do_sleep(char, state, logic)
        
        # ===== DEFAULT BEHAVIOR =====
        if self._should_forage(char, state, logic):
            return self._do_forage(char, state, logic)
        
        return self._do_wander(char, state, logic)
    
    def _can_become_steward(self, char, state, logic):
        """Can this trader be promoted to steward?"""
        return StewardJob.is_available(state, logic) and StewardJob.is_best_candidate(char, state, logic)
    
    def _do_become_steward(self, char, state, logic):
        """Try to become steward."""
        if StewardJob.can_enlist(char, state, logic):
            StewardJob.enlist(char, state, logic)
            return True
        
        # Go to barracks
        goal = StewardJob.get_enlistment_goal(char, state, logic)
        if goal:
            char.goal = goal
        return False


# =============================================================================
# JOB REGISTRY
# =============================================================================

# Instance registry for decide() calls
JOB_REGISTRY = {
    'Farmer': FarmerJob(),
    'Soldier': SoldierJob(),
    'Steward': StewardJob(),
    'Trader': TraderJob(),
}

# Class registry for enrollment (class methods)
JOB_CLASSES = {
    'Farmer': FarmerJob,
    'Soldier': SoldierJob,
    'Steward': StewardJob,
    'Trader': TraderJob,
}

# Jobs sorted by tier at module load (lower tier = higher priority)
# This pulls tier from JOB_TIERS in constants.py
JOBS_BY_TIER = sorted(JOB_CLASSES.values(), key=lambda cls: cls.get_tier())

# Default job for unemployed characters
DEFAULT_JOB = Job()


def get_job(job_name):
    """Get the job instance for a job name.
    
    Args:
        job_name: String job name, or None for unemployed
        
    Returns:
        Job instance (never None - returns DEFAULT_JOB for unemployed)
    """
    if job_name is None:
        return DEFAULT_JOB
    return JOB_REGISTRY.get(job_name, DEFAULT_JOB)


def get_job_class(job_name):
    """Get the job class for a job name.
    
    Args:
        job_name: String job name
        
    Returns:
        Job class or None if not found
    """
    return JOB_CLASSES.get(job_name)


def get_best_available_job(char, state, logic):
    """Get the best available job for this character.
    
    Checks jobs in tier order. Within same tier, picks randomly.
    
    Args:
        char: Character seeking job
        state: GameState
        logic: GameLogic
        
    Returns:
        Job name string or None if no jobs available
    """
    if char.get('job') is not None:
        return None
    
    # Group available jobs by tier
    available_by_tier = {}
    for job_cls in JOBS_BY_TIER:
        if job_cls.is_eligible(char, state, logic) and job_cls.is_available(state, logic):
            # Special case: Steward also needs to be best candidate
            if job_cls == StewardJob and not StewardJob.is_best_candidate(char, state, logic):
                continue
            
            tier = job_cls.get_tier()
            if tier not in available_by_tier:
                available_by_tier[tier] = []
            available_by_tier[tier].append(job_cls.name)
    
    # Return job from lowest tier (highest priority)
    if available_by_tier:
        min_tier = min(available_by_tier.keys())
        jobs = available_by_tier[min_tier]
        return random.choice(jobs)
    
    return None


def try_enlist(char, job_name, state, logic):
    """Try to enlist character in a specific job.
    
    Args:
        char: Character to enlist
        job_name: Job name string
        state: GameState
        logic: GameLogic
        
    Returns:
        True if successfully enlisted
    """
    job_cls = JOB_CLASSES.get(job_name)
    if job_cls:
        return job_cls.enlist(char, state, logic)
    return False