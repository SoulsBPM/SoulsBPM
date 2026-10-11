"""Modo "ao vivo": músicas REAIS sem lista pronta. A pessoa descreve a vibe e o app busca sozinho.

Fluxo de cada busca:
  vibe interpretada → tags/gêneros (traduzidos para as tags do Last.fm) → músicas populares dessas tags
  (Last.fm `tag.getTopTracks`) → BPM e tom de cada uma (GetSongBPM, com cache) → faixas no formato do app.

Limites honestos: Last.fm não traz BPM nem duração (BPM/tom vêm da GetSongBPM; duração fica em 200 s);
a energia é estimada pelo BPM e gênero; faixas sem BPM/tom na GetSongBPM são descartadas. A primeira
busca de uma vibe nova é a mais lenta (consultas por faixa); depois o cache acelera.
"""
import hashlib
import json
import logging
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from difflib import SequenceMatcher

from .fontes import FonteErro, montar_faixa

LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
log = logging.getLogger("soulsbpm.aovivo")

# tags do app → tags do Last.fm (inglês; ajuste livre, é só um dicionário)
TAG_LASTFM = {
    "calma": "chill", "relaxar": "relaxing", "foco": "focus", "concentracao": "study", "trabalhar": "study",
    "noite": "night", "dormir": "sleep", "meditar": "meditation", "treino": "workout", "correr": "running",
    "energia": "energetic", "motivacao": "motivational", "festa": "party", "danca": "dance", "balada": "club",
    "feliz": "happy", "animada": "upbeat", "triste": "sad", "melancolia": "melancholy", "saudade": "nostalgia",
    "nostalgia": "nostalgia", "romantico": "romantic", "raiva": "angry", "dirigir": "driving",
    "viagem": "road trip", "chuva": "rainy day", "cafe": "coffee", "manha": "morning", "tarde": "afternoon",
    "jantar": "dinner", "churrasco": "pagode", "amigos": "feel good",
}
GENERO_LASTFM = {
    "lofi": "lofi", "ambient": "ambient", "jazz": "jazz", "bossa": "bossa nova", "mpb": "mpb", "indie": "indie",
    "acustico": "acoustic", "pop": "pop", "rock": "rock", "eletronica": "electronic", "house": "house",
    "techno": "techno", "hiphop": "hip-hop", "pagode": "pagode", "samba": "samba", "forro": "forro",
    "instrumental": "instrumental",
}


def _slug(txt):
    t = unicodedata.normalize("NFKD", txt.lower())
    return re.sub(r"[^a-z0-9]+", "-", "".join(c for c in t if not unicodedata.combining(c))).strip("-")


def id_faixa(artista, titulo):
    return "l" + hashlib.sha1(f"{_slug(artista)}|{_slug(titulo)}".encode()).hexdigest()[:10]


class LastFm:
    def __init__(self, api_key, http=None, pausa=0.25):
        if not api_key:
            raise FonteErro("Defina a chave do Last.fm (variável LASTFM_API_KEY).")
        self.api_key, self._http, self.pausa = api_key, http or self._http_real, pausa

    @staticmethod
    def _http_real(url):
        req = urllib.request.Request(url, headers={"User-Agent": "SoulsBPM/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    def top_tracks(self, tag, limite=20):
        """[(artista, titulo)] das músicas mais associadas à tag. Levanta FonteErro em chave/rede inválidas."""
        url = LASTFM_URL + "?" + urllib.parse.urlencode(
            {"method": "tag.gettoptracks", "tag": tag, "limit": limite, "api_key": self.api_key, "format": "json"})
        time.sleep(self.pausa)
        try:
            r = self._http(url)
        except urllib.error.HTTPError as e:
            raise FonteErro(f"Last.fm respondeu HTTP {e.code}.")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise FonteErro(f"Falha de rede ao consultar o Last.fm: {e}")
        if isinstance(r, dict) and r.get("error"):
            if r["error"] in (10, 26):
                raise FonteErro("Chave do Last.fm recusada.")
            return []                                   # tag inexistente etc.: sem faixas, sem erro
        bloco = (r.get("tracks") or r.get("toptracks") or {}) if isinstance(r, dict) else {}
        lista = bloco.get("track") if isinstance(bloco, dict) else None
        saida = []
        for t in lista or []:
            if not isinstance(t, dict):
                continue
            artista = (t.get("artist") or {}).get("name") if isinstance(t.get("artist"), dict) else None
            if t.get("name") and artista:
                saida.append((artista, t["name"]))
        return saida


    def _chamar(self, metodo, **params):
        url = LASTFM_URL + "?" + urllib.parse.urlencode({"method": metodo, **params, "api_key": self.api_key, "format": "json"})
        time.sleep(self.pausa)
        try:
            r = self._http(url)
        except urllib.error.HTTPError as e:
            raise FonteErro(f"Last.fm respondeu HTTP {e.code}.")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise FonteErro(f"Falha de rede ao consultar o Last.fm: {e}")
        if isinstance(r, dict) and r.get("error"):
            if r["error"] in (10, 26):
                raise FonteErro("Chave do Last.fm recusada.")
            return {}
        return r if isinstance(r, dict) else {}

    @staticmethod
    def _lista(bloco, chave):
        v = bloco.get(chave) if isinstance(bloco, dict) else None
        if isinstance(v, dict):                                 # a API devolve objeto quando há só um item
            v = [v]
        return [x for x in (v or []) if isinstance(x, dict)]

    def buscar_artista(self, nome):
        """Nome oficial do artista mais parecido com o texto (None se não achar)."""
        r = self._chamar("artist.search", artist=nome, limit=1)
        achados = self._lista((r.get("results") or {}).get("artistmatches"), "artist")
        return achados[0].get("name") if achados and achados[0].get("name") else None

    def top_tracks_artista(self, artista, limite=15):
        r = self._chamar("artist.gettoptracks", artist=artista, limit=limite, autocorrect=1)
        return [(artista, t["name"]) for t in self._lista(r.get("toptracks"), "track") if t.get("name")]

    def artistas_similares(self, artista, limite=4):
        r = self._chamar("artist.getsimilar", artist=artista, limit=limite, autocorrect=1)
        return [a["name"] for a in self._lista(r.get("similarartists"), "artist") if a.get("name")]


class AoVivo:
    """Provedor de faixas reais para o Motor. `candidatas(interp)` devolve faixas novas prontas para uso."""

    def __init__(self, lastfm, getsongbpm, por_tag=20, max_tags=4, max_faixas=36, espera=10.0, trabalhadores=4):
        self.lastfm, self.bpm = lastfm, getsongbpm
        self.por_tag, self.max_tags, self.max_faixas = por_tag, max_tags, max_faixas
        self.espera, self.pool = espera, ThreadPoolExecutor(max_workers=trabalhadores)

    def tags_da_busca(self, interp):
        """[(tag_lastfm, tags_app, generos)] — primeiro as tags mais fortes, depois os gêneros."""
        achados, vistos = [], set()
        for tg, _ in sorted(interp["tags"].items(), key=lambda kv: -kv[1]):
            lf = TAG_LASTFM.get(tg)
            if lf:
                if lf in vistos:
                    for a in achados:
                        if a[0] == lf and tg not in a[1]:
                            a[1].append(tg)
                else:
                    vistos.add(lf)
                    achados.append((lf, [tg], []))
        for g in interp["generos"]:
            lf = GENERO_LASTFM.get(g)
            if lf and lf not in vistos:
                vistos.add(lf)
                achados.append((lf, [], [g]))
        return achados[: self.max_tags]

    def candidatas(self, interp):
        tags = self.tags_da_busca(interp)
        if not tags:
            return []
        por_faixa, ordem = {}, []                 # (artista,titulo) → dados; intercala as tags para variar
        listas = [(t, self.lastfm.top_tracks(t[0], self.por_tag)) for t in tags]
        for (lf, _, _), faixas in listas:
            log.info("Last.fm: tag %r → %d faixas", lf, len(faixas))
        for i in range(self.por_tag):
            for (lf, tags_app, gens), faixas in listas:
                if i < len(faixas):
                    chave = faixas[i]
                    if chave not in por_faixa:
                        por_faixa[chave] = {"tags": [], "generos": []}
                        ordem.append(chave)
                    d = por_faixa[chave]
                    d["tags"] += [t for t in tags_app if t not in d["tags"]]
                    d["generos"] += [g for g in gens if g not in d["generos"]]
        return self._resolver(ordem[: self.max_faixas], por_faixa)

    def _resolver(self, ordem, por_faixa):
        """BPM e tom de cada (artista, título) da lista, em paralelo e com cache. Devolve as faixas que tiveram dados."""
        futuros = {self.pool.submit(self._enriquecer, a, t, por_faixa[(a, t)]): (a, t) for a, t in ordem}
        feitos, pendentes = wait(list(futuros), timeout=self.espera)   # o resto segue em segundo plano e fica no cache
        novas, erros, sem_dados = [], [], 0
        for f in feitos:
            try:
                r = f.result()
            except FonteErro as e:
                erros.append(e)
                continue
            if r:
                novas.append(r)
            else:
                sem_dados += 1
        log.info("GetSongBPM: %d com BPM/tom, %d sem dados, %d erros, %d ainda em andamento (de %d faixas)",
                 len(novas), sem_dados, len(erros), len(pendentes), len(ordem))
        if erros:
            log.warning("GetSongBPM: %s", erros[0])
        if not novas and erros:
            raise erros[0]                    # nada deu certo por causa da fonte: o app mostra o motivo real
        pos = {k: i for i, k in enumerate(ordem)}
        novas.sort(key=lambda x: pos[(x["artista"], x["titulo"])])
        return novas

    def candidatas_artista(self, nome, estrito=False, por_artista=15, similares=4, por_similar=5):
        """Busca por artista: (nome oficial, {id: pontos}, faixas) ou None. As músicas do artista valem 1,0 e as de
        artistas parecidos 0,6. Com estrito=True (frase solta, sem "tipo X"), só aceita nome quase igual ao digitado."""
        oficial = self.lastfm.buscar_artista(nome)
        if not oficial:
            return None
        if estrito and SequenceMatcher(None, _slug(nome), _slug(oficial)).ratio() < 0.8:
            return None
        pesos, ordem, por_faixa = {}, [], {}
        def junta(faixas, peso):
            for chave in faixas:
                if chave not in por_faixa:
                    por_faixa[chave] = {"tags": [], "generos": []}
                    ordem.append(chave)
                    pesos[chave] = peso
        junta(self.lastfm.top_tracks_artista(oficial, por_artista), 1.0)
        for outro in self.lastfm.artistas_similares(oficial, similares):
            junta(self.lastfm.top_tracks_artista(outro, por_similar), 0.6)
        if not ordem:
            return None
        faixas = self._resolver(ordem[: self.max_faixas + 12], por_faixa)
        pontos = {f["id"]: pesos[(f["artista"], f["titulo"])] for f in faixas}
        return oficial, pontos, faixas

    def _enriquecer(self, artista, titulo, d):
        dados = self.bpm.buscar(artista, titulo)
        if not dados:
            return None
        f = montar_faixa(0, artista, titulo, dados, d["generos"], d["tags"])
        f["id"] = id_faixa(artista, titulo)
        f["fonte"] = "getsongbpm+lastfm"
        return f


def provedor_do_ambiente(pasta_cache):
    """AoVivo se LASTFM_API_KEY e GETSONGBPM_API_KEY existirem no ambiente; senão None (catálogo de amostra)."""
    import os
    from .fontes import Cache, GetSongBPM
    lf, gb = os.environ.get("LASTFM_API_KEY"), os.environ.get("GETSONGBPM_API_KEY")
    if not (lf and gb):
        return None
    return AoVivo(LastFm(lf), GetSongBPM(gb, Cache(str(pasta_cache / "cache_fontes.db"))))
