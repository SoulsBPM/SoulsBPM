"""Modo "ao vivo": músicas REAIS sem lista pronta. A pessoa descreve a vibe e o app busca sozinho.

Tudo vem de uma fonte só, a GetSongBPM (sem GetSongBPM). Fluxo de cada busca:
  vibe → BPM alvo pela energia pedida → músicas populares com esse BPM (`/tempo/`); a IA ainda pode sugerir artistas,
  cujas músicas são achadas pela busca da GetSongBPM; nome de música/artista → busca direta (`/search/`).
  Cada faixa precisa de BPM e tom (GetSongBPM, com cache) para entrar na lista.

Limites honestos: a GetSongBPM não diz o "clima" das músicas, então sem IA a vibe vira só um BPM alvo (por isso
a IA de artistas faz diferença); a duração fica em 200 s e a energia é estimada pelo BPM e gênero. A primeira
busca de uma vibe nova é a mais lenta (consultas por faixa); depois o cache acelera.
"""
import hashlib
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, wait
from difflib import SequenceMatcher

from .fontes import FonteErro, montar_faixa

log = logging.getLogger("soulsbpm.aovivo")

# tags do app → tags do GetSongBPM (inglês; ajuste livre, é só um dicionário)
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


class AoVivo:
    """Provedor de faixas reais para o Motor. `candidatas(interp)` devolve faixas novas prontas para uso."""

    def __init__(self, getsongbpm, max_faixas=36, espera=10.0, trabalhadores=4):
        self.bpm = getsongbpm
        self.max_faixas = max_faixas
        self.espera, self.pool = espera, ThreadPoolExecutor(max_workers=trabalhadores)

    @staticmethod
    def bpm_alvo(interp):
        """BPM que combina com a energia pedida (inverso da estimativa de energia), ou None se a vibe não disse."""
        e = interp.get("energia")
        if e is None:
            return None
        return int(round(max(60, min(170, 60 + (e - 0.2) / 0.7 * 90))))

    def candidatas(self, interp, por_bpm=12):
        """Músicas populares perto do BPM da vibe (alvo −8, alvo, alvo +8), intercaladas para variar."""
        alvo = self.bpm_alvo(interp)
        if alvo is None:
            return []
        listas = []
        for b in (alvo, alvo - 8, alvo + 8):
            try:
                listas.append(self.bpm.por_tempo(max(40, b), por_bpm))
            except FonteErro as e:
                if not listas:
                    raise
                log.warning("GetSongBPM: BPM %d ignorado (%s)", b, e)
        por_faixa, ordem = {}, []
        for i in range(por_bpm):
            for faixas in listas:
                if i < len(faixas) and faixas[i] not in por_faixa:
                    por_faixa[faixas[i]] = {"tags": list(interp["tags"]), "generos": list(interp["generos"])}
                    ordem.append(faixas[i])
        log.info("GetSongBPM: BPM alvo %d → %d faixas", alvo, len(ordem))
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
        oficial = self.bpm.buscar_artista(nome)
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
        junta(self.bpm.faixas_do_artista(oficial, por_artista), 1.0)
        for outro in self.bpm.artistas_similares(oficial, similares):
            junta(self.bpm.faixas_do_artista(outro, por_similar), 0.6)
        if not ordem:
            return None
        faixas = self._resolver(ordem[: self.max_faixas + 12], por_faixa)
        pontos = {f["id"]: pesos[(f["artista"], f["titulo"])] for f in faixas}
        return oficial, pontos, faixas

    def candidatas_musica(self, texto, identificar=None, max_achadas=3, minimo=0.7, do_artista=4):
        """Busca pelo NOME da música (ou "Artista - Música"). Se o GetSongBPM não achar e `identificar` existir (IA que
        reconhece música por trecho de letra), cada palpite é confirmado no GetSongBPM antes de valer.
        Devolve (pontos {id: nota}, faixas, info) ou None. A música achada vale 1,0; as do mesmo artista 0,8 e as
        parecidas 0,7. info = {"achadas": [(artista, título)], "sem_bpm": [(artista, título)]}."""
        from .musicfinder import relevancia
        texto = (texto or "").strip()
        if len(texto) < 2:
            return None
        def filtra(pares, consulta=texto, minimo=minimo):
            return [(a, t) for a, t in pares if relevancia(consulta, t, a) >= minimo][:max_achadas]
        achadas = []
        try:
            if " - " in texto:                                              # "Artista - Música"
                quem, _, nome = texto.partition(" - ")
                achadas = filtra(self.bpm.procurar(nome.strip(), 10, artista=quem.strip()))
            if not achadas:
                achadas = filtra(self.bpm.procurar(texto, 10))
            palavras = texto.split()
            if not achadas and " - " not in texto and 2 <= len(palavras) <= 5:   # "oi lagum", "lagum oi"
                cortes = [(" ".join(palavras[:i]), " ".join(palavras[i:])) for i in range(1, len(palavras))]
                for quem, nome in cortes + [(n, q) for q, n in cortes]:
                    achadas = filtra(self.bpm.procurar(nome, 5, artista=quem))
                    if achadas:
                        break
        except FonteErro as e:
            log.warning("GetSongBPM: busca por nome ignorada (%s)", e)
            if not achadas:
                raise
        if not achadas and identificar is not None:
            for a, t in identificar(texto)[:max_achadas]:                 # palpite da IA: só vale se a GetSongBPM confirma
                try:
                    ok = filtra(self.bpm.procurar(t, 5, artista=a), f"{a} {t}", 0.8)
                except FonteErro:
                    continue
                if ok and ok[0] not in achadas:
                    achadas.append(ok[0])
        if not achadas:
            return None
        pesos, ordem, por_faixa = {}, [], {}
        def junta(faixas, peso):
            for chave in faixas:
                if chave not in por_faixa:
                    por_faixa[chave] = {"tags": [], "generos": []}
                    ordem.append(chave)
                    pesos[chave] = peso
        junta(achadas, 1.0)
        artista, titulo = achadas[0]
        try:                                                   # o resto é enfeite: se falhar, ficam só as achadas
            junta([(artista, t) for _, t in self.bpm.faixas_do_artista(artista, do_artista + 1)
                   if (artista, t) not in por_faixa][:do_artista], 0.8)
            for outro in self.bpm.artistas_similares(artista, 3):
                junta(self.bpm.faixas_do_artista(outro, 2)[:2], 0.7)
        except FonteErro as e:
            log.warning("GetSongBPM: parecidas de %r ignoradas (%s)", titulo, e)
        faixas = self._resolver(ordem[: self.max_faixas], por_faixa)
        ids = {(f["artista"], f["titulo"]): f["id"] for f in faixas}
        pontos = {ids[k]: pesos[k] for k in ordem if k in ids}
        sem_bpm = [k for k in achadas if k not in ids]
        return pontos, faixas, {"achadas": achadas, "sem_bpm": sem_bpm}

    def candidatas_sugeridas(self, nomes, interp, max_artistas=3, por_artista=8):
        """Faixas dos artistas que a IA sugeriu para a vibe. Cada nome é confirmado no GetSongBPM (nome quase igual,
        senão é descartado: barra artista inventado) e todas as músicas são resolvidas de uma vez no GetSongBPM.
        As faixas herdam as tags e gêneros da vibe, porque o artista foi escolhido para ela."""
        por_faixa, ordem, aceitos = {}, [], 0
        for nome in nomes:
            if aceitos >= max_artistas:
                break
            try:
                oficial = self.bpm.buscar_artista(nome)
                if not oficial or SequenceMatcher(None, _slug(nome), _slug(oficial)).ratio() < 0.8:
                    log.info("IA sugeriu %r: não confirmado no GetSongBPM, descartado", nome)
                    continue
                musicas = self.bpm.faixas_do_artista(oficial, por_artista)
            except FonteErro as e:
                log.warning("GetSongBPM: %s (sugestão %r ignorada)", e, nome)
                continue
            if not musicas:
                continue
            aceitos += 1
            for chave in musicas:
                if chave not in por_faixa:
                    por_faixa[chave] = {"tags": list(interp["tags"]), "generos": list(interp["generos"])}
                    ordem.append(chave)
        return self._resolver(ordem, por_faixa) if ordem else []

    def _enriquecer(self, artista, titulo, d):
        dados = self.bpm.buscar(artista, titulo)
        if not dados:
            return None
        f = montar_faixa(0, artista, titulo, dados, d["generos"], d["tags"])
        f["id"] = id_faixa(artista, titulo)
        f["fonte"] = "getsongbpm"
        return f


def provedor_do_ambiente(pasta_cache):
    """AoVivo se GETSONGBPM_API_KEY existir no ambiente; senão None (catálogo de amostra)."""
    import os
    from .fontes import Cache, GetSongBPM
    gb = os.environ.get("GETSONGBPM_API_KEY")
    if not gb:
        return None
    return AoVivo(GetSongBPM(gb, Cache(str(pasta_cache / "cache_fontes.db"))))
