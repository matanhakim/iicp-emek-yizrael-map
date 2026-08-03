"""Open Location Code (Google Plus Code) decoding, offline and deterministic.

The institute's field inventory recorded a Plus Code for 115 of its 184 Emek Yizrael rows but
a latitude and longitude for only 34, so most culture institutions had no position and never
reached the map. A Plus Code is not an opaque identifier that needs a geocoding service: it is
a base-20 encoding of the coordinate itself, so it can be decoded exactly, with no API, no
network and no rate limit.

Short codes such as 'P4CV+H3' drop the leading four characters and are only meaningful next to
a reference location. The settlement centroid supplies that reference, which is safe because
the dropped prefix spans a full degree, about 111 km, and the settlements of one regional
council are nowhere near that far apart.

Spec: https://github.com/google/open-location-code/blob/main/docs/specification.md
Correctness here is not asserted, it is measured: src/test_plus_code.py decodes the 27 rows
that carry BOTH a Plus Code and a coordinate and checks the decoded position against theirs.
"""

from __future__ import annotations

ALPHABET = "23456789CFGHJMPQRVWX"
SEPARATOR = "+"
SEPARATOR_POSITION = 8
PADDING = "0"
PAIR_CODE_LENGTH = 10
GRID_ROWS = 5
GRID_COLUMNS = 4
LAT_MAX = 90.0
LON_MAX = 180.0


class PlusCodeError(ValueError):
    pass


def is_valid(code: str) -> bool:
    if not code or SEPARATOR not in code:
        return False
    if code.count(SEPARATOR) > 1:
        return False
    i = code.index(SEPARATOR)
    if i > SEPARATOR_POSITION or i % 2 == 1:
        return False
    body = code.replace(SEPARATOR, "").upper()
    if not body:
        return False
    return all(c in ALPHABET or c == PADDING for c in body)


def encode(latitude: float, longitude: float, code_length: int = PAIR_CODE_LENGTH) -> str:
    """Encode a coordinate. Only needed to build the prefix when recovering a short code."""
    code_length = min(max(code_length, 2), PAIR_CODE_LENGTH)
    if code_length % 2:
        code_length -= 1
    lat = min(LAT_MAX, max(-LAT_MAX, latitude))
    lon = ((longitude + LON_MAX) % (2 * LON_MAX)) - LON_MAX
    if lat >= LAT_MAX:
        lat = LAT_MAX - 1e-9

    code = ""
    adj_lat, adj_lon = lat + LAT_MAX, lon + LON_MAX
    lat_res = lon_res = 20.0
    for _ in range(code_length // 2):
        d_lat = int(adj_lat // lat_res)
        d_lon = int(adj_lon // lon_res)
        d_lat = min(d_lat, len(ALPHABET) - 1)
        d_lon = min(d_lon, len(ALPHABET) - 1)
        adj_lat -= d_lat * lat_res
        adj_lon -= d_lon * lon_res
        code += ALPHABET[d_lat] + ALPHABET[d_lon]
        lat_res /= 20.0
        lon_res /= 20.0
    if len(code) > SEPARATOR_POSITION:
        return code[:SEPARATOR_POSITION] + SEPARATOR + code[SEPARATOR_POSITION:]
    return code.ljust(SEPARATOR_POSITION, PADDING) + SEPARATOR


def decode(code: str) -> tuple[float, float, float, float]:
    """Decode a FULL code. Returns (lat_lo, lon_lo, lat_hi, lon_hi) of the cell."""
    if not is_valid(code):
        raise PlusCodeError(f"not a plus code: {code!r}")
    body = code.replace(SEPARATOR, "").upper().rstrip(PADDING)
    if len(body) < 2:
        raise PlusCodeError(f"too short to decode: {code!r}")

    lat, lon = -LAT_MAX, -LON_MAX
    lat_res = lon_res = 20.0
    pair_digits = min(len(body), PAIR_CODE_LENGTH)
    if pair_digits % 2:
        pair_digits -= 1
    for i in range(0, pair_digits, 2):
        lat += ALPHABET.index(body[i]) * lat_res
        lon += ALPHABET.index(body[i + 1]) * lon_res
        if i + 2 < pair_digits:
            lat_res /= 20.0
            lon_res /= 20.0

    # Digits beyond the tenth refine within the cell on a 5-by-4 grid rather than in pairs.
    if len(body) > PAIR_CODE_LENGTH:
        for i in range(PAIR_CODE_LENGTH, min(len(body), 15)):
            d = ALPHABET.index(body[i])
            lat_res /= GRID_ROWS
            lon_res /= GRID_COLUMNS
            lat += (d // GRID_COLUMNS) * lat_res
            lon += (d % GRID_COLUMNS) * lon_res

    return lat, lon, lat + lat_res, lon + lon_res


def center(code: str) -> tuple[float, float]:
    lat_lo, lon_lo, lat_hi, lon_hi = decode(code)
    return (lat_lo + lat_hi) / 2.0, (lon_lo + lon_hi) / 2.0


def recover(code: str, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Resolve a short code against a reference point and return its centre (lat, lon)."""
    code = (code or "").strip().upper()
    if SEPARATOR not in code:
        raise PlusCodeError(f"no separator in {code!r}")
    sep = code.index(SEPARATOR)
    if sep == SEPARATOR_POSITION:
        return center(code)                      # already a full code

    pad = SEPARATOR_POSITION - sep
    if pad % 2:
        raise PlusCodeError(f"odd short-code prefix length in {code!r}")
    resolution = 20.0 ** (2 - pad / 2)
    half = resolution / 2.0

    full = encode(ref_lat, ref_lon)[:pad] + code
    lat_c, lon_c = center(full)

    # The prefix taken from the reference can land the cell one step away from the reference
    # when the reference sits near a cell edge, so step back toward it.
    if ref_lat + half < lat_c and lat_c - resolution >= -LAT_MAX:
        lat_c -= resolution
    elif ref_lat - half > lat_c and lat_c + resolution <= LAT_MAX:
        lat_c += resolution
    if ref_lon + half < lon_c:
        lon_c -= resolution
    elif ref_lon - half > lon_c:
        lon_c += resolution
    return round(lat_c, 7), round(lon_c, 7)


def parse(raw: str) -> str | None:
    """Pull the code out of a messy cell such as 'P4CV+H3 Alonim' or 'M8GJ+JV איכסאל, ישראל'."""
    if not raw:
        return None
    for tok in str(raw).replace(",", " ").split():
        t = tok.strip().upper()
        if SEPARATOR in t and is_valid(t):
            return t
    return None
