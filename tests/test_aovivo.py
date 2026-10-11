"""Modo ao vivo sem rede: Last.fm e GetSongBPM simulados."""
import unittest

from app import create_app
from soulsbpm import musicfinder
from soulsbpm.aovivo import AoVivo, LastFm, id_faixa
from soulsbpm.engine import Motor
from soulsbpm.fontes import Cache, FonteErro, GetSongBPM
from soulsbpm.store import Store


def lastfm_falso(por_tag):
    def http(url):
        for tag, faixas in por_tag.items():
            if f"tag={tag.replace(' ', '+')}" in url:
                return {"tracks": {"track": [{"name": t, "artist": {"name": a}} for a, t in faixas]}}
        return {"tracks": {"track": []}}
    return LastFm("k", http, pausa=0)


def bpm_falso(tabela):
    def http(url):
        for (a, t), (bpm, tom) in tabela.items():
            if f"song%3A{t.replace(' ', '+')}" in url:
                return {"search": [{"id": "1", "title": t, "tempo": str(bpm), "key_of": tom, "artist": {"name": a}}]}
        return {"search": []}
    return GetSongBPM("k", Cache(), http, pausa=0)


FAIXAS_CHILL = [("Artista %d" % i, "Faixa %d" % i) for i in range(10)]
TABELA = {a_t: (70 + 2 * i, "Am") for i, a_t in enumerate(FAIXAS_CHILL)}


def provedor():
    return AoVivo(lastfm_falso({"chill": FAIXAS_CHILL, "night": FAIXAS_CHILL[:4], "study": FAIXAS_CHILL[2:7],
                                "focus": FAIXAS_CHILL[:3]}), bpm_falso(TABELA))


class TraducaoTests(unittest.TestCase):
    def test_tags_da_busca(self):
        interp = musicfinder.interpretar("música calma para estudar à noite")
        tags = [t[0] for t in provedor().tags_da_busca(interp)]
        self.assertIn("chill", tags)
        self.assertLessEqual(len(tags), 4)

    def test_genero_vira_tag(self):
        interp = musicfinder.interpretar("jazz")
        self.assertEqual(provedor().tags_da_busca(interp)[0][0], "jazz")

    def test_id_estavel(self):
        self.assertEqual(id_faixa("Daft Punk", "One More Time"), id_faixa("daft  punk", "ONE MORE TIME"))


class LastFmTests(unittest.TestCase):
    def test_erro_de_chave(self):
        with self.assertRaises(FonteErro):
            LastFm("k", lambda u: {"error": 10, "message": "Invalid API key"}, pausa=0).top_tracks("chill")

    def test_tag_inexistente_nao_e_erro(self):
        self.assertEqual(LastFm("k", lambda u: {"error": 6, "message": "x"}, pausa=0).top_tracks("zzz"), [])

    def test_resposta_estranha(self):
        for lixo in ({}, [], {"tracks": None}, {"tracks": {"track": ["x", 1]}}):
            self.assertEqual(LastFm("k", lambda u, l=lixo: l, pausa=0).top_tracks("t"), [])

    def test_sem_chave(self):
        with self.assertRaises(FonteErro):
            LastFm("")


class AoVivoTests(unittest.TestCase):
    def test_candidatas_formato_do_app(self):
        interp = musicfinder.interpretar("música calma para estudar à noite")
        faixas = provedor().candidatas(interp)
        self.assertTrue(faixas)
        for f in faixas:
            for campo in ("id", "titulo", "artista", "bpm", "tom", "energia", "generos", "tags", "duracao"):
                self.assertIn(campo, f)
        self.assertEqual(len({f["id"] for f in faixas}), len(faixas))     # sem repetição entre tags

    def test_faixa_sem_bpm_e_descartada(self):
        p = AoVivo(lastfm_falso({"chill": [("X", "Sem Dados")] + FAIXAS_CHILL[:3]}), bpm_falso(TABELA))
        faixas = p.candidatas(musicfinder.interpretar("música calma"))
        self.assertNotIn("Sem Dados", [f["titulo"] for f in faixas])
        self.assertEqual(len(faixas), 3)

    def test_busca_pelo_app_sem_lista_pronta_e_modo_dj(self):
        app = create_app(":memory:", provedor=provedor())
        c = app.test_client()
        self.assertEqual(c.get("/api/health").get_json()["ao_vivo"], True)
        self.assertEqual(c.get("/api/health").get_json()["faixas"], 0)          # parte vazio, sem faixas inventadas
        r = c.post("/api/search", json={"user_id": "u", "text": "música calma para estudar à noite"}).get_json()
        self.assertEqual(r["estado"], "resultados")
        self.assertTrue(all(x["id"].startswith("l") for x in r["resultados"]))
        sid = r["session_id"]
        d = c.post(f"/api/session/{sid}/play", json={"user_id": "u", "track_id": r["resultados"][0]["id"]}).get_json()
        self.assertEqual(d["estado"], "sugerindo_proxima")
        self.assertGreater(app.motor.store.load_tracks().__len__(), 0)           # faixas guardadas no banco

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
        m2 = Motor([], store, provedor=provedor())
        self.assertEqual(len(m2.catalogo), n)


if __name__ == "__main__":
    unittest.main()
