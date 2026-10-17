"""Embeddings de vibe: mede o quão perto uma faixa está da frase da busca, pelo significado.

O léxico e as tags só enxergam palavras-chave. Com embeddings, uma frase como "trilha pra dirigir de madrugada
sem pressa" fica perto de músicas com esse clima mesmo sem nenhuma das palavras da lista. O modelo de embeddings
transforma o texto em um vetor; quanto mais parecidos os vetores (cosseno), mais parecido o sentido.

Como é usado: a frase da busca e as músicas encontradas viram vetores; a similaridade vira uma nota de 0 a 1
(relativa ao grupo, para não depender da escala de cada modelo) e entra na nota de vibe (musicfinder.vibe_score)
com peso menor que o das tags. Sem chave, sem rede ou com qualquer erro, a nota de vibe continua a de antes.

Limite honesto: o texto da faixa é só "título + artista". O modelo reconhece o estilo de artistas e músicas
conhecidos, mas não ouve o áudio nem lê a letra; para faixas obscuras o sinal é fraco.

Provedores (pela chave do ambiente, a mesma da IA de linguagem):
  gemini      GEMINI_API_KEY      gemini-embedding-001 (plano gratuito do Google AI Studio)
  openrouter  OPENROUTER_API_KEY  openai/text-embedding-3-small
SOULSBPM_MODELO_EMB troca o modelo; SOULSBPM_EMBEDDINGS=0 desliga. A chave nunca é registrada em log.
"""
import logging
import math
import threading
import time
import urllib.error
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from .llm import _http_post

log = logging.getLogger("soulsbpm.ia")

# nome → (variável da chave, endereço, modelo padrão). Os dois falam o formato de embeddings da OpenAI.
PROVEDORES = {
    "gemini": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/embeddings",
               "gemini-embedding-001"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/embeddings", "openai/text-embedding-3-small"),
}
MAX_FAIXAS = 60             # por busca
LOTE = 64
MAX_INDIVIDUAIS = 24        # se o provedor não aceitar lista, no máximo tantos pedidos avulsos por vez
PISO_DESVIO = 0.02          # evita ampliar ruído quando todas as faixas têm quase a mesma similaridade


def cosseno(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def normalizar(similaridades):
    """Similaridades do grupo → notas de 0 a 1: a média vira 0,5 e +2 desvios chegam a 1,0 (−2 a 0,0)."""
    n = len(similaridades)
    media = sum(similaridades) / n
    desvio = max(math.sqrt(sum((s - media) ** 2 for s in similaridades) / n), PISO_DESVIO)
    return [round(min(1.0, max(0.0, 0.5 + (s - media) / (4 * desvio))), 3) for s in similaridades]


def texto_faixa(f):
    return f"Música “{f['titulo']}” de {f['artista']}"


def texto_consulta(consulta):
    return f"Música para: {consulta}"


def _vetor_valido(v):
    return isinstance(v, list) and v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)


def _extrair(resp, n):
    """Lista de n vetores na ordem do pedido, ou None se a resposta não servir."""
    dados = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(dados, list) or len(dados) != n:
        return None
    if all(isinstance(d, dict) and isinstance(d.get("index"), int) for d in dados):
        dados = sorted(dados, key=lambda d: d["index"])
    vetores = [d.get("embedding") if isinstance(d, dict) else None for d in dados]
    if not all(_vetor_valido(v) for v in vetores) or len({len(v) for v in vetores}) != 1:
        return None
    return [[float(x) for x in v] for v in vetores]


class ClienteEmbeddings:
    def __init__(self, chave, provedor="gemini", modelo=None, http=None, timeout=10.0, cache_max=3000,
                 falhas_max=3, pausa=60.0, agora=time.time):
        if not chave:
            raise ValueError("Defina a chave do provedor de embeddings.")
        if provedor not in PROVEDORES:
            raise ValueError(f"Provedor de embeddings desconhecido: {provedor}")
        _, self.url, padrao = PROVEDORES[provedor]
        self.provedor, self._chave, self.modelo = provedor, chave, modelo or padrao
        self._http, self.timeout = http or self._http_real, timeout
        self._cache, self._cache_max = OrderedDict(), cache_max
        self._lock = threading.Lock()
        self._falhas, self._falhas_max, self._pausa, self._agora = 0, falhas_max, pausa, agora
        self._pausado_ate = 0.0
        self._lote_ok = True                                 # vira False se o provedor recusar lista de textos

    def _http_real(self, corpo, chave, timeout):
        return _http_post(self.url, {"authorization": f"Bearer {chave}"}, corpo, timeout)

    def _pedir(self, textos):
        return _extrair(self._http({"model": self.modelo, "input": textos}, self._chave, self.timeout), len(textos))

    def _buscar(self, textos):
        """Vetores de textos que ainda não estão no cache (lista, ou avulsos se o provedor não aceita lista)."""
        if self._lote_ok:
            saida = []
            for i in range(0, len(textos), LOTE):
                parte = textos[i:i + LOTE]
                try:
                    v = self._pedir(parte)
                except urllib.error.HTTPError as e:
                    if e.code in (400, 422) and len(parte) > 1:       # provável recusa de lista: tenta avulso
                        self._lote_ok = False
                        return self._buscar_avulsos(textos)
                    raise
                if v is None:
                    self._lote_ok = False                              # resposta sem um vetor por texto
                    return self._buscar_avulsos(textos)
                saida += v
            return saida
        return self._buscar_avulsos(textos)

    def _buscar_avulsos(self, textos):
        if len(textos) > MAX_INDIVIDUAIS:
            raise ValueError("provedor sem suporte a lista e pedido grande demais")
        with ThreadPoolExecutor(max_workers=4) as pool:
            partes = list(pool.map(lambda t: self._pedir([t]), textos))
        if any(p is None for p in partes):
            raise ValueError("resposta fora do formato")
        return [p[0] for p in partes]

    def vetores(self, textos):
        """Um vetor por texto, na mesma ordem; None se o provedor falhar (quem chama usa a reserva)."""
        if not textos:
            return []
        with self._lock:
            if self._agora() < self._pausado_ate:
                return None
            faltam = [t for t in dict.fromkeys(textos) if t not in self._cache]
        if faltam:
            try:
                novos = self._buscar(faltam)
            except urllib.error.HTTPError as e:
                self._falhou(f"HTTP {e.code}")
                return None
            except Exception as e:
                self._falhou(type(e).__name__)
                return None
            with self._lock:
                self._falhas = 0
                for t, v in zip(faltam, novos):
                    self._cache[t] = v
                while len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)
        with self._lock:
            for t in textos:
                if t in self._cache:
                    self._cache.move_to_end(t)
            try:
                return [self._cache[t] for t in textos]
            except KeyError:                       # saiu do cache entre uma coisa e outra (cache pequeno demais)
                return None

    def pontuar(self, consulta, faixas, maximo=MAX_FAIXAS):
        """{id da faixa: nota 0..1} relativa ao grupo, ou None (menos de 3 faixas, ou provedor indisponível)."""
        faixas = list(faixas)[:maximo]
        if len(faixas) < 3 or not (consulta or "").strip():
            return None
        v = self.vetores([texto_consulta(consulta)] + [texto_faixa(f) for f in faixas])
        if v is None:
            return None
        notas = normalizar([cosseno(v[0], x) for x in v[1:]])
        return {f["id"]: n for f, n in zip(faixas, notas)}

    def _falhou(self, motivo):
        with self._lock:
            self._falhas += 1
            if self._falhas >= self._falhas_max:
                self._pausado_ate = self._agora() + self._pausa
                self._falhas = 0
                log.warning("Embeddings indisponíveis (%s); só tags e energia por %.0fs", motivo, self._pausa)
            else:
                log.warning("Falha ao consultar os embeddings (%s); só tags e energia nesta busca", motivo)


def do_ambiente(env=None):
    """ClienteEmbeddings conforme o ambiente, ou None. Usa o provedor de SOULSBPM_IA_PROVEDOR se ele tiver
    embeddings; senão o primeiro com chave (gemini, openrouter). SOULSBPM_EMBEDDINGS=0 desliga."""
    import os
    env = os.environ if env is None else env
    if (env.get("SOULSBPM_EMBEDDINGS") or "").strip().lower() in ("0", "nao", "não", "false", "off"):
        return None
    escolhido = (env.get("SOULSBPM_IA_PROVEDOR") or "").strip().lower()
    ordem = [escolhido] if escolhido in PROVEDORES else ["gemini", "openrouter"]
    for nome in ordem:
        chave = (env.get(PROVEDORES[nome][0]) or "").strip()
        if chave:
            return ClienteEmbeddings(chave, nome, (env.get("SOULSBPM_MODELO_EMB") or None))
    return None
