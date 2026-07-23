#!/usr/bin/env python3
"""
KTS Backend CLI Entry Point for PyInstaller
This module serves as the entry point for the PyInstaller-built executable.
It invokes the same CLI module used by the venv-based execution (Option A1).
"""

import sys
import os

# Handle PyInstaller's frozen state
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    bundle_dir = sys._MEIPASS
    # Add bundle dir to path so imports work
    sys.path.insert(0, bundle_dir)
else:
    # Running in normal Python environment
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    # Add parent directory to path for imports
    sys.path.insert(0, os.path.dirname(bundle_dir))

# Import and invoke the CLI module (Click-based)
from cli.main import cli


def _main():
    # ABS Waterfall IPC server mode (used by the VS Code WebView app):
    #   abs-backend abs-serve --deals-root <path>
    if len(sys.argv) > 1 and sys.argv[1] == 'abs-serve':
        from backend.abs.serve import main as abs_serve_main
        return abs_serve_main(sys.argv[2:])
    return cli()


if __name__ == '__main__':
    sys.exit(_main())
