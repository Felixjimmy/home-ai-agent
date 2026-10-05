CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE document_uploads (
 id uuid PRIMARY KEY, storage_key text NOT NULL, filename text NOT NULL,
 sha256 text NOT NULL, byte_size bigint NOT NULL, media_type text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT NOW(), expires_at timestamptz NOT NULL DEFAULT NOW()+interval '24 hours'
);
CREATE TABLE home_documents (
 id uuid PRIMARY KEY, title text NOT NULL, category text NOT NULL DEFAULT 'household',
 appliance_model text, effective_date date, revision integer NOT NULL DEFAULT 1,
 active_version_id uuid, deleted_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT NOW(), updated_at timestamptz NOT NULL DEFAULT NOW()
);
CREATE TABLE home_document_versions (
 id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES home_documents(id),
 upload_id uuid REFERENCES document_uploads(id), source_hash text NOT NULL,
 filename text NOT NULL, media_type text NOT NULL, storage_key text NOT NULL,
 byte_size bigint NOT NULL, config jsonb NOT NULL, config_hash text NOT NULL,
 expected_revision integer NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','ready','failed','deleted')),
 error text, created_at timestamptz NOT NULL DEFAULT NOW(),
 UNIQUE(document_id,source_hash,config_hash), UNIQUE(document_id,id)
);
ALTER TABLE home_documents ADD CONSTRAINT document_active_version
 FOREIGN KEY (id,active_version_id) REFERENCES home_document_versions(document_id,id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE home_document_chunks (
 id uuid PRIMARY KEY, version_id uuid NOT NULL REFERENCES home_document_versions(id) ON DELETE CASCADE,
 ordinal integer NOT NULL, text text NOT NULL, section text,
 page_start integer, page_end integer, char_count integer NOT NULL, text_hash text NOT NULL,
 embedding vector(768) NOT NULL, UNIQUE(version_id,ordinal)
);
CREATE TABLE document_ingestion_jobs (
 id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES home_documents(id),
 version_id uuid REFERENCES home_document_versions(id), action_id uuid UNIQUE REFERENCES pending_actions(id),
 kind text NOT NULL DEFAULT 'index' CHECK(kind IN ('index','delete')),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','processing','completed','failed','cancelled')),
 attempts integer NOT NULL DEFAULT 0, lease_until timestamptz, lease_token uuid,
 error text, created_at timestamptz NOT NULL DEFAULT NOW(), completed_at timestamptz
);
CREATE UNIQUE INDEX document_active_job ON document_ingestion_jobs(version_id) WHERE state IN ('queued','processing');
CREATE INDEX document_jobs_queue ON document_ingestion_jobs(state,created_at);
