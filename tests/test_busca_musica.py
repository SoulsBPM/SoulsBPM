"""Busca universal: nome da música, "Artista - Música" e trecho de letra (Last.fm e IA simulados)."""
import unittest
import urllib.parse

from soulsbpm import musicfinder, sugestor
from soulsbpm.aovivo import AoVivo, LastFm
from soulsbpm.engine import Motor
from soulsbpm.fontes import Cache, GetSongBPM
from soulsbpm.store import Store

ACHADAS = {"oi|lagum": [("Lagum", "Oi")], "yellow": [("Coldplay", "Yellow"), ("Outra Banda", "Yellow Submarine Blues")],
           "bohemian rhapsody": [("Queen", "Bohemian Rhapsody")]}
TABELA = {("Coldplay", "Yellow"): (87, "B"), ("Coldplay", "Clocks"): (131, "Eb"), ("Coldplay", "Fix You"): (138, "Eb"),
          ("Keane", "Somewhere Only We Know"): (172, "C")}


def lastfm():
    def http(url):
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}
        m = q["method"]
        if m == "track.search":
            nome = q["track"].lower()
            achadas = ACHADAS.get(nome + "|" + q["artist"].lower()) if "artist" in q else None
            achadas = achadas or ACHADAS.get(nome, [])
            return {"results": {"trackmatches": {"track": [{"name": t, "artist": a} for a, t in achadas]}}}
        if m == "artist.gettoptracks":
            return {"toptracks": {"track": [{"name": t, "artist": {"name": a}} for a, t in TABELA if a == q["artist"]]}}
        if m == "track.getsimilar":
            return {"similartracks": {"track": [{"name": "Somewhere Only We Know", "artist": {"name": "Keane"}}]}}
        return {}
    return LastFm("k", http, pausa=0)


def bpm():
    def http(url):
        for (a, t), (b, tom) in TABELA.items():
            if f"song%3A{t.replace(' ', '+')}" in url:
                return {"search": [{"id": "1", "title": t, "tempo": str(b), "key_of": tom, "artist": {"name": a}}]}
        return {"search": []}
    return GetSongBPM("k", Cache(), http, pausa=0)


class SoGetSongBPMTests(unittest.TestCase):
    def test_acha_pelo_getsongbpm_quando_lastfm_nao_conhece(self):
        def http_bpm(url):
            if "type=song" in url and "lookup=mundo+novo" in url:
                return {"search": [{"id": "9", "title": "Mundo Novo", "tempo": "100", "key_of": "Am",
                                    "artist": {"name": "Banda Z"}}]}
            return {"search": []}
        prov = AoVivo(LastFm("k", lambda u: {}, pausa=0), GetSongBPM("k", Cache(), http_bpm, pausa=0))
        pontos, faixas, info = prov.candidatas_musica("mundo novo")
        self.assertEqual(info["achadas"], [("Banda Z", "Mundo Novo")])
        self.assertEqual([f["bpm"] for f in faixas], [100])
        self.assertEqual(info["sem_bpm"], [])


class IAFalsa:
    def __init__(self, resposta):
        self.resposta, self.pedidos = resposta, []

    def completar(self, sistema, usuario, **kw):
        self.pedidos.append(usuario)
        return self.resposta


class RelevanciaTests(unittest.TestCase):
    def test_nome_exato_e_parcial(self):
        self.assertEqual(musicfinder.relevancia("yellow", "Yellow", "Coldplay"), 1.0)
        self.assertEqual(musicfinder.relevancia("Coldplay - Yellow", "Yellow", "Coldplay"), 1.0)
        self.assertLess(musicfinder.relevancia("yellow", "Yellow Submarine Blues", "X"), 0.7)
        self.assertEqual(musicfinder.relevancia("SÃO João", "Sao Joao", "x"), 1.0)
        self.assertEqual(musicfinder.relevancia("", "a", "b"), 0.0)

    def test_catalogo_local(self):
        cat = [{"id": "1", "titulo": "Yellow", "artista": "Coldplay"}, {"id": "2", "titulo": "Fix You", "artista": "Coldplay"}]
        self.assertEqual(musicfinder.destaques_no_catalogo(cat, "yellow"), {"1": 1.0})
        self.assertEqual(musicfinder.destaques_no_catalogo(cat, "zzz"), {})


class AoVivoMusicaTests(unittest.TestCase):
    def prov(self):
        return AoVivo(lastfm(), bpm())

    def test_por_nome(self):
        pontos, faixas, info = self.prov().candidatas_musica("yellow")
        self.assertEqual(info["achadas"], [("Coldplay", "Yellow")])
        por = {f["titulo"]: pontos[f["id"]] for f in faixas}
        self.assertEqual(por["Yellow"], 1.0)
        self.assertEqual(por["Clocks"], 0.8)
        self.assertEqual(por["Somewhere Only We Know"], 0.7)

    def test_artista_hifen_titulo(self):
        r = self.prov().candidatas_musica("Coldplay - Yellow")
        self.assertIsNotNone(r)

    def test_titulo_e_artista_juntos(self):
        r = self.prov().candidatas_musica("oi lagum")
        self.assertEqual(r[2]["achadas"], [("Lagum", "Oi")])
        self.assertEqual(self.prov().candidatas_musica("lagum oi")[2]["achadas"], [("Lagum", "Oi")])

    def test_nao_acha(self):
        self.assertIsNone(self.prov().candidatas_musica("nada disso existe"))
        self.assertIsNone(self.prov().candidatas_musica("a"))

    def test_letra_via_ia_confirmada(self):
        ia = IAFalsa('{"musicas": [{"artista": "Queen", "titulo": "Bohemian Rhapsody"}]}')
        ident = lambda t: sugestor.identificar_musica(ia, t)
        r = self.prov().candidatas_musica("is this the real life", ident)
        self.assertEqual(r[2]["achadas"], [("Queen", "Bohemian Rhapsody")])
        self.assertEqual(r[2]["sem_bpm"], [("Queen", "Bohemian Rhapsody")])   # sem BPM na fonte: dito com honestidade

    def test_ia_inventada_e_descartada(self):
        ia = IAFalsa('{"musicas": [{"artista": "Fulano", "titulo": "Musica Que Nao Existe"}]}')
        self.assertIsNone(self.prov().candidatas_musica("blá blá", lambda t: sugestor.identificar_musica(ia, t)))


class SugestorTests(unittest.TestCase):
    def test_lixo(self):
        for lixo in (None, "", "x", '{"musicas": "a"}', '{"musicas": [1, {"artista": 1}, {"artista": "<b>", "titulo": "t"}]}'):
            self.assertEqual(sugestor.identificar_musica(IAFalsa(lixo), "algo"), [])
        self.assertEqual(sugestor.identificar_musica(None, "algo"), [])


class MotorTests(unittest.TestCase):
    def test_busca_por_nome(self):
        m = Motor([], Store(":memory:"), provedor=AoVivo(lastfm(), bpm()))
        r = m.buscar(None, "yellow")
        self.assertEqual(r["estado"], "resultados")
        self.assertEqual(r["resultados"][0]["titulo"], "Yellow")
        self.assertIn("Yellow", r["interpretacao"]["resumo"])

    def test_letra_com_ia(self):
        ia = IAFalsa('{"musicas": [{"artista": "Queen", "titulo": "Bohemian Rhapsody"}]}')
        m = Motor([], Store(":memory:"), provedor=AoVivo(lastfm(), bpm()), ia=ia)
        r = m.buscar(None, "bohemian rhapsody")        # achada direto; a IA nem é chamada
        self.assertEqual(r["estado"], "resultados")
        self.assertIn("Bohemian Rhapsody", r["aviso"])
        self.assertIn("BPM", r["aviso"])

    def test_catalogo_local(self):
        cat = [{"id": "a1", "titulo": "Yellow", "artista": "Coldplay", "bpm": 87, "tom": "B", "energia": 0.5,
                "generos": [], "tags": [], "duracao": 200}]
        r = Motor(cat, Store(":memory:")).buscar(None, "yellow")
        self.assertEqual([x["id"] for x in r["resultados"]], ["a1"])

    def test_vibe_continua_funcionando(self):
        m = Motor([], Store(":memory:"), provedor=AoVivo(lastfm(), bpm()))
        r = m.buscar(None, "xyzzy qwerty")
        self.assertEqual(r["estado"], "inicio")
