import unittest

import pandas as pd

from app.analise_jornada import calcular_funil, maior_gargalo


class FunilTest(unittest.TestCase):
    def eventos(self, sessoes):
        return pd.DataFrame([
            {"session_id": sid, "pagina": pagina, "timestamp": pd.Timestamp("2026-09-16"),
             "ordem_na_sessao": i}
            for sid, paginas in enumerate(sessoes)
            for i, pagina in enumerate(paginas)
        ], columns=["session_id", "pagina", "timestamp", "ordem_na_sessao"])

    def test_ordem_repeticoes_e_entradas_diretas(self):
        eventos = self.eventos([
            ["home_publica", "home_publica", "avisos", "detalhe_oportunidade_publica",
             "tenho_interesse", "login", "envio_proposta", "envio_proposta"],
            ["login", "home_publica", "detalhe_oportunidade_publica", "tenho_interesse", "envio_proposta"],
            ["envio_proposta"],
        ])
        funil = calcular_funil(eventos.iloc[::-1])
        self.assertEqual(funil["Sessões na sequência"].tolist(), [2, 2, 2, 1, 1])
        self.assertEqual(funil["Alcance independente"].tolist(), [2, 2, 2, 2, 3])
        self.assertEqual(maior_gargalo(funil)["perdas"], 1)

    def test_nao_costura_sessoes(self):
        funil = calcular_funil(self.eventos([["home_publica"], ["detalhe_oportunidade_publica", "tenho_interesse"]]))
        self.assertEqual(funil["Sessões na sequência"].tolist(), [1, 0, 0, 0, 0])

    def test_vazio(self):
        funil = calcular_funil(self.eventos([]))
        self.assertEqual(funil["Sessões na sequência"].sum(), 0)
        self.assertIsNone(maior_gargalo(funil))


if __name__ == "__main__":
    unittest.main()
