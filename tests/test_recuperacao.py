"""Cadastro com e-mail, login por e-mail, recuperação de senha e envio pelo Brevo (sem rede)."""
import os
import pathlib
import re
import sqlite3
import tempfile
import unittest
from unittest import mock

from app import create_app
from soulsbpm import emails
from soulsbpm.store import Store

CATALOGO = str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json")


class Caixa:
    """Emailer falso: guarda o que seria enviado."""

    def __init__(self):
        self.enviados = []

    def enviar(self, para, nome_para, assunto, html_corpo, texto):
        self.enviados.append({"para": para, "nome": nome_para, "assunto": assunto, "html": html_corpo, "texto": texto})

    def token(self, i=-1):
        return re.search(r"token=([\w-]+)", self.enviados[i]["texto"]).group(1)


class Base(unittest.TestCase):
    def setUp(self):
        self.caixa = Caixa()
        self.app = create_app(":memory:", catalog_path=CATALOGO, emailer=self.caixa, email_sincrono=True)
        self.c = self.app.test_client()

    def cadastrar(self, nome="maria", email="maria@exemplo.com", senha="senha-forte-1", cliente=None):
        return (cliente or self.c).post("/api/auth/register", json={"nome": nome, "email": email, "senha": senha})

    def pedir(self, email="maria@exemplo.com"):
        return self.c.post("/api/auth/forgot", json={"email": email})

    def redefinir(self, token, senha="nova-senha-9"):
        return self.c.post("/api/auth/reset", json={"token": token, "senha": senha})


class TestCadastroELogin(Base):
    def test_cadastro_exige_email_valido(self):
        for ruim in (None, "", "sem-arroba", "a@b", "a b@c.com", "x" * 300 + "@c.com"):
            self.assertEqual(self.cadastrar(email=ruim).status_code, 400, ruim)
        self.assertEqual(self.cadastrar().status_code, 201)

    def test_email_e_unico_sem_diferenciar_maiusculas(self):
        self.cadastrar()
        r = self.cadastrar(nome="outra", email="MARIA@Exemplo.com", cliente=self.app.test_client())
        self.assertEqual(r.status_code, 409)
        self.assertIn("e-mail", r.get_json()["erro"])

    def test_nome_com_espaco_e_acento_e_aceito_e_repetido_nao(self):
        self.assertEqual(self.cadastrar(nome="Raimundo de Souza", email="r@exemplo.com").status_code, 201)
        r = self.cadastrar(nome="raimundo DE souza", email="r2@exemplo.com", cliente=self.app.test_client())
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.cadastrar(nome="  ", email="z@exemplo.com").status_code, 400)
        self.assertEqual(self.cadastrar(nome="ab", email="z@exemplo.com").status_code, 400)

    def test_entrar_com_nome_ou_com_email(self):
        self.cadastrar()
        for login in ("maria", "MARIA", "maria@exemplo.com", "  Maria@Exemplo.com "):
            cli = self.app.test_client()
            r = cli.post("/api/auth/login", json={"nome": login, "senha": "senha-forte-1"})
            self.assertEqual(r.status_code, 200, login)
        errado = self.app.test_client().post("/api/auth/login", json={"nome": "maria@exemplo.com", "senha": "errada-123"})
        self.assertEqual(errado.status_code, 401)

    def test_me_mostra_email_mascarado_e_se_a_recuperacao_existe(self):
        self.cadastrar()
        me = self.c.get("/api/auth/me").get_json()
        self.assertEqual((me["email"], me["tem_email"], me["recuperacao"]), ("m***@exemplo.com", True, True))
        self.assertNotIn("maria@exemplo.com", str(me))


class TestRecuperacao(Base):
    def setUp(self):
        super().setUp()
        self.cadastrar()

    def test_manda_o_link_por_email_e_nao_devolve_o_token(self):
        r = self.pedir()
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("token", str(r.get_json()))
        self.assertEqual(len(self.caixa.enviados), 1)
        m = self.caixa.enviados[0]
        self.assertEqual((m["para"], m["nome"]), ("maria@exemplo.com", "maria"))
        self.assertRegex(m["texto"], r"/redefinir\?token=[\w-]{30,}")

    def test_link_usa_a_url_configurada_e_nao_o_host_da_requisicao(self):
        with mock.patch.dict(os.environ, {"SOULSBPM_URL": "https://meu-app.onrender.com/"}):
            self.c.post("/api/auth/forgot", json={"email": "maria@exemplo.com"}, headers={"Host": "atacante.example"})
        self.assertIn("https://meu-app.onrender.com/redefinir?token=", self.caixa.enviados[0]["texto"])
        self.assertNotIn("atacante", self.caixa.enviados[0]["texto"])

    def test_email_sem_conta_responde_igual_e_nao_envia(self):
        a, b = self.pedir(), self.pedir("ninguem@exemplo.com")
        self.assertEqual((a.status_code, a.get_json()), (b.status_code, b.get_json()))
        self.assertEqual(len(self.caixa.enviados), 1)
        self.assertEqual(self.pedir("isso-nao-e-email").status_code, 400)

    def test_limite_de_pedidos_por_hora(self):
        for _ in range(5):
            self.assertEqual(self.pedir().status_code, 200)
        self.assertEqual(len(self.caixa.enviados), 3)

    def test_redefinir_troca_a_senha_e_o_link_so_vale_uma_vez(self):
        self.pedir()
        tk = self.caixa.token()
        self.assertEqual(self.redefinir(tk).status_code, 200)
        entra = lambda s: self.app.test_client().post("/api/auth/login", json={"nome": "maria", "senha": s}).status_code
        self.assertEqual((entra("nova-senha-9"), entra("senha-forte-1")), (200, 401))
        self.assertEqual(self.redefinir(tk, "outra-senha-8").status_code, 400)

    def test_redefinir_encerra_as_sessoes_abertas(self):
        self.assertTrue(self.c.get("/api/auth/me").get_json()["logado"])           # logada pelo cadastro
        self.pedir()
        self.redefinir(self.caixa.token())
        self.assertFalse(self.c.get("/api/auth/me").get_json()["logado"])

    def test_pedido_novo_invalida_o_anterior(self):
        self.pedir()
        self.pedir()
        velho, novo = self.caixa.token(0), self.caixa.token(1)
        self.assertEqual(self.redefinir(velho).status_code, 400)
        self.assertEqual(self.redefinir(novo).status_code, 200)

    def test_link_expira_depois_de_uma_hora(self):
        self.pedir()
        agora = self.app.contas.agora()
        self.app.contas.agora = lambda: agora + 3601
        self.assertEqual(self.redefinir(self.caixa.token()).status_code, 400)

    def test_senha_curta_e_recusada_e_o_link_continua_valido(self):
        self.pedir()
        tk = self.caixa.token()
        self.assertEqual(self.redefinir(tk, "curta").status_code, 400)
        self.assertEqual(self.redefinir(tk).status_code, 200)

    def test_token_invalido_ou_ausente(self):
        for tk in (None, "", "abc", "x" * 500, 123):
            self.assertEqual(self.redefinir(tk).status_code, 400)

    def test_token_nao_fica_guardado_em_texto_puro(self):
        self.pedir()
        tk = self.caixa.token()
        linhas = self.app.store._run("SELECT token FROM reset", fetch=True)
        self.assertTrue(linhas and all(tk not in l[0] for l in linhas))

    def test_sem_servico_de_email_a_recuperacao_fica_desligada(self):
        with mock.patch.dict(os.environ, {"EMAIL_MODO": "", "BREVO_API_KEY": "", "EMAIL_REMETENTE": ""}):
            app = create_app(":memory:", catalog_path=CATALOGO)
        c = app.test_client()
        self.assertEqual(c.post("/api/auth/forgot", json={"email": "maria@exemplo.com"}).status_code, 503)
        self.assertFalse(c.get("/api/auth/me").get_json()["recuperacao"])

    def test_paginas_de_login_e_redefinir_abrem(self):
        for caminho in ("/login", "/redefinir"):
            self.assertEqual(self.c.get(caminho).status_code, 200)


class TestContaAntigaSemEmail(Base):
    def entrar_sem_email(self):
        self.app.contas.criar("antiga", "senha-forte-1")                    # como era antes: sem e-mail
        r = self.c.post("/api/auth/login", json={"nome": "antiga", "senha": "senha-forte-1"})
        self.assertEqual(r.status_code, 200)

    def test_adicionar_email_exige_a_senha(self):
        self.entrar_sem_email()
        self.assertFalse(self.c.get("/api/auth/me").get_json()["tem_email"])
        self.assertEqual(self.c.post("/api/auth/email", json={"email": "a@exemplo.com", "senha": "errada-123"}).status_code, 401)
        r = self.c.post("/api/auth/email", json={"email": "a@exemplo.com", "senha": "senha-forte-1"})
        self.assertEqual((r.status_code, r.get_json()["email"]), (200, "a***@exemplo.com"))
        self.assertTrue(self.c.get("/api/auth/me").get_json()["tem_email"])
        self.pedir("a@exemplo.com")
        self.assertEqual(len(self.caixa.enviados), 1)

    def test_email_de_outra_conta_e_recusado_e_sem_login_nao_vale(self):
        self.cadastrar()
        self.entrar_sem_email()
        r = self.c.post("/api/auth/email", json={"email": "maria@exemplo.com", "senha": "senha-forte-1"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.app.test_client().post("/api/auth/email", json={"email": "x@exemplo.com", "senha": "x"}).status_code, 401)


class TestBancoAntigo(unittest.TestCase):
    def test_banco_sem_a_coluna_email_e_atualizado_sem_perder_contas(self):
        with tempfile.TemporaryDirectory() as d:
            arq = str(pathlib.Path(d) / "velho.db")
            con = sqlite3.connect(arq)
            con.executescript("CREATE TABLE users(id TEXT PRIMARY KEY, nome TEXT UNIQUE COLLATE NOCASE, hash TEXT, created_at REAL);"
                              "INSERT INTO users VALUES('u1','antigo','scrypt$aa$bb',1.0);")
            con.commit(); con.close()
            st = Store(arq)
            colunas = [r[1] for r in st._run("PRAGMA table_info(users)", fetch=True)]
            self.assertIn("email", colunas)
            self.assertEqual(st._run("SELECT nome,email FROM users", fetch=True), [("antigo", None)])
            Store(arq)                                                      # abrir de novo não quebra


class TestEnvioDeEmail(unittest.TestCase):
    def test_brevo_monta_a_chamada_certa(self):
        chamadas = []
        b = emails.Brevo("CHAVE", "no-reply@meusite.com", "SoulsBPM", http=lambda *a: chamadas.append(a) or 201)
        b.enviar("ana@exemplo.com", "Ana", "Assunto", "<p>oi</p>", "oi")
        url, cab, corpo, _ = chamadas[0]
        self.assertEqual(url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(cab["api-key"], "CHAVE")
        self.assertEqual(corpo["sender"], {"name": "SoulsBPM", "email": "no-reply@meusite.com"})
        self.assertEqual(corpo["to"], [{"email": "ana@exemplo.com", "name": "Ana"}])
        self.assertEqual((corpo["subject"], corpo["htmlContent"], corpo["textContent"]), ("Assunto", "<p>oi</p>", "oi"))

    def test_brevo_erro_vira_excecao_sem_vazar_a_chave(self):
        b = emails.Brevo("CHAVE-SECRETA", "a@b.com", http=lambda *a: 401)
        with self.assertRaises(emails.EmailErro) as cm:
            b.enviar("ana@exemplo.com", "Ana", "x", "x", "x")
        self.assertNotIn("CHAVE-SECRETA", str(cm.exception))
        self.assertIn("401", str(cm.exception))

    def test_ambiente_escolhe_o_servico(self):
        self.assertIsNone(emails.do_ambiente({}))
        self.assertIsNone(emails.do_ambiente({"BREVO_API_KEY": "k"}))                 # falta o remetente
        self.assertIsInstance(emails.do_ambiente({"BREVO_API_KEY": "k", "EMAIL_REMETENTE": "a@b.com"}), emails.Brevo)
        self.assertIsInstance(emails.do_ambiente({"EMAIL_MODO": "console"}), emails.Console)

    def test_texto_do_email_escapa_o_nome_e_leva_o_link(self):
        assunto, corpo, texto = emails.recuperacao('<b>Ana</b>"', "https://x.com/redefinir?token=abc")
        self.assertNotIn("<b>Ana</b>", corpo)
        self.assertIn("&lt;b&gt;Ana&lt;/b&gt;", corpo)
        self.assertIn("https://x.com/redefinir?token=abc", corpo)
        self.assertIn("https://x.com/redefinir?token=abc", texto)


if __name__ == "__main__":
    unittest.main()
