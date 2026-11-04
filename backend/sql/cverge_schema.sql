-- ---------- ENUMS ----------
CREATE TYPE user_role   AS ENUM ('candidate', 'reviewer', 'administrator');  -- requirements.md §2.10
CREATE TYPE file_type   AS ENUM ('pdf', 'docx', 'md', 'json');  -- file extension without the dot
CREATE TYPE file_status AS ENUM ('uploaded', 'processing', 'done', 'failed', 'needs_review');
CREATE TYPE link_type   AS ENUM ('linkedin', 'github', 'portfolio', 'website', 'other');

-- ---------- SYSTEM TABLES ----------
CREATE TABLE app_user (
  user_id       SERIAL PRIMARY KEY,
  name          VARCHAR(255) NOT NULL,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255),                   -- NULL for accounts that only use social login
  role          user_role NOT NULL DEFAULT 'candidate',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Social login: one row per provider account linked to a user
CREATE TABLE user_identity (
  identity_id      SERIAL PRIMARY KEY,
  user_id          INT NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
  provider         VARCHAR(20) NOT NULL CHECK (provider IN ('google', 'linkedin', 'github')),
  provider_user_id VARCHAR(255) NOT NULL,
  created_at       TIMESTAMP DEFAULT now(),
  UNIQUE (provider, provider_user_id)
);

CREATE TABLE country (
  country_id   SERIAL PRIMARY KEY,
  country_name VARCHAR(100) NOT NULL UNIQUE,
  country_code CHAR(2) NOT NULL UNIQUE          -- ISO 3166-1 alpha-2
);

-- ---------- FINAL DESTINATION ----------
-- One merged profile per user. One-value-per-person fields live here.
CREATE TABLE profile (
  profile_id  SERIAL PRIMARY KEY,
  user_id     INT NOT NULL UNIQUE REFERENCES app_user(user_id) ON DELETE CASCADE,
  first_name  VARCHAR(100),
  last_name   VARCHAR(100),
  email       VARCHAR(255),
  phone       VARCHAR(50),
  city        VARCHAR(100),
  country_id  INT REFERENCES country(country_id),
  title       VARCHAR(255),
  summary     TEXT,
  final_json  JSONB,                            -- the complete, merged, ready-to-use profile
  updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Keep profile.updated_at fresh on every update (PostgreSQL has no ON UPDATE)
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_profile_updated_at
  BEFORE UPDATE ON profile
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------- UPLOADED FILES ----------
CREATE TABLE source_file (
  file_id           SERIAL PRIMARY KEY,
  profile_id        INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  file_type         file_type NOT NULL,
  original_name     VARCHAR(255) NOT NULL,
  file_hash         CHAR(64) NOT NULL,          -- SHA-256: same file twice from the same candidate = no duplicate
  storage_path      TEXT NOT NULL,              -- raw file, never overwritten
  status            file_status NOT NULL DEFAULT 'uploaded',
  extraction_method VARCHAR(20),                -- text | ocr | parser | direct
  ocr_confidence    REAL CHECK (ocr_confidence BETWEEN 0 AND 1),
  error_message     TEXT,
  "Num_Of_Retries"  INT NOT NULL DEFAULT 0,     -- processing retries used so far (quoted: name used by the Alembic migration)
  llm_response      JSONB,                      -- raw LLM output, for debugging
  uploaded_at       TIMESTAMP NOT NULL DEFAULT now(),
  finished_at       TIMESTAMP,
  CONSTRAINT uq_source_file_profile_hash UNIQUE (profile_id, file_hash)  -- FR-055: unique per candidate
);

-- ---------- LOOKUP TABLES ----------
CREATE TABLE skill (
  skill_id       SERIAL PRIMARY KEY,
  canonical_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE skill_alias (
  alias_id   SERIAL PRIMARY KEY,
  skill_id   INT NOT NULL REFERENCES skill(skill_id) ON DELETE CASCADE,
  alias_name VARCHAR(100) NOT NULL UNIQUE       -- store lowercase, e.g. 'reactjs'
);

-- ---------- CV SECTIONS (many per profile) ----------
CREATE TABLE profile_skill (
  profile_id INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  skill_id   INT NOT NULL REFERENCES skill(skill_id),
  level      INT CHECK (level BETWEEN 1 AND 5),
  confidence REAL CHECK (confidence BETWEEN 0 AND 1),
  PRIMARY KEY (profile_id, skill_id)
);

CREATE TABLE work_experience (
  exp_id      SERIAL PRIMARY KEY,
  profile_id  INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  company     VARCHAR(255),
  title       VARCHAR(255),
  start_date  DATE,
  end_date    DATE,                             -- NULL = current job
  description TEXT
);

CREATE TABLE project (
  project_id  SERIAL PRIMARY KEY,
  profile_id  INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  name        VARCHAR(255) NOT NULL,
  description TEXT,
  url         TEXT,
  tech_stack  TEXT[]                            -- e.g. {'Node.js','PostgreSQL'}
);

CREATE TABLE education (
  edu_id      SERIAL PRIMARY KEY,
  profile_id  INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  institution VARCHAR(255),
  degree      VARCHAR(255),
  field       VARCHAR(255),
  start_date  DATE,
  end_date    DATE
);

CREATE TABLE language (                         -- spoken languages (not programming)
  language_id SERIAL PRIMARY KEY,
  profile_id  INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  name        VARCHAR(50) NOT NULL,
  proficiency VARCHAR(30),                      -- native | fluent | intermediate | basic
  UNIQUE (profile_id, name)
);

CREATE TABLE profile_link (                     -- LinkedIn, GitHub, portfolio...
  link_id    SERIAL PRIMARY KEY,
  profile_id INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  type       link_type NOT NULL,
  url        TEXT NOT NULL,
  UNIQUE (profile_id, url)
);

CREATE TABLE certification (
  cert_id    SERIAL PRIMARY KEY,
  profile_id INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  name       VARCHAR(255) NOT NULL,
  issuer     VARCHAR(255),
  issue_date DATE,
  url        TEXT
);

-- ---------- AUDIT TRAIL: where each value came from ----------
-- Every value from every file, with its confidence and the rule used.
CREATE TABLE extracted_field (
  field_id    SERIAL PRIMARY KEY,
  file_id     INT NOT NULL REFERENCES source_file(file_id) ON DELETE CASCADE,
  field_name  VARCHAR(100) NOT NULL,            -- e.g. title, city, skills.react
  value       TEXT,
  confidence  REAL CHECK (confidence BETWEEN 0 AND 1),
  rule        VARCHAR(100),                     -- e.g. newer_source, alias_table, vetted_wins
  is_winner   BOOLEAN DEFAULT FALSE,
  created_at  TIMESTAMP DEFAULT now()
);

-- ---------- HUMAN REVIEW QUEUE ----------
-- Resolved by a user whose role is 'reviewer' or 'administrator' (enforced in the backend).
-- file_id = the source file that triggered the review.
-- Every conflicting value, with the file it came from, is stored as one row
-- in review_option, so the reviewer can see the source of each value.
CREATE TABLE review_item (
  review_id      SERIAL PRIMARY KEY,
  profile_id     INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  file_id        INT NOT NULL REFERENCES source_file(file_id) ON DELETE CASCADE,
  field_name     VARCHAR(100) NOT NULL,
  assigned_to_candidate BOOLEAN DEFAULT FALSE,  -- reviewer sent this item to the candidate
  sent_to_candidate_at  TIMESTAMP,
  resolved       BOOLEAN DEFAULT FALSE,
  resolved_by    INT REFERENCES app_user(user_id),   -- reviewer, administrator or the candidate
  resolved_value TEXT,
  created_at     TIMESTAMP DEFAULT now(),
  resolved_at    TIMESTAMP
);

-- One row per conflicting value of a review item, linked to its source file.
-- Example: review 1 (city) has two options: Amman from resume.pdf, Dubai from linkedin.md.
CREATE TABLE review_option (
  option_id   SERIAL PRIMARY KEY,
  review_id   INT NOT NULL REFERENCES review_item(review_id) ON DELETE CASCADE,
  file_id     INT NOT NULL REFERENCES source_file(file_id) ON DELETE CASCADE,
  value       TEXT,
  confidence  REAL CHECK (confidence BETWEEN 0 AND 1)
);

-- ---------- AUDIT TRAIL: history of profile changes ----------
-- One row each time a profile value changes: who, when, old and new value, why.
-- changed_by NULL = automatic merge by the system.
CREATE TABLE profile_change_log (
  change_id   SERIAL PRIMARY KEY,
  profile_id  INT NOT NULL REFERENCES profile(profile_id) ON DELETE CASCADE,
  file_id     INT REFERENCES source_file(file_id) ON DELETE SET NULL,  -- file that caused it, if any
  field_name  VARCHAR(100) NOT NULL,
  old_value   TEXT,
  new_value   TEXT,
  changed_by  INT REFERENCES app_user(user_id),
  reason      VARCHAR(100),                     -- auto_merge | review_decision | manual_edit
  changed_at  TIMESTAMP DEFAULT now()
);

-- Automatic logging for the single-value profile fields.
-- The backend tells the trigger who is making the change and why, inside the
-- same transaction, before running the UPDATE:
--   SET LOCAL app.current_user_id = '5';
--   SET LOCAL app.change_reason   = 'review_decision';
-- If these are not set, the log records changed_by = NULL and reason = 'auto_merge'.
-- Changes to skills, experience, projects, etc. are written to this table by the
-- backend when it merges them (the trigger only watches the profile table).
CREATE OR REPLACE FUNCTION log_profile_changes() RETURNS TRIGGER AS $$
DECLARE
  k     TEXT;
  old_j JSONB := to_jsonb(OLD);
  new_j JSONB := to_jsonb(NEW);
  who   INT   := NULLIF(current_setting('app.current_user_id', true), '')::INT;
  why   TEXT  := NULLIF(current_setting('app.change_reason', true), '');
BEGIN
  FOREACH k IN ARRAY ARRAY['first_name','last_name','email','phone',
                           'city','country_id','title','summary']
  LOOP
    IF old_j->>k IS DISTINCT FROM new_j->>k THEN
      INSERT INTO profile_change_log
        (profile_id, field_name, old_value, new_value, changed_by, reason)
      VALUES
        (NEW.profile_id, k, old_j->>k, new_j->>k, who, COALESCE(why, 'auto_merge'));
    END IF;
  END LOOP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_profile_log
  AFTER UPDATE ON profile
  FOR EACH ROW EXECUTE FUNCTION log_profile_changes();

-- ---------- INDEXES ----------
CREATE INDEX idx_profile_city        ON profile(city);
CREATE INDEX idx_profile_country     ON profile(country_id);
CREATE INDEX idx_final_json          ON profile USING GIN (final_json);
CREATE INDEX idx_source_file_profile ON source_file(profile_id);
CREATE INDEX idx_source_file_status  ON source_file(status);
CREATE INDEX idx_exp_profile         ON work_experience(profile_id);
CREATE INDEX idx_project_profile     ON project(profile_id);
CREATE INDEX idx_extracted_file      ON extracted_field(file_id, field_name);
CREATE INDEX idx_review_resolved     ON review_item(resolved);
CREATE INDEX idx_review_file         ON review_item(file_id);
CREATE INDEX idx_option_review       ON review_option(review_id);
CREATE INDEX idx_option_file         ON review_option(file_id);
CREATE INDEX idx_change_profile      ON profile_change_log(profile_id, changed_at);
CREATE INDEX idx_identity_user       ON user_identity(user_id);

-- ---------- SEED DATA ----------
INSERT INTO country (country_name, country_code) VALUES
  ('Jordan', 'JO'), ('Palestine', 'PS'), ('United Arab Emirates', 'AE'),
  ('Saudi Arabia', 'SA'), ('Egypt', 'EG'), ('United States', 'US'),
  ('United Kingdom', 'GB'), ('Germany', 'DE');

INSERT INTO skill (canonical_name) VALUES
  ('React'), ('Node.js'), ('Python'), ('JavaScript'), ('TypeScript'),
  ('PostgreSQL'), ('MySQL'), ('Docker'), ('Java'), ('C#'), ('Git');

INSERT INTO skill_alias (skill_id, alias_name) VALUES
  ((SELECT skill_id FROM skill WHERE canonical_name = 'React'),      'reactjs'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'React'),      'react.js'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'Node.js'),    'node'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'Node.js'),    'nodejs'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'JavaScript'), 'js'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'TypeScript'), 'ts'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'PostgreSQL'), 'postgres'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'PostgreSQL'), 'psql'),
  ((SELECT skill_id FROM skill WHERE canonical_name = 'MySQL'),      'mysql8');

-- =====================================================================
-- DASHBOARD VIEWS (admin dashboard; the review queue also serves reviewers)
-- =====================================================================

CREATE VIEW v_dash_summary AS
SELECT
  (SELECT COUNT(*) FROM app_user WHERE role = 'candidate')         AS total_candidates,
  (SELECT COUNT(*) FROM profile)                                   AS total_profiles,
  (SELECT COUNT(*) FROM source_file)                               AS total_files,
  (SELECT COUNT(*) FROM source_file WHERE status = 'done')         AS files_done,
  (SELECT COUNT(*) FROM source_file WHERE status = 'failed')       AS files_failed,
  (SELECT COUNT(*) FROM review_item WHERE resolved = FALSE)        AS open_reviews,
  (SELECT ROUND(AVG(confidence)::numeric, 2) FROM extracted_field) AS avg_confidence;

CREATE VIEW v_dash_files_by_status AS
SELECT status, COUNT(*) AS total FROM source_file GROUP BY status;

CREATE VIEW v_dash_files_by_type AS
SELECT file_type, COUNT(*) AS total FROM source_file GROUP BY file_type;

CREATE VIEW v_dash_uploads_per_day AS
SELECT uploaded_at::date AS day, COUNT(*) AS uploads
FROM source_file
GROUP BY uploaded_at::date
ORDER BY day;

CREATE VIEW v_dash_top_skills AS
SELECT s.canonical_name AS skill, COUNT(*) AS candidates
FROM profile_skill ps
JOIN skill s ON s.skill_id = ps.skill_id
GROUP BY s.canonical_name
ORDER BY candidates DESC
LIMIT 10;

CREATE VIEW v_dash_countries AS
SELECT c.country_name, COUNT(*) AS candidates
FROM profile p
JOIN country c ON c.country_id = p.country_id
GROUP BY c.country_name
ORDER BY candidates DESC;

CREATE VIEW v_dash_cities AS
SELECT city, COUNT(*) AS candidates
FROM profile
WHERE city IS NOT NULL
GROUP BY city
ORDER BY candidates DESC;

CREATE VIEW v_dash_review_queue AS
SELECT r.review_id,
       concat_ws(' ', p.first_name, p.last_name) AS full_name,
       r.field_name,
       r.assigned_to_candidate,
       f.original_name AS triggered_by_file,
       (SELECT json_agg(json_build_object(
                 'value', o.value,
                 'file', sf.original_name,
                 'file_type', sf.file_type,
                 'confidence', o.confidence) ORDER BY o.option_id)
          FROM review_option o
          JOIN source_file sf ON sf.file_id = o.file_id
         WHERE o.review_id = r.review_id) AS options,
       r.created_at
FROM review_item r
JOIN profile p     ON p.profile_id = r.profile_id
JOIN source_file f ON f.file_id = r.file_id
WHERE r.resolved = FALSE
ORDER BY r.created_at;

-- Reviewer screen: one row per conflicting value, with its source file
CREATE VIEW v_review_option_detail AS
SELECT o.review_id, r.field_name, o.option_id, o.value, o.confidence,
       sf.file_id, sf.original_name, sf.file_type, sf.uploaded_at
FROM review_option o
JOIN review_item r  ON r.review_id = o.review_id
JOIN source_file sf ON sf.file_id = o.file_id
ORDER BY o.review_id, o.option_id;

CREATE VIEW v_dash_failed_files AS
SELECT f.file_id,
       concat_ws(' ', p.first_name, p.last_name) AS full_name,
       f.original_name, f.file_type, f.error_message, f.uploaded_at
FROM source_file f
JOIN profile p ON p.profile_id = f.profile_id
WHERE f.status = 'failed'
ORDER BY f.uploaded_at DESC;

CREATE VIEW v_dash_low_confidence AS
SELECT concat_ws(' ', p.first_name, p.last_name) AS full_name,
       e.field_name, e.value, e.confidence, e.rule, f.file_type AS source
FROM extracted_field e
JOIN source_file f ON f.file_id = e.file_id
JOIN profile p     ON p.profile_id = f.profile_id
WHERE e.confidence < 0.6
ORDER BY e.confidence;

CREATE VIEW v_dash_completeness AS
SELECT
  p.profile_id,
  concat_ws(' ', p.first_name, p.last_name) AS full_name,
  ROUND((
      (p.email IS NOT NULL)::int
    + (p.city  IS NOT NULL)::int
    + (p.title IS NOT NULL)::int
    + (p.country_id IS NOT NULL)::int
    + (EXISTS (SELECT 1 FROM profile_skill   WHERE profile_id = p.profile_id))::int
    + (EXISTS (SELECT 1 FROM work_experience WHERE profile_id = p.profile_id))::int
    + (EXISTS (SELECT 1 FROM project         WHERE profile_id = p.profile_id))::int
    + (EXISTS (SELECT 1 FROM education       WHERE profile_id = p.profile_id))::int
    + (EXISTS (SELECT 1 FROM profile_link    WHERE profile_id = p.profile_id))::int
  ) * 100.0 / 9) AS completeness_percent
FROM profile p;

-- Latest profile changes (who changed what, when and why)
CREATE VIEW v_dash_recent_changes AS
SELECT c.change_id,
       concat_ws(' ', p.first_name, p.last_name) AS candidate,
       c.field_name, c.old_value, c.new_value,
       COALESCE(u.name, 'system') AS changed_by,
       c.reason, c.changed_at
FROM profile_change_log c
JOIN profile p        ON p.profile_id = c.profile_id
LEFT JOIN app_user u  ON u.user_id = c.changed_by
ORDER BY c.changed_at DESC
LIMIT 50;

