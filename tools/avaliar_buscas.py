"""Avalia de onde vêm as músicas ruins: roda buscas por fonte e gera uma planilha para você marcar.

Passo 1 (gera a planilha):
    python tools/avaliar_buscas.py
  Cria a pasta `avaliacao/` com `avaliacao.csv` (uma linha por música) e imprime o tempo e a contagem por fonte.
  Opções: --buscas arquivo.txt (uma frase por linha), --saida pasta, --por-busca 10.

Passo 2 (você marca): abra `avaliacao.csv` no Excel/Planilhas e escreva `s` (boa) ou `n` (ruim) na coluna `boa`.
  Deixe em branco o que não souber avaliar.

Passo 3 (resumo):
    python tools/avaliar_buscas.py --resumo avaliacao/avaliacao.csv
  Mostra, por fonte, quantas músicas você marcou, quantas foram boas e quantos artistas diferentes apareceram.

Fontes comparadas (cada uma roda separada, com o mesmo ranking de vibe do app):
  lastfm_tags   o caminho clássico: músicas mais populares das tags do Last.fm
  ia_artistas   artistas sugeridos pela IA (confirmados no Last.fm), só se houver chave de IA
  combinado     o que o app realmente mostra (as duas fontes juntas, com embeddings se houver chave)

Usa as mesmas chaves do app (arquivo .env) e o mesmo cache da GetSongBPM: rodar de novo não gasta a cota.
As chaves nunca são impressas.
"""
import argparse
import csv
import pathlib
import sys
import threading
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from soulsbpm import musicfinder, sugestor                    # noqa: E402

BUSCAS_PADRAO = [
    "música calma para estudar à noite", "treino pesado de academia", "festa animada para dançar",
    "jantar romântico com jazz", "tristeza em dia de chuva", "viagem de carro na estrada",
    "lofi para programar", "churrasco com os amigos no domingo", "música para dormir",
    "domingo de manhã tomando café", "pagode para animar a casa", "tipo Calvin Harris",
    "rock para correr", "bossa nova no fim de tarde", "música para relaxar depois do trabalho",
]
FONTES = ("lastfm_tags", "ia_artistas", "combinado")
COLUNAS = ["busca", "fonte", "posicao", "artista", "titulo", "bpm", "tom", "energia", "vibe", "boa"]


class Espiao:
    """Conta quantas consultas à GetSongBPM foram feitas e quantas voltaram sem BPM/tom (faixa descartada)."""

    def __init__(self, provedor):
        self.consultas, self.sem_dados, self._trava = 0, 0, threading.Lock()
        self._bpm = getattr(provedor, "bpm", None)
        self._orig = self._bpm.buscar if self._bpm is not None else None
        if self._orig is not None:
            self._bpm.buscar = self._contar

    def _contar(self, artista, titulo):
        r = self._orig(artista, titulo)
        with self._trava:
            self.consultas += 1
            self.sem_dados += 0 if r else 1
        return r

    def zerar(self):
        with self._trava:
            self.consultas = self.sem_dados = 0

    def restaurar(self):
        if self._orig is not None:
            self._bpm.buscar = self._orig


def _linhas(busca, fonte, faixas):
    return [{"busca": busca, "fonte": fonte, "posicao": i, "artista": f["artista"], "titulo": f["titulo"],
             "bpm": f["bpm"], "tom": f["tom"], "energia": f["energia"], "vibe": f.get("vibe", ""), "boa": ""}
            for i, f in enumerate(faixas, 1)]


def _top(faixas, interp, limite):
    """As melhores da fonte pela mesma nota de vibe do app (mínimo 0: mostra o que ela trouxe, mesmo fraco)."""
    return musicfinder.buscar(faixas, interp, limite=limite, minimo=0.0)


def avaliar_busca(texto, provedor, ia, espiao, limite=10, embeddings=None):
    """Roda as três fontes para uma frase. Devolve (linhas, métricas por fonte)."""
    from soulsbpm.engine import Motor
    from soulsbpm.store import Store
    linhas, metricas = [], {}
    interp = musicfinder.interpretar(texto)
    nome, explicito = musicfinder.candidato_artista(texto, interp["clara"])
    por_artista = bool(nome and explicito)                    # "tipo X": só faz sentido o caminho combinado

    def medir(fonte, fn):
        espiao.zerar()
        t0 = time.time()
        try:
            faixas = fn()
            erro = ""
        except Exception as e:                               # uma fonte fora do ar não derruba a avaliação
            faixas, erro = [], f"{type(e).__name__}: {e}"
        metricas[fonte] = {"segundos": round(time.time() - t0, 1), "consultas_bpm": espiao.consultas,
                           "sem_bpm": espiao.sem_dados, "erro": erro, "retornou": len(faixas)}
        linhas.extend(_linhas(texto, fonte, faixas))

    if interp["clara"] and not por_artista:
        medir("lastfm_tags", lambda: _top(list(provedor.candidatas(interp)), interp, limite))
        if ia is not None and hasattr(provedor, "candidatas_sugeridas"):
            def via_ia():
                nomes = sugestor.sugerir(ia, texto)
                if not nomes:                                 # sem isto a fonte pareceria "ruim" quando na verdade nem rodou
                    raise RuntimeError("a IA não devolveu artistas (indisponível, sobrecarregada ou sem resposta)")
                return _top(list(provedor.candidatas_sugeridas(nomes, interp)), interp, limite)
            medir("ia_artistas", via_ia)

    def combinado():
        motor = Motor([], Store(":memory:"), provedor=provedor, ia=ia, embeddings=embeddings)
        return motor.buscar(None, texto).get("resultados", [])[:limite]
    medir("combinado", combinado)
    return linhas, metricas


def gerar(buscas, provedor, ia, saida, limite=10, embeddings=None, imprimir=print):
    saida = pathlib.Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    espiao = Espiao(provedor)
    todas, resumo = [], {f: {"segundos": 0.0, "consultas_bpm": 0, "sem_bpm": 0, "retornou": 0, "erros": 0} for f in FONTES}
    try:
        for i, texto in enumerate(buscas, 1):
            imprimir(f"[{i}/{len(buscas)}] {texto}")
            linhas, metricas = avaliar_busca(texto, provedor, ia, espiao, limite, embeddings)
            todas += linhas
            for fonte, m in metricas.items():
                r = resumo[fonte]
                r["segundos"] += m["segundos"]; r["consultas_bpm"] += m["consultas_bpm"]
                r["sem_bpm"] += m["sem_bpm"]; r["retornou"] += m["retornou"]; r["erros"] += 1 if m["erro"] else 0
                if m["erro"]:
                    imprimir(f"    {fonte}: ERRO {m['erro']}")
    finally:
        espiao.restaurar()
    arquivo = saida / "avaliacao.csv"
    with arquivo.open("w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: o Excel abre os acentos certos
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        w.writerows(todas)
    return arquivo, resumo


def imprimir_geracao(resumo, imprimir=print):
    imprimir("\nPor fonte (soma de todas as buscas):")
    imprimir(f"{'fonte':<13}{'músicas':>8}{'segundos':>10}{'consultas BPM':>15}{'sem BPM':>9}{'erros':>7}")
    for fonte in FONTES:
        r = resumo[fonte]
        if r["retornou"] or r["consultas_bpm"] or r["erros"]:
            imprimir(f"{fonte:<13}{r['retornou']:>8}{r['segundos']:>10.1f}{r['consultas_bpm']:>15}{r['sem_bpm']:>9}{r['erros']:>7}")
    imprimir("\nAbra o CSV, marque `s` (boa) ou `n` (ruim) na coluna `boa` e rode de novo com --resumo.")


def _marca(valor):
    v = (valor or "").strip().lower()
    if v in ("s", "sim", "1", "x", "boa", "bom"):
        return True
    if v in ("n", "nao", "não", "0", "ruim"):
        return False
    return None                                              # em branco ou valor estranho: não conta


def resumir(arquivo):
    """Por fonte: músicas marcadas, boas, % de boas e artistas diferentes. Lê o CSV que você preencheu."""
    por_fonte = {}
    with pathlib.Path(arquivo).open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d = por_fonte.setdefault(r["fonte"], {"marcadas": 0, "boas": 0, "artistas": set(), "total": 0})
            d["total"] += 1
            d["artistas"].add((r["artista"] or "").strip().lower())
            m = _marca(r.get("boa"))
            if m is not None:
                d["marcadas"] += 1
                d["boas"] += 1 if m else 0
    saida = []
    for fonte in FONTES:
        d = por_fonte.get(fonte)
        if d:
            pct = round(100 * d["boas"] / d["marcadas"], 1) if d["marcadas"] else None
            saida.append({"fonte": fonte, "total": d["total"], "marcadas": d["marcadas"], "boas": d["boas"],
                          "pct_boas": pct, "artistas_distintos": len(d["artistas"])})
    return saida


def imprimir_resumo(linhas, imprimir=print):
    imprimir(f"{'fonte':<13}{'músicas':>8}{'marcadas':>10}{'boas':>6}{'% boas':>8}{'artistas':>10}")
    for r in linhas:
        pct = "—" if r["pct_boas"] is None else f"{r['pct_boas']}%"
        imprimir(f"{r['fonte']:<13}{r['total']:>8}{r['marcadas']:>10}{r['boas']:>6}{pct:>8}{r['artistas_distintos']:>10}")
    if linhas and all(r["marcadas"] == 0 for r in linhas):
        imprimir("\nNenhuma música marcada ainda: preencha a coluna `boa` com s ou n.")
    elif len(linhas) > 1 and all(r["marcadas"] < 20 for r in linhas):
        imprimir("\nAtenção: menos de 20 músicas marcadas por fonte; a diferença pode ser acaso.")


def _buscas(arquivo):
    if not arquivo:
        return list(BUSCAS_PADRAO)
    linhas = [l.strip() for l in pathlib.Path(arquivo).read_text("utf-8-sig").splitlines()]
    return [l for l in linhas if l and not l.startswith("#")]


def main(argv=None):
    p = argparse.ArgumentParser(description="Avalia de onde vêm as músicas ruins (ver o topo do arquivo).")
    p.add_argument("--buscas", help="arquivo de texto com uma frase por linha (padrão: 15 frases prontas)")
    p.add_argument("--saida", default="avaliacao", help="pasta de saída (padrão: avaliacao)")
    p.add_argument("--por-busca", type=int, default=10, help="músicas por fonte em cada busca (padrão 10)")
    p.add_argument("--resumo", metavar="CSV", help="só calcula o resumo de um CSV já marcado")
    a = p.parse_args(argv)
    if a.resumo:
        imprimir_resumo(resumir(a.resumo))
        return 0

    import os
    from app import carregar_env
    from soulsbpm import embeddings as emb
    from soulsbpm.aovivo import provedor_do_ambiente
    from soulsbpm.llm import do_ambiente as llm_do_ambiente
    carregar_env()
    dados = pathlib.Path(os.environ.get("SOULSBPM_DATA") or RAIZ / "data")
    dados.mkdir(parents=True, exist_ok=True)
    provedor = provedor_do_ambiente(dados)
    if provedor is None:
        print("Faltam as chaves LASTFM_API_KEY e GETSONGBPM_API_KEY (coloque no arquivo .env).")
        return 1
    ia = llm_do_ambiente()
    musicfinder.configurar_ia(ia)
    embeddings = emb.do_ambiente() if ia else None
    print("IA de linguagem:", "ligada" if ia else "desligada (a fonte ia_artistas será pulada)")
    print("Embeddings:", "ligados" if embeddings else "desligados")
    arquivo, resumo = gerar(_buscas(a.buscas), provedor, ia, a.saida, a.por_busca, embeddings)
    print(f"\nPlanilha salva em: {arquivo}")
    imprimir_geracao(resumo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
