import json
import pathlib
import unittest
from soulsbpm import musicfinder as mf

CAT = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json").read_text("utf-8"))


class InterpretarTests(unittest.TestCase):
    def test_exemplo_do_projeto(self):
        i = mf.interpretar("Música calma para estudar à noite")
        self.assertTrue(i["clara"])
        for t in ("calma", "foco", "noite"):
            self.assertIn(t, i["tags"])
        self.assertLess(i["energia"], 0.35)

    def test_treino_tem_energia_alta(self):
        self.assertGreater(mf.interpretar("treino pesado na academia")["energia"], 0.8)

    def test_genero(self):
        self.assertIn("jazz", mf.interpretar("jantar romântico com jazz")["generos"])

    def test_sem_acento_e_caixa(self):
        a, b = mf.interpretar("MUSICA CALMA PARA ESTUDAR"), mf.interpretar("música calma para estudar")
        self.assertEqual(a["tags"], b["tags"])

    def test_vibe_pouco_clara_d1(self):
        i = mf.interpretar("asdf qwer zzz")
        self.assertFalse(i["clara"])
        self.assertTrue(i["exemplos"])

    def test_termos_tecnicos_ligam_visao_tecnica(self):
        self.assertTrue(mf.interpretar("house 124 bpm em camelot 8A")["tecnico"])
        self.assertFalse(mf.interpretar("música calma")["tecnico"])


class BuscaTests(unittest.TestCase):
    def test_calma_noite_traz_faixas_calmas(self):
        r = mf.buscar(CAT, mf.interpretar("música calma para estudar à noite"))
        self.assertTrue(r)
        self.assertTrue(all(f["energia"] < 0.5 for f in r[:5]))

    def test_treino_traz_faixas_agitadas(self):
        r = mf.buscar(CAT, mf.interpretar("treino pesado"))
        self.assertTrue(all(f["bpm"] >= 110 for f in r[:5]))

    def test_resultados_ordenados(self):
        r = mf.buscar(CAT, mf.interpretar("festa animada para dançar"))
        self.assertEqual([f["vibe"] for f in r], sorted((f["vibe"] for f in r), reverse=True))


class CatalogoTests(unittest.TestCase):
    def test_catalogo_so_tem_metadados_validos(self):
        from soulsbpm import dj
        ids = set()
        for f in CAT:
            dj.parse_key(f["tom"])
            self.assertNotIn(f["id"], ids)
            ids.add(f["id"])
            self.assertTrue(40 <= f["bpm"] <= 200)
            self.assertTrue(0 <= f["energia"] <= 1)
            self.assertFalse(any(k in f for k in ("audio", "arquivo", "mp3", "url")))   # sem áudio


if __name__ == "__main__":
    unittest.main()
