"""pythia for MySQL: stored-program development for AI agents, over
pythia-core. Alpha — see README.md for what works today."""
__version__ = "0.1.0.dev0"     # kept equal to pyproject.toml (tests/test_mysql.py)

from .engine import MySqlEngine  # noqa: E402,F401 — needs __version__ first
