"""Busca universal: nome da música, "Artista - Música" e trecho de letra (GetSongBPM e IA simulados)."""
import unittest

from soulsbpm import musicfinder, sugestor
from soulsbpm.aovivo import AoVivo
from soulsbpm.engine import Motor
from soulsbpm.store import Store
from tests.fakes import gsb_falso

TABELA = {("Coldplay", "Yellow"): (87, "B"), ("Coldplay", "Clocks"): (131, "Eb"), ("Coldplay", "Fix You"): (138, "Eb"),
          ("Keane", "Somewhere Only We Know"): (172, "C"), ("Lagum", "Oi"): (100, "Am"),
          ("Outra Banda", "Yellow Submarine Blues"): (90, "C"), ("Queen", "Bohemian Rhapsody"): (72, "Bb")}
SIMILARES = {"Coldplay": ["Keane"]}


def fonte(**kw):
    return gsb_falso(TABELA, similares=SIMILARES, sem_tempo=True, **kw)


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

    def test_musica_sem_bpm_avisa_e_mostra_parecidas(self):
        m = Motor([], Store(":memory:"), provedor=AoVivo(fonte(sem_tom={("Queen", "Bohemian Rhapsody")})))
        r = m.buscar(None, "Queen - Bohemian Rhapsody")
        self.assertEqual(r["estado"], "sem_resultados")
        self.assertIn("BPM", r["mensagem"])

    def test_catalogo_local(self):
        cat = [{"id": "1", "titulo": "Yellow", "artista": "Coldplay"}, {"id": "2", "titulo": "Fix You", "artista": "Coldplay"}]
        self.assertEqual(musicfinder.destaques_no_catalogo(cat, "yellow"), {"1": 1.0})
        self.assertEqual(musicfinder.destaques_no_catalogo(cat, "zzz"), {})


class AoVivoMusicaTests(unittest.TestCase):
    def prov(self):
        return AoVivo(fonte())

    def test_por_nome(self):
        pontos, faixas, info = self.prov().candidatas_musica("yellow")
        self.assertEqual(info["achadas"], [("Coldplay", "Yellow")])
        por = {f["titulo"]: pontos[f["id"]] for f in faixas}
        self.assertEqual(por["Yellow"], 1.0)
        self.assertEqual(por["Clocks"], 0.8)
        self.assertEqual(por["Somewhere Only We Know"], 0.7)      # de um artista parecido

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
        self.assertEqual(r[2]["sem_bpm"], [])

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
        m = Motor([], Store(":memory:"), provedor=AoVivo(fonte()))
        r = m.buscar(None, "yellow")
        self.assertEqual(r["estado"], "resultados")
        self.assertEqual(r["resultados"][0]["titulo"], "Yellow")
        self.assertIn("Yellow", r["interpretacao"]["resumo"])

    def test_letra_com_ia(self):
        ia = IAFalsa('{"musicas": [{"artista": "Queen", "titulo": "Bohemian Rhapsody"}]}')
        m = Motor([], Store(":memory:"), provedor=AoVivo(fonte()), ia=ia)
        r = m.buscar(None, "bohemian rhapsody")        # achada direto; a IA nem é chamada
        self.assertEqual(r["estado"], "resultados")
        self.assertEqual(r["resultados"][0]["titulo"], "Bohemian Rhapsody")
        self.assertEqual(ia.pedidos, [])

    def test_musica_sem_bpm_avisa_e_mostra_parecidas(self):
        m = Motor([], Store(":memory:"), provedor=AoVivo(fonte(sem_tom={("Queen", "Bohemian Rhapsody")})))
        r = m.buscar(None, "Queen - Bohemian Rhapsody")
        self.assertEqual(r["estado"], "sem_resultados")
        self.assertIn("BPM", r["mensagem"])

    def test_catalogo_local(self):
        cat = [{"id": "a1", "titulo": "Yellow", "artista": "Coldplay", "bpm": 87, "tom": "B", "energia": 0.5,
                "generos": [], "tags": [], "duracao": 200}]
        r = Motor(cat, Store(":memory:")).buscar(None, "yellow")
        self.assertEqual([x["id"] for x in r["resultados"]], ["a1"])

    def test_vibe_continua_funcionando(self):
        m = Motor([], Store(":memory:"), provedor=AoVivo(fonte()))
        r = m.buscar(None, "xyzzy qwerty")
        self.assertEqual(r["estado"], "inicio")


class ArtistaViaIATests(unittest.TestCase):
    """A GetSongBPM não lista as músicas de um artista: a IA diz as famosas e a GetSongBPM confirma o BPM."""
    RESP = ('{"musicas": [{"artista": "Coldplay", "titulo": "Clocks"}, {"artista": "Coldplay", "titulo": "Fix You"},'
            ' {"artista": "Coldplay", "titulo": "Musica Inventada"}, {"artista": "Outro", "titulo": "Intruso"}]}')

    def motor(self, ia):
        return Motor([], Store(":memory:"), provedor=AoVivo(fonte(sem_listagem=True)), ia=ia)

    def test_busca_por_artista_com_ia(self):
        r = self.motor(IAFalsa(self.RESP)).buscar(None, "Coldplay")
        self.assertEqual(r["estado"], "resultados")
        titulos = {x["titulo"] for x in r["resultados"]}
        self.assertEqual(titulos & {"Clocks", "Fix You"}, {"Clocks", "Fix You"})
        self.assertNotIn("Musica Inventada", titulos)          # a GetSongBPM não conhece: descartada
        self.assertNotIn("Intruso", titulos)                   # de outro artista: nem entra

    def test_sem_ia_o_artista_nao_quebra(self):
        r = self.motor(None).buscar(None, "Coldplay")
        self.assertIn(r["estado"], ("inicio", "sem_resultados"))
