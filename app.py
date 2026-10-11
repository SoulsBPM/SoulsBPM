"""API Flask + interface web do SoulsBPM (MVP)."""
import json
import os
import pathlib
import sys

# Se o Flask não estiver instalado no sistema, usa a cópia que acompanha o projeto (pasta libs/).
try:
    import flask  # noqa: F401
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "libs"))

from flask import Flask, jsonify, request, send_from_directory

from soulsbpm import feedback
from soulsbpm.aovivo import provedor_do_ambiente
from soulsbpm.engine import Erro, Motor
from soulsbpm.store import Store

RAIZ = pathlib.Path(__file__).resolve().parent


def create_app(db_path=None, catalog_path=None, provedor=None):
    app = Flask(__name__, static_folder=str(RAIZ / "static"), static_url_path="/static")
    arquivo = catalog_path or os.environ.get("SOULSBPM_CATALOG")
    if provedor is None and not arquivo:                 # com as duas chaves no ambiente, liga o modo ao vivo
        provedor = provedor_do_ambiente(RAIZ / "data")
    # modo ao vivo parte vazio (as faixas reais chegam a cada busca); senão usa o catálogo de amostra/arquivo
    catalogo = [] if (provedor and not arquivo) else json.loads(
        pathlib.Path(arquivo or RAIZ / "data" / "catalog.json").read_text("utf-8"))
    store = Store(db_path or os.environ.get("SOULSBPM_DB", str(RAIZ / "data" / "soulsbpm.db")))
    motor = Motor(catalogo, store, provedor=provedor)
    app.motor, app.store = motor, store

    def corpo():
        return request.get_json(silent=True) or {}

    @app.errorhandler(Erro)
    def erro(e):
        return jsonify({"erro": str(e)}), e.status

    def uid():
        return corpo().get("user_id") or request.args.get("user_id") or None

    @app.get("/")
    @app.get("/p/<pid>")
    def index(pid=None):
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "faixas": len(motor.catalogo), "ao_vivo": bool(provedor)}

    @app.post("/api/search")
    def search():
        return jsonify(motor.buscar(uid(), corpo().get("text")))

    @app.get("/api/recent")
    def recent():
        u = uid()
        return jsonify({"buscas": store.recent_queries(u) if u else []})

    @app.post("/api/session/<sid>/play")
    def play(sid):
        return jsonify(motor.tocar(sid, corpo().get("track_id")))

    @app.post("/api/session/<sid>/accept")
    def accept(sid):
        return jsonify(motor.aceitar(sid))

    @app.post("/api/session/<sid>/undo-accept")
    def undo_accept(sid):
        return jsonify(motor.desfazer_aceite(sid))

    @app.post("/api/session/<sid>/skip")
    def skip(sid):
        b = corpo()
        return jsonify(motor.pular(sid, b.get("target", "atual"), b.get("elapsed_fraction", 0.0)))

    @app.post("/api/session/<sid>/like")
    def like(sid):
        return jsonify(motor.curtir(sid))

    @app.post("/api/session/<sid>/adjust")
    def adjust(sid):
        return jsonify(motor.ajustar(sid, corpo().get("direction")))

    @app.post("/api/session/<sid>/bpm")
    def bpm(sid):
        b = corpo()
        return jsonify(motor.ajustar_bpm(sid, b.get("delta"), b.get("target"), bool(b.get("auto"))))

    @app.post("/api/session/<sid>/save")
    def save(sid):
        b = corpo()
        return jsonify(motor.salvar(sid, b.get("title"), b.get("tags")))

    @app.get("/api/playlists")
    def playlists():
        u = uid()
        lista = store.list_playlists(u) if u else []
        return jsonify({"playlists": [dict(p, faixas=len(p["track_ids"])) for p in lista]})

    @app.get("/api/playlists/<pid>")
    def playlist(pid):
        p = store.get_playlist(pid)
        if not p:
            raise Erro("Playlist não encontrada.", 404)
        p.pop("user_id", None)           # link público não expõe o dono
        p["faixas"] = [motor.por_id[i] for i in p["track_ids"]]
        return jsonify(p)

    @app.post("/api/playlists/<pid>/continue")
    def continuar(pid):
        return jsonify(motor.continuar_playlist(uid(), pid))

    # privacidade (LGPD) ------------------------------------------------------
    @app.get("/api/profile")
    def profile():
        u = uid()
        return jsonify(feedback.resumo(motor.perfil(u)) if u else {})

    @app.delete("/api/profile")
    def reset_profile():
        if uid():
            store.reset_profile(uid())
        return jsonify({"ok": True})

    @app.delete("/api/history")
    def delete_history():
        if uid():
            store.delete_history(uid())
        return jsonify({"ok": True})

    @app.get("/api/history")
    def export_history():
        return jsonify({"historico": store.history(uid()) if uid() else []})

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
