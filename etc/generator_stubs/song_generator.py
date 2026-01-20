#!/usr/bin/env python3
"""
Guitar Song Generator GUI - Seamless Looping Edition
Generates and plays guitar songs that loop perfectly.
"""

import random
import io
import tkinter as tk
from tkinter import ttk

from midiutil import MIDIFile
import pygame

# Guitar range: E2 (40) to E5 (76)
GUITAR_LOW = 40
GUITAR_HIGH = 76

MODES = {
    'Ionian (Major)': [0, 2, 4, 5, 7, 9, 11],
    'Dorian':         [0, 2, 3, 5, 7, 9, 10],
    'Phrygian':       [0, 1, 3, 5, 7, 8, 10],
    'Lydian':         [0, 2, 4, 6, 7, 9, 11],
    'Mixolydian':     [0, 2, 4, 5, 7, 9, 10],
    'Aeolian (Minor)':[0, 2, 3, 5, 7, 8, 10],
    'Locrian':        [0, 1, 3, 5, 6, 8, 10],
}

CHORD_TYPES = {
    'major':  [0, 4, 7],
    'minor':  [0, 3, 7],
    'dim':    [0, 3, 6],
    'maj7':   [0, 4, 7, 11],
    'min7':   [0, 3, 7, 10],
    'dom7':   [0, 4, 7, 10],
    'sus2':   [0, 2, 7],
    'sus4':   [0, 5, 7],
    'add9':   [0, 4, 7, 14],
}

# Looping progressions - designed to cycle back to the I chord naturally
# Each ends on V or a chord that resolves to I
PROGRESSIONS = {
    'Pop':       [0, 3, 4, 4],      # I - IV - V - V  -> resolves to I
    'Folk':      [0, 4, 3, 4],      # I - V - IV - V  -> resolves to I
    'Sad':       [0, 3, 4, 4],      # i - iv - v - v  -> resolves to i
    'Epic':      [0, 5, 3, 4],      # I - vi - IV - V -> resolves to I
    'Rock':      [0, 6, 3, 4],      # I - bVII - IV - V -> resolves to I
    'Dreamy':    [0, 4, 5, 4],      # I - V - vi - V  -> resolves to I
    'Moody':     [5, 3, 0, 4],      # vi - IV - I - V -> resolves to I
}

STRUM_PATTERNS = [
    [1, 1, 1, 1],
    [0.5, 0.5, 1, 0.5, 0.5, 1],
    [1.5, 0.5, 1, 1],
    [0.5, 0.5, 0.5, 0.5, 1, 1],
    [2, 2],
    [1, 0.5, 0.5, 1, 1],
]

ARPEGGIO_PATTERNS = [
    [0, 2, 1, 2],
    [0, 1, 2, 1],
    [0, 1, 2, 3, 2, 1],
    [0, 2, 1, 3, 2, 0],
    [0, 1, 2, 0, 1, 2],
]

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


class GuitarSongGenerator:
    """Generates guitar songs as in-memory MIDI data with seamless looping."""
    
    def __init__(self, bpm=100):
        self.bpm = bpm
        self.midi = MIDIFile(1)
        self.track = 0
        self.channel = 0
        self.midi.addTrackName(self.track, 0, "Guitar")
        self.midi.addTempo(self.track, 0, bpm)
        self.midi.addProgramChange(self.track, self.channel, 0, random.choice([25, 26]))
        
        self.root = random.randint(40, 52)
        self.mode_name = random.choice(list(MODES.keys()))
        self.mode = MODES[self.mode_name]
        self.progression_name = random.choice(list(PROGRESSIONS.keys()))
        self.progression = PROGRESSIONS[self.progression_name]
        self.current_time = 0.0
        
        # Store style choices for consistency across loops
        self.verse_style_seed = random.randint(0, 1000)
        self.chorus_style_seed = random.randint(0, 1000)
        
    def get_scale_note(self, degree, octave_offset=0):
        octave = degree // 7
        scale_degree = degree % 7
        note = self.root + self.mode[scale_degree] + (octave + octave_offset) * 12
        return max(GUITAR_LOW, min(GUITAR_HIGH, note))
    
    def get_chord_notes(self, scale_degree, chord_type='auto', bass_note=True):
        if chord_type == 'auto':
            chord_qualities = self._get_diatonic_chord_type(scale_degree)
            chord_type = random.choice(chord_qualities)
        
        root = self.get_scale_note(scale_degree, octave_offset=1)
        intervals = CHORD_TYPES[chord_type]
        notes = [root + interval for interval in intervals]
        
        if bass_note and random.random() > 0.3:
            bass = self.get_scale_note(scale_degree, octave_offset=0)
            notes.insert(0, bass)
        
        return [n for n in notes if GUITAR_LOW <= n <= GUITAR_HIGH]
    
    def _get_diatonic_chord_type(self, degree):
        if self.mode_name in ['Ionian (Major)', 'Lydian', 'Mixolydian']:
            if degree in [0, 3, 4]:
                return ['major', 'maj7', 'add9', 'sus2']
            elif degree in [1, 2, 5]:
                return ['minor', 'min7']
            else:
                return ['dim', 'minor']
        else:
            if degree in [0, 3, 4]:
                return ['minor', 'min7', 'sus4']
            elif degree in [2, 5, 6]:
                return ['major', 'maj7']
            else:
                return ['dim', 'minor']
    
    def add_strummed_chord(self, scale_degree, duration, velocity=80):
        notes = self.get_chord_notes(scale_degree)
        strum_delay = random.uniform(0.02, 0.05)
        
        for i, note in enumerate(notes):
            note_time = self.current_time + (i * strum_delay)
            note_vel = velocity + random.randint(-5, 5)
            # Slightly shorter to avoid overlap on loop
            note_dur = min(duration - (i * strum_delay), duration * 0.9)
            self.midi.addNote(self.track, self.channel, note, note_time, note_dur, note_vel)
    
    def add_arpeggiated_chord(self, scale_degree, total_duration, velocity=70):
        notes = self.get_chord_notes(scale_degree, bass_note=True)
        if len(notes) < 3:
            notes = notes + notes
        
        pattern = random.choice(ARPEGGIO_PATTERNS)
        note_duration = total_duration / len(pattern)
        
        for i, idx in enumerate(pattern):
            note_idx = idx % len(notes)
            note = notes[note_idx]
            note_time = self.current_time + (i * note_duration)
            note_vel = velocity + random.randint(-10, 10)
            # Keep notes from bleeding into loop point
            actual_dur = min(note_duration * 1.3, total_duration - (i * note_duration))
            self.midi.addNote(self.track, self.channel, note, note_time, actual_dur, note_vel)
    
    def add_melody_phrase(self, scale_degree, duration, velocity=75):
        chord_notes = self.get_chord_notes(scale_degree, bass_note=False)
        num_notes = random.randint(4, 8)
        note_duration = duration / num_notes
        current_note_idx = random.randint(0, 6)
        
        for i in range(num_notes):
            if random.random() > 0.3:
                note = random.choice(chord_notes)
            else:
                note = self.get_scale_note(current_note_idx, octave_offset=1)
            
            note_time = self.current_time + (i * note_duration)
            note_vel = velocity + random.randint(-8, 8)
            actual_duration = note_duration * random.uniform(0.7, 0.95)
            self.midi.addNote(self.track, self.channel, note, note_time, 
                            actual_duration, note_vel)
            
            current_note_idx += random.choice([-2, -1, 1, 2])
            current_note_idx = max(0, min(13, current_note_idx))
    
    def add_power_chord(self, scale_degree, duration, velocity=90):
        root = self.get_scale_note(scale_degree, octave_offset=0)
        fifth = root + 7
        octave = root + 12
        
        notes = [root, fifth]
        if octave <= GUITAR_HIGH:
            notes.append(octave)
        
        for note in notes:
            note_vel = velocity + random.randint(-5, 5)
            self.midi.addNote(self.track, self.channel, note, self.current_time, 
                            duration * 0.85, note_vel)
    
    def add_turnaround(self, duration, velocity=70):
        """Add a turnaround phrase that leads back to the I chord."""
        # Play the V chord in a way that creates tension -> resolution
        v_chord = self.get_chord_notes(4, bass_note=True)
        
        # Quick ascending arpeggio on V to build anticipation
        note_dur = duration / len(v_chord)
        for i, note in enumerate(v_chord):
            note_time = self.current_time + (i * note_dur)
            # Crescendo towards the end
            note_vel = velocity + (i * 5)
            # Notes get shorter toward the end for anticipation
            actual_dur = note_dur * (0.8 - (i * 0.05))
            self.midi.addNote(self.track, self.channel, note, note_time, actual_dur, note_vel)
    
    def generate_section(self, section_type, bars=4, is_final=False):
        if section_type == 'verse':
            styles = ['arpeggio', 'melody', 'strum']
            weights = [0.4, 0.3, 0.3]
            base_velocity = 65
            random.seed(self.verse_style_seed)
        else:
            styles = ['strum', 'power', 'arpeggio']
            weights = [0.5, 0.3, 0.2]
            base_velocity = 80
            random.seed(self.chorus_style_seed)
        
        beats_per_bar = 4
        
        for bar in range(bars):
            chord_degree = self.progression[bar % len(self.progression)]
            bar_duration = beats_per_bar
            
            # Last bar of final section: use turnaround for smooth loop
            if is_final and bar == bars - 1:
                # First half: regular playing on the chord
                style = random.choices(styles, weights=weights)[0]
                half_bar = bar_duration / 2
                
                if style == 'strum':
                    self.add_strummed_chord(chord_degree, half_bar, base_velocity)
                elif style == 'arpeggio':
                    self.add_arpeggiated_chord(chord_degree, half_bar, base_velocity - 10)
                elif style == 'melody':
                    self.add_melody_phrase(chord_degree, half_bar, base_velocity)
                elif style == 'power':
                    self.add_power_chord(chord_degree, half_bar, base_velocity + 10)
                
                self.current_time += half_bar
                
                # Second half: turnaround leading back to start
                self.add_turnaround(half_bar, base_velocity)
                self.current_time += half_bar
                continue
            
            style = random.choices(styles, weights=weights)[0]
            
            if style == 'strum':
                pattern = random.choice(STRUM_PATTERNS)
                time_in_bar = 0
                for duration in pattern:
                    if time_in_bar >= bar_duration:
                        break
                    self.add_strummed_chord(chord_degree, duration, base_velocity)
                    self.current_time += duration
                    time_in_bar += duration
                if time_in_bar < bar_duration:
                    self.current_time += (bar_duration - time_in_bar)
                    
            elif style == 'arpeggio':
                if random.random() > 0.5:
                    self.add_arpeggiated_chord(chord_degree, bar_duration / 2, base_velocity - 10)
                    self.current_time += bar_duration / 2
                    self.add_arpeggiated_chord(chord_degree, bar_duration / 2, base_velocity - 10)
                    self.current_time += bar_duration / 2
                else:
                    self.add_arpeggiated_chord(chord_degree, bar_duration, base_velocity - 10)
                    self.current_time += bar_duration
                    
            elif style == 'melody':
                self.add_melody_phrase(chord_degree, bar_duration, base_velocity)
                self.current_time += bar_duration
                
            elif style == 'power':
                pattern = random.choice([[2, 2], [1, 1, 2], [1.5, 1.5, 1]])
                time_in_bar = 0
                for duration in pattern:
                    if time_in_bar >= bar_duration:
                        break
                    self.add_power_chord(chord_degree, duration, base_velocity + 10)
                    self.current_time += duration
                    time_in_bar += duration
                if time_in_bar < bar_duration:
                    self.current_time += (bar_duration - time_in_bar)
        
        # Reset random seed so other parts of the code aren't affected
        random.seed()
    
    def generate_song(self):
        # Verse and Chorus - chorus is the final section with turnaround
        self.generate_section('verse', bars=4, is_final=False)
        self.generate_section('chorus', bars=4, is_final=True)
        
        # No trailing notes - song ends exactly at loop point
        return self.get_midi_bytes()
    
    def get_midi_bytes(self):
        """Return MIDI data as bytes (in-memory, no file)."""
        buffer = io.BytesIO()
        self.midi.writeFile(buffer)
        buffer.seek(0)
        return buffer
    
    def get_info(self):
        """Return song information for display."""
        root_name = NOTE_NAMES[self.root % 12]
        octave = (self.root // 12) - 1
        seconds_per_beat = 60 / self.bpm
        duration = self.current_time * seconds_per_beat
        
        return {
            'root': f"{root_name}{octave}",
            'mode': self.mode_name,
            'progression': self.progression_name,
            'bpm': self.bpm,
            'duration': f"{duration:.1f}s",
            'bars': 8
        }


class GuitarSongApp:
    """GUI Application for the guitar song generator with looping playback."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🎸 Guitar Song Generator")
        self.root.geometry("520x450")
        self.root.configure(bg='#1a1a2e')
        
        # Initialize pygame mixer for MIDI playback
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        
        self.current_midi = None
        self.is_playing = False
        self.is_looping = True  # Loop by default
        
        self.setup_ui()
        
    def setup_ui(self):
        # Title
        title = tk.Label(
            self.root, 
            text="🎸 Guitar Song Generator",
            font=('Helvetica', 24, 'bold'),
            fg='#e94560',
            bg='#1a1a2e'
        )
        title.pack(pady=20)
        
        # Info frame
        self.info_frame = tk.Frame(self.root, bg='#16213e', padx=20, pady=15)
        self.info_frame.pack(fill='x', padx=30, pady=10)
        
        self.info_labels = {}
        info_items = ['root', 'mode', 'progression', 'bpm', 'duration', 'bars']
        display_names = ['Root Note', 'Mode', 'Progression', 'Tempo', 'Duration', 'Bars']
        
        for i, (key, display) in enumerate(zip(info_items, display_names)):
            row_frame = tk.Frame(self.info_frame, bg='#16213e')
            row_frame.pack(fill='x', pady=3)
            
            label = tk.Label(
                row_frame,
                text=f"{display}:",
                font=('Helvetica', 12),
                fg='#a0a0a0',
                bg='#16213e',
                width=12,
                anchor='w'
            )
            label.pack(side='left')
            
            value = tk.Label(
                row_frame,
                text="—",
                font=('Helvetica', 12, 'bold'),
                fg='#ffffff',
                bg='#16213e',
                anchor='w'
            )
            value.pack(side='left', padx=10)
            self.info_labels[key] = value
        
        # Status label
        self.status_label = tk.Label(
            self.root,
            text="Click Generate to create a new song",
            font=('Helvetica', 11),
            fg='#7a7a7a',
            bg='#1a1a2e'
        )
        self.status_label.pack(pady=10)
        
        # Loop checkbox
        self.loop_var = tk.BooleanVar(value=True)
        loop_check = tk.Checkbutton(
            self.root,
            text="🔁 Loop Playback",
            variable=self.loop_var,
            font=('Helvetica', 11),
            fg='#4ecca3',
            bg='#1a1a2e',
            selectcolor='#16213e',
            activebackground='#1a1a2e',
            activeforeground='#4ecca3',
            command=self.toggle_loop_setting
        )
        loop_check.pack(pady=5)
        
        # Buttons frame
        btn_frame = tk.Frame(self.root, bg='#1a1a2e')
        btn_frame.pack(pady=15)
        
        # Generate button
        self.generate_btn = tk.Button(
            btn_frame,
            text="⚡ Generate",
            font=('Helvetica', 14, 'bold'),
            fg='white',
            bg='#e94560',
            activebackground='#ff6b6b',
            activeforeground='white',
            width=12,
            height=2,
            relief='flat',
            cursor='hand2',
            command=self.generate_song
        )
        self.generate_btn.pack(side='left', padx=10)
        
        # Play/Stop button
        self.play_btn = tk.Button(
            btn_frame,
            text="▶ Play",
            font=('Helvetica', 14, 'bold'),
            fg='white',
            bg='#4a4a6a',
            activebackground='#6a6a8a',
            activeforeground='white',
            width=12,
            height=2,
            relief='flat',
            cursor='hand2',
            command=self.toggle_playback,
            state='disabled'
        )
        self.play_btn.pack(side='left', padx=10)
        
        # Footer
        footer = tk.Label(
            self.root,
            text="Songs loop seamlessly • Verse → Chorus → Repeat",
            font=('Helvetica', 9),
            fg='#5a5a7a',
            bg='#1a1a2e'
        )
        footer.pack(side='bottom', pady=15)
        
    def toggle_loop_setting(self):
        """Update loop setting."""
        self.is_looping = self.loop_var.get()
        if self.is_playing:
            # Update the current playback loop setting
            loops = -1 if self.is_looping else 0
            # We can't change loop mid-playback easily, so just update for next play
    
    def generate_song(self):
        """Generate a new song."""
        self.stop_playback()
        self.status_label.config(text="Generating...", fg='#e94560')
        self.root.update()
        
        # Generate song
        bpm = random.randint(80, 120)
        generator = GuitarSongGenerator(bpm=bpm)
        self.current_midi = generator.generate_song()
        info = generator.get_info()
        
        # Update info display
        for key, value in info.items():
            if key in self.info_labels:
                self.info_labels[key].config(text=str(value))
        
        self.status_label.config(text="✓ Song ready! Click Play to listen", fg='#4ecca3')
        self.play_btn.config(state='normal', bg='#4ecca3')
        
    def toggle_playback(self):
        """Toggle between play and stop."""
        if self.is_playing:
            self.stop_playback()
        else:
            self.start_playback()
    
    def start_playback(self):
        """Start playing the current song."""
        if self.current_midi is None:
            return
        
        self.current_midi.seek(0)
        
        try:
            pygame.mixer.music.load(self.current_midi)
            # -1 loops = infinite loop, 0 = play once
            loops = -1 if self.loop_var.get() else 0
            pygame.mixer.music.play(loops=loops)
            self.is_playing = True
            self.play_btn.config(text="⏹ Stop", bg='#e94560')
            
            loop_text = "🔁 Looping..." if self.loop_var.get() else "♪ Playing..."
            self.status_label.config(text=loop_text, fg='#4ecca3')
            
            # Monitor playback in background (only matters if not looping)
            if not self.loop_var.get():
                self.check_playback()
            
        except Exception as e:
            self.status_label.config(text=f"Playback error: {e}", fg='#ff6b6b')
    
    def stop_playback(self):
        """Stop playback."""
        pygame.mixer.music.stop()
        self.is_playing = False
        self.play_btn.config(text="▶ Play", bg='#4ecca3')
        if self.current_midi:
            self.status_label.config(text="✓ Stopped. Click Play to restart", fg='#4ecca3')
    
    def check_playback(self):
        """Check if playback has finished (only for non-looping mode)."""
        if self.is_playing and not self.loop_var.get():
            if not pygame.mixer.music.get_busy():
                self.is_playing = False
                self.play_btn.config(text="▶ Play", bg='#4ecca3')
                self.status_label.config(text="✓ Finished! Play again or Generate new", fg='#4ecca3')
            else:
                self.root.after(100, self.check_playback)
    
    def run(self):
        """Start the application."""
        self.root.mainloop()
        pygame.mixer.quit()


def main():
    app = GuitarSongApp()
    app.run()


if __name__ == "__main__":
    main()