"""Safe writing: an existing output is never overwritten.

Before a script writes a file, keep(path) moves any existing file of that name into <folder>/_archive/<timestamp>/,
so every earlier version stays on disk. Original data (downloads, registers, raw exports) is never written by the
pipelines at all; this protects the derived outputs as well. The archives can be cleared by hand when no longer
needed.
"""
import datetime, pathlib, shutil

_RUN = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")      # one archive folder per run of a script


def keep(path):
    """Move an existing file at `path` to <folder>/_archive/<run time>/ and return `path` (now free to write)."""
    p = pathlib.Path(path)
    if p.exists():
        dest = p.parent / "_archive" / _RUN / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        n = 1
        while dest.exists():                                    # same file written twice in one run
            dest = dest.with_name(f"{p.stem}__{n}{p.suffix}"); n += 1
        shutil.move(str(p), str(dest))
    return p
