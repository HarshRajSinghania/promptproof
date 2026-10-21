"""Allow ``python -m promptproof`` in addition to the ``promptproof`` script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
