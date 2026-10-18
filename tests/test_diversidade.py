"""Variedade nos resultados: no máximo 3 músicas do mesmo artista no topo."""
import unittest

from soulsbpm import musicfinder


def faixas(*artistas):
    return [{"id": f"x{i}", "artista": a, "titulo": f"t{i}"} for i, a in enumerate(artistas)]


class TestDiversificar(unittest.TestCase):
    def test_limita_por_artista_mantendo_a_ordem(self):
        fx = faixas(*["A"] * 6 + ["B"] * 3 + ["C"] * 3)
        r = musicfinder.diversificar(fx, limite=9, max_por_artista=3)
        self.assertEqual([f["artista"] for f in r], ["A"] * 3 + ["B"] * 3 + ["C"] * 3)

    def test_nao_encolhe_quando_faltam_artistas(self):
        fx = faixas(*["A"] * 6 + ["B"] * 2)
        r = musicfinder.diversificar(fx, limite=8, max_por_artista=3)
        self.assertEqual(len(r), 8)
        self.assertEqual([f["artista"] for f in r[:5]], ["A", "A", "A", "B", "B"])   # variados primeiro, sobras depois

    def test_ignora_maiusculas_e_espacos_no_nome(self):
        r = musicfinder.diversificar(faixas("Norah Jones", "norah jones ", "NORAH JONES", "Norah Jones", "Outro"),
                                     limite=4, max_por_artista=3)
        self.assertEqual(r[3]["artista"], "Outro")

    def test_respeita_o_limite(self):
        self.assertEqual(len(musicfinder.diversificar(faixas(*"ABCDEFGHIJKL"), limite=10)), 10)


if __name__ == "__main__":
    unittest.main()
