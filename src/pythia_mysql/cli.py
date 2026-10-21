"""The `pythia-mysql` command: pythia-core's command line, handed this engine."""
from pythia_core import cli

from .engine import MySqlEngine


def main(argv=None):
    return cli.main(MySqlEngine(), argv)
