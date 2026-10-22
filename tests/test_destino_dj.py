"""Modo DJ com playlist de destino: o que a pessoa aceita é salvo na playlist e sai se o aceite for desfeito."""
import pathlib
import unittest

from app import create_app

CATALOGO = str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json")


class DestinoDJ(unittest.TestCase):
    def setUp(self):
        self.app = create_app(":memory:", catalog_path=CATALOGO)
        self.c = self.app.test_client()
        self.c.post("/api/auth/register", json={"nome": "tester", "email": "tester@exemplo.com", "senha": "senha-forte-1"})
        r = self.c.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()
        self.sid = r["session_id"]
        self.d = self.post(f"/api/session/{self.sid}/play", track_id=r["resultados"][0]["id"])
        self.pid = self.c.post("/api/playlists", json={"title": "Destino"}).get_json()["id"]

    def post(self, url, **corpo):
        return self.c.post(url, json=corpo).get_json()

    def destino(self, pid):
        return self.post(f"/api/session/{self.sid}/destination", playlist_id=pid)

    def faixas(self, pid=None):
        return [f["id"] for f in self.c.get(f"/api/playlists/{pid or self.pid}").get_json()["faixas"]]

    def sequencia(self, d):
        return [f["id"] for f in d["sequencia"]]

    def test_escolher_destino_leva_a_faixa_atual_e_aceitar_acrescenta(self):
        d = self.destino(self.pid)
        self.assertEqual(d["destino"]["title"], "Destino")
        self.assertEqual(self.faixas(), self.sequencia(d))
        d = self.post(f"/api/session/{self.sid}/accept")
        self.assertEqual(len(self.sequencia(d)), 2)
        self.assertEqual(self.faixas(), self.sequencia(d))
        self.assertEqual(d["destino"]["faixas"], 2)

    def test_desfazer_aceite_tira_a_faixa_da_playlist(self):
        self.destino(self.pid)
        self.post(f"/api/session/{self.sid}/accept")
        d = self.post(f"/api/session/{self.sid}/undo-accept")
        self.assertEqual(self.faixas(), self.sequencia(d))
        self.assertEqual(len(self.faixas()), 1)

    def test_pular_a_faixa_atual_troca_tambem_na_playlist(self):
        self.destino(self.pid)
        self.post(f"/api/session/{self.sid}/accept")
        d = self.post(f"/api/session/{self.sid}/skip", target="atual", elapsed_fraction=0.1)
        self.assertEqual(self.faixas(), self.sequencia(d))

    def test_voltar_mantem_a_playlist_igual_ao_set(self):
        self.destino(self.pid)
        self.post(f"/api/session/{self.sid}/accept")
        d = self.post(f"/api/session/{self.sid}/back")
        self.assertEqual(self.faixas(), self.sequencia(d))

    def test_sem_destino_nada_e_salvo(self):
        self.post(f"/api/session/{self.sid}/accept")
        self.assertEqual(self.faixas(), [])
        self.assertIsNone(self.post(f"/api/session/{self.sid}/accept")["destino"])

    def test_parar_o_destino_para_de_salvar(self):
        self.destino(self.pid)
        d = self.destino(None)
        self.assertIsNone(d["destino"])
        self.post(f"/api/session/{self.sid}/accept")
        self.assertEqual(len(self.faixas()), 1)                      # só a que entrou ao escolher

    def test_o_que_ja_estava_na_playlist_nao_sai(self):
        antigas = [f["id"] for f in self.c.post("/api/search", json={"text": "treino pesado de academia"}).get_json()["resultados"]][:2]
        pid2 = self.c.post("/api/playlists", json={"title": "Com faixas", "track_ids": antigas}).get_json()["id"]
        self.destino(pid2)
        self.post(f"/api/session/{self.sid}/accept")
        d = self.post(f"/api/session/{self.sid}/undo-accept")
        self.assertTrue(set(antigas) <= set(self.faixas(pid2)))
        self.assertEqual(self.faixas(pid2)[:2], antigas)

    def test_playlist_excluida_no_meio_avisa_e_o_aceite_continua(self):
        self.destino(self.pid)
        self.c.delete(f"/api/playlists/{self.pid}")
        d = self.post(f"/api/session/{self.sid}/accept")
        self.assertEqual(len(self.sequencia(d)), 2)
        self.assertIsNone(d["destino"])
        self.assertIn("não existe mais", d["aviso_destino"])
        self.assertIsNone(self.post(f"/api/session/{self.sid}/accept")["aviso_destino"])    # recado aparece uma vez

    def test_destino_de_outra_conta_ou_sem_login_e_recusado(self):
        outro = self.app.test_client()
        outro.post("/api/auth/register", json={"nome": "intruso", "email": "intruso@exemplo.com", "senha": "senha-forte-2"})
        r = outro.post(f"/api/session/{self.sid}/destination", json={"playlist_id": self.pid})
        self.assertEqual(r.status_code, 404)                          # sessão que não é dele
        anonimo = self.app.test_client().post(f"/api/session/{self.sid}/destination", json={"playlist_id": self.pid})
        self.assertEqual(anonimo.status_code, 403)
        c2 = self.app.test_client()
        c2.post("/api/auth/register", json={"nome": "outro", "email": "outro@exemplo.com", "senha": "senha-forte-3"})
        sid2 = c2.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()["session_id"]
        ids = [f["id"] for f in c2.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()["resultados"]]
        c2.post(f"/api/session/{sid2}/play", json={"track_id": ids[0]})
        self.assertEqual(c2.post(f"/api/session/{sid2}/destination", json={"playlist_id": self.pid}).status_code, 404)

    def test_continuar_playlist_ja_usa_ela_como_destino(self):
        ids = [f["id"] for f in self.c.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()["resultados"]][:2]
        pid = self.c.post("/api/playlists", json={"title": "Para continuar", "track_ids": ids}).get_json()["id"]
        d = self.post(f"/api/playlists/{pid}/continue")
        self.assertEqual(d["destino"]["id"], pid)
        sid = d["session_id"]
        d = self.post(f"/api/session/{sid}/accept")
        self.assertEqual(self.faixas(pid), self.sequencia(d))
        self.assertEqual(len(self.faixas(pid)), 3)


if __name__ == "__main__":
    unittest.main()
