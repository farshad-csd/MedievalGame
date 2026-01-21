# jobs.py - Job behavior classes with unified decide() pattern
"""
SIMPLIFIED VERSION - Reusable baseline behaviors

Each job defines:
- decide() method: handles ALL character decisions each tick
- Enrollment class methods: is_eligible, is_available, can_enlist, enlist

The decide() method reads top-to-bottom as a priority list.
Base Job class handles core survival and needs - subclasses extend, not replace.
"""

from constants import JOB_TIERS, DEFAULT_JOB_TIER


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
        Core decision loop - defines priority order for NPC decisions.
        Calls game_logic methods in priority order.

        Returns True if an action was taken, False otherwise.
        """
        # ===== SLEEPING (do nothing until woken) =====
        if char.get('is_sleeping'):
            return True

        # ===== SURVIVAL (highest priority) =====
        if logic.check_flee(char):
            return logic.do_flee(char)

        if logic.check_fight_back(char):
            return logic.do_fight_back(char)

        if logic.check_combat(char):
            return logic.do_combat(char)

        if logic.check_watch_threat(char):
            return logic.do_watch_threat(char)

        if logic.check_flee_criminal(char):
            return logic.do_flee_criminal(char)

        if logic.check_confront_criminal(char):
            return logic.do_confront_criminal(char)

        if logic.check_watch_fleeing_person(char):
            return logic.do_watch_fleeing_person(char)

        # ===== BASIC NEEDS =====
        if logic.check_eat(char):
            return logic.do_eat(char)

        if logic.check_cook(char):
            return logic.do_cook(char)

        if logic.check_sleep(char):
            return logic.do_sleep(char)

        # ===== FORAGE/THEFT (when desperate) =====
        if logic.check_forage(char):
            return logic.do_forage(char)

        # ===== DEFAULT =====
        return logic.do_wander(char)
    


class SoldierJob(Job):
    
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

        # ===== SLEEPING (do nothing until woken) =====
        if char.get('is_sleeping'):
            return True

        # ===== COMBAT (soldiers always fight) =====
        if logic.check_fight_back_soldier(char):
            return logic.do_fight_back(char)

        if logic.check_combat(char):
            return logic.do_combat(char)

        # ===== RESPOND TO CRIMINALS =====
        criminal, intensity = logic.find_known_criminal_nearby(char)
        if criminal:
            return logic.do_confront_criminal_soldier(char, criminal)

        # ===== BASIC NEEDS =====
        if logic.check_eat(char):
            return logic.do_eat(char)

        if logic.check_cook(char):
            return logic.do_cook(char)

        if logic.check_sleep(char):
            return logic.do_sleep(char)

        # ===== PATROL (default duty) =====
        return logic.do_patrol(char)
    


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