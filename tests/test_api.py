"""Fluxo ponta a ponta pela API (os estados e eventos dos documentos 3 e 4)."""
import unittest
from app import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(":memory:")
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

    def test_outra_acao_invalida_o_desfazer(self):
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        d = self.post(f"/api/session/{sid}/bpm", delta=5).get_json()
        self.assertFalse(d["pode_desfazer"])
        self.assertEqual(self.post(f"/api/session/{sid}/undo-accept").status_code, 400)

    def test_salvar_exige_sequencia_e_gera_link(self):
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
        sid, _ = self.tocar()
        self.post(f"/api/session/{sid}/accept")
        s = self.post(f"/api/session/{sid}/save", title="x").get_json()
        d = self.post(f"/api/playlists/{s['playlist_id']}/continue").get_json()
        self.assertEqual(len(d["sequencia"]), 2)
        self.assertIsNotNone(d["sugerida"])
        outro = self.c.post(f"/api/playlists/{s['playlist_id']}/continue", json={"user_id": "outro"})
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
        cat = json.loads((pathlib.Path(__file__).resolve().parent.parent / "data" / "catalog.json").read_text("utf-8"))
        so_rock = [f for f in cat if f["generos"] == ["rock"]]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(so_rock, fh)
        c = create_app(":memory:", catalog_path=fh.name).test_client()
        r = c.post("/api/search", json={"user_id": "u", "text": "dormir com música calma"}).get_json()
        self.assertEqual(r["estado"], "sem_resultados")
        self.assertEqual(r["caminho_estados"], ["buscando", "sem_resultados"])
        self.assertEqual(r["resultados"], [])
        self.assertTrue(r["mensagem"])
