# tools

- `catalog-check.py` — the pin rules (`--help` lists them). Exit 0 = every rule holds.
- `catalog-pin.py` — moves an entry to a release tag, or prints a new entry, after checking the release.
- `install-drill.sh` — installs every entry from this checkout in a throwaway configuration directory.
- `catalog_lib.py` — shared helpers.

All four need Python 3.9 or later and `git`; the drill also needs the `claude` command line.
