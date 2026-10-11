import unittest
from soulsbpm import dj


def f(id_, bpm, tom, en, gens=("pop",), tags=("feliz",)):
    return dict(id=id_, bpm=bpm, tom=tom, energia=en, generos=list(gens), tags=list(tags), titulo=id_, artista="x", duracao=200)


class BpmTests(unittest.TestCase):
    def test_igual_vale_um(self):
        self.assertEqual(dj.bpm_score(120, 120), 1.0)

    def test_cai_ate_zero_em_5_por_cento(self):
        self.assertAlmostEqual(dj.bpm_score(100, 102.5), 0.5)
        self.assertEqual(dj.bpm_score(100, 105), 0.0)
        self.assertEqual(dj.bpm_score(100, 120), 0.0)

    def test_meio_tempo_e_dobro(self):
        self.assertEqual(dj.bpm_score(70, 140), 1.0)
        self.assertEqual(dj.bpm_score(140, 70), 1.0)


class KeyTests(unittest.TestCase):
    def test_mesma_chave(self):
        self.assertEqual(dj.key_score("8A", "8A"), 1.0)

    def test_vizinha_e_relativa(self):
        self.assertEqual(dj.key_score("8A", "9A"), 0.9)
        self.assertEqual(dj.key_score("8A", "7A"), 0.9)
        self.assertEqual(dj.key_score("8A", "8B"), 0.9)

    def test_circular_12_para_1(self):
        self.assertEqual(dj.key_score("12A", "1A"), 0.9)

    def test_demais(self):
        self.assertEqual(dj.key_score("8A", "3B"), 0.3)
        self.assertEqual(dj.key_score("8A", "9B"), 0.3)   # número vizinho mas letra diferente

    def test_tom_invalido(self):
        with self.assertRaises(ValueError):
            dj.key_score("13A", "8A")


class NotaTests(unittest.TestCase):
    def test_pesos_da_formula(self):
        a, b = f("a", 120, "8A", .5), f("b", 120, "8A", .5)
        self.assertAlmostEqual(dj.nota(a, b, 1.0), 1.0)
        c = f("c", 200, "3B", .0)       # BPM 0, tom 0,3, energia 0,5
        self.assertAlmostEqual(dj.nota(a, c, 0.0), 0.25 * 0.3 + 0.15 * 0.5)

    def test_percentual_tecnico_ignora_vibe(self):
        a, b = f("a", 120, "8A", .5), f("b", 120, "8A", .5)
        self.assertEqual(dj.technical(a, b)["percentual"], 100)

    def test_ajuste_do_perfil_e_limitado(self):
        self.assertLessEqual(dj.ajuste_perfil(1000), dj.PROFILE_RANGE)
        self.assertGreaterEqual(dj.ajuste_perfil(-1000), -dj.PROFILE_RANGE)
        self.assertEqual(dj.ajuste_perfil(0), 0)


class RankingTests(unittest.TestCase):
    def test_prefere_faixa_compativel(self):
        a = f("a", 120, "8A", .6)
        bom, ruim = f("bom", 121, "9A", .6), f("ruim", 90, "3B", .2)
        r = dj.rank_next(a, [ruim, bom], lambda c: 0.8)
        self.assertEqual(r[0]["faixa"]["id"], "bom")
        self.assertEqual(r[0]["classe"], "combina_bem")

    def test_d2_sem_compativel_marca_arriscada(self):
        a = f("a", 120, "8A", .6)
        r = dj.rank_next(a, [f("x", 90, "3B", .2)], lambda c: 1.0)
        self.assertEqual(r[0]["classe"], "arriscada")

    def test_perfil_reordena(self):
        a = f("a", 120, "8A", .6)
        x, y = f("x", 120, "8A", .6), f("y", 120, "8A", .6)
        r = dj.rank_next(a, [x, y], lambda c: .5, lambda p, c: 3.0 if c["id"] == "y" else 0.0)
        self.assertEqual(r[0]["faixa"]["id"], "y")


class RumoTests(unittest.TestCase):
    def test_pesos_com_alvo_somam_um(self):
        self.assertAlmostEqual(sum(dj.W_ALVO.values()) + dj.W_RUMO, 1.0)

    def test_rumo_premia_quem_aproxima_do_alvo(self):
        self.assertEqual(dj.rumo_score(90, 110, 110), 1.0)
        self.assertGreater(dj.rumo_score(90, 100, 110), dj.rumo_score(90, 94, 110))
        self.assertEqual(dj.rumo_score(90, 90, 110), 0.5)          # não muda: neutro
        self.assertLess(dj.rumo_score(90, 80, 110), 0.5)           # afasta: abaixo do neutro

    def test_rumo_perto_do_alvo_mantem_o_ritmo(self):
        self.assertEqual(dj.rumo_score(110, 110, 110), 1.0)
        self.assertLess(dj.rumo_score(110, 120, 110), dj.rumo_score(110, 111, 110))

    def test_alvo_acima_prefere_faixa_mais_rapida(self):
        a = f("a", 100, "8A", .5)
        lenta, rapida = f("lenta", 97, "8A", .5), f("rapida", 104, "8A", .5)
        sem = dj.rank_next(a, [lenta, rapida], lambda c: .5)
        com = dj.rank_next(a, [lenta, rapida], lambda c: .5, alvo=120)
        self.assertEqual(com[0]["faixa"]["id"], "rapida")
        self.assertIsNone(sem[0]["rumo"])
        self.assertGreater(com[0]["rumo"], com[1]["rumo"])

    def test_alvo_abaixo_prefere_faixa_mais_lenta(self):
        a = f("a", 100, "8A", .5)
        r = dj.rank_next(a, [f("lenta", 96, "8A", .5), f("rapida", 104, "8A", .5)], lambda c: .5, alvo=80)
        self.assertEqual(r[0]["faixa"]["id"], "lenta")

    def test_com_alvo_meio_tempo_nao_conta_como_transicao(self):
        a, b = f("a", 130, "5A", .9), f("b", 65, "5A", .9)
        self.assertEqual(dj.technical(a, b)["bpm"], 1.0)
        self.assertEqual(dj.technical(a, b, meio_dobro=False)["bpm"], 0.0)
        r = dj.rank_next(a, [b, f("c", 124, "5A", .9)], lambda c: .5, alvo=98)
        self.assertEqual(r[0]["faixa"]["id"], "c")

    def test_perfil_pesa_menos_com_alvo(self):
        a = f("a", 100, "8A", .5)
        x, y = f("x", 104, "8A", .5), f("y", 96, "8A", .5)
        favorece_y = lambda p, c: 3.0 if c["id"] == "y" else 0.0
        self.assertEqual(dj.rank_next(a, [x, y], lambda c: .5, favorece_y)[0]["faixa"]["id"], "y")
        self.assertEqual(dj.rank_next(a, [x, y], lambda c: .5, favorece_y, alvo=120)[0]["faixa"]["id"], "x")

    def test_motivos_explicam_a_escolha(self):
        a, b = f("a", 100, "8A", .5), f("b", 104, "9A", .5)
        r = dj.rank_next(a, [b], lambda c: .8, alvo=120)[0]
        txt = " | ".join(r["motivos"])
        self.assertIn("100 → 104", txt)
        self.assertIn("chave compatível (8A → 9A)", txt)
        self.assertIn("sobe em direção ao alvo de 120 BPM", txt)
        self.assertIn("combina com a vibe", txt)


if __name__ == "__main__":
    unittest.main()
