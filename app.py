"""API Flask + interface web do SoulsBPM (MVP)."""
import json
import os
import logging
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

# Se o Flask não estiver instalado no sistema, usa a cópia que acompanha o projeto (pasta libs/).
try:
    import flask  # noqa: F401
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "libs"))

from flask import Flask, g, jsonify, make_response, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from soulsbpm import embeddings as embeddings_mod
from soulsbpm import emails, feedback, musicfinder
from soulsbpm.aovivo import provedor_do_ambiente
from soulsbpm.aprendizado import Aprendizado
from soulsbpm.contas import COOKIE, SESSAO_DIAS, Contas
from soulsbpm.engine import Erro, Motor
from soulsbpm.limite import LimiteJanela
from soulsbpm.llm import do_ambiente as llm_do_ambiente
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


def _desligado(nome):
    """True se a variável de ambiente pede para desligar o recurso (0, false, não, off)."""
    return (os.environ.get(nome) or "").strip().lower() in ("0", "false", "nao", "não", "off")


def _inteiro(nome, padrao):
    try:
        return int(os.environ.get(nome) or padrao)
    except ValueError:
        return padrao


def create_app(db_path=None, catalog_path=None, provedor=None, buscas_por_minuto=None, emailer=None, email_sincrono=False):
    app = Flask(__name__, static_folder=str(RAIZ / "static"), static_url_path="/static")
    # nº de proxies de confiança na frente (HTTPS da hospedagem). No Render (que define RENDER) vale 1: sem isso o
    # app enxerga o IP do próprio Render em todo pedido, e o limite de tentativas de login passa a valer para todos juntos.
    proxies = max(0, _inteiro("SOULSBPM_PROXY", 1 if os.environ.get("RENDER") else 0))
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)
    dados = pathlib.Path(os.environ.get("SOULSBPM_DATA") or RAIZ / "data")     # pasta do banco e do cache (disco persistente)
    limite_busca = LimiteJanela(buscas_por_minuto or int(os.environ.get("SOULSBPM_BUSCAS_POR_MIN", 20)))
    arquivo = catalog_path or os.environ.get("SOULSBPM_CATALOG")
    musicfinder.configurar_ia(None)
    ia_ativa, embeddings = None, None
    if provedor is None and not arquivo:                 # com as duas chaves no ambiente, liga o modo ao vivo
        dados.mkdir(parents=True, exist_ok=True)
        provedor = provedor_do_ambiente(dados)
        ia = llm_do_ambiente()                                          # MusicFinder por IA (opcional)
        if provedor is not None and ia:
            musicfinder.configurar_ia(ia)
            ia_ativa = ia                                               # também sugere artistas e narra transições
            embeddings = embeddings_mod.do_ambiente()                   # similaridade semântica (opcional)
        if provedor is None:
            raise SemChaves(MSG_SEM_CHAVES)
    # modo ao vivo parte vazio (as faixas reais chegam a cada busca); com arquivo próprio usa só as faixas dele
    catalogo = [] if (provedor and not arquivo) else json.loads(pathlib.Path(arquivo).read_text("utf-8"))
    if not db_path:
        dados.mkdir(parents=True, exist_ok=True)
    store = Store(db_path or os.environ.get("DATABASE_URL") or os.environ.get("SOULSBPM_DB", str(dados / "soulsbpm.db")))
    aprendizado = None if _desligado("SOULSBPM_APRENDER") else Aprendizado(store)   # pesos aprendidos com o feedback
    artistas_ia = _inteiro("SOULSBPM_IA_ARTISTAS", 3)                               # 0 desliga a sugestão de artistas
    motor = Motor(catalogo, store, provedor=provedor, ia=ia_ativa, embeddings=embeddings, aprendizado=aprendizado,
                  max_artistas_ia=artistas_ia)
    contas = Contas(store)
    emailer = emailer or emails.do_ambiente(os.environ)                             # recuperação de senha (opcional)
    envios = ThreadPoolExecutor(max_workers=2)
    app.motor, app.store, app.contas, app.aprendizado = motor, store, contas, aprendizado
    limite_ia = LimiteJanela(_inteiro("SOULSBPM_IA_POR_MIN", 30))                   # explicações por IA, por IP
    exigir_login = os.environ.get("SOULSBPM_EXIGIR_LOGIN", "").lower() in ("1", "true", "sim")   # sem conta, nada funciona
    limite_auth = LimiteJanela(int(os.environ.get("SOULSBPM_LOGINS_POR_MIN", 10)))                # contra tentativa de senha

    def corpo():
        b = request.get_json(silent=True)
        return b if isinstance(b, dict) else {}            # lista, texto ou número no lugar do objeto JSON: trata como vazio

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
        if request.is_secure:
            r.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
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
        email = contas.email_da_conta(c["id"]) if c else None
        return jsonify({"logado": bool(c), "nome": c["nome"] if c else None, "exigir_login": exigir_login,
                        "recuperacao": emailer is not None, "email": contas.mascara_email(email), "tem_email": bool(email)})

    @app.post("/api/auth/register")
    def auth_register():
        checa_limite_auth()
        b = corpo()
        anterior = b.get("user_id") if isinstance(b.get("user_id"), str) and ID_VALIDO.match(b["user_id"]) else None
        return com_sessao(contas.criar(b.get("nome"), b.get("senha"), anterior, email=b.get("email"), email_obrigatorio=True), 201)

    @app.post("/api/auth/login")
    def auth_login():
        checa_limite_auth()
        b = corpo()
        return com_sessao(contas.entrar(b.get("nome") or b.get("login"), b.get("senha")))

    def base_url():
        """Endereço do site para montar o link do e-mail. Prefira SOULSBPM_URL: o Host da requisição pode ser forjado."""
        return (os.environ.get("SOULSBPM_URL") or request.url_root).rstrip("/")

    @app.post("/api/auth/forgot")
    def auth_forgot():
        checa_limite_auth()
        if emailer is None:
            raise Erro("A recuperação de senha não está configurada neste servidor.", 503)
        r = contas.pedir_recuperacao(corpo().get("email"))
        if r:                                                  # mesma resposta com ou sem conta: não revela quem se cadastrou
            link = f"{base_url()}/redefinir?token={r['token']}"
            assunto, html_corpo, texto = emails.recuperacao(r["nome"], link)

            def envia():
                try:
                    emailer.enviar(r["email"], r["nome"], assunto, html_corpo, texto)
                except Exception as e:
                    log.error("Falha ao enviar o e-mail de recuperação: %s", e)
            envia() if email_sincrono else envios.submit(envia)
        return jsonify({"ok": True, "mensagem": "Se esse e-mail tiver cadastro, enviamos um link para escolher uma nova senha. Confira também o spam."})

    @app.post("/api/auth/reset")
    def auth_reset():
        checa_limite_auth()
        b = corpo()
        contas.redefinir(b.get("token"), b.get("senha"))
        return jsonify({"ok": True})

    @app.post("/api/auth/email")
    def auth_email():
        c = conta_logada()
        if not c:
            raise Erro("Entre na sua conta primeiro.", 401)
        checa_limite_auth()
        b = corpo()
        email = contas.definir_email(c["id"], b.get("email"), b.get("senha"))
        return jsonify({"ok": True, "email": contas.mascara_email(email)})

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
    @app.get("/redefinir")
    def pagina_login():
        return send_from_directory(app.static_folder, "login.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "faixas": len(motor.catalogo), "ao_vivo": bool(provedor), "ia": musicfinder.ia_ativa(), "ia_provedor": musicfinder.ia_nome(),
                "embeddings": embeddings is not None, "sugere_artistas": ia_ativa is not None and artistas_ia > 0,
                "aprende": aprendizado is not None}

    @app.get("/api/modelo")
    def modelo():
        """O que a IA do app está fazendo agora: recursos ligados e os pesos da nota (manuais x aprendidos)."""
        return jsonify({"recursos": {"interpreta_vibe": musicfinder.ia_ativa(), "sugere_artistas": ia_ativa is not None and artistas_ia > 0,
                                     "narra_transicoes": motor.narrador.ativo, "embeddings": embeddings is not None,
                                     "aprende_pesos": aprendizado is not None},
                        "aprendizado": aprendizado.estado() if aprendizado else None})

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

    @app.post("/api/session/<sid>/explain")
    def explain(sid):
        if not limite_ia.permite(request.remote_addr):
            raise Erro("Muitos pedidos de explicação em pouco tempo. Espere um minuto e tente de novo.", 429)
        return jsonify(motor.explicar(sid, corpo().get("simples") is True))     # simples: modo comum, sem termos técnicos

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

    @app.post("/api/session/<sid>/destination")
    def destino(sid):
        c = conta_logada()
        if not c:
            return jsonify({"erro": "Entre na sua conta para salvar em playlists.", "precisa_conta": True}), 403
        return jsonify(motor.definir_destino(sid, c["id"], corpo().get("playlist_id")))

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
        p["faixas"] = [motor.por_id[i] for i in p["track_ids"] if i in motor.por_id]     # faixa que sumiu do catálogo não derruba a página
        return jsonify(p)

    def dono():
        """Id da conta logada. Criar, editar e excluir playlists só vale com login."""
        c = conta_logada()
        if not c:
            raise Erro("Entre na sua conta para gerenciar playlists.", 403)
        return c["id"]

    @app.post("/api/playlists")
    def criar_playlist():
        b = corpo()
        return jsonify(motor.criar_playlist(dono(), b.get("title"), b.get("tags"), b.get("track_ids"))), 201

    @app.patch("/api/playlists/<pid>")
    def editar_playlist(pid):
        b = corpo()
        return jsonify(motor.editar_playlist(dono(), pid, b.get("title"), b.get("tags"), b.get("track_ids")))

    @app.delete("/api/playlists/<pid>")
    def excluir_playlist(pid):
        return jsonify(motor.excluir_playlist(dono(), pid))

    @app.post("/api/playlists/<pid>/tracks")
    def adicionar_faixa(pid):
        return jsonify(motor.adicionar_faixa_playlist(dono(), pid, corpo().get("track_id")))

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
