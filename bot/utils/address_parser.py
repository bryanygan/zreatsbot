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

NOISE_LINES = {
    'new', 'unpaid', 'forwarded', 'unmarked', 'done', 'sent',
    'okay', 'okay!',
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _smart_title(s: str) -> str:
    """Title-case a string without capitalizing letters immediately after
    digits when they form ordinals (e.g. ``"18th"`` stays ``"18th"``).
    Standalone letters after digits like ``"15H"`` remain uppercase.
    """
    if not s:
        return s
    titled = s.title()
    # Only lowercase when the uppercase letter is followed by another
    # lowercase letter (ordinal like 18Th → 18th), not standalone like 15H.
    return re.sub(
        r'(\d)([A-Z])(?=[a-z])',
        lambda m: m.group(1) + m.group(2).lower(),
        titled,
    )


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


def _is_noise_line(line: str) -> bool:
    lower = line.lower().strip()
    if lower in NOISE_LINES:
        return True
    if lower.startswith('@'):
        return True
    if lower.startswith('done.') or lower.startswith('my address'):
        return True
    if lower.startswith('address:'):
        return True
    if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', lower):
        return True
    return False


def _is_standalone_zip(line: str) -> bool:
    return bool(re.match(r'^\d{5}(?:-\d{4})?\s*$', line.strip()))


def _has_zip_at_end(line: str) -> bool:
    return bool(re.search(r'\b\d{5}(?:-\d{4})?\s*$', line.strip()))


def _has_street_suffix(line: str) -> bool:
    for word in line.split():
        if word.lower().rstrip('.') in STREET_SUFFIXES:
            return True
    return False


def _extract_state_from_end(text: str):
    """Return ``(state_abbrev, remaining_text)`` or ``(None, text)``."""
    text = text.strip().rstrip(',').strip()
    words = text.split()
    if not words:
        return None, text

    last = words[-1].strip(',')

    # 2-letter abbreviation (also handles D.C. → DC)
    last_clean = last.replace('.', '')
    if len(last_clean) == 2 and last_clean.upper() in STATE_ABBREVS:
        remaining = ' '.join(words[:-1]).rstrip(',').strip()
        return last_clean.upper(), remaining

    # Single-word full state name
    if last.strip(',').lower() in STATE_MAP:
        remaining = ' '.join(words[:-1]).rstrip(',').strip()
        return STATE_MAP[last.strip(',').lower()], remaining

    # Two-word state name (e.g. New York, West Virginia, Rhode Island)
    if len(words) >= 2:
        two = f'{words[-2].strip(",")} {words[-1].strip(",")}'.lower()
        if two in STATE_MAP:
            remaining = ' '.join(words[:-2]).rstrip(',').strip()
            return STATE_MAP[two], remaining
        # Also check combined without periods (D. C. → DC)
        combined = two.replace('.', '').replace(' ', '')
        if len(combined) == 2 and combined.upper() in STATE_ABBREVS:
            remaining = ' '.join(words[:-2]).rstrip(',').strip()
            return combined.upper(), remaining

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

    if last_suffix_idx >= 0:
        # Absorb directionals that follow the suffix
        split_idx = last_suffix_idx + 1
        while split_idx < len(words) and words[split_idx].lower() in DIRECTIONALS:
            split_idx += 1
        street = ' '.join(words[:split_idx])
        city = ' '.join(words[split_idx:])
        return street, city

    # Fallback for grid addresses (e.g. "2109 N 150 W Anderson"):
    # if there are 2+ directionals, split after the last number/directional run.
    dir_indices = [i for i, w in enumerate(words) if w.lower() in DIRECTIONALS]
    if len(dir_indices) >= 2:
        last_dir = dir_indices[-1]
        split_idx = last_dir + 1
        if split_idx < len(words):
            street = ' '.join(words[:split_idx])
            city = ' '.join(words[split_idx:])
            return street, city

    return text, ''


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

    # 4. If "city" starts with an apt marker, extract street2
    street2 = ''
    if city:
        apt_m = re.match(
            r'((?:apt|apartment|suite|ste|unit)\.?\s*#?\s*\w+)\s*[,;]?\s*',
            city, re.IGNORECASE,
        )
        if apt_m:
            street2 = apt_m.group(1).strip()
            city = city[apt_m.end():].strip().lstrip(',').strip()

    if not city:
        return None

    return {
        'street': street, 'street2': street2,
        'city': city, 'state': state, 'zip': zip_code,
    }


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


def _parse_full_line_address(line: str):
    """Parse a line containing ``name, street, city, state, zip`` all inline.

    Used for lines like ``"Ryan Cu, 10661 La Dona Dr., Garden Grove, CA, 92840"``.
    Returns a dict or ``None``.
    """
    line = line.strip()

    # 1. Extract ZIP
    zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\s*$', line)
    if not zip_match:
        return None
    zip_code = zip_match.group(1)
    remaining = line[:zip_match.start()].strip().rstrip(',').strip()

    # 2. Extract state
    state, remaining = _extract_state_from_end(remaining)
    if not state:
        return None
    remaining = remaining.strip().rstrip(',').strip()

    # Strategy A: comma-separated parts — find the part that looks like a street
    parts = [p.strip() for p in remaining.split(',') if p.strip()]
    name = ''
    street = ''
    street2 = ''
    city = ''

    for i, part in enumerate(parts):
        if part and part[0].isdigit() and _has_street_suffix(part):
            name = ', '.join(parts[:i]).strip()
            street = part
            rest = [p.strip() for p in parts[i + 1:] if p.strip()]
            if rest and _is_street2_line(rest[0]):
                street2 = rest[0]
                rest = rest[1:]
            city = ', '.join(rest).strip()
            break

    # Strategy B: regex to find digit+suffix pattern in full text
    if not street:
        suffix_alts = '|'.join(
            re.escape(s) for s in sorted(STREET_SUFFIXES, key=len, reverse=True)
        )
        m = re.search(
            r'(\d+\s+(?:\S+\s+)*?(?:' + suffix_alts + r')\.?)\b',
            remaining, re.IGNORECASE,
        )
        if m:
            street = m.group(1).strip()
            name = remaining[:m.start()].strip().rstrip(',').strip()
            after = remaining[m.end():].strip().lstrip(',').strip()
            # Check for apt in the text after street
            if after:
                apt_m = re.match(
                    r'((?:apt|apartment|suite|ste|unit)\.?\s*#?\s*\w+)\s*[,;]?\s*',
                    after, re.IGNORECASE,
                )
                if apt_m:
                    street2 = apt_m.group(1).strip()
                    after = after[apt_m.end():].strip().lstrip(',').strip()
            city = after.strip().rstrip(',').strip()

    if not street or not city:
        return None

    return {
        'name': name, 'street': street, 'street2': street2,
        'city': city, 'state': state, 'zip': zip_code,
    }


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

    # ---- Preprocess lines ----
    lines = []
    for raw in text.splitlines():
        cleaned = raw.strip()
        if not cleaned:
            continue
        # Strip trailing punctuation that interferes with zip detection
        cleaned = cleaned.rstrip('.,;:').strip()
        # Normalize tight commas: "Clinton,MD" → "Clinton, MD"
        cleaned = re.sub(r',([A-Za-z])', r', \1', cleaned)
        # Normalize state glued to zip: "Louisiana70570" → "Louisiana 70570"
        cleaned = re.sub(r'([a-zA-Z])(\d{5}(?:-\d{4})?)\s*$', r'\1 \2', cleaned)
        if cleaned.lower() in COUNTRY_LINES:
            continue
        lines.append(cleaned)

    if not lines:
        return {'error': 'No address provided'}

    # ---- Single-pass classification ----
    name = ''
    street = ''
    street2 = ''
    city = ''
    state = ''
    zip_code = ''
    street_idx = -1
    unclassified = []          # [(line_index, text)]

    for i, line in enumerate(lines):
        # Skip noise / email / discord mention lines
        if _is_noise_line(line):
            continue

        # 1. Secondary address (apt / suite / unit / …)
        if _is_street2_line(line):
            if not street2:
                street2 = line
            continue

        # 2. Starts with a digit
        if line[0].isdigit():
            # 2a. Just a ZIP code on its own
            if _is_standalone_zip(line):
                if not zip_code:
                    zip_code = line.strip()
                continue

            # 2b. Try inline extraction (street + city/state/zip)
            inline = _extract_inline_address(line)
            if inline and not street:
                street = inline['street']
                city = inline['city']
                state = inline['state']
                zip_code = inline['zip']
                street_idx = i
                if inline.get('street2') and not street2:
                    street2 = inline['street2']
                continue

            # 2c. Plain street line
            if not street:
                # Check for embedded apt mid-line and split it out
                apt_m = re.search(
                    r'\b(apt\.?|apartment|suite|ste\.?|unit)\b',
                    line, re.IGNORECASE,
                )
                if apt_m and _has_street_suffix(line[:apt_m.start()]):
                    street = line[:apt_m.start()].strip()
                    if not street2:
                        street2 = line[apt_m.start():].strip()
                else:
                    street = line
                street_idx = i
            continue

        # 3. Ends with a ZIP → city/state/zip line (or full-line address)
        if _has_zip_at_end(line):
            if not city:
                # If we don't have a street yet, try full-line parse
                if not street:
                    full = _parse_full_line_address(line)
                    if full:
                        name = full.get('name', '') or name
                        street = full['street']
                        street_idx = i
                        street2 = full.get('street2', '') or street2
                        city = full['city']
                        state = full['state']
                        zip_code = full['zip']
                        continue
                csz = _parse_city_state_zip(line)
                if csz:
                    city = csz['city']
                    state = csz['state']
                    zip_code = csz['zip']
            continue

        # 4. Unclassified — save for post-processing
        unclassified.append((i, line))

    # ---- Post-processing ----

    # P1: Find state from unclassified lines (handles "TX" or "California" alone)
    if street and not state:
        for idx, (i, line) in enumerate(unclassified):
            stripped = line.strip().rstrip(',').strip()
            clean = stripped.replace('.', '')
            if len(clean) == 2 and clean.upper() in STATE_ABBREVS:
                state = clean.upper()
                unclassified.pop(idx)
                break
            if stripped.lower() in STATE_MAP:
                state = STATE_MAP[stripped.lower()]
                unclassified.pop(idx)
                break

    # P2: Find city/state from unclassified lines that end with a state
    if street and not state:
        for idx, (i, line) in enumerate(unclassified):
            st, remaining = _extract_state_from_end(line)
            if st:
                state = st
                ct = remaining.strip().rstrip(',').strip()
                if ct and not city:
                    city = ct
                unclassified.pop(idx)
                break

    # P3: Find city from unclassified lines positioned between street and state/zip
    if street and state and not city:
        for idx, (i, line) in enumerate(unclassified):
            if street_idx < i:
                # Candidate city line — accept short lines (1–4 words)
                words = line.split()
                if 1 <= len(words) <= 4:
                    city = line
                    unclassified.pop(idx)
                    break

    # P4: Extract city from street if still missing (street has suffix + trailing city)
    if not city and street:
        st, ct = _split_street_city(street)
        if st and ct:
            street = st
            city = ct

    # P5: Name from remaining unclassified
    if not name:
        for idx, (i, line) in enumerate(unclassified):
            name = line
            break

    # ---- Validate ----
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
