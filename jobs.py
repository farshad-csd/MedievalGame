# jobs.py - Job behavior classes with unified decide() pattern
"""
SIMPLIFIED VERSION - Reusable baseline behaviors

Each job defines:
- decide() method: handles ALL character decisions each tick
- Enrollment class methods: is_eligible, is_available, can_enlist, enlist

The decide() method reads top-to-bottom as a priority list.
Base Job class handles core survival and needs - subclasses extend, not replace.
"""

import math
import random
from constants import (
    ITEMS, TICKS_PER_DAY, MAX_HUNGER,
    HUNGER_CHANCE_THRESHOLD, HUNGER_CRITICAL,
    WHEAT_TO_BREAD_RATIO, BREAD_PER_BITE, BREAD_BUFFER_TARGET,
    PATROL_SPEED_MULTIPLIER, PATROL_CHECK_MIN_TICKS, PATROL_CHECK_MAX_TICKS,
    PATROL_CHECK_CHANCE, PATROL_APPROACH_DISTANCE,
    CRIME_INTENSITY_MURDER,
    FLEE_TIMEOUT_TICKS,
    JOB_TIERS, DEFAULT_JOB_TIER,
    SOUND_RADIUS, VISION_RANGE, COMBAT_SPACE, MELEE_ATTACK_DISTANCE
)


class Job:
    """
    Base job - handles core character behavior.
    
    The decide() method is called each tick and should:
    1. Set char.goal = (x, y) if the character should move
    2. Execute any immediate actions (eating, attacking, etc.)
    3. Return True if an action was taken (consumes the tick)
    
    Subclasses should call super().decide() or selectively use _check_* methods
    to build their own priority chains.
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
        """Check if character meets requirements for this job."""
        return False
    
    @classmethod
    def is_available(cls, state, logic):
        """Check if there's an opening for this job."""
        return False
    
    @classmethod
    def can_enlist(cls, char, state, logic):
        """Check if character can enlist right now."""
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
    # MAIN DECIDE METHOD
    # =========================================================================
    
    def decide(self, char, state, logic):
        """
        Core decision loop. Subclasses can override entirely or call this
        as a fallback after checking job-specific priorities.
        
        Returns True if an action was taken, False otherwise.
        """
        # ===== SURVIVAL (highest priority) =====
        if self._check_flee(char, state, logic):
            return self._do_flee(char, state, logic)
        
        if self._check_fight_back(char, state, logic):
            return self._do_fight_back(char, state, logic)
        
        if self._check_combat(char, state, logic):
            return self._do_combat(char, state, logic)
        
        if self._check_watch_threat(char, state, logic):
            return self._do_watch_threat(char, state, logic)
        
        if self._check_flee_criminal(char, state, logic):
            return self._do_flee_criminal(char, state, logic)
        
        if self._check_confront_criminal(char, state, logic):
            return self._do_confront_criminal(char, state, logic)
        
        if self._check_watch_fleeing_person(char, state, logic):
            return self._do_watch_fleeing_person(char, state, logic)
        
        # ===== BASIC NEEDS =====
        if self._check_eat(char, state, logic):
            return self._do_eat(char, state, logic)
        
        if self._check_cook(char, state, logic):
            return self._do_cook(char, state, logic)
        
        if self._check_sleep(char, state, logic):
            return self._do_sleep(char, state, logic)
        
        # ===== FORAGE/THEFT (when desperate) =====
        if self._check_forage(char, state, logic):
            return self._do_forage(char, state, logic)
        
        # ===== DEFAULT =====
        return self._do_wander(char, state, logic)
    
    # =========================================================================
    # CONDITION CHECKS - Override these to customize when behaviors trigger
    # =========================================================================
    
    def _check_flee(self, char, state, logic):
        """Should flee from an attacker (victim) or violence (bystander)?"""
        # Already have flee intent - check if we should continue
        if char.intent and char.intent.get('action') == 'flee':
            reason = char.intent.get('reason')
            target = char.intent.get('target')
            if target and target in state.characters and target.health > 0:
                # Bystanders stop caring once out of perception
                if reason == 'bystander':
                    can_perceive, _ = logic.can_perceive_character(char, target)
                    if not can_perceive:
                        char.clear_intent()
                        return False
                    return True
                # Only handle victim flee reasons here (being_attacked, threat_approaching)
                # witnessed_crime and known_criminal go to _check_flee_criminal
                if reason in ('being_attacked', 'threat_approaching'):
                    return True
            return False
        
        # Check if someone is actively attacking us (recent attack + nearby)
        attacker = char.get_active_attacker(state.ticks, state.characters)
        if attacker:
            return char.get_trait('confidence') < 7
        
        # Also check: do we have attacked_by memory of someone nearby?
        # This catches cases where the attack was a while ago but attacker is back
        if char.get_trait('confidence') < 7:
            for memory in char.get_memories(memory_type='attacked_by'):
                attacker = memory.get('subject')
                if attacker and attacker in state.characters and attacker.health > 0:
                    # Is this attacker nearby (within perception)?
                    can_perceive, _ = logic.can_perceive_character(char, attacker)
                    if can_perceive:
                        # Resume fleeing from this attacker
                        char.set_intent('flee', attacker, reason='being_attacked', started_tick=state.ticks)
                        return True
        
        return False
    
    def _check_watch_threat(self, char, state, logic):
        """Should watch a threat from safe distance?"""
        if char.intent and char.intent.get('action') == 'watch':
            reason = char.intent.get('reason')
            # Handle: monitoring_threat (victim), bystander (saw violence)
            if reason not in ('monitoring_threat', 'bystander'):
                return False
            target = char.intent.get('target')
            if target and target in state.characters and target.health > 0:
                # Stop watching if we can't perceive them anymore
                # For victims: _check_flee will resume via memory if attacker returns
                # For bystanders: they just forget
                can_perceive, _ = logic.can_perceive_character(char, target)
                if not can_perceive:
                    char.clear_intent()
                    return False
                return True
        return False
    
    def _check_fight_back(self, char, state, logic):
        """Should fight back against attacker?"""
        if char.get_trait('confidence') < 7:
            return False
            
        attacker = char.get_active_attacker(state.ticks, state.characters)
        if attacker:
            return True
        
        # Also check: do we have attacked_by memory of someone nearby?
        for memory in char.get_memories(memory_type='attacked_by'):
            attacker = memory.get('subject')
            if attacker and attacker in state.characters and attacker.health > 0:
                # Is this attacker nearby (within perception)?
                can_perceive, _ = logic.can_perceive_character(char, attacker)
                if can_perceive:
                    return True
        
        return False
    
    def _check_combat(self, char, state, logic):
        """Is actively in combat with a target?"""
        if char.intent is None:
            return False
        if char.intent.get('action') != 'attack':
            return False
        target = char.intent.get('target')
        return target and target in state.characters and target.health > 0
    
    def _check_flee_criminal(self, char, state, logic):
        """Should flee from a known criminal (witnessed crime)?"""
        # Already have flee intent for witnessed crime - continue if target is valid
        if char.intent and char.intent.get('action') == 'flee':
            reason = char.intent.get('reason')
            if reason in ('witnessed_crime', 'known_criminal'):
                target = char.intent.get('target')
                if target and target in state.characters and target.health > 0:
                    return True
        
        # New criminal nearby?
        criminal, intensity = logic.find_known_criminal_nearby(char)
        return criminal is not None and char.get_trait('confidence') < 7
    
    def _check_confront_criminal(self, char, state, logic):
        """Should confront a known criminal? (High morality + confidence)"""
        if char.get_trait('morality') < 7 or char.get_trait('confidence') < 7:
            return False
        # Don't switch targets if already attacking someone
        if char.intent and char.intent.get('action') == 'attack':
            return False
        criminal, intensity = logic.find_known_criminal_nearby(char)
        return criminal is not None
    
    def _check_watch_fleeing_person(self, char, state, logic):
        """Should watch someone who is fleeing? (Potential defenders only)"""
        # Only potential defenders do this
        if char.get_trait('morality') < 7 or char.get_trait('confidence') < 7:
            return False
        # Don't switch if already attacking or confronting
        if char.intent and char.intent.get('action') == 'attack':
            return False
        # Already watching someone fleeing - continue if valid
        if char.intent and char.intent.get('action') == 'watch':
            if char.intent.get('reason') == 'monitoring_distress':
                target = char.intent.get('target')
                if target and target in state.characters:
                    # Still fleeing and we can perceive them?
                    if target.intent and target.intent.get('action') == 'flee':
                        can_perceive, _ = logic.can_perceive_character(char, target)
                        if can_perceive:
                            return True
                # Target no longer fleeing or out of range - clear and check for new
                char.clear_intent()
        # Look for someone fleeing within perception range
        fleeing_person = self._find_fleeing_person_nearby(char, state, logic)
        return fleeing_person is not None
    
    def _find_fleeing_person_nearby(self, char, state, logic):
        """Find someone fleeing within perception range."""
        for other in state.characters:
            if other == char:
                continue
            if other.get('health', 100) <= 0:
                continue
            # Check if they're fleeing
            if other.intent and other.intent.get('action') == 'flee':
                # Can we perceive them?
                can_perceive, _ = logic.can_perceive_character(char, other)
                if can_perceive:
                    return other
        return None
    
    def _check_eat(self, char, state, logic):
        """Should eat?"""
        return char.hunger <= HUNGER_CHANCE_THRESHOLD and char.get_item('bread') >= BREAD_PER_BITE
    
    def _check_cook(self, char, state, logic):
        """Should cook bread?"""
        if char.hunger > HUNGER_CHANCE_THRESHOLD:
            return False
        if char.get_item('bread') >= BREAD_PER_BITE:
            return False
        if char.get_item('wheat') < WHEAT_TO_BREAD_RATIO:
            return False
        return logic.can_bake_bread(char)
    
    def _check_sleep(self, char, state, logic):
        """Should sleep?"""
        return state.is_sleep_time()
    
    def _check_forage(self, char, state, logic):
        """Should forage/steal for food?"""
        # Don't forage if we have bread
        if char.get_item('bread') >= BREAD_PER_BITE:
            return False
        # Don't forage if not hungry enough
        if char.hunger > HUNGER_CRITICAL:
            return False
        return True
    
    # =========================================================================
    # ACTIONS - The actual behavior implementations
    # =========================================================================
    
    def _do_flee(self, char, state, logic):
        """Flee from attacker.
        
        Behavior for VICTIMS (being_attacked, witnessed_crime, etc.):
        1. If attacker is dangerously close (< VISION_RANGE/2), flee!
        2. If at safe distance and defender nearby, stay near defender
        3. If at safe distance with no defender, stop and watch attacker
        4. Can report crimes to same-allegiance soldiers via sound
        5. If in same interior as attacker, flee to exit
        6. If outside and own home is in safe direction, can flee into home
        
        Behavior for BYSTANDERS (just saw violence, don't know who's guilty):
        1. Flee until out of danger distance
        2. Then watch until out of perception
        """
        # Get attacker from intent first, fall back to get_active_attacker
        attacker = None
        if char.intent and char.intent.get('action') in ('flee', 'watch'):
            attacker = char.intent.get('target')
            if attacker and (attacker not in state.characters or attacker.health <= 0):
                attacker = None
        
        if not attacker:
            attacker = char.get_active_attacker(state.ticks, state.characters)
        
        if not attacker:
            char.clear_intent()
            return False
        
        # Get current flee reason
        flee_reason = char.intent.get('reason') if char.intent else None
        
        # BYSTANDER: Simple behavior - flee to safe distance, then watch (no cross-zone)
        if flee_reason == 'bystander':
            # Perception check already done in _check_flee, but double-check
            can_perceive, _ = logic.can_perceive_character(char, attacker)
            if not can_perceive:
                char.clear_intent()
                char['face_target'] = None  # Clear face target
                return False
            
            # Set face_target so they backpedal (face attacker while moving away)
            char['face_target'] = attacker
            
            # Check distance - use prevailing coords if same zone
            if char.zone is not None and char.zone == attacker.zone:
                dx = attacker.prevailing_x - char.prevailing_x
                dy = attacker.prevailing_y - char.prevailing_y
            else:
                dx = attacker.x - char.x
                dy = attacker.y - char.y
            dist = math.sqrt(dx*dx + dy*dy)
            
            confidence = char.get_trait('confidence')
            safe_distance = VISION_RANGE / 2 if confidence < 7 else VISION_RANGE / 3
            
            if dist < safe_distance:
                # Too close - keep fleeing (same zone only, use interior-aware flee if applicable)
                if char.zone is not None and char.zone == attacker.zone:
                    interior = state.interiors.get_interior(char.zone)
                    if interior:
                        flee_x, flee_y, flee_zone = logic._get_interior_flee_goal(char, attacker, interior)
                        logic.set_goal_to_position(char, flee_x, flee_y, flee_zone)
                        return False
                flee_pos = logic._get_flee_goal(char, attacker)
                logic.set_goal_same_zone(char, flee_pos[0], flee_pos[1])
                return False
            else:
                # Safe distance - switch to watching
                char.goal = None
                char['face_target'] = None  # Clear - _face_target will handle it
                self._face_target(char, attacker)
                char.set_intent('watch', attacker, reason='bystander', started_tick=state.ticks)
                return False
        
        # VICTIM: Complex flee logic (being_attacked, witnessed_crime, etc.)
        
        # If both in same interior, try to flee within interior first
        if char.zone is not None and attacker.zone == char.zone:
            interior = state.interiors.get_interior(char.zone)
            if interior:
                # Get best flee position (may be inside or exit if cornered)
                flee_x, flee_y, flee_zone = logic._get_interior_flee_goal(char, attacker, interior)
                logic.set_goal_to_position(char, flee_x, flee_y, flee_zone)
                if char.intent is None or char.intent.get('action') not in ('flee', 'watch'):
                    char.set_intent('flee', attacker, reason='being_attacked', started_tick=state.ticks)
                return False
        
        # Set flee intent if not already set
        if char.intent is None or char.intent.get('action') not in ('flee', 'watch'):
            char.set_intent('flee', attacker, reason='being_attacked', started_tick=state.ticks)
        
        # Calculate distance and direction to attacker
        # Use prevailing coords if same zone (correct for interiors)
        if char.zone == attacker.zone and char.zone is not None:
            dx_to_attacker = attacker.prevailing_x - char.prevailing_x
            dy_to_attacker = attacker.prevailing_y - char.prevailing_y
        else:
            dx_to_attacker = attacker.x - char.x
            dy_to_attacker = attacker.y - char.y
        dist_to_attacker = math.sqrt(dx_to_attacker**2 + dy_to_attacker**2)
        
        # Normalize direction to attacker
        if dist_to_attacker > 0.01:
            dir_to_attacker_x = dx_to_attacker / dist_to_attacker
            dir_to_attacker_y = dy_to_attacker / dist_to_attacker
        else:
            dir_to_attacker_x, dir_to_attacker_y = 0, 0
        
        # Check if we can flee into own home (exterior only) - check at ALL distances
        if char.zone is None and attacker.zone is None:
            home_interior = state.interiors.get_interior(char.get('home')) if char.get('home') else None
            if home_interior:
                door_x, door_y = home_interior.get_exit_position()
                if self._is_safe_direction(char, attacker, door_x, door_y):
                    # Target center of home interior
                    center_x = home_interior.width / 2
                    center_y = home_interior.height / 2
                    world_x, world_y = home_interior.interior_to_world(center_x, center_y)
                    logic.set_goal_to_position(char, world_x, world_y, char.get('home'))
                    return False
        
        # PRIORITY 1: Self-preservation - if attacker is too close, FLEE!
        if dist_to_attacker < VISION_RANGE / 2:
            char.set_intent('flee', attacker, reason='being_attacked', started_tick=state.ticks)
            flee_pos = logic._get_flee_goal(char, attacker)
            logic.set_goal_same_zone(char, flee_pos[0], flee_pos[1])
            return False
        
        # Look for any defender in range
        defender = logic.find_nearby_defender(char, VISION_RANGE * 2, exclude=attacker)
        
        if defender:
            # Use prevailing coords if same zone
            if char.zone == defender.zone and char.zone is not None:
                dx_to_defender = defender.prevailing_x - char.prevailing_x
                dy_to_defender = defender.prevailing_y - char.prevailing_y
            else:
                dx_to_defender = defender.x - char.x
                dy_to_defender = defender.y - char.y
            dist_to_defender = math.sqrt(dx_to_defender**2 + dy_to_defender**2)
            
            # Check if going to defender would move us toward attacker
            dot = dx_to_defender * dir_to_attacker_x + dy_to_defender * dir_to_attacker_y
            
            if dist_to_defender > 0.01:
                cos_angle = dot / dist_to_defender
                defender_is_safe_direction = (cos_angle < 0.5)  # Safe if > 60° from attacker
            else:
                defender_is_safe_direction = True
            
            # Can we report via sound? (sound circles overlap)
            can_report_via_sound = dist_to_defender <= (SOUND_RADIUS * 2)
            
            if can_report_via_sound:
                # Report the crime if defender doesn't already know (only works for same-allegiance soldiers)
                self._try_report_attack_to_defender(char, attacker, defender, state, logic)
            
            # PRIORITY 2: If defender is in a safe direction, go to them (cross-zone capable)
            if defender_is_safe_direction:
                logic.set_goal_to_character(char, defender)
                return False
        
        # PRIORITY 3: No safe defender - if at safe distance, stop and watch
        if dist_to_attacker >= VISION_RANGE:
            char.goal = None
            self._face_target(char, attacker)
            char.set_intent('watch', attacker, reason='monitoring_threat', started_tick=state.ticks)
            return False
        
        # Between safe and danger distance - keep moving away
        flee_pos = logic._get_flee_goal(char, attacker)
        logic.set_goal_same_zone(char, flee_pos[0], flee_pos[1])
        return False
    
    def _do_watch_threat(self, char, state, logic):
        """Watch a threat from safe distance.
        
        Behavior:
        - Stand still and face the threat
        - If threat approaches (< VISION_RANGE/2), switch back to flee
        - Victims (monitoring_threat): look for defenders, try to report
        - Bystanders: just watch, perception check done in _check_watch_threat
        """
        threat = char.intent.get('target') if char.intent else None
        if not threat or threat not in state.characters or threat.health <= 0:
            char.clear_intent()
            return False
        
        reason = char.intent.get('reason') if char.intent else None
        
        # Calculate distance to threat - use prevailing coords if same zone
        if char.zone is not None and char.zone == threat.zone:
            dx = threat.prevailing_x - char.prevailing_x
            dy = threat.prevailing_y - char.prevailing_y
        else:
            dx = threat.x - char.x
            dy = threat.y - char.y
        dist_to_threat = math.sqrt(dx * dx + dy * dy)
        
        # If threat got too close, switch to flee
        # Bystanders: low conf keeps more distance, high conf less
        # Victims: use standard VISION_RANGE / 2
        if reason == 'bystander':
            confidence = char.get_trait('confidence')
            flee_distance = VISION_RANGE / 2 if confidence < 7 else VISION_RANGE / 3
        else:
            flee_distance = VISION_RANGE / 2
        if dist_to_threat < flee_distance:
            # Bystanders stay bystanders, victims stay victims
            if reason == 'bystander':
                char.set_intent('flee', threat, reason='bystander', started_tick=state.ticks)
                char['face_target'] = threat  # Backpedal while watching
            else:
                char.set_intent('flee', threat, reason='threat_approaching', started_tick=state.ticks)
            
            # Use interior-aware flee if in same interior
            if char.zone is not None and char.zone == threat.zone:
                interior = state.interiors.get_interior(char.zone)
                if interior:
                    flee_x, flee_y, flee_zone = logic._get_interior_flee_goal(char, threat, interior)
                    logic.set_goal_to_position(char, flee_x, flee_y, flee_zone)
                    state.log_action(f"{char.get_display_name()} fleeing - {threat.get_display_name()} too close!")
                    return False
            
            flee_pos = logic._get_flee_goal(char, threat)
            logic.set_goal_same_zone(char, flee_pos[0], flee_pos[1])
            state.log_action(f"{char.get_display_name()} fleeing - {threat.get_display_name()} too close!")
            return False
        
        # Stand still and face threat
        char.goal = None
        char['face_target'] = None  # Not moving, clear face target
        self._face_target(char, threat)
        
        # Only victims (monitoring_threat) look for defenders and try to go home
        # Bystanders just watch
        if reason == 'monitoring_threat':
            dir_to_threat_x = dx / dist_to_threat if dist_to_threat > 0.01 else 0
            dir_to_threat_y = dy / dist_to_threat if dist_to_threat > 0.01 else 0
            
            # Check if we can go home (exterior only, safe direction)
            if char.zone is None and threat.zone is None:
                home_interior = state.interiors.get_interior(char.get('home')) if char.get('home') else None
                if home_interior:
                    door_x, door_y = home_interior.get_exit_position()
                    if self._is_safe_direction(char, threat, door_x, door_y):
                        # Target center of home interior
                        center_x = home_interior.width / 2
                        center_y = home_interior.height / 2
                        world_x, world_y = home_interior.interior_to_world(center_x, center_y)
                        logic.set_goal_to_position(char, world_x, world_y, char.get('home'))
                        return False
            
            defender = logic.find_nearby_defender(char, VISION_RANGE * 2, exclude=threat)
            if defender:
                dx_to_defender = defender.x - char.x
                dy_to_defender = defender.y - char.y
                dist_to_defender = math.sqrt(dx_to_defender**2 + dy_to_defender**2)
                
                # Can we report via sound?
                if dist_to_defender <= (SOUND_RADIUS * 2):
                    self._try_report_attack_to_defender(char, threat, defender, state, logic)
                
                # Check if defender is in safe direction (> 60° from threat)
                dot = dx_to_defender * dir_to_threat_x + dy_to_defender * dir_to_threat_y
                if dist_to_defender > 0.01:
                    cos_angle = dot / dist_to_defender
                    if cos_angle < 0.5:  # Safe direction (cross-zone capable)
                        logic.set_goal_to_character(char, defender)
        
        return False
    
    def _try_report_attack_to_defender(self, char, attacker, defender, state, logic):
        """Try to report an attack to a defender via sound.
        
        Can only verbally report to same-allegiance soldiers.
        Non-soldiers can still be sought as defenders (so they can witness the crime).
        """
        # Can only verbally report to same-allegiance soldiers
        char_allegiance = char.get('allegiance')
        is_same_allegiance_soldier = (defender.get('job') == 'Soldier' and 
                                       defender.get('allegiance') == char_allegiance and
                                       char_allegiance is not None)
        
        if not is_same_allegiance_soldier:
            return  # Can't report, but will still flee toward them so they can see
        
        # Check if defender already knows about this attacker
        if defender.has_memory_of('crime', attacker):
            return  # Already knows
        
        # Get attack memories about this attacker
        attack_memories = char.get_memories(memory_type='attacked_by', subject=attacker)
        
        if attack_memories:
            # Report the attack
            memory = attack_memories[-1]  # Most recent attack
            defender.add_memory('crime', attacker, state.ticks,
                               location=memory['location'],
                               intensity=memory['intensity'],
                               source='told_by',
                               reported=False,
                               crime_type='assault',
                               victim=char,
                               victim_allegiance=char.get('allegiance'),
                               informant=char)
            
            logic.evaluate_crime_reaction(defender, attacker, memory['intensity'], char.get('allegiance'))
            state.log_action(f"{char.get_display_name()} told {defender.get_display_name()} about {attacker.get_display_name()}'s attack!")
    
    def _do_fight_back(self, char, state, logic):
        """Fight back against attacker."""
        attacker = char.get_active_attacker(state.ticks, state.characters)
        
        # Also check attacked_by memory if no active attacker
        if not attacker:
            for memory in char.get_memories(memory_type='attacked_by'):
                potential = memory.get('subject')
                if potential and potential in state.characters and potential.health > 0:
                    can_perceive, _ = logic.can_perceive_character(char, potential)
                    if can_perceive:
                        attacker = potential
                        break
        
        if not attacker:
            char['combat_track_target'] = None
            return False
        
        # Set attack intent if not already targeting this attacker
        if char.intent is None or char.intent.get('target') is not attacker:
            state.log_action(f"{char.get_display_name()} FIGHTING BACK against {attacker.get_display_name()}!")
            char.set_intent('attack', attacker, reason='self_defense', started_tick=state.ticks)
        
        # Calculate distance to target
        dx = attacker.x - char.x
        dy = attacker.y - char.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        # Attack if in melee range and off cooldown
        if dist <= MELEE_ATTACK_DISTANCE and logic.can_attack(char):
            logic._do_attack(char, attacker)
            return True
        
        # Set combat tracking target - movement system handles the rest
        char['combat_track_target'] = attacker
        char.goal = None
        
        return False
    
    def _do_combat(self, char, state, logic):
        """Continue combat with target."""
        if char.intent is None or char.intent.get('action') != 'attack':
            char['combat_track_target'] = None
            return False
        
        target = char.intent.get('target')
        if not target or target not in state.characters or target.health <= 0:
            char.clear_intent()
            char['combat_track_target'] = None
            return False
        
        # Calculate distance to target
        dx = target.x - char.x
        dy = target.y - char.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        # Attack if in melee range and off cooldown
        if dist <= MELEE_ATTACK_DISTANCE and logic.can_attack(char):
            logic._do_attack(char, target)
            return True
        
        # Set combat tracking target - movement system handles the rest
        char['combat_track_target'] = target
        char.goal = None  # Clear any existing goal
        
        return False
    
    def _do_flee_criminal(self, char, state, logic):
        """Flee from a known criminal.
        
        Behavior (same as _do_flee):
        1. Run AWAY from criminal (not toward defender)
        2. Stop at safe distance and face criminal (watch them)
        3. If criminal approaches again, resume fleeing
        4. If defender comes in range and is in safe direction, go to them
        5. Report crime via sound radius (not adjacency)
        6. Can report to multiple defenders
        7. Prioritize fleeing over going to defender if defender is in dangerous direction
        8. If in same interior as criminal, flee to exit
        9. If outside and own home is in safe direction, can flee into home
        """
        # Get flee target from intent or find new one
        flee_target = None
        if char.intent and char.intent.get('action') == 'flee':
            flee_target = char.intent.get('target')
        
        # Find new criminal if needed
        if not flee_target or flee_target not in state.characters or flee_target.health <= 0:
            criminal, intensity = logic.find_known_criminal_nearby(char)
            if criminal:
                state.log_action(f"{char.get_display_name()} fleeing from {criminal.get_display_name()}!")
                char.set_intent('flee', criminal, reason='known_criminal', started_tick=state.ticks)
                flee_target = criminal
            else:
                char.clear_intent()
                return False
        
        # If both in same interior, try to flee within interior first
        if char.zone is not None and flee_target.zone == char.zone:
            interior = state.interiors.get_interior(char.zone)
            if interior:
                flee_x, flee_y, flee_zone = logic._get_interior_flee_goal(char, flee_target, interior)
                logic.set_goal_to_position(char, flee_x, flee_y, flee_zone)
                return False
        
        # Calculate distance and direction to criminal
        # Use prevailing coords if same zone (correct for interiors)
        if char.zone == flee_target.zone and char.zone is not None:
            dx_to_criminal = flee_target.prevailing_x - char.prevailing_x
            dy_to_criminal = flee_target.prevailing_y - char.prevailing_y
        else:
            dx_to_criminal = flee_target.x - char.x
            dy_to_criminal = flee_target.y - char.y
        dist_to_criminal = math.sqrt(dx_to_criminal**2 + dy_to_criminal**2)
        
        # Normalize direction to criminal
        if dist_to_criminal > 0.01:
            dir_to_criminal_x = dx_to_criminal / dist_to_criminal
            dir_to_criminal_y = dy_to_criminal / dist_to_criminal
        else:
            dir_to_criminal_x, dir_to_criminal_y = 0, 0
        
        # Check if we can flee into own home (exterior only) - check at ALL distances
        if char.zone is None and flee_target.zone is None:
            home_interior = state.interiors.get_interior(char.get('home')) if char.get('home') else None
            if home_interior:
                door_x, door_y = home_interior.get_exit_position()
                if self._is_safe_direction(char, flee_target, door_x, door_y):
                    # Target center of home interior
                    center_x = home_interior.width / 2
                    center_y = home_interior.height / 2
                    world_x, world_y = home_interior.interior_to_world(center_x, center_y)
                    logic.set_goal_to_position(char, world_x, world_y, char.get('home'))
                    return False
        
        # Look for any defender in range
        defender = logic.find_nearby_defender(char, VISION_RANGE * 2, exclude=flee_target)
        
        if defender:
            # Use prevailing coords if same zone
            if char.zone == defender.zone and char.zone is not None:
                dx_to_defender = defender.prevailing_x - char.prevailing_x
                dy_to_defender = defender.prevailing_y - char.prevailing_y
            else:
                dx_to_defender = defender.x - char.x
                dy_to_defender = defender.y - char.y
            dist_to_defender = math.sqrt(dx_to_defender**2 + dy_to_defender**2)
            
            # Check if going to defender would move us toward criminal
            # dot > 0 means defender is somewhat in criminal's direction
            # We use a threshold: only dangerous if defender is within ~60° of criminal direction
            dot = dx_to_defender * dir_to_criminal_x + dy_to_defender * dir_to_criminal_y
            
            # Normalize to get cos(angle): cos < 0.5 means angle > 60°, which is safe
            if dist_to_defender > 0.01:
                cos_angle = dot / dist_to_defender
                defender_is_safe_direction = (cos_angle < 0.5)  # Safe if > 60° from criminal
            else:
                defender_is_safe_direction = True
            
            # Can we report via sound? (sound circles overlap)
            can_report_via_sound = dist_to_defender <= (SOUND_RADIUS * 2)
            
            if can_report_via_sound:
                # Report crimes if defender doesn't already know
                self._try_report_crimes_to_defender(char, flee_target, defender, state, logic)
            
            # Go to defender only if they're in a safe direction (cross-zone capable)
            if defender_is_safe_direction:
                logic.set_goal_to_character(char, defender)
                return False
        
        # No safe defender - decide whether to flee or watch based on distance
        if dist_to_criminal >= VISION_RANGE:
            # Safe distance - stop and watch the criminal
            char.goal = None
            self._face_target(char, flee_target)
            # Clear flee intent since we're just watching now
            char.set_intent('watch', flee_target, reason='monitoring_threat', started_tick=state.ticks)
            return False
        
        if dist_to_criminal < VISION_RANGE / 2:
            # Too close - flee!
            flee_pos = logic._get_flee_goal(char, flee_target)
            logic.set_goal_same_zone(char, flee_pos[0], flee_pos[1])
            return False
        
        # Between safe and danger - keep moving away
        flee_pos = logic._get_flee_goal(char, flee_target)
        logic.set_goal_same_zone(char, flee_pos[0], flee_pos[1])
        return False
    
    def _is_safe_direction(self, char, threat, target_x, target_y):
        """Check if target position is in a safe direction (>60° from threat).
        target_x, target_y are world coords (typically exterior door position).
        Uses world coords for consistency since target is always exterior.
        """
        # Direction to threat (world coords)
        dx_threat = threat.x - char.x
        dy_threat = threat.y - char.y
        dist_threat = math.sqrt(dx_threat**2 + dy_threat**2)
        if dist_threat < 0.01:
            return True  # Threat is on top of us, any direction is fine
        
        dir_threat_x = dx_threat / dist_threat
        dir_threat_y = dy_threat / dist_threat
        
        # Direction to target (world coords)
        dx_target = target_x - char.x
        dy_target = target_y - char.y
        dist_target = math.sqrt(dx_target**2 + dy_target**2)
        if dist_target < 0.01:
            return False  # Already at target
        
        # Dot product gives cos(angle)
        dot = (dx_target * dir_threat_x + dy_target * dir_threat_y) / dist_target
        
        # Safe if angle > 60° (cos < 0.5)
        return dot < 0.5
    
    def _try_report_crimes_to_defender(self, char, criminal, defender, state, logic):
        """Try to report crimes to a defender via sound.
        
        Can only verbally report to same-allegiance soldiers.
        Non-soldiers can still be sought as defenders (so they can witness the crime).
        """
        # Can only verbally report to same-allegiance soldiers
        char_allegiance = char.get('allegiance')
        is_same_allegiance_soldier = (defender.get('job') == 'Soldier' and 
                                       defender.get('allegiance') == char_allegiance and
                                       char_allegiance is not None)
        
        if not is_same_allegiance_soldier:
            return  # Can't report, but will still flee toward them so they can see
        
        # Check if defender already knows about this criminal
        if defender.has_memory_of('crime', criminal):
            return  # Already knows
        
        # Get unreported crimes about this criminal
        crimes = char.get_unreported_crimes_about(criminal)
        
        if crimes:
            # Report the most recent crime
            memory = crimes[-1]
            logic.report_crime_to(char, defender, memory)
            state.log_action(f"{char.get_display_name()} told {defender.get_display_name()} about {criminal.get_display_name()}'s crime!")
    
    def _do_confront_criminal(self, char, state, logic):
        """Confront a known criminal."""
        criminal, intensity = logic.find_known_criminal_nearby(char)
        if not criminal:
            char['combat_track_target'] = None
            return False
        
        # Set attack intent if not already
        if char.intent is None or char.intent.get('target') is not criminal:
            state.log_action(f"{char.get_display_name()} confronting {criminal.get_display_name()}!")
            char.set_intent('attack', criminal, reason='confronting_criminal', started_tick=state.ticks)
        
        # Calculate distance to target
        dx = criminal.x - char.x
        dy = criminal.y - char.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        # Attack if in melee range and off cooldown
        if dist <= MELEE_ATTACK_DISTANCE and logic.can_attack(char):
            logic._do_attack(char, criminal)
            return True
        
        # Set combat tracking target - movement system handles the rest
        char['combat_track_target'] = criminal
        char.goal = None
        
        return False
    
    def _do_watch_fleeing_person(self, char, state, logic):
        """Watch someone who is fleeing - stay in place and observe."""
        # Get current target or find new one
        fleeing_person = None
        if char.intent and char.intent.get('action') == 'watch':
            if char.intent.get('reason') == 'monitoring_distress':
                fleeing_person = char.intent.get('target')
        
        if not fleeing_person or fleeing_person not in state.characters:
            fleeing_person = self._find_fleeing_person_nearby(char, state, logic)
        
        if not fleeing_person:
            char.clear_intent()
            return False
        
        # Check if they're still fleeing
        if not fleeing_person.intent or fleeing_person.intent.get('action') != 'flee':
            char.clear_intent()
            return False
        
        # Can we still perceive them?
        can_perceive, _ = logic.can_perceive_character(char, fleeing_person)
        if not can_perceive:
            char.clear_intent()
            return False
        
        # Set watch intent if not already
        if char.intent is None or char.intent.get('target') is not fleeing_person:
            char.set_intent('watch', fleeing_person, reason='monitoring_distress', started_tick=state.ticks)
            state.log_action(f"{char.get_display_name()} noticed {fleeing_person.get_display_name()} fleeing!")
        
        # Stay in place and face the fleeing person
        char.goal = None
        self._face_target(char, fleeing_person)
        
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
            amount = min(char.get_item('wheat') // WHEAT_TO_BREAD_RATIO, BREAD_BUFFER_TARGET)
            logic.bake_bread(char, amount)
            return True
        
        # Go to cooking spot (cross-zone capable)
        cooking_spot, cooking_pos = logic.get_nearest_cooking_spot(char)
        if cooking_spot:
            # cooking_spot is a dict with 'source' key being the actual object
            stove_obj = cooking_spot.get('source')
            if stove_obj:
                logic.set_goal_to_object(char, stove_obj)
            elif cooking_pos:
                # Fallback if no object (campfire case)
                logic.set_goal_same_zone(char, cooking_pos[0], cooking_pos[1])
        elif char.zone is None and logic.can_make_camp_at(char.x, char.y):
            # Can't camp indoors
            logic.make_camp(char)
            return True
        return False
    
    def _do_sleep(self, char, state, logic):
        """Go to sleep or head to bed."""
        bed = state.get_character_bed(char)
        
        if bed:
            # Calculate distance using world coordinates
            dist = math.sqrt((char.x - bed.world_x)**2 + (char.y - bed.world_y)**2)
            
            # Must be in same zone and close to actually sleep
            if char.zone == bed.zone and dist < 0.15:
                if not char.get('is_sleeping'):
                    char.is_sleeping = True
                    state.log_action(f"{char.get_display_name()} went to sleep")
                char.goal = None
                char.goal_zone = None
                return True
            else:
                # Navigate to bed (cross-zone capable)
                logic.set_goal_to_object(char, bed)
                return False
        else:
            # No bed - make camp (exterior only)
            if char.zone is None and logic.can_make_camp_at(char.x, char.y):
                logic.make_camp(char)
                char.is_sleeping = True
                return True
            elif char.zone is None:
                camp_spot = logic._find_camp_spot(char)
                if camp_spot:
                    logic.set_goal_same_zone(char, camp_spot[0], camp_spot[1])
                return False
            else:
                # Inside an interior with no bed - just stay put
                char.goal = None
                return False
    
    def _do_wander(self, char, state, logic):
        """Wander aimlessly within home area or interior."""
        home = char.get('home')
        if home:
            # _get_wander_goal handles both exterior areas and interior wandering
            wander_goal = logic._get_wander_goal(char, home)
            if wander_goal:
                logic.set_goal_same_zone(char, wander_goal[0], wander_goal[1])
            else:
                char.goal = None
        else:
            # Homeless wandering (exterior only)
            wander_goal = logic._get_homeless_idle_goal(char)
            if wander_goal:
                logic.set_goal_same_zone(char, wander_goal[0], wander_goal[1])
            else:
                char.goal = None
        return False
    
    def _do_forage(self, char, state, logic):
        """Forage or steal food from farms. Farms are always exterior."""
        # Check for theft in progress
        theft_target = char.get('theft_target')
        if theft_target:
            data = state.farm_cells.get(theft_target)
            if data and data['state'] == 'ready':
                char.goal = (theft_target[0] + 0.5, theft_target[1] + 0.5)
                char.goal_zone = None  # Farms are always exterior
                return logic.continue_theft(char)
            else:
                char.theft_target = None
        
        # Waiting at farm for crops to grow
        if char.get('theft_waiting'):
            farm_pos = logic.get_farm_waiting_position(char)
            if farm_pos:
                char.goal = farm_pos
                char.goal_zone = None  # Farms are always exterior
            return logic.continue_theft(char)
        
        # Critical hunger - start looking for food to steal
        if char.hunger <= HUNGER_CRITICAL:
            # Find nearest ready farm cell
            ready_cell = logic.find_nearby_ready_farm_cell(char)
            if ready_cell:
                char.theft_target = ready_cell
                char.goal = (ready_cell[0] + 0.5, ready_cell[1] + 0.5)
                char.goal_zone = None  # Farms are always exterior
                return logic.continue_theft(char)
            else:
                # No ready crops - wait near farm
                char.theft_waiting = True
                farm_pos = logic.get_farm_waiting_position(char)
                if farm_pos:
                    char.goal = farm_pos
                    char.goal_zone = None  # Farms are always exterior
                return False
        
        return False
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _face_target(self, char, target):
        """Make character face toward a target."""
        # Use prevailing coords if same zone (correct for interior facing)
        if char.zone == target.zone and char.zone is not None:
            dx = target.prevailing_x - char.prevailing_x
            dy = target.prevailing_y - char.prevailing_y
        else:
            dx = target.x - char.x
            dy = target.y - char.y
        if abs(dx) > abs(dy):
            char.facing = 'right' if dx > 0 else 'left'
        else:
            char.facing = 'down' if dy > 0 else 'up'


class SoldierJob(Job):
    """
    Soldier: patrols area, responds to threats.
    
    Soldiers don't flee - they always fight back.
    Main duty is patrolling waypoints.
    """
    
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
        """Check if there's a bed in barracks."""
        military_area = state.get_area_by_role('military_housing')
        if not military_area:
            return False
        bed = state.interactables.get_unowned_bed_by_home(military_area)
        return bed is not None
    
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
        
        military_area = state.get_area_by_role('military_housing')
        allegiance = state.get_allegiance_of_area(military_area)
        
        char.job = 'Soldier'
        char.home = military_area
        char.allegiance = allegiance
        
        # Assign bed
        bed = state.interactables.get_unowned_bed_by_home(military_area)
        if bed:
            bed.assign_owner(char.name)
        
        state.log_action(f"{char.get_display_name()} ENLISTED as Soldier!")
        return True
    
    @classmethod
    def get_enlistment_goal(cls, char, state, logic):
        """Go to barracks to enlist. Returns (position, zone) tuple or (None, None)."""
        military_area = state.get_area_by_role('military_housing')
        if military_area and state.get_area_at(char.x, char.y) != military_area:
            pos = logic._nearest_in_area(char, military_area)
            if pos:
                return pos, None  # Barracks is exterior
        return None, None
    
    # =========================================================================
    # DECIDE - Soldiers have modified priorities
    # =========================================================================
    
    def decide(self, char, state, logic):
        """Soldier decision logic - soldiers don't flee, they fight."""
        
        # ===== COMBAT (soldiers always fight) =====
        if self._check_fight_back(char, state, logic):
            return self._do_fight_back(char, state, logic)
        
        if self._check_combat(char, state, logic):
            return self._do_combat(char, state, logic)
        
        # ===== RESPOND TO CRIMINALS =====
        criminal, intensity = logic.find_known_criminal_nearby(char)
        if criminal:
            return self._do_confront_criminal_soldier(char, criminal, state, logic)
        
        # ===== BASIC NEEDS =====
        if self._check_eat(char, state, logic):
            return self._do_eat(char, state, logic)
        
        if self._check_cook(char, state, logic):
            return self._do_cook(char, state, logic)
        
        if self._check_sleep(char, state, logic):
            return self._do_sleep(char, state, logic)
        
        # ===== PATROL (default duty) =====
        return self._do_patrol(char, state, logic)
    
    def _check_fight_back(self, char, state, logic):
        """Soldiers ALWAYS fight back."""
        return char.get_active_attacker(state.ticks, state.characters) is not None
    
    def _do_confront_criminal_soldier(self, char, criminal, state, logic):
        """Soldiers confront criminals aggressively."""
        # Set attack intent if not already targeting this criminal
        if char.intent is None or char.intent.get('target') is not criminal:
            state.log_action(f"{char.get_display_name()} confronting {criminal.get_display_name()}!")
            char.set_intent('attack', criminal, reason='law_enforcement', started_tick=state.ticks)
        
        # Calculate distance to target
        dx = criminal.x - char.x
        dy = criminal.y - char.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        # Attack if in melee range and off cooldown
        if dist <= MELEE_ATTACK_DISTANCE and logic.can_attack(char):
            logic._do_attack(char, criminal)
            return True
        
        # Set combat tracking target - movement system handles the rest
        char['combat_track_target'] = criminal
        char.goal = None
        
        return False
    
    def _do_patrol(self, char, state, logic):
        """Patrol between waypoints."""
        waypoints = state.get_patrol_waypoints()
        if not waypoints:
            return self._do_wander(char, state, logic)
        
        char.is_patrolling = True
        
        # Handle checking/pausing state
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
            # Maybe pause to check area
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
        char.goal_zone = None  # Patrol is always exterior
        return False


# =============================================================================
# JOB REGISTRY
# =============================================================================

JOB_REGISTRY = {
    'Soldier': SoldierJob(),
}

JOB_CLASSES = {
    'Soldier': SoldierJob,
}

JOBS_BY_TIER = sorted(JOB_CLASSES.values(), key=lambda cls: cls.get_tier())

DEFAULT_JOB = Job()


def get_job(job_name):
    """Get the job instance for a job name."""
    if job_name is None:
        return DEFAULT_JOB
    return JOB_REGISTRY.get(job_name, DEFAULT_JOB)


def get_job_class(job_name):
    """Get the job class for a job name."""
    return JOB_CLASSES.get(job_name)


def get_best_available_job(char, state, logic):
    """Get the best available job for this character."""
    if char.get('job') is not None:
        return None
    
    available_by_tier = {}
    for job_cls in JOBS_BY_TIER:
        if job_cls.is_eligible(char, state, logic) and job_cls.is_available(state, logic):
            tier = job_cls.get_tier()
            if tier not in available_by_tier:
                available_by_tier[tier] = []
            available_by_tier[tier].append(job_cls.name)
    
    if available_by_tier:
        min_tier = min(available_by_tier.keys())
        return random.choice(available_by_tier[min_tier])
    
    return None


def try_enlist(char, job_name, state, logic):
    """Try to enlist character in a specific job."""
    job_cls = JOB_CLASSES.get(job_name)
    if job_cls:
        return job_cls.enlist(char, state, logic)
    return False