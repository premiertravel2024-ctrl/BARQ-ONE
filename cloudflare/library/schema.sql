-- BARQ ONE online library: only the owner publishes, users read by Google identity.
CREATE TABLE IF NOT EXISTS owner_drive (
 singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
 owner_sub TEXT NOT NULL,
 refresh_cipher TEXT NOT NULL,
 root_folder TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS series (
 id TEXT PRIMARY KEY,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS books (
 id TEXT PRIMARY KEY,
 title TEXT NOT NULL,
 original_title TEXT NOT NULL,
 folder_name TEXT NOT NULL DEFAULT '',
 cover_id TEXT,
 size_bytes INTEGER NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
 series_id TEXT REFERENCES series(id) ON DELETE SET NULL,
 issue_number INTEGER,
 position INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_books_public ON books(published,active,position);
CREATE TABLE IF NOT EXISTS reader_progress (
 reader_sub TEXT NOT NULL,
 book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
 page INTEGER NOT NULL DEFAULT 1,
 favourite INTEGER NOT NULL DEFAULT 0 CHECK(favourite IN (0,1)),
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(reader_sub,book_id)
);
