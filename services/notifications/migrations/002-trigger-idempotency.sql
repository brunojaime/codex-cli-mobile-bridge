-- Preserve existing intent IDs/outbox links while replacing conflict-sensitive triggers.
BEGIN IMMEDIATE;
DROP TRIGGER IF EXISTS bridge_push_message_insert;
DROP TRIGGER IF EXISTS bridge_push_message_update;
CREATE TRIGGER IF NOT EXISTS bridge_push_message_insert AFTER INSERT ON messages
WHEN NEW.role='assistant' AND NEW.status IN ('completed','failed')
BEGIN
 INSERT INTO bridge_push_events(id,event_key,session_id,run_id,message_id,job_id,created_at)
 VALUES(lower(hex(randomblob(16))),COALESCE('run:'||NEW.run_id,'job:'||NEW.job_id,'message:'||NEW.id),
 NEW.session_id,NEW.run_id,NEW.id,NEW.job_id,CAST(strftime('%s','now') AS INTEGER)*1000) ON CONFLICT(event_key) DO NOTHING;
END;
CREATE TRIGGER IF NOT EXISTS bridge_push_message_update AFTER UPDATE OF status ON messages
WHEN NEW.role='assistant' AND NEW.status IN ('completed','failed') AND OLD.status NOT IN ('completed','failed')
BEGIN
 INSERT INTO bridge_push_events(id,event_key,session_id,run_id,message_id,job_id,created_at)
 VALUES(lower(hex(randomblob(16))),COALESCE('run:'||NEW.run_id,'job:'||NEW.job_id,'message:'||NEW.id),
 NEW.session_id,NEW.run_id,NEW.id,NEW.job_id,CAST(strftime('%s','now') AS INTEGER)*1000) ON CONFLICT(event_key) DO NOTHING;
END;

COMMIT;
