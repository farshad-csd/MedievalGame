# debug_window.py - Tkinter-based debug window with scrollable, selectable text
import tkinter as tk
from tkinter import ttk, scrolledtext
from constants import TICKS_PER_YEAR, TICKS_PER_DAY, SKILLS, SPEED_OPTIONS, UPDATE_INTERVAL
from scenario_characters import CHARACTER_TEMPLATES


class DebugWindow:
    """A separate Tkinter window for debug info and action log.
    
    Supports:
    - Scrolling with mouse wheel and scrollbars
    - Text selection with mouse
    - Ctrl+C / Cmd+C to copy
    - Auto-updates from game state
    - Game controls (speed, pause, skip)
    """
    
    def __init__(self, state, logic=None):
        self.state = state
        self.logic = logic  # GameLogic instance for skip year
        self.root = tk.Tk()
        self.root.title("Debug Console")
        self.root.geometry("900x750")
        self.root.configure(bg='#1a1a2e')
        
        # Track last log length to detect new entries
        self._last_log_length = 0
        self._auto_scroll_log = True
        
        # Speed control
        self.speed_index = 0
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the UI components"""
        # Configure style
        style = ttk.Style()
        style.configure('Debug.TFrame', background='#1a1a2e')
        style.configure('Debug.TLabel', background='#1a1a2e', foreground='#e0e0e0', 
                       font=('Consolas', 10, 'bold'))
        style.configure('Debug.TCheckbutton', background='#1a1a2e', foreground='#e0e0e0')
        style.configure('Control.TButton', font=('Arial', 10))
        
        # Main container
        main_frame = ttk.Frame(self.root, style='Debug.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Control bar at top
        control_frame = ttk.Frame(main_frame, style='Debug.TFrame')
        control_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Speed button
        self.speed_btn = tk.Button(
            control_frame, text="Speed: 1x", command=self._toggle_speed,
            bg='#3a3a5a', fg='white', font=('Arial', 10), width=12
        )
        self.speed_btn.pack(side=tk.LEFT, padx=2)
        
        # Pause button
        self.pause_btn = tk.Button(
            control_frame, text="Pause", command=self._toggle_pause,
            bg='#3a3a5a', fg='white', font=('Arial', 10), width=10
        )
        self.pause_btn.pack(side=tk.LEFT, padx=2)
        
        # Skip year button
        self.skip_btn = tk.Button(
            control_frame, text="Skip 1 Year", command=self._skip_one_year,
            bg='#3a3a5a', fg='white', font=('Arial', 10), width=12
        )
        self.skip_btn.pack(side=tk.LEFT, padx=2)
        
        # Status bar (player info, zoom, etc)
        self.status_label = ttk.Label(control_frame, text="", style='Debug.TLabel')
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # Tick info section
        tick_frame = ttk.Frame(main_frame, style='Debug.TFrame')
        tick_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.tick_label = ttk.Label(tick_frame, text="", style='Debug.TLabel')
        self.tick_label.pack(side=tk.LEFT)
        
        # Paned window for resizable sections
        paned = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Debug stats section
        debug_frame = ttk.Frame(paned, style='Debug.TFrame')
        paned.add(debug_frame, weight=2)
        
        debug_label = ttk.Label(debug_frame, text="CHARACTER STATS (Ctrl+C to copy selection)", 
                               style='Debug.TLabel')
        debug_label.pack(anchor=tk.W)
        
        # Debug text area with scrollbar
        self.debug_text = scrolledtext.ScrolledText(
            debug_frame,
            wrap=tk.NONE,
            font=('Consolas', 9),
            bg='#0f0f1a',
            fg='#b0b0b0',
            insertbackground='white',
            selectbackground='#4a4a6a',
            selectforeground='white',
            height=15
        )
        self.debug_text.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        
        # Add horizontal scrollbar for debug
        debug_h_scroll = ttk.Scrollbar(debug_frame, orient=tk.HORIZONTAL, 
                                        command=self.debug_text.xview)
        debug_h_scroll.pack(fill=tk.X)
        self.debug_text.configure(xscrollcommand=debug_h_scroll.set)
        
        # Action log section
        log_frame = ttk.Frame(paned, style='Debug.TFrame')
        paned.add(log_frame, weight=1)
        
        # Log header with auto-scroll checkbox
        log_header = ttk.Frame(log_frame, style='Debug.TFrame')
        log_header.pack(fill=tk.X)
        
        log_label = ttk.Label(log_header, text="ACTION LOG (Ctrl+C to copy selection)", 
                             style='Debug.TLabel')
        log_label.pack(side=tk.LEFT)
        
        self.auto_scroll_var = tk.BooleanVar(value=True)
        auto_scroll_cb = ttk.Checkbutton(
            log_header, 
            text="Auto-scroll", 
            variable=self.auto_scroll_var,
            style='Debug.TCheckbutton'
        )
        auto_scroll_cb.pack(side=tk.RIGHT)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg='#1a0f1a',
            fg='#c0c0c0',
            insertbackground='white',
            selectbackground='#6a4a6a',
            selectforeground='white',
            height=12
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        
        # Bind copy shortcut (works by default but ensure it's there)
        self.debug_text.bind('<Control-c>', self._copy_selection)
        self.log_text.bind('<Control-c>', self._copy_selection)
        
        # Make text read-only but still selectable
        self.debug_text.bind('<Key>', lambda e: self._readonly_handler(e))
        self.log_text.bind('<Key>', lambda e: self._readonly_handler(e))
    
    def _toggle_speed(self):
        """Cycle through speed options"""
        self.speed_index = (self.speed_index + 1) % len(SPEED_OPTIONS)
        self.state.game_speed = SPEED_OPTIONS[self.speed_index]
        self.speed_btn.configure(text=f"Speed: {self.state.game_speed}x")
    
    def _toggle_pause(self):
        """Toggle pause state"""
        self.state.paused = not self.state.paused
        self.pause_btn.configure(text="Resume" if self.state.paused else "Pause")
    
    def _skip_one_year(self):
        """Skip forward one year"""
        if not self.logic:
            return
            
        self.state.log_action("=== SKIPPING 1 YEAR ===")
        
        # Time per tick in seconds
        tick_duration = UPDATE_INTERVAL / 1000.0
        
        for _ in range(TICKS_PER_YEAR):
            # Process game logic (sets velocities)
            self.logic.process_tick()
            
            # Move characters for this tick
            remaining = tick_duration
            while remaining > 0:
                step = min(remaining, 0.05)
                self.logic.update_player_position(step)
                self.logic.update_npc_positions(step)
                remaining -= step
        
        self.state.log_action("=== SKIP COMPLETE ===")
        
    def _readonly_handler(self, event):
        """Allow copy but prevent editing"""
        # Allow Ctrl+C, Ctrl+A, arrow keys, etc.
        if event.state & 0x4:  # Ctrl held
            return  # Allow
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Prior', 'Next'):
            return  # Allow navigation
        return 'break'  # Block other keys
    
    def _copy_selection(self, event=None):
        """Handle copy - let default behavior work"""
        pass  # Default Tkinter copy works fine
    
    def set_status(self, status_text):
        """Update the status label (called from GUI)"""
        self.status_label.configure(text=status_text)
    
    def update(self):
        """Update the window contents. Call this from the game loop."""
        try:
            self._update_tick_info()
            self._update_debug_stats()
            self._update_action_log()
            self._update_button_states()
            self.root.update()
        except tk.TclError:
            # Window was closed
            pass
    
    def _update_button_states(self):
        """Update button text to reflect current state"""
        self.speed_btn.configure(text=f"Speed: {self.state.game_speed}x")
        self.pause_btn.configure(text="Resume" if self.state.paused else "Pause")
    
    def _update_tick_info(self):
        """Update the tick/time display"""
        year = (self.state.ticks // TICKS_PER_YEAR) + 1
        day = ((self.state.ticks % TICKS_PER_YEAR) // TICKS_PER_DAY) + 1
        day_progress = (self.state.ticks % TICKS_PER_DAY) / TICKS_PER_DAY * 100
        
        paused_str = " [PAUSED]" if self.state.paused else ""
        tick_text = f"Year {year}, Day {day}/3 | {day_progress:.0f}% through day | Tick {self.state.ticks}{paused_str}"
        self.tick_label.configure(text=tick_text)
    
    def _update_debug_stats(self):
        """Update the character stats display"""
        # Save scroll position
        scroll_pos = self.debug_text.yview()
        
        # Build content
        lines = []
        header = f"{'Name':<18}{'Pos':<12}{'Age':<5}{'HP':<6}{'Hunger':<7}{'Inventory':<28}{'Home':<10}{'Job':<10}{'Alleg':<8}{'Traits':<12}{'Status':<12}"
        lines.append(header)
        lines.append("=" * 140)
        
        for char in self.state.characters:
            name = char['name']
            # Get position - show as float
            pos = f"({char['x']:.1f},{char['y']:.1f})"
            home = char.get('home', '-') or '-'
            job = char.get('job', '-') or '-'
            
            # Build inventory display
            inv_parts = []
            for slot in char['inventory']:
                if slot is None:
                    inv_parts.append('-')
                elif slot['type'] == 'money':
                    inv_parts.append(f"${slot['amount']}")
                elif slot['type'] == 'food':
                    inv_parts.append(f"F{slot['amount']}")
                else:
                    inv_parts.append(f"{slot['type'][:3]}{slot['amount']}")
            inv_display = '|'.join(inv_parts)
            
            # Get traits
            template = CHARACTER_TEMPLATES.get(name, {})
            attr = template.get('attractiveness', 0)
            conf = template.get('confidence', 0)
            cunn = template.get('cunning', 0)
            moral = char.get('morality', 5)
            traits_str = f"{attr}/{conf}/{cunn}/{moral}"
            
            # Status display
            status = ""
            known_crimes = char.get('known_crimes', {})
            known_criminals = len(known_crimes)
            if char.get('is_frozen', False):
                status = "FROZEN"
            elif char.get('is_starving', False):
                status = "STARVING"
            elif char.get('is_murderer', False):
                status = "MURDERER"
            elif char.get('is_thief', False):
                status = "THIEF"
            elif known_criminals > 0:
                status = f"knows:{known_criminals}"
            else:
                status = "-"
            
            hunger_display = f"{char['hunger']:.0f}"
            allegiance = char.get('allegiance', '-') or '-'
            
            line = f"{name:<18}{pos:<12}{char['age']:<5}{char['health']:<6}{hunger_display:<7}{inv_display:<28}{home:<10}{job:<10}{allegiance:<8}{traits_str:<12}{status:<12}"
            lines.append(line)
        
        # Barrels section
        lines.append("")
        lines.append("=" * 80)
        lines.append("BARRELS")
        lines.append("-" * 80)
        
        for pos, barrel in self.state.barrels.items():
            barrel_name = barrel['name']
            barrel_pos = f"({pos[0]},{pos[1]})"
            barrel_home = barrel['home']
            barrel_owner = barrel['owner'] if barrel['owner'] else "(unowned)"
            barrel_food = self.state.get_barrel_food(barrel)
            barrel_money = self.state.get_barrel_money(barrel)
            used_slots = sum(1 for slot in barrel['inventory'] if slot is not None)
            total_slots = len(barrel['inventory'])
            
            line = f"{barrel_name:<20} Pos:{barrel_pos:<10} Home:{barrel_home:<10} Owner:{barrel_owner:<18} Food:{barrel_food:<5} ${barrel_money:<5} Slots:{used_slots}/{total_slots}"
            lines.append(line)
        
        # Beds section
        lines.append("")
        lines.append("=" * 80)
        lines.append("BEDS")
        lines.append("-" * 80)
        
        for pos, bed in self.state.beds.items():
            bed_name = bed['name']
            bed_pos = f"({pos[0]},{pos[1]})"
            bed_home = bed['home']
            bed_owner = bed['owner'] if bed['owner'] else "(unowned)"
            line = f"{bed_name:<20} Pos:{bed_pos:<10} Home:{bed_home:<10} Owner:{bed_owner:<18}"
            lines.append(line)
        
        # Camps section
        camps = [(char['name'], char['camp_position']) for char in self.state.characters if char.get('camp_position')]
        if camps:
            lines.append("")
            lines.append("=" * 80)
            lines.append("CAMPS")
            lines.append("-" * 80)
            
            for owner_name, camp_pos in camps:
                camp_pos_str = f"({camp_pos[0]},{camp_pos[1]})"
                camp_name = owner_name + "'s Camp"
                line = f"{camp_name:<20} Pos:{camp_pos_str:<10}"
                lines.append(line)
        
        # Skills section
        chars_with_skills = []
        for char in self.state.characters:
            skills = char.get('skills', {})
            nonzero_skills = {k: v for k, v in skills.items() if v > 0}
            if nonzero_skills:
                chars_with_skills.append((char['name'], nonzero_skills))
        
        if chars_with_skills:
            lines.append("")
            lines.append("=" * 80)
            lines.append("SKILLS (non-zero only)")
            lines.append("-" * 80)
            
            for char_name, skills in chars_with_skills:
                skill_strs = []
                for skill_id, value in sorted(skills.items()):
                    skill_info = SKILLS.get(skill_id, {})
                    skill_name = skill_info.get('name', skill_id)
                    category = skill_info.get('category', '?')
                    cat_marker = 'C' if category == 'combat' else ('B' if category == 'benign' else 'C/B')
                    skill_strs.append(f"{skill_name}({cat_marker}):{value}")
                
                line = f"{char_name:<20} {', '.join(skill_strs)}"
                lines.append(line)
        
        # Update text widget
        content = '\n'.join(lines)
        self.debug_text.configure(state=tk.NORMAL)
        self.debug_text.delete('1.0', tk.END)
        self.debug_text.insert('1.0', content)
        self.debug_text.configure(state=tk.DISABLED)
        
        # Restore scroll position
        self.debug_text.yview_moveto(scroll_pos[0])
    
    def _update_action_log(self):
        """Update the action log display"""
        current_len = len(self.state.action_log)
        
        if current_len != self._last_log_length:
            # New entries - update the log
            self.log_text.configure(state=tk.NORMAL)
            
            if current_len > self._last_log_length:
                # Append new entries
                new_entries = self.state.action_log[self._last_log_length:]
                for entry in new_entries:
                    self.log_text.insert(tk.END, entry + '\n')
            else:
                # Log was cleared or reset - rebuild
                self.log_text.delete('1.0', tk.END)
                for entry in self.state.action_log:
                    self.log_text.insert(tk.END, entry + '\n')
            
            self.log_text.configure(state=tk.DISABLED)
            self._last_log_length = current_len
            
            # Auto-scroll to bottom if enabled
            if self.auto_scroll_var.get():
                self.log_text.see(tk.END)
    
    def is_open(self):
        """Check if the window is still open"""
        try:
            return self.root.winfo_exists()
        except tk.TclError:
            return False
    
    def close(self):
        """Close the window"""
        try:
            self.root.destroy()
        except tk.TclError:
            pass