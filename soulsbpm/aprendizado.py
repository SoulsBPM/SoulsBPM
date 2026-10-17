"""Aprendizado dos pesos da nota (machine learning de verdade, sem biblioteca externa).

A nota de cada candidata é `0,35·vibe + 0,25·BPM + 0,25·tom + 0,15·energia`. Esses pesos foram escolhidos à mão.
Aqui o app aprende com o que as pessoas fazem: cada vez que alguém aceita, curte, salva ou pula uma sugestão, o
app guarda os 4 números dessa transição (vibe, BPM, tom, energia, todos de 0 a 1) e o resultado. Uma regressão
logística responde: "quanto cada um desses 4 critérios pesa para a pessoa aceitar uma transição?".

Cuidados para não piorar o que já funciona:
- só treina com dados suficientes (mínimo de exemplos de aceite e de pulo);
- os pesos aprendidos entram aos poucos: quanto mais exemplos, maior a parte deles; com poucos, vale o ajuste manual;
- peso negativo vira zero e a soma continua 1,0, então a nota continua entre 0 e 1 e explicável;
- com BPM alvo definido pelo DJ, a fórmula é outra e continua como antes (o rumo domina por escolha do usuário);
- ninguém é identificado no modelo: ele é um único conjunto de 4 pesos para todos. As linhas de treino ficam ligadas
  ao usuário só para poderem ser apagadas junto com o histórico.

Limite honesto: o app só vê o que ele mesmo sugeriu (viés de seleção) e os 4 critérios são correlacionados.
Por isso o resultado é um ajuste fino sobre o prior, não uma troca da fórmula.
"""
import logging
import math
import threading

from . import dj

log = logging.getLogger("soulsbpm.ia")

CRITERIOS = ("vibe", "bpm", "tom", "energia")
PRIOR = (dj.W_VIBE, dj.W_BPM, dj.W_KEY, dj.W_ENERGY)
MIN_EXEMPLOS = 40           # total de transições para começar a treinar
MIN_POR_CLASSE = 10         # e pelo menos tantos aceites e tantos pulos
K_PRIOR = 150.0             # "exemplos virtuais" do ajuste manual: com n = 150 exemplos, metade vem do modelo
MAX_LINHAS = 5000           # usa as mais recentes
RETREINA_A_CADA = 20        # novos exemplos desde o último treino
PESO_ACAO = {"accept": 0.5, "like": 1.0, "save": 1.5, "skip_early": 1.0, "skip_late": 0.3}   # como em feedback.DELTAS


def _resolver(A, b):
    """Resolve A·x = b por eliminação de Gauss com pivô parcial; None se a matriz for singular."""
    n = len(b)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][k] * x[k] for k in range(i + 1, n))) / M[i][i]
    return x


def regressao_logistica(X, y, pesos, l2=1.0, iteracoes=30):
    """Coeficientes [viés, c1..ck] da regressão logística com pesos por exemplo (método de Newton / IRLS).
    X: lista de listas de k números; y: 0/1. O viés não é regularizado."""
    d = len(X[0]) + 1
    w = [0.0] * d
    for _ in range(iteracoes):
        g, H = [0.0] * d, [[0.0] * d for _ in range(d)]
        for xi, yi, si in zip(X, y, pesos):
            v = (1.0,) + tuple(xi)
            z = max(-30.0, min(30.0, sum(a * b for a, b in zip(w, v))))
            p = 1.0 / (1.0 + math.exp(-z))
            r, s = si * (p - yi), si * p * (1.0 - p)
            for a in range(d):
                g[a] += r * v[a]
                for b in range(a, d):
                    H[a][b] += s * v[a] * v[b]
        for a in range(d):
            for b in range(a):
                H[a][b] = H[b][a]
        for a in range(1, d):
            g[a] += l2 * w[a]
            H[a][a] += l2
        H[0][0] += 1e-9
        passo = _resolver(H, g)
        if passo is None:
            break
        w = [wi - di for wi, di in zip(w, passo)]
        if max(abs(di) for di in passo) < 1e-7:
            break
    return w


def pesos_do_modelo(coef):
    """Coeficientes → pesos dos 4 critérios (não negativos, soma 1,0), ou None se nenhum critério ajuda."""
    c = [max(0.0, x) for x in coef[1:]]
    total = sum(c)
    return tuple(x / total for x in c) if total > 1e-9 else None


def misturar(aprendidos, prior, n):
    """Parte do modelo = n / (n + K_PRIOR); o resto é o ajuste manual. A soma continua 1,0."""
    lam = n / (n + K_PRIOR)
    m = [lam * a + (1 - lam) * p for a, p in zip(aprendidos, prior)]
    s = sum(m)
    return tuple(x / s for x in m)


class Aprendizado:
    """Guarda as transições avaliadas e mantém os pesos aprendidos. `store` precisa dos métodos de transições."""

    def __init__(self, store, em_segundo_plano=True, minimo=MIN_EXEMPLOS, min_classe=MIN_POR_CLASSE,
                 retreina_a_cada=RETREINA_A_CADA):
        self.store, self.em_segundo_plano = store, em_segundo_plano
        self.minimo, self.min_classe, self.retreina_a_cada = minimo, min_classe, retreina_a_cada
        self._lock = threading.Lock()
        self._pesos, self._info = None, {"amostras": 0, "positivas": 0, "negativas": 0, "treinado": False}
        self._novas, self._treinando = 0, False
        try:
            self.treinar()
        except Exception as e:                       # banco vazio, tabela antiga etc.: segue com o ajuste manual
            log.warning("Aprendizado: não consegui treinar na partida (%s)", type(e).__name__)

    # -- registro ------------------------------------------------------------
    def registrar(self, uid, tipo, prev_id, cand_id, x, y):
        """x: dict com vibe/bpm/tom/energia (0 a 1); y: 1 = a pessoa gostou, 0 = recusou."""
        if not uid or tipo not in PESO_ACAO:
            return
        self.store.add_transicao(uid, tipo, prev_id, cand_id, [float(x[c]) for c in CRITERIOS], int(y), PESO_ACAO[tipo])
        with self._lock:
            self._novas += 1
            devido = self._novas >= self.retreina_a_cada and not self._treinando
            if devido:
                self._treinando = True
        if devido:
            if self.em_segundo_plano:
                threading.Thread(target=self._treinar_seguro, daemon=True).start()
            else:
                self._treinar_seguro()

    def remover(self, uid, tipo, prev_id, cand_id):
        """Desfaz o último registro igual (curtida desfeita, aceite desfeito, pulo desfeito)."""
        if uid:
            self.store.remove_transicao(uid, tipo, prev_id, cand_id)

    # -- treino --------------------------------------------------------------
    def _treinar_seguro(self):
        try:
            self.treinar()
        except Exception as e:
            log.warning("Aprendizado: falha ao treinar (%s)", type(e).__name__)
        finally:
            with self._lock:
                self._treinando = False

    def treinar(self):
        linhas = self.store.transicoes(MAX_LINHAS)          # (x_vibe, x_bpm, x_tom, x_energia, y, peso)
        n = len(linhas)
        pos = sum(1 for r in linhas if r[4] == 1)
        info = {"amostras": n, "positivas": pos, "negativas": n - pos, "treinado": False}
        pesos = None
        if n >= self.minimo and pos >= self.min_classe and n - pos >= self.min_classe:
            X = [list(r[:4]) for r in linhas]
            y = [r[4] for r in linhas]
            sw = [r[5] for r in linhas]
            aprendido = pesos_do_modelo(regressao_logistica(X, y, sw))
            if aprendido is not None:
                pesos, info["treinado"] = misturar(aprendido, PRIOR, n), True
                info["do_modelo"] = {c: round(v, 3) for c, v in zip(CRITERIOS, aprendido)}
                log.info("Aprendizado: %d exemplos → pesos %s", n, [round(p, 3) for p in pesos])
        with self._lock:
            self._pesos, self._info, self._novas = pesos, info, 0
        return pesos

    # -- consulta ------------------------------------------------------------
    def pesos(self):
        """(vibe, bpm, tom, energia) aprendidos, ou None enquanto não há dados suficientes (vale o ajuste manual)."""
        with self._lock:
            return self._pesos

    def estado(self):
        with self._lock:
            pesos, info = self._pesos, dict(self._info)
        return {**info, "em_uso": pesos is not None, "minimo_exemplos": self.minimo,
                "pesos_em_uso": {c: round(v, 3) for c, v in zip(CRITERIOS, pesos or PRIOR)},
                "pesos_manuais": {c: v for c, v in zip(CRITERIOS, PRIOR)}}
