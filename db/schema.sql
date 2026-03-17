-- ─────────────────────────────────────────────────────────────────────────────
-- CSC Database Schema v1.0
-- MySQL 8.0 InnoDB, utf8mb4_unicode_ci
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. CAMPS
CREATE TABLE IF NOT EXISTS camps (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. PROGRAMS (replaces legacy sessions)
CREATE TABLE IF NOT EXISTS programs (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. ACTIVITY_TAGS (replaces legacy sitems)
CREATE TABLE IF NOT EXISTS activity_tags (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. PROGRAM_TAGS (junction)
CREATE TABLE IF NOT EXISTS program_tags (
    program_id  INT UNSIGNED NOT NULL,
    tag_id      INT UNSIGNED NOT NULL,
    is_primary  TINYINT NOT NULL DEFAULT 1,
    tag_role    ENUM('specialty','category','activity') NOT NULL DEFAULT 'activity',
    PRIMARY KEY (program_id, tag_id),
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES activity_tags(id),
    INDEX idx_tag (tag_id),
    INDEX idx_primary (is_primary),
    INDEX idx_tag_role (tag_role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. CATEGORIES (SEO landing pages)
CREATE TABLE IF NOT EXISTS categories (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. TRAITS
CREATE TABLE IF NOT EXISTS traits (
    id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name    VARCHAR(150) NOT NULL,
    slug    VARCHAR(150) NOT NULL UNIQUE,
    INDEX idx_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO traits (name, slug) VALUES
('Resilience','resilience'),('Curiosity','curiosity'),('Courage','courage'),
('Independence','independence'),('Responsibility','responsibility'),
('Interpersonal Skills','interpersonal-skills'),('Creativity','creativity'),
('Physicality','physicality'),('Generosity','generosity'),('Tolerance','tolerance'),
('Self-regulation','self-regulation'),('Religious Faith','religious-faith')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- 7. PROGRAM_TRAITS (junction)
CREATE TABLE IF NOT EXISTS program_traits (
    program_id      INT UNSIGNED NOT NULL,
    trait_id        INT UNSIGNED NOT NULL,
    justification   VARCHAR(500),
    PRIMARY KEY (program_id, trait_id),
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (trait_id) REFERENCES traits(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. INTERACTION_LOG (for future Learning to Rank)
CREATE TABLE IF NOT EXISTS interaction_log (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
