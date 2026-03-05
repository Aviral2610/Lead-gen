"""Pytest configuration — ensures the project root is on sys.path so
all 'src.*' imports resolve correctly regardless of where pytest is invoked."""

import sys
from pathlib import Path

# Insert project root at the front of the import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
