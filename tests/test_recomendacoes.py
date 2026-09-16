import unittest

import pandas as pd

from app.recomendacoes import priorizar_fornecedores, resumir_recomendacoes


class RecomendacoesTest(unittest.TestCase):
    def setUp(self):
        self.metricas = pd.DataFrame([
            {"usuario_id": "U1", "segmento_regra": "Engajado convertendo", "recencia_dias": 1,
             "propostas_enviadas": 2, "bateu_bloqueio": False},
            {"usuario_id": "U2", "segmento_regra": "Inativo — risco de perda", "recencia_dias": 45,
             "propostas_enviadas": 1, "bateu_bloqueio": False},
            {"usuario_id": "U4", "segmento_regra": "Bloqueado — taxa de acesso", "recencia_dias": 3,
             "propostas_enviadas": 0, "bateu_bloqueio": True},
            {"usuario_id": "U3", "segmento_regra": "Bloqueado — taxa de acesso", "recencia_dias": 3,
             "propostas_enviadas": 0, "bateu_bloqueio": True},
        ])

    def test_prioridade_e_evidencia_sem_contar_engajados(self):
        original = self.metricas.copy(deep=True)
        fila = priorizar_fornecedores(self.metricas)
        self.assertEqual(fila.usuario_id.tolist(), ["U3", "U4", "U2", "U1"])
        resumo = resumir_recomendacoes(self.metricas)
        self.assertEqual([r["quantidade"] for r in resumo], [2, 1])
        self.assertEqual(sum(r["quantidade"] for r in resumo), int(fila.prioridade.gt(0).sum()))
        self.assertIn("0 sem proposta", resumo[1]["evidencia"])
        self.assertIn("45 dias", resumo[1]["evidencia"])
        pd.testing.assert_frame_equal(self.metricas, original)

    def test_sem_candidatos(self):
        self.assertEqual(resumir_recomendacoes(self.metricas.iloc[:1]), [])
        self.assertEqual(resumir_recomendacoes(self.metricas.iloc[:0]), [])
        self.assertTrue(priorizar_fornecedores(self.metricas.iloc[:0]).empty)


if __name__ == "__main__":
    unittest.main()
