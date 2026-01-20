# main.py - Entry point for the village simulation game

import sys
import multiprocessing

# Set multiprocessing start method BEFORE any other imports (for macOS)
if sys.platform == 'darwin':
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        pass  # Already set

from ui.gui import BoardGUI


def main():
    app = BoardGUI()
    app.run()


if __name__ == "__main__":
    main()
