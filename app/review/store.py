import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue

RUN_SCHEMA = '''CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT
);'''
SOURCE_SCHEMA = '''CREATE TABLE IF NOT EXISTS sources (
    run_id TEXT PRIMARY KEY, data BLOB NOT NULL
);'''
SUPPLEMENT_SCHEMA = '''CREATE TABLE IF NOT EXISTS supplements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, record_key TEXT NOT NULL,
    action TEXT NOT NULL, definition TEXT, note TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE', revision INTEGER NOT NULL DEFAULT 1,
    created TEXT NOT NULL, withdrawn TEXT
);'''
SUPPLEMENT_INDEX = '''CREATE UNIQUE INDEX IF NOT EXISTS idx_supplement_active
    ON supplements(run_id, record_key) WHERE status = 'ACTIVE';'''


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute(RUN_SCHEMA)
            db.execute(SOURCE_SCHEMA)
            db.execute(SUPPLEMENT_SCHEMA)
            db.execute(SUPPLEMENT_INDEX)
            yield db

    def register(self, run_id, report, source=None):
        with self.connect() as db:
            db.execute('INSERT INTO runs(id,report,created) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',
                       (run_id,json.dumps(report,ensure_ascii=False),report['manifest']['created']))
            if source is not None:
                db.execute('INSERT INTO sources(run_id,data) VALUES (?,?) ON CONFLICT(run_id) DO NOTHING',
                           (run_id,sqlite3.Binary(source)))
        return self.load(run_id)

    def source(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM sources WHERE run_id=?',(run_id,)).fetchone()
        return None if row is None else bytes(row['data'])

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if row is None:
            raise DomainIssue('RUN_NOT_FOUND')
        result = dict(row)
        result['report'] = json.loads(result['report'])
        return result

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,created,status,revision,note FROM runs ORDER BY created DESC,id LIMIT 50')]

    def revise(self, run_id, revision, status, note, now):
        with self.connect() as db:
            cursor = db.execute('UPDATE runs SET status=?,note=?,reviewed=?,revision=revision+1 WHERE id=? AND revision=?',
                                (status,note,now,run_id,revision))
            if cursor.rowcount != 1:
                raise DomainIssue('STALE_REVIEW')
        return self.load(run_id)

    def add_supplement(self, run_id, record_key, action, definition, note, now):
        payload = json.dumps(definition, ensure_ascii=False) if definition is not None else None
        with self.connect() as db:
            try:
                cursor = db.execute(
                    'INSERT INTO supplements(run_id,record_key,action,definition,note,created) VALUES (?,?,?,?,?,?)',
                    (run_id,record_key,action,payload,note,now))
            except sqlite3.IntegrityError as error:
                raise DomainIssue('SUPPLEMENT_EXISTS') from error
            row = db.execute('SELECT * FROM supplements WHERE id=?',(cursor.lastrowid,)).fetchone()
        return self._supplement(row)

    def withdraw_supplement(self, supplement_id, run_id, revision, now):
        with self.connect() as db:
            row = db.execute('SELECT * FROM supplements WHERE id=? AND run_id=?',(supplement_id,run_id)).fetchone()
            if row is None:
                raise DomainIssue('SUPPLEMENT_NOT_FOUND')
            if row['status'] != 'ACTIVE' or row['revision'] != revision:
                raise DomainIssue('STALE_REVIEW')
            if row['action'] != 'CORRECT':
                raise DomainIssue('SUPPLEMENT_NOT_ADOPTED')
            cursor = db.execute(
                "UPDATE supplements SET status='WITHDRAWN', withdrawn=?, revision=revision+1 "
                'WHERE id=? AND status=\'ACTIVE\' AND revision=?',(now,supplement_id,revision))
            if cursor.rowcount != 1:
                raise DomainIssue('STALE_REVIEW')
            row = db.execute('SELECT * FROM supplements WHERE id=?',(supplement_id,)).fetchone()
        return self._supplement(row)

    def supplements(self, run_id):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM supplements WHERE run_id=? ORDER BY id',(run_id,)).fetchall()
        return [self._supplement(row) for row in rows]

    @staticmethod
    def _supplement(row):
        item = dict(row)
        item['definition'] = json.loads(item['definition']) if item['definition'] else None
        return item
