"""API Flask + interface web do SoulsBPM (MVP)."""
import json
import os
import logging
import pathlib
import re
import sys

# Se o Flask não estiver instalado no sistema, usa a cópia que acompanha o projeto (pasta libs/).
try:
    import flask  # noqa: F401
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "libs"))

from flask import Flask, g, jsonify, make_response, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from soulsbpm import feedback
from soulsbpm.aovivo import provedor_do_ambiente
from soulsbpm.contas import COOKIE, SESSAO_DIAS, Contas
from soulsbpm.engine import Erro, Motor
from soulsbpm.limite import LimiteJanela
from soulsbpm.store import Store

RAIZ = pathlib.Path(__file__).resolve().parent
ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")      # código de usuário: só letras, números, _ e -
log = logging.getLogger("soulsbpm")

MSG_SEM_CHAVES = """O SoulsBPM usa músicas reais e precisa de duas chaves gratuitas:
  1. Last.fm:     https://www.last.fm/api/account/create   (LASTFM_API_KEY)
  2. GetSongBPM:  https://getsongbpm.com/api               (GETSONGBPM_API_KEY)
Copie o arquivo .env.exemplo para .env, cole as chaves nele e rode de novo: python app.py"""


class SemChaves(RuntimeError):
    """Faltam as chaves LASTFM_API_KEY e/ou GETSONGBPM_API_KEY."""


def carregar_env(arquivo=None):
    """Lê o arquivo .env (CHAVE=valor, uma por linha) para o ambiente, sem sobrescrever o que já está definido."""
    arquivo = pathlib.Path(arquivo or RAIZ / ".env")
    if not arquivo.is_file():
        return
    for linha in arquivo.read_text("utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def create_app(db_path=None, catalog_path=None, provedor=None, buscas_por_minuto=None):
    app = Flask(__name__, static_folder=str(RAIZ / "static"), static_url_path="/static")
    proxies = int(os.environ.get("SOULSBPM_PROXY", 0) or 0)       # nº de proxies de confiança na frente (HTTPS da hospedagem)
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)
    dados = pathlib.Path(os.environ.get("SOULSBPM_DATA") or RAIZ / "data")     # pasta do banco e do cache (disco persistente)
    limite_busca = LimiteJanela(buscas_por_minuto or int(os.environ.get("SOULSBPM_BUSCAS_POR_MIN", 20)))
    arquivo = catalog_path or os.environ.get("SOULSBPM_CATALOG")
    if provedor is None and not arquivo:                 # com as duas chaves no ambiente, liga o modo ao vivo
        dados.mkdir(parents=True, exist_ok=True)
        provedor = provedor_do_ambiente(dados)
        if provedor is None:
            raise SemChaves(MSG_SEM_CHAVES)
    # modo ao vivo parte vazio (as faixas reais chegam a cada busca); com arquivo próprio usa só as faixas dele
    catalogo = [] if (provedor and not arquivo) else json.loads(pathlib.Path(arquivo).read_text("utf-8"))
    if not db_path:
        dados.mkdir(parents=True, exist_ok=True)
    store = Store(db_path or os.environ.get("DATABASE_URL") or os.environ.get("SOULSBPM_DB", str(dados / "soulsbpm.db")))
    motor = Motor(catalogo, store, provedor=provedor)
    contas = Contas(store)
    app.motor, app.store, app.contas = motor, store, contas
    exigir_login = os.environ.get("SOULSBPM_EXIGIR_LOGIN", "").lower() in ("1", "true", "sim")   # sem conta, nada funciona
    limite_auth = LimiteJanela(int(os.environ.get("SOULSBPM_LOGINS_POR_MIN", 10)))                # contra tentativa de senha

    def corpo():
        return request.get_json(silent=True) or {}

    @app.errorhandler(Erro)
    def erro(e):
        return jsonify({"erro": str(e)}), e.status

    @app.errorhandler(Exception)
    def falha(e):
        if isinstance(e, HTTPException):                  # 404, 405…: JSON na API, página padrão no resto
            return (jsonify({"erro": e.name}), e.code) if request.path.startswith("/api/") else e
        log.exception("Erro inesperado em %s %s", request.method, request.path)
        return jsonify({"erro": "Erro interno. Tente de novo em instantes."}), 500

    @app.after_request
    def cabecalhos(r):
        r.headers.setdefault("X-Content-Type-Options", "nosniff")
        r.headers.setdefault("X-Frame-Options", "DENY")
        r.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/api/"):
            r.headers["Cache-Control"] = "no-store"        # respostas pessoais não ficam em cache
            r.headers["X-Souls-Logado"] = "1" if conta_logada() else "0"
        return r

    def conta_logada():
        if not hasattr(g, "conta"):
            g.conta = contas.por_token(request.cookies.get(COOKIE))
        return g.conta

    @app.before_request
    def exige_conta():
        p = request.path
        if not exigir_login or not p.startswith("/api/") or p.startswith("/api/auth/") or p == "/api/health":
            return None
        if request.method == "GET" and re.match(r"^/api/playlists/[^/]+$", p):      # link público de playlist continua aberto
            return None
        if not conta_logada():
            return jsonify({"erro": "Entre na sua conta para continuar.", "login": True}), 401
        return None

    def uid():
        c = conta_logada()
        if c:                                              # com login, o dono vem do cookie, nunca do que o navegador diz
            return c["id"]
        u = corpo().get("user_id") or request.args.get("user_id")
        if exigir_login or not (isinstance(u, str) and ID_VALIDO.match(u)) or contas.eh_conta(u):
            return None                                    # código de uma conta não vale sem login
        return u

    def com_sessao(conta, status=200):
        r = make_response(jsonify({"logado": True, "nome": conta["nome"]}), status)
        r.set_cookie(COOKIE, contas.abrir_sessao(conta["id"]), max_age=SESSAO_DIAS * 86400, httponly=True,
                     samesite="Lax", secure=request.is_secure)
        return r

    def checa_limite_auth():
        if not limite_auth.permite(request.remote_addr):
            raise Erro("Muitas tentativas. Espere um minuto e tente de novo.", 429)

    @app.get("/api/auth/me")
    def auth_me():
        c = conta_logada()
        return jsonify({"logado": bool(c), "nome": c["nome"] if c else None, "exigir_login": exigir_login})

    @app.post("/api/auth/register")
    def auth_register():
        checa_limite_auth()
        b = corpo()
        anterior = b.get("user_id") if isinstance(b.get("user_id"), str) and ID_VALIDO.match(b["user_id"]) else None
        return com_sessao(contas.criar(b.get("nome"), b.get("senha"), anterior), 201)    # leva o histórico anônimo para a conta

    @app.post("/api/auth/login")
    def auth_login():
        checa_limite_auth()
        b = corpo()
        return com_sessao(contas.entrar(b.get("nome"), b.get("senha")))

    @app.post("/api/auth/logout")
    def auth_logout():
        contas.fechar_sessao(request.cookies.get(COOKIE))
        g.conta = None
        r = make_response(jsonify({"ok": True}))
        r.delete_cookie(COOKIE, samesite="Lax")
        return r

    @app.get("/")
    @app.get("/p/<pid>")
    def index(pid=None):
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/login")
    def pagina_login():
        return send_from_directory(app.static_folder, "login.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "faixas": len(motor.catalogo), "ao_vivo": bool(provedor)}

    @app.post("/api/search")
    def search():
        if not limite_busca.permite(request.remote_addr):
            raise Erro("Muitas buscas em pouco tempo. Espere um minuto e tente de novo.", 429)
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

    @app.post("/api/session/<sid>/back")
    def back(sid):
        return jsonify(motor.voltar(sid))

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
        c = conta_logada()
        if not c:                                          # playlists só existem dentro de uma conta
            return jsonify({"erro": "Entre ou crie uma conta para salvar playlists.", "precisa_conta": True}), 403
        if motor.sessao(sid).user_id != c["id"]:
            raise Erro("Sessão não encontrada.", 404)
        b = corpo()
        return jsonify(motor.salvar(sid, b.get("title"), b.get("tags")))

    @app.get("/api/playlists")
    def playlists():
        u = uid()
        lista = store.list_playlists(u) if (u and conta_logada()) else []
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
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    carregar_env()
    try:
        aplicacao = create_app()
    except SemChaves as e:
        sys.exit(str(e))
    porta = int(os.environ.get("PORT", 5000))
    # na hospedagem (que define PORT) escuta em todas as interfaces; no seu PC, só em 127.0.0.1. Dá para forçar com HOST.
    host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    try:
        from waitress import serve                       # servidor de produção (pip install waitress)
    except ImportError:
        logging.warning("waitress não instalado: usando o servidor de desenvolvimento do Flask.")
        aplicacao.run(host=host, port=porta, debug=False, threaded=True)
    else:
        logging.info("SoulsBPM em http://%s:%s", host, porta)
        serve(aplicacao, host=host, port=porta, threads=8)
