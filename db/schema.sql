CREATE TABLE IF NOT EXISTS access_codes (
  code TEXT PRIMARY KEY,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS participants (
  access_code TEXT PRIMARY KEY REFERENCES access_codes(code) ON DELETE CASCADE,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  email TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questionnaire_questions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  helper TEXT NOT NULL DEFAULT '',
  placeholder TEXT NOT NULL DEFAULT 'Ta réponse…',
  required BOOLEAN NOT NULL DEFAULT TRUE,
  position INTEGER NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS questionnaire_questions_position_idx
  ON questionnaire_questions (position);

CREATE TABLE IF NOT EXISTS drafts (
  access_code TEXT PRIMARY KEY REFERENCES access_codes(code) ON DELETE CASCADE,
  answers JSONB NOT NULL DEFAULT '{}'::jsonb,
  saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS submissions (
  id TEXT PRIMARY KEY,
  access_code TEXT NOT NULL REFERENCES access_codes(code),
  questions JSONB NOT NULL,
  answers JSONB NOT NULL,
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS submissions_submitted_at_idx
  ON submissions (submitted_at DESC);

CREATE INDEX IF NOT EXISTS submissions_access_code_idx
  ON submissions (access_code);
