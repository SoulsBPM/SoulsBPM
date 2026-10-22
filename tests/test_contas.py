"""Login: cadastro, entrada, sessão por cookie, bloqueio de tentativas e modo 'login obrigatório'."""
import os
import pathlib
import unittest
from app import create_app

CAT = str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json")


def novo(**env):
    antigo = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        return create_app(":memory:", catalog_path=CAT)
    finally:
        for k, v in antigo.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class ContasTests(unittest.TestCase):
    def setUp(self):
        self.app = novo()
        self.c = self.app.test_client()

    def cadastrar(self, nome="maria", senha="senha-forte-1", **extra):
        return self.c.post("/api/auth/register", json={"nome": nome, "email": f"{nome}@exemplo.com", "senha": senha, **extra})

    def test_cadastro_loga_e_me_mostra_o_nome(self):
        r = self.cadastrar()
        self.assertEqual(r.status_code, 201)
        self.assertIn("HttpOnly", r.headers["Set-Cookie"])
        self.assertEqual(self.c.get("/api/auth/me").get_json()["nome"], "maria")

    def test_sem_login_me_diz_nao_logado(self):
        self.assertFalse(self.c.get("/api/auth/me").get_json()["logado"])

    def test_nome_repetido_ignora_maiusculas(self):
        self.cadastrar("Maria")
        self.assertEqual(self.app.test_client().post("/api/auth/register",
                         json={"nome": "MARIA", "email": "MARIA@exemplo.com", "senha": "outra-senha-1"}).status_code, 409)

    def test_senha_curta_e_nome_invalido_dao_400(self):
        self.assertEqual(self.cadastrar(senha="curta").status_code, 400)
        self.assertEqual(self.cadastrar(nome="a b").status_code, 400)
        self.assertEqual(self.cadastrar(nome=None).status_code, 400)

    def test_login_certo_e_errado(self):
        self.cadastrar()
        outro = self.app.test_client()
        self.assertEqual(outro.post("/api/auth/login", json={"nome": "maria", "email": "maria@exemplo.com", "senha": "errada-errada"}).status_code, 401)
        self.assertEqual(outro.post("/api/auth/login", json={"nome": "naoexiste", "email": "naoexiste@exemplo.com", "senha": "senha-forte-1"}).status_code, 401)
        self.assertEqual(outro.post("/api/auth/login", json={"nome": "MARIA", "email": "MARIA@exemplo.com", "senha": "senha-forte-1"}).status_code, 200)
        self.assertTrue(outro.get("/api/auth/me").get_json()["logado"])

    def test_senha_nao_e_guardada_em_texto(self):
        self.cadastrar()
        h = self.app.store._run("SELECT hash FROM users", fetch=True)[0][0]
        self.assertTrue(h.startswith("scrypt$"))
        self.assertNotIn("senha-forte-1", h)

    def test_logout_encerra_a_sessao(self):
        self.cadastrar()
        self.c.post("/api/auth/logout")
        self.assertFalse(self.c.get("/api/auth/me").get_json()["logado"])

    def test_sessao_expirada_nao_vale(self):
        self.cadastrar()
        self.app.store._run("UPDATE auth SET expires=1")
        self.assertFalse(self.c.get("/api/auth/me").get_json()["logado"])

    def test_dados_ficam_na_conta_e_seguem_em_outro_aparelho(self):
        self.cadastrar()
        sid = self.c.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()["session_id"]
        self.assertTrue(sid)
        self.assertEqual(self.c.get("/api/recent").get_json()["buscas"], ["música calma para estudar à noite"])
        outro = self.app.test_client()
        self.assertEqual(outro.get("/api/recent").get_json()["buscas"], [])
        outro.post("/api/auth/login", json={"nome": "maria", "email": "maria@exemplo.com", "senha": "senha-forte-1"})
        self.assertEqual(outro.get("/api/recent").get_json()["buscas"], ["música calma para estudar à noite"])

    def test_cadastro_leva_o_historico_anonimo(self):
        self.c.post("/api/search", json={"user_id": "u_anon", "text": "música calma para estudar à noite"})
        self.cadastrar(user_id="u_anon")
        self.assertEqual(self.c.get("/api/recent").get_json()["buscas"], ["música calma para estudar à noite"])

    def test_codigo_de_conta_nao_vale_sem_login(self):
        self.cadastrar()
        uid = self.app.store._run("SELECT id FROM users", fetch=True)[0][0]
        self.c.post("/api/search", json={"text": "música calma para estudar à noite"})
        intruso = self.app.test_client()
        self.assertEqual(intruso.get(f"/api/recent?user_id={uid}").get_json()["buscas"], [])
        self.assertEqual(intruso.get(f"/api/history?user_id={uid}").get_json()["historico"], [])

    def test_com_login_o_user_id_do_navegador_e_ignorado(self):
        self.cadastrar()
        self.c.post("/api/search", json={"user_id": "u_outra_pessoa", "text": "música calma para estudar à noite"})
        self.assertEqual(self.c.get("/api/recent?user_id=u_outra_pessoa").get_json()["buscas"],
                         ["música calma para estudar à noite"])
        self.assertEqual(self.app.test_client().get("/api/recent?user_id=u_outra_pessoa").get_json()["buscas"], [])

    def test_tentativas_demais_levam_429(self):
        for _ in range(10):
            self.c.post("/api/auth/login", json={"nome": "x", "email": "x@exemplo.com", "senha": "yyyyyyyy"})
        self.assertEqual(self.c.post("/api/auth/login", json={"nome": "x", "email": "x@exemplo.com", "senha": "yyyyyyyy"}).status_code, 429)


class PlaylistsSoComContaTests(unittest.TestCase):
    def setUp(self):
        self.app = novo()
        self.c = self.app.test_client()

    def montar(self, cli):
        r = cli.post("/api/search", json={"user_id": "u_visitante", "text": "música calma para estudar à noite"}).get_json()
        sid = r["session_id"]
        cli.post(f"/api/session/{sid}/play", json={"user_id": "u_visitante", "track_id": r["resultados"][0]["id"]})
        cli.post(f"/api/session/{sid}/accept", json={"user_id": "u_visitante"})
        return sid

    def test_visitante_nao_salva_playlist(self):
        sid = self.montar(self.c)
        r = self.c.post(f"/api/session/{sid}/save", json={"user_id": "u_visitante", "title": "x"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.get_json()["precisa_conta"])
        self.assertEqual(self.app.store.list_playlists("u_visitante"), [])

    def test_visitante_ve_lista_vazia(self):
        self.app.store.save_playlist("u_visitante", "antiga", [], ["a", "b"])        # de antes de existir login
        self.assertEqual(self.c.get("/api/playlists?user_id=u_visitante").get_json()["playlists"], [])

    def test_com_conta_salva_e_lista(self):
        self.c.post("/api/auth/register", json={"nome": "maria", "email": "maria@exemplo.com", "senha": "senha-forte-1"})
        sid = self.montar(self.c)
        self.assertEqual(self.c.post(f"/api/session/{sid}/save", json={"title": "Minha"}).status_code, 200)
        self.assertEqual([p["title"] for p in self.c.get("/api/playlists").get_json()["playlists"]], ["Minha"])
        self.assertEqual(self.app.test_client().get("/api/playlists").get_json()["playlists"], [])

    def test_playlist_antiga_do_visitante_vai_para_a_conta_ao_criar(self):
        self.app.store.save_playlist("u_visitante", "antiga", [], ["a", "b"])
        self.c.post("/api/auth/register", json={"nome": "maria", "email": "maria@exemplo.com", "senha": "senha-forte-1", "user_id": "u_visitante"})
        self.assertEqual([p["title"] for p in self.c.get("/api/playlists").get_json()["playlists"]], ["antiga"])

    def test_sessao_de_outra_pessoa_nao_salva(self):
        sid = self.montar(self.c)                                    # sessão criada por um visitante
        outro = self.app.test_client()
        outro.post("/api/auth/register", json={"nome": "joao", "email": "joao@exemplo.com", "senha": "senha-forte-1"})
        self.assertEqual(outro.post(f"/api/session/{sid}/save", json={"title": "x"}).status_code, 404)


class LoginObrigatorioTests(unittest.TestCase):
    def setUp(self):
        self.app = novo(SOULSBPM_EXIGIR_LOGIN="1")
        self.c = self.app.test_client()

    def test_sem_conta_a_api_responde_401(self):
        for r in (self.c.post("/api/search", json={"text": "festa"}), self.c.get("/api/playlists"), self.c.get("/api/history")):
            self.assertEqual(r.status_code, 401)
            self.assertTrue(r.get_json()["login"])

    def test_health_e_login_ficam_abertos(self):
        self.assertEqual(self.c.get("/api/health").status_code, 200)
        me = self.c.get("/api/auth/me").get_json()
        self.assertTrue(me["exigir_login"])

    def test_com_conta_funciona_e_user_id_anonimo_nao_vale(self):
        self.c.post("/api/auth/register", json={"nome": "joao", "email": "joao@exemplo.com", "senha": "senha-forte-1"})
        self.assertEqual(self.c.post("/api/search", json={"text": "música calma para estudar à noite"}).status_code, 200)

    def test_link_publico_de_playlist_continua_aberto(self):
        self.c.post("/api/auth/register", json={"nome": "joao", "email": "joao@exemplo.com", "senha": "senha-forte-1"})
        sid = self.c.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()
        pid = self.app.store.save_playlist("x", "t", [], [f["id"] for f in sid["resultados"][:2]])
        self.assertEqual(self.app.test_client().get(f"/api/playlists/{pid}").status_code, 200)


if __name__ == "__main__":
    unittest.main()


class PaginaLoginTests(unittest.TestCase):
    def test_login_e_pagina_propria_e_aberta_mesmo_com_login_obrigatorio(self):
        for env in ({}, {"SOULSBPM_EXIGIR_LOGIN": "1"}):
            r = novo(**env).test_client().get("/login")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b'id="f-login"', r.data)
            self.assertIn(b"viewport-fit=cover", r.data)
            r.close()

    def test_pagina_principal_nao_traz_mais_o_formulario(self):
        r = novo().test_client().get("/")
        self.assertNotIn(b'id="f-login"', r.data)
        r.close()
