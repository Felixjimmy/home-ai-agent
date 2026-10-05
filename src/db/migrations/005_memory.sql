CREATE TABLE conversation_sessions (
    id uuid PRIMARY KEY,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','deleted','expired')),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    last_used_at timestamptz NOT NULL DEFAULT NOW(),
    deleted_at timestamptz
);

CREATE TABLE conversation_messages (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    sequence integer NOT NULL,
    role text NOT NULL CHECK (role IN ('user','assistant','tool','system')),
    content text NOT NULL,
    request_id uuid,
    model text,
    char_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    UNIQUE(session_id, sequence)
);

CREATE TABLE conversation_summaries (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    covered_through integer NOT NULL,
    summary text NOT NULL,
    summary_version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    UNIQUE(session_id, covered_through)
);

CREATE TABLE memory_records (
    id uuid PRIMARY KEY,
    key text NOT NULL,
    value jsonb NOT NULL,
    scope text NOT NULL DEFAULT 'household',
    display_text text NOT NULL,
    source text NOT NULL CHECK (source IN ('explicit_user','confirmed_action','imported')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','forgotten')),
    revision integer NOT NULL DEFAULT 1,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    forgotten_at timestamptz,
    source_session_id uuid REFERENCES conversation_sessions(id),
    source_request_id uuid
);

CREATE INDEX memory_active_lookup ON memory_records(status, scope, key, updated_at DESC);
CREATE INDEX conversation_messages_recent ON conversation_messages(session_id, sequence DESC);
