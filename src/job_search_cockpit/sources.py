import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from job_search_cockpit.config import SourceSpec


class UnsafeSourceError(ValueError):
    """Raised when a curated source is not an ordinary, unchanged file."""


@dataclass(frozen=True, slots=True)
class OpenedSource:
    spec: SourceSpec
    content: bytes
    content_hash: str
    device: int
    inode: int
    size: int
    modified_ns: int


def _reject_symlink_components(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise UnsafeSourceError(f"Source path contains a symbolic link: {path}")


def safe_open_source(spec: SourceSpec) -> OpenedSource:
    path = spec.path.absolute()
    _reject_symlink_components(path)
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise UnsafeSourceError(f"Source cannot be opened safely: {path}") from error
    if not stat.S_ISREG(path_stat.st_mode):
        raise UnsafeSourceError(f"Source is not a regular file: {path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise UnsafeSourceError(f"Source cannot be opened safely: {path}") from error

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise UnsafeSourceError(f"Source is not a regular file: {path}")
        if (before.st_dev, before.st_ino) != (path_stat.st_dev, path_stat.st_ino):
            raise UnsafeSourceError(f"Source changed while being opened: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as source_file:
            content = source_file.read()
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise UnsafeSourceError(f"Source changed while being read: {path}")
    finally:
        os.close(descriptor)

    return OpenedSource(
        spec=spec,
        content=content,
        content_hash=sha256(content).hexdigest(),
        device=after.st_dev,
        inode=after.st_ino,
        size=after.st_size,
        modified_ns=after.st_mtime_ns,
    )
