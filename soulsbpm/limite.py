"""Limite simples de uso por chave (ex.: IP): no máximo N pedidos por janela de tempo, em memória."""
import threading
import time


class LimiteJanela:
    def __init__(self, maximo, janela=60.0, agora=time.monotonic):
        self.maximo, self.janela, self.agora = maximo, janela, agora
        self._h, self._trava = {}, threading.Lock()

    def permite(self, chave):
        t = self.agora()
        with self._trava:
            recentes = [x for x in self._h.get(chave, []) if t - x < self.janela]
            if len(recentes) >= self.maximo:
                self._h[chave] = recentes
                return False
            recentes.append(t)
            self._h[chave] = recentes
            if len(self._h) > 10000:                       # não deixa a tabela crescer sem fim
                self._h = {k: v for k, v in self._h.items() if v and t - v[-1] < self.janela}
            return True
