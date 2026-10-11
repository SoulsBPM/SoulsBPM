"""Monta um catálogo REAL a partir de uma lista de faixas, buscando BPM e tom na GetSongBPM.

Uso:
    export GETSONGBPM_API_KEY=sua_chave          # Windows (cmd): set GETSONGBPM_API_KEY=sua_chave
    python tools/importar_catalogo.py --entrada data/minhas_faixas.csv

Entrada: CSV com cabeçalho `artista,titulo` e, opcionais, `generos`, `tags`, `energia`, `duracao`
(generos e tags separados por | ; separador de colunas pode ser vírgula ou ponto e vírgula).
Saída: data/catalog.real.json (o catálogo de amostra NÃO é tocado). Para o app usar o real:
    SOULSBPM_CATALOG=data/catalog.real.json python app.py
Gêneros válidos para a busca por gênero: lofi, ambient, jazz, bossa, mpb, indie, acustico, pop, rock,
eletronica, house, techno, hiphop, pagode, samba, forro, instrumental.
"""
import argparse
import csv
import json
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from soulsbpm.fontes import Cache, FonteErro, GetSongBPM, montar_faixa  # noqa: E402


def ler_entrada(caminho):
    texto = pathlib.Path(caminho).read_text("utf-8-sig")
    dialeto = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=",;\t")
    linhas = list(csv.DictReader(texto.splitlines(), dialect=dialeto))
    for l in linhas:
        l["artista"], l["titulo"] = (l.get("artista") or "").strip(), (l.get("titulo") or "").strip()
    return [l for l in linhas if l["artista"] and l["titulo"]]


def lista(v):
    return [x.strip() for x in (v or "").split("|") if x.strip()]


def importar(linhas, fonte, avisar=print):
    faixas, faltaram, vistos = [], [], set()
    for l in linhas:
        chave = (l["artista"].lower(), l["titulo"].lower())
        if chave in vistos:
            continue
        vistos.add(chave)
        dados = fonte.buscar(l["artista"], l["titulo"])
        if not dados:
            faltaram.append(f'{l["artista"]} - {l["titulo"]}')
            avisar(f'  sem dados: {l["artista"]} - {l["titulo"]}')
            continue
        e = (l.get("energia") or "").replace(",", ".").strip()
        d = (l.get("duracao") or "").strip()
        faixas.append(montar_faixa(len(faixas) + 1, l["artista"], l["titulo"], dados, lista(l.get("generos")),
                                   lista(l.get("tags")), float(e) if e else None, int(d) if d.isdigit() else None))
        avisar(f'  ok: {l["artista"]} - {l["titulo"]}  {dados["bpm"]} BPM {dados["tom"]}')
    return faixas, faltaram


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--saida", default=str(RAIZ / "data" / "catalog.real.json"))
    ap.add_argument("--cache", default=str(RAIZ / "data" / "cache_fontes.db"))
    a = ap.parse_args()
    try:
        fonte = GetSongBPM(os.environ.get("GETSONGBPM_API_KEY"), Cache(a.cache))
        faixas, faltaram = importar(ler_entrada(a.entrada), fonte)
    except FonteErro as e:
        sys.exit(f"Erro: {e}")
    if len(faixas) < 20:
        print(f"Atenção: só {len(faixas)} faixas. Abaixo de ~100 o Modo DJ tem muitos 'buracos' de BPM.")
    pathlib.Path(a.saida).write_text(json.dumps(faixas, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(faixas)} faixas -> {a.saida}; {len(faltaram)} sem dados.")


if __name__ == "__main__":
    main()
