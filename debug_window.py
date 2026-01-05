# debug_window.py - Tkinter-based debug window running in separate process
# This solves the pygame/tkinter macOS conflict by complete process isolation
import tkinter as tk
from tkinter import ttk, scrolledtext
import multiprocessing
from constants import TICKS_PER_YEAR, TICKS_PER_DAY, SKILLS, SPEED_OPTIONS, UPDATE_INTERVAL
from scenario_characters import CHARACTER_TEMPLATES


class DebugWindowProcess:
    """
    Wrapper that spawns the debug window in a separate process.
    Used by the main game to communicate with the tkinter debug window.
    """
    
    def __init__(self, state, logic=None):
        self.state = state
        self.logic = logic
        
        # Queues for inter-process communication
        self.data_queue = multiprocessing.Queue()  # Main -> Debug window
        self.command_queue = multiprocessing.Queue()  # Debug window -> Main
        
        # Start the debug window process
        self.process = multiprocessing.Process(
            target=_run_debug_window,
            args=(self.data_queue, self.command_queue),
            daemon=True
        )
        self.process.start()
        
        # Track speed index locally
        self.speed_index = 0
    
    def set_status(self, status_text):
        """Send status update to debug window"""
        # This gets included in the state snapshot
        pass
    
    def update(self):
        """Send current state to debug window and process any commands"""
        # Build state snapshot to send
        snapshot = self._build_snapshot()
        
        # Send to debug window (non-blocking)
        try:
            self.data_queue.put_nowait(snapshot)
        except:
            pass  # Queue full, skip this update
        
        # Process commands from debug window
        self._process_commands()
    
    def _build_snapshot(self):
        """Build a serializable snapshot of game state for the debug window"""
        # Build character data
        characters = []
        for char in self.state.characters:
            # Build memory summaries
            memories_summary = []
            for m in char.memories:
                mem_type = m.get('type', '?')
                subject = m.get('subject')
                subject_name = subject.get('name', '?') if hasattr(subject, 'get') else str(subject)
                tick = m.get('tick', 0)
                source = m.get('source', '?')
                details = m.get('details', {})
                
                mem_info = {
                    'type': mem_type,
                    'subject': subject_name,
                    'tick': tick,
                    'source': source,
                }
                
                # Add type-specific details
                if mem_type == 'crime':
                    mem_info['crime_type'] = details.get('crime_type', '?')
                    victim = details.get('victim')
                    mem_info['victim'] = victim.get('name', '?') if hasattr(victim, 'get') else str(victim) if victim else None
                    mem_info['reported'] = m.get('reported', False)
                elif mem_type == 'committed_crime':
                    mem_info['crime_type'] = details.get('crime_type', '?')
                    victim = details.get('victim')
                    mem_info['victim'] = victim.get('name', '?') if hasattr(victim, 'get') else str(victim) if victim else None
                elif mem_type == 'attacked_by':
                    mem_info['reported'] = m.get('reported', False)
                
                memories_summary.append(mem_info)
            
            # Build intent summary
            intent_summary = None
            if char.intent:
                target = char.intent.get('target')
                target_name = target.get('name', '?') if hasattr(target, 'get') else str(target) if target else None
                intent_summary = {
                    'action': char.intent.get('action'),
                    'target': target_name,
                    'reason': char.intent.get('reason'),
                    'started_tick': char.intent.get('started_tick'),
                }
            
            char_data = {
                'name': char['name'],
                'x': char.x,  # World coordinates (projected when in interior)
                'y': char.y,
                'prevailing_x': char.prevailing_x,  # Actual stored position
                'prevailing_y': char.prevailing_y,
                'zone': char.zone,  # None = exterior, house_name = interior
                'age': char['age'],
                'health': char['health'],
                'hunger': char['hunger'],
                'fatigue': char.get('fatigue', 100),
                'stamina': char.get('stamina', 100),
                'inventory': char['inventory'][:],  # Copy
                'home': char.get('home'),
                'job': char.get('job'),
                'allegiance': char.get('allegiance'),
                'morality': char.get('morality', 5),
                'skills': dict(char.get('skills', {})),
                'is_frozen': char.get('is_frozen', False),
                'is_starving': char.get('is_starving', False),
                'is_murderer': char.has_committed_crime('murder'),
                'is_thief': char.has_committed_crime('theft'),
                'known_crimes_count': len(char.get_memories(memory_type='crime')),
                'camp_position': char.get('camp_position'),
                'memories': memories_summary,
                'intent': intent_summary,
                'facing': char.get('facing', 'down'),
            }
            characters.append(char_data)
        
        # Build barrel data
        barrels = {}
        for pos, barrel in self.state.interactables.barrels.items():
            barrels[pos] = {
                'name': barrel.name,
                'home': barrel.home,
                'owner': barrel.owner,
                'inventory': barrel.inventory[:],
            }
        
        # Build bed data
        beds = {}
        for pos, bed in self.state.interactables.beds.items():
            beds[pos] = {
                'name': bed.name,
                'home': bed.home,
                'owner': bed.owner,
            }
        
        # Player info for status
        player_status = ""
        if self.state.player:
            p = self.state.player
            player_food = p.get_item('wheat')
            player_money = p.get_item('money')
            if p.zone:
                # Show both local (interior) and world coords when inside
                player_status = f"Local:({p.prevailing_x:.1f},{p.prevailing_y:.1f}) World:({p.x:.1f},{p.y:.1f}) Zone:{p.zone} Wheat:{player_food} ${player_money} HP:{p.health}"
            else:
                player_status = f"Pos:({p.x:.1f},{p.y:.1f}) Wheat:{player_food} ${player_money} HP:{p.health}"
        
        return {
            'ticks': self.state.ticks,
            'game_speed': self.state.game_speed,
            'paused': self.state.paused,
            'characters': characters,
            'barrels': barrels,
            'beds': beds,
            'action_log': list(self.state.action_log),
            'log_total_count': self.state.log_total_count,
            'player_status': player_status,
        }
    
    def _process_commands(self):
        """Process commands sent from debug window"""
        while True:
            try:
                cmd = self.command_queue.get_nowait()
            except:
                break
            
            if cmd['type'] == 'toggle_speed':
                self.speed_index = (self.speed_index + 1) % len(SPEED_OPTIONS)
                self.state.game_speed = SPEED_OPTIONS[self.speed_index]
            
            elif cmd['type'] == 'toggle_pause':
                self.state.paused = not self.state.paused
            
            elif cmd['type'] == 'skip_year':
                if self.logic:
                    self._skip_one_year()
    
    def _skip_one_year(self):
        """Skip forward one year"""
        self.state.log_action("=== SKIPPING 1 YEAR ===")
        
        tick_duration = UPDATE_INTERVAL / 1000.0
        
        for _ in range(TICKS_PER_YEAR):
            self.logic.process_tick()
            
            # Update NPC positions (player doesn't move during skip - no input)
            remaining = tick_duration
            while remaining > 0:
                step = min(remaining, 0.05)
                self.logic.update_npc_positions(step)
                remaining -= step
        
        self.state.log_action("=== SKIP COMPLETE ===")
    
    def is_open(self):
        """Check if the debug window process is still running"""
        return self.process.is_alive()
    
    def close(self):
        """Close the debug window"""
        try:
            self.data_queue.put_nowait({'shutdown': True})
        except:
            pass
        self.process.terminate()


def _run_debug_window(data_queue, command_queue):
    """Entry point for the debug window process"""
    window = _DebugWindowInternal(data_queue, command_queue)
    window.run()


class _DebugWindowInternal:
    """The actual Tkinter debug window (runs in separate process).
    
    Supports:
    - Scrolling with mouse wheel and scrollbars
    - Text selection with mouse
    - Ctrl+C / Cmd+C to copy
    - Auto-updates from game state
    - Game controls (speed, pause, skip)
    """
    
    def __init__(self, data_queue, command_queue):
        self.data_queue = data_queue
        self.command_queue = command_queue
        
        # Current state snapshot
        self.snapshot = None
        
        # Track total log entries seen
        self._last_log_total = 0
        self._auto_scroll_log = True
        
        # Create window
        self.root = tk.Tk()
        self.root.title("Debug Console")
        self.root.geometry("900x750")
        self.root.configure(bg='#1a1a2e')
        
        self._setup_ui()
        
        # Schedule periodic updates
        self.root.after(50, self._poll_data)
    
    def _setup_ui(self):
        """Set up the UI components"""
        import sys
        is_mac = sys.platform == 'darwin'
        
        # Configure style
        style = ttk.Style()
        style.configure('Debug.TFrame', background='#1a1a2e')
        style.configure('Debug.TLabel', background='#1a1a2e', foreground='#e0e0e0', 
                       font=('Consolas', 10, 'bold'))
        style.configure('Debug.TCheckbutton', background='#1a1a2e', foreground='#e0e0e0')
        style.configure('Control.TButton', font=('Arial', 10))
        
        # Configure styled buttons that work on Mac dark mode
        # Use ttk.Button with custom styling for cross-platform compatibility
        style.configure('Dark.TButton', 
                       font=('Arial', 10, 'bold'),
                       padding=(8, 4))
        style.map('Dark.TButton',
                 background=[('active', '#5a5a8a'), ('!active', '#3a3a5a')],
                 foreground=[('active', 'white'), ('!active', 'white')])
        
        # Main container
        main_frame = ttk.Frame(self.root, style='Debug.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Control bar at top
        control_frame = ttk.Frame(main_frame, style='Debug.TFrame')
        control_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Helper function to create buttons
        # Use standard tk.Button - simpler and more reliable
        def create_button(parent, text, command, width=12):
            btn = tk.Button(
                parent, text=text, command=command,
                font=('Arial', 10, 'bold'),
                width=width,
                relief=tk.RAISED,
                bd=2
            )
            # On Mac, we can't easily control colors, but at least it will work
            if not is_mac:
                btn.configure(
                    bg='#3a3a5a', fg='white',
                    activebackground='#5a5a8a', activeforeground='white'
                )
            return btn
        
        self.create_button = create_button  # Store for later use
        self.is_mac = is_mac
        
        # Speed button
        self.speed_btn = create_button(control_frame, "Speed: 1x", self._toggle_speed, width=12)
        self.speed_btn.pack(side=tk.LEFT, padx=2)
        
        # Pause button
        self.pause_btn = create_button(control_frame, "Pause", self._toggle_pause, width=10)
        self.pause_btn.pack(side=tk.LEFT, padx=2)
        
        # Skip year button
        self.skip_btn = create_button(control_frame, "Skip 1 Year", self._skip_one_year, width=12)
        self.skip_btn.pack(side=tk.LEFT, padx=2)
        
        # Copy All button
        self.copy_all_btn = create_button(control_frame, "📋 Copy All", self._copy_all, width=12)
        self.copy_all_btn.pack(side=tk.LEFT, padx=2)
        
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
        
        # Bind copy shortcut
        self.debug_text.bind('<Control-c>', self._copy_selection)
        self.log_text.bind('<Control-c>', self._copy_selection)
        
        # Make text read-only but still selectable
        self.debug_text.bind('<Key>', lambda e: self._readonly_handler(e))
        self.log_text.bind('<Key>', lambda e: self._readonly_handler(e))
    
    def _toggle_speed(self):
        """Send speed toggle command to main process"""
        try:
            self.command_queue.put_nowait({'type': 'toggle_speed'})
        except:
            pass  # Queue full, command lost
    
    def _toggle_pause(self):
        """Send pause toggle command to main process"""
        try:
            self.command_queue.put_nowait({'type': 'toggle_pause'})
        except:
            pass
    
    def _skip_one_year(self):
        """Send skip year command to main process"""
        try:
            self.command_queue.put_nowait({'type': 'skip_year'})
        except:
            pass
    
    def _readonly_handler(self, event):
        """Allow copy but prevent editing"""
        if event.state & 0x4:  # Ctrl held
            return
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Prior', 'Next'):
            return
        return 'break'
    
    def _copy_selection(self, event=None):
        """Handle copy - let default behavior work"""
        pass
    
    def _copy_all(self):
        """Copy everything from debug stats and action log to clipboard"""
        # Get all text from debug stats
        debug_content = self.debug_text.get('1.0', tk.END).strip()
        
        # Get all text from action log
        log_content = self.log_text.get('1.0', tk.END).strip()
        
        # Combine with headers
        separator = "=" * 80
        combined = f"""DEBUG WINDOW - FULL EXPORT
{separator}

=== CHARACTER STATS ===
{debug_content}

{separator}

=== ACTION LOG ===
{log_content}
"""
        
        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(combined)
        self.root.update()  # Required for clipboard to persist
        
        # Flash the button to indicate success
        self._flash_copy_button()
    
    def _flash_copy_button(self):
        """Flash the copy button to indicate success"""
        self.copy_all_btn.configure(text='✓ Copied!')
        self.root.after(800, lambda: self.copy_all_btn.configure(text='📋 Copy All'))
    
    def _poll_data(self):
        """Poll for new data from main process"""
        # Get latest snapshot (skip old ones)
        latest = None
        while True:
            try:
                data = self.data_queue.get_nowait()
                if data.get('shutdown'):
                    self.root.quit()
                    return
                latest = data
            except:
                break
        
        if latest:
            self.snapshot = latest
            self._update_display()
        
        # Schedule next poll
        self.root.after(50, self._poll_data)
    
    def _update_display(self):
        """Update all display elements from current snapshot"""
        if not self.snapshot:
            return
        
        self._update_tick_info()
        self._update_debug_stats()
        self._update_action_log()
        self._update_button_states()
        self._update_status()
    
    def _update_status(self):
        """Update status label"""
        status = self.snapshot.get('player_status', '')
        self.status_label.configure(text=status)
    
    def _update_button_states(self):
        """Update button text to reflect current state"""
        self.speed_btn.configure(text=f"Speed: {self.snapshot['game_speed']}x")
        self.pause_btn.configure(text="Resume" if self.snapshot['paused'] else "Pause")
    
    def _update_tick_info(self):
        """Update the tick/time display"""
        ticks = self.snapshot['ticks']
        year = (ticks // TICKS_PER_YEAR) + 1
        day = ((ticks % TICKS_PER_YEAR) // TICKS_PER_DAY) + 1
        day_progress = (ticks % TICKS_PER_DAY) / TICKS_PER_DAY * 100
        
        paused_str = " [PAUSED]" if self.snapshot['paused'] else ""
        tick_text = f"Year {year}, Day {day}/3 | {day_progress:.0f}% through day | Tick {ticks}{paused_str}"
        self.tick_label.configure(text=tick_text)
    
    def _update_debug_stats(self):
        """Update the character stats display"""
        scroll_pos = self.debug_text.yview()
        
        lines = []
        header = f"{'Name':<18}{'Pos':<14}{'Zone':<12}{'Age':<5}{'HP':<6}{'Hunger':<7}{'Inventory':<28}{'Home':<10}{'Job':<10}{'Status/Intent':<16}"
        lines.append(header)
        lines.append("=" * 150)
        
        for char in self.snapshot['characters']:
            name = char['name']
            zone = char.get('zone')
            
            # Show position based on zone
            if zone:
                # In interior - show local (interior) coords
                pos = f"L({char['prevailing_x']:.1f},{char['prevailing_y']:.1f})"
                zone_display = zone[:10] if len(zone) > 10 else zone
            else:
                # Exterior - show world position
                pos = f"({char['x']:.1f},{char['y']:.1f})"
                zone_display = "exterior"
            
            home = char.get('home', '-') or '-'
            job = char.get('job', '-') or '-'
            
            # Build inventory display
            inv_parts = []
            for slot in char['inventory']:
                if slot is None:
                    inv_parts.append('-')
                elif slot['type'] == 'money':
                    inv_parts.append(f"${slot['amount']}")
                else:
                    inv_parts.append(f"{slot['type'][:3]}{slot['amount']}")
            inv_display = '|'.join(inv_parts)
            
            # Status display - use pre-computed values from snapshot
            status = ""
            known_crimes = char.get('known_crimes_count', 0)
            is_murderer = char.get('is_murderer', False)
            is_thief = char.get('is_thief', False)
            intent = char.get('intent')
            
            if char.get('is_frozen', False):
                status = "FROZEN"
            elif char.get('is_starving', False):
                status = "STARVING"
            elif is_murderer:
                status = "MURDERER"
            elif is_thief:
                status = "THIEF"
            elif intent:
                action = intent.get('action', '?')
                target = intent.get('target', '?')
                # Truncate target name for display
                target_short = target[:8] if target and len(target) > 8 else target
                status = f"{action}->{target_short}"
            elif known_crimes > 0:
                status = f"knows:{known_crimes}"
            else:
                status = "-"
            
            hunger_display = f"{char['hunger']:.0f}"
            
            line = f"{name:<18}{pos:<14}{zone_display:<12}{char['age']:<5}{char['health']:<6}{hunger_display:<7}{inv_display:<28}{home:<10}{job:<10}{status:<16}"
            lines.append(line)
        
        # Barrels section
        lines.append("")
        lines.append("=" * 80)
        lines.append("BARRELS")
        lines.append("-" * 80)
        
        for pos, barrel in self.snapshot['barrels'].items():
            barrel_name = barrel['name']
            barrel_pos = f"({pos[0]},{pos[1]})"
            barrel_home = barrel['home']
            barrel_owner = barrel['owner'] if barrel['owner'] else "(unowned)"
            
            # Calculate barrel contents
            barrel_wheat = 0
            barrel_money = 0
            used_slots = 0
            for slot in barrel['inventory']:
                if slot is not None:
                    used_slots += 1
                    if slot['type'] == 'wheat':
                        barrel_wheat += slot['amount']
                    elif slot['type'] == 'money':
                        barrel_money += slot['amount']
            total_slots = len(barrel['inventory'])
            
            line = f"{barrel_name:<20} Pos:{barrel_pos:<10} Home:{barrel_home:<10} Owner:{barrel_owner:<18} Wheat:{barrel_wheat:<5} ${barrel_money:<5} Slots:{used_slots}/{total_slots}"
            lines.append(line)
        
        # Beds section
        lines.append("")
        lines.append("=" * 80)
        lines.append("BEDS")
        lines.append("-" * 80)
        
        for pos, bed in self.snapshot['beds'].items():
            bed_name = bed['name']
            bed_pos = f"({pos[0]},{pos[1]})"
            bed_home = bed['home']
            bed_owner = bed['owner'] if bed['owner'] else "(unowned)"
            line = f"{bed_name:<20} Pos:{bed_pos:<10} Home:{bed_home:<10} Owner:{bed_owner:<18}"
            lines.append(line)
        
        # Camps section
        camps = [(char['name'], char['camp_position']) for char in self.snapshot['characters'] if char.get('camp_position')]
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
        for char in self.snapshot['characters']:
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
        
        # Memories & Intents section
        chars_with_memories_or_intents = []
        for char in self.snapshot['characters']:
            memories = char.get('memories', [])
            intent = char.get('intent')
            if memories or intent:
                chars_with_memories_or_intents.append((char['name'], memories, intent, char.get('facing', 'down')))
        
        if chars_with_memories_or_intents:
            lines.append("")
            lines.append("=" * 120)
            lines.append("MEMORIES & INTENTS")
            lines.append("=" * 120)
            
            for char_name, memories, intent, facing in chars_with_memories_or_intents:
                lines.append("")
                lines.append(f">>> {char_name} (facing: {facing}) <<<")
                
                # Show intent prominently
                if intent:
                    action = intent.get('action', '?')
                    target = intent.get('target', '?')
                    reason = intent.get('reason', '?')
                    started = intent.get('started_tick', '?')
                    lines.append(f"    INTENT: [{action.upper()}] target={target}, reason={reason}, started=T{started}")
                
                # Show memories in a table format
                if memories:
                    lines.append(f"    MEMORIES ({len(memories)} total):")
                    lines.append(f"    {'Type':<16} {'Subject':<18} {'Tick':<8} {'Source':<12} {'Details':<40}")
                    lines.append(f"    {'-'*14:<16} {'-'*16:<18} {'-'*6:<8} {'-'*10:<12} {'-'*38:<40}")
                    
                    # Show all memories (or limit to last 10 per type if too many)
                    for m in memories[-15:]:  # Show last 15 memories
                        mtype = m.get('type', '?')
                        subject = m.get('subject', '?')
                        # Truncate subject name
                        if len(str(subject)) > 16:
                            subject = str(subject)[:14] + '..'
                        tick = m.get('tick', '?')
                        source = m.get('source', '?')
                        
                        # Build details string
                        details_parts = []
                        if m.get('crime_type'):
                            details_parts.append(f"{m['crime_type']}")
                        if m.get('victim'):
                            victim_name = m['victim']
                            if len(str(victim_name)) > 12:
                                victim_name = str(victim_name)[:10] + '..'
                            details_parts.append(f"vic:{victim_name}")
                        if m.get('reported') is True:
                            details_parts.append("REPORTED")
                        elif m.get('reported') is False and mtype in ('crime', 'attacked_by'):
                            details_parts.append("unreported")
                        
                        details_str = ', '.join(details_parts) if details_parts else '-'
                        
                        lines.append(f"    {mtype:<16} {subject:<18} T{tick:<6} {source:<12} {details_str}")
                    
                    if len(memories) > 15:
                        lines.append(f"    ... and {len(memories) - 15} older memories")
        
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
        current_total = self.snapshot.get('log_total_count', 0)
        current_log = self.snapshot.get('action_log', [])
        current_len = len(current_log)
        
        if current_total != self._last_log_total:
            self.log_text.configure(state=tk.NORMAL)
            
            if current_total == 0:
                self.log_text.delete('1.0', tk.END)
            elif current_total > self._last_log_total:
                new_count = current_total - self._last_log_total
                new_entries = current_log[-new_count:] if new_count <= current_len else current_log
                
                for entry in new_entries:
                    self.log_text.insert(tk.END, entry + '\n')
                
                # Trim display if too long
                line_count = int(self.log_text.index('end-1c').split('.')[0])
                if line_count > 1000:
                    self.log_text.delete('1.0', f'{line_count - 1000}.0')
            else:
                self.log_text.delete('1.0', tk.END)
                for entry in current_log:
                    self.log_text.insert(tk.END, entry + '\n')
            
            self.log_text.configure(state=tk.DISABLED)
            self._last_log_total = current_total
            
            if self.auto_scroll_var.get():
                self.log_text.see(tk.END)
    
    def run(self):
        """Run the tkinter main loop"""
        self.root.mainloop()


# Backwards compatibility: alias for existing code
DebugWindow = DebugWindowProcess