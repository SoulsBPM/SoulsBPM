"""Script de avaliação das buscas (tools/avaliar_buscas.py), com fontes simuladas e sem rede."""
import csv
import pathlib
import tempfile
import unittest
import urllib.parse

from soulsbpm import musicfinder
from soulsbpm.aovivo import AoVivo, LastFm
from tools import avaliar_buscas as av
from tests.test_aovivo import bpm_falso

TAG = [(f"Tag Artista {i}", f"Tag Faixa {i}") for i in range(6)]
IA_FAIXAS = [("Maré Alta", f"Faixa A{i}") for i in range(1, 4)]
TABELA = {a_t: (70 + 2 * i, "Am") for i, a_t in enumerate(TAG + IA_FAIXAS)}


def lastfm():
    """Last.fm falso: tags devolvem TAG; só o artista "Maré Alta" existe; qualquer outro nome vira um impostor."""
    def http(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        m = q["method"][0]
        if m == "tag.gettoptracks":
            return {"tracks": {"track": [{"name": t, "artist": {"name": a}} for a, t in TAG]}}
        if m == "artist.search":
            nome = q["artist"][0]
            return {"results": {"artistmatches": {"artist": [{"name": nome if nome == "Maré Alta" else "Zzz Outro"}]}}}
        if m == "artist.gettoptracks":
            return {"toptracks": {"track": [{"name": t} for a, t in IA_FAIXAS if a == q["artist"][0]]}}
        return {}
    return LastFm("k", http, pausa=0)


class IA:
    def __init__(self, resposta='{"artistas": ["Maré Alta", "Banda Inventada"]}'):
        self.resposta = resposta

    def completar(self, sistema, usuario, max_tokens=400, temperatura=0.0):
        return self.resposta


def provedor():
    return AoVivo(lastfm(), bpm_falso(TABELA))


class TestGerar(unittest.TestCase):
    def setUp(self):
        musicfinder.configurar_ia(None)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def rodar(self, buscas, ia=None, p=None):
        p = p or provedor()
        return av.gerar(buscas, p, ia, self.dir.name, limite=5, imprimir=lambda *_: None), p

    def linhas(self, arquivo):
        with open(arquivo, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def test_gera_csv_com_as_tres_fontes_e_coluna_boa_vazia(self):
        (arquivo, resumo), _ = self.rodar(["música calma para estudar à noite"], IA())
        linhas = self.linhas(arquivo)
        self.assertEqual({l["fonte"] for l in linhas}, set(av.FONTES))
        self.assertTrue(all(l["boa"] == "" for l in linhas))
        self.assertEqual(list(linhas[0]), av.COLUNAS)
        ia = [l for l in linhas if l["fonte"] == "ia_artistas"]
        self.assertEqual({l["artista"] for l in ia}, {"Maré Alta"})            # o impostor foi barrado
        tags = [l for l in linhas if l["fonte"] == "lastfm_tags"]
        self.assertTrue(tags and all(l["artista"].startswith("Tag Artista") for l in tags))
        self.assertLessEqual(len([l for l in tags]), 5)                         # respeita o limite por busca

    def test_sem_ia_pula_a_fonte_ia(self):
        (arquivo, _), _ = self.rodar(["música calma para estudar à noite"], None)
        self.assertNotIn("ia_artistas", {l["fonte"] for l in self.linhas(arquivo)})

    def test_busca_por_artista_so_roda_o_caminho_combinado(self):
        (arquivo, _), _ = self.rodar(["tipo Maré Alta"], IA())
        self.assertEqual({l["fonte"] for l in self.linhas(arquivo)} - {"combinado"}, set())

    def test_frase_sem_sentido_nao_quebra(self):
        (arquivo, resumo), _ = self.rodar(["asdf qwer"], IA())
        self.assertTrue(arquivo.exists())

    def test_fonte_com_erro_nao_derruba_as_outras(self):
        class Quebrado:
            def completar(self, *a, **k):
                raise RuntimeError("fora do ar")
        (arquivo, resumo), _ = self.rodar(["música calma para estudar à noite"], Quebrado())
        self.assertIn("lastfm_tags", {l["fonte"] for l in self.linhas(arquivo)})

    def test_conta_consultas_e_faixas_sem_bpm(self):
        tabela_parcial = dict(list(TABELA.items())[:3])                           # só 3 faixas têm BPM
        p = AoVivo(lastfm(), bpm_falso(tabela_parcial))
        (_, resumo), _ = self.rodar(["música calma para estudar à noite"], None, p)
        r = resumo["lastfm_tags"]
        self.assertGreater(r["consultas_bpm"], 0)
        self.assertGreater(r["sem_bpm"], 0)
        self.assertLess(r["sem_bpm"], r["consultas_bpm"] + 1)

    def test_espiao_devolve_o_metodo_original(self):
        p = provedor()
        original = p.bpm.buscar
        (_, _), _ = self.rodar(["música calma para estudar à noite"], None, p)
        self.assertEqual(p.bpm.buscar, original)

    def test_nao_imprime_chaves(self):
        saidas = []
        av.gerar(["música calma para estudar à noite"], provedor(), None, self.dir.name, limite=3, imprimir=saidas.append)
        self.assertFalse(any("api_key" in s for s in saidas))


class TestPausaEMotivo(unittest.TestCase):
    def test_pausa_entre_buscas_e_nao_depois_da_ultima(self):
        esperas = []
        with tempfile.TemporaryDirectory() as d:
            av.gerar(["rock pesado", "jazz suave", "pagode alegre"], provedor(), None, d, limite=3,
                     imprimir=lambda *_: None, pausa=7, dormir=esperas.append)
        self.assertEqual(esperas, [7, 7])

    def test_sem_pausa_nao_dorme(self):
        esperas = []
        with tempfile.TemporaryDirectory() as d:
            av.gerar(["rock pesado", "jazz suave"], provedor(), None, d, limite=3, imprimir=lambda *_: None,
                     dormir=esperas.append)
        self.assertEqual(esperas, [])

    def test_o_motivo_da_ia_aparece_na_tela(self):
        saidas = []
        musicfinder.configurar_ia(None)
        with tempfile.TemporaryDirectory() as d:
            av.gerar(["música calma para estudar à noite"], provedor(), IA("Não sei."), d, limite=3,
                     imprimir=saidas.append)
        self.assertTrue(any("ia_artistas: ERRO" in s and "sem artistas válidos" in s for s in saidas), saidas)


class TestResumo(unittest.TestCase):
    def csv(self, linhas):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        arq = pathlib.Path(d.name) / "a.csv"
        with open(arq, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=av.COLUNAS)
            w.writeheader()
            for fonte, artista, boa in linhas:
                w.writerow({"busca": "x", "fonte": fonte, "posicao": 1, "artista": artista, "titulo": "t",
                            "bpm": 90, "tom": "8A", "energia": .5, "vibe": .5, "boa": boa})
        return arq

    def test_calcula_porcentagem_por_fonte_ignorando_em_branco(self):
        arq = self.csv([("lastfm_tags", "A", "s"), ("lastfm_tags", "A", "n"), ("lastfm_tags", "B", "n"),
                        ("lastfm_tags", "C", ""), ("ia_artistas", "D", "S"), ("ia_artistas", "E", "sim"),
                        ("ia_artistas", "E", "não")])
        r = {x["fonte"]: x for x in av.resumir(arq)}
        self.assertEqual((r["lastfm_tags"]["marcadas"], r["lastfm_tags"]["boas"]), (3, 1))
        self.assertEqual(r["lastfm_tags"]["pct_boas"], 33.3)
        self.assertEqual(r["lastfm_tags"]["artistas_distintos"], 3)
        self.assertEqual(r["ia_artistas"]["pct_boas"], 66.7)
        self.assertEqual(r["ia_artistas"]["artistas_distintos"], 2)

    def test_sem_marcacao_nao_divide_por_zero_e_avisa(self):
        arq = self.csv([("combinado", "A", ""), ("combinado", "B", "")])
        r = av.resumir(arq)
        self.assertIsNone(r[0]["pct_boas"])
        saida = []
        av.imprimir_resumo(r, saida.append)
        self.assertTrue(any("Nenhuma música marcada" in s for s in saida))

    def test_poucas_marcacoes_geram_aviso_de_acaso(self):
        arq = self.csv([("lastfm_tags", "A", "s"), ("ia_artistas", "B", "n")])
        saida = []
        av.imprimir_resumo(av.resumir(arq), saida.append)
        self.assertTrue(any("menos de 20" in s for s in saida))

    def test_valores_estranhos_nao_contam(self):
        self.assertIsNone(av._marca("talvez"))
        self.assertIs(av._marca(" N "), False)
        self.assertIs(av._marca("Sim"), True)

    def test_main_resumo_le_o_arquivo(self):
        arq = self.csv([("combinado", "A", "s")])
        self.assertEqual(av.main(["--resumo", str(arq)]), 0)

    def test_buscas_padrao_e_arquivo_de_buscas(self):
        self.assertGreaterEqual(len(av.BUSCAS_PADRAO), 15)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        f = pathlib.Path(d.name) / "b.txt"
        f.write_text("# comentário\n\nrock pesado\n  jazz suave  \n", "utf-8")
        self.assertEqual(av._buscas(f), ["rock pesado", "jazz suave"])


class IASequencia:
    """IA que responde na ordem dada (a primeira vazia, como no limite por minuto do plano gratuito)."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def completar(self, sistema, usuario, max_tokens=400, temperatura=0.0):
        self.chamadas += 1
        return self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]


class TestEsperaDaIA(unittest.TestCase):
    def rodar(self, ia, espera_ia):
        musicfinder.configurar_ia(None)
        pausas = []
        with tempfile.TemporaryDirectory() as d:
            arq, resumo = av.gerar(["música calma para estudar à noite"], provedor(), ia, d, limite=5,
                                   imprimir=lambda *_: None, espera_ia=espera_ia, dormir=pausas.append)
            with open(arq, newline="", encoding="utf-8-sig") as f:
                fontes = {l["fonte"] for l in csv.DictReader(f)}
        return resumo, fontes, pausas

    def test_espera_e_tenta_de_novo_quando_a_ia_falha_na_primeira(self):
        ia = IASequencia([None, '{"artistas": ["Maré Alta"]}'])
        resumo, fontes, pausas = self.rodar(ia, espera_ia=65.0)
        self.assertIn("ia_artistas", fontes)
        self.assertEqual(resumo["ia_artistas"]["erros"], 0)
        self.assertGreater(resumo["ia_artistas"]["retornou"], 0)
        self.assertIn(65.0, pausas)

    def test_sem_espera_configurada_nao_tenta_de_novo(self):
        ia = IASequencia([None, '{"artistas": ["Maré Alta"]}'])
        resumo, _, pausas = self.rodar(ia, espera_ia=0.0)
        self.assertEqual(resumo["ia_artistas"]["erros"], 1)
        self.assertEqual(pausas, [])

    def test_se_a_segunda_tentativa_tambem_falha_vira_erro_com_motivo(self):
        resumo, _, pausas = self.rodar(IASequencia([None]), espera_ia=65.0)
        self.assertEqual(resumo["ia_artistas"]["erros"], 1)
        self.assertEqual(pausas.count(65.0), 1)                  # espera uma vez só, sem ficar em laço


if __name__ == "__main__":
    unittest.main()
