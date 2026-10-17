"""Aprendizado dos pesos da nota: regressão logística, mistura com o ajuste manual e integração com o motor."""
import json
import pathlib
import random
import unittest

from app import create_app
from soulsbpm import aprendizado as ap
from soulsbpm import dj
from soulsbpm.aprendizado import Aprendizado
from soulsbpm.engine import Motor
from soulsbpm.store import Store

CATALOGO = str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json")


def dados_sinteticos(n=400, verdadeiros=(0.0, 4.0, 0.0, 0.0), seed=1):
    """Exemplos em que só o 2º critério (BPM) decide se a pessoa aceita."""
    rng = random.Random(seed)
    X, y = [], []
    for _ in range(n):
        x = [rng.random() for _ in range(4)]
        z = -2.0 + sum(c * v for c, v in zip(verdadeiros, x))
        p = 1 / (1 + 2.718281828 ** -z)
        X.append(x)
        y.append(1 if rng.random() < p else 0)
    return X, y


class TestRegressao(unittest.TestCase):
    def test_descobre_qual_criterio_importa(self):
        X, y = dados_sinteticos()
        coef = ap.regressao_logistica(X, y, [1.0] * len(y))
        self.assertEqual(max(range(4), key=lambda i: coef[i + 1]), 1)
        pesos = ap.pesos_do_modelo(coef)
        self.assertAlmostEqual(sum(pesos), 1.0)
        self.assertGreater(pesos[1], 0.7)

    def test_sem_sinal_nenhum_nao_inventa_pesos_extremos(self):
        rng = random.Random(3)
        X = [[rng.random() for _ in range(4)] for _ in range(300)]
        y = [rng.randint(0, 1) for _ in X]
        pesos = ap.pesos_do_modelo(ap.regressao_logistica(X, y, [1.0] * 300))
        if pesos is not None:                                  # ruído puro: nenhum critério domina
            self.assertLess(max(pesos), 0.9)

    def test_peso_negativo_vira_zero_e_tudo_negativo_devolve_none(self):
        pesos = ap.pesos_do_modelo([0.0, -1.0, 2.0, 0.0, 2.0])
        self.assertEqual(pesos, (0.0, 0.5, 0.0, 0.5))
        self.assertIsNone(ap.pesos_do_modelo([0.0, -1.0, -2.0, -0.5, -3.0]))

    def test_resolver_sistema_e_matriz_singular(self):
        self.assertEqual([round(v, 6) for v in ap._resolver([[2, 0], [0, 4]], [2, 8])], [1.0, 2.0])
        self.assertIsNone(ap._resolver([[1, 2], [2, 4]], [1, 2]))

    def test_pesos_por_exemplo_importam(self):
        X, y = dados_sinteticos(200)
        a = ap.regressao_logistica(X, y, [1.0] * 200)
        b = ap.regressao_logistica(X, y, [0.1] * 200)
        self.assertNotEqual([round(v, 3) for v in a], [round(v, 3) for v in b])


class TestMistura(unittest.TestCase):
    def test_poucos_exemplos_ficam_perto_do_manual_e_muitos_perto_do_modelo(self):
        modelo = (0.0, 1.0, 0.0, 0.0)
        pouco = ap.misturar(modelo, ap.PRIOR, 20)
        muito = ap.misturar(modelo, ap.PRIOR, 5000)
        self.assertLess(pouco[1] - ap.PRIOR[1], 0.15)
        self.assertGreater(muito[1], 0.9)
        for m in (pouco, muito):
            self.assertAlmostEqual(sum(m), 1.0)
            self.assertTrue(all(x >= 0 for x in m))

    def test_prior_soma_um(self):
        self.assertAlmostEqual(sum(ap.PRIOR), 1.0)


class TestAprendizado(unittest.TestCase):
    def novo(self, **kw):
        return Aprendizado(Store(":memory:"), em_segundo_plano=False, **kw)

    def alimentar(self, a, n_pos, n_neg):
        rng = random.Random(7)
        for i in range(n_pos):                                  # quem aceita tem BPM bom
            a.registrar("u1", "accept", "p", f"c{i}", {"vibe": rng.random(), "bpm": 0.8 + 0.2 * rng.random(),
                                                       "tom": rng.random(), "energia": rng.random()}, 1)
        for i in range(n_neg):                                  # quem pula tem BPM ruim
            a.registrar("u1", "skip_early", "p", f"d{i}", {"vibe": rng.random(), "bpm": 0.2 * rng.random(),
                                                           "tom": rng.random(), "energia": rng.random()}, 0)

    def test_comeca_sem_pesos_e_usa_o_manual(self):
        a = self.novo()
        self.assertIsNone(a.pesos())
        e = a.estado()
        self.assertFalse(e["em_uso"])
        self.assertEqual(e["pesos_em_uso"], e["pesos_manuais"])

    def test_nao_treina_sem_exemplos_suficientes_nem_com_uma_classe_so(self):
        a = self.novo(retreina_a_cada=5)
        self.alimentar(a, 30, 3)                                # 33 exemplos, só 3 pulos
        a.treinar()
        self.assertIsNone(a.pesos())
        self.assertEqual(a.estado()["negativas"], 3)

    def test_aprende_que_o_bpm_importa_e_mistura_com_o_manual(self):
        a = self.novo(retreina_a_cada=10)
        self.alimentar(a, 40, 40)
        pesos = a.pesos()
        self.assertIsNotNone(pesos)
        self.assertAlmostEqual(sum(pesos), 1.0)
        self.assertGreater(pesos[1], ap.PRIOR[1])               # BPM subiu em relação ao manual
        self.assertEqual(max(range(4), key=lambda i: pesos[i] - ap.PRIOR[i]), 1)
        e = a.estado()
        self.assertTrue(e["em_uso"] and e["amostras"] == 80)
        self.assertGreater(e["do_modelo"]["bpm"], e["pesos_em_uso"]["bpm"] - 1e-9)   # o modelo puro vai mais longe

    def test_retreina_sozinho_a_cada_n_registros(self):
        a = self.novo(retreina_a_cada=10)
        self.alimentar(a, 20, 20)
        self.assertIsNotNone(a.pesos())

    def test_ignora_usuario_anonimo_e_tipo_desconhecido(self):
        a = self.novo()
        a.registrar(None, "accept", "p", "c", {"vibe": .5, "bpm": .5, "tom": .5, "energia": .5}, 1)
        a.registrar("u1", "inventado", "p", "c", {"vibe": .5, "bpm": .5, "tom": .5, "energia": .5}, 1)
        self.assertEqual(a.store.transicoes(10), [])

    def test_remover_apaga_so_o_registro_mais_recente_igual(self):
        a = self.novo()
        x = {"vibe": .5, "bpm": .5, "tom": .5, "energia": .5}
        a.registrar("u1", "accept", "p", "c", x, 1)
        a.registrar("u1", "accept", "p", "c", x, 1)
        a.remover("u1", "accept", "p", "c")
        self.assertEqual(len(a.store.transicoes(10)), 1)

    def test_apagar_historico_ou_perfil_apaga_os_exemplos_da_pessoa(self):
        a = self.novo()
        x = {"vibe": .5, "bpm": .5, "tom": .5, "energia": .5}
        a.registrar("u1", "accept", "p", "c", x, 1)
        a.registrar("u2", "accept", "p", "c", x, 1)
        a.store.delete_history("u1")
        self.assertEqual(len(a.store.transicoes(10)), 1)
        a.store.reset_profile("u2")
        self.assertEqual(a.store.transicoes(10), [])

    def test_retoma_o_treino_ao_reiniciar_com_o_mesmo_banco(self):
        a = self.novo(retreina_a_cada=10)
        self.alimentar(a, 40, 40)
        b = Aprendizado(a.store, em_segundo_plano=False)
        self.assertIsNotNone(b.pesos())


class TestRankingComPesos(unittest.TestCase):
    def faixa(self, i, bpm, tom, en):
        return {"id": i, "bpm": bpm, "tom": tom, "energia": en, "generos": [], "tags": []}

    def test_pesos_mudam_a_ordem_quando_o_criterio_muda(self):
        prev = self.faixa("p", 100, "8A", 0.5)
        bom_bpm = self.faixa("a", 100, "3B", 0.5)               # BPM perfeito, tom distante
        bom_tom = self.faixa("b", 104, "8A", 0.5)               # BPM mais longe, tom igual
        so_tom = dj.rank_next(prev, [bom_bpm, bom_tom], lambda f: 0.0, pesos=(0.0, 0.0, 1.0, 0.0))
        so_bpm = dj.rank_next(prev, [bom_bpm, bom_tom], lambda f: 0.0, pesos=(0.0, 1.0, 0.0, 0.0))
        self.assertEqual(so_tom[0]["faixa"]["id"], "b")
        self.assertEqual(so_bpm[0]["faixa"]["id"], "a")

    def test_sem_pesos_vale_a_formula_original(self):
        prev = self.faixa("p", 100, "8A", 0.5)
        c = [self.faixa("a", 100, "3B", 0.5), self.faixa("b", 104, "8A", 0.6)]
        igual = dj.rank_next(prev, c, lambda f: 0.5)
        explicito = dj.rank_next(prev, c, lambda f: 0.5, pesos=(dj.W_VIBE, dj.W_BPM, dj.W_KEY, dj.W_ENERGY))
        self.assertEqual([x["nota"] for x in igual], [x["nota"] for x in explicito])

    def test_com_bpm_alvo_os_pesos_aprendidos_nao_entram(self):
        prev = self.faixa("p", 100, "8A", 0.5)
        c = [self.faixa("a", 110, "3B", 0.5), self.faixa("b", 104, "8A", 0.6)]
        a = dj.rank_next(prev, c, lambda f: 0.5, alvo=120)
        b = dj.rank_next(prev, c, lambda f: 0.5, alvo=120, pesos=(0.0, 0.0, 1.0, 0.0))
        self.assertEqual([x["nota"] for x in a], [x["nota"] for x in b])


class TestNoMotor(unittest.TestCase):
    def setUp(self):
        self.app = create_app(":memory:", catalog_path=CATALOGO)
        self.app.motor.aprendizado.em_segundo_plano = False
        self.c = self.app.test_client()

    def post(self, url, **b):
        return self.c.post(url, json={"user_id": "u_teste", **b})

    def tocar(self):
        r = self.post("/api/search", text="música calma para estudar à noite").get_json()
        sid = r["session_id"]
        self.post(f"/api/session/{sid}/play", track_id=r["resultados"][0]["id"])
        return sid

    def n(self):
        return len(self.app.store.transicoes(1000))

    def test_aceitar_e_pular_viram_exemplos_e_desfazer_apaga(self):
        sid = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        self.assertEqual(self.n(), 1)
        self.post(f"/api/session/{sid}/undo-accept")
        self.assertEqual(self.n(), 0)
        self.post(f"/api/session/{sid}/accept")
        self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.1)
        self.assertEqual(self.n(), 2)
        y = [r[4] for r in self.app.store.transicoes(10)]
        self.assertEqual(sorted(y), [0, 1])
        self.post(f"/api/session/{sid}/back")                   # voltar desfaz o pulo
        self.assertEqual(self.n(), 1)

    def test_curtir_e_descurtir(self):
        sid = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        self.post(f"/api/session/{sid}/like")
        self.assertEqual(self.n(), 2)
        self.post(f"/api/session/{sid}/like")
        self.assertEqual(self.n(), 1)

    def test_com_bpm_alvo_nao_registra(self):
        sid = self.tocar()
        self.post(f"/api/session/{sid}/bpm", delta=5)
        self.post(f"/api/session/{sid}/accept")
        self.assertEqual(self.n(), 0)

    def test_usuario_anonimo_nao_gera_exemplos(self):
        r = self.c.post("/api/search", json={"text": "música calma para estudar à noite"}).get_json()
        sid = r["session_id"]
        self.c.post(f"/api/session/{sid}/play", json={"track_id": r["resultados"][0]["id"]})
        self.c.post(f"/api/session/{sid}/accept", json={})
        self.assertEqual(self.n(), 0)

    def test_falha_no_aprendizado_nao_atrapalha_quem_ouve(self):
        def quebrado(*a, **k):
            raise RuntimeError("banco fora")
        self.app.motor.aprendizado.registrar = quebrado
        sid = self.tocar()
        self.assertEqual(self.post(f"/api/session/{sid}/accept").status_code, 200)

    def test_pode_ser_desligado_por_ambiente(self):
        import os
        os.environ["SOULSBPM_APRENDER"] = "0"
        try:
            app = create_app(":memory:", catalog_path=CATALOGO)
        finally:
            del os.environ["SOULSBPM_APRENDER"]
        self.assertIsNone(app.aprendizado)
        j = app.test_client().get("/api/modelo").get_json()
        self.assertFalse(j["recursos"]["aprende_pesos"])
        self.assertIsNone(j["aprendizado"])

    def test_endpoint_modelo_mostra_os_pesos(self):
        j = self.c.get("/api/modelo").get_json()
        self.assertTrue(j["recursos"]["aprende_pesos"])
        self.assertFalse(j["recursos"]["sugere_artistas"])
        self.assertEqual(j["aprendizado"]["pesos_manuais"], {"vibe": 0.35, "bpm": 0.25, "tom": 0.25, "energia": 0.15})


if __name__ == "__main__":
    unittest.main()
