from __future__ import annotations

import re

from .models import ReleaseLevel


_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_version(value: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"unsupported SemVer value: {value!r}")
    return tuple(int(item) for item in match.groups())  # type: ignore[return-value]


def next_version(current: str, level: ReleaseLevel) -> str:
    major, minor, patch = parse_version(current)
    if level is ReleaseLevel.MAJOR:
        return f"{major + 1}.0.0"
    if level is ReleaseLevel.MINOR:
        return f"{major}.{minor + 1}.0"
    if level is ReleaseLevel.PATCH:
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unsupported release level: {level!r}")


def max_level(levels: list[ReleaseLevel]) -> ReleaseLevel:
    if not levels:
        raise ValueError("at least one release level is required")
    order = {
        ReleaseLevel.PATCH: 1,
        ReleaseLevel.MINOR: 2,
        ReleaseLevel.MAJOR: 3,
    }
    return max(levels, key=order.__getitem__)
