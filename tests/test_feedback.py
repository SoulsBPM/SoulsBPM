import unittest
from soulsbpm import feedback as fb
from soulsbpm.store import Store

DIA = 86400.0


def f(id_, bpm=120, tom="8A", en=.5, gens=("pop",)):
    return dict(id=id_, bpm=bpm, tom=tom, energia=en, generos=list(gens), tags=["feliz"], titulo=id_, artista="x", duracao=200)


class Relogio:
    def __init__(self): self.t = 1_000_000.0
    def __call__(self): return self.t


class PesosTests(unittest.TestCase):
    def test_valores_do_documento(self):
        self.assertEqual(fb.DELTAS, {"like": 1.0, "save": 1.5, "accept": 0.5, "skip_late": -0.3, "skip_early": -1.0})

    def test_pulo_antes_ou_depois_da_metade(self):
        self.assertEqual(fb.tipo_pulo(0.49), "skip_early")
        self.assertEqual(fb.tipo_pulo(0.5), "skip_late")

    def test_usuario_novo_comeca_neutro(self):
        p = fb.Perfil(Store(), "novo")
        self.assertEqual(p.peso("genre:pop"), 0.0)
        self.assertEqual(p.bonus(None, f("a"), ["feliz"]), 0.0)

    def test_curtir_soma_no_genero(self):
        s, p = Store(), None
        p = fb.Perfil(s, "u")
        fb.registrar_positivo(p, "like", f("a", gens=("rock",)), None)
        self.assertAlmostEqual(p.peso("genre:rock"), 1.0)

    def test_persistencia(self):
        s = Store()
        fb.registrar_positivo(fb.Perfil(s, "u"), "save", f("a", gens=("rock",)), f("b"))
        self.assertAlmostEqual(fb.Perfil(s, "u").peso("genre:rock"), 1.5)

    def test_sem_usuario_nao_grava(self):
        s = Store()
        fb.registrar_positivo(fb.Perfil(s, None), "like", f("a"), None)
        self.assertEqual(s.get_weights(None), {})

    def test_decaimento_meia_vida(self):
        s, rel = Store(), Relogio()
        p = fb.Perfil(s, "u", rel)
        p.somar("genre:rock", 2.0)
        rel.t += fb.HALF_LIFE_DAYS * DIA
        self.assertAlmostEqual(fb.Perfil(s, "u", rel).peso("genre:rock"), 1.0, places=3)

    def test_limite_dos_pesos(self):
        p = fb.Perfil(Store(), "u")
        for _ in range(50):
            p.somar("genre:rock", 1.0)
        self.assertAlmostEqual(p.peso("genre:rock"), fb.CLAMP, places=3)


class AtribuicaoDoPuloTests(unittest.TestCase):
    def test_baixa_compatibilidade_culpa_a_transicao(self):
        s = Store(); p = fb.Perfil(s, "u")
        r = fb.registrar_pulo(p, f("b"), f("a"), ["calma"], 0.2, tecnica_pct=30)
        self.assertEqual(r["causa"], "transicao")
        self.assertAlmostEqual(p.peso("pair:a>b"), -1.0)
        self.assertEqual(p.peso("assoc:calma|b"), 0.0)

    def test_alta_compatibilidade_culpa_a_vibe(self):
        s = Store(); p = fb.Perfil(s, "u")
        r = fb.registrar_pulo(p, f("b"), f("a"), ["calma", "noite"], 0.8, tecnica_pct=90)
        self.assertEqual(r["causa"], "vibe")
        self.assertAlmostEqual(p.peso("assoc:calma|b"), -0.3)
        self.assertAlmostEqual(p.peso("assoc:noite|b"), -0.3)
        self.assertEqual(p.peso("pair:a>b"), 0.0)

    def test_pulo_reduz_bonus_da_faixa(self):
        s = Store(); p = fb.Perfil(s, "u")
        fb.registrar_pulo(p, f("b"), f("a"), ["calma"], 0.1, tecnica_pct=95)
        self.assertLess(p.bonus(f("a"), f("b"), ["calma"]), 0)


class StoreTests(unittest.TestCase):
    def test_grafo_guarda_so_pares_e_conta(self):
        s = Store()
        s.save_playlist("u1", "x", ["calma"], ["a", "b", "c"])
        s.save_playlist("u2", "y", ["calma"], ["a", "b"])
        self.assertEqual(s.graph_count("a", "b"), 2)
        self.assertEqual(s.graph_count("b", "c"), 1)
        self.assertEqual({r[0] for r in s.graph_pairs()}, {"a", "b"})

    def test_apagar_historico(self):
        s = Store()
        s.add_history("u", "search", query="x")
        s.add_history("u", "skip", "t001", "x", 0.2)
        s.delete_history("u")
        self.assertEqual(s.history("u"), [])

    def test_sem_user_id_nao_guarda_historico(self):
        s = Store()
        s.add_history(None, "search", query="x")
        self.assertEqual(s.history(None), [])


if __name__ == "__main__":
    unittest.main()
