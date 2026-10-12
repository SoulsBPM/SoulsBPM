import json
import unittest
import urllib.error

from soulsbpm import llm, musicfinder as mf


def resposta(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}]}


class HttpFalso:
    def __init__(self, respostas):
        self.respostas, self.chamadas = list(respostas), []

    def __call__(self, corpo, chave, timeout):
        self.chamadas.append(corpo)
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(r, Exception):
            raise r
        return r


OK = {"clara": True, "tags": {"triste": 3, "chuva": 1}, "energia": 0.3, "generos": ["indie"], "tecnico": False}


class TestValidar(unittest.TestCase):
    def test_aceita_resposta_boa(self):
        r = llm.validar(OK)
        self.assertTrue(r["clara"])
        self.assertEqual(r["tags"], {"triste": 3, "chuva": 1})
        self.assertEqual(r["generos"], ["indie"])

    def test_descarta_tags_e_generos_desconhecidos(self):
        r = llm.validar({"clara": True, "tags": {"hackear": 3, "calma": 2}, "energia": 0.2, "generos": ["xyz", "jazz"]})
        self.assertEqual(r["tags"], {"calma": 2})
        self.assertEqual(r["generos"], ["jazz"])

    def test_energia_fica_entre_limites_e_pesos_entre_1_e_3(self):
        r = llm.validar({"clara": True, "tags": {"calma": 99}, "energia": 7})
        self.assertEqual(r["energia"], 0.95)
        self.assertEqual(r["tags"]["calma"], 3)

    def test_sem_nada_util_vira_nao_clara(self):
        r = llm.validar({"clara": True, "tags": {"inventada": 2}, "generos": ["nada"], "energia": None})
        self.assertFalse(r["clara"])

    def test_lixo_devolve_none(self):
        self.assertIsNone(llm.validar("texto"))
        self.assertIsNone(llm.validar(None))


class TestInterpretador(unittest.TestCase):
    def test_chama_modelo_e_devolve_validado(self):
        http = HttpFalso([resposta(OK)])
        ia = llm.InterpretadorIA("k", http=http)
        r = ia("música pra chorar no ônibus")
        self.assertEqual(r["tags"]["triste"], 3)
        corpo = http.chamadas[0]
        self.assertEqual(corpo["model"], llm.MODELO_PADRAO)
        self.assertIn("<vibe>música pra chorar no ônibus</vibe>", corpo["messages"][0]["content"])

    def test_aceita_json_cercado_de_texto(self):
        http = HttpFalso([{"content": [{"type": "text", "text": "Claro! " + json.dumps(OK) + " pronto"}]}])
        self.assertTrue(llm.InterpretadorIA("k", http=http)("triste")["clara"])

    def test_cache_evita_segunda_chamada(self):
        http = HttpFalso([resposta(OK)])
        ia = llm.InterpretadorIA("k", http=http)
        ia("Música TRISTE"); ia("musica triste")
        self.assertEqual(len(http.chamadas), 1)

    def test_falha_de_rede_devolve_none(self):
        ia = llm.InterpretadorIA("k", http=HttpFalso([urllib.error.URLError("sem rede")]))
        self.assertIsNone(ia("triste"))

    def test_erro_http_devolve_none(self):
        err = urllib.error.HTTPError("u", 401, "x", {}, None)
        self.assertIsNone(llm.InterpretadorIA("k", http=HttpFalso([err]))("triste"))

    def test_resposta_invalida_devolve_none(self):
        http = HttpFalso([{"content": [{"type": "text", "text": "não sei"}]}])
        self.assertIsNone(llm.InterpretadorIA("k", http=http)("triste"))

    def test_pausa_depois_de_varias_falhas(self):
        t = [1000.0]
        http = HttpFalso([RuntimeError("x")])
        ia = llm.InterpretadorIA("k", http=http, falhas_max=2, pausa=60, agora=lambda: t[0])
        ia("a"); ia("b")                       # 2 falhas → pausa
        n = len(http.chamadas)
        self.assertIsNone(ia("c"))
        self.assertEqual(len(http.chamadas), n)   # nem tentou
        t[0] += 61
        ia("d")
        self.assertEqual(len(http.chamadas), n + 1)

    def test_exige_chave(self):
        with self.assertRaises(ValueError):
            llm.InterpretadorIA("")


class TestProvedoresGratuitos(unittest.TestCase):
    def test_formato_openai_monta_system_e_le_choices(self):
        http = HttpFalso([{"choices": [{"message": {"content": json.dumps(OK)}}]}])
        ia = llm.InterpretadorIA("k", http=http, provedor="gemini")
        r = ia("triste")
        self.assertEqual(r["tags"]["triste"], 3)
        msgs = http.chamadas[0]["messages"]
        self.assertEqual([m["role"] for m in msgs], ["system", "user"])
        self.assertNotIn("system", http.chamadas[0])
        self.assertEqual(ia.url, llm.PROVEDORES["gemini"][2])

    def test_modelo_pode_ser_trocado(self):
        ia = llm.InterpretadorIA("k", modelo="outro-modelo", provedor="groq")
        self.assertEqual(ia.modelo, "outro-modelo")

    def test_provedor_desconhecido(self):
        with self.assertRaises(ValueError):
            llm.InterpretadorIA("k", provedor="xyz")

    def test_do_ambiente_sem_chave_devolve_none(self):
        self.assertIsNone(llm.do_ambiente({}))

    def test_do_ambiente_escolhe_pelo_que_existe(self):
        self.assertEqual(llm.do_ambiente({"GROQ_API_KEY": "k"}).provedor, "groq")
        self.assertEqual(llm.do_ambiente({"GEMINI_API_KEY": "k", "GROQ_API_KEY": "k"}).provedor, "gemini")
        self.assertEqual(llm.do_ambiente({"ANTHROPIC_API_KEY": "k"}).provedor, "anthropic")

    def test_do_ambiente_respeita_provedor_escolhido_e_modelo(self):
        env = {"GEMINI_API_KEY": "k", "GROQ_API_KEY": "k", "SOULSBPM_IA_PROVEDOR": "groq", "SOULSBPM_MODELO_IA": "m1"}
        ia = llm.do_ambiente(env)
        self.assertEqual((ia.provedor, ia.modelo), ("groq", "m1"))

    def test_nome_da_ia_no_musicfinder(self):
        mf.configurar_ia(llm.InterpretadorIA("k", provedor="gemini"))
        self.assertTrue(mf.ia_nome().startswith("gemini/"))
        mf.configurar_ia(None)
        self.assertIsNone(mf.ia_nome())


class TestMusicFinderComIA(unittest.TestCase):
    def tearDown(self):
        mf.configurar_ia(None)

    def test_sem_ia_continua_no_lexico(self):
        self.assertFalse(mf.ia_ativa())
        self.assertNotIn("origem", mf.interpretar("música calma para estudar à noite"))

    def test_usa_a_ia_quando_ligada(self):
        mf.configurar_ia(llm.InterpretadorIA("k", http=HttpFalso([resposta(OK)])))
        i = mf.interpretar("frase que o léxico não conhece")
        self.assertEqual(i["origem"], "ia")
        self.assertTrue(i["clara"])
        self.assertEqual(i["energia"], 0.3)
        self.assertIn("triste", i["resumo"])

    def test_se_ia_falha_cai_no_lexico(self):
        mf.configurar_ia(llm.InterpretadorIA("k", http=HttpFalso([RuntimeError("x")])))
        i = mf.interpretar("música calma para estudar à noite")
        self.assertTrue(i["clara"])
        self.assertNotIn("origem", i)

    def test_se_ia_nao_entende_vale_o_lexico(self):
        nao = {"clara": False, "tags": {}, "energia": None, "generos": [], "tecnico": False}
        mf.configurar_ia(llm.InterpretadorIA("k", http=HttpFalso([resposta(nao)])))
        self.assertTrue(mf.interpretar("treino pesado")["clara"])
        self.assertFalse(mf.interpretar("asdf qwer zzz")["clara"])


if __name__ == "__main__":
    unittest.main()
