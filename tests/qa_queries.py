"""
tests/qa_queries.py
40-query QA test set for CSC Intent Parser and CSSL validation.
Covers: known failure modes, multilingual, edge cases, normal cases.
"""

QA_QUERIES = [
    # ── NORMAL QUERIES ──────────────────────────────────────────────────────
    {
        "query": "hockey camps in Toronto for my 10 year old",
        "expect_tags": ["hockey"],
        "expect_city": "Toronto",
        "expect_age_from": 9,
    },
    {
        "query": "soccer camps in Mississauga",
        "expect_tags": ["soccer"],
        "expect_city": "Mississauga",
    },
    {
        "query": "summer dance camps Ottawa",
        "expect_tags": ["dance-multi"],
        "expect_city": "Ottawa",
    },
    {
        "query": "coding camp for teenagers in Vancouver",
        "expect_tags": ["programming-multi"],
        "expect_age_from": 13,
    },
    {
        "query": "robotics camps for kids",
        "expect_tags": ["robotics"],
    },
    {
        "query": "art camp Toronto",
        "expect_tags": ["arts-multi", "visual-arts-multi"],  # either acceptable
    },
    {
        "query": "gymnastics summer camp girls",
        "expect_tags": ["gymnastics"],
        "expect_gender": "Girls",
    },
    # ── FIX 14: SKATING DISAMBIGUATION ──────────────────────────────────────
    {
        "query": "skating camps in Hamilton",
        "expect_tags_include": ["figure-skating"],
        "expect_tags_not": ["skateboarding"],
        "note": "Fix 14: skating → figure-skating, not skateboarding",
    },
    {
        "query": "skateboarding camp",
        "expect_tags": ["skateboarding"],
        "expect_tags_not": ["figure-skating"],
        "note": "Fix 14: skateboarding is explicit",
    },
    # ── FIX 12/13: SEA KAYAKING ─────────────────────────────────────────────
    {
        "query": "sea kayaking camps for kids",
        "expect_tags": ["kayaking-sea-kayaking"],
        "note": "Fix 12/13: sea qualifier preserved",
    },
    {
        "query": "kayaking camp",
        "expect_tags_include": ["kayaking-sea-kayaking"],
        "note": "General kayaking — both slugs acceptable",
    },
    # ── FIX 11: BALLET RANKING ───────────────────────────────────────────────
    {
        "query": "ballet camps in Toronto",
        "expect_tags": ["ballet"],
        "expect_tags_not": ["hip-hop", "dance-multi"],
        "note": "Fix 11: specific ballet, not generic dance",
    },
    # ── FIX 2: SYNONYM MAP ───────────────────────────────────────────────────
    {
        "query": "puppy camps in Belleville",
        "expect_tags": ["animals"],
        "expect_city": "Belleville",
        "note": "Fix 2: puppy → animals",
    },
    # ── FIX 5: UMBRELLA CATEGORIES ──────────────────────────────────────────
    {
        "query": "sports camps in Toronto",
        "expect_tags_include": ["sport-multi"],
        "note": "Fix 5: umbrella sports tag",
    },
    {
        "query": "arts camps",
        "expect_tags_include": ["arts-multi"],
        "note": "Fix 5: umbrella arts tag",
    },
    # ── TRAIT LANGUAGE ───────────────────────────────────────────────────────
    {
        "query": "camp for my shy 9 year old daughter to make friends",
        "expect_traits": ["interpersonal-skills"],
        "expect_gender": "Girls",
        "expect_age_from": 8,
        "note": "Outcome language → traits",
    },
    {
        "query": "build resilience and confidence at summer camp",
        "expect_traits_include": ["resilience", "courage"],
        "note": "Developmental language → multiple traits",
    },
    {
        "query": "camps that build leadership Ontario",
        "expect_tags_include": ["leadership-multi"],
        "expect_province": "Ontario",
        "note": "Leadership is a tag not a trait",
    },
    # ── NEGATIVE INTENT ─────────────────────────────────────────────────────
    {
        "query": "hockey camp not too competitive",
        "expect_tags": ["hockey"],
        "expect_exclude_tags_include": ["sports-instructional-training"],
        "note": "Negative intent extraction",
    },
    # ── MULTILINGUAL ─────────────────────────────────────────────────────────
    {
        "query": "我的兒子喜歡足球，有沒有夏令營？",
        "expect_tags": ["soccer"],
        "expect_language": "zh-Hant",
        "note": "Traditional Chinese — soccer",
    },
    {
        "query": "mon fils aime le hockey, camps à Toronto",
        "expect_tags": ["hockey"],
        "expect_city": "Toronto",
        "expect_language": "fr",
        "note": "Canadian French — hockey Toronto",
    },
    {
        "query": "ਮੇਰੀ ਧੀ ਡਾਂਸ ਕੈਂਪ ਲੱਭ ਰਹੀ ਹੈ",
        "expect_tags_include": ["dance-multi"],
        "expect_language": "pa",
        "note": "Punjabi — dance camp",
    },
    {
        "query": "내 아들이 수영 캠프를 원해요 토론토",
        "expect_tags": ["swimming"],
        "expect_city": "Toronto",
        "expect_language": "ko",
        "note": "Korean — swimming camp Toronto",
    },
    # ── GEO EXPANSION ────────────────────────────────────────────────────────
    {
        "query": "hockey camps in the GTA",
        "expect_tags": ["hockey"],
        "expect_cities_include": ["Toronto", "Mississauga"],
        "note": "GTA expansion",
    },
    {
        "query": "camps in cottage country",
        "expect_cities_include": ["Bracebridge", "Haliburton"],
        "note": "Cottage country geo alias — model resolves to actual towns",
    },
    # ── AGE LANGUAGE ─────────────────────────────────────────────────────────
    {
        "query": "camps for tweens",
        "expect_age_from": 10,
        "expect_age_to": 12,
        "note": "Age alias: tweens",
    },
    {
        "query": "toddler programs",
        "expect_age_from": 2,
        "expect_age_to": 4,
        "note": "Age alias: toddler",
    },
    # ── TYPE DETECTION ───────────────────────────────────────────────────────
    {
        "query": "overnight hockey camp Ontario",
        "expect_tags": ["hockey"],
        "expect_type": "Overnight",
        "note": "Overnight type detection",
    },
    {
        "query": "sleepaway camp for girls",
        "expect_type": "Overnight",
        "expect_gender": "Girls",
        "note": "Sleepaway = Overnight",
    },
    # ── EDGE CASES ───────────────────────────────────────────────────────────
    {
        "query": "camp",
        "expect_ics_max": 0.20,
        "note": "Single word — should be low ICS",
    },
    {
        "query": "something fun for my kid",
        "expect_ics_max": 0.50,
        "note": "Vague — low ICS, no tags",
    },
    {
        "query": "xyzzy camps",
        "expect_recognized": False,
        "expect_ics_max": 0.30,
        "note": "Nonsense word — recognized=False",
    },
    # ── CHILD VOICE ──────────────────────────────────────────────────────────
    {
        "query": "minecraft camp where u make games",
        "expect_tags_include": ["minecraft"],
        "expect_voice": "child",
        "note": "Child voice detection",
    },
    {
        "query": "i wanna do hockey its so fun",
        "expect_tags": ["hockey"],
        "expect_voice": "child",
        "note": "Child voice first person",
    },
    # ── SPECIAL CASES ────────────────────────────────────────────────────────
    {
        "query": "camps for kids with autism Toronto",
        "expect_is_special_needs": True,
        "expect_city": "Toronto",
        "note": "Special needs flag",
    },
    {
        "query": "online coding camp",
        "expect_tags_include": ["programming-multi"],
        "expect_is_virtual": True,
        "expect_type": "Virtual Program",
        "note": "Virtual program detection",
    },
    {
        "query": "ESL summer camp Ontario",
        "expect_language_immersion": "English",
        "expect_province": "Ontario",
        "note": "Language immersion detection",
    },
    {
        "query": "Christian overnight camp for boys",
        "expect_type": "Overnight",
        "expect_gender": "Boys",
        "expect_traits_include": ["religious-faith"],
        "note": "Religion → trait",
    },
    # ── FOLLOW-UP SIMULATION ─────────────────────────────────────────────────
    {
        "query": "what about overnight?",
        "session_context": {"accumulated_params": {"tags": ["hockey"], "city": "Toronto"}},
        "expect_type": "Overnight",
        "expect_city": "Toronto",  # should inherit from session
        "note": "Fix 6: follow-up inherits location",
    },
    {
        "query": "sure go ahead",
        "session_context": {"pending_suggestion": {"type": "geo_broaden", "to_city": "Toronto"}},
        "expect_accepted_suggestion": True,
        "note": "Fix 10: affirmative accepts pending suggestion",
    },
    # ── V1 QA REMEDIATION — 8 NEW CASES ─────────────────────────────────────
    {
        "query": "overnight all girls camp Ontario",
        "expect_gender": "Girls",
        "expect_type": "Overnight",
        "note": "V1 QA: All girls = gender=Girls only, no coed",
    },
    {
        "query": "horse camps in Ontario",
        "expect_tags": ["horseback-riding-equestrian"],
        "note": "V1 QA: Horse → equestrian slug",
    },
    {
        "query": "ballet camps for kids in Vaughan",
        "expect_tags": ["ballet"],
        "expect_city": "Vaughan",
        "note": "V1 QA: Ballet is specific sub-slug of dance",
    },
    {
        "query": "french tutoring camps",
        "expect_tags": ["language-instruction"],
        "note": "V1 QA: French tutoring → language-instruction",
    },
    {
        "query": "university prep camps in toronto",
        "expect_tags_include": ["test-preparation"],
        "expect_city": "Toronto",
        "note": "V1 QA: University prep → test-preparation + credit-courses",
    },
    {
        "query": "camps that build self-confidence",
        "expect_traits_include": ["empowerment"],
        "note": "V1 QA: Self-confidence → empowerment trait",
    },
    {
        "query": "financial literacy camps in toronto",
        "expect_tags": ["financial-literacy"],
        "expect_city": "Toronto",
        "note": "V1 QA: Financial literacy slug direct match",
    },
    {
        "query": "cheer camps in etobicoke",
        "expect_tags": ["cheer"],
        "note": "V1 QA: Cheer + etobicoke geo",
    },
]
