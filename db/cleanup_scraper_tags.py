#!/usr/bin/env python3
"""
db/cleanup_scraper_tags.py

*** DEPRECATED — DO NOT USE ***

This script was a one-time cleanup that removed scraper-inserted program_tags
from multi-program camps.  However, it cannot distinguish scraper-inserted tags
from OurKids-materialized tags (both use tag_role='activity', is_primary=0),
so it accidentally deleted ~30,000 legitimate tags.

The root causes have been fixed:
  1. Scraper single-program gate (tag_from_campsca_pages.py) prevents new pollution
  2. Broad-page redirects (/fashion-camps.php → /arts_camps.php) set to None
  3. Override JSON cleaned of polluted entries

If tag pollution recurs, fix the source (scraper config or override JSON)
rather than running a bulk delete against program_tags.
"""
import sys

def main():
    print("ERROR: This script is deprecated and should not be run.")
    print("It cannot distinguish scraper tags from OurKids tags and will")
    print("delete legitimate program_tags rows.")
    print()
    print("To fix tag pollution, update the scraper config or override JSON.")
    sys.exit(1)


if __name__ == "__main__":
    main()
