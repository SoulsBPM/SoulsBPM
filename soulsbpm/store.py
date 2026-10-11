"""Persistência em SQLite: perfil, histórico, playlists e grafo global.

Substitui o PostgreSQL sugerido no documento 5 só para o MVP rodar sem infraestrutura.
O grafo global guarda apenas pares de faixas (A → B), nunca dados pessoais.
"""
import json
import secrets
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS weights(user_id TEXT, key TEXT, value REAL, updated_at REAL,
                                   PRIMARY KEY(user_id, key));
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ts REAL,
                                   type TEXT, track_id TEXT, query TEXT, fraction REAL);
CREATE TABLE IF NOT EXISTS playlists(id TEXT PRIMARY KEY, user_id TEXT, title TEXT, tags TEXT,
                                     track_ids TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS graph(a TEXT, b TEXT, count INTEGER, PRIMARY KEY(a, b));
CREATE TABLE IF NOT EXISTS tracks(id TEXT PRIMARY KEY, data TEXT);
"""


class Store:
    def __init__(self, path=":memory:"):
        self.path = path
        self._lock = threading.Lock()
        self._mem = sqlite3.connect(path, check_same_thread=False) if path == ":memory:" else None
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return self._mem if self._mem else sqlite3.connect(self.path, timeout=10)

    def _run(self, sql, args=(), many=False, fetch=False):
        with self._lock:
            c = self._conn()
            try:
                cur = c.executemany(sql, args) if many else c.execute(sql, args)
                rows = cur.fetchall() if fetch else None
                c.commit()
                return rows
            finally:
                if not self._mem:
                    c.close()

    # perfil -------------------------------------------------------------
    def get_weights(self, uid):
        rows = self._run("SELECT key,value,updated_at FROM weights WHERE user_id=?", (uid,), fetch=True)
        return {k: (v, ts) for k, v, ts in rows}

    def set_weight(self, uid, key, value, ts):
        self._run("INSERT INTO weights VALUES(?,?,?,?) ON CONFLICT(user_id,key) "
                  "DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                  (uid, key, value, ts))

    def reset_profile(self, uid):
        self._run("DELETE FROM weights WHERE user_id=?", (uid,))

    # histórico ----------------------------------------------------------
    def add_history(self, uid, type_, track_id=None, query=None, fraction=None, ts=None):
        if not uid:
            return
        self._run("INSERT INTO history(user_id,ts,type,track_id,query,fraction) VALUES(?,?,?,?,?,?)",
                  (uid, ts or time.time(), type_, track_id, query, fraction))

    def recent_queries(self, uid, limit=5):
        rows = self._run("SELECT query FROM history WHERE user_id=? AND type='search' AND query IS NOT NULL "
                         "GROUP BY query ORDER BY MAX(ts) DESC LIMIT ?", (uid, limit), fetch=True)
        return [r[0] for r in rows]

    def history(self, uid):
        rows = self._run("SELECT ts,type,track_id,query,fraction FROM history WHERE user_id=? ORDER BY id",
                         (uid,), fetch=True)
        return [dict(ts=r[0], type=r[1], track_id=r[2], query=r[3], fraction=r[4]) for r in rows]

    def delete_history(self, uid):
        self._run("DELETE FROM history WHERE user_id=?", (uid,))

    # playlists e grafo ---------------------------------------------------
    def save_playlist(self, uid, title, tags, track_ids):
        pid = secrets.token_urlsafe(6)
        self._run("INSERT INTO playlists VALUES(?,?,?,?,?,?)",
                  (pid, uid, title, json.dumps(tags, ensure_ascii=False), json.dumps(track_ids), time.time()))
        pares = [(a, b) for a, b in zip(track_ids, track_ids[1:])]
        self._run("INSERT INTO graph VALUES(?,?,1) ON CONFLICT(a,b) DO UPDATE SET count=count+1",
                  pares, many=True)
        return pid

    @staticmethod
    def _pl(r):
        return dict(id=r[0], user_id=r[1], title=r[2], tags=json.loads(r[3]),
                    track_ids=json.loads(r[4]), created_at=r[5])

    def get_playlist(self, pid):
        rows = self._run("SELECT * FROM playlists WHERE id=?", (pid,), fetch=True)
        return self._pl(rows[0]) if rows else None

    def list_playlists(self, uid):
        rows = self._run("SELECT * FROM playlists WHERE user_id=? ORDER BY created_at DESC", (uid,), fetch=True)
        return [self._pl(r) for r in rows]

    # faixas reais descobertas no modo ao vivo (só metadados) ------------------
    def save_tracks(self, faixas):
        self._run("INSERT OR REPLACE INTO tracks VALUES(?,?)",
                  [(f["id"], json.dumps(f, ensure_ascii=False)) for f in faixas], many=True)

    def load_tracks(self):
        return [json.loads(r[0]) for r in self._run("SELECT data FROM tracks ORDER BY rowid", fetch=True)]

    def graph_count(self, a, b):
        rows = self._run("SELECT count FROM graph WHERE a=? AND b=?", (a, b), fetch=True)
        return rows[0][0] if rows else 0

    def graph_pairs(self):
        return self._run("SELECT a,b,count FROM graph", fetch=True)
