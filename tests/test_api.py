"""Fluxo ponta a ponta pela API (os estados e eventos dos documentos 3 e 4)."""
import os
import pathlib
import unittest
from app import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(":memory:", catalog_path=str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json"))
        self.c = self.app.test_client()
        self.uid = "u_teste"

    def post(self, url, **b):
        return self.c.post(url, json={"user_id": self.uid, **b})

    def iniciar(self, texto="música calma para estudar à noite"):
        r = self.post("/api/search", text=texto).get_json()
        return r, r["session_id"]

    def tocar(self):
        r, sid = self.iniciar()
        d = self.post(f"/api/session/{sid}/play", track_id=r["resultados"][0]["id"]).get_json()
        return sid, d

    def test_busca_gera_resultados(self):
        r, _ = self.iniciar()
        self.assertEqual(r["estado"], "resultados")
        self.assertEqual(r["eventos"], ["BuscaContextualEfetuada"])
        self.assertTrue(r["resultados"])

    def test_d1_vibe_pouco_clara(self):
        r, _ = self.iniciar("asdf qwer")
        self.assertEqual(r["estado"], "inicio")
        self.assertTrue(r["exemplos"])

    def test_busca_vazia_da_erro(self):
        self.assertEqual(self.post("/api/search", text="  ").status_code, 400)

    def test_busca_com_texto_nao_string_da_400(self):
        for valor in (123, ["a"], {"x": 1}):
            self.assertEqual(self.post("/api/search", text=valor).status_code, 400)

    def test_pular_com_fracao_invalida_da_400(self):
        sid, _ = self.tocar()
        for valor in ("abc", [1], {"a": 1}):
            r = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=valor)
            self.assertEqual(r.status_code, 400, valor)
            self.assertIn("erro", r.get_json())

    def test_bpm_com_valor_invalido_da_400(self):
        sid, _ = self.tocar()
        for corpo in ({"target": "abc"}, {"delta": [1]}, {"target": "nan"}, {"target": "inf"}):
            self.assertEqual(self.post(f"/api/session/{sid}/bpm", **corpo).status_code, 400, corpo)

    def test_modo_dj_sugere_com_percentual(self):
        _, d = self.tocar()
        self.assertEqual(d["estado"], "sugerindo_proxima")
        self.assertEqual(d["caminho_estados"], ["tocando", "sugerindo_proxima"])
        self.assertIn("ProximaFaixaSolicitada", d["eventos"])
        self.assertTrue(0 <= d["sugerida"]["compatibilidade"] <= 100)

    def test_aceitar_avanca_sequencia_sem_repetir(self):
        sid, d = self.tocar()
        vistos = {d["atual"]["id"]}
        for _ in range(6):
            d = self.post(f"/api/session/{sid}/accept").get_json()
            self.assertNotIn(d["atual"]["id"], vistos)
            vistos.add(d["atual"]["id"])
        self.assertEqual(len(d["sequencia"]), 7)

    def test_pular_troca_a_faixa_na_hora_e_registra(self):
        sid, d = self.tocar()
        d = self.post(f"/api/session/{sid}/accept").get_json()
        pulada = d["atual"]["id"]
        d = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.1).get_json()
        self.assertEqual(d["caminho_estados"], ["reajustando", "tocando", "sugerindo_proxima"])
        self.assertIn("FaixaPulada", d["eventos"])
        self.assertNotEqual(d["atual"]["id"], pulada)
        self.assertEqual(d["feedback"]["tipo"], "skip_early")
        # a faixa pulada não volta nesta sessão
        for _ in range(5):
            d = self.post(f"/api/session/{sid}/accept").get_json()
            self.assertNotEqual(d["atual"]["id"], pulada)

    def test_pular_a_primeira_faixa_troca_sem_erro(self):
        sid, d = self.tocar()
        primeira = d["atual"]["id"]
        r = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.1)
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertNotEqual(d["atual"]["id"], primeira)
        self.assertEqual(len(d["sequencia"]), 1)
        self.assertIsNotNone(d["sugerida"])

    def test_voltar_aos_resultados_e_tocar_outra(self):
        r, sid = self.iniciar()
        self.post(f"/api/session/{sid}/play", track_id=r["resultados"][0]["id"])
        self.post(f"/api/session/{sid}/accept")
        d = self.post(f"/api/session/{sid}/play", track_id=r["resultados"][1]["id"]).get_json()
        self.assertEqual([f["id"] for f in d["sequencia"]], [r["resultados"][1]["id"]])
        self.assertEqual(d["pulos_seguidos"], 0)

    def test_controle_de_bpm_sobe_o_set(self):
        sid, d = self.tocar()
        inicio = d["atual"]["bpm"]
        self.assertIsNone(d["bpm_alvo"])
        d = self.post(f"/api/session/{sid}/bpm", delta=5).get_json()
        self.assertEqual(d["bpm_alvo"], inicio + 5)
        self.assertIn("BpmAlvoAlterado", d["eventos"])
        self.assertTrue(d["sugerida"]["motivos"])
        for _ in range(8):
            self.post(f"/api/session/{sid}/bpm", delta=5)
            d = self.post(f"/api/session/{sid}/accept").get_json()
        self.assertEqual(d["bpm_alvo"], inicio + 45)
        self.assertGreater(d["atual"]["bpm"], inicio + 15)

    def test_controle_de_bpm_desce_o_set(self):
        r, sid = self.iniciar("festa animada para dançar")
        d = self.post(f"/api/session/{sid}/play", track_id=r["resultados"][0]["id"]).get_json()
        inicio = d["atual"]["bpm"]
        for _ in range(6):
            self.post(f"/api/session/{sid}/bpm", delta=-5)
            d = self.post(f"/api/session/{sid}/accept").get_json()
        self.assertLess(d["atual"]["bpm"], inicio - 5)

    def test_bpm_alvo_direto_automatico_e_limites(self):
        sid, d = self.tocar()
        d = self.post(f"/api/session/{sid}/bpm", target=120).get_json()
        self.assertEqual(d["bpm_alvo"], 120)
        self.assertEqual(self.post(f"/api/session/{sid}/bpm", target=999).get_json()["bpm_alvo"], 200)
        self.assertEqual(self.post(f"/api/session/{sid}/bpm", target=1).get_json()["bpm_alvo"], 50)
        self.assertIsNone(self.post(f"/api/session/{sid}/bpm", auto=True).get_json()["bpm_alvo"])
        self.assertEqual(self.post(f"/api/session/{sid}/bpm", target="abc").status_code, 400)
        self.assertEqual(self.post(f"/api/session/{sid}/bpm").status_code, 400)

    def test_bpm_sem_faixa_tocando(self):
        _, sid = self.iniciar()
        self.assertEqual(self.post(f"/api/session/{sid}/bpm", delta=5).status_code, 400)

    def test_com_alvo_a_ia_ignora_o_filtro_de_vibe(self):
        sid, d = self.tocar()                      # vibe calma: o catálogo calmo é lento
        d = self.post(f"/api/session/{sid}/bpm", target=140).get_json()
        for _ in range(12):
            d = self.post(f"/api/session/{sid}/accept").get_json()
        self.assertGreater(max(f["bpm"] for f in d["sequencia"]), 110)

    def test_pulo_depois_da_metade_pesa_menos(self):
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        d = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.9).get_json()
        self.assertEqual(d["feedback"]["tipo"], "skip_late")

    def test_varios_pulos_oferecem_ajuste_da_vibe(self):
        sid, d = self.tocar()
        for _ in range(3):
            d = self.post(f"/api/session/{sid}/skip", target="sugestao").get_json()
        self.assertEqual(d["dica"], "ajustar_vibe")
        e0 = d["interpretacao"]["energia"]
        d = self.post(f"/api/session/{sid}/adjust", direction="animada").get_json()
        self.assertGreater(d["interpretacao"]["energia"], e0)
        self.assertIsNone(d["dica"])

    def test_curtir_de_novo_tira_a_curtida_e_desfaz_o_perfil(self):
        sid, d = self.tocar()
        self.assertFalse(d["curtida"])
        r1 = self.post(f"/api/session/{sid}/like").get_json()
        self.assertTrue(r1["curtida"])
        pesos = {k: round(v[0], 6) for k, v in self.app.store.get_weights(self.uid).items()}
        self.assertTrue(any(v > 0 for v in pesos.values()))
        r2 = self.post(f"/api/session/{sid}/like").get_json()
        self.assertFalse(r2["curtida"])
        zerados = [v for k, v in self.app.store.get_weights(self.uid).items() if abs(v[0]) > 1e-6]
        self.assertEqual(zerados, [])
        self.assertTrue(self.post(f"/api/session/{sid}/like").get_json()["curtida"])

    def test_estado_do_dj_informa_se_a_faixa_esta_curtida(self):
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/like")
        d = self.post(f"/api/session/{sid}/bpm", delta=5).get_json()
        self.assertTrue(d["curtida"])
        d = self.post(f"/api/session/{sid}/accept").get_json()
        self.assertFalse(d["curtida"])      # a nova faixa atual ainda não foi curtida

    def test_desfazer_aceite_volta_a_sugestao_e_reverte_o_perfil(self):
        sid, d0 = self.tocar()
        self.assertFalse(d0["pode_desfazer"])
        sugerida = d0["sugerida"]["faixa"]["id"] if "faixa" in d0["sugerida"] else d0["sugerida"]["id"]
        d1 = self.post(f"/api/session/{sid}/accept").get_json()
        self.assertTrue(d1["pode_desfazer"])
        self.assertEqual(len(d1["sequencia"]), 2)
        d2 = self.post(f"/api/session/{sid}/undo-accept").get_json()
        self.assertEqual(len(d2["sequencia"]), 1)
        self.assertFalse(d2["pode_desfazer"])
        self.assertEqual(d2["eventos"], ["AceiteDesfeito"])
        self.assertEqual(d2["sugerida"]["faixa"]["id"] if "faixa" in d2["sugerida"] else d2["sugerida"]["id"], sugerida)
        self.assertEqual([k for k, v in self.app.store.get_weights(self.uid).items() if abs(v[0]) > 1e-6], [])
        tipos = [h["type"] for h in self.app.store.history(self.uid)]
        self.assertIn("undo_accept", tipos)
        self.assertEqual(self.post(f"/api/session/{sid}/undo-accept").status_code, 400)
        # aceitar de novo a mesma sugestão funciona
        d3 = self.post(f"/api/session/{sid}/accept").get_json()
        self.assertEqual(d3["atual"]["id"], sugerida)

    def test_voltar_retorna_a_faixa_anterior_e_a_que_tocava_vira_sugestao(self):
        sid, d0 = self.tocar()
        primeira = d0["atual"]["id"]
        self.assertFalse(d0["pode_voltar"])
        d1 = self.post(f"/api/session/{sid}/accept").get_json()
        d2 = self.post(f"/api/session/{sid}/accept").get_json()
        segunda, terceira = d1["atual"]["id"], d2["atual"]["id"]
        self.assertTrue(d2["pode_voltar"])
        d3 = self.post(f"/api/session/{sid}/back").get_json()
        self.assertEqual(d3["atual"]["id"], segunda)
        self.assertEqual([f["id"] for f in d3["sequencia"]], [primeira, segunda])
        self.assertEqual(d3["sugerida"]["id"], terceira)       # Aceitar leva de volta a ela
        self.assertEqual(d3["eventos"], ["FaixaAnteriorRetomada"])
        self.assertFalse(d3["pode_desfazer"])
        d4 = self.post(f"/api/session/{sid}/back").get_json()
        self.assertEqual(d4["atual"]["id"], primeira)
        self.assertFalse(d4["pode_voltar"])
        self.assertEqual(d4["sugerida"]["id"], segunda)
        d5 = self.post(f"/api/session/{sid}/accept").get_json()
        self.assertEqual(d5["atual"]["id"], segunda)

    def test_voltar_depois_de_pular_retoma_a_pulada_e_desfaz_o_pulo(self):
        sid, d0 = self.tocar()
        self.assertFalse(d0["pode_voltar"])
        primeira = d0["atual"]["id"]
        d1 = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.1).get_json()
        troca = d1["atual"]["id"]
        self.assertNotEqual(troca, primeira)
        self.assertTrue(d1["pode_voltar"])                      # vale mesmo sem nenhum aceite
        d2 = self.post(f"/api/session/{sid}/back").get_json()
        self.assertEqual(d2["atual"]["id"], primeira)
        self.assertEqual([f["id"] for f in d2["sequencia"]], [primeira])
        self.assertEqual(d2["sugerida"]["id"], troca)
        self.assertFalse(d2["pode_voltar"])
        self.assertEqual([k for k, v in self.app.store.get_weights(self.uid).items() if abs(v[0]) > 1e-6], [])
        self.assertEqual(self.post(f"/api/session/{sid}/back").status_code, 400)

    def test_voltar_varios_pulos_seguidos_e_misturados_com_aceite(self):
        sid, d0 = self.tocar()
        a = d0["atual"]["id"]
        b = self.post(f"/api/session/{sid}/accept").get_json()["atual"]["id"]
        c = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.1).get_json()["atual"]["id"]
        d = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.1).get_json()["atual"]["id"]
        self.assertEqual([self.post(f"/api/session/{sid}/back").get_json()["atual"]["id"] for _ in range(2)], [c, b])
        self.assertEqual(self.post(f"/api/session/{sid}/back").get_json()["atual"]["id"], a)
        self.assertEqual(self.post(f"/api/session/{sid}/back").status_code, 400)
        self.assertNotIn(d, [a, b, c])

    def test_pular_sem_faixas_sobrando_nao_perde_a_faixa_atual(self):
        sid, d = self.tocar()
        for _ in range(200):
            r = self.post(f"/api/session/{sid}/skip", target="atual", elapsed_fraction=0.1)
            if r.status_code != 200:
                break
            d = r.get_json()
        self.assertEqual(r.status_code, 400)
        s = self.app.motor.sessoes[sid]
        self.assertEqual(s.sequencia, [d["atual"]["id"]])           # a faixa que tocava continua lá
        self.assertEqual(self.post(f"/api/session/{sid}/like").status_code, 200)
        self.assertEqual(self.post(f"/api/session/{sid}/back").status_code, 200)   # e o Voltar ainda funciona

    def test_voltar_sem_faixa_anterior_da_400(self):
        sid, _ = self.tocar()
        self.assertEqual(self.post(f"/api/session/{sid}/back").status_code, 400)

    def test_voltar_nao_conta_como_pulo_nem_mexe_no_perfil(self):
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        antes = self.app.store.get_weights(self.uid)
        d = self.post(f"/api/session/{sid}/back").get_json()
        self.assertEqual(d["pulos_seguidos"], 0)
        self.assertEqual(self.app.store.get_weights(self.uid), antes)
        self.assertIn("back", [h["type"] for h in self.app.store.history(self.uid)])

    # --- publicação: limites e proteções ---------------------------------------
    def test_codigo_de_usuario_invalido_e_ignorado(self):
        for ruim in ("../../etc", "a" * 65, "com espaço", 123, ""):
            r = self.c.post("/api/search", json={"user_id": ruim, "text": "música calma para estudar à noite"})
            self.assertEqual(r.status_code, 200)
        self.assertEqual(self.app.store.history("../../etc"), [])
        self.assertEqual(self.c.get("/api/history?user_id=" + "a" * 65).get_json(), {"historico": []})

    def test_busca_muito_longa_da_400(self):
        r = self.post("/api/search", text="calma " * 60)
        self.assertEqual(r.status_code, 400)
        self.assertIn("200", r.get_json()["erro"])

    def test_limite_de_buscas_por_minuto_responde_429(self):
        app = create_app(":memory:", catalog_path=str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json"),
                         buscas_por_minuto=3)
        c = app.test_client()
        codigos = [c.post("/api/search", json={"text": "música calma"}).status_code for _ in range(5)]
        self.assertEqual(codigos[:3], [200, 200, 200])
        self.assertEqual(codigos[3:], [429, 429])

    def test_sessoes_paradas_expiram_e_o_total_tem_teto(self):
        from soulsbpm import engine
        _, sid = self.iniciar()
        self.app.motor.sessoes[sid].ultimo -= engine.SESSAO_TTL + 1
        _, outra = self.iniciar()                              # uma nova busca limpa as expiradas
        self.assertNotIn(sid, self.app.motor.sessoes)
        self.assertEqual(self.post(f"/api/session/{sid}/accept").status_code, 404)
        antigo = engine.MAX_SESSOES
        try:
            engine.MAX_SESSOES = 3
            for _ in range(6):
                self.iniciar()
            self.assertLessEqual(len(self.app.motor.sessoes), 3)
        finally:
            engine.MAX_SESSOES = antigo

    def test_cabecalhos_de_seguranca_e_erros_em_json(self):
        r = self.c.get("/api/health")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        r404 = self.c.get("/api/nao-existe")
        self.assertEqual(r404.status_code, 404)
        self.assertIn("erro", r404.get_json())

    def test_erro_inesperado_vira_json_500_sem_vazar_detalhes(self):
        def quebra(*a, **k):
            raise RuntimeError("segredo interno")
        self.app.motor.buscar = quebra
        r = self.post("/api/search", text="calma")
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("segredo", r.get_data(as_text=True))

    def test_pasta_de_dados_configuravel_por_variavel(self):
        import tempfile
        d = tempfile.mkdtemp()
        os.environ["SOULSBPM_DATA"] = d
        try:
            create_app(catalog_path=str(pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json"))
        finally:
            os.environ.pop("SOULSBPM_DATA", None)
        self.assertTrue((pathlib.Path(d) / "soulsbpm.db").exists())

    def test_outra_acao_invalida_o_desfazer(self):
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        d = self.post(f"/api/session/{sid}/bpm", delta=5).get_json()
        self.assertFalse(d["pode_desfazer"])
        self.assertEqual(self.post(f"/api/session/{sid}/undo-accept").status_code, 400)

    def entrar(self):
        """Playlists só existem em conta: cria e entra numa conta de teste."""
        self.c.post("/api/auth/register", json={"nome": "tester", "senha": "senha-forte-1"})

    def test_salvar_exige_sequencia_e_gera_link(self):
        self.entrar()
        sid, _ = self.tocar()
        self.assertEqual(self.post(f"/api/session/{sid}/save", title="x").status_code, 400)
        self.post(f"/api/session/{sid}/accept")
        s = self.post(f"/api/session/{sid}/save", title="Minha noite").get_json()
        self.assertEqual(s["estado"], "playlist_salva")
        self.assertEqual(s["eventos"], ["SequenciaSalva"])
        pub = self.c.get(s["link"].replace("/p/", "/api/playlists/")).get_json()
        self.assertEqual(pub["title"], "Minha noite")
        self.assertEqual(len(pub["faixas"]), 2)
        self.assertNotIn("user_id", pub)                     # link público não expõe o dono
        self.assertEqual(self.c.get(s["link"]).status_code, 200)   # página compartilhável

    def test_continuar_playlist(self):
        self.entrar()
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        s = self.post(f"/api/session/{sid}/save", title="x").get_json()
        d = self.post(f"/api/playlists/{s['playlist_id']}/continue").get_json()
        self.assertEqual(len(d["sequencia"]), 2)
        self.assertIsNotNone(d["sugerida"])
        outro = self.app.test_client().post(f"/api/playlists/{s['playlist_id']}/continue", json={"user_id": "outro"})
        self.assertEqual(outro.status_code, 404)

    def test_aprendizado_muda_as_proximas_sugestoes(self):
        """Quem pula forte uma faixa não volta a vê-la na próxima sessão."""
        r, sid = self.iniciar()
        d = self.post(f"/api/session/{sid}/play", track_id=r["resultados"][0]["id"]).get_json()
        alvo = d["sugerida"]["id"]
        for _ in range(3):
            d = self.post(f"/api/session/{sid}/skip", target="sugestao").get_json()
        r2, sid2 = self.iniciar()
        d2 = self.post(f"/api/session/{sid2}/play", track_id=r["resultados"][0]["id"]).get_json()
        sugestoes_antes = alvo
        self.assertNotEqual(d2["sugerida"]["id"], sugestoes_antes)

    def test_privacidade_apagar_e_zerar(self):
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/skip", target="sugestao")
        self.assertTrue(self.c.get("/api/history?user_id=" + self.uid).get_json()["historico"])
        self.c.delete("/api/history?user_id=" + self.uid)
        self.assertEqual(self.c.get("/api/history?user_id=" + self.uid).get_json()["historico"], [])
        self.c.delete("/api/profile?user_id=" + self.uid)
        self.assertEqual(self.c.get("/api/profile?user_id=" + self.uid).get_json()["total_pesos"], 0)

    def test_sem_consentimento_nada_e_guardado(self):
        r = self.c.post("/api/search", json={"text": "música calma"}).get_json()   # sem user_id
        self.assertEqual(r["estado"], "resultados")
        self.assertEqual(self.app.store.history(None), [])
        self.assertEqual(self.c.get("/api/recent").get_json()["buscas"], [])

    def test_sessao_inexistente(self):
        self.assertEqual(self.post("/api/session/nao-existe/accept").status_code, 404)


if __name__ == "__main__":
    unittest.main()


class SemResultadosTests(unittest.TestCase):
    """D4: catálogo sem nada que combine com a vibe leva ao estado 'Sem resultados'."""

    def test_sem_resultados(self):
        import json, pathlib, tempfile
        cat = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "catalog.json").read_text("utf-8"))
        so_rock = [f for f in cat if f["generos"] == ["rock"]]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(so_rock, fh)
        c = create_app(":memory:", catalog_path=fh.name).test_client()
        r = c.post("/api/search", json={"user_id": "u", "text": "dormir com música calma"}).get_json()
        self.assertEqual(r["estado"], "sem_resultados")
        self.assertEqual(r["caminho_estados"], ["buscando", "sem_resultados"])
        self.assertEqual(r["resultados"], [])
        self.assertTrue(r["mensagem"])


class TestSemChaves(unittest.TestCase):
    def test_sem_chaves_nao_cai_no_catalogo_de_amostra(self):
        import os
        from app import SemChaves
        antigo = {k: os.environ.pop(k, None) for k in ("LASTFM_API_KEY", "GETSONGBPM_API_KEY", "SOULSBPM_CATALOG")}
        try:
            with self.assertRaises(SemChaves):
                create_app(":memory:")
        finally:
            for k, v in antigo.items():
                if v is not None:
                    os.environ[k] = v

    def test_carregar_env_aceita_arquivo_com_bom_do_windows(self):
        import tempfile
        from app import carregar_env
        os.environ.pop("CHAVE_BOM_TESTE", None)
        with tempfile.NamedTemporaryFile("wb", suffix=".env", delete=False) as fh:
            fh.write("\ufeffCHAVE_BOM_TESTE=abc123\r\n".encode("utf-8"))
        carregar_env(fh.name)
        self.assertEqual(os.environ.get("CHAVE_BOM_TESTE"), "abc123")
        os.environ.pop("CHAVE_BOM_TESTE", None)

    def test_carregar_env_le_chaves_sem_sobrescrever(self):
        import os
        import tempfile
        from app import carregar_env
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as fh:
            fh.write('# c\nXX_TESTE_A="abc"\nXX_TESTE_B=\nXX_TESTE_C=nova\n')
        os.environ["XX_TESTE_C"] = "antiga"
        carregar_env(fh.name)
        self.assertEqual(os.environ["XX_TESTE_A"], "abc")
        self.assertNotIn("XX_TESTE_B", os.environ)
        self.assertEqual(os.environ["XX_TESTE_C"], "antiga")
        for k in ("XX_TESTE_A", "XX_TESTE_C"):
            os.environ.pop(k, None)
