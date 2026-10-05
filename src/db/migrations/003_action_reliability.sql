ALTER TABLE pending_actions ADD COLUMN IF NOT EXISTS payload_version integer NOT NULL DEFAULT 1;
ALTER TABLE pending_actions ADD COLUMN IF NOT EXISTS request_id uuid;
ALTER TABLE pending_actions ADD COLUMN IF NOT EXISTS idempotency_key text;
ALTER TABLE pending_actions DROP CONSTRAINT IF EXISTS pending_actions_status_check;
ALTER TABLE pending_actions ADD CONSTRAINT pending_actions_status_check
 CHECK (status IN ('pending','confirmed','rejected','failed','expired'));
-- Old 'failed' rows represented expiry in Phase 2.
UPDATE pending_actions SET status='expired' WHERE status='failed' AND payload_version=1;
UPDATE pending_actions SET status='expired', completed_at=NOW()
 WHERE status='pending' AND payload_version=1;
CREATE UNIQUE INDEX IF NOT EXISTS pending_actions_idempotency ON pending_actions(idempotency_key)
 WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS pending_actions_request ON pending_actions(request_id);
ALTER TABLE tool_call_logs ADD COLUMN IF NOT EXISTS request_id uuid;
