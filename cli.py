import os
import sys

try:
    import msvcrt
    def getch():
        return msvcrt.getch()
except ImportError:
    import select
    import termios
    import tty
    
    _getch_buffer = []
    
    def getch():
        global _getch_buffer
        if _getch_buffer:
            return _getch_buffer.pop(0)
        
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            # Read up to 10 bytes from stdin
            data = os.read(fd, 10)
            if not data:
                return b''
            
            if data.startswith(b'\x1b') and len(data) > 1:
                seq = data[1:]
                if seq in (b'[A', b'OA'):  # UP arrow
                    _getch_buffer.append(b'H')
                    return b'\xe0'
                elif seq in (b'[B', b'OB'):  # DOWN arrow
                    _getch_buffer.append(b'P')
                    return b'\xe0'
                elif seq in (b'[D', b'OD'):  # LEFT arrow
                    _getch_buffer.append(b'K')
                    return b'\xe0'
                elif seq in (b'[C', b'OC'):  # RIGHT arrow
                    _getch_buffer.append(b'M')
                    return b'\xe0'
                
                # Buffer any leftover bytes from other escape sequences
                for b in seq:
                    _getch_buffer.append(bytes([b]))
                return b'\x1b'
            
            ch = data[0]
            if ch == 0x7f:  # Backspace on Unix
                return b'\x08'
            elif ch == 0x0a or ch == 0x0d:
                return b'\r'
            return bytes([ch])
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def select_item_cli(options, title="Select an option:", show_exit=True):
    """
    Interactively select an option using keyboard arrow keys or shortcuts.
    Displays dynamic pagination and shortcut indicators on top of the screen.
    Allows selection by arrow navigation or direct index input.
    """
    display_options = list(options)
    if show_exit:
        display_options.append("Exit / Cancel")
        
    options_count = len(display_options)
    
    # Scroll Mode
    selected = 0
    display_all = False
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\033[94m=====================================================================\033[0m")
        print(" [ESC] Exit  |  [LEFT ARROW] Go Back  |  [C] " + ("Show paginated list" if display_all else "Show full list"))
        print("\033[94m=====================================================================\033[0m")
        print(f"\n=== {title} ===")
        print("(Use UP/DOWN arrows to navigate, SPACE or ENTER to select.)\n")
        
        if display_all:
            start_idx = 0
            end_idx = options_count
        else:
            start_idx = max(0, selected - 5)
            end_idx = min(options_count, selected + 6)
            
            if selected - 5 < 0:
                end_idx = min(options_count, 11)
            if selected + 6 > options_count:
                start_idx = max(0, options_count - 11)
        
        if not display_all and start_idx > 0:
            print("   ... (more options above) ...")
            
        for i in range(start_idx, end_idx):
            opt = display_options[i]
            if i == selected:
                print(f"\033[33m > [x] {i + 1:3d}. {opt}\033[0m")
            else:
                print(f"   [ ] {i + 1:3d}. {opt}")
                
        if not display_all and end_idx < options_count:
            print("   ... (more options below) ...")
        
        key = getch()
        
        # Key Bindings & Shortcuts
        if key == b'\x1b': # ESC
            print("\nExiting program...")
            exit(0)
        elif key == b'\x03': # Ctrl+C
            print("\nOperation cancelled.")
            exit(0)
        elif key == b'c' or key == b'C': # C shortcut - toggle full list / paginated list
            display_all = not display_all
        elif key == b'\r' or key == b' ': # Enter or Space
            if show_exit and selected == options_count - 1:
                print("\nExiting program...")
                exit(0)
            return selected
        elif key == b'\xe0': # Special key (arrows)
            arrow = getch()
            if arrow == b'H': # UP arrow
                selected = (selected - 1) % options_count
            elif arrow == b'P': # DOWN arrow
                selected = (selected + 1) % options_count
            elif arrow == b'K': # LEFT arrow
                return -2
            elif arrow == b'M': # RIGHT arrow
                if show_exit and selected == options_count - 1:
                    print("\nExiting program...")
                    exit(0)
                return selected

def input_number_cli(prompt, min_val, max_val, title="Enter Range", options=None):
    """
    Reads a number character-by-character from standard console.
    Supports ESC to exit instantly, LEFT arrow to go back, and C to view list of options.
    """
    typed = ""
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\033[94m=====================================================================\033[0m")
        print(" [ESC] Exit  |  [LEFT ARROW] Go Back" + ("  |  [C] Display list" if options else ""))
        print("\033[94m=====================================================================\033[0m")
        print(f"\n=== {title} ===")
        print(prompt)
        print(f"> {typed}", end="", flush=True)
        
        key = getch()
        if key == b'\x1b':  # ESC
            print("\nExiting program...")
            exit(0)
        elif key == b'\x03':  # Ctrl+C
            print("\nOperation cancelled.")
            exit(0)
        elif key == b'c' or key == b'C':  # C shortcut
            if options:
                sel_idx = select_item_cli(options, title=title, show_exit=False)
                if sel_idx >= 0:
                    return sel_idx + 1  # Return 1-based index
                elif sel_idx == -2:
                    continue
        elif key == b'\r':  # ENTER
            if typed:
                try:
                    num = int(typed)
                    if min_val <= num <= max_val:
                        return num
                except ValueError:
                    pass
            typed = ""  # Reset if invalid
        elif key == b'\x08':  # Backspace
            typed = typed[:-1]
        elif key == b'\xe0':  # Special key
            arrow = getch()
            if arrow == b'K':  # LEFT arrow
                return -2
        else:
            try:
                char = key.decode('utf-8')
                if char.isdigit():
                    typed += char
            except UnicodeDecodeError:
                pass
