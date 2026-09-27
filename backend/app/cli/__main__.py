"""Lets the CLI run as `python -m app.cli`; the implementation is in app/cli/main.py."""

import sys

from app.cli.main import main

sys.exit(main(sys.argv[1:]))
