-- Apply through the consumer's reviewed migration; isolated namespace per app/environment.
CREATE TABLE IF NOT EXISTS nienfos_push_devices (
 app_id TEXT NOT NULL, environment TEXT NOT NULL CHECK(environment IN ('dev','qa','prod')),
 installation_id TEXT NOT NULL, fid TEXT NOT NULL,
 platform TEXT NOT NULL DEFAULT 'web' CHECK(platform IN ('web','android','ios')),
 user_id TEXT NOT NULL, tenant_id TEXT NOT NULL, session_id TEXT NOT NULL,
 updated_at INTEGER NOT NULL,
 PRIMARY KEY(app_id,environment,installation_id),
 UNIQUE(app_id,environment,fid)
);
CREATE INDEX IF NOT EXISTS nienfos_push_recipient ON nienfos_push_devices(app_id,environment,tenant_id,user_id,updated_at);
CREATE TABLE IF NOT EXISTS nienfos_push_outbox (
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL, environment TEXT NOT NULL,
 installation_id TEXT NOT NULL, fid TEXT NOT NULL,
 platform TEXT NOT NULL DEFAULT 'web' CHECK(platform IN ('web','android','ios')),
 user_id TEXT NOT NULL, tenant_id TEXT NOT NULL, session_id TEXT NOT NULL,
 event_id TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, path TEXT NOT NULL,
 expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','accepted','failed','cancelled')),
 attempt INTEGER NOT NULL DEFAULT 0, next_at INTEGER NOT NULL,
 lease TEXT, lease_until INTEGER NOT NULL DEFAULT 0, last_code TEXT,
 UNIQUE(app_id,environment,installation_id,event_id)
);
CREATE INDEX IF NOT EXISTS nienfos_push_due ON nienfos_push_outbox(app_id,environment,state,next_at,lease_until);
-- Additive: the push schema remains generation 3. Apply both on new consumers.
CREATE TABLE IF NOT EXISTS nienfos_notice_inbox (
 app_id TEXT NOT NULL, environment TEXT NOT NULL,
 tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, event_id TEXT NOT NULL,
 kind TEXT NOT NULL, resource_id TEXT NOT NULL,
 title TEXT NOT NULL, body TEXT NOT NULL, path TEXT NOT NULL,
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
 read_at INTEGER, cancelled_at INTEGER, expanded_at INTEGER,
 PRIMARY KEY(app_id,environment,tenant_id,user_id,event_id)
);
CREATE INDEX IF NOT EXISTS nienfos_notice_pending ON nienfos_notice_inbox(app_id,environment,expanded_at,created_at);
CREATE INDEX IF NOT EXISTS nienfos_notice_reader ON nienfos_notice_inbox(app_id,environment,tenant_id,user_id,created_at);
CREATE TABLE IF NOT EXISTS nienfos_notice_preferences (
 app_id TEXT NOT NULL, environment TEXT NOT NULL, tenant_id TEXT NOT NULL,
 user_id TEXT NOT NULL, kind TEXT NOT NULL,
 web INTEGER NOT NULL CHECK(web IN (0,1)), android INTEGER NOT NULL CHECK(android IN (0,1)),
 updated_at INTEGER NOT NULL,
 PRIMARY KEY(app_id,environment,tenant_id,user_id,kind)
);

-- Bridge identity is the existing private tailnet, not a new user directory.
CREATE TABLE IF NOT EXISTS bridge_push_installations (
 id TEXT PRIMARY KEY, credential_hash TEXT NOT NULL UNIQUE,
 enabled INTEGER NOT NULL DEFAULT 1, verified_at INTEGER, created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bridge_push_events (
 id TEXT PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
 session_id TEXT, run_id TEXT, message_id TEXT, job_id TEXT,
 installation_id TEXT, kind TEXT NOT NULL DEFAULT 'chat.completed',
 created_at INTEGER NOT NULL, ready_at INTEGER, expanded_at INTEGER,
 cancelled_at INTEGER
);
CREATE TABLE IF NOT EXISTS bridge_push_reads (
 installation_id TEXT NOT NULL, resource TEXT NOT NULL, read_at INTEGER NOT NULL,
 PRIMARY KEY(installation_id,resource)
);
CREATE TABLE IF NOT EXISTS bridge_push_limits (
 bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, window_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bridge_project_logos (
 workspace_path TEXT PRIMARY KEY, relative_path TEXT NOT NULL, updated_at INTEGER NOT NULL
);
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
