"""Utility for parsing free-form US shipping addresses into structured components."""

import re


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_MAP = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY',
    'district of columbia': 'DC',
}

STATE_ABBREVS = set(STATE_MAP.values())

STREET_SUFFIXES = {
    'st', 'street', 'ave', 'avenue', 'blvd', 'boulevard', 'dr', 'drive',
    'ln', 'lane', 'rd', 'road', 'way', 'ct', 'court', 'pl', 'place',
    'cir', 'circle', 'trl', 'trail', 'pkwy', 'parkway', 'aly', 'alley',
    'ter', 'terrace', 'hwy', 'highway', 'loop', 'run', 'pass', 'pike',
}

STREET2_PREFIXES = {
    'apt', 'apartment', 'suite', 'ste', 'unit', 'floor', 'fl',
    'bldg', 'building', 'rm', 'room', 'dept', 'department',
    'lot', 'spc', 'space', 'box',
}

STREET2_TWO_WORD_PREFIXES = {'po box', 'p.o. box'}

COUNTRY_LINES = {
    'united states', 'us', 'usa',
    'united states of america', 'u.s.', 'u.s.a.',
}

DIRECTIONALS = {
    'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw',
    'north', 'south', 'east', 'west',
    'northeast', 'northwest', 'southeast', 'southwest',
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _smart_title(s: str) -> str:
    """Title-case a string without capitalizing letters immediately after digits.

    ``"18th"`` stays ``"18th"`` instead of ``"18Th"``.
    """
    if not s:
        return s
    titled = s.title()
    return re.sub(r'(\d)([A-Z])', lambda m: m.group(1) + m.group(2).lower(), titled)


def _is_street2_line(line: str) -> bool:
    lower = line.lower().strip()
    if not lower:
        return False
    if lower.startswith('#'):
        return True
    words = lower.split()
    if words[0] in STREET2_PREFIXES:
        return True
    if len(words) >= 2 and f'{words[0]} {words[1]}' in STREET2_TWO_WORD_PREFIXES:
        return True
    return False


def _has_zip_at_end(line: str) -> bool:
    return bool(re.search(r'\b\d{5}(?:-\d{4})?\s*$', line.strip()))


def _extract_state_from_end(text: str):
    """Return ``(state_abbrev, remaining_text)`` or ``(None, text)``."""
    text = text.strip().rstrip(',').strip()
    words = text.split()
    if not words:
        return None, text

    # 2-letter abbreviation
    last = words[-1].strip(',')
    if len(last) == 2 and last.upper() in STATE_ABBREVS:
        remaining = ' '.join(words[:-1]).rstrip(',').strip()
        return last.upper(), remaining

    # Single-word full state name
    if last.strip(',').lower() in STATE_MAP:
        remaining = ' '.join(words[:-1]).rstrip(',').strip()
        return STATE_MAP[last.strip(',').lower()], remaining

    # Two-word state name (e.g. New York, West Virginia)
    if len(words) >= 2:
        two = f'{words[-2].strip(",")} {words[-1].strip(",")}'.lower()
        if two in STATE_MAP:
            remaining = ' '.join(words[:-2]).rstrip(',').strip()
            return STATE_MAP[two], remaining

    # Three-word state name (District of Columbia)
    if len(words) >= 3:
        three = f'{words[-3].strip(",")} {words[-2].strip(",")} {words[-1].strip(",")}'.lower()
        if three in STATE_MAP:
            remaining = ' '.join(words[:-3]).rstrip(',').strip()
            return STATE_MAP[three], remaining

    return None, text


def _split_street_city(text: str):
    """Split ``"street part, city part"`` or ``"street part city part"`` into
    ``(street, city)`` using commas first, then street-suffix detection.
    """
    text = text.strip().rstrip(',').strip()

    # Comma present → split on the first comma
    if ',' in text:
        idx = text.index(',')
        before = text[:idx].strip()
        after = text[idx + 1:].strip()
        if before and after:
            return before, after

    # No comma → find the rightmost street suffix
    words = text.split()
    last_suffix_idx = -1
    for i, word in enumerate(words):
        if word.lower().rstrip('.') in STREET_SUFFIXES:
            last_suffix_idx = i

    if last_suffix_idx == -1:
        return text, ''

    # Absorb directionals that follow the suffix (e.g. "south" in "street south")
    split_idx = last_suffix_idx + 1
    while split_idx < len(words) and words[split_idx].lower() in DIRECTIONALS:
        split_idx += 1

    street = ' '.join(words[:split_idx])
    city = ' '.join(words[split_idx:])
    return street, city


def _extract_inline_address(line: str):
    """Try to extract street + city/state/zip from a single line that starts
    with a digit.  Returns a dict or ``None``.
    """
    line = line.strip()

    # 1. ZIP at the end
    zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\s*$', line)
    if not zip_match:
        return None
    zip_code = zip_match.group(1)
    remaining = line[:zip_match.start()].strip().rstrip(',').strip()

    # 2. State at the end of what's left
    state, remaining = _extract_state_from_end(remaining)
    if not state:
        return None
    remaining = remaining.strip().rstrip(',').strip()

    # 3. Street / city split
    street, city = _split_street_city(remaining)
    if not street or not city:
        return None

    return {'street': street, 'city': city, 'state': state, 'zip': zip_code}


def _parse_city_state_zip(line: str):
    """Parse a standalone ``"City, ST 12345"`` line."""
    line = line.strip()
    zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\s*$', line)
    if not zip_match:
        return None

    zip_code = zip_match.group(1)
    remaining = line[:zip_match.start()].strip().rstrip(',').strip()

    state, remaining = _extract_state_from_end(remaining)
    city = remaining.strip().rstrip(',').strip()

    return {'city': city, 'state': state or '', 'zip': zip_code}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_address(text: str) -> dict:
    """Parse a free-form US shipping address into structured components.

    Returns a dict with keys ``name``, ``street``, ``street2``, ``city``,
    ``state``, ``zip``.  Returns ``{"error": "..."}`` on failure.
    """
    if not text or not text.strip():
        return {'error': 'No address provided'}

    # Preprocess lines
    lines = []
    for raw in text.splitlines():
        cleaned = raw.strip()
        if cleaned and cleaned.lower() not in COUNTRY_LINES:
            lines.append(cleaned)

    if not lines:
        return {'error': 'No address provided'}

    name = ''
    street = ''
    street2 = ''
    city = ''
    state = ''
    zip_code = ''

    for line in lines:
        # 1. Secondary address (apt / suite / unit / …)
        if _is_street2_line(line):
            street2 = line
            continue

        # 2. Starts with a digit → street, possibly with inline city/state/zip
        if line[0].isdigit():
            inline = _extract_inline_address(line)
            if inline:
                street = inline['street']
                city = inline['city']
                state = inline['state']
                zip_code = inline['zip']
            else:
                street = line
            continue

        # 3. Ends with a ZIP → city/state/zip line
        if _has_zip_at_end(line):
            csz = _parse_city_state_zip(line)
            if csz:
                city = csz['city']
                state = csz['state']
                zip_code = csz['zip']
            continue

        # 4. Otherwise → name (first unclassified line)
        if not name:
            name = line

    if not street:
        return {'error': 'Could not parse address: no street found'}
    if not zip_code:
        return {'error': 'Could not parse address: no ZIP code found'}

    return {
        'name': _smart_title(name),
        'street': _smart_title(street),
        'street2': _smart_title(street2),
        'city': _smart_title(city),
        'state': state.upper() if state else '',
        'zip': zip_code,
    }


def format_address_csv(parsed: dict) -> str:
    """Format a parsed address as ``name,street,street2,city,state,zip``.

    Fields containing commas are wrapped in double quotes.
    """
    if 'error' in parsed:
        return parsed['error']

    fields = [
        parsed.get('name', ''),
        parsed.get('street', ''),
        parsed.get('street2', ''),
        parsed.get('city', ''),
        parsed.get('state', ''),
        parsed.get('zip', ''),
    ]
    return ','.join(f'"{f}"' if ',' in f else f for f in fields)


# ---------------------------------------------------------------------------
# Quick verification
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    examples = [
        # 1. Standard multi-line
        'Elijah Martir\n1863 Corner Meadow Circle\nOrlando, FL 32820',
        # 2. Comma-separated street + city/state/zip on one line
        'Joey Cusic\n334 American Avenue, Lexington, KY, 40503',
        # 3. With apartment line
        'Rowan Klein\n728 E 18th Aly\napt 1\nEugene, OR, 97401',
        # 4. Lowercase everything
        'marcelo torres\n13804 Trull Way\nHudson, Fl, 34669',
        # 5. Single line, no name, full state name
        '2211 7th street south Moorhead Minnesota 56560',
        # 6. With "United States" at the end
        'Pavel Hernandez\n17 Pecan blvd\nPittsburg, TX  75686\nUnited States',
        # 7. Street + city/state/zip inline (no comma between street and city)
        'Carlos Alas\n83 Jefferson St Inwood, NY 11096',
    ]

    for i, addr in enumerate(examples, 1):
        print(f'--- Example {i} ---')
        print(f'Input:\n{addr}\n')
        result = parse_address(addr)
        if 'error' in result:
            print(f'  ERROR: {result["error"]}')
        else:
            for key in ('name', 'street', 'street2', 'city', 'state', 'zip'):
                print(f'  {key:8s}: {result[key]}')
            print(f'  CSV     : {format_address_csv(result)}')
        print()
