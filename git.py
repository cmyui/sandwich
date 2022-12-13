from __future__ import annotations

import fnmatch
import os
import tempfile
from collections.abc import Iterator
from collections.abc import Sequence


def find_files(directory: str, patterns: Sequence[str]) -> Iterator[str]:
    for root, dirs, files in os.walk(directory):
        for basename in files:
            if any([fnmatch.fnmatch(basename, pattern) for pattern in patterns]):
                filename = os.path.join(root, basename)
                yield filename


def clone_repository(repository_url: str, target_dir: str) -> int:
    return os.system(f"git clone --quiet {repository_url} {target_dir}")
