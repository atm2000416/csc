# CSC — Claude Code Project Specification
# OurKids.net Camp Search Concierge
# For use with: `claude /plan` mode
# Version: 1.0 | March 2026
# ─────────────────────────────────────────────────────────────────────────────

## PROJECT OVERVIEW

Build the Camp Search Concierge (CSC) — a hybrid AI + SQL search application
for OurKids.net, a Canadian camp directory. The app allows parents and kids to
find summer camps and programs using natural language in any language.

Full architecture is documented in: `CSC_Plan_v3.docx`
Intent Parser prompt is in: `intent_parser_system_prompt.md`
Taxonomy mapping module is in: `taxonomy_mapping.py`

---

## TECH STACK

| Layer       | Technology                        | Version  |
|-------------|-----------------------------------|----------|
| UI          | Streamlit                         | >=1.35   |
| Database    | MySQL                             | 8.0      |
| AI          | Google Gemini (via google-generativeai) | Latest |
| Language    | Python                            | 3.11+    |
| DB driver   | mysql-connector-python            | Latest   |
| Cache       | Streamlit session_state (v1)      | Built-in |
| Environment | python-dotenv                     | Latest   |

---

## PROJECT STRUCTURE

```
csc/
├── app.py                          # Streamlit entry point
├── .env                            # API keys and DB credentials (gitignored)
├── requirements.txt
├── taxonomy_mapping.py             # PROVIDED — do not regenerate
├── intent_parser_system_prompt.md  # PROVIDED — load at startup
│
├── core/
│   ├── __init__.py
│   ├── intent_parser.py            # Gemini call → structured JSON + ICS
│   ├── fuzzy_preprocessor.py       # Raw text → hints (no API call)
│   ├── session_manager.py          # Session context accumulation
│   ├── cssl.py                     # MySQL FULLTEXT + structured queries
│   ├── casl.py                     # Semantic tag expansion (CASL stage)
│   ├── reranker.py                 # Re-rank pool + generate Line 3 blurbs
│   ├── decision_matrix.py          # 2x2 ICS/RCS routing logic
│   ├── zero_results_advisor.py     # Proximity diagnostic query
│   ├── diversity_filter.py         # Max N results per camp
│   ├── semantic_cache.py           # Parameter-keyed result cache
│   └── interaction_logger.py       # Async click/search logging
│
├── db/
│   ├── __init__.py
│   ├── connection.py               # MySQL connection pool
│   ├── taxonomy_loader.py          # Load activity_tags from DB at startup
│   └── schema.sql                  # Full 7-table schema (see below)
│
├── ui/
│   ├── __init__.py
│   ├── search_bar.py               # Search input component
│   ├── filter_sidebar.py           # Age, type, cost, location filters
│   ├── results_card.py             # Result display (5-line format)
│   ├── clarification_widget.py     # Clarification question UI
│   └── surprise_me.py              # Surprise Me feature
│
└── tests/
    ├── test_intent_parser.py       # QA query set tests
    ├── test_cssl.py                # SQL query tests
    ├── test_fuzzy.py               # Pre-processor tests
    └── qa_queries.py               # 40-query QA test set (see below)
```

---

## ENVIRONMENT VARIABLES (.env)

```env
GEMINI_API_KEY=your_gemini_api_key_here
DB_HOST=localhost
DB_PORT=3306
DB_NAME=csc_db
DB_USER=csc_user
DB_PASSWORD=your_db_password
DB_POOL_SIZE=5
TAXONOMY_REFRESH_HOURS=24
RESULTS_POOL_SIZE=100
DIVERSITY_MAX_PER_CAMP=2
RERANKER_THRESHOLD=15
ICS_HIGH_THRESHOLD=0.70
RCS_HIGH_THRESHOLD=0.70
CACHE_TTL_MINUTES=30
LOG_INTERACTIONS=true
```

---

## DATABASE SCHEMA

File: `db/schema.sql`

```sql
-- ─────────────────────────────────────────────────────────────────────────────
-- CSC Database Schema v1.0
-- MySQL 8.0 InnoDB
-- ─────────────────────────────────────────────────────────────────────────────

CREATE DATABASE IF NOT EXISTS csc_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE csc_db;

-- 1. CAMPS
CREATE TABLE camps (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    camp_name       VARCHAR(150) NOT NULL,
    slug            VARCHAR(200) NOT NULL UNIQUE,
    tier            ENUM('gold','silver','bronze') NOT NULL DEFAULT 'bronze',
    status          TINYINT NOT NULL DEFAULT 1,
    lat             DECIMAL(10,7),
    lon             DECIMAL(10,7),
    city            VARCHAR(80),
    province        VARCHAR(60),
    country         TINYINT NOT NULL DEFAULT 1 COMMENT '1=Canada 2=USA 3=International',
    website         VARCHAR(200),
    description     TEXT,
    mission         VARCHAR(300),
    lgbtq_welcoming TINYINT NOT NULL DEFAULT 0,
    accessibility   TINYINT NOT NULL DEFAULT 0,
    review_count    SMALLINT NOT NULL DEFAULT 0,
    review_avg      FLOAT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FULLTEXT KEY ft_camp (camp_name, description),
    INDEX idx_tier (tier),
    INDEX idx_status (status),
    INDEX idx_city (city),
    INDEX idx_province (province),
    INDEX idx_geo (lat, lon)
) ENGINE=InnoDB;

-- 2. PROGRAMS (replaces legacy sessions)
CREATE TABLE programs (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    camp_id             INT UNSIGNED NOT NULL,
    name                VARCHAR(300) NOT NULL,
    type                VARCHAR(45),
    start_date          DATE,
    end_date            DATE,
    age_from            SMALLINT UNSIGNED,
    age_to              SMALLINT UNSIGNED,
    cost_from           SMALLINT UNSIGNED,
    cost_to             SMALLINT UNSIGNED,
    gender              TINYINT NOT NULL DEFAULT 0 COMMENT '0=Coed 1=Boys 2=Girls',
    is_special_needs    TINYINT NOT NULL DEFAULT 0,
    is_virtual          TINYINT NOT NULL DEFAULT 0,
    is_family           TINYINT NOT NULL DEFAULT 0,
    language_immersion  VARCHAR(45),
    tagline             VARCHAR(100),
    mini_description    VARCHAR(500),
    description         TEXT,
    status              TINYINT NOT NULL DEFAULT 1,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (camp_id) REFERENCES camps(id) ON DELETE CASCADE,
    FULLTEXT KEY ft_program (name, description, mini_description),
    INDEX idx_camp (camp_id),
    INDEX idx_type (type),
    INDEX idx_age (age_from, age_to),
    INDEX idx_cost (cost_from, cost_to),
    INDEX idx_dates (start_date, end_date),
    INDEX idx_status (status)
) ENGINE=InnoDB;

-- 3. ACTIVITY_TAGS (replaces legacy sitems)
CREATE TABLE activity_tags (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    parent_id   INT UNSIGNED,
    domain_id   INT UNSIGNED,
    name        VARCHAR(150) NOT NULL,
    short_name  VARCHAR(125),
    slug        VARCHAR(150) NOT NULL UNIQUE,
    level       TINYINT NOT NULL COMMENT '1=Domain 2=Category 3=Sub-activity',
    tag_type    VARCHAR(20) DEFAULT 'specialty',
    related_ids TEXT COMMENT 'Comma-separated tag IDs for CASL expansion',
    aliases     TEXT COMMENT 'Common user terms — feeds Fuzzy Pre-processor and Intent Parser',
    color_code  VARCHAR(10),
    is_active   TINYINT NOT NULL DEFAULT 1,
    FOREIGN KEY (parent_id) REFERENCES activity_tags(id),
    FULLTEXT KEY ft_tag (name, aliases),
    INDEX idx_slug (slug),
    INDEX idx_level (level),
    INDEX idx_domain (domain_id),
    INDEX idx_active (is_active)
) ENGINE=InnoDB;

-- 4. PROGRAM_TAGS (junction)
CREATE TABLE program_tags (
    program_id  INT UNSIGNED NOT NULL,
    tag_id      INT UNSIGNED NOT NULL,
    is_primary  TINYINT NOT NULL DEFAULT 1,
    PRIMARY KEY (program_id, tag_id),
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES activity_tags(id),
    INDEX idx_tag (tag_id),
    INDEX idx_primary (is_primary)
) ENGINE=InnoDB;

-- 5. CATEGORIES (SEO landing pages)
CREATE TABLE categories (
    id                    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title                 VARCHAR(200) NOT NULL,
    slug                  VARCHAR(250) NOT NULL UNIQUE,
    filter_activity_tags  TEXT,
    filter_city           TEXT,
    filter_province       VARCHAR(100),
    filter_day_overnight  VARCHAR(100),
    filter_gender         VARCHAR(20),
    filter_religion       VARCHAR(50),
    filter_options_sql    TEXT COMMENT 'Legacy complex filter SQL',
    is_active             TINYINT NOT NULL DEFAULT 1,
    INDEX idx_slug (slug),
    INDEX idx_active (is_active)
) ENGINE=InnoDB;

-- 6. TRAITS
CREATE TABLE traits (
    id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name    VARCHAR(150) NOT NULL,
    slug    VARCHAR(150) NOT NULL UNIQUE,
    INDEX idx_slug (slug)
) ENGINE=InnoDB;

INSERT INTO traits (name, slug) VALUES
('Resilience','resilience'),('Curiosity','curiosity'),('Courage','courage'),
('Independence','independence'),('Responsibility','responsibility'),
('Interpersonal Skills','interpersonal-skills'),('Creativity','creativity'),
('Physicality','physicality'),('Generosity','generosity'),('Tolerance','tolerance'),
('Self-regulation','self-regulation'),('Religious Faith','religious-faith');

-- 7. PROGRAM_TRAITS (junction)
CREATE TABLE program_traits (
    program_id      INT UNSIGNED NOT NULL,
    trait_id        INT UNSIGNED NOT NULL,
    justification   VARCHAR(500),
    PRIMARY KEY (program_id, trait_id),
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (trait_id) REFERENCES traits(id)
) ENGINE=InnoDB;

-- 8. INTERACTION_LOG (for future Learning to Rank)
CREATE TABLE interaction_log (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(64),
    raw_query       TEXT,
    intent_json     JSON,
    ics             FLOAT,
    rcs             FLOAT,
    result_count    SMALLINT,
    clicked_program INT UNSIGNED,
    refinement      TINYINT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB;
```

---

## CORE MODULE SPECIFICATIONS

### core/intent_parser.py

```python
"""
Intent Parser — wraps Gemini API call.
Loads system prompt from intent_parser_system_prompt.md at startup.
Injects live taxonomy context from DB (refreshed every 24h).
Returns structured IntentResult dataclass.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
import google.generativeai as genai
from taxonomy_mapping import format_taxonomy_for_prompt, TRAIT_ALIASES, GEO_ALIASES

@dataclass
class IntentResult:
    tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    age_from: int | None = None
    age_to: int | None = None
    city: str | None = None
    cities: list[str] = field(default_factory=list)
    province: str | None = None
    type: str | None = None
    gender: str | None = None
    cost_max: int | None = None
    cost_sensitive: bool = False
    traits: list[str] = field(default_factory=list)
    is_special_needs: bool = False
    is_virtual: bool = False
    language_immersion: str | None = None
    voice: str = "unknown"
    detected_language: str = "en"
    needs_clarification: list[str] = field(default_factory=list)
    needs_geolocation: bool = False
    ics: float = 0.0
    recognized: bool = False
    raw_query: str = ""
    accepted_suggestion: bool = False

def load_system_prompt() -> str:
    """Load Intent Parser system prompt from file. Called once at startup."""
    path = Path("intent_parser_system_prompt.md")
    return path.read_text(encoding="utf-8")

def parse_intent(
    user_query: str,
    session_context: dict | None = None,
    fuzzy_hints: dict | None = None,
    current_date: str | None = None,
    model_name: str = "gemini-1.5-flash"
) -> IntentResult:
    """
    Call Gemini to parse user query into structured search parameters.
    
    Args:
        user_query: Raw user input (any language)
        session_context: Accumulated parameters from prior session turns
        fuzzy_hints: Tag hints from Fuzzy Pre-processor
        current_date: ISO date string for temporal reasoning
        model_name: Gemini model to use
    
    Returns:
        IntentResult dataclass with all extracted parameters
    """
    system_prompt = load_system_prompt()  # cached after first load
    
    # Build user message with context
    context_block = ""
    if session_context and session_context.get("accumulated_params"):
        context_block += f"\nSESSION_CONTEXT: {json.dumps(session_context['accumulated_params'])}"
    if session_context and session_context.get("pending_suggestion"):
        context_block += f"\nPENDING_SUGGESTION: {json.dumps(session_context['pending_suggestion'])}"
    if fuzzy_hints:
        context_block += f"\nFUZZY_HINTS: {json.dumps(fuzzy_hints)}"
    if current_date:
        context_block += f"\nCURRENT_DATE: {current_date}"
    
    user_message = f"{user_query}{context_block}" if context_block else user_query
    
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt
    )
    
    response = model.generate_content(
        user_message,
        generation_config={"temperature": 0.1, "max_output_tokens": 1000}
    )
    
    raw = response.text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    
    parsed = json.loads(raw)
    return IntentResult(**{k: v for k, v in parsed.items() 
                           if k in IntentResult.__dataclass_fields__})
```

---

### core/fuzzy_preprocessor.py

```python
"""
Fuzzy Pre-processor — runs BEFORE Intent Parser, zero API cost.
Catches common misspellings, aliases, and domain-specific terms.
Returns hints dict injected into Intent Parser call.
"""
from taxonomy_mapping import FUZZY_ALIASES, TRAIT_ALIASES, GEO_ALIASES, AGE_ALIASES

def preprocess(raw_query: str) -> dict:
    """
    Scan raw user input for known aliases and return hints.
    
    Returns dict with:
      - tag_hints: list of candidate tag slugs
      - trait_hints: list of candidate trait slugs  
      - geo_expansion: list of cities if regional term found
      - age_bracket: {age_from, age_to} if age language found
      - needs_geolocation: True if "near me" detected
    """
    normalized = raw_query.lower().strip()
    hints = {"tag_hints": [], "trait_hints": [], "geo_expansion": [], 
             "age_bracket": None, "needs_geolocation": False}
    
    # Check geo aliases
    for region, cities in GEO_ALIASES.items():
        if region.lower() in normalized:
            if cities is None:
                hints["needs_geolocation"] = True
            else:
                hints["geo_expansion"] = cities
            break
    
    # Check age aliases
    for term, bracket in AGE_ALIASES.items():
        if term in normalized:
            hints["age_bracket"] = bracket
            break
    
    # Check trait aliases
    for term, slugs in TRAIT_ALIASES.items():
        if term in normalized:
            hints["trait_hints"].extend(s for s in slugs if s not in hints["trait_hints"])
    
    # Check activity aliases (FUZZY_ALIASES)
    for term, mapping in FUZZY_ALIASES.items():
        if not isinstance(mapping, list):
            continue  # skip geo/age/type entries
        if term in normalized:
            hints["tag_hints"].extend(s for s in mapping if s not in hints["tag_hints"])
    
    return {k: v for k, v in hints.items() if v}  # strip empty
```

---

### core/session_manager.py

```python
"""
Session Manager — manages conversational context across turns.
Uses Streamlit session_state. Zero infrastructure cost.
"""
import streamlit as st
from dataclasses import asdict
from core.intent_parser import IntentResult

def init_session():
    """Initialize session state on first load."""
    if "session_context" not in st.session_state:
        st.session_state.session_context = {
            "accumulated_params": {},
            "query_history": [],
            "results_shown": [],
            "pending_suggestion": None,
            "refinement_count": 0,
            "raw_query": ""
        }

def merge_intent(intent: IntentResult) -> dict:
    """
    Merge new intent with accumulated session parameters.
    New values override session values. Session fills gaps.
    Returns merged parameters dict ready for CSSL.
    """
    session = st.session_state.session_context
    acc = session["accumulated_params"].copy()
    new = asdict(intent)
    
    # Override with new non-null values
    for key in ["tags","exclude_tags","age_from","age_to","city","cities",
                "province","type","gender","cost_max","traits",
                "is_special_needs","is_virtual","language_immersion"]:
        if new.get(key):
            acc[key] = new[key]
    
    # Store raw_query immutably
    session["raw_query"] = intent.raw_query
    session["accumulated_params"] = acc
    session["query_history"].append(intent.raw_query)
    session["refinement_count"] += 1
    
    return acc

def store_suggestion(suggestion: dict):
    """Store a structured suggestion for affirmative acceptance."""
    st.session_state.session_context["pending_suggestion"] = suggestion

def clear_suggestion():
    """Clear pending suggestion after execution."""
    st.session_state.session_context["pending_suggestion"] = None

def store_results(program_ids: list[int]):
    """Track which programs user has seen."""
    shown = st.session_state.session_context["results_shown"]
    shown.extend(p for p in program_ids if p not in shown)
```

---

### core/cssl.py

```python
"""
CSSL — Camp SQL Search Logic
Executes structured MySQL queries against programs, camps, activity_tags.
Returns result pool and RCS (Result Confidence Score).
"""
from db.connection import get_connection

def query(params: dict, limit: int = 100) -> tuple[list[dict], float]:
    """
    Execute CSSL query with structured parameters.
    
    Args:
        params: Merged session parameters dict
        limit: Pool size (default 100, use 200 for broad/multi-tag queries)
    
    Returns:
        (results list, rcs float 0.0-1.0)
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    conditions = ["p.status = 1", "c.status = 1"]
    joins = [
        "JOIN camps c ON p.camp_id = c.id",
    ]
    args = {}
    
    # Tags
    tag_ids = resolve_tag_ids(params.get("tags", []), cursor)
    if tag_ids:
        joins.append("JOIN program_tags pt ON p.id = pt.program_id")
        conditions.append("pt.tag_id IN %(tag_ids)s")
        args["tag_ids"] = tag_ids
    
    # Exclude tags
    exclude_ids = resolve_tag_ids(params.get("exclude_tags", []), cursor)
    if exclude_ids:
        conditions.append("""
            p.id NOT IN (
                SELECT program_id FROM program_tags WHERE tag_id IN %(exclude_ids)s
            )
        """)
        args["exclude_ids"] = exclude_ids
    
    # Location
    if params.get("cities"):
        conditions.append("c.city IN %(cities)s")
        args["cities"] = params["cities"]
    elif params.get("city"):
        conditions.append("c.city = %(city)s")
        args["city"] = params["city"]
    if params.get("province"):
        conditions.append("c.province = %(province)s")
        args["province"] = params["province"]
    
    # Age
    if params.get("age_from") and params.get("age_to"):
        conditions.append("p.age_from <= %(age_to)s AND p.age_to >= %(age_from)s")
        args["age_from"] = params["age_from"]
        args["age_to"] = params["age_to"]
    
    # Type
    if params.get("type"):
        conditions.append("p.type = %(type)s")
        args["type"] = params["type"]
    
    # Gender
    gender_map = {"Boys": 1, "Girls": 2, "Coed": 0}
    if params.get("gender") and params["gender"] != "Coed":
        conditions.append("p.gender IN (%(gender)s, 0)")
        args["gender"] = gender_map.get(params["gender"], 0)
    
    # Cost
    if params.get("cost_max"):
        conditions.append("(p.cost_from IS NULL OR p.cost_from <= %(cost_max)s)")
        args["cost_max"] = params["cost_max"]
    
    # Special needs / Virtual
    if params.get("is_special_needs"):
        conditions.append("p.is_special_needs = 1")
    if params.get("is_virtual"):
        conditions.append("p.is_virtual = 1")
    
    # Traits
    trait_ids = resolve_trait_ids(params.get("traits", []), cursor)
    if trait_ids:
        joins.append("""
            JOIN program_traits ptrait ON p.id = ptrait.program_id
        """)
        conditions.append("ptrait.trait_id IN %(trait_ids)s")
        args["trait_ids"] = trait_ids
    
    # Date filter — suppress expired programs
    conditions.append("(p.end_date IS NULL OR p.end_date >= CURDATE())")
    
    where = " AND ".join(conditions)
    joins_str = " ".join(joins)
    
    sql = f"""
        SELECT 
            p.id, p.camp_id, p.name, p.type,
            p.age_from, p.age_to, p.cost_from, p.cost_to,
            p.mini_description, p.description,
            p.start_date, p.end_date,
            c.camp_name, c.tier, c.city, c.province,
            c.lat, c.lon, c.website, c.lgbtq_welcoming, c.accessibility
        FROM programs p
        {joins_str}
        WHERE {where}
        ORDER BY 
            FIELD(c.tier, 'gold', 'silver', 'bronze') ASC,
            c.review_avg DESC
        LIMIT %(limit)s
    """
    args["limit"] = limit
    
    cursor.execute(sql, args)
    results = cursor.fetchall()
    cursor.close()
    
    rcs = calculate_rcs(results, params, tag_ids)
    return results, rcs

def calculate_rcs(results: list, params: dict, tag_ids: list) -> float:
    """Calculate Result Confidence Score based on result quality."""
    if not results:
        return 0.0
    
    count = len(results)
    gold_count = sum(1 for r in results if r.get("tier") == "gold")
    
    # Base score from result count
    if count >= 20:
        base = 0.90
    elif count >= 10:
        base = 0.80
    elif count >= 5:
        base = 0.70
    elif count >= 1:
        base = 0.50
    else:
        return 0.0
    
    # Bonus for Gold tier presence
    if gold_count > 0:
        base = min(1.0, base + 0.05)
    
    # Penalty if we had tags but results have no tag matches
    # (means we broadened and results may be off-topic)
    if tag_ids and count < 3:
        base = max(0.30, base - 0.20)
    
    return round(base, 2)

def resolve_tag_ids(slugs: list[str], cursor) -> list[int]:
    """Convert slug list to DB tag IDs."""
    if not slugs:
        return []
    cursor.execute(
        "SELECT id FROM activity_tags WHERE slug IN %s AND is_active = 1",
        (slugs,)
    )
    return [row["id"] for row in cursor.fetchall()]

def resolve_trait_ids(slugs: list[str], cursor) -> list[int]:
    """Convert trait slug list to DB trait IDs."""
    if not slugs:
        return []
    cursor.execute("SELECT id FROM traits WHERE slug IN %s", (slugs,))
    return [row["id"] for row in cursor.fetchall()]
```

---

### core/decision_matrix.py

```python
"""
2x2 Decision Matrix — routes based on ICS x RCS scores.
Returns routing decision and action parameters.
"""
from dataclasses import dataclass
from enum import Enum

class Route(Enum):
    SHOW_RESULTS    = "show_results"       # ICS high + RCS high
    BROADEN_SEARCH  = "broaden_search"     # ICS high + RCS low
    SHOW_CLARIFY    = "show_and_clarify"   # ICS low + RCS high
    CLARIFY_LOOP    = "clarification_loop" # ICS low + RCS low

@dataclass
class Decision:
    route: Route
    show_results: bool
    invoke_casl: bool
    ask_clarification: bool
    clarification_dimensions: list[str]

ICS_THRESHOLD = 0.70  # from env ICS_HIGH_THRESHOLD
RCS_THRESHOLD = 0.70  # from env RCS_HIGH_THRESHOLD

def decide(ics: float, rcs: float, 
           needs_clarification: list[str] = None) -> Decision:
    """
    Route the search based on ICS and RCS scores.
    
    Quadrants:
    ICS >= 0.70 + RCS >= 0.70 → SHOW_RESULTS
    ICS >= 0.70 + RCS < 0.70  → BROADEN_SEARCH (then CASL if broaden fails)
    ICS < 0.70  + RCS >= 0.70 → SHOW_AND_CLARIFY (show results + soft question)
    ICS < 0.70  + RCS < 0.70  → CLARIFICATION_LOOP
    """
    high_ics = ics >= ICS_THRESHOLD
    high_rcs = rcs >= RCS_THRESHOLD
    clarify = needs_clarification or []
    
    if high_ics and high_rcs:
        return Decision(
            route=Route.SHOW_RESULTS,
            show_results=True,
            invoke_casl=False,
            ask_clarification=False,
            clarification_dimensions=[]
        )
    elif high_ics and not high_rcs:
        return Decision(
            route=Route.BROADEN_SEARCH,
            show_results=False,
            invoke_casl=True,  # after broaden attempt
            ask_clarification=False,
            clarification_dimensions=[]
        )
    elif not high_ics and high_rcs:
        return Decision(
            route=Route.SHOW_CLARIFY,
            show_results=True,
            invoke_casl=False,
            ask_clarification=True,
            clarification_dimensions=clarify[:1]  # max 1 soft question
        )
    else:
        return Decision(
            route=Route.CLARIFY_LOOP,
            show_results=False,
            invoke_casl=False,
            ask_clarification=True,
            clarification_dimensions=clarify[:2]  # max 2 questions
        )
```

---

### core/zero_results_advisor.py

```python
"""
Zero Results Advisor — fires when ICS is high but RCS = 0.0.
Runs proximity-aware diagnostic query to find where activity exists.
Returns structured suggestion stored in session_context.pending_suggestion.
"""
from db.connection import get_connection

def diagnose(tag_ids: list[int], searched_city: str | None, 
             searched_province: str | None,
             user_lat: float | None = None,
             user_lon: float | None = None) -> dict:
    """
    Find where the requested activity exists, closest first.
    Returns one of three response types:
      - geo_broaden_specific: activity exists nearby, suggest city
      - geo_broaden_province: activity exists but far, suggest province-wide
      - no_supply: activity not in DB, suggest alternatives
    """
    if not tag_ids:
        return {"type": "no_tags", "message": "Could not identify the activity requested."}
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Find where activity exists, ordered by proximity if we have coords
    if user_lat and user_lon:
        order_by = "ST_Distance_Sphere(POINT(c.lon, c.lat), POINT(%s, %s)) ASC"
        order_args = [user_lon, user_lat]
    else:
        order_by = "program_count DESC"
        order_args = []
    
    cursor.execute(f"""
        SELECT c.city, c.province, COUNT(p.id) as program_count
        FROM programs p
        JOIN program_tags pt ON p.id = pt.program_id
        JOIN camps c ON p.camp_id = c.id
        WHERE pt.tag_id IN %s AND p.status = 1 AND c.status = 1
          AND (p.end_date IS NULL OR p.end_date >= CURDATE())
        GROUP BY c.city, c.province
        ORDER BY {order_by}
        LIMIT 10
    """, [tuple(tag_ids)] + order_args)
    
    locations = cursor.fetchall()
    cursor.close()
    
    if not locations:
        # Activity genuinely not in DB — suggest alternatives via related tags
        return {
            "type": "no_supply",
            "message": "We don't currently have camps for that activity in our directory.",
            "pending_suggestion": None
        }
    
    nearest = locations[0]
    # Check if nearest is close (same province at minimum)
    same_province = nearest["province"] == searched_province if searched_province else False
    
    if same_province and nearest["city"] != searched_city:
        return {
            "type": "geo_broaden_specific",
            "message": (f"No results found in {searched_city}, but I found "
                       f"{nearest['program_count']} program(s) in {nearest['city']}. "
                       f"Want me to show those instead?"),
            "pending_suggestion": {
                "type": "geo_broaden",
                "to_city": nearest["city"],
                "to_province": nearest["province"],
                "tag_ids": tag_ids
            }
        }
    else:
        province = searched_province or nearest["province"]
        province_total = sum(l["program_count"] for l in locations 
                            if l["province"] == province)
        return {
            "type": "geo_broaden_province",
            "message": (f"No results found near {searched_city or 'your location'}. "
                       f"There are {province_total} programs across {province} though — "
                       f"want me to search province-wide instead?"),
            "pending_suggestion": {
                "type": "geo_broaden_province",
                "to_province": province,
                "tag_ids": tag_ids
            }
        }
```

---

### core/diversity_filter.py

```python
"""Diversity Filter — prevents result clustering by same camp."""

def apply(results: list[dict], max_per_camp: int = 2) -> list[dict]:
    """
    Ensure no more than max_per_camp results from the same camp
    appear in the top results. Preserves tier ordering.
    """
    seen: dict[int, int] = {}
    diverse = []
    overflow = []
    
    for r in results:
        camp_id = r["camp_id"]
        count = seen.get(camp_id, 0)
        if count < max_per_camp:
            diverse.append(r)
            seen[camp_id] = count + 1
        else:
            overflow.append(r)
    
    # Append overflow after diverse results
    # so user can scroll past top 10 to see more from same camp
    return diverse + overflow
```

---

### core/reranker.py

```python
"""
Re-ranker — re-scores result pool against raw_query and generates Line 3 blurbs.
Uses Gemini. Fires when result pool > RERANKER_THRESHOLD (15) or ICS < 0.8.
"""
import json
import google.generativeai as genai

RERANKER_SYSTEM = """You are a search result ranker for a Canadian summer camp directory.
Given a user query and a list of camp programs, re-rank the programs by relevance to the query.
For each program, generate a personalized context blurb (Line 3) of 1-2 sentences explaining
WHY this specific program matches the user's search.

Scoring rules:
- Score against the raw_query, not just extracted tags
- Preserve specificity: "ballet" should rank above "hip-hop" for a ballet query
- Consider the full context including age, location, and trait language
- Gold tier programs get a 5% boost if their relevance score >= 0.70

Return ONLY valid JSON: {"ranked": [{"id": int, "score": float, "blurb": str}]}
Ordered by score descending. Include top 10 only."""

def rerank(results: list[dict], raw_query: str, 
           intent_params: dict, top_n: int = 10) -> list[dict]:
    """
    Re-rank result pool and generate context blurbs.
    Returns top_n results with blurb field added.
    """
    if len(results) <= 3:
        # Not enough results to warrant re-ranking — add generic blurb
        for r in results:
            r["blurb"] = r.get("mini_description", "")
        return results
    
    # Build compact result list for Gemini (mini_description only, not full desc)
    compact = [
        {
            "id": r["id"],
            "name": r["name"],
            "camp": r["camp_name"],
            "city": r["city"],
            "tier": r["tier"],
            "age": f"{r.get('age_from','?')}-{r.get('age_to','?')}",
            "tags": r.get("_tags", []),  # populated by CSSL if needed
            "summary": (r.get("mini_description") or "")[:200]
        }
        for r in results[:20]  # max 20 to reranker
    ]
    
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=RERANKER_SYSTEM
    )
    
    prompt = f"Query: {raw_query}\n\nPrograms:\n{json.dumps(compact, indent=2)}"
    response = model.generate_content(prompt, 
        generation_config={"temperature": 0.2, "max_output_tokens": 2000})
    
    raw = response.text.strip().replace("```json","").replace("```","").strip()
    ranked_data = json.loads(raw)["ranked"]
    
    # Merge blurbs back into results
    id_to_result = {r["id"]: r for r in results}
    final = []
    for item in ranked_data[:top_n]:
        result = id_to_result.get(item["id"])
        if result:
            result["blurb"] = item["blurb"]
            result["rerank_score"] = item["score"]
            final.append(result)
    
    return final
```

---

### app.py (Main Streamlit App)

```python
"""
app.py — CSC Main Entry Point
Camp Search Concierge for OurKids.net
"""
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
import os

from core.intent_parser import parse_intent
from core.fuzzy_preprocessor import preprocess
from core.session_manager import init_session, merge_intent, store_suggestion, clear_suggestion
from core.cssl import query as cssl_query
from core.decision_matrix import decide, Route
from core.zero_results_advisor import diagnose
from core.diversity_filter import apply as diversity_filter
from core.reranker import rerank
from core.semantic_cache import get_cached, set_cache, build_cache_key
from core.interaction_logger import log_search
from ui.results_card import render_result
from ui.clarification_widget import render_clarification
from ui.filter_sidebar import render_filters

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

st.set_page_config(page_title="Camp Search Concierge", page_icon="🏕️", layout="wide")

def main():
    init_session()
    
    st.title("🏕️ Camp Search Concierge")
    st.caption("Find the perfect camp — type anything, in any language")
    
    # Search bar
    user_query = st.chat_input("Search for camps, activities, or programs...")
    
    # Sidebar filters (age, location, type)
    sidebar_filters = render_filters()
    
    if not user_query:
        render_welcome()
        return
    
    # ── PIPELINE ───────────────────────────────────────────────────────────────
    
    # Check for affirmative suggestion acceptance
    session = st.session_state.session_context
    if session.get("pending_suggestion"):
        if is_affirmative(user_query):
            params = session["pending_suggestion"].get("params", {})
            clear_suggestion()
            execute_and_display(params, raw_query=session.get("raw_query",""), is_suggestion=True)
            return
    
    with st.spinner("Searching..."):
        
        # Stage 1: Fuzzy Pre-processor
        hints = preprocess(user_query)
        
        # Stage 2: Intent Parser
        intent = parse_intent(
            user_query,
            session_context=session,
            fuzzy_hints=hints,
            current_date=datetime.now().isoformat()
        )
        
        # Stage 3: Merge with session
        merged_params = merge_intent(intent)
        
        # Stage 4: Semantic Cache check
        cache_key = build_cache_key(merged_params)
        cached = get_cached(cache_key)
        if cached:
            display_results(cached["results"], intent, from_cache=True)
            return
        
        # Stage 5: Query Expansion (related_ids from activity_tags)
        # Handled inside CSSL — tag_ids include children via domain_id lookup
        
        # Stage 6: CSSL
        results, rcs = cssl_query(merged_params)
        
        # Stage 7: Decision Matrix
        decision = decide(intent.ics, rcs, intent.needs_clarification)
        
        # Stage 8: Route decision
        if decision.route == Route.SHOW_RESULTS:
            final = process_results(results, intent, merged_params)
            set_cache(cache_key, {"results": final})
            display_results(final, intent)
        
        elif decision.route == Route.BROADEN_SEARCH:
            # Try Zero Results Advisor first
            tag_ids = resolve_tag_ids_from_slugs(intent.tags)
            advice = diagnose(tag_ids, merged_params.get("city"), 
                            merged_params.get("province"))
            if advice["pending_suggestion"]:
                store_suggestion(advice["pending_suggestion"])
            st.info(advice["message"])
            if results:  # show partial results even if low confidence
                final = process_results(results, intent, merged_params)
                display_results(final, intent, partial=True)
        
        elif decision.route == Route.SHOW_CLARIFY:
            final = process_results(results, intent, merged_params)
            display_results(final, intent)
            if intent.needs_clarification:
                render_clarification(intent.needs_clarification[0], session)
        
        elif decision.route == Route.CLARIFY_LOOP:
            render_clarification(
                intent.needs_clarification[0] if intent.needs_clarification else "activity",
                session
            )
        
        # Log interaction
        log_search(session, intent, rcs, len(results))

def process_results(results, intent, params):
    """Apply diversity filter and re-ranker."""
    diverse = diversity_filter(results, max_per_camp=int(os.getenv("DIVERSITY_MAX_PER_CAMP", 2)))
    threshold = int(os.getenv("RERANKER_THRESHOLD", 15))
    if len(diverse) > threshold or intent.ics < 0.80:
        return rerank(diverse, intent.raw_query, params)
    for r in diverse:
        r["blurb"] = r.get("mini_description", "")
    return diverse[:10]

def display_results(results, intent, from_cache=False, partial=False):
    """Render result cards."""
    if not results:
        st.warning("No results found. Try broadening your search.")
        return
    label = f"{'Partial r' if partial else 'R'}esults ({len(results)})"
    if from_cache:
        label += " ⚡"
    st.subheader(label)
    for r in results:
        render_result(r)

def is_affirmative(text: str) -> bool:
    """Detect affirmative responses to suggestions."""
    AFFIRM = {"yes","sure","ok","okay","go ahead","sounds good","yeah","yep",
              "absolutely","do it","please","of course","definitely","great"}
    normalized = text.lower().strip().rstrip(".,!")
    return normalized in AFFIRM or any(w in normalized.split() for w in AFFIRM)

def render_welcome():
    st.markdown("""
    ### How to search
    - **By activity**: "hockey camps in Toronto for my 10 year old"
    - **By outcome**: "something to help my shy daughter make friends"  
    - **By type**: "overnight camp in Ontario for teenagers"
    - **In any language**: 我的兒子喜歡足球 • Mon fils aime le soccer
    """)

if __name__ == "__main__":
    main()
```

---

## QA TEST QUERY SET

File: `tests/qa_queries.py`

```python
"""
40-query QA test set for CSC Intent Parser and CSSL validation.
Covers: known failure modes, multilingual, edge cases, normal cases.
"""

QA_QUERIES = [
    # ── NORMAL QUERIES ──────────────────────────────────────────────────────
    {"query": "hockey camps in Toronto for my 10 year old",
     "expect_tags": ["hockey"], "expect_city": "Toronto", "expect_age_from": 9},
    
    {"query": "soccer camps in Mississauga",
     "expect_tags": ["soccer"], "expect_city": "Mississauga"},
    
    {"query": "summer dance camps Ottawa",
     "expect_tags": ["dance-multi"], "expect_city": "Ottawa"},
    
    {"query": "coding camp for teenagers in Vancouver",
     "expect_tags": ["programming-multi"], "expect_age_from": 13},
    
    {"query": "robotics camps for kids",
     "expect_tags": ["robotics"]},
    
    {"query": "art camp Toronto",
     "expect_tags": ["arts-multi", "visual-arts-multi"]},  # either acceptable
    
    {"query": "gymnastics summer camp girls",
     "expect_tags": ["gymnastics"], "expect_gender": "Girls"},
    
    # ── FIX 14: SKATING DISAMBIGUATION ──────────────────────────────────────
    {"query": "skating camps in Hamilton",
     "expect_tags_include": ["figure-skating"],
     "expect_tags_not": ["skateboarding"],
     "note": "Fix 14: skating → figure-skating, not skateboarding"},
    
    {"query": "skateboarding camp",
     "expect_tags": ["skateboarding"],
     "expect_tags_not": ["figure-skating"],
     "note": "Fix 14: skateboarding is explicit"},
    
    # ── FIX 12/13: SEA KAYAKING ─────────────────────────────────────────────
    {"query": "sea kayaking camps for kids",
     "expect_tags": ["kayaking-sea-kayaking"],
     "note": "Fix 12/13: sea qualifier preserved"},
    
    {"query": "kayaking camp",
     "expect_tags_include": ["kayaking-sea-kayaking"],
     "note": "General kayaking — both slugs acceptable"},
    
    # ── FIX 11: BALLET RANKING ───────────────────────────────────────────────
    {"query": "ballet camps in Toronto",
     "expect_tags": ["ballet"],
     "expect_tags_not": ["hip-hop", "dance-multi"],
     "note": "Fix 11: specific ballet, not generic dance"},
    
    # ── FIX 2: SYNONYM MAP ───────────────────────────────────────────────────
    {"query": "puppy camps in Belleville",
     "expect_tags": ["animals"],
     "expect_city": "Belleville",
     "note": "Fix 2: puppy → animals"},
    
    # ── FIX 5: UMBRELLA CATEGORIES ──────────────────────────────────────────
    {"query": "sports camps in Toronto",
     "expect_tags_include": ["sport-multi"],
     "note": "Fix 5: umbrella sports tag"},
    
    {"query": "arts camps",
     "expect_tags_include": ["arts-multi"],
     "note": "Fix 5: umbrella arts tag"},
    
    # ── TRAIT LANGUAGE ───────────────────────────────────────────────────────
    {"query": "camp for my shy 9 year old daughter to make friends",
     "expect_traits": ["interpersonal-skills"],
     "expect_gender": "Girls",
     "expect_age_from": 8,
     "note": "Outcome language → traits"},
    
    {"query": "build resilience and confidence at summer camp",
     "expect_traits_include": ["resilience", "courage"],
     "note": "Developmental language → multiple traits"},
    
    {"query": "camps that build leadership Ontario",
     "expect_tags_include": ["leadership-multi"],
     "expect_province": "Ontario",
     "note": "Leadership is a tag not a trait"},
    
    # ── NEGATIVE INTENT ─────────────────────────────────────────────────────
    {"query": "hockey camp not too competitive",
     "expect_tags": ["hockey"],
     "expect_exclude_tags_include": ["sports-instructional-and-training"],
     "note": "Negative intent extraction"},
    
    # ── MULTILINGUAL ─────────────────────────────────────────────────────────
    {"query": "我的兒子喜歡足球，有沒有夏令營？",
     "expect_tags": ["soccer"],
     "expect_language": "zh-Hant",
     "note": "Traditional Chinese — soccer"},
    
    {"query": "mon fils aime le hockey, camps à Toronto",
     "expect_tags": ["hockey"],
     "expect_city": "Toronto",
     "expect_language": "fr",
     "note": "Canadian French — hockey Toronto"},
    
    {"query": "ਮੇਰੀ ਧੀ ਡਾਂਸ ਕੈਂਪ ਲੱਭ ਰਹੀ ਹੈ",
     "expect_tags_include": ["dance-multi"],
     "expect_language": "pa",
     "note": "Punjabi — dance camp"},
    
    {"query": "내 아들이 수영 캠프를 원해요 토론토",
     "expect_tags": ["swimming"],
     "expect_city": "Toronto",
     "expect_language": "ko",
     "note": "Korean — swimming camp Toronto"},
    
    # ── GEO EXPANSION ────────────────────────────────────────────────────────
    {"query": "hockey camps in the GTA",
     "expect_tags": ["hockey"],
     "expect_cities_include": ["Toronto", "Mississauga"],
     "note": "GTA expansion"},
    
    {"query": "camps in cottage country",
     "expect_cities_include": ["Muskoka", "Haliburton"],
     "note": "Cottage country geo alias"},
    
    # ── AGE LANGUAGE ─────────────────────────────────────────────────────────
    {"query": "camps for tweens",
     "expect_age_from": 10, "expect_age_to": 12,
     "note": "Age alias: tweens"},
    
    {"query": "toddler programs",
     "expect_age_from": 2, "expect_age_to": 4,
     "note": "Age alias: toddler"},
    
    # ── TYPE DETECTION ───────────────────────────────────────────────────────
    {"query": "overnight hockey camp Ontario",
     "expect_tags": ["hockey"],
     "expect_type": "Overnight",
     "note": "Overnight type detection"},
    
    {"query": "sleepaway camp for girls",
     "expect_type": "Overnight",
     "expect_gender": "Girls",
     "note": "Sleepaway = Overnight"},
    
    # ── EDGE CASES ───────────────────────────────────────────────────────────
    {"query": "camp",
     "expect_ics_max": 0.20,
     "note": "Single word — should be low ICS"},
    
    {"query": "something fun for my kid",
     "expect_ics_max": 0.50,
     "note": "Vague — low ICS, no tags"},
    
    {"query": "xyzzy camps",
     "expect_recognized": False,
     "expect_ics_max": 0.30,
     "note": "Nonsense word — recognized=False"},
    
    # ── CHILD VOICE ──────────────────────────────────────────────────────────
    {"query": "minecraft camp where u make games",
     "expect_tags_include": ["minecraft"],
     "expect_voice": "child",
     "note": "Child voice detection"},
    
    {"query": "i wanna do hockey its so fun",
     "expect_tags": ["hockey"],
     "expect_voice": "child",
     "note": "Child voice first person"},
    
    # ── SPECIAL CASES ────────────────────────────────────────────────────────
    {"query": "camps for kids with autism Toronto",
     "expect_is_special_needs": True,
     "expect_city": "Toronto",
     "note": "Special needs flag"},
    
    {"query": "online coding camp",
     "expect_tags_include": ["programming-multi"],
     "expect_is_virtual": True,
     "expect_type": "Virtual Program",
     "note": "Virtual program detection"},
    
    {"query": "ESL summer camp Ontario",
     "expect_language_immersion": "English",
     "expect_province": "Ontario",
     "note": "Language immersion detection"},
    
    {"query": "Christian overnight camp for boys",
     "expect_type": "Overnight",
     "expect_gender": "Boys",
     "expect_traits_include": ["religious-faith"],
     "note": "Religion → trait"},
    
    # ── FOLLOW-UP SIMULATION ─────────────────────────────────────────────────
    {"query": "what about overnight?",
     "session_context": {"accumulated_params": {"tags": ["hockey"], "city": "Toronto"}},
     "expect_type": "Overnight",
     "expect_city": "Toronto",  # should inherit from session
     "note": "Fix 6: follow-up inherits location"},
    
    {"query": "sure go ahead",
     "session_context": {"pending_suggestion": {"type": "geo_broaden", "to_city": "Toronto"}},
     "expect_accepted_suggestion": True,
     "note": "Fix 10: affirmative accepts pending suggestion"},
]
```

---

## REQUIREMENTS.TXT

```
streamlit>=1.35.0
google-generativeai>=0.7.0
mysql-connector-python>=8.4.0
python-dotenv>=1.0.0
```

---

## STARTUP SEQUENCE

On `streamlit run app.py`:

1. Load `.env` — API keys and DB config
2. Configure Gemini API key
3. Load `intent_parser_system_prompt.md` into memory (cached)
4. Load `taxonomy_mapping.py` module (already loaded as import)
5. Connect to MySQL — verify schema exists
6. Load `activity_tags` from DB → merge with `taxonomy_mapping.TAXONOMY_CONTEXT`
   (DB is authoritative; `taxonomy_mapping.py` is the seed/fallback)
7. Start Streamlit UI

---

## CLAUDE CODE PLAN MODE INSTRUCTIONS

When running `claude /plan` with this spec, implement in this order:

### Phase 1 — Foundation (no UI yet)
1. `db/schema.sql` — create all 7 tables + indexes
2. `db/connection.py` — MySQL connection pool
3. `taxonomy_mapping.py` — already provided, do not regenerate
4. `core/fuzzy_preprocessor.py` — pure Python, no dependencies
5. `core/session_manager.py` — Streamlit session_state

### Phase 2 — Search Pipeline
6. `core/intent_parser.py` — Gemini wrapper
7. `core/cssl.py` — MySQL query engine  
8. `core/decision_matrix.py` — routing logic
9. `core/zero_results_advisor.py` — diagnostic query
10. `core/diversity_filter.py` — pure Python

### Phase 3 — Quality Layer
11. `core/reranker.py` — Gemini re-ranker
12. `core/semantic_cache.py` — parameter-keyed cache
13. `core/interaction_logger.py` — async DB logging

### Phase 4 — UI
14. `ui/results_card.py` — 5-line result format
15. `ui/filter_sidebar.py` — sidebar filters
16. `ui/clarification_widget.py` — clarification UI
17. `ui/surprise_me.py` — Surprise Me feature
18. `app.py` — main Streamlit orchestrator

### Phase 5 — Tests
19. `tests/qa_queries.py` — already provided
20. `tests/test_intent_parser.py` — run QA queries against Intent Parser
21. `tests/test_cssl.py` — SQL query validation
22. `tests/test_fuzzy.py` — pre-processor validation

---

## KEY ARCHITECTURAL RULES (do not violate)

1. `raw_query` is ALWAYS preserved unchanged from Intent Parser output through to Re-ranker
2. Session `accumulated_params` MERGE — never replace
3. Re-ranker scores against `raw_query`, not extracted `tags`
4. CSSL fetches pool of 100, Diversity Filter reduces, Re-ranker selects top 10
5. CASL only fires in ICS_HIGH + RCS_LOW quadrant, after Zero Results Advisor
6. Gemini is called in 3 places only: Intent Parser, CASL expansion, Re-ranker
7. `taxonomy_mapping.py` is the pre-populated seed — DB is authoritative at runtime
8. All suggestions stored as structured objects in `session_context.pending_suggestion`
9. Never regex-parse response text for structured data — use typed objects
10. Temporal filter (suppress expired programs) runs in CSSL SQL, not post-processing
