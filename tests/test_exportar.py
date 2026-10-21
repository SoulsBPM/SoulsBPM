"""Exportar playlist (static/exportar.js): roda o módulo no Node, sem navegador."""
import json
import pathlib
import shutil
import subprocess
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
NODE = shutil.which("node")

PLAYLIST = {"title": "Estudar à noite", "faixas": [
    {"artista": "Ludovico Einaudi", "titulo": "Una Mattina", "bpm": 83, "tom": "8A"},
    {"artista": "Brian Eno", "titulo": "An Ending, (Ascent)", "bpm": 67, "tom": "4B"},
    {"artista": "=HYPERLINK(\"x\")", "titulo": "Aspas \"duplas\"", "bpm": 90, "tom": "1A"}]}


def js(expr):
    prog = f"const E=require({json.dumps(str(RAIZ / 'static' / 'exportar.js'))});const p={json.dumps(PLAYLIST)};console.log(JSON.stringify({expr}));"
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@unittest.skipUnless(NODE, "Node não instalado")
class TestExportar(unittest.TestCase):
    def test_csv_tem_cabecalho_linhas_bom_e_links(self):
        csv = js("E.csvDaPlaylist(p)")
        self.assertTrue(csv.startswith("﻿posicao,artista,titulo,bpm,tom,link_spotify,link_youtube\r\n"))
        linhas = csv.strip().split("\r\n")
        self.assertEqual(len(linhas), 4)
        self.assertIn("1,Ludovico Einaudi,Una Mattina,83,8A,https://open.spotify.com/search/Ludovico%20Einaudi%20Una%20Mattina,"
                      "https://www.youtube.com/results?search_query=Ludovico%20Einaudi%20Una%20Mattina", linhas[1])

    def test_csv_protege_virgula_aspas_e_formula(self):
        csv = js("E.csvDaPlaylist(p)")
        self.assertIn('"An Ending, (Ascent)"', csv)
        self.assertIn('"Aspas ""duplas"""', csv)
        self.assertIn("\"'=HYPERLINK(\"\"x\"\")\"", csv)                  # começa com ': não vira fórmula no Excel
        self.assertNotIn(",=HYPERLINK", csv)

    def test_texto_e_uma_faixa_por_linha(self):
        self.assertEqual(js("E.textoDaPlaylist(p)").split("\n")[:2],
                         ["Ludovico Einaudi - Una Mattina", "Brian Eno - An Ending, (Ascent)"])

    def test_nome_do_arquivo_sem_acento_nem_simbolo(self):
        self.assertEqual(js("E.nomeDoArquivo(p)"), "estudar-a-noite.csv")
        self.assertEqual(js("E.nomeDoArquivo({title:'???'})"), "playlist.csv")


class TestPaginaLigaOExportador(unittest.TestCase):
    def test_index_carrega_exportar_antes_do_app(self):
        html = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("/static/exportar.js"), html.index("/static/app.js"))

    def test_app_usa_os_tres_botoes(self):
        js_app = (RAIZ / "static" / "app.js").read_text(encoding="utf-8")
        for trecho in ("baixar-csv", "copiar-lista", "Exportar.csvDaPlaylist", "Exportar.textoDaPlaylist"):
            self.assertIn(trecho, js_app)


if __name__ == "__main__":
    unittest.main()
