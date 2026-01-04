# Village Simulation - Cross-Platform Game

A medieval village simulation game with cross-platform support and gamepad controls.

## Features

- **Cross-platform**: Windows, Mac, Linux, Android (Retroid/Anbernic)
- **Controller support**: Xbox, PlayStation, Switch Pro, generic gamepads
- **Rust-ready**: Designed for easy migration to raylib-rs
- **Sprite layering**: Efficient texture-based rendering

## Quick Start

```bash
pip install raylib
python main.py
```

## Controls

### Keyboard/Mouse
| Action | Key |
|--------|-----|
| Move | WASD |
| Sprint | Shift (hold) |
| Attack | Left Click |
| Eat | E |
| Trade | T |
| Bake | B |
| Make Camp | C |
| Recenter Camera | R |
| Pan Camera | Arrow Keys |
| Zoom In/Out | +/- or Mouse Wheel |
| Pause | Escape |

### Gamepad/Controller
| Action | Button |
|--------|--------|
| Move | Left Stick |
| Sprint | Right Bumper (hold) |
| Attack | A / Cross |
| Eat | Y / Triangle |
| Trade | X / Square |
| Bake | Left Bumper |
| Make Camp | B / Circle |
| Recenter Camera | Select/Back |
| Pan Camera | Right Stick |
| Zoom In | Right Trigger |
| Zoom Out | Left Trigger |
| Pause | Start |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       main.py                                │
│                  (Entry Point)                               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │    gui.py     │
              │   (Raylib)    │
              └───────┬───────┘
                      │
                      ▼
        ┌───────────────────────┐
        │   player_controller   │
        │   (Input → Actions)   │
        └───────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │     game_logic.py     │
        │   (Rules & Systems)   │
        └───────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │     game_state.py     │
        │    (Data Container)   │
        └───────────────────────┘
```

## Building for Different Platforms

### Windows/Mac/Linux
```bash
pip install raylib
python main.py
```

### Android (Retroid/Anbernic)

1. Install buildozer:
```bash
pip install buildozer
```

2. Initialize buildozer:
```bash
buildozer init
```

3. Edit `buildozer.spec`:
```ini
[app]
title = Village Simulation
package.name = villagesim
package.domain = com.yourname

requirements = python3,raylib

# For gamepad support
android.permissions = VIBRATE
```

4. Build APK:
```bash
buildozer android debug
```

5. Install on device:
```bash
adb install bin/*.apk
```

## Future: Rust Migration

The game is designed for migration to Rust with raylib-rs:

```rust
// Python (current)
rl.draw_texture_pro(texture, source, dest, origin, rotation, tint)

// Rust (identical API)
draw_texture_pro(texture, source, dest, origin, rotation, tint)
```

Benefits:
- 10-100x performance improvement
- Native Android/iOS builds
- Single binary distribution
- Memory safety

## Performance Notes

For 580x850 cells with many NPCs:

1. **Culling**: Only render visible cells (implemented)
2. **Texture Atlases**: Combine sprites into sheets (implemented)
3. **Spatial Partitioning**: For collision checks (todo)
4. **ECS Architecture**: Consider for Rust version (planned)

## File Structure

```
├── main.py              # Entry point
├── gui.py               # Raylib renderer
├── sprites.py           # Sprite manager
├── game_state.py        # Data container
├── game_logic.py        # Game rules
├── player_controller.py # Input handling
├── character.py         # Character class
├── jobs.py              # NPC behaviors
├── constants.py         # Configuration
├── scenario_world.py    # World definition
├── scenario_characters.py # Character templates
├── static_interactables.py # World objects
├── town_gen.py          # Procedural generation
└── sprites/             # Sprite assets
    ├── U_Walk.png
    ├── U_Attack.png
    ├── U_Death.png
    ├── S_Walk.png
    ├── ...
    ├── Tree.png
    ├── Road.png
    └── ...
```

## Credits

- Raylib: https://www.raylib.com/
- raylib-py: https://github.com/electronstudio/raylib-python-cffi
