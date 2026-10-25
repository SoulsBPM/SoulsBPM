"""Modo ao vivo sem rede: GetSongBPM simulada (tests/fakes.py)."""
import unittest
import urllib.error

from app import create_app
from soulsbpm import musicfinder
from soulsbpm.aovivo import AoVivo, id_faixa
from soulsbpm.engine import Motor
from soulsbpm.fontes import Cache, FonteErro, GetSongBPM
from soulsbpm.store import Store
from tests.fakes import gsb_falso

FAIXAS_CHILL = [("Artista %d" % i, "Faixa %d" % i) for i in range(10)]
TABELA = {a_t: (70 + 2 * i, "Am") for i, a_t in enumerate(FAIXAS_CHILL)}


def provedor(tabela=None, **kw):
    return AoVivo(gsb_falso(tabela or TABELA, **kw))


class TraducaoTests(unittest.TestCase):
    def test_bpm_alvo_segue_a_energia(self):
        lento, rapido = {"energia": 0.2}, {"energia": 0.8}
        self.assertLess(AoVivo.bpm_alvo(lento), AoVivo.bpm_alvo(rapido))
        self.assertIsNone(AoVivo.bpm_alvo({"energia": None}))
        self.assertEqual(AoVivo.bpm_alvo({"energia": 0.0}), 60)           # nunca sai da faixa útil
        self.assertLessEqual(AoVivo.bpm_alvo({"energia": 1.0}), 170)

    def test_id_estavel(self):
        self.assertEqual(id_faixa("Daft Punk", "One More Time"), id_faixa("daft  punk", "ONE MORE TIME"))


class GetSongBPMTests(unittest.TestCase):
    def test_chave_recusada(self):
        def http(url):
            raise urllib.error.HTTPError(url, 403, "x", {}, None)
        with self.assertRaises(FonteErro):
            GetSongBPM("k", Cache(), http, pausa=0).por_tempo(120)

    def test_resposta_estranha(self):
        for lixo in ({}, [], {"search": None}, {"search": ["x", 1]}, {"tempo": [{"artist": 3}]}):
            g = GetSongBPM("k", Cache(), lambda u, l=lixo: l, pausa=0)
            self.assertEqual(g.procurar("x"), [])
            self.assertEqual(g.por_tempo(100), [])
            self.assertIsNone(g.buscar_artista("x"))
            self.assertEqual(g.faixas_do_artista("x"), [])

    def test_sem_chave(self):
        with self.assertRaises(FonteErro):
            GetSongBPM("")


class AoVivoTests(unittest.TestCase):
    def test_candidatas_formato_do_app(self):
        faixas = provedor().candidatas(musicfinder.interpretar("música calma para estudar à noite"))
        self.assertTrue(faixas)
        for f in faixas:
            for campo in ("id", "titulo", "artista", "bpm", "tom", "energia", "generos", "tags", "duracao"):
                self.assertIn(campo, f)
        self.assertEqual(len({f["id"] for f in faixas}), len(faixas))

    def test_vibe_sem_energia_nao_chuta(self):
        self.assertEqual(provedor().candidatas({"energia": None, "tags": {}, "generos": []}), [])

    def test_faixa_sem_bpm_e_descartada(self):
        tabela = {**TABELA, ("X", "Sem Dados"): (73, "Am")}
        p = provedor(tabela, sem_tom={("X", "Sem Dados")})
        faixas = p.candidatas(musicfinder.interpretar("música calma"))
        self.assertTrue(faixas)
        self.assertNotIn("Sem Dados", [f["titulo"] for f in faixas])

    def test_busca_pelo_app_sem_lista_pronta_e_modo_dj(self):
        app = create_app(":memory:", provedor=provedor())
        c = app.test_client()
        self.assertEqual(c.get("/api/health").get_json()["ao_vivo"], True)
        self.assertEqual(c.get("/api/health").get_json()["faixas"], 0)          # parte vazio, sem faixas inventadas
        r = c.post("/api/search", json={"user_id": "u", "text": "música calma para estudar à noite"}).get_json()
        self.assertEqual(r["estado"], "resultados")
        self.assertTrue(all(x["id"].startswith("l") for x in r["resultados"]))
        d = c.post(f"/api/session/{r['session_id']}/play",
                   json={"user_id": "u", "track_id": r["resultados"][0]["id"]}).get_json()
        self.assertEqual(d["estado"], "sugerindo_proxima")
        self.assertGreater(len(app.motor.store.load_tracks()), 0)                # faixas guardadas no banco

    def test_falha_da_fonte_nao_derruba_a_busca(self):
        class Quebrado:
            def candidatas(self, interp):
                raise FonteErro("sem rede")
        app = create_app(":memory:", provedor=Quebrado())
        r = app.test_client().post("/api/search", json={"user_id": "u", "text": "música calma"}).get_json()
        self.assertIn("aviso", r)
        self.assertEqual(r["estado"], "sem_resultados")

    def test_faixas_descobertas_sobrevivem_ao_reinicio(self):
        store = Store(":memory:")
        m1 = Motor([], store, provedor=provedor())
        m1.buscar("u", "música calma para estudar à noite")
        n = len(m1.catalogo)
        self.assertGreater(n, 0)
        self.assertEqual(len(Motor([], store, provedor=provedor()).catalogo), n)


class ErroRealApareceTests(unittest.TestCase):
    def test_chave_da_getsongbpm_recusada_mostra_o_motivo(self):
        def http(url):
            raise urllib.error.HTTPError(url, 403, "x", {}, None)
        app = create_app(":memory:", provedor=AoVivo(GetSongBPM("k", Cache(), http, pausa=0)))
        r = app.test_client().post("/api/search", json={"user_id": "u", "text": "música calma"}).get_json()
        self.assertEqual(r["estado"], "sem_resultados")
        self.assertIn("recusada", r["aviso"])


TAB_ART = {("Calvin Harris", "Summer"): (128, "Am"), ("Calvin Harris", "Feel So Close"): (128, "Cm"),
           ("Calvin Harris", "Outside"): (128, "Gm"), ("David Guetta", "Titanium"): (126, "Dm"),
           ("David Guetta", "Memories"): (130, "Am")}


def prov_artista():
    return AoVivo(gsb_falso(TAB_ART, similares={"Calvin Harris": ["David Guetta"]}))


class ArtistaTests(unittest.TestCase):
    def test_extrai_artista_so_quando_explicito(self):
        ex = musicfinder.extrair_artista
        self.assertEqual(ex("tipo Calvin Harris"), "Calvin Harris")
        self.assertEqual(ex("eu gosto das músicas de Calvin Harris"), "Calvin Harris")
        self.assertEqual(ex("parecido com Coldplay"), "Coldplay")
        self.assertIsNone(ex("música calma para estudar à noite"))
        self.assertIsNone(ex("músicas de treino"))              # é vibe, não artista
        self.assertIsNone(ex("treino de pernas"))

    def test_busca_por_artista_traz_as_dele_e_de_parecidos(self):
        app = create_app(":memory:", provedor=prov_artista())
        c = app.test_client()
        r = c.post("/api/search", json={"user_id": "u", "text": "tipo Calvin Harris"}).get_json()
        self.assertEqual(r["estado"], "resultados")
        self.assertIn("Calvin Harris", r["interpretacao"]["resumo"])
        arts = [x["artista"] for x in r["resultados"]]
        self.assertEqual(arts[:3], ["Calvin Harris"] * 3)             # as dele primeiro
        self.assertIn("David Guetta", arts)                           # e as de artista parecido
        d = c.post(f"/api/session/{r['session_id']}/play",
                   json={"user_id": "u", "track_id": r["resultados"][0]["id"]}).get_json()
        self.assertIsNotNone(d["sugerida"])

    def test_frase_solta_so_vira_artista_se_o_nome_bater(self):
        app = create_app(":memory:", provedor=AoVivo(gsb_falso(TAB_ART, impostor="Zzz Outro")))
        c = app.test_client()
        r = c.post("/api/search", json={"user_id": "u", "text": "calvin harris"}).get_json()
        self.assertEqual(r["estado"], "resultados")
        r2 = c.post("/api/search", json={"user_id": "u", "text": "asdf qwer"}).get_json()   # não é artista
        self.assertEqual(r2["estado"], "inicio")


if __name__ == "__main__":
    unittest.main()
