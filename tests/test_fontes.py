"""Integração com a fonte real (GetSongBPM) sem rede: HTTP simulado."""
import json
import os
import tempfile
import unittest
import urllib.error

from app import create_app
from soulsbpm import fontes
from soulsbpm.fontes import Cache, FonteErro, GetSongBPM, montar_faixa, para_camelot
from tools.importar_catalogo import importar, ler_entrada


class FakeHttp:
    def __init__(self, respostas):
        self.respostas, self.chamadas = respostas, []

    def __call__(self, url):
        self.chamadas.append(url)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def item(titulo="Strobe", artista="deadmau5", tempo="128", key_of="F#m", open_key="11m"):
    return {"id": "x1", "title": titulo, "tempo": tempo, "key_of": key_of, "open_key": open_key,
            "artist": {"name": artista}}


def fonte(*respostas, **kw):
    return GetSongBPM("chave", Cache(), FakeHttp(list(respostas)), pausa=0, **kw)


class CamelotTests(unittest.TestCase):
    def test_tons_conhecidos(self):
        casos = {"Am": "8A", "C": "8B", "F#m": "11A", "Bb": "6B", "G♯m": "1A", "A♭": "4B", "Dm": "7A",
                 "E minor": "9A", "D major": "10B", "Ebm": "2A", "B": "1B"}
        for k, esperado in casos.items():
            self.assertEqual(para_camelot(k), esperado, k)

    def test_open_key(self):
        self.assertEqual(para_camelot(None, "1d"), "8B")     # Dó maior
        self.assertEqual(para_camelot(None, "1m"), "8A")     # Lá menor
        self.assertEqual(para_camelot(None, "6d"), "1B")     # Si maior

    def test_invalido(self):
        self.assertIsNone(para_camelot("???", "x"))
        self.assertIsNone(para_camelot(None, None))

    def test_toda_saida_e_camelot_valido(self):
        from soulsbpm.dj import parse_key
        for pc in range(12):
            parse_key(fontes._CAMELOT_MAIOR[pc])
            parse_key(fontes._CAMELOT_MENOR[pc])
        self.assertEqual(len(set(fontes._CAMELOT_MAIOR.values())), 12)
        self.assertEqual(len(set(fontes._CAMELOT_MENOR.values())), 12)


class BuscaTests(unittest.TestCase):
    def test_busca_basica_e_cache(self):
        f = fonte({"search": [item()]})
        self.assertEqual(f.buscar("deadmau5", "Strobe"), {"bpm": 128, "tom": "11A"})
        self.assertEqual(f.buscar("DeadMau5", "strobe"), {"bpm": 128, "tom": "11A"})   # veio do cache
        self.assertEqual(len(f._http.chamadas), 1)

    def test_nao_encontrado_vai_para_cache_negativo(self):
        f = fonte({"search": []})
        self.assertIsNone(f.buscar("Ninguém", "Nada"))
        self.assertIsNone(f.buscar("Ninguém", "Nada"))
        self.assertEqual(len(f._http.chamadas), 1)

    def test_recusa_artista_diferente(self):
        f = fonte({"search": [item(artista="Outro Artista")]})
        self.assertIsNone(f.buscar("deadmau5", "Strobe"))

    def test_consulta_detalhe_quando_busca_nao_traz_tom(self):
        sem_tom = {"id": "x1", "title": "Strobe", "artist": {"name": "deadmau5"}}
        f = fonte({"search": [sem_tom]}, {"song": item()})
        self.assertEqual(f.buscar("deadmau5", "Strobe"), {"bpm": 128, "tom": "11A"})

    def test_bpm_absurdo_ou_lixo_e_descartado(self):
        sem_id = lambda **k: {kk: v for kk, v in item(**k).items() if kk != "id"}
        f = fonte({"search": [sem_id(tempo="9000"), sem_id(tempo="abc")]})
        self.assertIsNone(f.buscar("deadmau5", "Strobe"))

    def test_resposta_estranha_nao_quebra(self):
        for lixo in ({}, {"search": None}, {"search": ["x", 3]}, [], "texto"):
            self.assertIsNone(fonte(lixo).buscar("a", "b"))

    def test_chave_recusada(self):
        err = urllib.error.HTTPError("u", 403, "x", {}, None)
        with self.assertRaises(FonteErro):
            fonte(err).buscar("a", "b")

    def test_sem_chave(self):
        with self.assertRaises(FonteErro):
            GetSongBPM("")

    def test_cota_429_tenta_de_novo(self):
        orig = fontes.time.sleep
        fontes.time.sleep = lambda s: None
        try:
            f = fonte(urllib.error.HTTPError("u", 429, "x", {}, None), {"search": [item()]})
            self.assertEqual(f.buscar("deadmau5", "Strobe")["bpm"], 128)
        finally:
            fontes.time.sleep = orig

    def test_ttl_do_cache(self):
        c = Cache()
        c.put("k", None, agora=0)
        self.assertEqual(c.get("k", agora=6 * 86400), (True, None))
        self.assertEqual(c.get("k", agora=8 * 86400), (False, None))


class DadosDaApiTests(unittest.TestCase):
    def test_exemplo_da_documentacao(self):
        """Resposta real documentada pela GetSongBPM (Master of Puppets)."""
        doc = {"id": "o2r0L", "title": "Master of Puppets", "tempo": "220", "time_sig": "4/4", "key_of": "Em",
               "open_key": "2m", "danceability": 55, "acousticness": 0,
               "artist": {"id": "nZR", "name": "Metallica"}}
        f = fonte({"search": [doc]})
        r = f.buscar("Metallica", "Master of Puppets")
        self.assertEqual((r["bpm"], r["tom"]), (220, "9A"))                 # Mi menor = 9A; Open Key 2m também
        self.assertEqual(para_camelot(None, "2m"), "9A")
        self.assertEqual((r["danceabilidade"], r["acustica"]), (55, 0))

    def test_danceability_e_acustica_influenciam_a_energia(self):
        base = fontes.estimar_energia(100)
        self.assertGreater(fontes.estimar_energia(100, (), 95, 0), base)
        self.assertLess(fontes.estimar_energia(100, (), 5, 100), base)
        self.assertEqual(fontes.estimar_energia(100, (), "x", None), base)     # lixo é ignorado

    def test_limite_por_hora_protege_a_chave(self):
        f = fonte(*[{"search": []} for _ in range(5)], limite_hora=2)
        f.buscar("a", "1")
        f.buscar("a", "2")
        with self.assertRaises(FonteErro):
            f.buscar("a", "3")
        self.assertEqual(len(f._http.chamadas), 2)


class CatalogoTests(unittest.TestCase):
    def test_faixa_no_formato_do_app_e_energia_marcada_como_estimada(self):
        f = montar_faixa(1, "A", "B", {"bpm": 128, "tom": "8A"}, ["house"])
        for campo in ("id", "titulo", "artista", "bpm", "tom", "energia", "generos", "tags", "duracao"):
            self.assertIn(campo, f)
        self.assertTrue(f["energia_estimada"])
        self.assertTrue(0.05 <= f["energia"] <= 0.95)
        g = montar_faixa(2, "A", "C", {"bpm": 70, "tom": "8A"}, energia="0,4".replace(",", "."), duracao=180)
        self.assertFalse(g["energia_estimada"])
        self.assertEqual((g["energia"], g["duracao"]), (0.4, 180))

    def test_energia_estimada_cresce_com_bpm(self):
        self.assertLess(fontes.estimar_energia(70, ["ambient"]), fontes.estimar_energia(140, ["techno"]))

    def test_importar_csv_e_app_roda_com_catalogo_real(self):
        with tempfile.TemporaryDirectory() as d:
            csv_ = os.path.join(d, "f.csv")
            with open(csv_, "w", encoding="utf-8") as fh:
                fh.write("artista;titulo;generos;tags\n")
                fh.write("deadmau5;Strobe;house|eletronica;festa|danca\n")
                fh.write("deadmau5;Strobe;house;festa\n")                   # duplicada: ignora
                fh.write("Nada;Inexistente;;\n")
                for i in range(8):
                    fh.write(f"Artista{i};Faixa{i};pop;feliz\n")
            resp = [{"search": [item()]}, {"search": []}] + [
                {"search": [item(f"Faixa{i}", f"Artista{i}", str(100 + i), "C", "1d")]} for i in range(8)]
            faixas, faltaram = importar(ler_entrada(csv_), fonte(*resp), avisar=lambda *_: None)
            self.assertEqual((len(faixas), faltaram), (9, ["Nada - Inexistente"]))
            self.assertEqual(len({x["id"] for x in faixas}), 9)
            cat = os.path.join(d, "cat.json")
            with open(cat, "w", encoding="utf-8") as fh:
                json.dump(faixas, fh)
            c = create_app(":memory:", catalog_path=cat).test_client()
            r = c.post("/api/search", json={"user_id": "u", "text": "música animada feliz"}).get_json()
            self.assertEqual(r["estado"], "resultados")
            sid = r["session_id"]
            d = c.post(f"/api/session/{sid}/play", json={"user_id": "u", "track_id": r["resultados"][0]["id"]}).get_json()
            self.assertEqual(d["estado"], "sugerindo_proxima")


if __name__ == "__main__":
    unittest.main()
