"""Explicação em linguagem simples (modo comum) e texto das regras sem o "bPM" quebrado."""
import pathlib
import unittest
from unittest import mock

from app import create_app
from soulsbpm.narrador import Narrador, texto_das_regras, texto_simples

CATALOGO = str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json")
A = {"id": "a", "titulo": "Corpo e Som", "artista": "X", "bpm": 120, "tom": "8A", "energia": 0.8}
B = {"id": "b", "titulo": "Pista Cheia", "artista": "Y", "bpm": 121, "tom": "9A", "energia": 0.82}
TEC = {"bpm": 0.95, "tom": 0.9, "energia": 0.98, "percentual": 93}


class IAFalsa:
    def __init__(self, resposta):
        self.resposta, self.pedidos = resposta, []

    def completar(self, sistema, usuario, max_tokens=400, temperatura=0.0):
        self.pedidos.append((sistema, usuario))
        return self.resposta


class TestTextoSimples(unittest.TestCase):
    def test_regras_nao_quebram_a_sigla_bpm(self):
        t = texto_das_regras(A, B, ["BPM 120 → 121 (+0,8%)", "Chave compatível (8A → 9A)"])
        self.assertIn("BPM 120", t)
        self.assertNotIn("bPM", t)
        self.assertIn("chave compatível", t)

    def test_texto_simples_sem_jargao_nem_numeros(self):
        t = texto_simples(A, B, TEC, vibe=0.8)
        for proibido in ("BPM", "bpm", "Camelot", "chave", "tom ", "%", "8A", "120"):
            self.assertNotIn(proibido, t)
        self.assertIn("ritmo é parecido", t)
        self.assertIn("Pista Cheia", t)

    def test_sem_nada_em_comum_ainda_explica(self):
        t = texto_simples(A, B, {"bpm": 0, "tom": 0.3, "energia": 0.2, "percentual": 20}, vibe=0.1)
        self.assertIn("mais parecida", t)


class TestNarradorSimples(unittest.TestCase):
    def test_ia_recebe_o_pedido_simples_sem_numeros(self):
        ia = IAFalsa("As duas têm um ritmo parecido e deixam o clima da festa.")
        r = Narrador(ia).explicar(A, B, TEC, ["BPM 120 → 121"], "festa", None, simples=True, vibe=0.8)
        self.assertEqual(r["origem"], "ia")
        sistema, fatos = ia.pedidos[0]
        self.assertIn("NÃO é DJ", sistema)
        self.assertNotRegex(fatos, r"\d{2,}")                      # nenhum BPM nos fatos
        self.assertNotIn("8A", fatos)

    def test_se_a_ia_usar_jargao_vale_o_texto_das_regras(self):
        ia = IAFalsa("As duas estão em 120 BPM e na mesma chave Camelot, combina bem.")
        r = Narrador(ia).explicar(A, B, TEC, [], None, None, simples=True, vibe=0.8)
        self.assertEqual(r["origem"], "regras")
        self.assertNotIn("BPM", r["texto"])

    def test_cache_separa_simples_de_tecnico(self):
        ia = IAFalsa("Uma frase longa o bastante para passar na validação do texto.")
        n = Narrador(ia)
        n.explicar(A, B, TEC, [], None, None, simples=False)
        n.explicar(A, B, TEC, [], None, None, simples=True)
        self.assertEqual(len(ia.pedidos), 2)


class TestRotaExplicar(unittest.TestCase):
    def test_flag_simples_chega_ao_motor(self):
        app = create_app(":memory:", catalog_path=CATALOGO)
        c = app.test_client()
        r = c.post("/api/search", json={"text": "festa animada para dançar"}).get_json()
        sid = r["session_id"]
        c.post(f"/api/session/{sid}/play", json={"track_id": r["resultados"][0]["id"]})
        tecnico = c.post(f"/api/session/{sid}/explain", json={}).get_json()["texto"]
        simples = c.post(f"/api/session/{sid}/explain", json={"simples": True}).get_json()["texto"]
        self.assertRegex(tecnico, r"BPM")
        self.assertNotRegex(simples, r"BPM|chave|\d%")


if __name__ == "__main__":
    unittest.main()
