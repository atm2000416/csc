"""
db/sync_from_dump.py
Sync the new CSC database from a fresh SQL dump of the legacy camp directory.

What this syncs:
  1. NEW camps          — cids in dump (status=1, with city) not present in new DB → INSERT
  2. RE-ACTIVATED       — cids status=0 in new DB, now status=1 in dump → UPDATE status=1
  3. DEACTIVATED        — cids status=1 in new DB, now status=0 in dump → UPDATE status=0
                          (requires --deactivate flag; only touches camps whose ID came from
                           the old DB, not manually-created location branches)
  NOTE: Uses status (field 6) as the activation criterion — the only active/inactive
        signal in the legacy schema. Field 17 (showAnalytics) was previously mislabelled
        as is_member; it defaults to 1 for almost all camps and is not a membership flag.
  4. SEED PROGRAMS      — for newly-active camps with no programs: create default program
                          and infer activity tags from dump session names (--seed-programs flag)
  4b. REFRESH PROGRAMS  — replace single generic placeholder programs (name=camp name)
                          with individual session records from the dump (--refresh-programs flag)
  4c. IMPORT ALL        — replace ALL programs for ALL active camps with dump sessions.
                          Covers every camp regardless of current program count. Camps with
                          no sessions in the dump are left untouched. (--import-all-sessions)
  5. METADATA           — tier/website changes for active camps (--update-meta flag)
  6. LOCATIONS          — new extra_locations not yet in new DB → INSERT
  7. PROGRAM DATES      — program_dates table refreshed from session_date in dump

What this does NOT touch:
  - activity_tags (curated in new DB)
  - Camps with no sessions in the dump (existing programs preserved)
  - Camps added manually in new DB (IDs not present in dump)

Usage:
  # Dry run — see what would change (always do this first)
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --dry-run

  # Standard sync: activate status=1 camps + new locations + program dates
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql

  # Seed programs/tags for newly-active camps that have none
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --seed-programs

  # Full sync with deactivations + metadata + seeded programs
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --deactivate --update-meta --seed-programs

  # Replace placeholder programs with real sessions (always dry-run first)
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --refresh-programs --dry-run
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --refresh-programs

  # Comprehensive: import ALL sessions for ALL active camps from the dump
  # (recommended after receiving a new dump — run dry-run first)
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --import-all-sessions --dry-run
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --import-all-sessions

  # Run only a specific section
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --only dates
"""
import re
import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

DEFAULT_DUMP = "/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260311.sql"

PROVINCE_MAP = {
    'ON': 'Ontario', 'On': 'Ontario', 'ont': 'Ontario', 'Ont': 'Ontario',
    'ontario': 'Ontario',
    'BC': 'British Columbia', 'B.C.': 'British Columbia',
    'AB': 'Alberta', 'Ab': 'Alberta',
    'QC': 'Quebec', 'Qc': 'Quebec', 'QuÃ©bec': 'Quebec',
    'MB': 'Manitoba', 'SK': 'Saskatchewan', 'NS': 'Nova Scotia',
    'NB': 'New Brunswick', 'NL': 'Newfoundland', 'PE': 'Prince Edward Island',
}

TIER_MAP = {
    'gold': 'gold', 'silver': 'silver', 'bronze': 'bronze',
    'double': 'silver',  # legacy tier name
    'single': 'bronze',
}


def normalise_province(p):
    p = (p or '').strip()
    return PROVINCE_MAP.get(p, p) if p else None


def normalise_city(c):
    return c.strip().title() if c else None


def slugify(text):
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


# ── Dump parsers ──────────────────────────────────────────────────────────────

def _extract_block(content, table):
    """Extract the VALUES block from an INSERT INTO `table` VALUES (...);
    Uses ';\\n' as the terminator — MySQL dumps end each statement with ';\\n'.
    Falls back to greedy match if not found.
    """
    # Primary: match up to semicolon at end of line
    match = re.search(
        rf'INSERT INTO `{table}` VALUES (.*?);\n',
        content, re.DOTALL
    )
    if match:
        return match.group(1)
    # Fallback: greedy to end of file section
    match = re.search(
        rf'INSERT INTO `{table}` VALUES (.*)',
        content, re.DOTALL
    )
    return match.group(1).rstrip(';\n') if match else None


def parse_camps(content):
    """
    Legacy schema (confirmed from CREATE TABLE in dump):
      (cid, camp_name, prefix, listingClass, eListingType, status,
       mod_date, location, Lat, Lon, weight, filename, usePretty,
       prettyURL, onlineonly, wentLive, showAnalytics, agate)

    Field 6  = status        — 1 if camp listing is active/live (THE activation signal)
    Field 17 = showAnalytics — defaults to 1 for almost all camps; NOT a membership flag

    NOTE: There is no is_member field in the legacy schema. Field 17 was previously
    mislabelled as is_member — it is showAnalytics and should not be used for activation.
    """
    block = _extract_block(content, 'camps')
    if not block:
        raise RuntimeError("camps INSERT not found in dump")

    rows = re.findall(
        r"\((\d+),'((?:[^'\\]|\\.)*)',('(?:[^'\\]|\\.)*'|NULL),'([^']*)',"
        r"'([^']*)',(\d+),'[^']*','[^']*','([^']*?)','([^']*?)',"
        r"\d+,'[^']*',\d+,'([^']*?)',\d+,'[^']*',\d+,\d+\)",
        block
    )
    result = {}
    for row in rows:
        cid, camp_name, _, listing_class, e_listing, status, lat, lon, prettyurl = row
        cid = int(cid)
        camp_name = camp_name.replace("\\'", "'")
        tier = TIER_MAP.get(e_listing, 'bronze')
        try:
            lat_f = float(lat) if lat and lat != '0' else None
            lon_f = float(lon) if lon and lon != '0' else None
        except ValueError:
            lat_f = lon_f = None
        result[cid] = {
            'cid': cid,
            'camp_name': camp_name,
            'tier': tier,
            'status': int(status),
            'lat': lat_f,
            'lon': lon_f,
            'prettyurl': prettyurl or None,
        }
    return result


def parse_addresses(content):
    """
    Old schema: (cid, address, city, province, postal, country, ...)
    Returns dict: {cid: {city, province, postal, address}}
    """
    block = _extract_block(content, 'addresses')
    if not block:
        return {}

    rows = re.findall(
        r"\((\d+),'((?:[^'\\]|\\.)*?)','((?:[^'\\]|\\.)*?)','((?:[^'\\]|\\.)*?)',"
        r"'((?:[^'\\]|\\.)*?)',(\d+)",
        block
    )
    result = {}
    for row in rows:
        cid, address, city, province, postal, _ = row
        cid = int(cid)
        result[cid] = {
            'city': normalise_city(city),
            'province': normalise_province(province),
            'postal': postal.strip(),
            'address': address.strip().replace("\\'", "'"),
        }
    return result


def parse_general_info(content):
    """
    Old schema: (cid, website, director_name|NULL, category, description, ...)
    director_name may be NULL or a quoted string.
    Returns dict: {cid: {website}}
    """
    block = _extract_block(content, 'generalInfo')
    if not block:
        return {}

    # Match: (cid, 'website', NULL|'director',  -> grab cid + website
    # Websites don't contain single quotes so [^']* is safe here
    rows = re.findall(
        r"\((\d+),'([^']*)',(?:NULL|'[^']*'),",
        block
    )
    result = {}
    for cid, website in rows:
        result[int(cid)] = {
            'website': website.strip(),
        }
    return result


def parse_session_dates(content) -> list[dict]:
    """
    Parse session_date rows for program schedule data.
    Returns list of {seid, start_date, end_date, cost_from, cost_to, before_care, after_care}.
    """
    blocks = re.findall(
        r"INSERT INTO `session_date` VALUES (.*?);\n",
        content, re.DOTALL
    )
    rows = []
    for block in blocks:
        matches = re.findall(
            r"\((\d+),(\d+),(\d+),"           # id, cid, seid
            r"'(\d{4}-\d{2}-\d{2})',"         # start
            r"'(\d{4}-\d{2}-\d{2})',"         # end
            r"(\d+),(\d+),"                    # cost_from, cost_to
            r"\d+,'[^']*',\d+,\d+,"           # location, timestamp, loc, period
            r"'[^']*','[^']*',"               # start_time, end_time
            r"(\d+),"                          # before_care
            r"'[^']*',\d+,"                   # before_start, before_fee
            r"(\d+),",                         # after_care
            block
        )
        for m in matches:
            rows.append({
                "seid":        int(m[2]),
                "start_date":  m[3],
                "end_date":    m[4],
                "cost_from":   int(m[5]) or None,
                "cost_to":     int(m[6]) or None,
                "before_care": int(m[7]),
                "after_care":  int(m[8]),
            })
    return rows


def parse_extra_locations(content):
    """Returns dict: {cid: [location_dict, ...]}"""
    block = _extract_block(content, 'extra_locations')
    if not block:
        return {}

    rows = re.findall(
        r'\((\d+),(\d+),(\d+),\'([^\']*)\',([0-9.-]+),([0-9.-]+),'
        r'(\d+),\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',(\d+)',
        block
    )
    result = defaultdict(list)
    for row in rows:
        el_id, cid, loc_id, postal, lat, lon, admin, address, city, province, country, main_loc = row
        city = normalise_city(city)
        province = normalise_province(province)
        if not city:
            continue
        result[int(cid)].append({
            'city': city, 'province': province,
            'lat': float(lat), 'lon': float(lon),
            'address': address.strip(), 'postal': postal.strip(),
        })
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def name_related(a, b):
    stop = {"camp", "the", "of", "at", "in", "and", "&", "-", "summer",
            "day", "sports", "inc", "ltd", "school", "schools"}
    a_sig = set(a.lower().split()) - stop
    b_sig = set(b.lower().split()) - stop
    return bool(a_sig & b_sig) if a_sig and b_sig else False


def ensure_unique_slug(cursor, slug_base):
    slug = slug_base
    counter = 1
    while True:
        cursor.execute("SELECT id FROM camps WHERE slug = %s", (slug,))
        if not cursor.fetchone():
            return slug
        slug = f"{slug_base}-{counter}"
        counter += 1


# ── Session parser ────────────────────────────────────────────────────────────

def parse_sessions_by_camp(content, camp_ids: set) -> dict:
    """
    Parse session/session_draft names from the dump, grouped by camp_id.
    Only returns data for camp_ids in the provided set.
    Returns: {camp_id: [session_name, ...]}
    """
    result = defaultdict(list)
    for m in re.finditer(
        r"INSERT INTO `sessions(?:_draft)?` VALUES (.*?);\n",
        content, re.DOTALL
    ):
        for sm in re.finditer(r"\(\d+,(\d+),'([^']+)'", m.group(1)):
            cid = int(sm.group(1))
            if cid in camp_ids:
                result[cid].append(sm.group(2).strip())
    return result


def parse_sitems(content) -> dict:
    """
    Parse the sitems table from the dump.
    Maps sitems ID → activity_tag slug via WEBITEMS_TO_SLUG.
    Returns: {sitems_id: slug} for items that have a known mapping.
    """
    from db.tag_from_campsca_pages import WEBITEMS_TO_SLUG

    # Build name→slug lookup (case-insensitive)
    name_to_slug = {k.lower(): v for k, v in WEBITEMS_TO_SLUG.items()}

    result = {}
    for block_m in re.finditer(
        r"INSERT INTO `sitems` VALUES (.*?);\n",
        content, re.DOTALL
    ):
        # Each row: (id, ?, 'item_name', ...)
        for row_m in re.finditer(
            r"\((\d+),\d+,'((?:[^'\\]|\\.)*?)'",
            block_m.group(1)
        ):
            sitems_id = int(row_m.group(1))
            item_name = row_m.group(2).strip().replace("\\'", "'")
            slug = name_to_slug.get(item_name.lower())
            if slug:
                result[sitems_id] = slug

    return result


def parse_activities_field(raw: str) -> list[int]:
    """
    Parse the activities text field from a session row.
    Input:  "[133]2,[81]3,[154]1"
    Output: [133, 81, 154]  (sitems IDs, priority discarded)
    """
    if not raw:
        return []
    return [int(m) for m in re.findall(r'\[(\d+)\]', raw)]


def parse_sessions_full(content, camp_ids: set) -> dict:
    """
    Parse full session details from the dump for specific camp_ids.
    Deduplicates by cleaned name — returns one record per unique program name.
    Skips: status=0, blank/draft names ("New program", "Copy of ...").
    Returns: {camp_id: [{"name", "type", "category_id", "specialty_id",
                          "age_from", "age_to", "cost_from", "cost_to",
                          "date_from", "date_to", "activity_ids"}, ...]}
    """
    # Schema: (id, camp_id, 'name', 'type', category, specialty, status,
    #           'date_from', 'date_to', age_from, age_to, cost_from, cost_to, ...)
    _SESSION_RE = re.compile(
        r"\((\d+),(\d+),'((?:[^'\\]|\\.)*?)','([^']*)',(\d+),(\d+),(\d+),"
        r"'(\d{4}-\d{2}-\d{2})','(\d{4}-\d{2}-\d{2})',"
        r"(\d+),(\d+),(\d+),(\d+),"
    )
    # Pattern to extract activities field: [id]priority encoded text
    _ACTIVITIES_RE = re.compile(r'\[(\d+)\]\d+')
    _SKIP_PREFIXES = ("new program", "copy of")

    result = defaultdict(dict)  # camp_id → {clean_name: session_dict}

    for m in re.finditer(
        r"INSERT INTO `sessions` VALUES (.*?);\n",
        content, re.DOTALL
    ):
        block = m.group(1)
        for sm in _SESSION_RE.finditer(block):
            cid    = int(sm.group(2))
            if cid not in camp_ids:
                continue
            status = int(sm.group(7))
            if status != 1:
                continue
            name = sm.group(3).strip().replace("\\'", "'")
            if not name:
                continue
            name_lower = name.lower()
            if any(name_lower.startswith(p) for p in _SKIP_PREFIXES):
                continue

            clean_key = re.sub(r'\s+', ' ', name_lower).strip()
            if clean_key in result[cid]:
                continue  # keep first occurrence per unique name

            category_id  = int(sm.group(5))
            specialty_id = int(sm.group(6))

            date_from = sm.group(8)
            date_to   = sm.group(9)

            # Extract activities from the tail of this row.
            # Find the text from end of regex match to the next row start.
            tail_start = sm.end()
            next_row = block.find('),(', tail_start)
            if next_row == -1:
                tail = block[tail_start:]
            else:
                tail = block[tail_start:next_row]
            activity_ids = [int(x) for x in _ACTIVITIES_RE.findall(tail)]

            result[cid][clean_key] = {
                "name":         name,
                "type":         sm.group(4) or None,
                "category_id":  category_id or None,
                "specialty_id": specialty_id or None,
                "age_from":     int(sm.group(10)) or None,
                "age_to":       int(sm.group(11)) or None,
                "cost_from":    int(sm.group(12)) or None,
                "cost_to":      int(sm.group(13)) or None,
                "date_from":    date_from if date_from != "0000-00-00" else None,
                "date_to":      date_to   if date_to   != "0000-00-00" else None,
                "activity_ids": activity_ids,
            }

    # Convert inner dicts to lists
    return {cid: list(sessions.values()) for cid, sessions in result.items()}


# ── Activity tag inference ─────────────────────────────────────────────────────
# Keyword → [tag_slug, ...] mapping.
# Validated against camps.ca taxonomy, OurKids.net category pages, and
# industry sources (summercamps.com, galileo-camps.com, ourkids.net).
# Rules: longer/more specific phrases take priority over bare keywords.
# Bare sport/activity names map directly; generic umbrella terms use *-multi tags.

_KEYWORD_TO_TAGS = [
    # ── Tech / STEM ──────────────────────────────────────────────────────────
    (["robotics", "robot", "robotic"],                      ["robotics"]),
    (["coding", "code", "programming", "programmer",
      "software", "developer", "learn to code"],            ["programming-multi"]),
    (["stem camp", "stem program", "stem learning",
      "science tech", "science, tech", "science and tech"], ["stem"]),
    (["stem"],                                              ["stem"]),
    (["steam"],                                             ["steam"]),
    (["minecraft"],                                         ["minecraft", "video-game-design"]),
    (["roblox"],                                            ["roblox", "video-game-design"]),
    (["python"],                                            ["python"]),
    (["scratch coding", "mit scratch", "scratch junior",
      "block coding", "visual coding", "scratch program",
      "scratch camp"],                                      ["scratch"]),
    (["scratch"],                                           ["scratch"]),
    (["java"],                                              ["java"]),
    (["arduino"],                                           ["arduino"]),
    (["raspberry pi"],                                      ["raspberry-pi"]),
    (["3d printing", "3d-printing"],                        ["3d-printing"]),
    (["3d design", "3d-design", "3d modelling",
      "3d modeling"],                                       ["3d-design"]),
    (["artificial intelligence", "machine learning",
      "ai camp", "ai program"],                             ["ai-artificial-intelligence"]),
    (["drone", "uav", "unmanned aerial"],                   ["drone-technology"]),
    (["virtual reality", "vr camp", "vr headset"],          ["virtual-reality"]),
    (["lego robotics", "lego mindstorm"],                   ["robotics", "lego"]),
    (["lego building", "lego engineering"],                 ["lego", "engineering"]),
    (["lego"],                                              ["lego"]),
    (["makerspace", "maker space", "maker camp"],           ["makerspace"]),
    (["mechatronics"],                                      ["mechatronics"]),
    (["micro:bit", "micro bit", "microbit"],                ["micro-bit"]),
    (["c++", "c plus plus"],                                ["c-plus-plus"]),
    (["c#", "c-sharp", "csharp"],                           ["c-sharp"]),
    (["swift", "ios development", "iphone app"],            ["swift-apple"]),
    (["pygame"],                                            ["pygame"]),
    (["web design", "website design"],                      ["web-design"]),
    (["web dev", "web development"],                        ["web-development"]),
    (["video game design", "game design", "game dev",
      "game development", "game creation"],                 ["video-game-design"]),
    (["video game development"],                            ["video-game-development"]),
    (["esports", "e-sports", "competitive gaming",
      "gaming camp", "gaming tournament"],                  ["gaming"]),
    (["animation"],                                         ["animation"]),
    (["technology camp", "tech camp"],                      ["technology"]),
    (["engineering"],                                       ["engineering"]),
    (["architecture"],                                      ["architecture"]),
    (["science"],                                           ["science-multi"]),
    (["math", "mathematics", "algebra", "calculus",
      "numeracy"],                                          ["math"]),
    (["space", "astronomy", "astrophysics", "nasa"],        ["space"]),
    (["forensic", "csi camp"],                              ["forensic-science"]),
    (["marine biology", "ocean science"],                   ["marine-biology"]),
    (["meteorology", "weather science"],                    ["meteorology"]),
    (["health science", "medical science",
      "medicine camp", "pharmacy"],                         ["health-science"]),
    (["zoology", "zoo camp"],                               ["zoology"]),
    (["animals", "animal care", "veterinary"],              ["animals"]),
    (["nature", "environment", "ecology",
      "conservation", "environmental"],                     ["nature-environment"]),
    (["archaeology", "paleontology", "fossil"],             ["archaeology-paleontology"]),
    # ── Sports ───────────────────────────────────────────────────────────────
    (["soccer", "football (soccer)", "futsal"],             ["soccer"]),
    (["basketball"],                                        ["basketball"]),
    (["tennis"],                                            ["tennis"]),
    (["volleyball"],                                        ["volleyball"]),
    (["swimming", "swim lesson", "swim camp",
      "learn to swim"],                                     ["swimming"]),
    (["hockey"],                                            ["hockey"]),
    (["baseball", "softball"],                              ["baseball-softball"]),
    (["football", "american football", "cfl"],              ["football"]),
    (["flag football"],                                     ["flag-football"]),
    (["lacrosse"],                                          ["lacrosse"]),
    (["gymnastics", "gymnastic"],                           ["gymnastics"]),
    (["martial arts"],                                      ["martial-arts"]),
    (["karate"],                                            ["karate"]),
    (["taekwondo", "tae kwon do"],                          ["taekwondo"]),
    (["archery"],                                           ["archery"]),
    (["badminton"],                                         ["badminton"]),
    (["cycling", "bicycle camp"],                           ["cycling"]),
    (["golf"],                                              ["golf"]),
    (["cricket"],                                           ["cricket"]),
    (["rugby"],                                             ["rugby"]),
    (["ultimate frisbee", "ultimate disc"],                 ["ultimate-frisbee"]),
    (["fencing"],                                           ["fencing"]),
    (["figure skating", "figure skate"],                    ["figure-skating"]),
    (["ice skating", "skating camp"],                       ["ice-skating"]),
    (["skiing", "ski camp", "downhill ski"],                ["skiing"]),
    (["snowboarding"],                                      ["snowboarding"]),
    (["rock climbing", "climbing wall"],                    ["rock-climbing"]),
    (["parkour"],                                           ["parkour"]),
    (["trampoline"],                                        ["trampoline"]),
    (["track and field", "track & field", "athletics"],     ["track-and-field"]),
    (["dodgeball"],                                         ["dodgeball"]),
    (["ping pong", "table tennis"],                         ["ping-pong"]),
    (["squash"],                                            ["squash"]),
    (["pickleball"],                                        ["pickleball"]),
    (["cheerleading", "cheer camp"],                        ["cheer"]),
    (["disc golf"],                                         ["disc-golf"]),
    (["gaga ball", "ga-ga"],                                ["gaga"]),
    (["bmx", "motocross"],                                  ["bmx-motocross"]),
    (["skateboard"],                                        ["skateboarding"]),
    (["rollerblad", "rollerblade"],                         ["rollerblading"]),
    (["mountain bike", "mountain biking"],                  ["mountain-biking"]),
    (["ninja warrior", "ninja obstacle", "ninja camp",
      "ninja training", "obstacle course"],                 ["ninja-warrior"]),
    (["paintball"],                                         ["paintball"]),
    (["water polo"],                                        ["water-polo"]),
    (["multi sport", "multi-sport", "multisport",
      "all sports", "variety sport"],                       ["sport-multi"]),
    # ── Water sports ─────────────────────────────────────────────────────────
    (["sailing", "sail camp", "cansail"],                   ["sailing-marine-skills"]),
    (["canoeing", "canoe camp"],                            ["canoeing"]),
    (["kayak"],                                             ["kayaking-sea-kayaking"]),
    (["waterskiing", "water skiing", "wakeboard",
      "wake board"],                                        ["waterskiing-wakeboarding"]),
    (["rowing"],                                            ["rowing"]),
    (["surfing"],                                           ["surfing"]),
    (["fishing"],                                           ["fishing"]),
    (["paddle board", "paddleboard", "sup camp"],           ["stand-up-paddle-boarding"]),
    (["scuba", "diving camp"],                              ["diving"]),
    (["whitewater", "white water", "rafting"],              ["whitewater-rafting"]),
    (["board sailing", "windsurfing"],                      ["board-sailing"]),
    (["tubing"],                                            ["tubing"]),
    # ── Visual arts ──────────────────────────────────────────────────────────
    (["arts and crafts", "arts & crafts",
      "art and craft"],                                     ["arts-crafts"]),
    (["drawing", "sketching", "illustration"],              ["drawing"]),
    (["painting"],                                          ["painting"]),
    (["pottery"],                                           ["pottery"]),
    (["ceramics"],                                          ["ceramics"]),
    (["sculpture"],                                         ["sculpture"]),
    (["photography"],                                       ["photography"]),
    (["videography"],                                       ["videography"]),
    (["filmmaking", "film making", "film camp",
      "movie making"],                                      ["filmmaking"]),
    (["fashion design", "fashion camp"],                    ["fashion-design"]),
    (["knitting", "crochet"],                               ["knitting-and-crochet"]),
    (["mixed media"],                                       ["mixed-media"]),
    (["papier mache", "papier-mache"],                      ["papier-mache"]),
    (["cartooning", "cartoon"],                             ["cartooning"]),
    (["comic art", "comic book"],                           ["comic-art"]),
    (["woodworking", "wood shop"],                          ["woodworking"]),
    (["sewing", "textile"],                                 ["sewing"]),
    # ── Dance ────────────────────────────────────────────────────────────────
    (["ballet"],                                            ["ballet"]),
    (["jazz dance", "jazz class"],                          ["jazz"]),
    (["hip hop", "hip-hop"],                                ["hip-hop"]),
    (["breakdancing", "break dancing", "breakdance"],       ["breakdancing"]),
    (["contemporary dance"],                                ["contemporary"]),
    (["lyrical"],                                           ["lyrical"]),
    (["tap dance", "tap class"],                            ["tap"]),
    (["ballroom"],                                          ["ballroom"]),
    (["acro dance", "acrodance", "acrobatics"],             ["acro-dance"]),
    (["modern dance"],                                      ["modern"]),
    (["dance"],                                             ["dance-multi"]),
    # ── Performing arts / music ──────────────────────────────────────────────
    (["musical theatre", "musical theater"],                ["musical-theatre"]),
    (["theatre arts", "theater arts", "theatre camp",
      "drama camp"],                                        ["theatre-arts"]),
    (["acting", "film & tv", "film and tv",
      "screen acting"],                                     ["acting-film-tv"]),
    (["improv comedy", "sketch comedy"],                    ["comedy", "theatre-arts"]),
    (["improv"],                                            ["comedy", "theatre-arts"]),
    (["comedy"],                                            ["comedy"]),
    (["glee"],                                              ["glee"]),
    (["magic camp", "magic show"],                          ["magic"]),
    (["puppetry"],                                          ["puppetry"]),
    (["playwriting"],                                       ["playwriting"]),
    (["singing", "vocal", "voice lesson",
      "choir", "choral"],                                   ["vocal-training-singing"]),
    (["guitar"],                                            ["guitar"]),
    (["piano", "keyboard"],                                 ["piano"]),
    (["percussion", "drums", "drumming"],                   ["percussion"]),
    (["violin", "cello", "viola", "string"],                ["string"]),
    (["songwriting", "song writing"],                       ["songwriting"]),
    (["music recording", "music production",
      "recording studio"],                                  ["music-recording"]),
    (["dj", "djing", "turntable"],                          ["djing"]),
    (["band camp", "jam camp", "rock camp"],                ["jam-camp"]),
    (["instrument", "musical instrument"],                  ["musical-instrument-training"]),
    (["music"],                                             ["music-multi"]),
    (["performing arts"],                                   ["performing-arts-multi"]),
    # ── Language / academic ──────────────────────────────────────────────────
    (["chess"],                                             ["chess"]),
    (["board game", "board-game", "tabletop"],              ["board-games"]),
    (["dungeons and dragons", "dungeons & dragons", "d&d",
      "dnd", "d & d"],                                      ["dungeons-and-dragons"]),
    (["debate"],                                            ["debate"]),
    (["public speaking", "speech"],                         ["public-speaking"]),
    (["creative writing"],                                  ["creative-writing"]),
    (["journalism"],                                        ["journalism"]),
    (["storytelling"],                                      ["storytelling"]),
    (["essay writing", "essay camp"],                       ["essay-writing"]),
    (["reading"],                                           ["reading"]),
    (["podcasting", "podcast"],                             ["podcasting"]),
    (["youtube", "vlog", "vlogging"],                       ["youtube-vlogging"]),
    (["writing"],                                           ["writing"]),
    (["french immersion", "french camp",
      "immersion française", "parler français",
      "francais", "français"],                              ["language-instruction"]),
    (["english instruction", "esl", "fsl",
      "language camp", "bilingual", "language immersion",
      "mandarin", "spanish camp", "learn french",
      "learn english"],                                     ["language-instruction"]),
    (["french"],                                            ["language-instruction"]),
    # Note: bare "english" intentionally excluded — too often used as session-language
    # descriptor (e.g. "Soccer Camp (English)") rather than English instruction.
    (["tutoring", "tutor", "academic support",
      "homework help", "learning centre",
      "academic enrichment"],                               ["academic-tutoring-multi"]),
    (["logical thinking", "critical thinking",
      "logic"],                                             ["logical-thinking"]),
    (["test prep", "sat prep", "act prep",
      "standardized test"],                                 ["test-preparation"]),
    (["credit course", "credit class", "high school credit",
      "university credit"],                                 ["credit-courses"]),
    # ── Leadership / personal dev ────────────────────────────────────────────
    (["leadership"],                                        ["leadership-training"]),
    (["empowerment"],                                       ["empowerment"]),
    (["social justice"],                                    ["social-justice"]),
    (["financial literacy", "money management"],            ["financial-literacy"]),
    (["entrepreneurship", "entrepreneur", "startup"],       ["entrepreneurship"]),
    (["cit", "counsellor in training",
      "counselor in training"],                             ["cit-lit-program"]),
    # ── Outdoor / adventure ──────────────────────────────────────────────────
    (["wilderness trip", "canoe trip", "out-tripping",
      "outtripping"],                                       ["wilderness-out-tripping"]),
    (["wilderness", "bushcraft", "backcountry"],            ["wilderness-skills"]),
    (["ropes course", "high ropes", "low ropes"],           ["ropes-course"]),
    (["survival skills", "survival camp"],                  ["survival-skills"]),
    (["urban exploration"],                                 ["urban-exploration"]),
    (["hiking", "backpacking", "trekking"],                 ["hiking"]),
    (["travel camp", "teen travel", "world travel"],        ["travel"]),
    (["adventure camp", "adventure program"],               ["adventure"]),
    (["safari"],                                            ["safari"]),
    (["zip line", "zipline"],                               ["zip-line"]),
    # ── Equestrian ───────────────────────────────────────────────────────────
    (["horseback", "horse riding", "horse camp",
      "equestrian", "equine", "pony", "stable"],            ["horseback-riding-equestrian"]),
    # ── Health / wellness ────────────────────────────────────────────────────
    (["yoga"],                                              ["yoga"]),
    (["meditation"],                                        ["meditation"]),
    (["mindfulness"],                                       ["mindfulness-training"]),
    (["pilates"],                                           ["pilates"]),
    (["nutrition", "healthy eating"],                       ["nutrition"]),
    (["fitness", "conditioning", "bootcamp", "boot camp"],  ["health-fitness"]),
    (["lifeguard", "lifesaving", "first aid", "cpr",
      "emergency response", "bronze cross",
      "water safety", "standard first aid",
      "nls", "national lifeguard"],                         ["first-aid-lifesaving"]),
    (["cooking", "culinary", "chef", "kitchen",
      "junior chef", "food prep", "canning"],               ["cooking"]),
    (["baking", "cake decorating", "pastry", "cupcake"],    ["baking-decorating"]),
    # ── Misc arts ────────────────────────────────────────────────────────────
    (["circus", "acrobat", "aerial"],                       ["circus"]),
]


def infer_tags(session_names: list, tag_slug_to_id: dict) -> set:
    """
    Given a list of session names for a camp, return the set of matched
    activity tag slugs using keyword matching against _KEYWORD_TO_TAGS.

    Matching is case-insensitive. Longer phrases are checked before shorter
    ones to prevent e.g. 'scratch' matching inside 'basketball'.
    Returns only slugs that exist in tag_slug_to_id (i.e. active in our DB).
    """
    combined = " | ".join(session_names).lower()
    found = set()
    for keywords, slugs in _KEYWORD_TO_TAGS:
        for kw in keywords:
            if kw in combined:
                for slug in slugs:
                    if slug in tag_slug_to_id:
                        found.add(slug)
                break  # first matching keyword in the group is enough
    return found


def insert_sitems_tags(cursor, prog_id: int, session: dict,
                       sitems_to_slug: dict, tag_slug_to_id: dict) -> int:
    """
    Insert program_tags from OurKids sitems data (specialty, category, activities).
    Returns the number of tags inserted.
    Falls back to infer_tags() if no sitems data resolves to valid tags.
    """
    inserted = 0
    seen_tag_ids: set[int] = set()

    # 1. Specialty — highest priority tag_role
    spec_id = session.get("specialty_id")
    if spec_id:
        slug = sitems_to_slug.get(spec_id)
        if slug:
            tag_id = tag_slug_to_id.get(slug)
            if tag_id and tag_id not in seen_tag_ids:
                cursor.execute(
                    "INSERT IGNORE INTO program_tags "
                    "(program_id, tag_id, is_primary, tag_role) "
                    "VALUES (%s, %s, 1, 'specialty')",
                    (prog_id, tag_id)
                )
                seen_tag_ids.add(tag_id)
                inserted += cursor.rowcount

    # 2. Category — skip if same tag as specialty
    cat_id = session.get("category_id")
    if cat_id:
        slug = sitems_to_slug.get(cat_id)
        if slug:
            tag_id = tag_slug_to_id.get(slug)
            if tag_id and tag_id not in seen_tag_ids:
                cursor.execute(
                    "INSERT IGNORE INTO program_tags "
                    "(program_id, tag_id, is_primary, tag_role) "
                    "VALUES (%s, %s, 0, 'category')",
                    (prog_id, tag_id)
                )
                seen_tag_ids.add(tag_id)
                inserted += cursor.rowcount

    # 3. Activities — skip duplicates of specialty/category
    for act_id in session.get("activity_ids", []):
        slug = sitems_to_slug.get(act_id)
        if slug:
            tag_id = tag_slug_to_id.get(slug)
            if tag_id and tag_id not in seen_tag_ids:
                cursor.execute(
                    "INSERT IGNORE INTO program_tags "
                    "(program_id, tag_id, is_primary, tag_role) "
                    "VALUES (%s, %s, 0, 'activity')",
                    (prog_id, tag_id)
                )
                seen_tag_ids.add(tag_id)
                inserted += cursor.rowcount

    # 4. Fallback: if no sitems tags resolved, use keyword inference
    if not seen_tag_ids:
        for slug in sorted(infer_tags([session["name"]], tag_slug_to_id)):
            tag_id = tag_slug_to_id.get(slug)
            if tag_id:
                cursor.execute(
                    "INSERT IGNORE INTO program_tags "
                    "(program_id, tag_id, is_primary, tag_role) "
                    "VALUES (%s, %s, 0, 'activity')",
                    (prog_id, tag_id)
                )
                inserted += cursor.rowcount

    return inserted


# ── Main sync logic ───────────────────────────────────────────────────────────

def run(dump_path, dry_run, only, update_meta, deactivate=False, skip_ids=None,
        seed_programs=False, refresh_programs=False, import_all_sessions=False):
    print(f"Reading dump: {dump_path}")
    with open(dump_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    dump_camps  = parse_camps(content)
    dump_addrs  = parse_addresses(content)
    dump_info   = parse_general_info(content)
    dump_locs   = parse_extra_locations(content)
    dump_sdates = parse_session_dates(content)
    sitems_to_slug = parse_sitems(content)

    print(f"  Parsed {len(dump_camps)} camps, {len(dump_addrs)} addresses, "
          f"{len(dump_info)} generalInfo rows, "
          f"{sum(len(v) for v in dump_locs.values())} extra_location rows, "
          f"{len(dump_sdates)} session_date rows, "
          f"{len(sitems_to_slug)} sitems→slug mappings\n")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Load all new-DB camps
    cursor.execute("SELECT id, camp_name, city, province, status, tier, website FROM camps")
    new_db_all = {r['id']: r for r in cursor.fetchall()}

    skip_ids = set(skip_ids or [])

    stats = {
        'new_camps': 0,
        'deactivated': 0,
        'reactivated': 0,
        'programs_seeded': 0,
        'programs_refreshed': 0,
        'programs_refresh_skipped': 0,
        'sessions_imported': 0,
        'sessions_skipped': 0,
        'sessions_unchanged': 0,
        'meta_updated': 0,
        'locations_added': 0,
        'dates_inserted': 0,
    }

    # ── 1. Status changes ─────────────────────────────────────────────────────
    if only in (None, 'status', 'all'):
        print("=== Status changes ===")
        changed = 0
        for cid, old in dump_camps.items():
            if cid not in new_db_all:
                continue
            new = new_db_all[cid]
            old_active = old['status'] == 1  # status=1 means active in legacy DB
            new_active = new['status'] == 1

            if old_active and not new_active:
                # Re-activate: dump says active, new DB says inactive
                print(f"  RE-ACTIVATE id={cid}: {new['camp_name']!r}")
                if not dry_run:
                    cursor.execute("UPDATE camps SET status=1 WHERE id=%s", (cid,))
                stats['reactivated'] += 1
                changed += 1
            elif not old_active and new_active and deactivate:
                # Dump says inactive (camp left client list), new DB still active.
                # Only deactivate camps whose ID came from the old DB (cid in dump).
                # Manually-created location branches (IDs assigned post-migration)
                # won't appear in dump_camps at all, so they're never touched here.
                if cid in skip_ids:
                    print(f"  SKIPPED     id={cid}: {new['camp_name']!r}  (in --skip-ids)")
                    continue
                print(f"  DEACTIVATE  id={cid}: {new['camp_name']!r}")
                if not dry_run:
                    cursor.execute("UPDATE camps SET status=0 WHERE id=%s", (cid,))
                stats['deactivated'] += 1
                changed += 1

        if not changed:
            print("  No status changes.")
        print()

    # ── 2. New camps ──────────────────────────────────────────────────────────
    if only in (None, 'new', 'all'):
        print("=== New camps (in dump, not in new DB) ===")
        added = 0
        for cid, old in sorted(dump_camps.items()):
            if cid in new_db_all:
                continue
            if old['status'] != 1:
                continue  # only import active camps (status=1 in legacy DB)

            addr = dump_addrs.get(cid, {})
            info = dump_info.get(cid, {})
            city = addr.get('city')
            province = addr.get('province')

            if not city:
                continue  # skip camps with no city data

            camp_name = old['camp_name']
            slug = ensure_unique_slug(cursor, slugify(camp_name)) if not dry_run else slugify(camp_name)

            print(f"  NEW id={cid}: {camp_name!r} ({city}, {province})")
            if dry_run:
                added += 1
                continue

            cursor.execute(
                """
                INSERT INTO camps
                    (id, camp_name, slug, tier, status, lat, lon,
                     city, province, country, website, description, prettyurl)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s, %s)
                ON DUPLICATE KEY UPDATE id=id
                """,
                (cid, camp_name, slug, old.get('tier', 'bronze'),
                 old.get('lat'), old.get('lon'),
                 city, province,
                 info.get('website', ''), info.get('description', ''),
                 old.get('prettyurl'))
            )
            added += 1

        stats['new_camps'] = added
        if not added:
            print("  No new camps.")
        print()

    # ── 3. Seed programs for newly-active camps ───────────────────────────────
    if seed_programs and only in (None, 'seed', 'all'):
        print("=== Seed programs for active camps with none ===")

        # Find all currently-active camps in our DB with no programs
        cursor.execute("""
            SELECT c.id, c.camp_name
            FROM camps c
            LEFT JOIN programs p ON p.camp_id = c.id AND p.status = 1
            WHERE c.status = 1
            GROUP BY c.id
            HAVING COUNT(p.id) = 0
        """)
        needs_program = {r['id']: r['camp_name'] for r in cursor.fetchall()}

        if not needs_program:
            print("  No active camps without programs.")
            print()
        else:
            # Only seed camps whose DB id exists as a CID in the dump
            # (auto-increment location branches have IDs that don't match legacy CIDs)
            dump_cids = set(dump_camps.keys())
            needs_program = {k: v for k, v in needs_program.items() if k in dump_cids}

            print(f"  {len(needs_program)} active camps need programs — "
                  f"parsing sessions from dump...")

            # Parse sessions only for camps that need them
            sessions_by_camp = parse_sessions_by_camp(content, set(needs_program.keys()))

            # Load active tag slug → id map
            cursor.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
            tag_slug_to_id = {r['slug']: r['id'] for r in cursor.fetchall()}

            seeded = 0
            for camp_id, camp_name in sorted(needs_program.items()):
                sessions = sessions_by_camp.get(camp_id, [])
                inferred = sorted(infer_tags(sessions, tag_slug_to_id))

                tag_preview = inferred[:6]
                if len(inferred) > 6:
                    tag_preview_str = ", ".join(tag_preview) + f" (+{len(inferred)-6} more)"
                else:
                    tag_preview_str = ", ".join(tag_preview) or "(none inferred)"

                print(f"  SEED id={camp_id}: {camp_name!r}  "
                      f"sessions={len(sessions)}  tags=[{tag_preview_str}]")

                if dry_run:
                    seeded += 1
                    continue

                # Create default program
                cursor.execute(
                    """
                    INSERT INTO programs (camp_id, name, type, age_from, age_to, status)
                    VALUES (%s, %s, 'Day', 4, 18, 1)
                    """,
                    (camp_id, camp_name)
                )
                prog_id = cursor.lastrowid

                # Assign inferred tags (seed path has no per-session sitems data)
                for slug in inferred:
                    tag_id = tag_slug_to_id.get(slug)
                    if tag_id:
                        cursor.execute(
                            "INSERT IGNORE INTO program_tags "
                            "(program_id, tag_id, is_primary, tag_role) "
                            "VALUES (%s, %s, 0, 'activity')",
                            (prog_id, tag_id)
                        )

                seeded += 1
                if seeded % 50 == 0:
                    conn.commit()

            stats['programs_seeded'] = seeded
            if not dry_run and seeded % 50 != 0:
                conn.commit()
            print()

    # ── 4. Refresh programs — replace single generic placeholders ────────────
    if refresh_programs and only in (None, 'refresh', 'all'):
        print("=== Refresh programs (replace generic placeholders with real sessions) ===")

        # Find camps with exactly 1 program where program name = camp name
        cursor.execute("""
            SELECT c.id, c.camp_name, MIN(p.id) as prog_id
            FROM camps c
            JOIN programs p ON p.camp_id = c.id AND p.status = 1
            WHERE c.status = 1
            GROUP BY c.id, c.camp_name
            HAVING COUNT(p.id) = 1 AND MIN(p.name) = MAX(c.camp_name)
        """)
        placeholder_camps = {r['id']: r for r in cursor.fetchall()}

        if not placeholder_camps:
            print("  No camps with generic placeholder programs found.")
            print()
        else:
            # Only refresh camps whose DB id exists as a CID in the dump
            dump_cids = set(dump_camps.keys())
            placeholder_camps = {k: v for k, v in placeholder_camps.items() if k in dump_cids}

            print(f"  {len(placeholder_camps)} camps with generic placeholders — "
                  f"parsing sessions from dump...")

            sessions_by_camp = parse_sessions_full(content, set(placeholder_camps.keys()))

            # Load active tag slug → id map
            cursor.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
            tag_slug_to_id = {r['slug']: r['id'] for r in cursor.fetchall()}

            refreshed = skipped = 0
            for camp_id, row in sorted(placeholder_camps.items()):
                sessions = sessions_by_camp.get(camp_id, [])
                if not sessions:
                    skipped += 1
                    if dry_run:
                        print(f"  SKIP  id={camp_id}: {row['camp_name']!r}  (no sessions in dump)")
                    continue

                tag_names = [s["name"] for s in sessions]
                print(f"  {'DRY ' if dry_run else ''}REFRESH id={camp_id}: "
                      f"{row['camp_name']!r}  → {len(sessions)} sessions")

                if dry_run:
                    for s in sessions[:5]:
                        inferred = sorted(infer_tags([s["name"]], tag_slug_to_id))
                        print(f"    · {s['name']!r:50s}  tags={inferred}")
                    if len(sessions) > 5:
                        print(f"    … (+{len(sessions)-5} more)")
                    refreshed += 1
                    continue

                old_prog_id = row['prog_id']

                # Remove old placeholder tags, dates, and program
                cursor.execute("DELETE FROM program_tags WHERE program_id = %s", (old_prog_id,))
                cursor.execute("DELETE FROM program_dates WHERE program_id = %s", (old_prog_id,))
                cursor.execute("DELETE FROM programs WHERE id = %s", (old_prog_id,))

                # Insert one program per unique session name
                for s in sessions:
                    cursor.execute(
                        """
                        INSERT INTO programs
                            (camp_id, name, type, age_from, age_to,
                             cost_from, cost_to, start_date, end_date, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                        """,
                        (
                            camp_id,
                            s["name"],
                            s["type"],
                            s["age_from"],
                            s["age_to"],
                            s["cost_from"],
                            s["cost_to"],
                            s["date_from"],
                            s["date_to"],
                        )
                    )
                    prog_id = cursor.lastrowid
                    insert_sitems_tags(cursor, prog_id, s,
                                      sitems_to_slug, tag_slug_to_id)

                refreshed += 1
                if refreshed % 20 == 0:
                    conn.commit()

            stats['programs_refreshed'] = refreshed
            stats['programs_refresh_skipped'] = skipped
            if not dry_run and refreshed % 20 != 0:
                conn.commit()
            print()

    # ── 4c. Import all sessions — comprehensive program sync for ALL camps ────
    if import_all_sessions and only in (None, 'import', 'all'):
        print("=== Import all sessions (comprehensive program sync) ===")

        # Load every active camp in the DB
        cursor.execute("SELECT id, camp_name FROM camps WHERE status = 1")
        all_active = {r['id']: r['camp_name'] for r in cursor.fetchall()}

        # SAFETY: Only import sessions for camps whose DB id exists as a CID in
        # the dump.  Camps created by the sync itself (location branches, etc.)
        # have auto-increment IDs that do NOT correspond to legacy CIDs.  If we
        # pass those IDs to parse_sessions_full the dump's sessions for the
        # *unrelated* legacy camp with the same CID get imported under the wrong
        # camp — causing cross-camp data corruption.
        dump_cids = set(dump_camps.keys())
        id_collisions = {cid for cid in all_active if cid not in dump_cids}
        if id_collisions:
            print(f"  Skipping {len(id_collisions)} camps whose DB id has no "
                  f"matching CID in dump (auto-increment location branches)")
            all_active = {k: v for k, v in all_active.items() if k in dump_cids}

        print(f"  {len(all_active)} active camps — parsing dump sessions...")

        all_sessions = parse_sessions_full(content, set(all_active.keys()))
        camps_with_sessions = len(all_sessions)
        camps_no_sessions   = len(all_active) - camps_with_sessions
        total_session_recs  = sum(len(v) for v in all_sessions.values())
        print(f"  Dump has sessions for {camps_with_sessions} camps "
              f"({camps_no_sessions} will be skipped — no sessions in dump)")
        print(f"  Total unique session records to import: {total_session_recs}")
        print()

        # Load active tag slug → id map
        cursor.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
        tag_slug_to_id = {r['slug']: r['id'] for r in cursor.fetchall()}

        # Load existing program names per camp (for change detection in dry-run)
        cursor.execute(
            "SELECT camp_id, GROUP_CONCAT(name ORDER BY name SEPARATOR '|||') as names "
            "FROM programs WHERE status = 1 GROUP BY camp_id"
        )
        existing_names = {
            r['camp_id']: set(r['names'].split('|||'))
            for r in cursor.fetchall()
        }

        imported = skipped = unchanged = 0
        for camp_id in sorted(all_active):
            sessions = all_sessions.get(camp_id)
            if not sessions:
                skipped += 1
                continue

            dump_name_set = {s['name'].strip() for s in sessions}
            db_name_set   = existing_names.get(camp_id, set())
            new_names     = dump_name_set - db_name_set
            gone_names    = db_name_set - dump_name_set

            if not new_names and not gone_names:
                unchanged += 1
                if dry_run:
                    pass  # silent — nothing to do
                continue

            camp_name = all_active[camp_id]
            print(f"  {'DRY ' if dry_run else ''}SYNC  id={camp_id}: {camp_name!r}  "
                  f"+{len(new_names)} new  -{len(gone_names)} removed  "
                  f"(total → {len(sessions)})")

            if dry_run:
                for name in sorted(new_names)[:3]:
                    tags = sorted(infer_tags([name], tag_slug_to_id))
                    print(f"    + {name!r:50s}  tags={tags}")
                if len(new_names) > 3:
                    print(f"    … (+{len(new_names)-3} more new)")
                imported += 1
                continue

            # Delete all existing programs and their tags/dates for this camp
            cursor.execute(
                "SELECT id FROM programs WHERE camp_id = %s AND status = 1",
                (camp_id,)
            )
            old_ids = [r['id'] for r in cursor.fetchall()]
            if old_ids:
                id_list = ','.join(str(x) for x in old_ids)
                cursor.execute(f"DELETE FROM program_tags  WHERE program_id IN ({id_list})")
                cursor.execute(f"DELETE FROM program_dates WHERE program_id IN ({id_list})")
                cursor.execute(f"DELETE FROM programs      WHERE id          IN ({id_list})")

            # Insert fresh session records
            for s in sessions:
                cursor.execute(
                    "INSERT INTO programs "
                    "(camp_id, name, type, age_from, age_to, "
                    " cost_from, cost_to, start_date, end_date, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)",
                    (
                        camp_id, s["name"], s["type"],
                        s["age_from"], s["age_to"],
                        s["cost_from"], s["cost_to"],
                        s["date_from"], s["date_to"],
                    )
                )
                prog_id = cursor.lastrowid
                insert_sitems_tags(cursor, prog_id, s,
                                   sitems_to_slug, tag_slug_to_id)

            imported += 1
            if imported % 25 == 0:
                conn.commit()

        stats['sessions_imported'] = imported
        stats['sessions_skipped']  = skipped
        stats['sessions_unchanged'] = unchanged
        if not dry_run and imported % 25 != 0:
            conn.commit()

        print()
        print(f"  {'(DRY RUN) ' if dry_run else ''}Result: "
              f"{imported} camps synced, {unchanged} unchanged, {skipped} skipped (no dump data)")
        print()

    # ── 5. Metadata updates ───────────────────────────────────────────────────
    if update_meta and only in (None, 'meta', 'all'):
        print("=== Metadata updates (tier/website) ===")
        updated = 0
        for cid, old in dump_camps.items():
            if cid not in new_db_all:
                continue
            new = new_db_all[cid]
            new_tier = TIER_MAP.get(old.get('tier', ''), old.get('tier', 'bronze'))
            info = dump_info.get(cid, {})
            changes = {}
            if new_tier != new.get('tier'):
                changes['tier'] = new_tier
            website = info.get('website', '')
            if website and website != (new.get('website') or ''):
                changes['website'] = website
            prettyurl = old.get('prettyurl')
            if prettyurl and prettyurl != (new.get('prettyurl') or ''):
                changes['prettyurl'] = prettyurl

            if changes:
                desc = ', '.join(f"{k}: {new.get(k)!r}→{v!r}" for k, v in changes.items())
                print(f"  UPDATE id={cid} {new['camp_name']!r}: {desc}")
                if not dry_run:
                    set_clause = ', '.join(f"{k}=%s" for k in changes)
                    cursor.execute(
                        f"UPDATE camps SET {set_clause} WHERE id=%s",
                        list(changes.values()) + [cid]
                    )
                updated += 1

        stats['meta_updated'] = updated
        if not updated:
            print("  No metadata changes.")
        print()

    # ── 5. Extra locations ────────────────────────────────────────────────────
    if only in (None, 'locations', 'all'):
        print("=== Missing extra_locations ===")

        # Build city+province index for all new-DB camps
        cursor.execute("SELECT id, camp_name, city, province, status FROM camps")
        all_camps = cursor.fetchall()
        city_prov_index = defaultdict(list)
        for c in all_camps:
            key = ((c['city'] or '').strip().lower(), (c['province'] or '').strip().lower())
            city_prov_index[key].append(c)

        active_in_new = {r['id']: r for r in all_camps if r['status'] == 1}

        # Build city-only index as fallback (handles empty province in extra_locations)
        city_only_index = defaultdict(list)
        for c in all_camps:
            city_only_index[(c['city'] or '').strip().lower()].append(c)

        # Cities that are not real searchable places
        INVALID_CITIES = {'.', '', 'virtual', 'international', 'online', 'tbd', 'n/a'}

        added_locs = 0
        COMMIT_EVERY = 20  # commit after every N new camps created
        camps_since_commit = 0

        for cid, locs in sorted(dump_locs.items()):
            if cid not in active_in_new:
                continue
            primary = active_in_new[cid]

            for loc in locs:
                # Skip invalid/non-geographic cities
                if (loc['city'] or '.').lower() in INVALID_CITIES:
                    continue

                key = (loc['city'].lower(), (loc['province'] or '').lower())
                # Always merge city+province match with city-only match
                # (handles empty province in dump matching populated province in DB)
                prov_matches = city_prov_index.get(key, [])
                city_matches = city_only_index.get(loc['city'].lower(), [])
                seen_ids = set()
                all_matches = []
                for m in prov_matches + city_matches:
                    if m['id'] not in seen_ids:
                        seen_ids.add(m['id'])
                        all_matches.append(m)
                related = [m for m in all_matches if name_related(primary['camp_name'], m['camp_name'])]
                if related:
                    continue  # already present

                camp_name = f"{primary['camp_name']} - {loc['city']}"
                slug_base = slugify(camp_name)

                if dry_run:
                    print(f"  [DRY] CREATE {camp_name!r} "
                          f"({loc['city']}, {loc['province'] or '?'})")
                    added_locs += 1
                    continue

                slug = ensure_unique_slug(cursor, slug_base)

                # Get master camp details
                cursor.execute("SELECT * FROM camps WHERE id=%s", (cid,))
                master = cursor.fetchone() or primary

                cursor.execute(
                    """
                    INSERT INTO camps
                        (camp_name, slug, tier, status, lat, lon,
                         city, province, country, website, description)
                    VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s)
                    ON DUPLICATE KEY UPDATE id=id
                    """,
                    (camp_name, slug, master.get('tier', 'bronze'),
                     loc['lat'], loc['lon'],
                     loc['city'], loc['province'],
                     master.get('website'), master.get('description'))
                )
                new_camp_id = cursor.lastrowid
                print(f"  CREATE id={new_camp_id}: {camp_name!r}")

                # Copy programs from primary
                cursor.execute(
                    "SELECT * FROM programs WHERE camp_id=%s AND status=1", (cid,)
                )
                for prog in cursor.fetchall():
                    cursor.execute(
                        """
                        INSERT INTO programs
                            (camp_id, name, type, age_from, age_to, cost_from, cost_to,
                             mini_description, description, status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
                        """,
                        (new_camp_id, prog['name'], prog['type'],
                         prog.get('age_from'), prog.get('age_to'),
                         prog.get('cost_from'), prog.get('cost_to'),
                         prog.get('mini_description', ''), prog.get('description', ''))
                    )
                    new_prog_id = cursor.lastrowid
                    cursor.execute(
                        "SELECT tag_id FROM program_tags WHERE program_id=%s", (prog['id'],)
                    )
                    for tag_row in cursor.fetchall():
                        cursor.execute(
                            "INSERT INTO program_tags (program_id, tag_id) VALUES (%s,%s)",
                            (new_prog_id, tag_row['tag_id'])
                        )

                added_locs += 1
                camps_since_commit += 1
                # Refresh index so duplicates within same dump don't re-trigger
                city_prov_index[key].append({'id': new_camp_id, 'camp_name': camp_name,
                                              'city': loc['city'], 'province': loc['province'],
                                              'status': 1})
                city_only_index[loc['city'].lower()].append({'id': new_camp_id,
                    'camp_name': camp_name, 'city': loc['city'],
                    'province': loc['province'], 'status': 1})
                # Commit in batches to avoid lock timeouts
                if camps_since_commit >= COMMIT_EVERY:
                    conn.commit()
                    camps_since_commit = 0

        stats['locations_added'] = added_locs
        if not added_locs:
            print("  No missing locations.")
        print()

    # ── 6. Program dates (was 6, now 6) ───────────────────────────────────────
    if only in (None, 'dates', 'all'):
        from datetime import date as _date
        today = str(_date.today())
        print("=== Program dates (session_date sync) ===")

        # Get active program IDs
        cursor.execute("SELECT id FROM programs WHERE status=1")
        active_prog_ids = {r['id'] for r in cursor.fetchall()}

        # Filter to future rows matching active programs
        matched = [r for r in dump_sdates
                   if r['seid'] in active_prog_ids and r['end_date'] >= today]

        from collections import defaultdict as _dd
        by_prog = _dd(list)
        for r in matched:
            by_prog[r['seid']].append(r)

        print(f"  {len(matched)} future session_date rows across "
              f"{len(by_prog)} programs")

        if not dry_run and by_prog:
            # Clear existing future rows for those programs, then re-insert
            prog_id_list = ",".join(str(pid) for pid in by_prog)
            cursor.execute(
                f"DELETE FROM program_dates WHERE end_date >= %s "
                f"AND program_id IN ({prog_id_list})",
                (today,)
            )
            inserted = 0
            for r in matched:
                cursor.execute(
                    """
                    INSERT IGNORE INTO program_dates
                        (program_id, start_date, end_date, cost_from, cost_to,
                         before_care, after_care)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (r['seid'], r['start_date'], r['end_date'],
                     r['cost_from'], r['cost_to'],
                     r['before_care'], r['after_care'])
                )
                inserted += 1
                if inserted % 100 == 0:
                    conn.commit()
            stats['dates_inserted'] = inserted
        elif dry_run:
            stats['dates_inserted'] = len(matched)

        if not by_prog:
            print("  No matching program dates found.")
        print()

    # ── Commit & summary ──────────────────────────────────────────────────────
    if not dry_run:
        conn.commit()

    cursor.close()
    conn.close()

    prefix = "DRY RUN — " if dry_run else ""
    print("=" * 60)
    print(f"{prefix}Sync complete")
    print(f"  New camps {'would be ' if dry_run else ''}inserted:         {stats['new_camps']}")
    print(f"  Camps {'would be ' if dry_run else ''}re-activated:         {stats['reactivated']}")
    if deactivate:
        print(f"  Camps {'would be ' if dry_run else ''}deactivated:          {stats['deactivated']}")
    if seed_programs:
        print(f"  Programs {'would be ' if dry_run else ''}seeded:           {stats['programs_seeded']}")
    if refresh_programs:
        print(f"  Programs {'would be ' if dry_run else ''}refreshed:        {stats['programs_refreshed']}")
        print(f"  Programs skipped (no sessions in dump):  {stats['programs_refresh_skipped']}")
    if import_all_sessions:
        print(f"  Camps {'would be ' if dry_run else ''}synced (changed):  {stats['sessions_imported']}")
        print(f"  Camps unchanged (already up to date):    {stats['sessions_unchanged']}")
        print(f"  Camps skipped (no sessions in dump):     {stats['sessions_skipped']}")
    if update_meta:
        print(f"  Metadata {'would be ' if dry_run else ''}updated:          {stats['meta_updated']}")
    print(f"  Locations {'would be ' if dry_run else ''}added:            {stats['locations_added']}")
    print(f"  Program dates {'would be ' if dry_run else ''}inserted:     {stats['dates_inserted']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync CSC new DB from a legacy SQL dump"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing to DB")
    parser.add_argument("--only",
                        choices=["status", "new", "seed", "refresh", "import", "meta", "locations", "dates", "all"],
                        default=None,
                        help="Run only a specific sync section")
    parser.add_argument("--update-meta", action="store_true",
                        help="Also update tier/website for existing camps")
    parser.add_argument("--deactivate", action="store_true",
                        help="Deactivate camps whose status=0 in the dump "
                             "(i.e. no longer active). Always dry-run first "
                             "to review the list before applying.")
    parser.add_argument("--seed-programs", action="store_true",
                        help="For active camps with no programs: create a default program "
                             "and infer activity tags from dump session names.")
    parser.add_argument("--refresh-programs", action="store_true",
                        help="Replace single generic placeholder programs with individual "
                             "session records imported from the dump. Infers activity tags "
                             "per session name. Always dry-run first.")
    parser.add_argument("--import-all-sessions", action="store_true",
                        help="Comprehensive sync: for every active camp that has sessions "
                             "in the dump, replace ALL its programs with the dump's session "
                             "records. Camps with no sessions in the dump are left untouched. "
                             "Recommended after each new dump. Always dry-run first.")
    parser.add_argument("--skip-ids",
                        help="Comma-separated camp IDs to skip during deactivation "
                             "(e.g. manually-promoted sub-locations: 422,529,579)")
    parser.add_argument("--dump", default=DEFAULT_DUMP,
                        help="Path to SQL dump file")
    args = parser.parse_args()
    skip_ids = set(int(x) for x in args.skip_ids.split(",")) if args.skip_ids else None
    run(args.dump, args.dry_run, args.only, args.update_meta, args.deactivate, skip_ids,
        seed_programs=args.seed_programs, refresh_programs=args.refresh_programs,
        import_all_sessions=args.import_all_sessions)
