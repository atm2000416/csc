#!/usr/bin/env python3
"""
db/tag_from_campsca_pages.py

Scrapes ALL camps.ca activity category pages (sourced from
csc_collaterals/ALL CAMP PAGES CURRENT.xlsx), extracts camp IDs, and inserts
the corresponding activity_tags into program_tags for every active program
belonging to those camps.

Run:
    python3 db/tag_from_campsca_pages.py [--dry-run]

This is an idempotent backfill — INSERT IGNORE means re-runs are safe.
The automated OurKids sync (sync_from_source.py) will keep tags current once live.
"""

import re
import ssl
import sys
import time
import urllib.request
import urllib.error

_SSL_CTX = ssl._create_unverified_context()  # macOS Python lacks system certs

# ── SQLwebitems display name → our activity_tag slug ───────────────────────
# Skips special-needs conditions (Autism, ADHD, etc.) and age-bracket pages.
WEBITEMS_TO_SLUG: dict[str, str] = {
    "3D Design":                        "3d-design",
    "3D Printing":                      "3d-printing",
    "Academic/Tutoring (multi)":        "academic-tutoring-multi",
    "Acro Dance":                       "acro-dance",
    "Acting (Film & TV)":               "acting-film-tv",
    "AI (Artificial Intelligence)":     "ai-artificial-intelligence",
    "Animals":                          "animals",
    "Animation":                        "animation",
    "Archery":                          "archery",
    "Architecture":                     "architecture",
    "Arduino":                          "arduino",
    "Arts & Crafts":                    "arts-crafts",
    "Aviation":                         "aviation",
    "Badminton":                        "badminton",
    "Baking/Decorating":                "baking-decorating",
    "Ball Sports (multi)":              "ball-sports-multi",
    "Ballet":                           "ballet",
    "Ballroom":                         "ballroom",
    "Baseball/Softball":                "baseball-softball",
    "Basketball":                       "basketball",
    "BMX/Motocross":                    "bmx-motocross",
    "Board Sailing":                    "board-sailing",
    "Breakdancing":                     "breakdancing",
    "Bronze Cross":                     "bronze-cross",
    "Canoeing":                         "canoeing",
    "Cartooning":                       "cartooning",
    "Ceramics":                         "ceramics",
    "Chess":                            "chess",
    "Cheer":                            "cheer",
    "CIT/LIT Program":                  "cit-lit-program",
    "Circus":                           "circus",
    "Comedy":                           "comedy",
    "Cooking":                          "cooking",
    "Creative writing":                 "creative-writing",
    "Credit Courses":                   "credit-courses",
    "Cricket":                          "cricket",
    "Cycling":                          "cycling",
    "Dance (multi)":                    "dance-multi",
    "Debate":                           "debate",
    "Diving":                           "diving",
    "Drawing":                          "drawing",
    "Empowerment":                      "empowerment",
    "Engineering":                      "engineering",
    "Entrepreneurship":                 "entrepreneurship",
    "Extreme Sports (multi)":           "extreme-sports-multi",
    "Fantasy (multi)":                  "fantasy-multi",
    "Fashion Design":                   "fashion-design",
    "Fencing":                          "fencing",
    "Figure Skating":                   "figure-skating",
    "Financial Literacy":               "financial-literacy",
    "First-aid/lifesaving":             "first-aid-lifesaving",
    "Filmmaking":                       "filmmaking",
    "Fishing":                          "fishing",
    "Flag Football":                    "flag-football",
    "Football":                         "football",
    "Gaga":                             "gaga",
    "Gaming":                           "gaming",
    "Glee":                             "glee",
    "Golf":                             "golf",
    "Guitar":                           "guitar",
    "Gymnastics":                       "gymnastics",
    "Harry Potter":                     "harry-potter",
    "Hiking":                           "hiking",
    "Hip Hop":                          "hip-hop",
    "Hockey":                           "hockey",
    "Horseback Riding/Equestrian":      "horseback-riding-equestrian",
    "Ice Skating":                      "ice-skating",
    "Instructor lead (group)":          "instructor-led-group",
    "Instructor lead (one on one)":     "instructor-led-one-on-one",
    "Jam Camp":                         "jam-camp",
    "JAVA":                             "java",
    "Jazz":                             "jazz",
    "Karate":                           "karate",
    "Kayaking/Sea Kayaking":            "kayaking-sea-kayaking",
    "Lacrosse":                         "lacrosse",
    "Language Instruction":             "language-instruction",
    "Leadership (multi)":               "leadership-multi",
    "Leadership Training":              "leadership-training",
    "LEGO":                             "lego",
    "Magic":                            "magic",
    "Makeup Artistry":                  "makeup-artistry",
    "Makerspace":                       "makerspace",
    "Marine Biology":                   "marine-biology",
    "Martial Arts":                     "martial-arts",
    "Math":                             "math",
    "Medical Science":                  "medical-science",
    "Meditation":                       "meditation",
    "Mindfulness Training":             "mindfulness-training",
    "Minecraft":                        "minecraft",
    "Military":                         "military",
    "Modeling":                         "modeling",
    "Mountain Biking":                  "mountain-biking",
    "Music (multi)":                    "music-multi",
    "Music Recording":                  "music-recording",
    "Musical instrument training":      "musical-instrument-training",
    "Musical Theatre":                  "musical-theatre",
    "Nature/Environment":               "nature-environment",
    "Ninja Warrior":                    "ninja-warrior",
    "Paintball":                        "paintball",
    "Painting":                         "painting",
    "Parkour":                          "parkour",
    "Percussion":                       "percussion",
    "Performing Arts (multi)":          "performing-arts-multi",
    "Photography":                      "photography",
    "Piano":                            "piano",
    "Pickleball":                       "pickleball",
    "Ping Pong":                        "ping-pong",
    "Pottery":                          "pottery",
    "Programming (multi)":              "programming-multi",
    "Public Speaking":                  "public-speaking",
    "Python":                           "python",
    "Reading":                          "reading",
    "Robotics":                         "robotics",
    "Rock Climbing":                    "rock-climbing",
    "Roblox":                           "roblox",
    "Rollerblading":                    "rollerblading",
    "Ropes Course":                     "ropes-course",
    "Rowing":                           "rowing",
    "Rugby":                            "rugby",
    "Safari":                           "safari",
    "Sailing/Marine Skills":            "sailing-marine-skills",
    "Science (multi)":                  "science-multi",
    "Scratch":                          "scratch",
    "Sewing":                           "sewing",
    "Skateboarding":                    "skateboarding",
    "Skiing":                           "skiing",
    "Skilled Trades Activities":        "skilled-trades-activities",
    "Soccer":                           "soccer",
    "Social Justice":                   "social-justice",
    "Songwriting":                      "songwriting",
    "Space":                            "space",
    "Sports-Instructional and Training": "sports-instructional-training",
    "Squash":                           "squash",
    "STEAM":                            "steam",
    "STEM":                             "stem",
    "Strength and Conditioning":        "strength-and-conditioning",
    "Super Camp":                       "super-camp",
    "Surfing":                          "surfing",
    "Survival skills":                  "survival-skills",
    "Swimming":                         "swimming",
    "Taekwondo":                        "taekwondo",
    "Technology":                       "technology",
    "Tennis":                           "tennis",
    "Test Preparation":                 "test-preparation",
    "Theatre Arts":                     "theatre-arts",
    "Track and Field":                  "track-and-field",
    "Trampoline":                       "trampoline",
    "Travel":                           "travel",
    "Ultimate Frisbee":                 "ultimate-frisbee",
    "Videography":                      "videography",
    "Video Game Design":                "video-game-design",
    "Visual Arts (multi)":              "visual-arts-multi",
    "Vocal Training / Singing":         "vocal-training-singing",
    "Volleyball":                       "volleyball",
    "Water Sports (multi)":             "water-sports-multi",
    "Waterskiing/Wakeboarding":         "waterskiing-wakeboarding",
    "Web Design":                       "web-design",
    "Web Development":                  "web-development",
    "Weight Loss Program":              "weight-loss-program",
    "Whitewater Rafting":               "whitewater-rafting",
    "Wilderness Out-tripping":          "wilderness-out-tripping",
    "Wilderness Skills":                "wilderness-skills",
    "Woodworking":                      "woodworking",
    "Writing":                          "writing",
    "Yoga":                             "yoga",
    "Zip Line":                         "zip-line",
    "Zoology":                          "zoology",
    # ── Specialty-level (sitems isact=0) — broad camp categories ──
    "Health & Fitness":                     "health-fitness",
    "Education":                            "education",
    "Sports":                               "sports",
    "Arts":                                 "arts",
    "Adventure":                            "adventure",
    "Computer (multi)":                     "computer-multi",
    "Sport (multi)":                        "sport-multi",
    "Arts (multi)":                         "arts-multi",
    "Computers & Tech":                     "computers-tech",
    "Traditional (multi activity)":         "traditional",
    "Adventure (multi)":                    "adventure-multi",
    "Immersion":                            "language-immersion",
    "Health and Fitness (multi)":           "health-fitness-multi",
    "Education (multi)":                    "education-multi",
    "Bilingual":                            "language-instruction",
    # ── Additional activities from sitems not in webitems ──
    "Dodgeball":                            "dodgeball",
    "Forensic Science":                     "forensic-science",
    "Journalism":                           "journalism",
    "Snowboarding":                         "snowboarding",
    "Storytelling":                         "storytelling",
    "Disc Golf":                            "disc-golf",
    "Water Polo":                           "water-polo",
    # ── ok_sitems with EXACT name matches in activity_tags ──
    "String":                               "string",
    "Set and Costume Design":               "set-and-costume-design",
    "Playwriting":                          "playwriting",
    "Sculpture":                            "sculpture",
    "Star Wars":                            "star-wars",
    "Comic Art":                            "comic-art",
    "Drone Technology":                     "drone-technology",
    "Virtual Reality":                      "virtual-reality",
    "Mechatronics":                         "mechatronics",
    "Health Science":                       "health-science",
    "Nutrition":                            "nutrition",
    "Pilates":                              "pilates",
    "Papier-mache":                         "papier-mache",
    "Podcasting":                           "podcasting",
    "Puppetry":                             "puppetry",
    "YouTube Vlogging":                     "youtube-vlogging",
    "Knitting and Crochet":                 "knitting-and-crochet",
    "Dungeons and Dragons":                 "dungeons-and-dragons",
    "Scooter":                              "scooter",
    "micro:bit":                            "micro-bit",
    "Video Game Development":               "video-game-development",
    "Pygame":                               "pygame",
    "C++":                                  "c-plus-plus",
    "C#":                                   "c-sharp",
    "Mixed Media":                          "mixed-media",
    "Medieval":                             "medieval",
    "Contemporary":                         "contemporary",
    "Tap":                                  "tap",
    "Modern":                               "modern",
    "Lyrical":                              "lyrical",
    "Technique":                            "technique",
    "Preschool dance":                      "preschool-dance",
    "Essay Writing":                        "essay-writing",
    "Swift (Apple)":                        "swift-apple",
    "Stand Up Paddle Boarding":             "stand-up-paddle-boarding",
    "Tubing":                               "tubing",
    "Behavioral therapy":                   "behavioral-therapy",
    "DJing":                                "djing",
    "Board Games":                          "board-games",
    "Logical thinking":                     "logical-thinking",
    "Urban exploration":                    "urban-exploration",
    "Meteorology":                          "meteorology",
    # ── ok_sitems with close/variant name matches ──
    "Arts  (multi)":                        "arts-multi",
    "Superhero/Marvel/DC":                  "superhero-marvel-dc",
    "Rasberry Pi":                          "raspberry-pi",
    "Archaeology/Paleontology":             "archaeology-paleontology",
    "Team Building":                        "leadership-multi",
    "French Language":                      "language-instruction",
    # Special needs / medical — no activity tag mapping:
    # ADD/ADHD, Autism Spectrum Disorder, Cancer, Diabetes, Down Syndrome,
    # Dyslexia, Intellectual disability, Physical Disability, Vision loss,
    # Troubled Teens, Aspergers Syndrome
    # Meta / non-activity — not mapped:
    # International Camp (outside Canada)
    # Age brackets — not activity tags:
    # Ages 4 to 6, Ages 7 to 9, Ages 10 to 12, Ages 13 to 15, Ages 16+
}


# ── URL overrides ─────────────────────────────────────────────────────────────
# Two classes of broken URLs in the Excel:
#   1. /camp/* pages — newer SEO pages with only a general all-camps dropdown
#   2. Dash-format .php pages (e.g. /golf-camps.php) — redirect to homepage
# Both return all 276 camps regardless of activity.
# Map them to working underscore/specific .php equivalents.
CAMP_PAGE_OVERRIDES: dict[str, str] = {
    # ── Dash-format .php → correct underscore versions ──
    "/baseball-camps.php":          "/baseball_camps.php",
    "/basketball-camps.php":        "/basketball-summer-camps.php",
    "/cheerleading-camps.php":      "/cheerleading-summer-camps.php",
    "/dance-camps.php":             "/dance_camps.php",
    "/dance-programs.php":          "/dance_camps.php",
    "/drama-acting-camps.php":      "/drama_camps.php",
    "/golf-camps.php":              "/golf_camps.php",
    "/gymnastics-camps.php":        "/gymnastics_camps.php",
    "/hockey-camps.php":            "/hockey_schools_camps.php",
    "/horse-camps.php":             "/horse_camps.php",
    "/lacrosse-camps.php":          "/lacrosse-summer-camps.php",
    "/karate-camps.php":            "/martial_arts_camps.php",
    "/kayaking-camps.php":          "/kayak-camp.php",
    "/leadership-camps.php":        None,   # skip — /leadership_camps.php handles leadership; education_camps.php is too broad
    "/math-camps.php":              "/math-camp.php",
    "/music-camps.php":             "/music_camps.php",
    "/music-programs.php":          "/music_camps.php",
    "/engineering-camps.php":       "/engineer-camps.php",
    "/fishing-camps.php":           "/fish-camps.php",
    "/fitness-boot-camps.php":      "/boot-camps-fitness.php",
    "/film-video-camps.php":        None,   # skip — /filmmaking-camp.php handles film tagging; arts_camps.php is too broad
    "/fashion-camps.php":           None,   # skip — /fashion-design-camp.php handles fashion; arts_camps.php is too broad
    "/cycling-camps.php":           None,   # skip — /bike-camps.php handles cycling; sports_camps.php is too broad
    "/camp/animal-camps":                       "/animal-camps.php",
    "/camp/martial-arts-camps":                 "/martial_arts_camps.php",
    "/camp/martial-arts-programs":              "/martial_arts_camps.php",
    "/camp/taekwondo-camps":                    "/taekwondo-camps.php",
    "/camp/taekwondo-classes":                  "/taekwondo-camps.php",
    "/camp/rugby-camps":                        "/rugby-camps-for-kids.php",
    "/camp/yoga-camps":                         "/yoga-camps.php",
    "/camp/yoga-programs":                      "/yoga-camps.php",
    "/camp/debate-and-public-speaking-camps":   "/debate-and-speech-camps-for-kids.php",
    "/camp/public-speaking-classes":            "/debate-and-speech-camps-for-kids.php",
    "/camp/magic-camps":                        "/magic-camps.php",
    "/camp/minecraft-camps":                    "/minecraft-camps.php",
    "/camp/minecraft-programs":                 "/minecraft-camps.php",
    "/camp/stem-camps":                         "/stem-camps.php",
    "/camp/stem-programs":                      "/stem-camps.php",
    "/camp/steam-camps":                        "/stem-camps.php",
    "/camp/steam-programs":                     "/stem-camps.php",
    "/camp/technology-camps":                   "/technology-camps.php",
    "/camp/technology-programs":               "/technology-camps.php",
    "/camp/horse-camps-alberta":               "/horse_camps.php",
    "/camp/horseback-riding-lessons":          "/horse_camps.php",
    "/camp/swimming-camps":                    "/swimming_camps.php",
    "/camp/tennis-programs":                   "/tennis_camps.php",
    "/camp/volleyball-programs":               "/volleyball_camps.php",
    "/camp/robotics-classes":                  "/robotics-camp-kids.php",
    "/camp/musical-theatre-camps":             "/drama_camps.php",
    "/camp/theatre-arts-camps":               "/drama_camps.php",
    "/camp/theatre-arts-programs":            "/drama_camps.php",
    "/camp/acting-film-tv":                   "/drama_camps.php",
    "/camp/acting-classes":                   "/drama_camps.php",
    "/camp/comedy-camps":                     "/drama_camps.php",
    "/camp/arts-crafts-camps":               "/arts-crafts-camps.php",
    "/camp/arts-crafts-programs":            "/arts-crafts-camps.php",
    "/camp/visual-arts-camps":               None,   # no specific page — arts_camps.php too broad
    "/camp/visual-arts-classes":             None,
    "/camp/drawing-camps":                   "/drawing-camps.php",
    "/camp/drawing-classes":                 "/drawing-camps.php",
    "/camp/online-drawing-classes":          "/drawing-camps.php",
    "/camp/painting-camps":                  "/painting-camps.php",
    "/camp/painting-classes":               "/painting-camps.php",
    "/camp/coding-classes":                  "/summer-programming.php",
    "/camp/online-coding-classes":           "/summer-programming.php",
    "/camp/engineering-programs":            "/engineer-camps.php",
    "/camp/lego-programs":                   "/lego-camps.php",
    "/camp/video-game-web-design":           "/game-design-camps.php",
    "/camp/roblox-camps":                    "/game-design-camps.php",
    "/camp/soccer-programs":                 "/soccer_camps.php",
    "/camp/toronto-soccer-camps":            "/soccer_camps.php",
    "/camp/girls-soccer":                    "/soccer_camps.php",
    "/camp/basketball-programs":             "/basketball-summer-camps.php",
    "/camp/baseball-programs":               "/baseball_camps.php",
    "/camp/hockey-programs":                 "/hockey_schools_camps.php",
    "/camp/sailing-lessons":                 "/sailing_camps.php",
    "/camp/nature-camps":                    "/adventure_camps.php",
    "/camp/nature-environment-programs":     "/adventure_camps.php",
    "/camp/wilderness-skills-camps":         "/wilderness_trip_camps.php",
    "/camp/canoe-camps":                     "/kayak-camp.php",
    "/camp/waterski-camps":                  "/wakeboard-camp.php",
    "/camp/figure-skating-camps":            "/skating_camps.php",
    "/camp/ball-sports-camps":              "/multi-sports-camp.php",
    "/camp/performing-arts-programs":        "/performing-arts-camp.php",
    "/camp/math-programs":                   "/math-camp.php",
    "/camp/language-studies-camps":         "/french-camps.php",
    "/camp/language-studies-programs":      "/french-camps.php",
    "/camp/tutoring-programs":              "/tutoring-programs.php",
    "/camp/tutoring-programs-instructor-led": "/tutoring-programs.php",
    "/camp/leadership-training-programs":   "/leadership_camps.php",
    "/camp/creative-writing-camps":         "/creative_writing_camps.php",
    "/camp/creative-writing-classes":       "/creative-writing-classes.php",
    "/camp/writing-classes":               "/creative-writing-classes.php",
    "/camp/writing-journalism-camps":      "/journalism-camps.php",
    "/camp/reading-camps":                 "/reading-camps.php",
    "/camp/reading-programs":             "/reading-camps.php",
    "/camp/power-of-words":              None,   # no specific page exists
    "/camp/photography-camps":           "/photography-camps.php",
    "/camp/video-photography-programs":  "/photography-camps.php",
    "/camp/filmmaking-camps":            "/filmmaking-camp.php",
    "/camp/animation-camps":             "/animation-camps.php",
    "/camp/animation-3-d-design":        "/animation-camps.php",
    "/camp/music-recording-camps":       "/music_camps.php",
    "/camp/guitar-camps":               "/music_camps.php",
    "/camp/guitar-lessons":             "/music_camps.php",
    "/camp/piano-camps":               "/music_camps.php",
    "/camp/piano-lessons":             "/music_camps.php",
    "/camp/singing-vocal-training-camps": "/music_camps.php",
    "/camp/singing-lessons":            "/music_camps.php",
    "/camp/percussion-camps":           "/music_camps.php",
    "/camp/music-lessons":             "/music_camps.php",
    "/camp/music-lessons-online":       "/music_camps.php",
    "/camp/jam-camps":                 "/music_camps.php",
    "/camp/hip-hop-dance-classes":     "/dance_camps.php",
    "/camp/hiphop-camps":              "/dance_camps.php",
    "/camp/jazz-dance-lessons":        "/dance_camps.php",
    "/camp/jazz-dance-camps":         "/dance_camps.php",
    "/camp/ballet-classes":           "/dance_camps.php",
    "/camp/ballet-camps":            "/dance_camps.php",
    "/camp/ballroom-dance-lessons":   "/dance_camps.php",
    "/camp/ballroom-dance-camps":    "/dance_camps.php",
    "/camp/breakdancing-lessons":     "/dance_camps.php",
    "/camp/breakdancing-camps":      "/dance_camps.php",
    "/camp/acro-camps":              "/dance_camps.php",
    "/camp/acro-classes":           "/dance_camps.php",
    # ── Additional broken dash-format pages found during scrape ──
    "/tutors-and-learning-centres.php":  "/tutoring-centres.php",
    "/paintball-camps.php":              "/paintball_camps.php",
    "/sailing-camps.php":                "/sailing_camps.php",
    "/science-camps.php":                "/science_camps.php",
    "/soccer-camps.php":                 "/soccer_camps.php",
    "/swimming-camps.php":               "/swimming_camps.php",
    "/tennis-camps.php":                 "/tennis_camps.php",
    "/volleyball-camps.php":             "/volleyball_camps.php",
    "/weight-loss-camps.php":            "/weight-loss-fitness-camps.php",
    "/wilderness-trips-camps.php":       "/wilderness_trip_camps.php",
    "/video-game-design-camps.php":      "/game-design-camps.php",
    "/skating-camps.php":                "/skate-camp.php",
    "/performing-arts-camps.php":        "/performing-arts-camp.php",
    "/robotics-camps.php":               "/robotics-camp-kids.php",
    "/wakeboarding-camps.php":           "/wakeboard-camp.php",
    "/programming-camps.php":            "/summer-programming.php",
    "/ski-camps.php":                    "/ski-camp.php",
    "/skateboarding-camps.php":          "/skate-camp.php",
    "/survival-camps.php":               "/wilderness-skills-camps.php",
    "/rock-climbing-camps.php":          None,   # no working page; skip
    "/super-camps.php":                  None,   # no working page; skip
    "/dwaynederosario.php":              None,   # celebrity page; skip
    "/sueeckersley.php":                 None,   # celebrity page; skip
    "/ashleighmcivor.php":               None,   # celebrity page; skip
    "/science-programs.php":             "/science_camps.php",
    "/swimming-lessons.php":             "/swimming_camps.php",
    "/skating_camps.php":                "/skate-camp.php",
}


# ── Sitemap-derived pages not in the Excel ────────────────────────────────────
# Maps page_path → [slug_list] directly, bypassing the Excel/WEBITEMS flow.
# Use for pages that either (a) didn't exist when the Excel was built, or
# (b) are redirected to a broader page in CAMP_PAGE_OVERRIDES but deserve a
# more specific slug (e.g. /ballet-camps.php → ballet, not dance-multi).
# Processed in addition to the Excel pages — INSERT IGNORE keeps it idempotent.
# ── Canonical Excel pages (hardcoded for CI) ──────────────────────────────────
# Replicates the core mappings from ALL CAMP PAGES CURRENT.xlsx.
# When the Excel is unavailable (GitHub Actions), this is used as the fallback.
# Keep in sync with the Excel — update here when camps.ca adds a new main category.
# Conservative: one primary slug per page; sub-activity detail comes from PAGE_SLUG_OVERRIDES.
CANONICAL_PAGES: dict[str, list[str]] = {
    "/adventure_camps.php":                  ["adventure-multi"],
    "/animal-camps.php":                     ["animals"],
    "/arts_camps.php":                       ["arts-multi"],
    "/baseball_camps.php":                   ["baseball-softball"],
    "/basketball-summer-camps.php":          ["basketball"],
    "/boot-camps-fitness.php":               ["health-fitness-multi"],
    "/cheerleading-summer-camps.php":        ["cheer"],
    "/computer_camps.php":                   ["computer-multi"],
    "/dance_camps.php":                      ["dance-multi"],
    "/debate-and-speech-camps-for-kids.php": ["debate", "public-speaking"],
    "/drama_camps.php":                      ["theatre-arts", "acting-film-tv"],
    "/education_camps.php":                  ["education-multi", "academic-tutoring-multi"],
    "/engineer-camps.php":                   ["engineering"],
    "/esl_camps.php":                        ["language-instruction"],
    "/fashion-design-camp.php":              ["fashion-design"],
    "/fencing-camps.php":                    ["fencing"],
    "/fish-camps.php":                       ["fishing"],
    "/french-camps.php":                     ["language-instruction"],
    "/game-design-camps.php":                ["video-game-design", "video-game-development"],
    "/glee-camps.php":                       ["glee"],
    "/golf_camps.php":                       ["golf"],
    "/gymnastics_camps.php":                 ["gymnastics"],
    "/health_fitness_camps.php":             ["health-fitness-multi"],
    "/hockey_schools_camps.php":             ["hockey"],
    "/horse_camps.php":                      ["horseback-riding-equestrian"],
    "/international_travel_camps.php":       ["travel"],
    "/kayak-camp.php":                       ["kayaking-sea-kayaking", "canoeing"],
    "/lacrosse-summer-camps.php":            ["lacrosse"],
    "/leadership_camps.php":                 ["leadership-multi"],
    "/lego-camps.php":                       ["lego"],
    "/magic-camps.php":                      ["magic"],
    "/martial_arts_camps.php":               ["martial-arts", "karate"],
    "/math-camp.php":                        ["math"],
    "/minecraft-camps.php":                  ["minecraft"],
    "/multi-sports-camp.php":                ["ball-sports-multi", "sport-multi"],
    "/music_camps.php":                      ["music-multi"],
    "/paintball_camps.php":                  ["paintball"],
    "/performing-arts-camp.php":             ["performing-arts-multi"],
    "/robotics-camp-kids.php":               ["robotics"],
    "/rugby-camps-for-kids.php":             ["rugby"],
    "/sailing_camps.php":                    ["sailing-marine-skills"],
    "/science_camps.php":                    ["science-multi"],
    "/skate-camp.php":                       ["figure-skating", "ice-skating", "skateboarding"],
    "/ski-camp.php":                         ["skiing", "snowboarding"],
    "/soccer_camps.php":                     ["soccer"],
    "/stem-camps.php":                       ["stem"],
    "/summer-programming.php":               ["programming-multi"],
    "/swimming_camps.php":                   ["swimming"],
    "/taekwondo-camps.php":                  ["taekwondo"],
    "/technology-camps.php":                 ["technology", "computer-multi"],
    "/tennis_camps.php":                     ["tennis"],
    "/volleyball_camps.php":                 ["volleyball"],
    "/wakeboard-camp.php":                   ["waterskiing-wakeboarding"],
    "/wilderness-skills-camps.php":          ["wilderness-skills"],
    "/wilderness_trip_camps.php":            ["wilderness-out-tripping"],
    "/yoga-camps.php":                       ["yoga"],
}


# ── Sitemap-derived pages not in the Excel ────────────────────────────────────
PAGE_SLUG_OVERRIDES: dict[str, list[str]] = {
    # ── Arts / Dance ─────────────────────────────────────────────────────────
    "/acro-camps.php":                             ["acro-dance"],
    "/acro-lessons.php":                           ["acro-dance"],
    "/animation-camps.php":                        ["animation"],
    "/arts-camps-creativity.php":                  ["arts-multi"],
    "/arts-crafts-camps.php":                      ["arts-crafts"],
    "/baking-camps.php":                           ["baking-decorating"],
    "/ballet-camps.php":                           ["ballet"],
    "/ballet-classes.php":                         ["ballet"],
    "/ballroom-dance-lessons-and-classes.php":     ["ballroom"],
    "/breakdancing-lessons.php":                   ["breakdancing"],
    "/cartooning-camps.php":                       ["cartooning"],
    "/circus-camps.php":                           ["circus"],
    "/comedy-camps.php":                           ["comedy"],
    "/cooking-camps.php":                          ["cooking"],
    "/cooking-classes.php":                        ["cooking"],
    "/creative-writing-classes.php":               ["creative-writing"],
    "/creative_writing_camps.php":                 ["creative-writing"],
    "/dance-classes.php":                          ["dance-multi"],
    "/drawing-camps.php":                          ["drawing"],
    "/drawing-lessons.php":                        ["drawing"],
    "/fashion-design-classes.php":                 ["fashion-design"],
    "/filmmaking-camps.php":                       ["filmmaking"],
    "/fine_art_camps.php":                         ["visual-arts-multi"],
    "/guitar-camps.php":                           ["guitar"],
    "/guitar-lessons.php":                         ["guitar"],
    "/hip-hop-dance-camps.php":                    ["hip-hop"],
    "/hip-hop-dance-classes.php":                  ["hip-hop"],
    "/jazz-dance-camps.php":                       ["jazz"],
    "/jazz-dance-lessons.php":                     ["jazz"],
    "/music-lessons.php":                          ["music-multi"],
    "/music_recording.php":                        ["music-recording"],
    "/music_recording_camps.php":                  ["music-recording"],
    "/musical-theatre-camps.php":                  ["musical-theatre"],
    "/online-cooking-classes.php":                 ["cooking"],
    "/painting-camps.php":                         ["painting"],
    "/photography-camps.php":                      ["photography"],
    "/photography-classes.php":                    ["photography"],
    "/piano-camps.php":                            ["piano"],
    "/piano-lessons.php":                          ["piano"],
    "/pottery-camps.php":                          ["pottery"],
    "/scratch-camps.php":                          ["scratch"],
    "/singing-lessons.php":                        ["vocal-training-singing"],
    "/songwriting-camps.php":                      ["songwriting"],
    "/theatre-arts-camps.php":                     ["theatre-arts"],
    "/theatre-arts-classes.php":                   ["theatre-arts"],
    "/violin_guitar_camps.php":                    ["guitar", "string"],
    "/visual-arts-camps.php":                      ["visual-arts-multi"],
    "/visual-arts-programs.php":                   ["arts-crafts", "cartooning", "ceramics", "drawing", "filmmaking", "painting", "photography", "pottery", "videography"],
    "/vocal_camps.php":                            ["vocal-training-singing"],
    "/writing-camps.php":                          ["writing"],
    "/writing-classes.php":                        ["writing"],
    "/acting-classes.php":                         ["acting-film-tv", "theatre-arts"],
    "/online-drawing-classes.php":                 ["drawing"],
    "/online-music-lessons.php":                   ["glee", "guitar", "jam-camp", "music-recording", "musical-instrument-training", "percussion", "piano", "songwriting", "vocal-training-singing"],
    "/painting-classes.php":                       ["painting"],
    "/performing-arts-programs.php":               ["acting-film-tv", "magic", "modeling", "musical-theatre", "theatre-arts"],

    # ── Computers & Tech ─────────────────────────────────────────────────────
    "/artificial-intelligence-camps.php":          ["ai-artificial-intelligence"],
    "/coding-classes.php":                         ["programming-multi"],
    "/java-classes.php":                           ["java"],
    "/maker-camps.php":                            ["makerspace"],
    "/minecraft-classes.php":                      ["minecraft"],
    "/online-coding-classes.php":                  ["programming-multi"],
    "/python-camps.php":                           ["python"],
    "/python-classes.php":                         ["python"],
    "/STEM-classes.php":                           ["stem"],
    "/steam-camps.php":                            ["steam"],
    "/steam-classes.php":                          ["steam"],
    "/roblox-camps.php":                           ["roblox"],
    "/robotics-programs.php":                      ["robotics"],
    "/technology-programs.php":                    ["technology"],

    # ── Education ─────────────────────────────────────────────────────────────
    "/chess-camps.php":                            ["chess"],
    "/counsellor-in-training-camps.php":           ["cit-lit-program"],
    "/credit-courses.php":                         ["credit-courses"],
    "/entrepreneurship-camps.php":                 ["entrepreneurship"],
    "/financial-literacy-camps.php":               ["financial-literacy"],
    "/math-classes.php":                           ["math"],
    "/outdoor-education.php":                      ["adventure-multi", "nature-environment"],
    "/public-speaking-classes.php":                ["public-speaking"],
    "/reading-camps.php":                          ["reading"],
    "/space.php":                                  ["space"],
    "/tutoring-centres.php":                       ["academic-tutoring-multi"],
    "/youth-empowerment-social-justice-camps.php": ["empowerment", "social-justice"],
    "/zoo-camps.php":                              ["animals"],

    # ── Sports ────────────────────────────────────────────────────────────────
    "/baseball-lessons.php":                       ["baseball-softball"],
    "/basketball-lessons.php":                     ["basketball"],
    "/bike-camps.php":                             ["cycling"],
    "/bronze-cross-courses.php":                   ["bronze-cross"],
    "/canoe-camps.php":                            ["canoeing"],
    "/cricket-camps.php":                          ["cricket"],
    "/first-aid-camps.php":                        ["first-aid-lifesaving"],
    "/first-aid-courses.php":                      ["first-aid-lifesaving"],
    "/football-camps.php":                         ["football"],
    "/hockey-lessons.php":                         ["hockey"],
    "/horseback-riding-lessons.php":               ["horseback-riding-equestrian"],
    "/karate-lessons.php":                         ["karate"],
    "/martial-arts-lessons.php":                   ["martial-arts"],
    "/soccer-lessons.php":                         ["soccer"],
    "/summer-camps-water-sports.php":              ["water-sports-multi"],
    "/swimming-classes.php":                       ["swimming"],
    "/taekwondo-lessons.php":                      ["taekwondo"],
    "/tennis-lessons.php":                         ["tennis"],
    "/trampoline-camps.php":                       ["trampoline"],
    "/ultimate-frisbee-camps.php":                 ["ultimate-frisbee"],
    "/volleyball-classes.php":                     ["volleyball"],
    "/water-sports-camps.php":                     ["water-sports-multi"],
    "/waterski-camps.php":                         ["waterskiing-wakeboarding"],
    "/alberta-horse-camps.php":                    ["horseback-riding-equestrian"],
    "/girls-soccer.php":                           ["soccer"],
    "/international-travel-programs.php":          ["travel"],
    "/toronto-soccer-camps.php":                   ["soccer"],
}


def parse_webitems(list_options: str) -> list[str]:
    """Extract SQLwebitems values from a list_options string."""
    m = re.search(r'SQLwebitems:\s*(.+?)(?:\s*,\s*SQL|\s*$)', list_options)
    if not m:
        return []
    raw = m.group(1)
    # Each item is comma-separated; strip whitespace from each
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return items


def load_pages_from_excel(xlsx_path: str) -> list[tuple[str, list[str]]]:
    """
    Parse the Excel and return a deduplicated list of (page_url, [tag_slugs]).
    Only pages with at least one mappable SQLwebitems tag are included.
    Deduplicates by (page_url) — keeps first occurrence.
    """
    import pandas as pd
    df = pd.read_excel(xlsx_path)

    seen_urls: set[str] = set()
    # effective_url → accumulated tag slugs (merge multiple /camp/* → same .php)
    url_slugs: dict[str, list[str]] = {}

    for _, row in df.iterrows():
        url = str(row.get("page URL", "") or "").strip()
        opts = str(row.get("list options", "") or "")
        if not url or "SQLwebitems" not in opts:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        items = parse_webitems(opts)
        slugs = [WEBITEMS_TO_SLUG[i] for i in items if i in WEBITEMS_TO_SLUG]
        if slugs:
            # Substitute broken URLs with working equivalents; None = skip entirely
            effective_url = CAMP_PAGE_OVERRIDES.get(url, url)
            if effective_url is None:
                continue
            if effective_url not in url_slugs:
                url_slugs[effective_url] = []
            for s in slugs:
                if s not in url_slugs[effective_url]:
                    url_slugs[effective_url].append(s)

    pages: list[tuple[str, list[str]]] = list(url_slugs.items())

    return pages


def fetch_camp_ids(path: str, cur=None) -> list[int]:
    """Fetch a camps.ca category page and extract camp IDs from links.

    Handles two page formats:
      - Older pages: <a href="/slug/ID">          (gymnastics_camps.php style)
      - Newer pages: <option value="/slug/ID">    (hockey-camps.php style)

    Note: /camp/* format pages (newer SEO pages) use a general all-camps
    navigation dropdown that does not expose category-specific camp IDs —
    these pages return 0 and are skipped by the caller.
    """
    url = f"https://www.camps.ca{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"  FETCH ERROR: {e}")
        return []
    pattern = r'(?:href|value)=["\']\/[a-z0-9\-]+\/(\d+)["\']'
    ids = re.findall(pattern, html)
    return list({int(i) for i in ids})


def main():
    import os
    from db.connection import get_connection

    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("DRY RUN — no writes\n")

    # Excel is the preferred source locally; in CI it won't exist — fall back to
    # CANONICAL_PAGES which replicates its core mappings as hardcoded Python.
    xlsx = os.environ.get(
        "CAMP_PAGES_XLSX",
        "/Users/181lp/Documents/CLAUDE_code/csc_collaterals/ALL CAMP PAGES CURRENT.xlsx",
    )
    if os.path.exists(xlsx):
        pages = load_pages_from_excel(xlsx)
        print(f"Loaded {len(pages)} unique activity pages from Excel")
    else:
        pages = list(CANONICAL_PAGES.items())
        print(f"Excel not found — using {len(pages)} hardcoded canonical pages")

    # Augment with sitemap-derived pages not in the Excel / CANONICAL_PAGES.
    # Dedup by path: if a path is already queued, merge slugs so we don't
    # fetch the same URL twice.
    existing_paths = {path for path, _ in pages}
    extra: list[tuple[str, list[str]]] = []
    for path, slugs in PAGE_SLUG_OVERRIDES.items():
        if path in existing_paths:
            for i, (p, s) in enumerate(pages):
                if p == path:
                    pages[i] = (p, list(dict.fromkeys(s + slugs)))  # dedup, preserve order
                    break
        else:
            extra.append((path, slugs))
    pages.extend(extra)
    print(f"Added {len(extra)} sitemap-only pages → {len(pages)} total\n")

    # Pre-load tag slug → id map (fresh connection, then close)
    _conn = get_connection()
    _cur = _conn.cursor(dictionary=True)
    _cur.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
    slug_to_id = {r["slug"]: r["id"] for r in _cur.fetchall()}
    _cur.close()
    _conn.close()

    total_ins = total_skp = 0
    results = []

    for path, tag_slugs in pages:
        print(f"Fetching {path} ...", end=" ", flush=True)
        camp_ids = fetch_camp_ids(path)
        if not camp_ids:
            print("0 camps, skip")
            continue

        # Fresh DB connection per page — avoids Aiven idle-timeout drops
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        # Filter to active camps in our DB
        ph = ",".join(["%s"] * len(camp_ids))
        cur.execute(
            f"SELECT id FROM camps WHERE id IN ({ph}) AND status = 1", camp_ids
        )
        db_ids = [r["id"] for r in cur.fetchall()]
        if not db_ids:
            cur.close(); conn.close()
            print(f"{len(camp_ids)} on page, 0 in DB, skip")
            continue

        # Get active program IDs per camp — needed for program-count gating
        ph2 = ",".join(["%s"] * len(db_ids))
        cur.execute(
            f"SELECT id, camp_id FROM programs WHERE camp_id IN ({ph2}) AND status = 1",
            db_ids,
        )
        prog_rows = cur.fetchall()

        # Only tag programs at SINGLE-program camps.  Multi-program camps
        # are covered by the camp_tag_overrides.json parallel lookup in CSSL
        # (camp_id-level match).  Tagging all programs at multi-program camps
        # creates false program-level signals — e.g. a basketball session at
        # a multi-sport camp getting a hockey tag because the camp appears on
        # the hockey page.
        from collections import defaultdict
        by_camp: dict[int, list[int]] = defaultdict(list)
        for r in prog_rows:
            by_camp[r["camp_id"]].append(r["id"])
        prog_ids = []
        for cid, pids in by_camp.items():
            if len(pids) == 1:
                prog_ids.extend(pids)

        tag_ids = [slug_to_id[s] for s in tag_slugs if s in slug_to_id]
        pairs = [(pid, tid) for pid in prog_ids for tid in tag_ids]
        ins = skp = 0
        if dry_run:
            ins = len(pairs)
        else:
            # Bulk INSERT IGNORE in chunks of 500 for speed
            chunk_size = 500
            for i in range(0, len(pairs), chunk_size):
                chunk = pairs[i : i + chunk_size]
                placeholders = ",".join(["(%s,%s,0,'activity','scraper')"] * len(chunk))
                flat = [v for pair in chunk for v in pair]
                cur.execute(
                    f"INSERT IGNORE INTO program_tags (program_id, tag_id, is_primary, tag_role, source) "
                    f"VALUES {placeholders}",
                    flat,
                )
                ins += cur.rowcount
            skp = len(pairs) - ins

        if not dry_run:
            conn.commit()
        cur.close()
        conn.close()

        total_ins += ins
        total_skp += skp
        results.append((path, len(camp_ids), len(db_ids), ins, skp))
        print(f"{len(camp_ids)} camps ({len(db_ids)} in DB) → +{ins} new tags, {skp} existed")
        time.sleep(0.3)

    print(f"\n{'[DRY RUN] ' if dry_run else ''}COMPLETE")
    print(f"Total new tag rows: {total_ins:,}")
    print(f"Already existed:    {total_skp:,}")
    print(f"Pages processed:    {len(results)}")


if __name__ == "__main__":
    main()
