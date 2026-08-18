"""Probe a Python interpreter for the xray-import skill.

Run this script under each candidate interpreter name (python3, then python,
then py) until one prints a line beginning "PYCHECK ok". That line is the proof
the name is a working interpreter here; a name that prints no such line is not
usable, so the caller moves to the next. The line also reports the version,
whether it meets the minimum the parser needs, and whether xlrd is installed
for legacy .xls parsing.

The script is deliberately written in the common subset of Python 2 and 3, with
no f-strings or other version-specific syntax, so that even a too-old
interpreter still runs it and reports "min_ok=no" rather than failing to parse
and looking absent.
"""

import sys

# The parser relies on standard-library features present from this version on.
MIN_VERSION = (3, 8)


def main():
    version = ".".join(str(part) for part in sys.version_info[:3])
    minimum = "{0}.{1}".format(MIN_VERSION[0], MIN_VERSION[1])
    min_ok = "yes" if sys.version_info[:2] >= MIN_VERSION else "no"

    # Importing is the surest test; xlrd is optional, so its absence is fine.
    try:
        import xlrd  # noqa: F401
        xlrd_state = "present"
    except ImportError:
        xlrd_state = "absent"

    print("PYCHECK ok python={0} min={1} min_ok={2} xlrd={3}".format(
        version, minimum, min_ok, xlrd_state))


if __name__ == "__main__":
    main()
