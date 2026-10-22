"""Entradas estranhas na API (nunca 500), limite por IP atrás do proxy, nomes acentuados e erro do Brevo."""
import io
import os
import pathlib
import unittest
import urllib.error
from unittest import mock

from app import create_app
from soulsbpm import emails
from soulsbpm.engine import MAX_PLAYLISTS, MAX_TITULO_PLAYLIST

CATALOGO = str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json")


class Base(unittest.TestCase):
    def setUp(self):
        self.app = create_app(":memory:", catalog_path=CATALOGO, emailer=mock.Mock(), email_sincrono=True)
        self.c = self.app.test_client()

    def conta(self, nome="Teste Um", cliente=None):
        c = cliente or self.c
        r = c.post("/api/auth/register", json={"nome": nome, "email": f"{nome.split()[0].lower()}@ex.com", "senha": "senha1234"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))

    def busca(self):
        r = self.c.post("/api/search", json={"text": "festa animada para dançar"}).get_json()
        return r["session_id"], [f["id"] for f in r["resultados"]]


class TestCorpoEstranho(Base):
    URLS = ["/api/search", "/api/auth/login", "/api/auth/register", "/api/auth/forgot", "/api/auth/reset", "/api/auth/email",
            "/api/playlists"]

    def test_json_que_nao_e_objeto_vira_erro_de_cliente(self):
        self.conta()
        sid, ids = self.busca()
        urls = self.URLS + [f"/api/session/{sid}/{x}" for x in ("play", "skip", "bpm", "adjust", "save", "destination")]
        for corpo in ('[1]', '"texto"', '5', 'null', 'true', '{'):
            for u in urls:
                r = self.c.post(u, data=corpo, content_type="application/json")
                self.assertLess(r.status_code, 500, (u, corpo, r.get_data(as_text=True)))
            r = self.c.patch("/api/playlists/qualquer", data=corpo, content_type="application/json")
            self.assertLess(r.status_code, 500, corpo)

    def test_id_de_faixa_que_nao_e_texto_responde_404(self):
        self.conta()
        sid, ids = self.busca()
        self.c.post("/api/playlists", json={"title": "pl", "track_ids": ids[:2]})
        pid = self.c.get("/api/playlists").get_json()["playlists"][0]["id"]
        for ruim in ([], {}, 5, [1], True):
            self.assertEqual(self.c.post(f"/api/session/{sid}/play", json={"track_id": ruim}).status_code, 404, ruim)
            self.assertEqual(self.c.post(f"/api/playlists/{pid}/tracks", json={"track_id": ruim}).status_code, 404, ruim)


class TestSalvarSequencia(Base):
    def sequencia(self):
        sid, ids = self.busca()
        self.c.post(f"/api/session/{sid}/play", json={"track_id": ids[0]})
        self.assertEqual(self.c.post(f"/api/session/{sid}/accept").status_code, 200)
        return sid

    def test_titulo_e_tags_sao_validados(self):
        self.conta()
        sid = self.sequencia()
        for corpo in ({"title": 5}, {"title": ["a"]}, {"title": "x" * 200}, {"tags": "calma"}, {"tags": {"a": 1}}):
            self.assertEqual(self.c.post(f"/api/session/{sid}/save", json=corpo).status_code, 400, corpo)
        r = self.c.post(f"/api/session/{sid}/save", json={"title": "  Meu   set ", "tags": ["  Festa ", "festa", 7, ""]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["titulo"], r.get_json()["tags"]), ("Meu set", ["festa"]))

    def test_titulo_padrao_nunca_passa_do_limite(self):
        self.conta()
        sid, ids = self.busca()
        self.c.post(f"/api/session/{sid}/play", json={"track_id": ids[0]})
        self.app.motor.sessao(sid).consulta = "festa " * 33          # 198 caracteres
        self.c.post(f"/api/session/{sid}/accept")
        r = self.c.post(f"/api/session/{sid}/save", json={})
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(len(r.get_json()["titulo"]), MAX_TITULO_PLAYLIST)

    def test_salvar_respeita_o_limite_de_playlists(self):
        self.conta()
        sid = self.sequencia()
        with mock.patch.object(self.app.store, "count_playlists", return_value=MAX_PLAYLISTS):
            self.assertEqual(self.c.post(f"/api/session/{sid}/save", json={}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/session/{sid}/save", json={}).status_code, 200)


class TestFaixaQueSumiu(Base):
    def test_playlist_com_faixa_fora_do_catalogo_ainda_abre(self):
        self.conta()
        sid, ids = self.busca()
        r = self.c.post("/api/playlists", json={"title": "pl", "track_ids": ids[:3]}).get_json()
        self.app.store.update_playlist(r["id"], track_ids=[ids[0], "fantasma", ids[1]])
        p = self.c.get(f"/api/playlists/{r['id']}")
        self.assertEqual(p.status_code, 200)
        self.assertEqual([f["id"] for f in p.get_json()["faixas"]], [ids[0], ids[1]])
        d = self.c.post(f"/api/playlists/{r['id']}/continue")
        self.assertEqual(d.status_code, 200)
        self.assertEqual([f["id"] for f in d.get_json()["sequencia"]], [ids[0], ids[1]])

    def test_playlist_so_com_faixas_perdidas_nao_continua(self):
        self.conta()
        r = self.c.post("/api/playlists", json={"title": "pl"}).get_json()
        self.app.store.update_playlist(r["id"], track_ids=["fantasma"])
        self.assertEqual(self.c.post(f"/api/playlists/{r['id']}/continue").status_code, 400)


class TestProxyDoRender(unittest.TestCase):
    def app_com_env(self, **env):
        base = {k: v for k, v in os.environ.items() if k not in ("RENDER", "SOULSBPM_PROXY")}
        with mock.patch.dict(os.environ, {**base, **env}, clear=True):
            return create_app(":memory:", catalog_path=CATALOGO, emailer=mock.Mock())

    def tentativas(self, app, ip):
        c = app.test_client()
        return [c.post("/api/auth/login", json={"nome": "x", "senha": "y"}, headers={"X-Forwarded-For": ip},
                       environ_overrides={"REMOTE_ADDR": "10.0.0.1"}).status_code for _ in range(12)]

    def test_no_render_o_limite_vale_por_visitante_e_nao_para_todos(self):
        app = self.app_com_env(RENDER="true")
        self.assertIn(429, self.tentativas(app, "200.1.1.1"))
        self.assertNotIn(429, self.tentativas(app, "200.2.2.2")[:3])          # outro visitante não é barrado

    def test_fora_do_render_nao_confia_no_cabecalho(self):
        app = self.app_com_env()
        self.assertIn(429, self.tentativas(app, "200.1.1.1"))
        self.assertIn(429, self.tentativas(app, "200.2.2.2")[:11])            # cabeçalho forjado não escapa do limite

    def test_proxy_pode_ser_forcado_ou_desligado(self):
        app = self.app_com_env(RENDER="true", SOULSBPM_PROXY="0")
        self.assertIn(429, self.tentativas(app, "200.2.2.2")[:11])

    def test_hsts_so_em_https(self):
        app = self.app_com_env()
        c = app.test_client()
        self.assertNotIn("Strict-Transport-Security", c.get("/api/health").headers)
        self.assertIn("Strict-Transport-Security", c.get("/api/health", base_url="https://exemplo.com").headers)


class TestNomesAcentuados(Base):
    def test_login_ignora_maiusculas_em_nome_com_acento(self):
        self.conta("João Silva")
        c2 = self.app.test_client()
        for tentativa in ("JOÃO SILVA", "joão silva", "João Silva"):
            r = c2.post("/api/auth/login", json={"nome": tentativa, "senha": "senha1234"})
            self.assertEqual(r.status_code, 200, tentativa)

    def test_nome_repetido_so_com_maiusculas_diferentes_e_recusado(self):
        self.conta("João Silva")
        r = self.app.test_client().post("/api/auth/register",
                                        json={"nome": "JOÃO SILVA", "email": "outro@ex.com", "senha": "senha1234"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("nome", r.get_json()["erro"])

    def test_nome_que_contem_a_palavra_email_nao_vira_erro_de_email(self):
        self.conta("Fulano")
        r = self.app.test_client().post("/api/auth/register",
                                        json={"nome": "fulano", "email": "novo@ex.com", "senha": "senha1234"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("nome", r.get_json()["erro"])


class TestErroDoBrevo(unittest.TestCase):
    def test_mensagem_do_brevo_aparece_no_erro(self):
        corpo = io.BytesIO(b'{"code":"invalid_parameter","message":"Sender is not valid"}')
        http_erro = urllib.error.HTTPError("https://api.brevo.com", 400, "Bad", {}, corpo)
        with mock.patch("urllib.request.urlopen", side_effect=http_erro):
            with self.assertRaises(emails.EmailErro) as ctx:
                emails.Brevo("chave-secreta", "eu@ex.com").enviar("a@ex.com", "A", "Oi", "<p>oi</p>", "oi")
        self.assertIn("HTTP 400", str(ctx.exception))
        self.assertIn("Sender is not valid", str(ctx.exception))
        self.assertNotIn("chave-secreta", str(ctx.exception))

    def test_erro_sem_corpo_legivel_ainda_informa_o_codigo(self):
        http_erro = urllib.error.HTTPError("https://api.brevo.com", 401, "Unauthorized", {}, io.BytesIO(b"<html>"))
        with mock.patch("urllib.request.urlopen", side_effect=http_erro):
            with self.assertRaises(emails.EmailErro) as ctx:
                emails.Brevo("k", "eu@ex.com").enviar("a@ex.com", "A", "Oi", "<p>oi</p>", "oi")
        self.assertIn("HTTP 401", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
