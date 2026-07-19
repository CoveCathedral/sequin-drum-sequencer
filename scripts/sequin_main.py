"""PyInstaller entry point for the frozen Sequin build (see ../Sequin.spec).

Kept separate from ``sequin/__main__.py`` so the build has a concrete script path to analyze;
it does nothing but hand off to the same ``main()`` that ``python -m sequin`` calls.
"""

from sequin.app import main

if __name__ == "__main__":
    main()
