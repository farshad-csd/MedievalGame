# Combat System Implementation Document

## Version 1.0 | Complete Technical Specification

---

# TABLE OF CONTENTS

1. Design Philosophy
2. Core Combat Mechanics
3. Stamina System
4. Shield and Blocking
5. Status Effects
6. Weapon Statistics (Complete)
7. Skill Progression
8. AI Behavior
9. Group Combat
10. Terrain and Positioning
11. Implementation Constants

---

# 1. DESIGN PHILOSOPHY

## Core Principles

This combat system is designed around **realism** and **dueling**. It is NOT a hack-and-slash power fantasy. The following principles guide all design decisions:

1. **Player and NPC parity**: NPCs have the same abilities, weapons, stamina, and rules as the player. Every fight is a mirror match with different stats.

2. **No dodge roll**: There is no i-frame invincibility or "get out of jail free" button. Defense comes from blocking, parrying, or not being there.

3. **Positioning over reflexes**: Terrain and spacing matter more than reaction speed. Finding a doorway is smarter than perfecting parry timing.

4. **Realistic group combat**: Being outnumbered is deadly. 3+ enemies in open ground means death without terrain advantage.

5. **Commitment matters**: Every swing locks you into animation. There is no animation canceling. Mistakes are punished.

6. **Stamina as resource**: Blocking, sprinting, and (optionally) attacking cost stamina. Running out means vulnerability.

## Combat Feel Targets

- **Pace**: Slow and methodical. Each swing is a decision.
- **Weight**: Attacks feel heavy. Recovery frames enforce commitment.
- **Tension**: No safety net. Every fight could go wrong.
- **Skill expression**: Parry timing, spacing control, stamina management.
- **Progression feel**: Skills make parry easier, recovery faster, damage higher—but don't break the rules.

## What This System Is NOT

- Not a character action game (no combos that last 30 hits)
- Not a hack-and-slash (you cannot mow down hordes)
- Not forgiving (one mistake in group combat = death)
- Not reflex-based primarily (positioning > reactions)

---

# 2. CORE COMBAT MECHANICS

## 2.1 Attack Structure

All melee attacks have three phases:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   WIND-UP   │ → │    SWING    │ → │  RECOVERY   │
│  (visible)  │    │  (damage)   │    │ (vulnerable)│
└─────────────┘    └─────────────┘    └─────────────┘
```

### Wind-up Phase
- Duration: Weapon-dependent (0.08s to 0.45s)
- Visible telegraph—enemy can see it coming
- Can be interrupted by taking damage (hit stun)
- Movement allowed (weapon-dependent speed)
- CAN be canceled by releasing attack button (no attack occurs)

### Swing Phase
- Duration: Weapon-dependent (0.08s to 0.25s)
- Damage is dealt during this phase
- Hit detection active
- CANNOT be canceled
- Movement allowed (weapon-dependent speed, usually 0%)

### Recovery Phase
- Duration: Weapon-dependent (0.15s to 0.55s)
- Character is vulnerable
- CANNOT block
- CANNOT attack
- CANNOT cancel into any action
- Movement allowed (weapon-dependent speed)

### Total Attack Time
```
Total Attack Time = Wind-up + Swing + Recovery
```
Ranges from 0.31s (Fists) to 1.25s (Warhammer).

## 2.2 Hit Detection

### Attack Cone
Attacks hit within a cone in front of the attacker:
- Cone angle: Weapon-dependent (narrow for thrust, wide for sweep)
- Default: 90° arc for most weapons
- Spear: 30° arc (thrust, narrow)
- Great Sword: 150° arc (sweep, wide)

### Reach
Distance from character center to maximum hit range:
- Measured in cells/units
- Ranges from 0.6 (Fists) to 2.0 (Spear)

### Hit Registration
```
IF target is within reach distance
AND target is within attack cone angle
AND swing phase is active
AND target is not in i-frames (there are none in this system)
THEN hit registers
```

## 2.3 Blocking

### Basic Block
- Activated by holding block button
- Creates a block arc in front of character
- Stops incoming damage from attacks within the arc
- Costs stamina to hold
- Costs additional stamina when hit

### Block Arc
- With Shield: 180° (front half)
- Weapon Only (Medium): 90° (front quarter)
- Weapon Only (Heavy): 60° (narrow cone)
- Quick Melee: Cannot block

### Block Stamina Costs
```
While holding block: 2 stamina per tick
When hit while blocking: 15-30 stamina (setup-dependent)
```

### Guard Break
```
IF stamina reaches 0 while blocking:
    Character enters GUARD BREAK state
    Stunned for 0.8 seconds
    Cannot act during stun
    Next hit received deals 2x damage
```

## 2.4 Parry

Parry is a well-timed block. Same input, different timing.

### Parry Window
The parry window is the time before an enemy attack lands during which pressing block triggers a parry instead of a normal block.

```
IF block button pressed within [parry_window] seconds before enemy hit lands:
    Parry succeeds
ELSE:
    Normal block (or miss if too late)
```

### Parry Windows by Setup
| Setup | Parry Window |
|-------|--------------|
| With Shield | 0.15 seconds |
| Medium Weapon Only | 0.10 seconds |
| Heavy Weapon Only | 0.08 seconds |

### Parry Success Effects
```
ON successful parry:
    Attacker enters STAGGER state
    Attacker cannot act for [stagger_duration]
    Defender stamina cost: 0 (parry is free)
    Defender can act immediately (free hit opportunity)
```

### Parry Stagger Duration by Setup
| Setup | Stagger Duration Inflicted |
|-------|----------------------------|
| With Shield | 0.4 seconds |
| Weapon Only | 0.6 seconds |

Note: Weapon-only parry is harder (smaller window) but more rewarding (longer stagger).

## 2.5 Clash

When two attacks would hit simultaneously, they clash.

### Clash Detection
```
IF attacker_A swing phase overlaps with attacker_B swing phase
AND both attacks would hit each other
AND attacks land within 0.1 seconds of each other:
    CLASH occurs
```

### Clash Effects
```
ON clash:
    Both attacks are canceled (no damage dealt)
    Both characters pushed back 0.3 cells
    Both characters enter brief recovery (0.3 seconds)
    Both characters lose 10 stamina
```

### Clash Purpose
- Prevents simultaneous trades
- Resets to neutral
- Punishes panic swinging (wastes stamina, gains nothing)

## 2.6 Heavy Attack

Some weapons can perform a charged heavy attack.

### Heavy Attack Input
```
Hold attack button:
    IF hold duration >= charge_time:
        Release triggers heavy attack
    ELSE:
        Release triggers normal attack (or nothing if released very early)
```

### Heavy Attack Properties
| Property | Effect |
|----------|--------|
| Damage | Base damage × heavy_multiplier |
| Wind-up | Same as normal attack |
| Swing | Same as normal attack |
| Recovery | Normal recovery + 0.1-0.3s (weapon-dependent) |

### Movement While Charging
| Weapon Class | Movement During Charge |
|--------------|------------------------|
| Medium Melee | 25% speed |
| Heavy Melee | 0% (cannot move) |

### Heavy Attack Availability
| Weapon | Has Heavy Attack | Charge Time | Multiplier |
|--------|------------------|-------------|------------|
| Fists | No | — | — |
| Whip | No | — | — |
| Dagger | No | — | — |
| Tools | No | — | — |
| Axe | Yes | 0.6s | 2.0x |
| Short Sword | Yes | 0.5s | 2.0x |
| Mace | Yes | 0.55s | 2.0x |
| Flail | No | — | — |
| Long Sword | Yes | 0.6s | 2.0x |
| Spear | Yes | 0.7s | 2.0x |
| Warhammer | Yes | 0.9s | 2.5x |
| Halberd | Yes | 0.8s | 2.25x |
| Great Sword | Yes | 0.85s | 2.25x |

### When to Use Heavy Attack
Heavy attacks are rewards for creating openings, not openers themselves:
- After successful parry (enemy staggered, time to charge)
- After enemy whiffs (they're in recovery)
- When enemy is far and approaching (time to prepare)

## 2.7 Combo System

Some weapons can chain multiple attacks.

### Combo Input
```
Attack 1 lands (or is blocked):
    Window opens for 0.4 seconds
    IF attack pressed during window:
        Attack 2 begins (shortened wind-up)
        IF weapon has 3-hit combo AND attack 2 lands/blocked:
            Window opens for 0.4 seconds
            IF attack pressed during window:
                Attack 3 begins (combo finisher)
```

### Combo Rules
1. Must HIT or be BLOCKED to continue (whiff = combo ends)
2. Each hit commits further into the combo
3. Can choose to stop after any hit
4. Final hit has bonus damage but extended recovery

### Combo Damage Scaling
| Hit | Damage Modifier | Recovery Modifier |
|-----|-----------------|-------------------|
| Hit 1 | 100% | Normal |
| Hit 2 | +10-15% | Normal |
| Hit 3 | +25-30% | +0.15-0.2s extended |

### Combo Availability
| Weapon | Combo Hits | Hit 2 Bonus | Hit 3 Bonus |
|--------|------------|-------------|-------------|
| Fists | 2 | +10% damage | — |
| Dagger | 2 | +10% damage | — |
| Short Sword | 2 | +10% damage | — |
| Long Sword | 3 | +10% damage | +25% damage, +0.15s recovery |
| Halberd | 2 | +15% damage | — |
| Great Sword | 3 | +15% damage | +30% damage, +0.2s recovery |

### Combo Tactics
- Stopping after hit 1 or 2: Safe, can block soon
- Committing to hit 3: High damage but long vulnerability window
- If enemy is blocking: Consider stopping (they may parry hit 3)
- If enemy is staggered: Full combo is safe

## 2.8 Movement During Combat

Movement speed is modified during combat actions.

### Movement Speed by Action and Weapon Class
| Action | Quick Melee | Tools | Medium Melee | Heavy Melee |
|--------|-------------|-------|--------------|-------------|
| Wind-up | 100% | 25% | 50% | 0% |
| Swing | 100% | 0% | 0% | 0% |
| Recovery | 100% | 25% | 50% | 0% |
| Charging Heavy | — | — | 25% | 0% |
| Blocking | — | 25% | See Shield section | See Shield section |

### Movement Speed While Blocking
| Setup | Movement Speed |
|-------|----------------|
| With Shield | 50% |
| Medium Weapon Only | 25% |
| Heavy Weapon Only | 0% |

## 2.9 Hit Stun

Taking damage interrupts actions.

### Hit Stun Effects
```
ON taking damage:
    IF currently in wind-up:
        Attack is canceled
    IF currently in swing:
        Attack completes (trade)
    IF currently in recovery:
        Recovery continues (already committed)
    IF currently charging heavy:
        Charge is canceled
    
    Enter HIT STUN state for 0.2 seconds
    Cannot act during hit stun
```

### Hit Stun Implications
- Getting hit during wind-up prevents your attack entirely
- Getting hit during swing allows trade (both attacks land)
- Getting hit while charging cancels your heavy attack

---

# 3. STAMINA SYSTEM

## 3.1 Stamina Pool

### Base Stamina
```
Base stamina: 100
Maximum stamina: 100 + (Endurance skill × 0.5)
At 100 Endurance: 150 stamina
```

### Stamina Regeneration
```
Regen rate: 5 stamina per second
Regen delay: 0.8 seconds after last stamina expenditure
```
Stamina does not regenerate during the delay period.

## 3.2 Stamina Costs

### Action Costs
| Action | Stamina Cost |
|--------|--------------|
| Holding block | 2 per tick (10/second) |
| Blocked hit (with shield) | 15 per hit |
| Blocked hit (weapon only, medium) | 25 per hit |
| Blocked hit (weapon only, heavy) | 30 per hit |
| Successful parry | 0 (free) |
| Sprinting | 2 per tick (10/second) |
| Clash | 10 per clash |

### Optional: Attack Stamina Costs
If desired, attacks can cost stamina:
| Attack Type | Stamina Cost |
|-------------|--------------|
| Light attack | 10 |
| Heavy attack | 25 |
| Combo hit 2 | 10 |
| Combo hit 3 | 15 |

Note: Current design has attacks as free. Add stamina costs if combat feels too spammy.

## 3.3 Stamina States

### Normal (Stamina > 0)
All actions available.

### Depleted (Stamina = 0)
```
IF stamina reaches 0:
    Cannot sprint
    Cannot block (or guard breaks if currently blocking)
    CAN still attack
    CAN still move (normal speed)
    Stamina regeneration begins after delay
```

### Guard Break (Stamina = 0 while blocking)
```
IF stamina reaches 0 while actively blocking:
    Enter GUARD BREAK state
    Stunned for 0.8 seconds
    Cannot perform any action
    Next hit deals 2x damage
    After stun ends, stamina regeneration begins
```

---

# 4. SHIELD AND BLOCKING

## 4.1 Shield Compatibility

### By Weapon
| Weapon | Hands Required | Can Use Shield |
|--------|----------------|----------------|
| Fists | 1 | Yes |
| Whip | 1 | Yes |
| Dagger | 1 | Yes |
| Pickaxe | 2 | No |
| Hoe | 2 | No |
| Shovel | 2 | No |
| Smithing Hammer | 1 | Yes |
| Axe | 1 | Yes |
| Short Sword | 1 | Yes |
| Mace | 1 | Yes |
| Flail | 1 | Yes |
| Long Sword | 1 | Yes |
| Spear | 2 | No |
| Warhammer | 2 | No |
| Halberd | 2 | No |
| Great Sword | 2 | No |
| Bow | 2 | No |
| Crossbow | 2 | No |
| Slingshot | 1 | Yes (not while firing) |

## 4.2 Shield vs No Shield Trade-offs

### Combat Statistics Comparison
| Stat | With Shield | Weapon Only |
|------|-------------|-------------|
| Base Movement Speed | 90% | 100% |
| Attack Speed Modifier | 1.0x | 0.9x (10% faster) |
| Stamina per Blocked Hit | 15 | 25-30 |
| Parry Window | 0.15s | 0.08-0.10s |
| Parry Stagger Inflicted | 0.4s | 0.6s |
| Block Arc | 180° | 60-90° |
| Movement While Blocking | 50% | 0-25% |

### Shield Identity
- Easier defense (larger parry window, wider block arc)
- Cheaper blocking (less stamina per hit)
- Slower offense (no attack speed bonus)
- Reduced mobility (90% base speed)
- Playstyle: Outlast opponent, win stamina war

### No Shield Identity
- Harder defense (tiny parry window, narrow block arc)
- Expensive blocking (more stamina per hit)
- Faster offense (10% faster attacks)
- Better mobility (100% base speed)
- Higher parry reward (0.6s stagger vs 0.4s)
- Playstyle: Aggressive, parry-focused, high risk/reward

## 4.3 Quick Melee and Blocking

Quick Melee weapons (Fists, Dagger, Whip) CANNOT block, even with a shield equipped.

### Why Quick Melee Can't Block
- Fists: Cannot catch a sword blade
- Dagger: Too small to stop incoming weapon
- Whip: Not a defensive tool

### Quick Melee Defense
Quick Melee users defend through:
1. Not being there (full movement during attacks)
2. Getting inside enemy reach (enemy can't swing effectively)
3. Disengaging and re-approaching

### Shield + Quick Melee
Technically possible to equip, but:
- Still cannot block (weapon determines blocking ability)
- Loses Quick Melee movement advantage (shield weight)
- Not recommended—contradictory loadout

---

# 5. STATUS EFFECTS

## 5.1 Bleed

Persistent wound from sharp/piercing weapons. Does NOT stop on its own.

### Bleed Mechanics
```
ON hit with bleed weapon:
    Add 1 bleed stack to target
    No stack limit
    
Bleed ticks once per second
Damage per tick = 2 × stack_count

BLEED DOES NOT STOP
    Does not expire
    Does not decay
    Must use BANDAGE item to remove all stacks
    
IF not bandaged:
    Continues dealing damage indefinitely
    Persists after combat ends
    Will eventually kill target
```

### Bleed Math Examples
| Stacks | Damage/Sec | Time to 100 Damage |
|--------|------------|-------------------|
| 1 | 2 | 50 seconds |
| 2 | 4 | 25 seconds |
| 3 | 6 | 17 seconds |
| 5 | 10 | 10 seconds |
| 10 | 20 | 5 seconds |

### Bleed Weapons
All sharp/piercing weapons cause bleed:
- Whip
- Dagger
- Pickaxe
- Hoe
- Axe
- Short Sword
- Long Sword
- Spear
- Halberd
- Great Sword
- Bow
- Crossbow
- Throwing Knives

### Bandaging
```
BANDAGE item:
    Removes ALL bleed stacks
    Takes time to apply (interruptible)
    Must be out of combat or in safe position
```

## 5.2 Stagger

Interrupts enemy action. Severity determines punishment window.

### Stagger Levels
| Level | Duration | Effect |
|-------|----------|--------|
| Light | 0.15 seconds | Brief flinch, minor interrupt |
| Medium | 0.25 seconds | Action fully canceled |
| Heavy | 3.0 seconds | DAZED: 50% move speed, cannot sprint, cannot parry |

### Stagger Mechanics
```
ON hit with stagger weapon:
    Target enters STAGGER state
    Target's current action is interrupted
    Target cannot act for [stagger_duration]
    
    IF heavy stagger:
        Target enters DAZED state
        Movement speed: 50%
        Cannot sprint
        Cannot parry (can still block)
        Duration: 3 seconds
    
Stagger does NOT stack (refresh only)
```

### Stagger Weapons
| Weapon | Stagger Level |
|--------|---------------|
| Shovel | Light |
| Smithing Hammer | Medium |
| Axe | Light |
| Mace | Medium |
| Flail | Medium |
| Long Sword | Light |
| Spear | Light |
| Warhammer | Heavy |
| Halberd | Medium |
| Great Sword | Medium |
| Bow | Light |
| Crossbow | Medium |
| Explosives | Heavy |

## 5.3 Concuss

Buildup effect that triggers KNOCKOUT when threshold reached. Fight-ending.

### Concuss Mechanics
```
ON hit with concuss weapon:
    Add [buildup_amount] to target's concuss meter
    Roll for instant knockout: random(0,1) < [instant_ko_chance]
    
    IF instant knockout roll succeeds:
        Trigger KNOCKOUT immediately
    
Concuss meter:
    Threshold: 100
    Decay: Meter resets to 0 after 10 seconds without concuss hit
    
IF concuss meter >= 100:
    Trigger KNOCKOUT
    Reset concuss meter to 0

KNOCKOUT state:
    Target is UNCONSCIOUS
    Cannot act at all
    Duration: 2 in-game hours
    Fight is over for this target
    
    What happens next depends on context:
        - NPC may be robbed, captured, killed, left alone
        - Player may wake up robbed, in jail, dead, etc.
```

### Concuss Weapons
| Weapon | Buildup | Instant KO Chance | Hits to KO (no luck) |
|--------|---------|-------------------|----------------------|
| Fists | 10 | 1% | 10 hits |
| Shovel | 20 | 3% | 5 hits |
| Smithing Hammer | 15 | 2% | 7 hits |
| Mace | 25 | 5% | 4 hits |
| Flail | 15 | 2% | 7 hits |
| Warhammer | 40 | 10% | 3 hits |
| Slingshot | 10 | 1% | 10 hits |
| Rocks | 20 | 3% | 5 hits |
| Explosives | 15 (AoE) | 2% | 7 hits |

### Concuss Strategy
- Blunt weapons are for non-lethal takedowns
- High instant KO chance makes Warhammer terrifying (10% per hit)
- Fists can knock someone out but takes sustained beating
- Meter decay means you must maintain pressure

## 5.4 Status Effect Summary by Weapon

| Weapon | Bleed | Stagger | Concuss (buildup / KO%) |
|--------|-------|---------|-------------------------|
| Fists | — | — | 10 / 1% |
| Whip | Yes | — | — |
| Dagger | Yes | — | — |
| Pickaxe | Yes | — | — |
| Hoe | Yes | — | — |
| Shovel | — | Light | 20 / 3% |
| Smithing Hammer | — | Medium | 15 / 2% |
| Axe | Yes | Light | — |
| Short Sword | Yes | — | — |
| Mace | — | Medium | 25 / 5% |
| Flail | — | Medium | 15 / 2% |
| Long Sword | Yes | Light | — |
| Spear | Yes | Light | — |
| Warhammer | — | Heavy | 40 / 10% |
| Halberd | Yes | Medium | — |
| Great Sword | Yes | Medium | — |
| Slingshot | — | — | 10 / 1% |
| Bow | Yes | Light | — |
| Crossbow | Yes | Medium | — |
| Rocks | — | — | 20 / 3% |
| Explosives | — | Heavy | 15 / 2% (AoE) |
| Throwing Knives | Yes | — | — |

## 5.5 Status Effect Design Notes

### Bleed vs Concuss: Lethal vs Non-Lethal
- **Bleed weapons** (sharp): Will kill if untreated. Lethal path.
- **Concuss weapons** (blunt): Knock out without killing. Non-lethal path.
- **Some weapons have both stagger and bleed/concuss**: Stagger creates opening, other effect is the consequence.

### Why No Bleed Severity?
Stacking handles severity naturally. One cut is manageable. Ten cuts is death. Simpler system, same effect.

### Why Instant KO Chance?
- Creates tension: Any hit MIGHT end the fight
- Warhammer at 10% is scary even on first swing
- Rewards aggression with blunt weapons
- Lucky knockout is memorable moment

---

# 6. WEAPON STATISTICS (COMPLETE)

## 6.1 Quick Melee

### Fists
```
Class: Quick Melee
Hands: 1
Shield Compatible: Yes (but cannot block)
Reach: 0.6 cells

Timing:
  Wind-up: 0.08s
  Swing: 0.08s
  Recovery: 0.15s
  Total: 0.31s

Movement During Attack: 100% (all phases)

Damage:
  Base: 8-12
  Heavy Attack: No
  Combo: 2-hit
  Combo Hit 2: +10% damage

Status Effects:
  Bleed: No
  Stagger: None
  Concuss: 10 buildup, 1% instant KO

Special Abilities:
  - Always available (cannot be disarmed)
  - Bonus damage when inside enemy weapon reach (+25%)
```

### Whip
```
Class: Quick Melee
Hands: 1
Shield Compatible: Yes (but cannot block)
Reach: 1.8 cells

Timing:
  Wind-up: 0.15s
  Swing: 0.12s
  Recovery: 0.25s
  Total: 0.52s

Movement During Attack: 100% (all phases)

Damage:
  Base: 10-15
  Heavy Attack: No
  Combo: No

Status Effects:
  Bleed: Yes
  Stagger: None
  Concuss: None

Special Abilities:
  - Ignores shields (wraps around)
```

### Dagger
```
Class: Quick Melee
Hands: 1
Shield Compatible: Yes (but cannot block)
Reach: 0.8 cells

Timing:
  Wind-up: 0.10s
  Swing: 0.10s
  Recovery: 0.20s
  Total: 0.40s

Movement During Attack: 100% (all phases)

Damage:
  Base: 15-20
  Heavy Attack: No
  Combo: 2-hit
  Combo Hit 2: +10% damage

Status Effects:
  Bleed: Yes
  Stagger: None
  Concuss: None

Special Abilities:
  - Backstab: 2x damage when hitting from behind
```

## 6.2 Tools

### Pickaxe
```
Class: Tool
Hands: 2
Shield Compatible: No
Reach: 1.0 cells

Timing:
  Wind-up: 0.35s
  Swing: 0.20s
  Recovery: 0.45s
  Total: 1.00s

Movement During Attack:
  Wind-up: 25%
  Swing: 0%
  Recovery: 25%

Damage:
  Base: 25-35
  Heavy Attack: No
  Combo: No

Status Effects:
  Bleed: Yes
  Stagger: None
  Concuss: None

Block (Weapon Only):
  Stamina per block: 30
  Parry window: 0.08s
  Block arc: 60°
  Movement while blocking: 0%
```

### Hoe
```
Class: Tool
Hands: 2
Shield Compatible: No
Reach: 1.2 cells

Timing:
  Wind-up: 0.32s
  Swing: 0.20s
  Recovery: 0.44s
  Total: 0.96s

Movement During Attack:
  Wind-up: 25%
  Swing: 0%
  Recovery: 25%

Damage:
  Base: 18-25
  Heavy Attack: No
  Combo: No

Status Effects:
  Bleed: Yes
  Stagger: None
  Concuss: None

Block (Weapon Only):
  Stamina per block: 30
  Parry window: 0.08s
  Block arc: 60°
  Movement while blocking: 0%
```

### Shovel
```
Class: Tool
Hands: 2
Shield Compatible: No
Reach: 1.1 cells

Timing:
  Wind-up: 0.32s
  Swing: 0.20s
  Recovery: 0.44s
  Total: 0.96s

Movement During Attack:
  Wind-up: 25%
  Swing: 0%
  Recovery: 25%

Damage:
  Base: 20-28
  Heavy Attack: No
  Combo: No

Status Effects:
  Bleed: No
  Stagger: Light (0.15s)
  Concuss: 20 buildup, 3% instant KO

Block (Weapon Only):
  Stamina per block: 30
  Parry window: 0.08s
  Block arc: 60°
  Movement while blocking: 0%
```

### Smithing Hammer
```
Class: Tool
Hands: 1
Shield Compatible: Yes
Reach: 0.8 cells

Timing:
  Wind-up: 0.28s
  Swing: 0.18s
  Recovery: 0.46s
  Total: 0.92s

Movement During Attack:
  Wind-up: 25%
  Swing: 0%
  Recovery: 25%

Damage:
  Base: 28-35
  Heavy Attack: No
  Combo: No

Status Effects:
  Bleed: No
  Stagger: Medium (0.25s)
  Concuss: 15 buildup, 2% instant KO

Block (With Shield):
  Stamina per block: 15
  Parry window: 0.15s
  Block arc: 180°
  Movement while blocking: 50%

Block (Weapon Only):
  Stamina per block: 25
  Parry window: 0.10s
  Block arc: 90°
  Movement while blocking: 25%
```

## 6.3 Medium Melee

### Axe
```
Class: Medium Melee
Hands: 1
Shield Compatible: Yes
Reach: 1.1 cells

Timing:
  Wind-up: 0.22s
  Swing: 0.18s
  Recovery: 0.40s
  Total: 0.80s

Movement During Attack:
  Wind-up: 50%
  Swing: 0%
  Recovery: 50%

Damage:
  Base: 28-35
  Heavy Attack: Yes
  Heavy Charge Time: 0.6s
  Heavy Multiplier: 2.0x
  Combo: No

Status Effects:
  Bleed: Yes
  Stagger: Light (0.15s)
  Concuss: None

Special Abilities:
  - Shield Breaker: +50% stamina damage when hitting shields

Block (With Shield):
  Stamina per block: 15
  Parry window: 0.15s
  Block arc: 180°
  Movement while blocking: 50%

Block (Weapon Only):
  Stamina per block: 25
  Parry window: 0.10s
  Block arc: 90°
  Movement while blocking: 25%
```

### Short Sword
```
Class: Medium Melee
Hands: 1
Shield Compatible: Yes
Reach: 1.0 cells

Timing:
  Wind-up: 0.18s
  Swing: 0.18s
  Recovery: 0.35s
  Total: 0.71s

Movement During Attack:
  Wind-up: 50%
  Swing: 0%
  Recovery: 50%

Damage:
  Base: 22-30
  Heavy Attack: Yes
  Heavy Charge Time: 0.5s
  Heavy Multiplier: 2.0x
  Combo: 2-hit
  Combo Hit 2: +10% damage

Status Effects:
  Bleed: Yes
  Stagger: None
  Concuss: None

Special Abilities:
  - Fastest medium weapon

Block (With Shield):
  Stamina per block: 15
  Parry window: 0.15s
  Block arc: 180°
  Movement while blocking: 50%

Block (Weapon Only):
  Stamina per block: 25
  Parry window: 0.10s
  Block arc: 90°
  Movement while blocking: 25%
```

### Mace
```
Class: Medium Melee
Hands: 1
Shield Compatible: Yes
Reach: 0.9 cells

Timing:
  Wind-up: 0.20s
  Swing: 0.18s
  Recovery: 0.38s
  Total: 0.76s

Movement During Attack:
  Wind-up: 50%
  Swing: 0%
  Recovery: 50%

Damage:
  Base: 25-32
  Heavy Attack: Yes
  Heavy Charge Time: 0.55s
  Heavy Multiplier: 2.0x
  Combo: No

Status Effects:
  Bleed: No
  Stagger: Medium (0.25s)
  Concuss: 25 buildup, 5% instant KO

Block (With Shield):
  Stamina per block: 15
  Parry window: 0.15s
  Block arc: 180°
  Movement while blocking: 50%

Block (Weapon Only):
  Stamina per block: 25
  Parry window: 0.10s
  Block arc: 90°
  Movement while blocking: 25%
```

### Flail
```
Class: Medium Melee
Hands: 1
Shield Compatible: Yes
Reach: 1.3 cells

Timing:
  Wind-up: 0.25s
  Swing: 0.22s
  Recovery: 0.45s
  Total: 0.92s

Movement During Attack:
  Wind-up: 50%
  Swing: 0%
  Recovery: 50%

Damage:
  Base: 30-38
  Heavy Attack: No
  Combo: No

Status Effects:
  Bleed: No
  Stagger: Medium (0.25s)
  Concuss: 15 buildup, 2% instant KO

Special Abilities:
  - Ignores shields (chain wraps around)

Block (With Shield):
  Stamina per block: 15
  Parry window: 0.15s
  Block arc: 180°
  Movement while blocking: 50%

Block (Weapon Only):
  Stamina per block: 25
  Parry window: 0.10s
  Block arc: 90°
  Movement while blocking: 25%
```

### Long Sword
```
Class: Medium Melee
Hands: 1
Shield Compatible: Yes
Reach: 1.2 cells

Timing:
  Wind-up: 0.20s
  Swing: 0.20s
  Recovery: 0.38s
  Total: 0.78s

Movement During Attack:
  Wind-up: 50%
  Swing: 0%
  Recovery: 50%

Damage:
  Base: 25-32
  Heavy Attack: Yes
  Heavy Charge Time: 0.6s
  Heavy Multiplier: 2.0x
  Combo: 3-hit
  Combo Hit 2: +10% damage
  Combo Hit 3: +25% damage, +0.15s recovery

Status Effects:
  Bleed: Yes
  Stagger: Light (0.15s)
  Concuss: None

Special Abilities:
  - Combo finisher (hit 3) causes guard break if blocked

Block (With Shield):
  Stamina per block: 15
  Parry window: 0.15s
  Block arc: 180°
  Movement while blocking: 50%

Block (Weapon Only):
  Stamina per block: 25
  Parry window: 0.10s
  Block arc: 90°
  Movement while blocking: 25%
```

## 6.4 Heavy Melee

### Spear
```
Class: Heavy Melee
Hands: 2
Shield Compatible: No
Reach: 2.0 cells

Timing:
  Wind-up: 0.35s
  Swing: 0.18s
  Recovery: 0.45s
  Total: 0.98s

Movement During Attack: 0% (all phases)

Damage:
  Base: 35-45
  Heavy Attack: Yes
  Heavy Charge Time: 0.7s
  Heavy Multiplier: 2.0x
  Combo: No

Status Effects:
  Bleed: Yes
  Stagger: Light (0.15s)
  Concuss: None

Special Abilities:
  - Thrust attack: Narrow cone (30°), +0.3 reach (total 2.3)

Block (Weapon Only):
  Stamina per block: 30
  Parry window: 0.08s
  Block arc: 60°
  Movement while blocking: 0%
```

### Warhammer
```
Class: Heavy Melee
Hands: 2
Shield Compatible: No
Reach: 1.2 cells

Timing:
  Wind-up: 0.45s
  Swing: 0.25s
  Recovery: 0.55s
  Total: 1.25s

Movement During Attack: 0% (all phases)

Damage:
  Base: 55-70
  Heavy Attack: Yes
  Heavy Charge Time: 0.9s
  Heavy Multiplier: 2.5x
  Combo: No

Status Effects:
  Bleed: No
  Stagger: Heavy (3.0s daze)
  Concuss: 40 buildup, 10% instant KO

Special Abilities:
  - Guaranteed stagger on every hit
  - Ignores 50% of armor damage reduction

Block (Weapon Only):
  Stamina per block: 30
  Parry window: 0.08s
  Block arc: 60°
  Movement while blocking: 0%
```

### Halberd
```
Class: Heavy Melee
Hands: 2
Shield Compatible: No
Reach: 1.8 cells

Timing:
  Wind-up: 0.40s
  Swing: 0.22s
  Recovery: 0.50s
  Total: 1.12s

Movement During Attack: 0% (all phases, except special)

Damage:
  Base: 45-55
  Heavy Attack: Yes
  Heavy Charge Time: 0.8s
  Heavy Multiplier: 2.25x
  Combo: 2-hit
  Combo Hit 2: +15% damage

Status Effects:
  Bleed: Yes
  Stagger: Medium (0.25s)
  Concuss: None

Special Abilities:
  - Retreat Strike: Can attack while moving backward (25% speed)

Block (Weapon Only):
  Stamina per block: 30
  Parry window: 0.08s
  Block arc: 60°
  Movement while blocking: 0%
```

### Great Sword
```
Class: Heavy Melee
Hands: 2
Shield Compatible: No
Reach: 1.5 cells

Timing:
  Wind-up: 0.42s
  Swing: 0.22s
  Recovery: 0.50s
  Total: 1.14s

Movement During Attack: 0% (all phases)

Damage:
  Base: 50-62
  Heavy Attack: Yes
  Heavy Charge Time: 0.85s
  Heavy Multiplier: 2.25x
  Combo: 3-hit
  Combo Hit 2: +15% damage
  Combo Hit 3: +30% damage, +0.2s recovery

Status Effects:
  Bleed: Yes
  Stagger: Medium (0.25s)
  Concuss: None

Special Abilities:
  - Wide Arc: 150° attack cone, hits all enemies in front

Block (Weapon Only):
  Stamina per block: 30
  Parry window: 0.08s
  Block arc: 60°
  Movement while blocking: 0%
```

## 6.5 Ranged Weapons

### Slingshot
```
Class: Ranged
Hands: 1
Shield Compatible: Yes (not while firing)
Shield Quick-Switch: 0.3s

Movement:
  While Drawing: 100%
  While Aiming: 100%

Timing:
  Draw Time (min): 0.2s
  Draw Time (max): 0.5s
  Recovery After Shot: 0.2s

Range:
  Min Draw: 4 cells
  Max Draw: 8 cells

Projectile:
  Speed (min draw): Slow
  Speed (max draw): Medium
  Accuracy (min draw): ±15°
  Accuracy (max draw): ±5°

Damage:
  Min Draw: 5-8
  Max Draw: 10-15

Status Effects:
  Bleed: No
  Stagger: None
  Concuss: 10 buildup, 1% instant KO

Ammo: Rocks (abundant, found everywhere)
```

### Bow
```
Class: Ranged
Hands: 2
Shield Compatible: No

Movement:
  While Drawing: 50%
  While Aiming: 25%

Timing:
  Draw Time (min): 0.3s
  Draw Time (max): 1.5s
  Recovery After Shot: 0.3s

Range:
  Min Draw: 6 cells
  Max Draw: 15 cells

Projectile:
  Speed (min draw): Slow
  Speed (max draw): Fast
  Accuracy (min draw): ±20°
  Accuracy (max draw): ±2°

Damage:
  Min Draw: 12-18
  Max Draw: 30-40

Status Effects:
  Bleed: Yes
  Stagger: Light (0.15s)
  Concuss: None

Ammo: Arrows (crafted)

Special: All stats (damage, range, accuracy, projectile speed) scale linearly with draw time.
```

### Crossbow
```
Class: Ranged
Hands: 2
Shield Compatible: No

Movement:
  While Aiming: 50%
  While Reloading: 25%

Timing:
  Draw Time: None (instant fire)
  Reload Time: 2.5s
  Recovery After Shot: 0.4s

Range: 18 cells (fixed)

Projectile:
  Speed: Fast
  Accuracy: ±3°

Damage: 45-55 (fixed)

Status Effects:
  Bleed: Yes
  Stagger: Medium (0.25s)
  Concuss: None

Ammo: Bolts (crafted)

Special: No draw time, fires instantly. Long reload makes each shot precious.
```

## 6.6 Throwables

### Rocks
```
Class: Throwable
Hands: 1
Shield Compatible: Yes

Movement While Throwing: 100%

Timing:
  Wind-up: 0.15s
  Recovery: 0.20s

Range: 5 cells
Projectile Speed: Slow
Accuracy: ±12°

Damage: 5-10

Status Effects:
  Bleed: No
  Stagger: None
  Concuss: 20 buildup, 3% instant KO

Ammo Capacity: 10

Special: Found everywhere. Weak but plentiful.
```

### Explosives
```
Class: Throwable
Hands: 1
Shield Compatible: Yes

Movement While Throwing: 50%

Timing:
  Wind-up: 0.35s
  Recovery: 0.45s

Range: 6 cells
Projectile Speed: Medium
Accuracy: ±8°

Damage: 70-90 (area effect)
Blast Radius: 1.5 cells

Status Effects:
  Bleed: No
  Stagger: Heavy (3.0s daze) - all targets in radius
  Concuss: 15 buildup, 2% instant KO - all targets in radius

Ammo Capacity: 3

Special: Damages thrower if too close. Affects all entities in blast radius including allies.
```

### Throwing Knives
```
Class: Throwable
Hands: 1
Shield Compatible: Yes

Movement While Throwing: 100%

Timing:
  Wind-up: 0.12s
  Recovery: 0.18s

Range: 8 cells
Projectile Speed: Fast
Accuracy: ±5°

Damage: 18-25

Status Effects:
  Bleed: Yes
  Stagger: None
  Concuss: None

Ammo Capacity: 6

Special: Silent. Does not alert nearby enemies.
```

## 6.7 Quick Reference Tables

### Damage by Weapon
| Weapon | Base Damage | Heavy Damage | Combo 3 Damage |
|--------|-------------|--------------|----------------|
| Fists | 8-12 | — | — |
| Whip | 10-15 | — | — |
| Dagger | 15-20 | — | — |
| Pickaxe | 25-35 | — | — |
| Hoe | 18-25 | — | — |
| Shovel | 20-28 | — | — |
| Smithing Hammer | 28-35 | — | — |
| Axe | 28-35 | 56-70 | — |
| Short Sword | 22-30 | 44-60 | — |
| Mace | 25-32 | 50-64 | — |
| Flail | 30-38 | — | — |
| Long Sword | 25-32 | 50-64 | 31-40 |
| Spear | 35-45 | 70-90 | — |
| Warhammer | 55-70 | 138-175 | — |
| Halberd | 45-55 | 101-124 | — |
| Great Sword | 50-62 | 113-140 | 65-81 |

### Speed by Weapon
| Weapon | Total Attack Time | Attacks per Second |
|--------|-------------------|-------------------|
| Fists | 0.31s | 3.2 |
| Whip | 0.52s | 1.9 |
| Dagger | 0.40s | 2.5 |
| Short Sword | 0.71s | 1.4 |
| Long Sword | 0.78s | 1.3 |
| Mace | 0.76s | 1.3 |
| Axe | 0.80s | 1.25 |
| Flail | 0.92s | 1.1 |
| Smithing Hammer | 0.92s | 1.1 |
| Tools (avg) | 0.97s | 1.0 |
| Spear | 0.98s | 1.0 |
| Halberd | 1.12s | 0.9 |
| Great Sword | 1.14s | 0.9 |
| Warhammer | 1.25s | 0.8 |

### Hits to Kill (100 HP, no armor)
| Weapon | Light Attacks | Heavy Attack | With Bleed |
|--------|---------------|--------------|------------|
| Fists | 8-12 | — | — |
| Dagger | 5-7 | — | 4-5 |
| Short Sword | 3-5 | 2 | 3-4 |
| Long Sword | 3-4 | 2 | 3 |
| Axe | 3-4 | 2 | 2-3 |
| Spear | 2-3 | 1-2 | 2 |
| Great Sword | 2 | 1 | 1-2 |
| Warhammer | 1-2 | 1 | — |

---

# 7. SKILL PROGRESSION

## 7.1 Skill Effects on Combat

### Strength
```
Effect: Increases damage dealt
Scaling: Linear
Formula: damage = base_damage × (1 + (strength / 100) × 0.5)

At Strength 0: 1.0x damage (no bonus)
At Strength 50: 1.25x damage (+25%)
At Strength 100: 1.5x damage (+50%)
```

### Agility
```
Effect: Reduces recovery time
Scaling: Linear
Formula: recovery = base_recovery × (1 - (agility / 100) × 0.3)

At Agility 0: 1.0x recovery (no reduction)
At Agility 50: 0.85x recovery (-15%)
At Agility 100: 0.7x recovery (-30%)

Example with Short Sword (0.35s base recovery):
  Agility 0: 0.35s
  Agility 50: 0.30s
  Agility 100: 0.25s
```

### Weapon Skills (Swords, Axes, etc.)
```
Effect: Increases parry window
Scaling: Linear
Formula: parry_window = base_window × (1 + (skill / 100) × 1.0)

At Skill 0: 1.0x parry window
At Skill 50: 1.5x parry window (+50%)
At Skill 100: 2.0x parry window (+100%)

Example with Shield (0.15s base parry window):
  Skill 0: 0.15s
  Skill 50: 0.225s
  Skill 100: 0.30s

Example with Weapon Only (0.10s base parry window):
  Skill 0: 0.10s
  Skill 50: 0.15s
  Skill 100: 0.20s
```

### Endurance
```
Effects:
  1. Increases maximum stamina
  2. Reduces block stamina cost

Stamina Formula: max_stamina = 100 + (endurance / 100) × 50
  At Endurance 0: 100 stamina
  At Endurance 50: 125 stamina
  At Endurance 100: 150 stamina

Block Cost Formula: block_cost = base_cost × (1 - (endurance / 100) × 0.25)
  At Endurance 0: 1.0x cost
  At Endurance 50: 0.875x cost (-12.5%)
  At Endurance 100: 0.75x cost (-25%)
```

## 7.2 Skill Progression Summary

| Skill | Effect | At 50 | At 100 |
|-------|--------|-------|--------|
| Strength | +Damage | +25% | +50% |
| Agility | -Recovery | -15% | -30% |
| Weapon Skill | +Parry Window | +50% | +100% |
| Endurance | +Stamina, -Block Cost | +25 stam, -12.5% cost | +50 stam, -25% cost |

## 7.3 Progression Feel

### Early Game (Skills 0-25)
- Tight parry windows (requires precise timing)
- Long recovery (mistakes are very punishing)
- Low stamina (can only block a few hits)
- Combat is demanding and tense

### Mid Game (Skills 25-50)
- Parry becomes more forgiving
- Recovery shortens noticeably
- More stamina for blocking
- Combat feels more manageable

### Late Game (Skills 50-100)
- Parry windows feel generous
- Quick recovery enables aggression
- Large stamina pool for sustained combat
- Combat feels masterful but not trivial

### Design Philosophy
The mechanics stay identical. Numbers shift in player's favor. A skilled player at level 1 can beat an unskilled player at level 50. But equal player skill + higher character skill = consistent advantage.

---

# 8. AI BEHAVIOR

## 8.1 AI Core Principle

Every weapon has a **win condition**—a range and situation where it dominates. The AI should try to create that situation.

| Weapon Type | Win Condition | Lose Condition |
|-------------|---------------|----------------|
| Quick Melee | Inside enemy reach | Mid-range where enemy can swing freely |
| Medium + Shield | Neutral range, trading safely | Stamina depleted, guard broken |
| Medium No Shield | Landing parries, quick punishes | Missing parries, eating chip damage |
| Heavy Melee | Max reach, enemy can't reach | Enemy inside reach, can't swing |
| Ranged | Far away, enemy can't close | Close range, weapon is useless |

## 8.2 AI by Weapon Class

### Quick Melee AI (Fists, Dagger, Whip)

**Goal:** Get inside, stay inside, never stop moving.

**Approach Phase:**
```
Sprint directly at target
IF target has ranged weapon:
    Zigzag while approaching
Do NOT attempt to block (cannot block)
```

**Combat Phase:**
```
IF distance > enemy_weapon_reach:
    Sprint toward enemy (close the gap fast)
    
IF distance <= enemy_weapon_reach AND distance > my_reach:
    DANGER ZONE - sprint through it quickly
    
IF distance <= my_reach:
    Attack repeatedly
    IF has_combo:
        Use full combo
    Circle while attacking (never stand still)
    IF enemy starts wind-up:
        Strafe sideways (dodge by movement)
    IF health < 30%:
        Disengage, sprint away, re-approach from different angle
```

**Dagger Special Behavior:**
```
Attempt to circle behind target
IF behind target (>135° from their facing):
    Always attack immediately (backstab bonus)
More likely to disengage and re-approach than fight head-on
```

**Whip Special Behavior:**
```
Maintain distance at max whip range (1.8 cells)
Kite backward while attacking
Never close to melee range voluntarily
```

### Medium Melee + Shield AI

**Goal:** Safe trades. Block, wait for opening, punish.

**Approach Phase:**
```
Walk toward target (don't sprint, conserve stamina)
IF target has ranged weapon:
    Raise shield while approaching
```

**Combat Phase:**
```
IF distance > my_reach:
    Walk toward enemy
    
IF distance <= my_reach:
    IF enemy is in recovery:
        Attack (guaranteed free hit)
    ELIF enemy is in wind-up:
        Block OR attempt parry (based on difficulty setting)
    ELIF enemy is blocking:
        Attack (drain their stamina)
    ELIF enemy is neutral:
        Wait 0.5-1.0s, then attack to force response
        
IF my_stamina < 30%:
    Back away from enemy
    Lower shield
    Let stamina regenerate
    
IF enemy_stamina appears low (blocked many hits):
    Press aggressively to force guard break
```

**Axe Special Behavior:**
```
Prioritize attacking enemy shield (shield breaker bonus)
More aggressive against shielded enemies
```

**Mace Special Behavior:**
```
Track estimated concuss buildup on target
After 3-4 hits, become very aggressive (concuss is imminent)
```

### Medium Melee No Shield AI

**Goal:** Land parries. Punish hard with speed advantage.

**Approach Phase:**
```
Walk toward target
Stay mobile, don't commit early
```

**Combat Phase:**
```
IF distance > my_reach:
    Walk toward enemy
    
IF distance <= my_reach:
    IF enemy is in recovery:
        Attack (free hit)
        IF recovery is long enough:
            Charge heavy attack instead
    ELIF enemy is in wind-up:
        Attempt parry (higher priority than shield users)
        IF parry succeeds AND has_combo:
            Execute full combo
        ELIF parry succeeds:
            Heavy attack
    ELIF enemy is blocking:
        Attack to drain stamina (but don't overcommit)
    ELIF enemy is neutral:
        Feint approach to bait their swing
        Then parry
        
IF missed parry (took damage):
    Back off, reassess
    
IF enemy is very aggressive:
    Let them exhaust themselves
    Parry their desperation swings
```

**Long Sword Special Behavior:**
```
After landing combo hit 1 or 2, evaluate:
    IF enemy is staggered/recovering:
        Continue combo (safe)
    IF enemy is blocking:
        Consider stopping (they may parry hit 3)
    IF enemy is neutral:
        Gamble based on aggression personality
```

### Heavy Melee AI (Spear, Warhammer, Halberd, Great Sword)

**Goal:** Keep them at max reach. They can't hit you, you can hit them.

**Approach Phase:**
```
Walk toward target until at weapon reach
Stop at max reach (do not get closer)
```

**Combat Phase:**
```
IF distance > my_reach:
    Walk toward enemy (close the gap)
    
IF distance == my_reach (optimal zone):
    Attack when enemy tries to approach
    IF enemy is in wind-up:
        Parry attempt OR trade (my weapon hits first due to reach)
    IF enemy is neutral:
        Poke to keep them out
        
IF distance < my_reach (they got inside):
    DANGER STATE
    Options by weapon:
        Halberd: Back away while attacking (retreat strike)
        Warhammer: Swing anyway (high damage + stagger wins trades)
        Others: Walk backward, try to recreate spacing
    
IF enemy is blocking at my max reach:
    Charge heavy attack (I have time, they can't reach me)
```

**Spear Special Behavior:**
```
Thrust attacks only (use narrow 30° cone)
Extremely focused on maintaining exact 2.0 cell distance
IF enemy gets inside reach:
    Enter panic state
    Attempt to back away immediately
```

**Warhammer Special Behavior:**
```
Does NOT panic when enemy gets close
Will trade hits confidently
Rationale: 55-70 damage + guaranteed stagger wins trades
Uses heavy attack more often (stagger covers long recovery)
```

**Halberd Special Behavior:**
```
Uses retreat strike when enemy closes
More mobile than other heavy weapons
Can play mid-range like medium weapon if spacing fails
```

**Great Sword Special Behavior:**
```
Wide swings (150° cone), doesn't need precise aim
Uses sweep attacks when multiple enemies nearby
Slower reactions but more forgiving on accuracy
```

### Ranged AI (Bow, Crossbow, Slingshot)

**Goal:** Never let them reach you.

**Approach Phase:**
```
Do NOT approach
Maintain maximum distance
IF target is far:
    Stand still and shoot
IF target is approaching:
    Back away while drawing
```

**Combat Phase:**
```
IF distance > my_max_range:
    Walk toward enemy until in range
    
IF distance > melee_range AND <= my_max_range:
    Draw and fire
    IF enemy approaching:
        Back away while drawing
    
IF distance <= melee_range:
    PANIC STATE
    Options:
        Switch to melee weapon (0.5s switch time)
        Fire desperation shot (minimum draw, weak)
        Sprint away to create distance
        IF slingshot: Quick-switch to shield (0.3s)
```

**Bow Special Behavior:**
```
Prefer full draw for maximum damage
IF enemy closing fast:
    Accept half-draw shots (less damage, faster)
Attempt to lead moving targets (predict movement)
```

**Crossbow Special Behavior:**
```
Fire immediately (no draw time)
After firing:
    MUST create distance during 2.5s reload
    Very vulnerable during reload
IF enemy is close after firing:
    Consider switching to melee instead of reloading
```

**Slingshot Special Behavior:**
```
Quick shots, low commitment
Can shoot while moving backward at full speed
More willing to fight at medium range than other ranged
```

## 8.3 AI Response to Enemy Weapon

AI should adapt behavior based on what the target is using:

| Target Has... | AI Should... |
|---------------|--------------|
| Quick Melee | Don't let them inside. Attack when they approach. Maintain reach advantage. |
| Shield | Drain stamina with attacks. Use shield-breaking weapon if available. Be patient. |
| Heavy Weapon | Get inside their reach. Stay close. They can't swing effectively at close range. |
| Ranged | Close distance aggressively. Zigzag while approaching. Shield up if available. |
| No Shield | Pressure with attacks. Force them to parry or take damage. Punish missed parries. |

## 8.4 AI State Machine

```
┌──────────────────────────────────────────────────────────────┐
│                         STATES                                │
├──────────────────────────────────────────────────────────────┤
│ IDLE      │ No target. Wandering or stationary.              │
│ APPROACH  │ Target acquired. Closing distance.               │
│ COMBAT    │ In weapon range. Actively fighting.              │
│ SURROUND  │ Group fight. Spreading to flank.                 │
│ RETREAT   │ Creating distance. Recovering stamina/health.    │
│ PANIC     │ Something went wrong. Desperate actions.         │
└──────────────────────────────────────────────────────────────┘

TRANSITIONS:

IDLE → APPROACH
    Trigger: Target acquired (player spotted)
    
APPROACH → COMBAT
    Trigger: Distance <= my weapon reach
    
APPROACH → SURROUND
    Trigger: Allies present AND engaging same target
    
COMBAT → RETREAT
    Trigger: Stamina < 20% OR health < 30% OR need to reload
    
COMBAT → PANIC
    Trigger: Guard broken OR enemy inside reach (heavy weapon) OR ambushed
    
RETREAT → COMBAT
    Trigger: Stamina > 60% AND health > 30%
    
RETREAT → IDLE
    Trigger: Distance > perception range (gave up chase)
    
PANIC → COMBAT
    Trigger: Regained spacing OR landed a hit OR recovered from stagger
    
Any State → IDLE
    Trigger: Target dead OR target escaped perception range
```

## 8.5 AI Difficulty Levels

| Behavior | Easy | Medium | Hard |
|----------|------|--------|------|
| Reaction Delay | 0.3s | 0.15s | 0s |
| Parry Attempt Rate | 10% | 40% | 80% |
| Parry Success Rate | 30% | 60% | 90% |
| Punishes Recovery | 50% | 80% | 100% |
| Maintains Optimal Spacing | Rarely | Sometimes | Always |
| Reads Player Patterns | No | No | Yes |
| Combos Optimally | Random | Usually | Always |
| Heavy Attack Timing | Random | After parry | Perfect openings only |
| Retreats When Low | Never | Sometimes | Always |

### Difficulty Descriptions

**Easy:**
- Slow to react (0.3s delay on all decisions)
- Rarely attempts parry, usually fails when trying
- Often misses opportunities to punish player mistakes
- Doesn't retreat even when dying
- Predictable timing

**Medium:**
- Moderate reaction time (0.15s delay)
- Attempts parry regularly, succeeds about half the time
- Usually punishes obvious openings
- Sometimes retreats when in danger
- Decent challenge for average players

**Hard:**
- No artificial reaction delay
- Parries most attacks successfully
- Always punishes player mistakes
- Retreats intelligently to recover
- Learns and adapts to player patterns

## 8.6 AI Personality Types

| Personality | Description | Behavior Modifiers |
|-------------|-------------|-------------------|
| **Aggressive** | Always pressing, rarely defends | +50% attack frequency, -50% block frequency, chases retreating targets, ignores optimal spacing |
| **Defensive** | Waits for opponent to commit | +100% block frequency, only counterattacks, never initiates, very patient |
| **Cowardly** | Avoids fair fights | Retreats at 50% health, prefers ranged, disengages frequently, avoids 1v1 |
| **Reckless** | No self-preservation | Never retreats, trades hits willingly, attacks even when hurt, ignores stamina |
| **Calculating** | Optimal play | Exploits every opening, adapts to patterns, perfect stamina management |
| **Berserker** | Gets dangerous when hurt | Normal until <50% health, then +attack speed, +aggression, -defense |

## 8.7 AI Example Profiles

### Profile 1: Town Guard (Medium, Defensive, Short Sword + Shield)
```
Weapon: Short Sword
Shield: Yes
Difficulty: Medium
Personality: Defensive

Behavior:
- Approaches with shield raised
- Waits for player to attack first
- Blocks most attacks, attempts parry 40% of time
- Only counterattacks after successful block/parry
- Backs away to recover stamina when low
- Won't chase if player flees
- Easy to bait but hard to pressure
```

### Profile 2: Bandit (Easy, Aggressive, Axe)
```
Weapon: Axe
Shield: No
Difficulty: Easy
Personality: Aggressive

Behavior:
- Charges directly at player
- Swings frequently, rarely blocks
- Doesn't retreat even when hurt
- Easy to parry (predictable timing)
- Dangerous if player makes mistakes (axe hits hard)
- Will chase player relentlessly
```

### Profile 3: Assassin (Hard, Calculating, Dagger)
```
Weapon: Dagger
Shield: No
Difficulty: Hard
Personality: Calculating

Behavior:
- Approaches carefully
- Circles to get behind player
- Waits for player to commit, then strikes
- Disengages and re-approaches rather than trading
- Exploits every recovery window
- If spotted, may flee and try again later
- Extremely dangerous if gets backstab
```

### Profile 4: Knight (Hard, Calculating, Long Sword + Shield)
```
Weapon: Long Sword
Shield: Yes
Difficulty: Hard
Personality: Calculating

Behavior:
- Perfect spacing and timing
- Parries almost everything
- Uses full 3-hit combo optimally
- Manages stamina perfectly
- Retreats when necessary, re-engages when ready
- Adapts to player patterns
- The "boss fight" tier enemy
```

### Profile 5: Berserker (Medium, Berserker, Great Sword)
```
Weapon: Great Sword
Shield: No (can't)
Difficulty: Medium
Personality: Berserker

Behavior:
- Fights normally at full health
- At 50% health: Attacks faster, more aggressive
- At 25% health: Constant attacks, no blocking, terrifying pressure
- Dangerous when cornered
- Will chase player forever
- High risk enemy - kill fast or get overwhelmed
```

### Profile 6: Archer (Medium, Cowardly, Bow)
```
Weapon: Bow
Shield: No
Difficulty: Medium
Personality: Cowardly

Behavior:
- Maintains maximum distance
- Retreats while firing
- Flees if player gets close
- Switches to knife as last resort
- Will call for help if available
- Easy to pressure, hard to catch
```

---

# 9. GROUP COMBAT

## 9.1 Core Philosophy

Group combat is **realistic and deadly**. There are no artificial balancing mechanisms like attack slots or turn-taking. If 4 people surround you, 4 people hit you.

### Realistic Outcomes
| Situation | Realistic Outcome |
|-----------|-------------------|
| 1v1 | Skill and equipment decide |
| 1v2 | Heavily disadvantaged. Winnable only with major skill/equipment gap or terrain. |
| 1v3 | You lose. Unless chokepoint. |
| 1v4+ | You die. Run or use terrain. |

## 9.2 How NPCs Fight Together

### Simultaneous Attacks
```
IF multiple NPCs are in range:
    They ALL attack
    No artificial waiting
    No turn-taking
    Player gets hit by all attacks they cannot block
```

### Natural Attack Stagger
Attacks don't perfectly sync because:
- NPCs have different distances to close
- NPCs have different reaction times
- NPCs have different weapon speeds
- This creates 0.1-0.3s natural gaps (realistic, not designed fairness)

### Positioning Priority
```
FOR each NPC in group:
    PRIORITY 1: Get behind the target (highest damage, unblockable)
    PRIORITY 2: Get to the side of the target (flanking bonus)
    PRIORITY 3: Attack from front if others have flanks covered
    
NPCs spread out to surround
NPCs do NOT bunch up in front
```

### Communication (Implicit)
NPCs don't talk but read each other:
```
IF ally is engaging target:
    Move to flank while target is distracted
    
IF target is facing me:
    Keep their attention (feint, attack)
    Let allies get behind them
    
IF target turns away from me:
    Attack immediately
```

## 9.3 Flanking Mechanics

### Flanking Damage Bonuses
| Attack Angle | Damage Modifier | Block Possible? |
|--------------|-----------------|-----------------|
| Front (0-45°) | 100% | Yes |
| Side (45-135°) | 125% | Difficult (must turn) |
| Behind (135-180°) | 150% | No |

### Flanking Detection
```
angle = angle_between(target.facing_direction, attack_direction)

IF angle < 45:
    front_attack (normal)
ELIF angle < 135:
    side_attack (+25% damage, hard to block)
ELSE:
    back_attack (+50% damage, cannot block)
```

### Surrounding Behavior
```
WHEN 3+ NPCs engage one target:
    NPC_A: Position at front
    NPC_B: Position at left flank
    NPC_C: Position at right flank
    NPC_D+: Position at rear
    
ONCE surrounded:
    Target cannot block all directions
    Target cannot escape easily
    Target takes damage from all angles
```

## 9.4 Group AI States

### Role Assignment
When multiple NPCs fight one target, they dynamically take roles:

| Role | Count | Behavior |
|------|-------|----------|
| **Attacker** | All in range | Actively swinging, pressing target |
| **Flanker** | Those not in range yet | Moving to flank position |
| **Blocker** | Optional | Cuts off escape routes |

### Group State Machine
```
STATES (Group):
    CONVERGE: All NPCs moving toward target
    SURROUND: NPCs spreading to flank positions
    ASSAULT: All NPCs in range attacking
    PURSUE: Target fleeing, NPCs chasing

TRANSITIONS:

CONVERGE → SURROUND
    Trigger: First NPC reaches melee range

SURROUND → ASSAULT
    Trigger: NPCs have achieved flanking positions

ASSAULT → PURSUE
    Trigger: Target breaks from encirclement and runs

PURSUE → SURROUND
    Trigger: Caught up to target
```

## 9.5 The Only Equalizers

### Terrain
The primary way to survive being outnumbered.

| Terrain | Effect |
|---------|--------|
| **Doorway** | Only 1 enemy can reach you at a time |
| **Narrow Hall** | Only 1-2 enemies can reach you |
| **Back to Wall** | Cannot be flanked from behind |
| **Corner** | Can only be attacked from 90° arc |
| **Stairs** | Higher ground advantage, enemies funnel |
| **Obstacles** | Breaks up formation, creates mini-chokepoints |

### Killing Fast
```
IF you can kill one enemy before others reach you:
    4v1 becomes 3v1
    Still bad, but better
    
Strategy:
    Ambush isolated enemies
    Kill before reinforcements arrive
    Then run or reposition
```

### Allies
```
2v3 is survivable
3v3 is fair
4v3 is advantaged

The player should recruit allies, hire mercenaries, make friends.
```

### Equipment Advantage
```
Full plate armor vs unarmored peasants:
    Their attacks do minimal damage
    You can survive long enough to fight back
    Still hard, but possible
    
This is the ONLY way skill + gear overcomes numbers significantly.
```

### Running Away
```
IF outnumbered in open ground:
    RUN
    This is the correct strategic choice
    Find terrain or allies
    Re-engage on YOUR terms
```

## 9.6 Player Tells (Fairness)

Even in realistic combat, players need information:

| Situation | Tell (Warning) |
|-----------|----------------|
| Attack from behind incoming | Audio cue (footstep, grunt, weapon sound) |
| NPC about to attack | Visible wind-up animation |
| Surrounded (3+ in 180° arc) | Screen edge indicator or character reaction |
| Flanker about to strike | Brief visual/audio cue |

Player should never be hit without ANY warning. Even 0.2 seconds is enough to feel fair.

## 9.7 Difficulty Scaling for Groups

| Difficulty | Flank Speed | Coordination | Pursuit |
|------------|-------------|--------------|---------|
| Easy | Slow to flank, bunch up | Poor, get in each other's way | Give up quickly |
| Medium | Attempt to surround | Basic coordination | Chase for a while |
| Hard | Immediately spread | Excellent coordination, cut off escapes | Relentless |

Note: Even Easy NPCs will kill you if you stand surrounded in the open. They're just slower to achieve the surround.

## 9.8 Example: Realistic 1v3 Fight

**Setup:** Player with Short Sword + Shield. 3 NPCs with Short Swords. Open ground.

**What Happens:**
```
Second 0:
    NPCs spot player
    All three begin approaching

Second 1:
    NPCs naturally spread (not coordinated, just smart)
    NPC_A: Approaches from front
    NPC_B: Moving to player's left
    NPC_C: Moving to player's right

Second 2:
    Player is facing NPC_A
    NPC_A: In range, swings
    Player: Blocks (costs stamina)
    NPC_B: Reaches left flank position
    NPC_C: Reaches right flank position

Second 3:
    Player still facing NPC_A
    NPC_A: Swings again
    Player: Blocks again
    NPC_B: In position, swings at player's exposed left side
    Player: CANNOT BLOCK (already blocking A)
    Player: Takes hit from B (+25% flank damage)

Second 4:
    Player turns to face B
    NPC_A: Now at player's right, swings
    Player: CANNOT BLOCK (facing B)
    Player: Takes hit from A
    NPC_C: Now behind player, swings
    Player: CANNOT BLOCK (can't see C)
    Player: Takes hit from C (+50% back damage)

Second 5:
    Player is taking hits from all directions
    Player dies shortly after

Total fight time: ~6 seconds
```

**Player Mistakes:**
- Engaged 3 enemies in open ground
- Didn't run when flanked
- No mistake in COMBAT technique—the mistake was BEING THERE

## 9.9 Example: Smart 1v3 Fight

**Setup:** Same. But there's a doorway nearby.

**What Happens:**
```
Second 0:
    NPCs spot player
    Player IMMEDIATELY runs to doorway

Second 1-2:
    Player reaches doorway
    Back against door frame
    Now: Only 1 NPC can reach player at a time
    NPCs stack up at doorway entrance

Second 3+:
    1v1 fight with NPC_A (others cannot reach)
    Player parries NPC_A, counterattacks
    Player kills NPC_A
    NPC_B steps up to doorway
    1v1 fight with NPC_B
    Player kills NPC_B
    NPC_C steps up
    Player kills NPC_C

Player wins through POSITIONING, not superior combat skill.
```

---

# 10. TERRAIN AND POSITIONING

## 10.1 Level Design Implications

The game world must provide opportunities for smart play:

| Location | Design Requirements |
|----------|---------------------|
| Bandit Camp | Narrow paths between tents, doorways, obstacles |
| Forest | Trees create natural chokepoints |
| Building Interior | Doorways, furniture, hallways |
| Town Streets | Alleys, carts, market stalls as cover |
| Open Field | **DEATH ZONE for outnumbered combat** |

## 10.2 Strategic Locations

### Chokepoints
Definition: Location where only 1-2 enemies can engage simultaneously.

Examples:
- Doorways
- Narrow bridges
- Gaps between rocks
- Hallways
- Staircases

Value: Transforms 1v5 into series of 1v1 fights.

### Defensible Positions
Definition: Location that limits angles of attack.

Examples:
- Corner (90° threat arc)
- Wall (180° threat arc)
- Elevated position (enemies must approach from below)

Value: Prevents flanking, reduces number of simultaneous attackers.

### Escape Routes
Definition: Path to retreat when combat turns bad.

Players should always know:
- Where can I run?
- Where is the nearest chokepoint?
- Where are enemies positioned relative to escape?

## 10.3 Player Guidance

### Before Combat
| Situation | Correct Action |
|-----------|----------------|
| See 3+ enemies ahead | Do not engage. Find chokepoint or leave. |
| See isolated enemy | Kill them before friends arrive. |
| Enemy group patrolling | Wait for one to separate. |
| Must pass enemy group | Find alternate route or create distraction. |

### During Combat
| Situation | Correct Action |
|-----------|----------------|
| Outnumbered in open | RUN. Find doorway, corner, anything. |
| At chokepoint | Hold position. Kill them one at a time. |
| One enemy down | Reposition if still outnumbered. |
| Taking hits from behind | You're surrounded. Sprint out or die. |

---

# 11. IMPLEMENTATION CONSTANTS

## 11.1 Timing Constants

```
// Attack phases (seconds)
FISTS_WINDUP = 0.08
FISTS_SWING = 0.08
FISTS_RECOVERY = 0.15

DAGGER_WINDUP = 0.10
DAGGER_SWING = 0.10
DAGGER_RECOVERY = 0.20

WHIP_WINDUP = 0.15
WHIP_SWING = 0.12
WHIP_RECOVERY = 0.25

SHORT_SWORD_WINDUP = 0.18
SHORT_SWORD_SWING = 0.18
SHORT_SWORD_RECOVERY = 0.35

LONG_SWORD_WINDUP = 0.20
LONG_SWORD_SWING = 0.20
LONG_SWORD_RECOVERY = 0.38

AXE_WINDUP = 0.22
AXE_SWING = 0.18
AXE_RECOVERY = 0.40

MACE_WINDUP = 0.20
MACE_SWING = 0.18
MACE_RECOVERY = 0.38

FLAIL_WINDUP = 0.25
FLAIL_SWING = 0.22
FLAIL_RECOVERY = 0.45

SPEAR_WINDUP = 0.35
SPEAR_SWING = 0.18
SPEAR_RECOVERY = 0.45

WARHAMMER_WINDUP = 0.45
WARHAMMER_SWING = 0.25
WARHAMMER_RECOVERY = 0.55

HALBERD_WINDUP = 0.40
HALBERD_SWING = 0.22
HALBERD_RECOVERY = 0.50

GREAT_SWORD_WINDUP = 0.42
GREAT_SWORD_SWING = 0.22
GREAT_SWORD_RECOVERY = 0.50

// Tool timings
PICKAXE_WINDUP = 0.35
PICKAXE_SWING = 0.20
PICKAXE_RECOVERY = 0.45

HOE_WINDUP = 0.32
HOE_SWING = 0.20
HOE_RECOVERY = 0.44

SHOVEL_WINDUP = 0.32
SHOVEL_SWING = 0.20
SHOVEL_RECOVERY = 0.44

SMITHING_HAMMER_WINDUP = 0.28
SMITHING_HAMMER_SWING = 0.18
SMITHING_HAMMER_RECOVERY = 0.46
```

## 11.2 Combat Constants

```
// Parry windows (seconds)
PARRY_WINDOW_SHIELD = 0.15
PARRY_WINDOW_MEDIUM_WEAPON = 0.10
PARRY_WINDOW_HEAVY_WEAPON = 0.08

// Parry stagger durations (seconds)
PARRY_STAGGER_SHIELD = 0.4
PARRY_STAGGER_WEAPON_ONLY = 0.6

// Block arcs (degrees)
BLOCK_ARC_SHIELD = 180
BLOCK_ARC_MEDIUM_WEAPON = 90
BLOCK_ARC_HEAVY_WEAPON = 60

// Block stamina costs
BLOCK_STAMINA_HOLD = 2  // per tick
BLOCK_STAMINA_HIT_SHIELD = 15
BLOCK_STAMINA_HIT_MEDIUM = 25
BLOCK_STAMINA_HIT_HEAVY = 30

// Guard break
GUARD_BREAK_STUN_DURATION = 0.8
GUARD_BREAK_DAMAGE_MULTIPLIER = 2.0

// Clash
CLASH_WINDOW = 0.1  // seconds
CLASH_PUSHBACK = 0.3  // cells
CLASH_RECOVERY = 0.3  // seconds
CLASH_STAMINA_COST = 10

// Hit stun
HIT_STUN_DURATION = 0.2

// Combo
COMBO_WINDOW = 0.4  // seconds to input next hit
COMBO_HIT_2_DAMAGE_BONUS = 0.10  // +10%
COMBO_HIT_3_DAMAGE_BONUS = 0.25  // +25% (Long Sword)
COMBO_HIT_3_DAMAGE_BONUS_GREAT = 0.30  // +30% (Great Sword)
COMBO_HIT_3_RECOVERY_PENALTY = 0.15  // +0.15s (Long Sword)
COMBO_HIT_3_RECOVERY_PENALTY_GREAT = 0.20  // +0.20s (Great Sword)
```

## 11.3 Stamina Constants

```
// Base values
STAMINA_BASE = 100
STAMINA_REGEN_RATE = 5  // per second
STAMINA_REGEN_DELAY = 0.8  // seconds after last use

// Sprint
SPRINT_STAMINA_COST = 2  // per tick (10/second)
```

## 11.4 Status Effect Constants

```
// Bleed
BLEED_DAMAGE_PER_STACK = 2  // per second
BLEED_MAX_STACKS = unlimited
BLEED_DECAY = none  // never stops without bandage

// Stagger
STAGGER_LIGHT = 0.15
STAGGER_MEDIUM = 0.25
STAGGER_HEAVY = 3.0  // daze state
STAGGER_HEAVY_MOVE_SPEED = 0.5
STAGGER_HEAVY_CAN_SPRINT = false
STAGGER_HEAVY_CAN_PARRY = false

// Concuss
CONCUSS_THRESHOLD = 100
CONCUSS_DECAY_TIME = 10  // seconds until meter resets
CONCUSS_KNOCKOUT_DURATION = 2  // in-game hours

// Concuss buildup and instant KO chance by weapon
CONCUSS_FISTS_BUILDUP = 10
CONCUSS_FISTS_INSTANT_KO = 0.01
CONCUSS_SHOVEL_BUILDUP = 20
CONCUSS_SHOVEL_INSTANT_KO = 0.03
CONCUSS_SMITHING_HAMMER_BUILDUP = 15
CONCUSS_SMITHING_HAMMER_INSTANT_KO = 0.02
CONCUSS_MACE_BUILDUP = 25
CONCUSS_MACE_INSTANT_KO = 0.05
CONCUSS_FLAIL_BUILDUP = 15
CONCUSS_FLAIL_INSTANT_KO = 0.02
CONCUSS_WARHAMMER_BUILDUP = 40
CONCUSS_WARHAMMER_INSTANT_KO = 0.10
CONCUSS_SLINGSHOT_BUILDUP = 10
CONCUSS_SLINGSHOT_INSTANT_KO = 0.01
CONCUSS_ROCKS_BUILDUP = 20
CONCUSS_ROCKS_INSTANT_KO = 0.03
CONCUSS_EXPLOSIVES_BUILDUP = 15
CONCUSS_EXPLOSIVES_INSTANT_KO = 0.02
```

## 11.5 Movement Constants

```
// Base movement speed = 1.0

// Shield penalty
SHIELD_MOVEMENT_SPEED = 0.9

// No shield bonus
NO_SHIELD_ATTACK_SPEED = 0.9  // 10% faster (multiply timing by this)

// Movement during attack by class
QUICK_MELEE_ATTACK_MOVEMENT = 1.0
TOOL_ATTACK_MOVEMENT = 0.25
MEDIUM_MELEE_ATTACK_MOVEMENT = 0.5
HEAVY_MELEE_ATTACK_MOVEMENT = 0.0

// Movement while blocking
BLOCK_MOVEMENT_SHIELD = 0.5
BLOCK_MOVEMENT_MEDIUM_WEAPON = 0.25
BLOCK_MOVEMENT_HEAVY_WEAPON = 0.0

// Movement while charging heavy
HEAVY_CHARGE_MOVEMENT_MEDIUM = 0.25
HEAVY_CHARGE_MOVEMENT_HEAVY = 0.0
```

## 11.6 Weapon Reach Constants

```
// Reach in cells
REACH_FISTS = 0.6
REACH_DAGGER = 0.8
REACH_WHIP = 1.8
REACH_SMITHING_HAMMER = 0.8
REACH_MACE = 0.9
REACH_SHORT_SWORD = 1.0
REACH_PICKAXE = 1.0
REACH_SHOVEL = 1.1
REACH_AXE = 1.1
REACH_HOE = 1.2
REACH_LONG_SWORD = 1.2
REACH_FLAIL = 1.3
REACH_GREAT_SWORD = 1.5
REACH_WARHAMMER = 1.2
REACH_HALBERD = 1.8
REACH_SPEAR = 2.0
REACH_SPEAR_THRUST = 2.3  // with thrust bonus

// Attack cones (degrees)
ATTACK_CONE_DEFAULT = 90
ATTACK_CONE_SPEAR = 30
ATTACK_CONE_GREAT_SWORD = 150
```

## 11.7 Skill Scaling Constants

```
// Strength
STRENGTH_DAMAGE_BONUS_MAX = 0.5  // +50% at 100

// Agility
AGILITY_RECOVERY_REDUCTION_MAX = 0.3  // -30% at 100

// Weapon skill
WEAPON_SKILL_PARRY_BONUS_MAX = 1.0  // +100% window at 100

// Endurance
ENDURANCE_STAMINA_BONUS_MAX = 50  // +50 at 100
ENDURANCE_BLOCK_COST_REDUCTION_MAX = 0.25  // -25% at 100
```

## 11.8 AI Constants

```
// Reaction delays (seconds)
AI_REACTION_EASY = 0.3
AI_REACTION_MEDIUM = 0.15
AI_REACTION_HARD = 0.0

// Parry attempt rates
AI_PARRY_RATE_EASY = 0.1
AI_PARRY_RATE_MEDIUM = 0.4
AI_PARRY_RATE_HARD = 0.8

// Parry success rates (when attempted)
AI_PARRY_SUCCESS_EASY = 0.3
AI_PARRY_SUCCESS_MEDIUM = 0.6
AI_PARRY_SUCCESS_HARD = 0.9

// Retreat thresholds
AI_RETREAT_STAMINA_THRESHOLD = 0.2
AI_RETREAT_HEALTH_THRESHOLD = 0.3

// Pursuit
AI_PURSUIT_GIVE_UP_DISTANCE = 20  // cells
```

## 11.9 Flanking Constants

```
// Angle thresholds (degrees from target facing)
FLANK_FRONT_THRESHOLD = 45
FLANK_SIDE_THRESHOLD = 135
// > 135 is back

// Damage multipliers
FLANK_SIDE_DAMAGE = 1.25
FLANK_BACK_DAMAGE = 1.50

// Dagger backstab
DAGGER_BACKSTAB_MULTIPLIER = 2.0
```

## 11.10 Ranged Constants

```
// Bow
BOW_DRAW_MIN = 0.3
BOW_DRAW_MAX = 1.5
BOW_RANGE_MIN = 6
BOW_RANGE_MAX = 15
BOW_DAMAGE_MIN = 12
BOW_DAMAGE_MAX = 40
BOW_ACCURACY_MIN = 20  // degrees
BOW_ACCURACY_MAX = 2
BOW_RECOVERY = 0.3
BOW_MOVEMENT_DRAWING = 0.5
BOW_MOVEMENT_AIMING = 0.25

// Crossbow
CROSSBOW_RANGE = 18
CROSSBOW_DAMAGE_MIN = 45
CROSSBOW_DAMAGE_MAX = 55
CROSSBOW_ACCURACY = 3
CROSSBOW_RELOAD_TIME = 2.5
CROSSBOW_RECOVERY = 0.4
CROSSBOW_MOVEMENT_AIMING = 0.5
CROSSBOW_MOVEMENT_RELOADING = 0.25

// Slingshot
SLINGSHOT_DRAW_MIN = 0.2
SLINGSHOT_DRAW_MAX = 0.5
SLINGSHOT_RANGE_MIN = 4
SLINGSHOT_RANGE_MAX = 8
SLINGSHOT_DAMAGE_MIN = 5
SLINGSHOT_DAMAGE_MAX = 15
SLINGSHOT_ACCURACY_MIN = 15
SLINGSHOT_ACCURACY_MAX = 5
SLINGSHOT_RECOVERY = 0.2
SLINGSHOT_MOVEMENT = 1.0
SLINGSHOT_SHIELD_SWITCH = 0.3
```

---

# END OF DOCUMENT

This document contains all information required to implement the combat system. All values are tunable—playtest and adjust as needed.

Key reminders:
1. No dodge roll. Defense is blocking, parrying, or positioning.
2. Group combat is deadly. Terrain is survival.
3. Player and NPC use identical rules.
4. Skills improve numbers, not mechanics.
5. Weapon choice defines playstyle fundamentally.

---

*Document Version: 1.0*
*For implementation reference*
