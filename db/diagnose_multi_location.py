"""
db/diagnose_multi_location.py

Diagnostic: find camps that appear to have multiple locations in the DB
(same or similar name, different cities) and report which locations are
active vs. inactive.

Also flags:
  - Brand names where the active record has programs but sibling locations
    are status=0 (those cities are invisible to search)
  - Province/city data quality issues (inconsistent province strings)

Run:
  source .venv/bin/activate && python3 db/diagnose_multi_location.py

Optional: pipe to file
  python3 db/diagnose_multi_location.py > multi_location_report.txt
"""
import sys, os, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection


# ── Helpers ──────────────────────────────────────────────────────────────────

def normalise_name(name: str) -> str:
    """Strip location suffixes and noise to get a brand-level key."""
    s = name.lower().strip()
    # Remove trailing location qualifiers
    s = re.sub(r'\s*[-–—/]\s*(toronto|etobicoke|scarborough|north york|oakville|'
               r'mississauga|brampton|vaughan|markham|richmond hill|'
               r'winnipeg|vancouver|victoria|calgary|edmonton|'
               r'ottawa|hamilton|london|kitchener|waterloo|'
               r'victoria park|[a-z\s]+)$', '', s)
    # Remove common suffixes
    for suffix in [' ice sports', ' camps', ' sports', ' camp', ' ice', ' arena',
                   ' east', ' west', ' north', ' south', ' centre', ' center']:
        s = s.rstrip(suffix) if s.endswith(suffix) else s
        s = s.replace(suffix + ' ', ' ')
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def province_key(province: str) -> str:
    """Normalise province strings to full name."""
    mapping = {
        'on': 'Ontario', 'ont': 'Ontario', 'ontario': 'Ontario',
        'bc': 'British Columbia', 'b.c.': 'British Columbia',
        'british columbia': 'British Columbia',
        'ab': 'Alberta', 'alberta': 'Alberta',
        'qc': 'Quebec', 'québec': 'Quebec', 'quebec': 'Quebec',
        'mb': 'Manitoba', 'manitoba': 'Manitoba',
        'sk': 'Saskatchewan', 'saskatchewan': 'Saskatchewan',
        'ns': 'Nova Scotia', 'nova scotia': 'Nova Scotia',
        'nb': 'New Brunswick', 'new brunswick': 'New Brunswick',
        'nl': 'Newfoundland', 'newfoundland': 'Newfoundland',
        'pe': 'PEI', 'pei': 'PEI',
        'yt': 'Yukon', 'nt': 'NWT', 'nu': 'Nunavut',
    }
    return mapping.get(province.lower().strip(), province.strip().title()) if province else ''


def run():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ── Load all camps ────────────────────────────────────────────────────────
    cursor.execute("""
        SELECT id, camp_name, city, province, status,
               (SELECT COUNT(*) FROM programs WHERE camp_id = camps.id AND status = 1) AS active_programs
        FROM camps
        ORDER BY camp_name
    """)
    all_camps = cursor.fetchall()

    # ── Group by normalised brand name ────────────────────────────────────────
    groups: dict[str, list] = {}
    for camp in all_camps:
        key = normalise_name(camp['camp_name'])
        groups.setdefault(key, []).append(camp)

    # ── Filter to groups with multiple records ────────────────────────────────
    multi = {k: v for k, v in groups.items() if len(v) > 1}

    print(f"{'='*70}")
    print(f"MULTI-LOCATION CAMP REPORT")
    print(f"Total camps in DB: {len(all_camps)}")
    print(f"Unique brand groups with 2+ records: {len(multi)}")
    print(f"{'='*70}\n")

    # Separate into categories
    problematic = []   # active record exists but sibling locations are inactive
    all_inactive = []  # all locations inactive
    all_active   = []  # all locations active (healthy)

    for brand, camps in sorted(multi.items()):
        active   = [c for c in camps if c['status'] == 1]
        inactive = [c for c in camps if c['status'] == 0]

        if active and inactive:
            problematic.append((brand, camps, active, inactive))
        elif not active:
            all_inactive.append((brand, camps))
        else:
            all_active.append((brand, camps))

    # ── Section 1: Problematic — active + inactive siblings ──────────────────
    print(f"SECTION 1: Brands with ACTIVE + INACTIVE location records ({len(problematic)})")
    print(f"  These are searchable from their active city only — other locations are invisible.\n")

    for brand, camps, active, inactive in sorted(problematic,
            key=lambda x: sum(c['active_programs'] for c in x[1]), reverse=True):

        total_programs = sum(c['active_programs'] for c in camps)
        print(f"  Brand: {brand!r}  (total active programs: {total_programs})")

        for c in sorted(camps, key=lambda x: (-x['status'], (x['city'] or ''))):
            prov = province_key(c['province'] or '')
            flag = '✓ ACTIVE  ' if c['status'] == 1 else '✗ INACTIVE'
            progs = f"{c['active_programs']} programs" if c['active_programs'] else 'no programs'
            print(f"    [{flag}] id={c['id']:5d}  {(c['city'] or 'unknown'):25s}  "
                  f"{prov:20s}  {progs}  | {c['camp_name']!r}")
        print()

    # ── Section 2: All inactive brand groups ─────────────────────────────────
    print(f"\nSECTION 2: Brands where ALL locations are INACTIVE ({len(all_inactive)})")
    print(f"  These brands are completely invisible to search.\n")

    for brand, camps in sorted(all_inactive):
        cities = ', '.join(
            f"{c['city'] or '?'} ({province_key(c['province'] or '')})" for c in camps
        )
        print(f"  {brand!r}  →  {cities}")

    # ── Section 3: Healthy multi-location camps ───────────────────────────────
    print(f"\nSECTION 3: Brands where ALL locations are ACTIVE ({len(all_active)})")
    for brand, camps in sorted(all_active):
        cities = ', '.join(f"{c['city'] or '?'}" for c in camps)
        print(f"  {brand!r}  →  {cities}")

    # ── Section 4: Province data quality ─────────────────────────────────────
    print(f"\nSECTION 4: Province string inconsistencies (active camps only)")
    cursor.execute("SELECT DISTINCT province FROM camps WHERE status = 1 ORDER BY province")
    provinces = [r['province'] for r in cursor.fetchall()]
    print(f"  Distinct province values in active camps: {provinces}")

    # Find active camps with non-standard province strings
    cursor.execute("""
        SELECT id, camp_name, city, province FROM camps
        WHERE status = 1
          AND province NOT IN ('Ontario','British Columbia','Alberta','Quebec',
                               'Manitoba','Saskatchewan','Nova Scotia',
                               'New Brunswick','Newfoundland','PEI',
                               'Yukon','NWT','Nunavut')
        ORDER BY province, camp_name
    """)
    bad_prov = cursor.fetchall()
    if bad_prov:
        print(f"\n  Active camps with non-standard province strings ({len(bad_prov)}):")
        for r in bad_prov:
            print(f"    id={r['id']:5d}  province={r['province']!r:15s}  "
                  f"{r['camp_name']!r} ({r['city']})")
    else:
        print("  All active camps have standard province strings. ✓")

    # ── Summary ───────────────────────────────────────────────────────────────
    inactive_locations = sum(len(i) for _, _, _, i in problematic)
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"  Brands with hidden sibling locations:  {len(problematic)}")
    print(f"  Total inactive sibling records:        {inactive_locations}")
    print(f"  Fully invisible brand groups:          {len(all_inactive)}")
    print(f"  Healthy multi-location brands:         {len(all_active)}")
    print(f"{'='*70}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    run()
