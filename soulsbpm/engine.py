"""Orquestra a sessão: estados do documento 4, eventos do documento 3 e decisões D1–D5."""
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

from .fontes import FonteErro
from . import dj, feedback, musicfinder, sugestor
from .narrador import Narrador

log = logging.getLogger("soulsbpm.engine")

# estados (documento 4)
INICIO, BUSCANDO, RESULTADOS, SEM_RESULTADOS = "inicio", "buscando", "resultados", "sem_resultados"
TOCANDO, SUGERINDO, REAJUSTANDO = "tocando", "sugerindo_proxima", "reajustando"
SALVANDO, SALVA = "salvando", "playlist_salva"

PULOS_PARA_AJUSTE = 3
BPM_MIN, BPM_MAX, BPM_PASSO = 50, 200, 5
VIBE_MINIMA = 0.3
SESSAO_TTL = 3 * 3600          # sessão parada por 3 h expira (o app guarda tudo em memória)
MAX_SESSOES = 5000
MAX_TEXTO_BUSCA = 200
ESPERA_SUGESTAO_IA = 20.0      # tempo máximo esperando a IA sugerir artistas (a busca segue sem ela se passar)


class Erro(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


class Sessao:
    def __init__(self, user_id, consulta, interp):
        self.id = secrets.token_urlsafe(8)
        self.user_id = user_id
        self.consulta = consulta
        self.interp = interp
        self.estado = INICIO
        self.sequencia = []        # ids na ordem em que tocam (a última é a atual)
        self.puladas = set()
        self.sugerida = None       # dict de rank_next
        self.pulos_seguidos = 0
        self.aceites = []          # pilha de aceites que ainda podem ser desfeitos
        self.volta = []            # pilha do botão Voltar: um item por aceite ou pulo da faixa atual
        self.curtidas = set()      # faixas curtidas nesta sessão (curtir de novo desfaz)
        self.bpm_alvo = None       # BPM que o DJ quer atingir (None = a IA segue só a vibe)
        self.ultimo = time.monotonic()   # último uso (para expirar sessões paradas)


class Motor:
    def __init__(self, catalogo, store, agora=None, provedor=None, ia=None, embeddings=None, aprendizado=None,
                 max_artistas_ia=3):
        self.catalogo = list(catalogo)
        self.por_id = {f["id"]: f for f in self.catalogo}
        self.store = store
        self.agora = agora
        self.sessoes = {}
        self.provedor = provedor              # modo ao vivo: busca faixas reais a cada vibe (soulsbpm/aovivo.py)
        # recursos de IA, todos opcionais e com reserva: sem eles o app funciona como antes
        self.ia = ia                          # modelo de linguagem: sugere artistas e narra as transições
        self.embeddings = embeddings          # similaridade semântica entre a frase e as faixas
        self.aprendizado = aprendizado        # pesos da nota aprendidos com o feedback
        self.max_artistas_ia = max_artistas_ia
        self.narrador = Narrador(ia)
        self._pool_ia = ThreadPoolExecutor(max_workers=2)
        if provedor:                          # reabre playlists e histórico de faixas já descobertas
            self.adicionar_faixas(store.load_tracks(), salvar=False)

    def adicionar_faixas(self, faixas, salvar=True):
        novas = [f for f in faixas if f["id"] not in self.por_id]
        for f in novas:
            self.catalogo.append(f)
            self.por_id[f["id"]] = f
        if novas and salvar:
            self.store.save_tracks(novas)
        return len(novas)

    # utilidades -----------------------------------------------------------
    def perfil(self, uid):
        return feedback.Perfil(self.store, uid, self.agora)

    def sessao(self, sid) -> Sessao:
        s = self.sessoes.get(sid)
        if not s:
            raise Erro("Sessão não encontrada. Faça uma nova busca.", 404)
        s.ultimo = time.monotonic()
        return s

    def _limpar_sessoes(self):
        """Tira sessões paradas há muito tempo e, se ainda houver demais, as mais antigas."""
        agora = time.monotonic()
        for k, v in list(self.sessoes.items()):
            if agora - v.ultimo > SESSAO_TTL:
                self.sessoes.pop(k, None)
        sobra = len(self.sessoes) - (MAX_SESSOES - 1)
        if sobra > 0:
            for k, _ in sorted(self.sessoes.items(), key=lambda kv: kv[1].ultimo)[:sobra]:
                self.sessoes.pop(k, None)

    def faixa(self, tid):
        f = self.por_id.get(tid)
        if not f:
            raise Erro("Faixa não encontrada.", 404)
        return f

    def _atual(self, s):
        return self.por_id[s.sequencia[-1]] if s.sequencia else None

    def _vibe(self, s):
        return lambda f: musicfinder.vibe_score(f, s.interp)

    def _candidatos(self, s):
        usados = set(s.sequencia) | s.puladas
        livres = [f for f in self.catalogo if f["id"] not in usados]
        if s.bpm_alvo is not None:     # com BPM alvo, a vibe vira só um dos critérios (não filtra)
            return livres
        com_vibe = [f for f in livres if musicfinder.vibe_score(f, s.interp) >= VIBE_MINIMA]
        return com_vibe or livres

    def _melhor(self, s, prev, excluir=()):
        perfil = self.perfil(s.user_id)
        tags = list(s.interp["tags"])
        cands = [f for f in self._candidatos(s) if f["id"] not in excluir]
        if not cands:
            return None
        if prev is None:    # primeira faixa da sequência: não há transição, vale a vibe + perfil
            vibe = self._vibe(s)
            alvo = s.bpm_alvo
            perto = (lambda f: 0.5 * dj.rumo_score(alvo, f["bpm"], alvo)) if alvo is not None else (lambda f: 0.0)
            nota = lambda f: vibe(f) + perto(f) + dj.ajuste_perfil(perfil.bonus(None, f, tags))
            return {"faixa": min(cands, key=lambda f: (-nota(f), f["id"]))}
        ranking = dj.rank_next(prev, cands, self._vibe(s), lambda p, c: perfil.bonus(p, c, tags), s.bpm_alvo,
                               self._pesos())
        return ranking[0]

    def _pesos(self):
        """Pesos da nota aprendidos com o feedback (None enquanto não há dados: valem os pesos manuais)."""
        return self.aprendizado.pesos() if self.aprendizado else None

    def _x(self, s, prev, cand):
        """Os 4 critérios (0 a 1) da transição prev → cand: o que o aprendizado enxerga."""
        t = dj.technical(prev, cand)
        return {"vibe": musicfinder.vibe_score(cand, s.interp), "bpm": t["bpm"], "tom": t["tom"], "energia": t["energia"]}

    def _aprende(self, s, tipo, prev, cand, y):
        """Guarda a transição como exemplo de treino. Com BPM alvo a fórmula é outra, então não conta."""
        if not self.aprendizado or not s.user_id or prev is None or s.bpm_alvo is not None:
            return
        try:
            self.aprendizado.registrar(s.user_id, tipo, prev["id"], cand["id"], self._x(s, prev, cand), y)
        except Exception as e:                # o aprendizado nunca pode atrapalhar quem está ouvindo
            log.warning("Aprendizado: não registrei a transição (%s)", type(e).__name__)

    def _desaprende(self, s, tipo, prev, cand):
        if not self.aprendizado or not s.user_id or prev is None:
            return
        try:
            self.aprendizado.remover(s.user_id, tipo, prev["id"], cand["id"])
        except Exception as e:
            log.warning("Aprendizado: não desfiz a transição (%s)", type(e).__name__)

    def _publica(self, r):
        if r is None:
            return None
        return {**r["faixa"], "nota": r["nota"], "vibe": r["vibe"], "tecnica": r["tecnica"],
                "compatibilidade": r["tecnica"]["percentual"], "classe": r["classe"],
                "arriscada": r["classe"] == "arriscada",
                "motivos": r.get("motivos", []), "rumo": r.get("rumo")}

    def _estado_dj(self, s, caminho, eventos):
        return {"session_id": s.id, "estado": s.estado, "caminho_estados": caminho, "eventos": eventos,
                "interpretacao": self._interp_publica(s.interp),
                "atual": self._pub_faixa(self._atual(s)),
                "sugerida": self._publica(s.sugerida),
                "sequencia": [self._pub_faixa(self.por_id[i]) for i in s.sequencia],
                "pulos_seguidos": s.pulos_seguidos, "bpm_alvo": s.bpm_alvo,
                "pode_desfazer": bool(s.aceites) and bool(s.sequencia) and s.aceites[-1]["faixa_id"] == s.sequencia[-1],
                "pode_voltar": bool(s.volta) or len(s.sequencia) > 1,
                "curtida": bool(s.sequencia) and s.sequencia[-1] in s.curtidas,
                "dica": ("ajustar_vibe" if s.pulos_seguidos >= PULOS_PARA_AJUSTE else None)}

    @staticmethod
    def _pub_faixa(f):
        return dict(f) if f else None

    @staticmethod
    def _interp_publica(i):
        return {"resumo": i["resumo"], "tags": list(i["tags"]), "energia": i["energia"],
                "generos": i["generos"], "tecnico": i["tecnico"]}

    def _sugerir(self, s):
        """Evento ProximaFaixaSolicitada (disparado pelo DJ Intelligent)."""
        s.sugerida = self._melhor(s, self._atual(s))

    def _busca_artista(self, texto, interp):
        """Se o texto cita um artista ("tipo Calvin Harris", "Coldplay"), confirma no Last.fm e troca a vibe por
        'músicas dele + de artistas parecidos'. Devolve um aviso se a fonte falhou, senão None."""
        if not (self.provedor and hasattr(self.provedor, "candidatas_artista")):
            return None
        nome, explicito = musicfinder.candidato_artista(texto, interp["clara"])
        if not nome:
            return None
        try:
            r = self.provedor.candidatas_artista(nome, estrito=not explicito)
        except FonteErro as e:
            return f"Não consegui consultar as fontes de música agora ({e})." if explicito else None
        if not r:
            return None
        oficial, pontos, faixas = r
        self.adicionar_faixas(faixas)
        interp.update(artista=oficial, pontos=pontos, clara=True, energia=None, tags={}, generos=[],
                      resumo=f"Entendi: artista {oficial} e artistas parecidos")
        return None

    # IA na busca: artistas sugeridos e similaridade semântica (ambos opcionais) ---------
    def _pedir_artistas_ia(self, texto):
        """Começa em segundo plano a sugestão de artistas pela IA. None se o recurso não estiver disponível."""
        if self.ia is None or self.max_artistas_ia <= 0 or not hasattr(self.provedor, "candidatas_sugeridas"):
            return None
        return self._pool_ia.submit(sugestor.sugerir, self.ia, texto)

    def _faixas_dos_artistas_ia(self, sugestao, interp):
        """Faixas dos artistas sugeridos, já confirmados no Last.fm e com BPM/tom. Vazio se algo falhar."""
        if sugestao is None:
            return []
        try:
            nomes = sugestao.result(timeout=ESPERA_SUGESTAO_IA)
            if not nomes:
                return []
            return list(self.provedor.candidatas_sugeridas(nomes, interp, self.max_artistas_ia))
        except Exception as e:                      # IA lenta, fonte fora do ar etc.: a busca segue sem as sugestões
            log.warning("Artistas sugeridos pela IA ignorados (%s)", type(e).__name__)
            return []

    def _pontuar_semantica(self, texto, interp, faixas):
        """Nota de similaridade semântica (embeddings) entre a frase e as faixas desta busca."""
        if self.embeddings is None or not faixas:
            return
        unicas = list({f["id"]: f for f in faixas}.values())
        try:
            notas = self.embeddings.pontuar(texto, unicas)
        except Exception as e:
            log.warning("Embeddings ignorados nesta busca (%s)", type(e).__name__)
            return
        if notas:
            interp["semantica"] = notas

    # busca (evento BuscaContextualEfetuada) --------------------------------
    def buscar(self, user_id, texto):
        if texto is not None and not isinstance(texto, str):
            raise Erro("O texto da busca deve ser uma frase.")
        texto = (texto or "").strip()
        if not texto:
            raise Erro("Digite a vibe que você quer ouvir.")
        if len(texto) > MAX_TEXTO_BUSCA:
            raise Erro(f"Descreva a vibe em até {MAX_TEXTO_BUSCA} caracteres.")
        self._limpar_sessoes()
        interp = musicfinder.interpretar(texto)
        aviso_artista = self._busca_artista(texto, interp)
        s = Sessao(user_id, texto, interp)
        s.estado = BUSCANDO
        base = {"session_id": s.id, "eventos": ["BuscaContextualEfetuada"],
                "interpretacao": self._interp_publica(interp)}
        if aviso_artista:
            base["aviso"] = aviso_artista
        self.store.add_history(user_id, "search", query=texto)
        if not interp["clara"]:                                        # D1: vibe pouco clara
            s.estado = INICIO
            return {**base, "estado": INICIO, "caminho_estados": [BUSCANDO, INICIO], "resultados": [],
                    "mensagem": "Não entendi o clima. Tente descrever o momento, por exemplo:",
                    "exemplos": musicfinder.EXEMPLOS}
        perfil, tags = self.perfil(user_id), list(interp["tags"])
        if self.provedor and interp.get("artista") is None:            # modo ao vivo: traz faixas reais da vibe
            sugestao = self._pedir_artistas_ia(texto)                  # a IA pensa enquanto o Last.fm responde
            achadas = []
            try:
                achadas = list(self.provedor.candidatas(interp))
                self.adicionar_faixas(achadas)
            except FonteErro as e:
                base["aviso"] = f"Não consegui consultar as fontes de música agora ({e}). Usando o que já conheço."
            extras = self._faixas_dos_artistas_ia(sugestao, interp)
            self.adicionar_faixas(extras)
            self._pontuar_semantica(texto, interp, achadas + extras)
        achados = musicfinder.buscar(self.catalogo, interp)
        # perfil só reordena os resultados já alinhados à vibe
        achados.sort(key=lambda f: -(f["vibe"] + dj.ajuste_perfil(perfil.bonus(None, f, tags))))
        if not achados:                                                # D4: nada encontrado
            s.estado = SEM_RESULTADOS
            self.sessoes[s.id] = s
            return {**base, "estado": SEM_RESULTADOS, "caminho_estados": [BUSCANDO, SEM_RESULTADOS],
                    "resultados": [], "mensagem": "Nenhuma faixa combina com essa vibe. Tente outra descrição.",
                    "exemplos": musicfinder.EXEMPLOS}
        s.estado = RESULTADOS
        self.sessoes[s.id] = s
        return {**base, "estado": RESULTADOS, "caminho_estados": [BUSCANDO, RESULTADOS], "resultados": achados}

    # Modo DJ ----------------------------------------------------------------
    def tocar(self, sid, track_id):
        s = self.sessao(sid)
        s.aceites.clear()
        s.volta.clear()
        f = self.faixa(track_id)             # pode voltar aos resultados e escolher outra faixa
        s.sequencia = [f["id"]]
        s.pulos_seguidos = 0
        s.sugerida = None
        s.estado = TOCANDO
        self.store.add_history(s.user_id, "play", f["id"], s.consulta)
        self._sugerir(s)
        s.estado = SUGERINDO
        return self._estado_dj(s, [TOCANDO, SUGERINDO], ["ProximaFaixaSolicitada"])

    def aceitar(self, sid):
        s = self.sessao(sid)
        if not s.sugerida:
            raise Erro("Não há sugestão para aceitar.")
        nova, prev = s.sugerida["faixa"], self._atual(s)
        feedback.registrar_positivo(self.perfil(s.user_id), "accept", nova, prev)
        self.store.add_history(s.user_id, "accept", nova["id"], s.consulta)
        self._aprende(s, "accept", prev, nova, 1)
        s.aceites.append({"faixa_id": nova["id"], "sugerida": s.sugerida})   # para o "Desfazer aceite"
        s.sequencia.append(nova["id"])
        s.volta.append({"tipo": "aceite"})
        s.pulos_seguidos = 0
        s.estado = TOCANDO
        self._sugerir(s)
        s.estado = SUGERINDO
        return self._estado_dj(s, [TOCANDO, SUGERINDO], ["ProximaFaixaSolicitada"])

    def desfazer_aceite(self, sid):
        """Volta ao estado de antes do último aceite: a faixa sai da sequência, a mesma sugestão reaparece
        e o +0,5 do aceite é revertido no perfil (sem penalidade, ao contrário de pular)."""
        s = self.sessao(sid)
        if not s.aceites:
            raise Erro("Não há aceite para desfazer.")
        reg = s.aceites.pop()
        if not s.sequencia or s.sequencia[-1] != reg["faixa_id"]:
            s.aceites.clear()
            raise Erro("Não há aceite para desfazer.")
        s.sequencia.pop()
        if s.volta and s.volta[-1]["tipo"] == "aceite":
            s.volta.pop()
        feedback.registrar_positivo(self.perfil(s.user_id), "accept", self.por_id[reg["faixa_id"]], self._atual(s), sinal=-1)
        self.store.add_history(s.user_id, "undo_accept", reg["faixa_id"], s.consulta)
        self._desaprende(s, "accept", self._atual(s), self.por_id[reg["faixa_id"]])
        s.sugerida = reg["sugerida"]
        s.estado = SUGERINDO
        return self._estado_dj(s, [SUGERINDO], ["AceiteDesfeito"])

    def pular(self, sid, alvo="atual", fracao=0.0):
        """Evento FaixaPulada. alvo='atual' pula a que toca; 'sugestao' recusa a sugerida."""
        s = self.sessao(sid)
        s.aceites.clear()
        try:
            fracao = float(fracao or 0.0)
        except (TypeError, ValueError):
            raise Erro("elapsed_fraction inválido: use um número entre 0 e 1.")
        if fracao != fracao:                                           # NaN
            raise Erro("elapsed_fraction inválido: use um número entre 0 e 1.")
        fracao = max(0.0, min(1.0, fracao))
        perfil = self.perfil(s.user_id)
        tags = list(s.interp["tags"])
        if alvo == "sugestao":
            if not s.sugerida:
                raise Erro("Não há sugestão para pular.")
            pulada, prev, pct = s.sugerida["faixa"], self._atual(s), s.sugerida["tecnica"]["percentual"]
            fracao = 0.0   # a sugestão nem chegou a tocar
        else:
            if not s.sequencia:
                raise Erro("Nenhuma faixa está tocando.")
            pulada = self._atual(s)
            prev = self.por_id[s.sequencia[-2]] if len(s.sequencia) > 1 else None
            pct = dj.technical(prev, pulada)["percentual"] if prev else None
            if not self._candidatos(s):      # confere antes de mexer em qualquer coisa: sem troca, nada muda
                raise Erro("Acabaram as faixas disponíveis para esta vibe. Faça uma nova busca ou volte.")
        s.estado = REAJUSTANDO
        info = feedback.registrar_pulo(perfil, pulada, prev, tags, fracao, pct)
        self.store.add_history(s.user_id, "skip", pulada["id"], s.consulta, fracao)
        self._aprende(s, info["tipo"], prev, pulada, 0)
        s.puladas.add(pulada["id"])
        s.pulos_seguidos += 1
        if alvo == "sugestao":
            self._sugerir(s)                                # nova sugestão sobre a mesma faixa atual
        else:
            s.sequencia.pop()
            troca = self._melhor(s, prev)                    # alternativa de maior compatibilidade
            if troca is None:
                raise Erro("Acabaram as faixas disponíveis para esta vibe.")
            s.sequencia.append(troca["faixa"]["id"])
            s.volta.append({"tipo": "pulo", "faixa_id": pulada["id"], "info": info, "tags": tags,
                            "prev_id": prev["id"] if prev else None})
            self._sugerir(s)
        s.estado = SUGERINDO
        r = self._estado_dj(s, [REAJUSTANDO, TOCANDO, SUGERINDO], ["FaixaPulada", "ProximaFaixaSolicitada"])
        r["feedback"] = info
        return r

    def voltar(self, sid):
        """Evento FaixaAnteriorRetomada: volta à faixa anterior. Se ela saiu por um aceite, basta sair da faixa
        atual; se saiu por um pulo, a pulada volta a tocar e o pulo é desfeito no perfil. A faixa que tocava
        vira a sugestão (Aceitar leva de volta a ela). Fora o pulo desfeito, é só navegação."""
        s = self.sessao(sid)
        reg = s.volta.pop() if s.volta else None
        if reg is None and len(s.sequencia) < 2:
            raise Erro("Não há faixa anterior para voltar.")
        s.aceites.clear()
        perfil = self.perfil(s.user_id)
        saiu = self.por_id[s.sequencia.pop()]
        if reg and reg["tipo"] == "pulo":
            pulada = self.por_id[reg["faixa_id"]]
            prev = self.por_id[reg["prev_id"]] if reg["prev_id"] else None
            feedback.desfazer_pulo(perfil, pulada, prev, reg["tags"], reg["info"])
            self._desaprende(s, reg["info"]["tipo"], prev, pulada)
            s.puladas.discard(pulada["id"])
            s.sequencia.append(pulada["id"])
        tags = list(s.interp["tags"])
        s.sugerida = dj.rank_next(self._atual(s), [saiu], self._vibe(s),
                                  lambda p, c: perfil.bonus(p, c, tags), s.bpm_alvo, self._pesos())[0]
        s.pulos_seguidos = 0
        self.store.add_history(s.user_id, "back", saiu["id"], s.consulta)
        s.estado = SUGERINDO
        return self._estado_dj(s, [TOCANDO, SUGERINDO], ["FaixaAnteriorRetomada"])

    def curtir(self, sid):
        """Liga/desliga a curtida da faixa atual. Descurtir desfaz o ajuste que a curtida fez no perfil."""
        s = self.sessao(sid)
        if not s.sequencia:
            raise Erro("Nenhuma faixa está tocando.")
        atual = self._atual(s)
        prev = self.por_id[s.sequencia[-2]] if len(s.sequencia) > 1 else None
        if atual["id"] in s.curtidas:
            s.curtidas.discard(atual["id"])
            feedback.registrar_positivo(self.perfil(s.user_id), "like", atual, prev, sinal=-1)
            self.store.add_history(s.user_id, "unlike", atual["id"], s.consulta)
            self._desaprende(s, "like", prev, atual)
            return {"ok": True, "faixa_id": atual["id"], "curtida": False}
        s.curtidas.add(atual["id"])
        feedback.registrar_positivo(self.perfil(s.user_id), "like", atual, prev)
        self.store.add_history(s.user_id, "like", atual["id"], s.consulta)
        self._aprende(s, "like", prev, atual, 1)
        s.pulos_seguidos = 0
        return {"ok": True, "faixa_id": atual["id"], "curtida": True}

    def ajustar(self, sid, direcao):
        """Atalhos 'mais calma' / 'mais animada' após vários pulos."""
        s = self.sessao(sid)
        s.aceites.clear()
        if direcao not in ("calma", "animada"):
            raise Erro("Direção inválida.")
        base = s.interp["energia"] if s.interp["energia"] is not None else 0.5
        s.interp["energia"] = round(min(0.95, max(0.05, base + (0.2 if direcao == "animada" else -0.2))), 2)
        s.interp["resumo"] = "Ajustei a energia: " + musicfinder.rotulo_energia(s.interp["energia"])
        s.pulos_seguidos = 0
        self._sugerir(s)
        return self._estado_dj(s, [SUGERINDO], ["ProximaFaixaSolicitada"])

    def ajustar_bpm(self, sid, delta=None, alvo=None, auto=False):
        """Controle de BPM do DJ: sobe/desce o alvo (delta), define um valor (alvo) ou volta ao automático."""
        s = self.sessao(sid)
        s.aceites.clear()
        if not s.sequencia:
            raise Erro("Nenhuma faixa está tocando.")
        if auto:
            s.bpm_alvo = None
        else:
            try:
                if alvo is not None:
                    novo = float(alvo)
                elif delta is not None:
                    novo = (s.bpm_alvo if s.bpm_alvo is not None else self._atual(s)["bpm"]) + float(delta)
                else:
                    raise Erro("Informe delta, target ou auto.")
            except (TypeError, ValueError):
                raise Erro("BPM inválido.")
            if novo != novo or novo in (float("inf"), float("-inf")):
                raise Erro("BPM inválido.")
            s.bpm_alvo = int(round(min(BPM_MAX, max(BPM_MIN, novo))))
        s.pulos_seguidos = 0
        s.estado = REAJUSTANDO
        self._sugerir(s)
        s.estado = SUGERINDO
        return self._estado_dj(s, [REAJUSTANDO, SUGERINDO], ["BpmAlvoAlterado", "ProximaFaixaSolicitada"])

    def explicar(self, sid):
        """Explica em linguagem natural por que a faixa sugerida combina com a atual (IA, ou as regras sem IA)."""
        s = self.sessao(sid)
        if not s.sugerida or not s.sequencia:
            raise Erro("Não há sugestão para explicar.")
        r = s.sugerida
        return self.narrador.explicar(self._atual(s), r["faixa"], r["tecnica"], r.get("motivos", []),
                                      s.interp.get("resumo"), s.bpm_alvo)

    # salvar (evento SequenciaSalva) ------------------------------------------
    def salvar(self, sid, titulo=None, tags=None):
        s = self.sessao(sid)
        if len(s.sequencia) < 2:
            raise Erro("Aceite pelo menos uma sugestão antes de salvar a sequência.")
        s.estado = SALVANDO
        titulo = (titulo or "").strip() or s.consulta.capitalize()
        tags = tags if tags else list(s.interp["tags"])[:4]
        perfil = self.perfil(s.user_id)
        for a, b in zip(s.sequencia, s.sequencia[1:]):
            feedback.registrar_positivo(perfil, "save", self.por_id[b], self.por_id[a])
            self._aprende(s, "save", self.por_id[a], self.por_id[b], 1)
        self.store.add_history(s.user_id, "save", query=s.consulta)
        pid = self.store.save_playlist(s.user_id, titulo, tags, list(s.sequencia))
        s.estado = SALVA
        return {"estado": SALVA, "caminho_estados": [SALVANDO, SALVA], "eventos": ["SequenciaSalva"],
                "playlist_id": pid, "link": f"/p/{pid}", "titulo": titulo, "tags": tags}

    def continuar_playlist(self, user_id, pid):
        """Reabre uma playlist salva e volta ao Modo DJ a partir da última faixa."""
        pl = self.store.get_playlist(pid)
        if not pl or pl["user_id"] != user_id:
            raise Erro("Playlist não encontrada.", 404)
        faixas = [self.por_id[i] for i in pl["track_ids"]]
        energia = round(sum(f["energia"] for f in faixas) / len(faixas), 2)
        interp = {"clara": True, "tags": {t: 1 for t in pl["tags"]}, "energia": energia, "generos": [],
                  "tecnico": False, "termos": [], "resumo": f"Continuando “{pl['title']}”", "exemplos": []}
        self._limpar_sessoes()
        s = Sessao(user_id, pl["title"], interp)
        s.sequencia = list(pl["track_ids"])
        self.sessoes[s.id] = s
        self._sugerir(s)
        s.estado = SUGERINDO
        return self._estado_dj(s, [TOCANDO, SUGERINDO], ["ProximaFaixaSolicitada"])
