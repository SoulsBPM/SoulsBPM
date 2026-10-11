"""Orquestra a sessão: estados do documento 4, eventos do documento 3 e decisões D1–D5."""
import secrets

from .fontes import FonteErro
from . import dj, feedback, musicfinder

# estados (documento 4)
INICIO, BUSCANDO, RESULTADOS, SEM_RESULTADOS = "inicio", "buscando", "resultados", "sem_resultados"
TOCANDO, SUGERINDO, REAJUSTANDO = "tocando", "sugerindo_proxima", "reajustando"
SALVANDO, SALVA = "salvando", "playlist_salva"

PULOS_PARA_AJUSTE = 3
BPM_MIN, BPM_MAX, BPM_PASSO = 50, 200, 5
VIBE_MINIMA = 0.3


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
        self.curtidas = set()      # faixas curtidas nesta sessão (curtir de novo desfaz)
        self.bpm_alvo = None       # BPM que o DJ quer atingir (None = a IA segue só a vibe)


class Motor:
    def __init__(self, catalogo, store, agora=None, provedor=None):
        self.catalogo = list(catalogo)
        self.por_id = {f["id"]: f for f in self.catalogo}
        self.store = store
        self.agora = agora
        self.sessoes = {}
        self.provedor = provedor              # modo ao vivo: busca faixas reais a cada vibe (soulsbpm/aovivo.py)
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
        return s

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
        ranking = dj.rank_next(prev, cands, self._vibe(s), lambda p, c: perfil.bonus(p, c, tags), s.bpm_alvo)
        return ranking[0]

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

    # busca (evento BuscaContextualEfetuada) --------------------------------
    def buscar(self, user_id, texto):
        if texto is not None and not isinstance(texto, str):
            raise Erro("O texto da busca deve ser uma frase.")
        texto = (texto or "").strip()
        if not texto:
            raise Erro("Digite a vibe que você quer ouvir.")
        interp = musicfinder.interpretar(texto)
        s = Sessao(user_id, texto, interp)
        s.estado = BUSCANDO
        base = {"session_id": s.id, "eventos": ["BuscaContextualEfetuada"],
                "interpretacao": self._interp_publica(interp)}
        self.store.add_history(user_id, "search", query=texto)
        if not interp["clara"]:                                        # D1: vibe pouco clara
            s.estado = INICIO
            return {**base, "estado": INICIO, "caminho_estados": [BUSCANDO, INICIO], "resultados": [],
                    "mensagem": "Não entendi o clima. Tente descrever o momento, por exemplo:",
                    "exemplos": musicfinder.EXEMPLOS}
        perfil, tags = self.perfil(user_id), list(interp["tags"])
        if self.provedor:                                              # modo ao vivo: traz faixas reais da vibe
            try:
                self.adicionar_faixas(self.provedor.candidatas(interp))
            except FonteErro as e:
                base["aviso"] = f"Não consegui consultar as fontes de música agora ({e}). Usando o que já conheço."
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
        s.aceites.append({"faixa_id": nova["id"], "sugerida": s.sugerida})   # para o "Desfazer aceite"
        s.sequencia.append(nova["id"])
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
        feedback.registrar_positivo(self.perfil(s.user_id), "accept", self.por_id[reg["faixa_id"]], self._atual(s), sinal=-1)
        self.store.add_history(s.user_id, "undo_accept", reg["faixa_id"], s.consulta)
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
        s.estado = REAJUSTANDO
        info = feedback.registrar_pulo(perfil, pulada, prev, tags, fracao, pct)
        self.store.add_history(s.user_id, "skip", pulada["id"], s.consulta, fracao)
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
            self._sugerir(s)
        s.estado = SUGERINDO
        r = self._estado_dj(s, [REAJUSTANDO, TOCANDO, SUGERINDO], ["FaixaPulada", "ProximaFaixaSolicitada"])
        r["feedback"] = info
        return r

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
            return {"ok": True, "faixa_id": atual["id"], "curtida": False}
        s.curtidas.add(atual["id"])
        feedback.registrar_positivo(self.perfil(s.user_id), "like", atual, prev)
        self.store.add_history(s.user_id, "like", atual["id"], s.consulta)
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
        s = Sessao(user_id, pl["title"], interp)
        s.sequencia = list(pl["track_ids"])
        self.sessoes[s.id] = s
        self._sugerir(s)
        s.estado = SUGERINDO
        return self._estado_dj(s, [TOCANDO, SUGERINDO], ["ProximaFaixaSolicitada"])
