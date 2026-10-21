"""Gerenciar playlists pela API: criar, renomear, reordenar/remover faixas, adicionar e excluir (só o dono)."""
import pathlib
import unittest

from app import create_app
from soulsbpm import engine

CATALOGO = str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json")


class PlaylistsApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app(":memory:", catalog_path=CATALOGO)
        self.c = self.app.test_client()
        self.c.post("/api/auth/register", json={"nome": "tester", "senha": "senha-forte-1"})
        r = self.c.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()
        self.ids = [f["id"] for f in r["resultados"]]
        self.assertGreaterEqual(len(self.ids), 4)

    def criar(self, titulo="Minha lista", **extra):
        return self.c.post("/api/playlists", json={"title": titulo, **extra})

    def outro_usuario(self):
        c = self.app.test_client()
        c.post("/api/auth/register", json={"nome": "intruso", "senha": "senha-forte-2"})
        return c

    def faixas(self, pid):
        return [f["id"] for f in self.c.get(f"/api/playlists/{pid}").get_json()["faixas"]]

    # criar
    def test_criar_vazia_aparece_na_lista_e_no_link_publico(self):
        r = self.criar("Treino de sábado", tags=["Treino", "treino", " energia "])
        self.assertEqual(r.status_code, 201)
        pl = r.get_json()
        self.assertEqual((pl["title"], pl["tags"], pl["faixas"]), ("Treino de sábado", ["treino", "energia"], 0))
        lista = self.c.get("/api/playlists").get_json()["playlists"]
        self.assertEqual([p["id"] for p in lista], [pl["id"]])
        self.assertEqual(self.c.get(f"/api/playlists/{pl['id']}").get_json()["faixas"], [])

    def test_criar_ja_com_faixas_sem_repetir(self):
        pl = self.criar(track_ids=self.ids[:3] + [self.ids[0]]).get_json()
        self.assertEqual(self.faixas(pl["id"]), self.ids[:3])

    def test_criar_nao_alimenta_o_grafo_de_transicoes(self):
        store = next(o for v in self.app.view_functions.values() for cell in (v.__closure__ or ())
                     for o in [cell.cell_contents] if hasattr(o, "graph_pairs"))
        antes = list(store.graph_pairs())
        self.criar(track_ids=self.ids[:4])
        self.assertEqual(list(store.graph_pairs()), antes)

    def test_validacoes_de_nome_e_faixas(self):
        self.assertEqual(self.criar("   ").status_code, 400)
        self.assertEqual(self.criar("x" * 81).status_code, 400)
        self.assertEqual(self.criar(track_ids=["nao-existe"]).status_code, 404)
        self.assertEqual(self.criar(track_ids="abc").status_code, 400)
        self.assertEqual(self.criar(tags="treino").status_code, 400)

    def test_limite_de_playlists_por_conta(self):
        antigo, engine.MAX_PLAYLISTS = engine.MAX_PLAYLISTS, 2
        self.addCleanup(setattr, engine, "MAX_PLAYLISTS", antigo)
        self.assertEqual(self.criar("a").status_code, 201)
        self.assertEqual(self.criar("b").status_code, 201)
        self.assertEqual(self.criar("c").status_code, 400)

    # editar
    def test_renomear_e_trocar_tags(self):
        pid = self.criar("Antigo").get_json()["id"]
        r = self.c.patch(f"/api/playlists/{pid}", json={"title": "  Novo   nome ", "tags": ["calma"]})
        self.assertEqual((r.status_code, r.get_json()["title"], r.get_json()["tags"]), (200, "Novo nome", ["calma"]))
        self.assertEqual(self.c.patch(f"/api/playlists/{pid}", json={"title": ""}).status_code, 400)

    def test_remover_e_reordenar_faixas(self):
        pid = self.criar(track_ids=self.ids[:4]).get_json()["id"]
        nova = [self.ids[3], self.ids[1], self.ids[0]]                    # tirou a 3ª e mudou a ordem
        r = self.c.patch(f"/api/playlists/{pid}", json={"track_ids": nova})
        self.assertEqual(r.get_json()["faixas"], 3)
        self.assertEqual(self.faixas(pid), nova)

    def test_patch_so_muda_o_que_foi_enviado(self):
        pid = self.criar("Fixo", tags=["a"], track_ids=self.ids[:2]).get_json()["id"]
        self.c.patch(f"/api/playlists/{pid}", json={"title": "Outro"})
        pub = self.c.get(f"/api/playlists/{pid}").get_json()
        self.assertEqual((pub["tags"], [f["id"] for f in pub["faixas"]]), (["a"], self.ids[:2]))

    def test_adicionar_faixa_uma_vez_so(self):
        pid = self.criar().get_json()["id"]
        a = self.c.post(f"/api/playlists/{pid}/tracks", json={"track_id": self.ids[0]}).get_json()
        b = self.c.post(f"/api/playlists/{pid}/tracks", json={"track_id": self.ids[0]}).get_json()
        self.assertEqual((a["faixas"], a["ja_estava"], b["faixas"], b["ja_estava"]), (1, False, 1, True))
        self.assertEqual(self.c.post(f"/api/playlists/{pid}/tracks", json={"track_id": "nao-existe"}).status_code, 404)

    # excluir
    def test_excluir_remove_da_lista_e_do_link(self):
        pid = self.criar().get_json()["id"]
        self.assertEqual(self.c.delete(f"/api/playlists/{pid}").status_code, 200)
        self.assertEqual(self.c.get("/api/playlists").get_json()["playlists"], [])
        self.assertEqual(self.c.get(f"/api/playlists/{pid}").status_code, 404)
        self.assertEqual(self.c.delete(f"/api/playlists/{pid}").status_code, 404)

    # permissões
    def test_sem_login_nada_disso_funciona(self):
        anonimo = self.app.test_client()
        pid = self.criar().get_json()["id"]
        for r in (anonimo.post("/api/playlists", json={"title": "x"}),
                  anonimo.patch(f"/api/playlists/{pid}", json={"title": "x"}),
                  anonimo.delete(f"/api/playlists/{pid}"),
                  anonimo.post(f"/api/playlists/{pid}/tracks", json={"track_id": self.ids[0]})):
            self.assertEqual(r.status_code, 403)

    def test_outra_conta_nao_edita_nem_exclui(self):
        pid = self.criar("Minha", track_ids=self.ids[:2]).get_json()["id"]
        intruso = self.outro_usuario()
        self.assertEqual(intruso.patch(f"/api/playlists/{pid}", json={"title": "Roubada"}).status_code, 404)
        self.assertEqual(intruso.delete(f"/api/playlists/{pid}").status_code, 404)
        self.assertEqual(intruso.post(f"/api/playlists/{pid}/tracks", json={"track_id": self.ids[3]}).status_code, 404)
        pub = self.c.get(f"/api/playlists/{pid}").get_json()
        self.assertEqual((pub["title"], len(pub["faixas"])), ("Minha", 2))

    # Modo DJ
    def test_continuar_playlist_vazia_explica(self):
        pid = self.criar().get_json()["id"]
        r = self.c.post(f"/api/playlists/{pid}/continue")
        self.assertEqual(r.status_code, 400)
        self.assertIn("vazia", r.get_json()["erro"])


if __name__ == "__main__":
    unittest.main()
