"""Persistência: perfil, histórico, playlists, contas e grafo global.

Usa SQLite por padrão (local e testes) e PostgreSQL quando o endereço de um banco é informado
(variável DATABASE_URL, por exemplo o Postgres do Neon). Assim as contas e playlists não somem
quando a hospedagem reinicia. O grafo global guarda apenas pares de faixas (A → B), nunca dados pessoais.
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
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, nome TEXT UNIQUE COLLATE NOCASE, hash TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS auth(token TEXT PRIMARY KEY, user_id TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS transicoes(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ts REAL, tipo TEXT,
                                      prev_id TEXT, cand_id TEXT, x_vibe REAL, x_bpm REAL, x_tom REAL,
                                      x_energia REAL, y INTEGER, peso REAL);
CREATE INDEX IF NOT EXISTS history_user ON history(user_id);
CREATE INDEX IF NOT EXISTS playlists_user ON playlists(user_id);
CREATE INDEX IF NOT EXISTS transicoes_user ON transicoes(user_id);
"""

# Mesmo esquema para PostgreSQL: timestamps em precisão dupla, id de histórico automático e
# usuário único sem diferenciar maiúsculas de minúsculas.
SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS weights(user_id TEXT, key TEXT, value DOUBLE PRECISION, updated_at DOUBLE PRECISION,
                                   PRIMARY KEY(user_id, key));
CREATE TABLE IF NOT EXISTS history(id BIGSERIAL PRIMARY KEY, user_id TEXT, ts DOUBLE PRECISION,
                                   type TEXT, track_id TEXT, query TEXT, fraction DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS playlists(id TEXT PRIMARY KEY, user_id TEXT, title TEXT, tags TEXT,
                                     track_ids TEXT, created_at DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS graph(a TEXT, b TEXT, count INTEGER, PRIMARY KEY(a, b));
CREATE TABLE IF NOT EXISTS tracks(id TEXT PRIMARY KEY, data TEXT, seq BIGSERIAL);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, nome TEXT, hash TEXT, created_at DOUBLE PRECISION);
CREATE UNIQUE INDEX IF NOT EXISTS users_nome_ci ON users(lower(nome));
CREATE TABLE IF NOT EXISTS auth(token TEXT PRIMARY KEY, user_id TEXT, expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS transicoes(id BIGSERIAL PRIMARY KEY, user_id TEXT, ts DOUBLE PRECISION, tipo TEXT,
                                      prev_id TEXT, cand_id TEXT, x_vibe DOUBLE PRECISION, x_bpm DOUBLE PRECISION,
                                      x_tom DOUBLE PRECISION, x_energia DOUBLE PRECISION, y INTEGER,
                                      peso DOUBLE PRECISION);
CREATE INDEX IF NOT EXISTS history_user ON history(user_id);
CREATE INDEX IF NOT EXISTS playlists_user ON playlists(user_id);
CREATE INDEX IF NOT EXISTS transicoes_user ON transicoes(user_id);
"""


def eh_postgres(caminho):
    return isinstance(caminho, str) and caminho.startswith(("postgres://", "postgresql://"))


class Store:
    def __init__(self, path=":memory:"):
        self.path = path
        self._lock = threading.Lock()
        self._pg = eh_postgres(path)
        self._pgconn = None
        self._mem = sqlite3.connect(path, check_same_thread=False) if path == ":memory:" else None
        if self._pg:
            self._run_script(SCHEMA_PG)
        else:
            with self._conn() as c:
                c.executescript(SCHEMA)

    def _conn(self):
        return self._mem if self._mem else sqlite3.connect(self.path, timeout=10)

    # PostgreSQL: uma conexão reaproveitada (abrir uma a cada consulta é lento) e refeita se o banco
    # tiver dormido ou derrubado a conexão (o Neon suspende o banco quando fica parado).
    def _pg_conectar(self):
        import psycopg                                  # só é necessário quando há DATABASE_URL
        if self._pgconn is None or self._pgconn.closed:
            self._pgconn = psycopg.connect(self.path, connect_timeout=15)
        return self._pgconn

    def _pg_fechar(self):
        try:
            if self._pgconn is not None:
                self._pgconn.close()
        except Exception:
            pass
        self._pgconn = None

    def _run_script(self, script):
        with self._lock:
            for tentativa in (1, 2):
                try:
                    c = self._pg_conectar()
                    c.execute(script)
                    c.commit()
                    return
                except Exception as e:
                    self._pg_fechar()
                    if tentativa == 2 or not self._erro_de_conexao(e):
                        raise

    @staticmethod
    def _erro_de_conexao(e):
        import psycopg
        return isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError))

    def _run_pg(self, sql, args, many, fetch):
        sql = sql.replace("?", "%s")
        for tentativa in (1, 2):
            try:
                c = self._pg_conectar()
                with c.cursor() as cur:
                    if many:
                        cur.executemany(sql, args)
                    else:
                        cur.execute(sql, args)
                    rows = cur.fetchall() if fetch else None
                c.commit()
                return rows
            except Exception as e:
                try:
                    if self._pgconn is not None and not self._pgconn.closed:
                        self._pgconn.rollback()
                except Exception:
                    pass
                if tentativa == 1 and self._erro_de_conexao(e):
                    self._pg_fechar()                    # banco dormiu: reconecta e tenta de novo
                    continue
                raise

    def _run(self, sql, args=(), many=False, fetch=False):
        with self._lock:
            if self._pg:
                return self._run_pg(sql, args, many, fetch)
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
        self.delete_transicoes(uid)                      # o que o app aprendeu sobre a pessoa inclui os exemplos de treino

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
        self.delete_transicoes(uid)

    # transições avaliadas (exemplos de treino dos pesos; ver soulsbpm/aprendizado.py) ----------
    def add_transicao(self, uid, tipo, prev_id, cand_id, x, y, peso, ts=None):
        self._run("INSERT INTO transicoes(user_id,ts,tipo,prev_id,cand_id,x_vibe,x_bpm,x_tom,x_energia,y,peso) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (uid, ts or time.time(), tipo, prev_id, cand_id, *x, y, peso))

    def remove_transicao(self, uid, tipo, prev_id, cand_id):
        """Apaga só o registro mais recente igual a este (usado quando a pessoa desfaz o gesto)."""
        self._run("DELETE FROM transicoes WHERE id=(SELECT MAX(id) FROM transicoes "
                  "WHERE user_id=? AND tipo=? AND prev_id=? AND cand_id=?)", (uid, tipo, prev_id, cand_id))

    def transicoes(self, limite):
        """Os exemplos mais recentes: (x_vibe, x_bpm, x_tom, x_energia, y, peso)."""
        return [tuple(r) for r in self._run(
            "SELECT x_vibe,x_bpm,x_tom,x_energia,y,peso FROM transicoes ORDER BY id DESC LIMIT ?", (limite,), fetch=True)]

    def delete_transicoes(self, uid):
        self._run("DELETE FROM transicoes WHERE user_id=?", (uid,))

    # playlists e grafo ---------------------------------------------------
    def save_playlist(self, uid, title, tags, track_ids, grafo=True):
        """grafo=False: playlist montada à mão (ordem não é uma transição de DJ), então não alimenta o grafo global."""
        pid = secrets.token_urlsafe(6)
        self._run("INSERT INTO playlists VALUES(?,?,?,?,?,?)",
                  (pid, uid, title, json.dumps(tags, ensure_ascii=False), json.dumps(track_ids), time.time()))
        pares = [(a, b) for a, b in zip(track_ids, track_ids[1:])]
        if grafo and pares:
            self._run("INSERT INTO graph VALUES(?,?,1) ON CONFLICT(a,b) DO UPDATE SET count=graph.count+1",
                      pares, many=True)
        return pid

    def update_playlist(self, pid, title=None, tags=None, track_ids=None):
        """Troca só o que for informado (título, tags, lista de faixas). A checagem de dono fica no motor."""
        campos, args = [], []
        if title is not None:
            campos.append("title=?")
            args.append(title)
        if tags is not None:
            campos.append("tags=?")
            args.append(json.dumps(tags, ensure_ascii=False))
        if track_ids is not None:
            campos.append("track_ids=?")
            args.append(json.dumps(track_ids))
        if campos:
            self._run(f"UPDATE playlists SET {', '.join(campos)} WHERE id=?", (*args, pid))

    def delete_playlist(self, pid):
        self._run("DELETE FROM playlists WHERE id=?", (pid,))

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
        self._run("INSERT INTO tracks(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                  [(f["id"], json.dumps(f, ensure_ascii=False)) for f in faixas], many=True)

    def load_tracks(self):
        ordem = "seq" if self._pg else "rowid"
        return [json.loads(r[0]) for r in self._run(f"SELECT data FROM tracks ORDER BY {ordem}", fetch=True)]

    def graph_count(self, a, b):
        rows = self._run("SELECT count FROM graph WHERE a=? AND b=?", (a, b), fetch=True)
        return rows[0][0] if rows else 0

    def graph_pairs(self):
        return self._run("SELECT a,b,count FROM graph", fetch=True)
