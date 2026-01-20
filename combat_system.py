# combat_system.py - Combat mechanics system
"""
CombatSystem handles combat action mechanics.

This is a PURE REFACTORING of existing game_logic.py code.
All logic is identical - just moved into a separate class for organization.

Responsibilities:
- Attack cooldown checking
- Hit detection (cone-based)
- Damage application
- Processing pending attacks (animation completion)

Does NOT handle:
- Combat mode state (still in game_logic._process_npc_combat_mode)
- AI decisions (still in jobs.py)
- Crime/witness systems (still in game_logic)
"""

import math
import random
from constants import (
    FISTS, ATTACK_CONE_BASE_ANGLE, ATTACK_CONE_ANGLE,
    CRIME_INTENSITY_ASSAULT, CRIME_INTENSITY_MURDER
)


class CombatSystem:
    """Handles combat action mechanics - extracted from GameLogic for organization."""

    def __init__(self, game_logic):
        """
        Args:
            game_logic: Reference to GameLogic instance for accessing helper methods
        """
        self.logic = game_logic
        self.state = game_logic.state

    # =========================================================================
    # ATTACK VALIDATION
    # =========================================================================

    def can_attack(self, char):
        """Check if character can attack (not on cooldown and in combat mode).

        MOVED FROM: game_logic.py (line 400)

        Returns True if in combat mode and enough time has passed since last attack.
        """
        # Must be in combat mode to attack
        if not char.get('combat_mode', False):
            return False
        weapon_stats = self.logic.get_weapon_stats(char)
        attack_speed = weapon_stats.get('attack_speed', FISTS['attack_speed'])
        last_attack_tick = char.get('last_attack_tick', -attack_speed)
        return self.state.ticks - last_attack_tick >= attack_speed

    # =========================================================================
    # ATTACK RESOLUTION
    # =========================================================================

    def resolve_attack(self, attacker, attack_direction=None, damage_multiplier=1.0):
        """Resolve an attack from a character.

        MOVED FROM: game_logic.py (line 412)

        This is the unified attack resolution used by BOTH player and NPCs.
        Handles: finding targets, dealing damage, witnesses, death, loot.

        Args:
            attacker: Character performing the attack
            attack_direction: Optional direction ('up', 'down', 'left', 'right')
                            If None, uses attacker's current facing
            damage_multiplier: Multiplier for damage (1.0 = normal, 2.0 = double)
                              Used for heavy attacks

        Returns:
            List of characters that were hit
        """
        if attack_direction is None:
            attack_direction = attacker.get('facing', 'down')

        attacker_name = attacker.get_display_name()

        # Get weapon stats (equipped weapon or fists)
        weapon_stats = self.logic.get_weapon_stats(attacker)
        weapon_name = weapon_stats.get('name', 'Fists')
        weapon_reach = weapon_stats.get('range', FISTS['range'])
        damage_min = weapon_stats.get('base_damage_min', 2)
        damage_max = weapon_stats.get('base_damage_max', 5)

        # Check if using 360° aiming (player) or 8-direction (NPCs)
        attack_angle = attacker.get('attack_angle')
        use_360_aiming = attack_angle is not None

        # Get direction vector (for 8-direction fallback)
        dx, dy = self.logic._get_direction_vector(attack_direction)

        # Convert cone angles to radians (half angle for each side)
        # Cone interpolates from BASE at player to FULL at weapon_reach
        half_base_rad = math.radians(ATTACK_CONE_BASE_ANGLE / 2)
        half_full_rad = math.radians(ATTACK_CONE_ANGLE / 2)

        # Find targets in attack arc
        targets_hit = []
        for char in self.state.characters:
            if char is attacker:
                continue

            # Skip dying characters
            if char.get('health', 100) <= 0:
                continue

            # Can only attack characters in the same zone (both exterior or same interior)
            if char.zone != attacker.zone:
                continue

            # Calculate relative position using prevailing coords (local when in interior)
            # This gives correct distance in interior space
            rel_x = char.prevailing_x - attacker.prevailing_x
            rel_y = char.prevailing_y - attacker.prevailing_y

            # Calculate distance to target
            distance = math.sqrt(rel_x * rel_x + rel_y * rel_y)

            # Must be within weapon reach and not at same position
            if distance <= 0 or distance > weapon_reach:
                continue

            if use_360_aiming:
                # 360° angle-based cone detection (player)
                # Interpolate cone half-angle based on distance (wider at range)
                t = distance / weapon_reach  # 0 at player, 1 at max range
                half_cone_rad = half_base_rad + t * (half_full_rad - half_base_rad)

                # Calculate angle to target
                angle_to_target = math.atan2(rel_y, rel_x)

                # Calculate angular difference (handle wraparound)
                angle_diff = angle_to_target - attack_angle
                # Normalize to [-pi, pi]
                while angle_diff > math.pi:
                    angle_diff -= 2 * math.pi
                while angle_diff < -math.pi:
                    angle_diff += 2 * math.pi

                # Hit if within interpolated cone angle
                if abs(angle_diff) <= half_cone_rad:
                    targets_hit.append(char)
            else:
                # 8-direction perpendicular distance method (NPCs)
                if dx != 0 or dy != 0:
                    proj_dist = rel_x * dx + rel_y * dy  # Distance along attack direction
                    perp_dist = abs(rel_x * (-dy) + rel_y * dx)  # Perpendicular distance

                    # Hit if in front and within swing width
                    if proj_dist > 0 and perp_dist < 0.7:
                        targets_hit.append(char)

        # Log miss if no targets (use appropriate verb based on weapon)
        if not targets_hit:
            if weapon_name == 'Fists':
                self.state.log_action(f"{attacker_name} swings fist (missed)")
            else:
                self.state.log_action(f"{attacker_name} swings {weapon_name.lower()} (missed)")
            return []

        # Determine if attacker is a known criminal to anyone
        attacker_is_criminal = self.logic.is_known_criminal(attacker)

        # Deal damage to all targets
        for target in targets_hit:
            target_name = target.get_display_name()

            # Check if target is blocking (blocks attacks from any direction for now)
            if target.is_blocking:
                self.state.log_action(f"{target_name} BLOCKED {attacker_name}'s attack!")
                continue  # Skip damage for this target

            # Calculate and apply damage (with multiplier for heavy attacks)
            base_damage = random.randint(damage_min, damage_max)
            damage = int(base_damage * damage_multiplier)
            old_health = target.health
            target.health -= damage

            # Log with weapon name and attack type (IDENTICAL format to resolve_melee_attack)
            if damage_multiplier > 1.01:
                # Heavy attack
                self.state.log_action(f"{attacker_name} HEAVY ATTACKS {target_name} with {weapon_name} for {damage} damage! (x{damage_multiplier:.1f}) Health: {old_health} -> {target.health}")
            else:
                # Normal attack - vary message based on weapon
                if weapon_name == 'Fists':
                    self.state.log_action(f"{attacker_name} PUNCHES {target_name} for {damage} damage! Health: {old_health} -> {target.health}")
                else:
                    self.state.log_action(f"{attacker_name} ATTACKS {target_name} with {weapon_name} for {damage} damage! Health: {old_health} -> {target.health}")

            # Cancel ongoing action if player is hit
            if target.is_player and target.has_ongoing_action():
                cancelled = target.cancel_ongoing_action()
                if cancelled:
                    action_name = cancelled['action'].title()
                    self.state.log_action(f"{target_name}'s {action_name} interrupted by attack!")

            # Cancel heavy attack charge if player is hit
            if target.is_player and target.is_charging_heavy_attack():
                target.cancel_heavy_attack()
                self.state.log_action(f"{target_name}'s heavy attack interrupted!")

            # Set hit flash for visual feedback
            target['hit_flash_until'] = self.state.ticks + 2  # Flash for ~8 ticks

            # Clear face_target and intent - being hit interrupts current behavior
            # This forces immediate re-evaluation (e.g. bystander -> fight back)
            target['face_target'] = None
            if target.intent and target.intent.get('reason') == 'bystander':
                target.clear_intent()

            # Target remembers being attacked
            self.logic.remember_attack(target, attacker, damage)

            # Update attacker's intent if not already attacking someone
            if attacker.intent is None or attacker.intent.get('action') != 'attack':
                attacker.set_intent('attack', target, reason='initiated_attack', started_tick=self.state.ticks)

            # Check if target was a criminal
            target_was_criminal = self.logic.is_known_criminal(target)

            # If attacking an innocent, this is a crime
            if not target_was_criminal:
                # Attacker records they committed a crime (only once)
                if not attacker_is_criminal:
                    attacker.add_memory('committed_crime', attacker, self.state.ticks,
                                       location=(attacker.x, attacker.y),
                                       intensity=CRIME_INTENSITY_ASSAULT,
                                       source='self',
                                       crime_type='assault', victim=target)
                    attacker_is_criminal = True

                # Witness EVERY attack against an innocent (not just first)
                if target.health > 0:
                    self.logic.witness_crime(attacker, target, 'assault')

            # Handle death
            if target.health <= 0:
                if target_was_criminal and not attacker_is_criminal:
                    # Justified kill
                    self.state.log_action(f"{attacker_name} killed {target_name} (justified)")
                else:
                    # Murder - record and witness
                    attacker.add_memory('committed_crime', attacker, self.state.ticks,
                                       location=(attacker.x, attacker.y),
                                       intensity=CRIME_INTENSITY_MURDER,
                                       source='self',
                                       crime_type='murder', victim=target)
                    self.logic.witness_crime(attacker, target, 'murder')

                # Transfer items to attacker
                attacker.transfer_all_items_from(target)

                # Clear intent if this was the target
                if attacker.intent and attacker.intent.get('target') is target:
                    attacker.clear_intent()

        # Broadcast violence to nearby characters (regardless of justification)
        for target in targets_hit:
            self.logic.broadcast_violence(attacker, target)

        return targets_hit

    def resolve_melee_attack(self, attacker, target):
        """Resolve a direct melee attack against a specific target.

        MOVED FROM: game_logic.py (line 618)

        Used by NPCs who have a specific target (combat, murder intent).

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

        # Get attacker's weapon stats for blocking cone calculation
        attacker_weapon_stats = self.logic.get_weapon_stats(attacker)
        attacker_weapon_reach = attacker_weapon_stats.get('range', FISTS['range'])

        # Check if in melee attack range
        if not self.logic.is_in_melee_range(attacker, target):
            return result

        # Check if target is blocking
        if target.is_blocking:
            # Check if attacker is within target's block cone (same as attack cone)
            block_angle = target.get('attack_angle')
            if block_angle is not None:
                # Calculate angle from target to attacker
                rel_x = attacker.prevailing_x - target.prevailing_x
                rel_y = attacker.prevailing_y - target.prevailing_y
                distance = math.sqrt(rel_x * rel_x + rel_y * rel_y)

                if distance > 0:
                    angle_to_attacker = math.atan2(rel_y, rel_x)

                    # Use attack cone angles for block cone
                    half_base_rad = math.radians(ATTACK_CONE_BASE_ANGLE / 2)
                    half_full_rad = math.radians(ATTACK_CONE_ANGLE / 2)

                    # Interpolate cone angle based on distance (relative to attacker's weapon reach)
                    t = min(distance / attacker_weapon_reach, 1.0)
                    half_cone_rad = half_base_rad + t * (half_full_rad - half_base_rad)

                    # Check if attacker is within block cone
                    angle_diff = angle_to_attacker - block_angle
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi

                    if abs(angle_diff) <= half_cone_rad:
                        # Attack blocked!
                        self.state.log_action(f"{target_name} BLOCKED {attacker_name}'s attack!")
                        result['hit'] = False
                        return result

        result['hit'] = True

        # Get weapon stats (equipped weapon or fists)
        weapon_stats = self.logic.get_weapon_stats(attacker)
        weapon_name = weapon_stats.get('name', 'Fists')
        damage_min = weapon_stats.get('base_damage_min', 2)
        damage_max = weapon_stats.get('base_damage_max', 5)

        # Apply damage
        damage = random.randint(damage_min, damage_max)
        result['damage'] = damage
        old_health = target.health
        target.health -= damage

        # Log with weapon name (IDENTICAL format to resolve_attack)
        if weapon_name == 'Fists':
            self.state.log_action(f"{attacker_name} PUNCHES {target_name} for {damage} damage! Health: {old_health} -> {target.health}")
        else:
            self.state.log_action(f"{attacker_name} ATTACKS {target_name} with {weapon_name} for {damage} damage! Health: {old_health} -> {target.health}")

        # Cancel ongoing action if player is hit
        if target.is_player and target.has_ongoing_action():
            cancelled = target.cancel_ongoing_action()
            if cancelled:
                action_name = cancelled['action'].title()
                self.state.log_action(f"{target_name}'s {action_name} interrupted by attack!")

        # Cancel heavy attack charge if player is hit
        if target.is_player and target.is_charging_heavy_attack():
            target.cancel_heavy_attack()
            self.state.log_action(f"{target_name}'s heavy attack interrupted!")

        # Set hit flash for visual feedback
        target['hit_flash_until'] = self.state.ticks + 2

        # Clear face_target and intent - being hit interrupts current behavior
        target['face_target'] = None
        if target.intent and target.intent.get('reason') == 'bystander':
            target.clear_intent()

        # Target remembers being attacked
        self.logic.remember_attack(target, attacker, damage)

        # Update attacker's intent if not already attacking someone
        if attacker.intent is None or attacker.intent.get('action') != 'attack':
            attacker.set_intent('attack', target, reason='initiated_attack', started_tick=self.state.ticks)

        # Check if target was a criminal
        target_was_criminal = self.logic.is_known_criminal(target)

        # Determine if attacker is a known criminal to anyone
        attacker_is_criminal = self.logic.is_known_criminal(attacker)

        # If attacking an innocent, this is a crime
        if not target_was_criminal:
            if not attacker_is_criminal:
                attacker.add_memory('committed_crime', attacker, self.state.ticks,
                                   location=(attacker.x, attacker.y),
                                   intensity=CRIME_INTENSITY_ASSAULT,
                                   source='self',
                                   crime_type='assault', victim=target)
                attacker_is_criminal = True

            # Witness attack
            if target.health > 0:
                self.logic.witness_crime(attacker, target, 'assault')

        # Handle death
        if target.health <= 0:
            result['killed'] = True

            if target_was_criminal and not attacker_is_criminal:
                # Justified kill
                self.state.log_action(f"{attacker_name} killed {target_name} (justified)")
            else:
                # Murder - record and witness
                attacker.add_memory('committed_crime', attacker, self.state.ticks,
                                   location=(attacker.x, attacker.y),
                                   intensity=CRIME_INTENSITY_MURDER,
                                   source='self',
                                   crime_type='murder', victim=target)
                self.logic.witness_crime(attacker, target, 'murder')

            # Transfer items to attacker
            attacker.transfer_all_items_from(target)

            # Clear intent if this was the target
            if attacker.intent and attacker.intent.get('target') is target:
                attacker.clear_intent()

        # Broadcast violence
        self.logic.broadcast_violence(attacker, target)

        return result

    # =========================================================================
    # PENDING ATTACK PROCESSING
    # =========================================================================

    def process_pending_attacks(self):
        """Process pending attacks when their animations complete.

        MOVED FROM: game_logic.py (line 4229)

        Called every tick. Checks all characters for pending attacks and
        resolves damage when the attack animation has finished.
        """
        for char in self.state.characters:
            # Skip dead characters
            if char.get('health', 100) <= 0:
                continue

            # Check if character has a pending attack and animation is complete
            if char.has_pending_attack() and char.is_attack_animation_complete():
                pending = char.get_and_clear_pending_attack()
                if pending is None:
                    continue

                target = pending.get('target')

                if target is not None:
                    # NPC targeted melee attack
                    result = self.resolve_melee_attack(char, target)

                    # Clear attack intent if target killed
                    if result.get('killed'):
                        if char.intent and char.intent.get('action') == 'attack':
                            char.clear_intent()
                else:
                    # Player AOE cone attack (or NPC without specific target)
                    attack_dir = pending.get('direction', char.facing)
                    multiplier = pending.get('multiplier', 1.0)

                    # Temporarily set attack_angle for resolve_attack
                    old_angle = char.attack_angle
                    char.attack_angle = pending.get('angle')

                    self.resolve_attack(char, attack_dir, damage_multiplier=multiplier)

                    # Restore angle
                    char.attack_angle = old_angle
