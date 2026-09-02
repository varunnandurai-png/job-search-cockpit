"""Strict matching between profile locations and provider-supplied location labels."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence


def listing_supports_profile_location(
    profile_location: str, listing_locations: Iterable[object]
) -> bool:
    """Return whether a provider location label contains an exact profile location component."""
    expected = _normalise(profile_location)
    if not expected:
        return False
    return any(
        expected == _normalise(component)
        for location in listing_locations
        for component in re.split(r"[,;/|]", str(location))
    )


def select_profile_location(
    listing_locations: Iterable[object], profile_locations: Sequence[str]
) -> str | None:
    """Choose the first approved profile location represented by a provider label."""
    locations = tuple(listing_locations)
    return next(
        (
            profile_location
            for profile_location in profile_locations
            if listing_supports_profile_location(profile_location, locations)
        ),
        None,
    )


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_marks.casefold()).strip()
