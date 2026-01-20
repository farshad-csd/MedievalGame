# scenario_characters.py - Character definitions
# Edit this file to create new characters within the same simulation structure
# Note: Characters do NOT reference specific locations - homes/beds are assigned at runtime based on jobs

# =============================================================================
# CHARACTER TEMPLATES (JSON-serializable)
# =============================================================================
# Static traits that define character archetypes
# - starting_job determines where they live (Steward -> military_housing, Farmer -> farm, etc.)
# - starting_home is only for characters with no job (homeless/wanderer spawn point)
# - starting_inventory is a list of item dicts matching the in-game format:
#   [{'type': 'item_type', 'amount': N}, ...] or None for empty slots
CHARACTER_TEMPLATES = {
    "Wulfred Barley": {
        "attractiveness": 5,
        "confidence": 2,
        "cunning": 3,
        "morality": 8,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_home": "Dunmere Farmhouse 1",
        "starting_inventory": [
            {"type": "gold", "amount": 50},
            {"type": "wheat", "amount": 15},
            {"type": "wheat", "amount": 15},
            {"type": "wheat", "amount": 15},
            {"type": "wheat", "amount": 15},
        ],
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
        "starting_inventory": [],
        "starting_age": 25,
        "starting_skills": {"strength": 50, "swords": 50},
        "is_player": False
    },
    # "Edmund Cole": {
    #     "attractiveness": 5,
    #     "confidence": 3,
    #     "cunning": 9,
    #     "morality": 7,
    #     "starting_allegiance": "Dunmere",
    #     "starting_job": None,
    #     "starting_inventory": [
    #         {"type": "gold", "amount": 200},
    #         {"type": "wheat", "amount": 15},
    #         {"type": "wheat", "amount": 15},
    #         {"type": "wheat", "amount": 15},
    #         {"type": "wheat", "amount": 15},
    #     ],
    #     "starting_age": 45,
    #     "starting_skills": {"mercantile": 70},
    #     "is_player": False
    # },
    "Brynn Ashford": {
        "attractiveness": 5,
        "confidence": 9,
        "cunning": 3,
        "morality": 9,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_inventory": [
            {"type": "longsword", "amount": 1},
            {"type": "bow", "amount": 1},
            None,
            None,
            None,
        ],
        "starting_age": 28,
        "starting_skills": {"strength": 50, "swords": 50},
        "is_player": False
    },
    # "Harren Slade": {
    #     "attractiveness": 5,
    #     "confidence": 9,
    #     "cunning": 9,
    #     "morality": 4,
    #     "starting_allegiance": None,
    #     "starting_job": None,
    #     "starting_inventory": [],
    #     "starting_age": 32,
    #     "starting_skills": {"grifting": 50, "swords": 50},
    #     "is_player": False
    # },
    # "Aldric Thorne": {
    #     "attractiveness": 5,
    #     "confidence": 9,
    #     "cunning": 9,
    #     "morality": 5,
    #     "starting_allegiance": None,
    #     "starting_job": None,
    #     "starting_inventory": [
    #         {"type": "gold", "amount": 200},
    #         None,
    #         None,
    #         None,
    #         None,
    #     ],
    #     "starting_age": 32,
    #     "starting_skills": {"mercantile": 50},
    #     "is_player": False
    # },
    "Cade Wren": {
        "attractiveness": 5,
        "confidence": 10,
        "cunning": 10,
        "morality": 5,
        "starting_allegiance": None,
        "starting_job": None,
        "starting_home": "Dunmere Farmhouse 2",
        "starting_inventory": [
            {"type": "gold", "amount": 50},
            {"type": "warhammer", "amount": 1},
            {"type": "bow", "amount": 1},
            None,
            None,
        ],
        "starting_age": 22,
        "starting_skills": {},
        "is_player": True
    }
}
