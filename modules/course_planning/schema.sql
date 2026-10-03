-- Development design, not applied to any database.
CREATE TABLE learning_plans (
  id uuid PRIMARY KEY, user_id uuid NOT NULL, map_version text NOT NULL,
  profile_version bigint NOT NULL, rule_version text NOT NULL,
  target_id text NOT NULL, rationale jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE teaching_assignments (
  id uuid PRIMARY KEY, plan_id uuid NOT NULL REFERENCES learning_plans(id),
  schema_version text NOT NULL, payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE generation_jobs (
  id uuid PRIMARY KEY, user_id uuid NOT NULL, idempotency_key text NOT NULL,
  request_hash text NOT NULL, assignment_id uuid REFERENCES teaching_assignments(id),
  request jsonb NOT NULL, state text NOT NULL CHECK (state IN
    ('queued','planning','generating_text','checking_text','generating_audio','checking_audio','approved','needs_review','failed','cancelled')),
  row_version bigint NOT NULL DEFAULT 1, stage_attempts jsonb NOT NULL DEFAULT '{}',
  lease_owner text, lease_until timestamptz, next_attempt_at timestamptz,
  error jsonb, budget jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(user_id,idempotency_key)
);
CREATE INDEX generation_jobs_ready ON generation_jobs(state,next_attempt_at,lease_until);
CREATE TABLE lesson_versions (
  lesson_id uuid NOT NULL, version integer NOT NULL, assignment_id uuid NOT NULL REFERENCES teaching_assignments(id),
  map_version text NOT NULL, schema_version text NOT NULL, status text NOT NULL CHECK(status IN ('draft','approved','needs_review')),
  server_payload jsonb NOT NULL, provenance jsonb NOT NULL, learner_ready boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(lesson_id,version), CHECK(NOT learner_ready OR status='approved')
);
CREATE TABLE quality_reports (
  id uuid PRIMARY KEY, job_id uuid NOT NULL REFERENCES generation_jobs(id),
  lesson_id uuid NOT NULL, lesson_version integer NOT NULL, stage text NOT NULL,
  checker_version text NOT NULL, decision text NOT NULL CHECK(decision IN ('pass','fail','unjudgeable')),
  checks jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(lesson_id,lesson_version) REFERENCES lesson_versions(lesson_id,version)
);
CREATE TABLE audio_assets (
  id uuid PRIMARY KEY, lesson_id uuid NOT NULL, lesson_version integer NOT NULL,
  text_hash text NOT NULL, voice_version text NOT NULL, object_ref text NOT NULL,
  purpose text NOT NULL, quality_status text NOT NULL, metadata jsonb NOT NULL,
  FOREIGN KEY(lesson_id,lesson_version) REFERENCES lesson_versions(lesson_id,version)
);
CREATE TABLE outbox_events (
  id uuid PRIMARY KEY, event_type text NOT NULL, aggregate_id uuid NOT NULL,
  aggregate_version integer NOT NULL, payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz,
  UNIQUE(event_type,aggregate_id,aggregate_version)
);
-- Ownership and publication checks are enforced by application transactions.
-- Published lesson versions are immutable; create a new version to revise.
-- No database connection, migration or production worker has been created.
