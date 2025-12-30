# main.py - Entry point for the village simulation game

# IMPORTANT: Set multiprocessing start method BEFORE any other imports
# This is required on macOS to avoid pygame/tkinter conflicts
import multiprocessing
import sys
if sys.platform == 'darwin':
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        pass  # Already set

from gui import BoardGUI


def main():
    app = BoardGUI()
    app.run()


if __name__ == "__main__":
    main()


# git push https://farshad-csd@github.com/farshad-csd/MedievalGame.git main
# git push https://farshad-csd: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@github.com/farshad-csd/MedievalGame.git main