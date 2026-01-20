#!/usr/bin/env python3
"""
Tkinter Piano App
- One octave C to C plus D, E, F
- Keyboard controlled with polyphonic playback
- Toggleable labels (keyboard keys / note names)
"""

import tkinter as tk
import numpy as np

try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
    pygame.mixer.set_num_channels(32)  # Allow many simultaneous sounds
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Pygame not found. Install with: pip install pygame")
    print("Running in visual-only mode (no sound)")


class SoundGenerator:
    """Generate and cache piano sounds"""
    
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.sounds = {}  # Cache generated sounds
        
    def generate_tone(self, frequency, duration=1.0):
        """Generate a piano-like tone"""
        if frequency in self.sounds:
            return self.sounds[frequency]
            
        t = np.linspace(0, duration, int(self.sample_rate * duration), False)
        
        # Generate a richer tone with harmonics
        tone = np.zeros_like(t)
        
        # Fundamental and harmonics with decreasing amplitude
        harmonics = [1.0, 0.5, 0.25, 0.15, 0.1]
        for i, amp in enumerate(harmonics):
            harmonic_freq = frequency * (i + 1)
            if harmonic_freq < self.sample_rate / 2:  # Nyquist limit
                tone += amp * np.sin(2 * np.pi * harmonic_freq * t)
        
        # Apply ADSR envelope for more natural sound
        attack = int(0.01 * self.sample_rate)
        decay = int(0.1 * self.sample_rate)
        sustain_level = 0.7
        release = int(0.3 * self.sample_rate)
        
        envelope = np.ones_like(t)
        # Attack
        envelope[:attack] = np.linspace(0, 1, attack)
        # Decay
        envelope[attack:attack+decay] = np.linspace(1, sustain_level, decay)
        # Sustain
        envelope[attack+decay:-release] = sustain_level
        # Release
        envelope[-release:] = np.linspace(sustain_level, 0, release)
        
        tone = tone * envelope
        
        # Normalize and convert to 16-bit
        tone = tone / np.max(np.abs(tone))
        tone = (tone * 32767 * 0.5).astype(np.int16)
        
        # Create pygame sound
        if AUDIO_AVAILABLE:
            sound = pygame.mixer.Sound(buffer=tone.tobytes())
            self.sounds[frequency] = sound
            return sound
        return None


class PianoKey:
    """Represents a single piano key"""
    
    def __init__(self, note_name, frequency, keyboard_key, is_black=False):
        self.note_name = note_name
        self.frequency = frequency
        self.keyboard_key = keyboard_key
        self.is_black = is_black
        self.is_pressed = False
        self.canvas_id = None
        self.text_id = None
        self.channel = None  # Pygame channel for this note
        

class PianoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Piano - C to F (Extended)")
        self.root.configure(bg='#2b2b2b')
        
        # Label mode: 'keyboard' or 'notes'
        self.label_mode = tk.StringVar(value='keyboard')
        
        # Sound generator
        self.sound_gen = SoundGenerator()
        
        # Define keys with frequencies (A4 = 440Hz, calculate others)
        # Starting from C4 (middle C)
        self.keys = self._create_keys()
        
        # Pre-generate all sounds
        self._pregenerate_sounds()
        
        # Track pressed keys
        self.pressed_keys = set()
        
        # Track active channels for each key
        self.active_channels = {}
        
        # Setup UI
        self._setup_ui()
        
        # Bind keyboard events
        self._bind_keys()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _create_keys(self):
        """Create all piano keys with their properties"""
        # Frequencies for notes (starting from C4 = 261.63 Hz)
        # Using equal temperament: f = 440 * 2^((n-49)/12) where n is key number (A4 = 49)
        
        def freq(semitones_from_c4):
            # C4 is 261.63 Hz (key 40 on piano, A4=440 is key 49)
            return 261.63 * (2 ** (semitones_from_c4 / 12))
        
        keys = []
        
        # White keys: C D E F G A B C D E F
        # Keyboard:   A S D F G H J K L ; '
        white_notes = [
            ('C4', 0, 'a'),
            ('D4', 2, 's'),
            ('E4', 4, 'd'),
            ('F4', 5, 'f'),
            ('G4', 7, 'g'),
            ('A4', 9, 'h'),
            ('B4', 11, 'j'),
            ('C5', 12, 'k'),
            ('D5', 14, 'l'),
            ('E5', 16, 'semicolon'),
            ('F5', 17, 'quoteright'),
        ]
        
        # Black keys: C# D# F# G# A# C# D#
        # Keyboard:   W  E  T  Y  U  O  P
        black_notes = [
            ('C#4', 1, 'w'),
            ('D#4', 3, 'e'),
            ('F#4', 6, 't'),
            ('G#4', 8, 'y'),
            ('A#4', 10, 'u'),
            ('C#5', 13, 'o'),
            ('D#5', 15, 'p'),
        ]
        
        for note_name, semitones, kb_key in white_notes:
            keys.append(PianoKey(note_name, freq(semitones), kb_key, is_black=False))
            
        for note_name, semitones, kb_key in black_notes:
            keys.append(PianoKey(note_name, freq(semitones), kb_key, is_black=True))
            
        return keys
    
    def _pregenerate_sounds(self):
        """Pre-generate all piano sounds for instant playback"""
        print("Generating piano sounds...")
        for key in self.keys:
            self.sound_gen.generate_tone(key.frequency)
        print("Ready to play!")
    
    def _setup_ui(self):
        """Setup the user interface"""
        # Control frame
        control_frame = tk.Frame(self.root, bg='#2b2b2b')
        control_frame.pack(pady=10)
        
        tk.Label(control_frame, text="Label Mode:", bg='#2b2b2b', fg='white',
                font=('Arial', 12)).pack(side=tk.LEFT, padx=5)
        
        tk.Radiobutton(control_frame, text="Keyboard Keys", variable=self.label_mode,
                      value='keyboard', command=self._update_labels,
                      bg='#2b2b2b', fg='white', selectcolor='#404040',
                      activebackground='#2b2b2b', activeforeground='white',
                      font=('Arial', 11)).pack(side=tk.LEFT, padx=5)
        
        tk.Radiobutton(control_frame, text="Note Names", variable=self.label_mode,
                      value='notes', command=self._update_labels,
                      bg='#2b2b2b', fg='white', selectcolor='#404040',
                      activebackground='#2b2b2b', activeforeground='white',
                      font=('Arial', 11)).pack(side=tk.LEFT, padx=5)
        
        # Piano canvas
        self.canvas_width = 770
        self.canvas_height = 250
        self.canvas = tk.Canvas(self.root, width=self.canvas_width, 
                               height=self.canvas_height, bg='#1a1a1a',
                               highlightthickness=2, highlightbackground='#444')
        self.canvas.pack(pady=20, padx=20)
        
        # Draw piano keys
        self._draw_piano()
        
        # Instructions
        if AUDIO_AVAILABLE:
            status = "🔊 Audio enabled"
        else:
            status = "🔇 No audio - install pygame: pip install pygame"
            
        instructions = f"""
        {status}
        
        Play with keyboard: A S D F G H J K (white keys C-C) | L ; ' (D E F)
        Black keys: W E (C# D#) | T Y U (F# G# A#) | O P (C# D#)
        Multiple keys can be played simultaneously!
        """
        tk.Label(self.root, text=instructions, bg='#2b2b2b', fg='#aaaaaa',
                font=('Arial', 10), justify=tk.CENTER).pack(pady=10)
        
    def _draw_piano(self):
        """Draw the piano keys on canvas"""
        white_key_width = 70
        white_key_height = 220
        black_key_width = 40
        black_key_height = 140
        
        # Get white and black keys
        white_keys = [k for k in self.keys if not k.is_black]
        black_keys = [k for k in self.keys if k.is_black]
        
        # Draw white keys first
        for i, key in enumerate(white_keys):
            x1 = i * white_key_width
            y1 = 0
            x2 = x1 + white_key_width - 2
            y2 = white_key_height
            
            key.canvas_id = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill='#f5f5f5', outline='#333', width=2
            )
            
            # Add label
            label = self._get_label_text(key)
            key.text_id = self.canvas.create_text(
                x1 + white_key_width // 2, y2 - 30,
                text=label, font=('Arial', 12, 'bold'), fill='#333'
            )
            
            # Bind mouse events
            self.canvas.tag_bind(key.canvas_id, '<Button-1>', 
                               lambda e, k=key: self._mouse_press(k))
            self.canvas.tag_bind(key.canvas_id, '<ButtonRelease-1>', 
                               lambda e, k=key: self._mouse_release(k))
        
        # Black key positions (relative to white keys)
        # After white key index: 0(C), 1(D), 3(F), 4(G), 5(A), 7(C5), 8(D5)
        black_positions = [0, 1, 3, 4, 5, 7, 8]
        
        # Draw black keys on top
        for i, key in enumerate(black_keys):
            white_idx = black_positions[i]
            x1 = (white_idx + 1) * white_key_width - black_key_width // 2 - 1
            y1 = 0
            x2 = x1 + black_key_width
            y2 = black_key_height
            
            key.canvas_id = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill='#1a1a1a', outline='#000', width=2
            )
            
            # Add label
            label = self._get_label_text(key)
            key.text_id = self.canvas.create_text(
                x1 + black_key_width // 2, y2 - 20,
                text=label, font=('Arial', 10, 'bold'), fill='#ddd'
            )
            
            # Bind mouse events
            self.canvas.tag_bind(key.canvas_id, '<Button-1>', 
                               lambda e, k=key: self._mouse_press(k))
            self.canvas.tag_bind(key.canvas_id, '<ButtonRelease-1>', 
                               lambda e, k=key: self._mouse_release(k))
    
    def _get_label_text(self, key):
        """Get the label text based on current mode"""
        if self.label_mode.get() == 'keyboard':
            # Convert key names for display
            display_map = {
                'semicolon': ';',
                'quoteright': "'",
            }
            return display_map.get(key.keyboard_key, key.keyboard_key.upper())
        else:
            return key.note_name
    
    def _update_labels(self):
        """Update all key labels when mode changes"""
        for key in self.keys:
            if key.text_id:
                label = self._get_label_text(key)
                self.canvas.itemconfig(key.text_id, text=label)
    
    def _bind_keys(self):
        """Bind keyboard events"""
        self.root.bind('<KeyPress>', self._key_press)
        self.root.bind('<KeyRelease>', self._key_release)
        self.root.focus_set()
        
    def _normalize_key(self, event):
        """Normalize key event to our key names"""
        key = event.keysym.lower()
        # Handle special keys
        if key == 'semicolon':
            return 'semicolon'
        elif key == 'apostrophe' or key == "'" or event.char == "'":
            return 'quoteright'
        return key
    
    def _key_press(self, event):
        """Handle keyboard key press"""
        key_name = self._normalize_key(event)
        
        # Prevent key repeat
        if key_name in self.pressed_keys:
            return
            
        self.pressed_keys.add(key_name)
        
        # Find and activate the piano key
        for key in self.keys:
            if key.keyboard_key == key_name:
                self._activate_key(key)
                break
    
    def _key_release(self, event):
        """Handle keyboard key release"""
        key_name = self._normalize_key(event)
        
        self.pressed_keys.discard(key_name)
        
        # Find and deactivate the piano key
        for key in self.keys:
            if key.keyboard_key == key_name:
                self._deactivate_key(key)
                break
    
    def _mouse_press(self, key):
        """Handle mouse press on key"""
        self._activate_key(key)
        
    def _mouse_release(self, key):
        """Handle mouse release on key"""
        self._deactivate_key(key)
    
    def _activate_key(self, key):
        """Activate a piano key (visual + sound)"""
        if key.is_pressed:
            return
            
        key.is_pressed = True
        
        # Visual feedback
        if key.is_black:
            self.canvas.itemconfig(key.canvas_id, fill='#444')
        else:
            self.canvas.itemconfig(key.canvas_id, fill='#c0e0ff')
        
        # Play sound
        if AUDIO_AVAILABLE:
            sound = self.sound_gen.sounds.get(key.frequency)
            if sound:
                # Find a free channel and play
                channel = pygame.mixer.find_channel(True)
                if channel:
                    channel.play(sound, loops=-1)  # Loop until released
                    self.active_channels[key.frequency] = channel
    
    def _deactivate_key(self, key):
        """Deactivate a piano key"""
        if not key.is_pressed:
            return
            
        key.is_pressed = False
        
        # Reset visual
        if key.is_black:
            self.canvas.itemconfig(key.canvas_id, fill='#1a1a1a')
        else:
            self.canvas.itemconfig(key.canvas_id, fill='#f5f5f5')
        
        # Stop sound with fadeout
        if AUDIO_AVAILABLE and key.frequency in self.active_channels:
            channel = self.active_channels[key.frequency]
            channel.fadeout(150)  # 150ms fadeout for smooth release
            del self.active_channels[key.frequency]
    
    def _on_close(self):
        """Clean up on window close"""
        if AUDIO_AVAILABLE:
            pygame.mixer.quit()
        self.root.destroy()


def main():
    root = tk.Tk()
    root.resizable(False, False)
    app = PianoApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()