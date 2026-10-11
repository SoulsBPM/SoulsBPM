"""Fonte de dados REAL de faixas: BPM e tom via GetSongBPM (https://getsongbpm.com/api).

Entrega o mesmo formato de faixa do catálogo de amostra (id, titulo, artista, bpm, tom, energia,
generos, tags, duracao), então o resto do app não muda.

Limites honestos desta fonte (ver README):
- a GetSongBPM só fornece BPM e tom; a ENERGIA aqui é uma ESTIMATIVA (`estimar_energia`) e a faixa
  sai marcada com `energia_estimada: true`;
- a duração não existe na fonte (usa o valor do arquivo de entrada ou 200 s);
- a licença da API exige um link visível para getsongbpm.com onde os dados forem exibidos.
"""
import json
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.getsong.co"
TTL_POSITIVO = 30 * 86400      # lookups que deram certo ficam 30 dias no cache
TTL_NEGATIVO = 7 * 86400       # "não encontrado" fica 7 dias (evita gastar a cota à toa)

# classe de altura (0=Dó … 11=Si) → Camelot (maior = B, menor = A)
_CAMELOT_MAIOR = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
                  6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}
_CAMELOT_MENOR = {0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A",
                  6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A"}
_NOTAS = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


class FonteErro(Exception):
    """Falha ao consultar a fonte (chave inválida, cota estourada, rede)."""


def para_camelot(key_of=None, open_key=None):
    """Converte 'Am', 'F#m', 'Bb', 'C♯ minor'… (ou Open Key '1m', '6d') para Camelot ('8A'). None se não der."""
    if key_of:
        t = key_of.strip().replace("♯", "#").replace("♭", "b")
        m = re.match(r"^([A-Ga-g])\s*([#b]?)\s*(.*)$", t)
        if m:
            pc = _NOTAS[m.group(1).lower()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
            resto = m.group(3).strip().lower()
            menor = resto.startswith("m") and not resto.startswith("maj") or resto.startswith("min")
            return (_CAMELOT_MENOR if menor else _CAMELOT_MAIOR)[pc % 12]
    if open_key:
        m = re.match(r"^(1[0-2]|[1-9])\s*([dm])$", open_key.strip().lower())
        if m:   # Open Key 1d = Dó maior = Camelot 8B; o número anda 7 casas
            n = (int(m.group(1)) + 6) % 12 + 1
            return f"{n}{'B' if m.group(2) == 'd' else 'A'}"
    return None


def estimar_energia(bpm, generos=(), danceabilidade=None, acustica=None):
    """ESTIMATIVA (0,05–0,95). Não vem da fonte: a GetSongBPM não tem 'energia'.

    Base: BPM e gênero. Se a API trouxe danceability e acousticness (0–100), entram na conta
    (dançável e pouco acústica → mais energia). Trocar por dado medido (ReccoBeats, Essentia…)
    quando houver. Meio tempo/dobro não é corrigido aqui de propósito.
    """
    base = 0.2 + 0.7 * min(1.0, max(0.0, (bpm - 60) / 90))
    viés = 0.0
    for g in generos:
        viés += {"ambient": -0.2, "lofi": -0.12, "chillhop": -0.1, "acustico": -0.1, "jazz": -0.08,
                 "bossa": -0.1, "mpb": -0.05, "instrumental": -0.05,
                 "techno": 0.08, "house": 0.05, "rock": 0.1, "eletronica": 0.05}.get(g, 0.0)
    e = base + max(-0.25, min(0.15, viés))
    sinais = [(danceabilidade, 0.3, False), (acustica, 0.2, True)]
    for v, peso, invertido in sinais:
        if isinstance(v, (int, float)) and 0 <= v <= 100:
            alvo = 1 - v / 100 if invertido else v / 100
            e = e * (1 - peso) + alvo * peso
    return round(min(0.95, max(0.05, e)), 2)


def tags_estimadas(energia, bpm):
    """Tags de clima do vocabulário do app, derivadas da energia (estimativa; o CSV pode sobrescrever)."""
    if energia < 0.3:
        return ["calma", "relaxar", "noite", "foco"]
    if energia < 0.5:
        return ["calma", "tarde", "cafe", "foco"]
    if energia < 0.7:
        return ["feliz", "animada", "dirigir", "amigos"]
    return ["energia", "animada", "treino", "festa"]


def _slug(txt):
    t = unicodedata.normalize("NFKD", txt.lower())
    return re.sub(r"[^a-z0-9]+", "-", "".join(c for c in t if not unicodedata.combining(c))).strip("-")


class Cache:
    """Cache em SQLite (arquivo próprio) com TTL separado para acertos e para 'não encontrado'."""

    def __init__(self, path=":memory:"):
        self._lock = threading.Lock()
        self._c = sqlite3.connect(path, check_same_thread=False)
        self._c.execute("CREATE TABLE IF NOT EXISTS lookup(k TEXT PRIMARY KEY, payload TEXT, ts REAL)")
        self._c.commit()

    def get(self, k, agora=None):
        with self._lock:
            row = self._c.execute("SELECT payload, ts FROM lookup WHERE k=?", (k,)).fetchone()
        if not row:
            return False, None
        payload, ts = row
        valor = json.loads(payload)
        ttl = TTL_POSITIVO if valor is not None else TTL_NEGATIVO
        if (time.time() if agora is None else agora) - ts > ttl:
            return False, None
        return True, valor

    def put(self, k, valor, agora=None):
        with self._lock:
            self._c.execute("INSERT OR REPLACE INTO lookup VALUES(?,?,?)",
                            (k, json.dumps(valor), time.time() if agora is None else agora))
            self._c.commit()


class GetSongBPM:
    LIMITE_HORA = 2500      # a API bloqueia a chave por 1 h acima de 3000/h; paramos antes, com folga

    def __init__(self, api_key, cache=None, http=None, pausa=0.5, tentativas=3, limite_hora=None):
        if not api_key:
            raise FonteErro("Defina a chave da GetSongBPM (variável GETSONGBPM_API_KEY).")
        self.api_key, self.cache = api_key, cache or Cache()
        self._http, self.pausa, self.tentativas = http or self._http_real, pausa, tentativas
        self.limite_hora = limite_hora or self.LIMITE_HORA
        self._envios, self._trava = [], threading.Lock()

    def _reservar(self):
        agora = time.time()
        with self._trava:
            self._envios = [t for t in self._envios if agora - t < 3600]
            if len(self._envios) >= self.limite_hora:
                raise FonteErro("Limite de consultas por hora da GetSongBPM quase atingido; usando só o que já está no cache.")
            self._envios.append(agora)

    def _http_real(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "SoulsBPM/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get(self, caminho, **params):
        url = f"{BASE_URL}{caminho}?" + urllib.parse.urlencode({"api_key": self.api_key, **params})
        for i in range(self.tentativas):
            try:
                self._reservar()
                time.sleep(self.pausa)
                return self._http(url)
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise FonteErro("Chave da GetSongBPM recusada (confira a chave e o link de retorno cadastrado).")
                if e.code == 429 and i < self.tentativas - 1:
                    time.sleep(2 ** (i + 1))        # cota por hora: espera e tenta de novo
                    continue
                raise FonteErro(f"GetSongBPM respondeu HTTP {e.code}.")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                if i == self.tentativas - 1:
                    raise FonteErro(f"Falha de rede ao consultar a GetSongBPM: {e}")
        raise FonteErro("GetSongBPM indisponível.")

    @staticmethod
    def _normaliza(item):
        """Extrai bpm e tom do item da API; None se faltar dado utilizável."""
        try:
            bpm = float(item.get("tempo"))
        except (TypeError, ValueError):
            return None
        tom = para_camelot(item.get("key_of"), item.get("open_key"))
        if not tom or not 40 <= bpm <= 250:
            return None
        out = {"bpm": round(bpm), "tom": tom}
        for chave, campo in (("danceability", "danceabilidade"), ("acousticness", "acustica")):
            v = item.get(chave)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100:
                out[campo] = v
        return out

    def buscar(self, artista, titulo):
        """{'bpm': 128, 'tom': '8A'} ou None. Usa e alimenta o cache."""
        k = f"{_slug(artista)}|{_slug(titulo)}"
        achou, valor = self.cache.get(k)
        if achou:
            return valor
        r = self._get("/search/", type="both", lookup=f"song:{titulo} artist:{artista}", limit=5)
        resultado = None
        for item in (r.get("search") or []) if isinstance(r, dict) else []:
            if not isinstance(item, dict):
                continue
            nome = _slug(((item.get("artist") or {}).get("name") or "")) if isinstance(item.get("artist"), dict) else ""
            if nome and _slug(artista) not in nome and nome not in _slug(artista):
                continue                         # artista diferente: não aceita o primeiro resultado às cegas
            resultado = self._normaliza(item)
            if not resultado and item.get("id"):                # a busca nem sempre traz tom: consulta a faixa
                det = self._get("/song/", id=item["id"])
                resultado = self._normaliza((det.get("song") or {}) if isinstance(det, dict) else {})
            if resultado:
                break
        self.cache.put(k, resultado)
        return resultado


def montar_faixa(idx, artista, titulo, dados, generos=(), tags=(), energia=None, duracao=None):
    """Monta a faixa no formato do catálogo. `dados` vem de GetSongBPM.buscar."""
    generos = list(generos)
    estimada = energia is None
    e = round(float(energia), 2) if energia is not None else estimar_energia(
        dados["bpm"], generos, dados.get("danceabilidade"), dados.get("acustica"))
    return {"id": f"r{idx:04d}", "titulo": titulo, "artista": artista, "bpm": dados["bpm"], "tom": dados["tom"],
            "energia": e, "generos": generos, "tags": list(tags) or tags_estimadas(e, dados["bpm"]),
            "duracao": int(duracao) if duracao else 200,
            "fonte": "getsongbpm", "energia_estimada": estimada}
