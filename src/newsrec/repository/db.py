import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from newsrec.domain.page import Page


class Repository:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "blobs").mkdir(exist_ok=True)
        self.database = self.root / "metadata.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY, document_id TEXT NOT NULL
                  REFERENCES documents(id) ON DELETE CASCADE, image TEXT, thumbnail TEXT,
                  image_hash TEXT);
                CREATE TABLE IF NOT EXISTS results(page_id TEXT REFERENCES pages(id) ON DELETE CASCADE,
                  engine TEXT, data TEXT NOT NULL, PRIMARY KEY(page_id, engine));
                CREATE TABLE IF NOT EXISTS corrections(page_id TEXT REFERENCES pages(id) ON DELETE CASCADE,
                  engine TEXT, block_id INTEGER, line_index INTEGER, text TEXT NOT NULL,
                  PRIMARY KEY(page_id, engine, block_id, line_index));
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,
                  page_id TEXT REFERENCES pages(id) ON DELETE CASCADE, engine TEXT, status TEXT);
                CREATE TABLE IF NOT EXISTS events(job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
                  sequence INTEGER, data TEXT NOT NULL, PRIMARY KEY(job_id, sequence));
            """)
            # Databases created before content addressing predate the column; NULL hashes
            # never collide in SQLite, so older pages simply stay uncached.
            if "image_hash" not in {row[1] for row in db.execute("PRAGMA table_info(pages)")}:
                db.execute("ALTER TABLE pages ADD COLUMN image_hash TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS pages_image_hash ON pages(image_hash)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def blob_path(self, name):
        if str(UUID(name)) != name:
            raise ValueError("invalid blob id")
        return self.root / "blobs" / name

    def put_blob(self, content):
        name = str(uuid4())
        self.blob_path(name).write_bytes(content)
        return name

    def page_by_hash(self, image_hash):
        with self.connect() as db:
            row = db.execute("SELECT document_id, id AS page_id FROM pages WHERE image_hash=?",
                             (image_hash,)).fetchone()
            return dict(row) if row else None

    def create_document(self, name, image, thumbnail, image_hash):
        """Content addressed: the same scan dropped twice reuses its recognition.

        The digest is over the normalised PNG, so the same page re-encoded or
        arriving as TIFF instead of PNG still hits the cache.
        """
        cached = self.page_by_hash(image_hash)
        if cached:
            return {**cached, "cached": True}
        document_id, page_id = str(uuid4()), str(uuid4())
        blobs = []
        try:
            blobs.append(self.put_blob(image))
            blobs.append(self.put_blob(thumbnail))
            with self.connect() as db:
                db.execute("INSERT INTO documents VALUES (?,?)", (document_id, name))
                db.execute("INSERT INTO pages VALUES (?,?,?,?,?)",
                           (page_id, document_id, *blobs, image_hash))
        except Exception as exc:
            for blob in blobs:
                self.blob_path(blob).unlink(missing_ok=True)
            # Two identical scans uploaded at once: the loser reuses the winner's row.
            if isinstance(exc, sqlite3.IntegrityError) and (cached := self.page_by_hash(image_hash)):
                return {**cached, "cached": True}
            raise
        return {"document_id": document_id, "page_id": page_id, "cached": False}

    def documents(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT d.*, p.id AS page_id FROM documents d JOIN pages p ON p.document_id=d.id ORDER BY d.rowid DESC")]

    def page_ref(self, page_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM pages WHERE id=?", (page_id,)).fetchone()
            if row is None:
                raise KeyError(page_id)
            return dict(row)

    def delete_document(self, document_id):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM jobs JOIN pages ON jobs.page_id=pages.id WHERE document_id=? AND status IN ('queued','running')", (document_id,)).fetchone():
                raise ValueError("document has an active job")
            blobs = db.execute("SELECT image,thumbnail FROM pages WHERE document_id=?", (document_id,)).fetchall()
            if not db.execute("DELETE FROM documents WHERE id=?", (document_id,)).rowcount:
                raise KeyError(document_id)
        for row in blobs:
            for name in row:
                self.blob_path(name).unlink(missing_ok=True)

    def save_page(self, page_id, page):
        with self.connect() as db:
            db.execute("INSERT INTO results VALUES (?,?,?) ON CONFLICT(page_id,engine) DO UPDATE SET data=excluded.data", (page_id, page.engine, json.dumps(page.to_dict(), ensure_ascii=False)))
            # Indices belong to a particular recognition; stale edits must never move silently.
            db.execute("DELETE FROM corrections WHERE page_id=? AND engine=?", (page_id, page.engine))

    def get_page(self, page_id, engine):
        with self.connect() as db:
            row = db.execute("SELECT data FROM results WHERE page_id=? AND engine=?", (page_id, engine)).fetchone()
            if row is None:
                raise KeyError("recognition result not found")
            return Page.from_dict(json.loads(row[0]))

    def get_corrections(self, page_id, engine):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT block_id,line_index,text FROM corrections WHERE page_id=? AND engine=? ORDER BY block_id,line_index", (page_id, engine))]

    def replace_corrections(self, page_id, engine, edits):
        with self.connect() as db:
            db.execute("DELETE FROM corrections WHERE page_id=? AND engine=?", (page_id, engine))
            db.executemany("INSERT INTO corrections VALUES (?,?,?,?,?)", [(page_id, engine, e["block_id"], e["line_index"], e["text"]) for e in edits])

    def create_job(self, page_id, engine):
        job_id = str(uuid4())
        with self.connect() as db:
            if db.execute("SELECT 1 FROM jobs WHERE page_id=? AND status IN ('queued','running')", (page_id,)).fetchone():
                raise ValueError("page already has an active job")
            db.execute("INSERT INTO jobs VALUES (?,?,?,'queued')", (job_id, page_id, engine))
        return job_id

    def job(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            events = [json.loads(r[0]) for r in db.execute("SELECT data FROM events WHERE job_id=? ORDER BY sequence", (job_id,))]
            return {**dict(row), "events": events}

    def append_event(self, job_id, data):
        with self.connect() as db:
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE job_id=?", (job_id,)).fetchone()[0]
            event = {**data, "id": sequence}
            db.execute("INSERT INTO events VALUES (?,?,?)", (job_id, sequence, json.dumps(event, ensure_ascii=False)))
            status = data["stage"] if data["stage"] in ("queued", "done", "error") else "running"
            db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        return event

    def interrupt_jobs(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM jobs WHERE status IN ('queued','running')")]
        for job_id in ids:
            self.append_event(job_id, {"stage": "error", "message": "Server restarted; submit recognition again."})
