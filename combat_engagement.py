# combat_engagement.py - Combat engagement state management
"""
CombatEngagementManager handles combat mode state.

This is a PURE REFACTORING of existing game_logic.py code.
All logic is identical - just moved into a separate class for organization.

Responsibilities:
- Managing combat_mode flag for NPCs (player controls their own)
- Auto-equipping weapons when entering combat
- Auto-unequipping weapons when exiting combat
- Determining when NPCs should be in combat mode based on intent

Does NOT handle:
- Combat mechanics (that's combat_system.py)
- AI decisions (that's jobs.py)
- Player combat mode toggle (that's gui.py)
"""


class CombatEngagementManager:
    """Manages combat mode state (who is in combat, weapon equipping)."""

    def __init__(self, game_logic):
        """
        Args:
            game_logic: Reference to GameLogic instance for accessing state
        """
        self.logic = game_logic
        self.state = game_logic.state

    # =========================================================================
    # NPC COMBAT MODE MANAGEMENT
    # =========================================================================

    def update_npc_engagement(self, characters):
        """Update combat mode for NPCs based on their intent.

        MOVED FROM: game_logic.py _process_npc_combat_mode() (line 3873)

        NPCs enter combat mode when:
        - Their intent is 'attack'
        - Their intent is 'flee' (defensive stance)

        NPCs exit combat mode when:
        - They have no intent or a non-combat intent

        When entering combat mode, NPCs auto-equip their strongest weapon.
        When exiting combat mode, NPCs unequip weapons.

        Player combat mode is controlled manually via R key (in gui.py).

        Args:
            characters: List of Character instances to process
        """
        for char in characters:
            # Skip player - player controls their own combat mode
            if char.is_player:
                continue

            # Skip dead characters
            if char.get('health', 100) <= 0:
                continue

            intent = char.intent
            if intent:
                action = intent.get('action')
                # Enter combat mode for attack or flee intents
                if action in ('attack', 'flee'):
                    if not char.get('combat_mode', False):
                        char['combat_mode'] = True
                        # Auto-equip strongest weapon when entering combat
                        char.equip_strongest_weapon()
                else:
                    # Non-combat intent - exit combat mode
                    if char.get('combat_mode', False):
                        char['combat_mode'] = False
                        # Unequip weapon when leaving combat
                        char.equipped_weapon = None
            else:
                # No intent - exit combat mode
                if char.get('combat_mode', False):
                    char['combat_mode'] = False
                    # Unequip weapon when leaving combat
                    char.equipped_weapon = None

    # =========================================================================
    # HELPER METHODS (for future expansion)
    # =========================================================================

    def enter_combat(self, char, reason='unknown'):
        """
        Helper to explicitly enter combat mode.

        Currently just sets the flag and equips weapon (NPCs only - player equips manually).
        In the future, could:
        - Track engagement start time
        - Record engagement reason
        - Trigger combat UI state
        - Apply combat-specific buffs/debuffs

        Args:
            char: Character entering combat
            reason: Why entering combat ('attack', 'flee', 'defending', etc.)
        """
        if char.get('combat_mode', False):
            return  # Already in combat

        char['combat_mode'] = True

        # NPCs auto-equip strongest weapon, player equips manually
        if not char.is_player:
            char.equip_strongest_weapon()

    def exit_combat(self, char):
        """
        Helper to explicitly exit combat mode.

        Currently just clears the flag and unequips weapon (NPCs only - player keeps equipped weapon).
        In the future, could:
        - Clear engagement timers
        - Reset combat-specific state
        - Trigger post-combat cooldowns

        Args:
            char: Character exiting combat
        """
        if not char.get('combat_mode', False):
            return  # Not in combat

        char['combat_mode'] = False

    def is_in_combat(self, char):
        """
        Check if character is currently in combat mode.

        Args:
            char: Character to check

        Returns:
            True if in combat mode, False otherwise
        """
        return char.get('combat_mode', False)
