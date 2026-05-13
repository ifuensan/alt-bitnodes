"""Small pure helpers shared across the data layer."""

from functools import lru_cache

import pycountry


@lru_cache(maxsize=512)
def iso2_to_iso3(code: str) -> str | None:
    if not code:
        return None
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None
