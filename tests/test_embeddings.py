"""Embeddings de vibe: similaridade semântica entre a frase e as faixas. Provedor simulado, sem rede."""
import pathlib
import unittest
import urllib.error

from app import create_app
from soulsbpm import embeddings as emb
from soulsbpm import musicfinder
from soulsbpm.embeddings import ClienteEmbeddings
from soulsbpm.engine import Motor
from soulsbpm.store import Store


def vetor(texto):
    """Vetor de brinquedo: 3 "assuntos" + um viés pequeno. Texto com a palavra do assunto liga a dimensão."""
    t = texto.lower()
    return [1.0 if "calma" in t else 0.0, 1.0 if "festa" in t else 0.0, 1.0 if "rock" in t else 0.0, 0.1]


class HttpEmb:
    def __init__(self, modo="ok"):
        self.modo, self.chamadas = modo, []

    def __call__(self, corpo, chave, timeout):
        self.chamadas.append(corpo)
        entrada = corpo["input"] if isinstance(corpo["input"], list) else [corpo["input"]]
        if self.modo == "erro":
            raise urllib.error.URLError("sem rede")
        if self.modo == "sem_lista" and len(entrada) > 1:
            raise urllib.error.HTTPError("u", 400, "input deve ser texto", {}, None)
        if self.modo == "resposta_curta" and len(entrada) > 1:
            entrada = entrada[:-1]                       # devolve um vetor a menos que o pedido
        if self.modo == "embaralhado":
            return {"data": [{"index": i, "embedding": vetor(t)} for i, t in reversed(list(enumerate(entrada)))]}
        return {"data": [{"index": i, "embedding": vetor(t)} for i, t in enumerate(entrada)]}


FAIXAS = [{"id": "a", "titulo": "Noite calma", "artista": "X"}, {"id": "b", "titulo": "Festa total", "artista": "Y"},
          {"id": "c", "titulo": "Rock pesado", "artista": "Z"}, {"id": "d", "titulo": "Domingo de calma", "artista": "W"}]


class TestMatematica(unittest.TestCase):
    def test_cosseno(self):
        self.assertAlmostEqual(emb.cosseno([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(emb.cosseno([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(emb.cosseno([1, 2], [-1, -2]), -1.0)
        self.assertEqual(emb.cosseno([0, 0], [1, 1]), 0.0)          # vetor nulo não divide por zero
        self.assertEqual(emb.cosseno([1, 2], [1, 2, 3]), 0.0)       # tamanhos diferentes

    def test_normalizar_centra_em_meio_e_mantem_a_ordem(self):
        n = emb.normalizar([0.2, 0.5, 0.8, 0.5])
        self.assertAlmostEqual(sum(n) / len(n), 0.5, places=2)
        self.assertEqual(n.index(max(n)), 2)
        self.assertEqual(n.index(min(n)), 0)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in n))

    def test_similaridades_quase_iguais_nao_viram_ruido(self):
        n = emb.normalizar([0.70, 0.7001, 0.6999])
        self.assertTrue(all(abs(x - 0.5) < 0.05 for x in n))


class TestCliente(unittest.TestCase):
    def test_pontua_as_faixas_mais_parecidas_com_a_frase(self):
        http = HttpEmb()
        notas = ClienteEmbeddings("k", http=http).pontuar("música calma", FAIXAS)
        self.assertGreater(notas["a"], 0.5)
        self.assertGreater(notas["d"], 0.5)
        self.assertLess(notas["b"], 0.5)
        self.assertLess(notas["c"], 0.5)
        self.assertEqual(len(http.chamadas), 1)                      # frase e faixas em um único pedido
        self.assertEqual(http.chamadas[0]["model"], "gemini-embedding-001")
        self.assertEqual(len(http.chamadas[0]["input"]), 5)

    def test_cache_evita_repetir_pedidos(self):
        http = HttpEmb()
        c = ClienteEmbeddings("k", http=http)
        c.pontuar("música calma", FAIXAS)
        c.pontuar("música calma", FAIXAS)
        self.assertEqual(len(http.chamadas), 1)
        c.pontuar("música calma", FAIXAS + [{"id": "e", "titulo": "Calma 2", "artista": "V"}])
        self.assertEqual(len(http.chamadas), 2)                      # só o texto novo foi pedido
        self.assertEqual(len(http.chamadas[1]["input"]), 1)

    def test_respeita_a_ordem_mesmo_com_resposta_embaralhada(self):
        notas = ClienteEmbeddings("k", http=HttpEmb("embaralhado")).pontuar("música calma", FAIXAS)
        self.assertGreater(notas["a"], notas["b"])

    def test_provedor_que_recusa_lista_cai_para_pedidos_avulsos(self):
        http = HttpEmb("sem_lista")
        c = ClienteEmbeddings("k", http=http)
        notas = c.pontuar("música calma", FAIXAS)
        self.assertGreater(notas["a"], notas["b"])
        self.assertFalse(c._lote_ok)
        self.assertEqual(sum(1 for x in http.chamadas if isinstance(x["input"], list) and len(x["input"]) == 1), 5)

    def test_resposta_com_numero_errado_de_vetores_cai_para_avulsos(self):
        notas = ClienteEmbeddings("k", http=HttpEmb("resposta_curta")).pontuar("música calma", FAIXAS)
        self.assertGreater(notas["a"], notas["b"])

    def test_falha_devolve_none_e_pausa_depois_de_varias(self):
        t = [0.0]
        http = HttpEmb("erro")
        c = ClienteEmbeddings("k", http=http, falhas_max=2, pausa=60, agora=lambda: t[0])
        self.assertIsNone(c.pontuar("música calma", FAIXAS))
        self.assertIsNone(c.pontuar("festa", FAIXAS))
        n = len(http.chamadas)
        self.assertIsNone(c.pontuar("rock", FAIXAS))
        self.assertEqual(len(http.chamadas), n)                      # em pausa: nem tenta
        t[0] = 61
        c.pontuar("outra", FAIXAS)
        self.assertGreater(len(http.chamadas), n)

    def test_poucas_faixas_ou_frase_vazia_nao_pontuam(self):
        c = ClienteEmbeddings("k", http=HttpEmb())
        self.assertIsNone(c.pontuar("música calma", FAIXAS[:2]))
        self.assertIsNone(c.pontuar("   ", FAIXAS))

    def test_configuracao_invalida(self):
        with self.assertRaises(ValueError):
            ClienteEmbeddings("")
        with self.assertRaises(ValueError):
            ClienteEmbeddings("k", provedor="groq")


class TestDoAmbiente(unittest.TestCase):
    def test_sem_chave_nao_liga(self):
        self.assertIsNone(emb.do_ambiente({}))
        self.assertIsNone(emb.do_ambiente({"GROQ_API_KEY": "k"}))     # Groq não oferece embeddings

    def test_escolhe_o_provedor_pela_chave(self):
        c = emb.do_ambiente({"GEMINI_API_KEY": "k"})
        self.assertEqual((c.provedor, c.modelo), ("gemini", "gemini-embedding-001"))
        self.assertTrue(c.url.endswith("/v1beta/openai/embeddings"))
        c = emb.do_ambiente({"OPENROUTER_API_KEY": "k", "SOULSBPM_MODELO_EMB": "google/gemini-embedding-001"})
        self.assertEqual((c.provedor, c.modelo), ("openrouter", "google/gemini-embedding-001"))
        self.assertEqual(c.url, "https://openrouter.ai/api/v1/embeddings")

    def test_provedor_escolhido_sem_embeddings_usa_o_que_tiver_chave(self):
        c = emb.do_ambiente({"SOULSBPM_IA_PROVEDOR": "groq", "GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k2"})
        self.assertEqual(c.provedor, "openrouter")

    def test_pode_ser_desligado(self):
        for v in ("0", "false", "off", "não"):
            self.assertIsNone(emb.do_ambiente({"GEMINI_API_KEY": "k", "SOULSBPM_EMBEDDINGS": v}))


class TestNotaDeVibe(unittest.TestCase):
    def faixa(self, i):
        return {"id": i, "titulo": i, "artista": "A", "bpm": 90, "tom": "8A", "energia": 0.3,
                "generos": [], "tags": ["calma"]}

    def interp(self, **extra):
        return {"clara": True, "tags": {"calma": 3}, "energia": 0.3, "generos": [], **extra}

    def test_sem_semantica_a_nota_e_a_de_sempre(self):
        self.assertAlmostEqual(musicfinder.vibe_score(self.faixa("x"), self.interp()), 1.0)

    def test_semantica_ajusta_a_nota_com_peso_menor_que_o_das_tags(self):
        i = self.interp(semantica={"alta": 1.0, "baixa": 0.0})
        alta, baixa = musicfinder.vibe_score(self.faixa("alta"), i), musicfinder.vibe_score(self.faixa("baixa"), i)
        self.assertAlmostEqual(alta, 1.0)
        self.assertAlmostEqual(baixa, 1 - musicfinder.PESO_SEMANTICA)
        self.assertGreater(baixa, 0.5)                               # as tags continuam mandando

    def test_faixa_fora_do_grupo_fica_neutra(self):
        i = self.interp(semantica={"outra": 1.0})
        esperado = (1 - musicfinder.PESO_SEMANTICA) * 1.0 + musicfinder.PESO_SEMANTICA * 0.5
        self.assertAlmostEqual(musicfinder.vibe_score(self.faixa("x"), i), esperado)

    def test_busca_por_artista_ignora_a_semantica(self):
        i = self.interp(pontos={"x": 0.6}, semantica={"x": 0.0})
        self.assertEqual(musicfinder.vibe_score(self.faixa("x"), i), 0.6)


class ProvedorFalso:
    def __init__(self, faixas):
        self.faixas = faixas

    def candidatas(self, interp):
        return [dict(f) for f in self.faixas]


class TestNaBusca(unittest.TestCase):
    catalogo = __import__("json").loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json").read_text("utf-8"))

    def motor(self, embeddings):
        return Motor([], Store(":memory:"), provedor=ProvedorFalso(self.catalogo), embeddings=embeddings)

    def test_guarda_as_notas_na_interpretacao_da_sessao(self):
        class Fixo:
            def pontuar(self, consulta, faixas):
                return {f["id"]: 0.9 for f in faixas}
        m = self.motor(Fixo())
        r = m.buscar("u1", "música calma para estudar à noite")
        self.assertEqual(r["estado"], "resultados")
        interp = m.sessoes[r["session_id"]].interp
        self.assertEqual(len(interp["semantica"]), len(self.catalogo))
        self.assertNotIn("semantica", r["interpretacao"])            # nada disso vai para o navegador

    def test_falha_nos_embeddings_nao_derruba_a_busca(self):
        class Quebrado:
            def pontuar(self, consulta, faixas):
                raise RuntimeError("fora do ar")
        r = self.motor(Quebrado()).buscar("u1", "música calma para estudar à noite")
        self.assertEqual(r["estado"], "resultados")

    def test_sem_provedor_de_embeddings_a_busca_e_a_de_antes(self):
        m = self.motor(None)
        r = m.buscar("u1", "música calma para estudar à noite")
        self.assertNotIn("semantica", m.sessoes[r["session_id"]].interp)

    def test_cliente_real_simulado_de_ponta_a_ponta(self):
        c = ClienteEmbeddings("k", http=HttpEmb())
        m = self.motor(c)
        r = m.buscar("u1", "música calma para estudar à noite")
        self.assertEqual(r["estado"], "resultados")
        self.assertTrue(m.sessoes[r["session_id"]].interp["semantica"])


class TestSaudeEModelo(unittest.TestCase):
    def test_health_informa_os_recursos(self):
        app = create_app(":memory:", catalog_path=str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json"))
        j = app.test_client().get("/api/health").get_json()
        self.assertEqual((j["embeddings"], j["sugere_artistas"], j["aprende"]), (False, False, True))


if __name__ == "__main__":
    unittest.main()
