# scenario_characters.py - Character definitions
# Edit this file to create new characters within the same simulation structure
# Note: Characters do NOT reference specific locations - homes/beds are assigned at runtime based on jobs

# =============================================================================
# CHARACTER TEMPLATES (JSON-serializable)
# =============================================================================
# Static traits that define character archetypes
# - starting_job determines where they live (Steward -> military_housing, Farmer -> farm, etc.)
# - starting_home is only for characters with no job (homeless/wanderer spawn point)
CHARACTER_TEMPLATES = {
    "Edmund Cole": {
        "attractiveness": 5,
        "confidence": 3,
        "cunning": 9,
        "morality": 7,
        "starting_allegiance": "VILLAGE",
        "starting_job": "Steward",
        "starting_money": 200,
        "starting_food": 0,
        "starting_age": 45,
        "starting_skills": {},
        "is_player": False
    },
    "Wulfred Barley": {
        "attractiveness": 5,
        "confidence": 2,
        "cunning": 3,
        "morality": 8,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_money": 50,
        "starting_food": 36,
        "starting_age": 35,
        "starting_skills": {"farming": 50},
        "is_player": False
    },
    "Gareth Hollow": {
        "attractiveness": 5,
        "confidence": 9,
        "cunning": 3,
        "morality": 9,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_money": 20,
        "starting_food": 0,
        "starting_age": 25,
        "starting_skills": {"strength": 50},
        "is_player": False
    },
    "Brynn Ashford": {
        "attractiveness": 5,
        "confidence": 9,
        "cunning": 3,
        "morality": 9,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_money": 20,
        "starting_food": 0,
        "starting_age": 28,
        "starting_skills": {"strength": 50},
        "is_player": False
    },
    "Harren Slade": {
        "attractiveness": 5,
        "confidence": 9,
        "cunning": 9,
        "morality": 4,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_home": "RUIN",  # Homeless wanderer - spawns at specific location
        "starting_money": 0,
        "starting_food": 0,
        "starting_age": 32,
        "starting_skills": {},
        "is_player": False
    },
    "Aldric Thorne": {
        "attractiveness": 5,
        "confidence": 9,
        "cunning": 9,
        "morality": 5,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_money": 200,
        "starting_food": 0,
        "starting_age": 32,
        "starting_skills": {"mercantile": 50},
        "is_player": False
    },
    "Cade Wren": {
        "attractiveness": 5,
        "confidence": 6,
        "cunning": 10,
        "morality": 7,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_money": 50,
        "starting_food": 0,
        "starting_age": 22,
        "starting_skills": {},
        "is_player": True
    }
}
