"""Small pure helpers shared across the data layer."""

from functools import lru_cache

import pycountry


def classify_network(address: str) -> str:
    """Network class of a node address: ipv4 / ipv6 / tor / i2p."""
    if address.endswith(".onion"):
        return "tor"
    if address.endswith(".b32.i2p"):
        return "i2p"
    if ":" in address:
        return "ipv6"
    return "ipv4"


@lru_cache(maxsize=512)
def iso2_to_iso3(code: str) -> str | None:
    if not code:
        return None
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None
