import os
import msvcrt

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
    
    # Ask the user if they want to digit index manually or scroll
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"=== {title} ===")
    print("Choose selection method:")
    print("1. Scroll/Navigate with keyboard arrows")
    print("2. Type/Digit the index number directly")
    choice = ""
    while choice not in ["1", "2"]:
        k = msvcrt.getch()
        if k == b'1':
            choice = "1"
        elif k == b'2':
            choice = "2"
        elif k == b'\x1b': # ESC
            print("\nExiting program...")
            exit(0)
            
    if choice == "2":
        # Digit mode
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"=== {title} ===")
            for idx, opt in enumerate(display_options, start=1):
                print(f"{idx:3d}. {opt}")
            print(f"\nEnter the number (1 to {options_count}) or type 'exit' to quit:")
            typed = input("> ").strip()
            if typed.lower() == 'exit':
                print("\nExiting program...")
                exit(0)
            try:
                num = int(typed) - 1
                if 0 <= num < options_count:
                    if show_exit and num == options_count - 1:
                        print("\nExiting program...")
                        exit(0)
                    return num
            except ValueError:
                pass
            print("Invalid index. Press any key to retry...")
            msvcrt.getch()
            
    # Scroll Mode
    selected = 0
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=====================================================================")
        print(" [ESC] Exit  |  [F] Find/Type index directly  |  [C] Display all content ")
        print("=====================================================================")
        print(f"\n=== {title} ===")
        print("(Use UP/DOWN arrows to navigate, SPACE or ENTER to select.)\n")
        
        start_idx = max(0, selected - 5)
        end_idx = min(options_count, selected + 6)
        
        if selected - 5 < 0:
            end_idx = min(options_count, 11)
        if selected + 6 > options_count:
            start_idx = max(0, options_count - 11)
        
        if start_idx > 0:
            print("   ... (more options above) ...")
            
        for i in range(start_idx, end_idx):
            opt = display_options[i]
            if i == selected:
                print(f" > [x] {i + 1:3d}. {opt}")
            else:
                print(f"   [ ] {i + 1:3d}. {opt}")
                
        if end_idx < options_count:
            print("   ... (more options below) ...")
        
        key = msvcrt.getch()
        
        # Key Bindings & Shortcuts
        if key == b'\x1b': # ESC
            print("\nExiting program...")
            exit(0)
        elif key == b'\x03': # Ctrl+C
            print("\nOperation cancelled.")
            exit(0)
        elif key == b'f' or key == b'F': # F shortcut - switch to typing mode
            while True:
                print(f"\nEnter the number (1 to {options_count}) to select: ")
                typed = input("> ").strip()
                try:
                    num = int(typed) - 1
                    if 0 <= num < options_count:
                        if show_exit and num == options_count - 1:
                            print("\nExiting program...")
                            exit(0)
                        return num
                except ValueError:
                    pass
                print("Invalid index. Try again.")
        elif key == b'c' or key == b'C': # C shortcut - display all content
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"=== {title} (Full List) ===")
            for idx, opt in enumerate(display_options, start=1):
                print(f"{idx:3d}. {opt}")
            print("\nPress any key to return to navigation...")
            msvcrt.getch()
        elif key == b'\r' or key == b' ': # Enter or Space
            if show_exit and selected == options_count - 1:
                print("\nExiting program...")
                exit(0)
            return selected
        elif key == b'\xe0': # Special key (arrows)
            arrow = msvcrt.getch()
            if arrow == b'H': # UP arrow
                selected = (selected - 1) % options_count
            elif arrow == b'P': # DOWN arrow
                selected = (selected + 1) % options_count
