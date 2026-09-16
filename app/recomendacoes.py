"""Prioridades de negócio e evidências para revisão humana de contatos."""

PRIORIDADE_SEGMENTO = {
    "Bloqueado — taxa de acesso": 5,
    "Inativo — risco de perda": 4,
    "Novo cadastro": 3,
    "Explorador sem conversão": 2,
    "Esporádico": 1,
    "Engajado convertendo": 0,
}

PLANOS_SEGMENTO = {
    "Bloqueado — taxa de acesso": {
        "decisao": "Oferecer suporte sobre a taxa de acesso",
        "acao": "Confirmar se o bloqueio ainda ocorre e orientar o fornecedor sobre as condições de participação.",
        "responsavel": "Atendimento",
        "indicador": "Fornecedores contatados que enviam proposta em até 7 dias / fornecedores contatados deste grupo.",
    },
    "Inativo — risco de perda": {
        "decisao": "Reativar fornecedores que deixaram de retornar",
        "acao": "Revisar oportunidades compatíveis com o interesse cadastrado; quando não houver, oferecer atendimento para entender o afastamento.",
        "responsavel": "Marketing e Atendimento",
        "indicador": "Fornecedores contatados que voltam ao portal em até 7 dias / fornecedores contatados deste grupo.",
    },
    "Novo cadastro": {
        "decisao": "Orientar os primeiros passos dos novos cadastros",
        "acao": "Revisar a atividade de cada fornecedor e oferecer um guia de busca e participação conforme a etapa em que está.",
        "responsavel": "Atendimento",
        "indicador": "Novos fornecedores sem proposta que enviam a primeira em até 7 dias / novos fornecedores sem proposta contatados.",
    },
    "Explorador sem conversão": {
        "decisao": "Investigar obstáculos ao envio de propostas",
        "acao": "Abordar os fornecedores que já voltaram ao portal e oferecer suporte para entender por que ainda não enviaram propostas.",
        "responsavel": "Atendimento e Produto",
        "indicador": "Fornecedores contatados que enviam a primeira proposta em até 7 dias / fornecedores contatados deste grupo.",
    },
    "Esporádico": {
        "decisao": "Revisar contatos de menor prioridade",
        "acao": "Avaliar a atividade individual e a existência de oportunidades compatíveis antes de sugerir uma comunicação informativa.",
        "responsavel": "Marketing",
        "indicador": "Fornecedores contatados que retornam em até 7 dias / fornecedores contatados deste grupo.",
    },
}


def evidencia_fornecedor(row):
    return (
        f"{int(row['recencia_dias'])} dias desde o último acesso; "
        f"{int(row['dias_ativos'])} dias ativos; "
        f"{int(row['propostas_enviadas'])} propostas na janela; "
        f"registro de bloqueio: {'sim' if row['bateu_bloqueio'] else 'não'}."
    )


def priorizar_fornecedores(metricas):
    """Mesma ordenação para resumo e fila; prioridade não é previsão de retorno."""
    fila = metricas.copy()
    fila["prioridade"] = fila["segmento_regra"].map(PRIORIDADE_SEGMENTO).fillna(0).astype(int)
    return fila.sort_values(
        ["prioridade", "recencia_dias", "usuario_id"], ascending=[False, False, True],
        kind="stable",
    )


def resumir_recomendacoes(metricas):
    """Grupos exclusivos da segmentação existente, sem inventar efeito esperado."""
    recomendacoes = []
    for segmento, plano in PLANOS_SEGMENTO.items():
        grupo = metricas.loc[metricas["segmento_regra"] == segmento]
        if grupo.empty:
            continue
        n = len(grupo)
        recencia = int(grupo["recencia_dias"].median())
        sem_proposta = int(grupo["propostas_enviadas"].eq(0).sum())
        bloqueados = int(grupo["bateu_bloqueio"].sum())
        recomendacoes.append({
            "segmento": segmento,
            "quantidade": n,
            "evidencia": (
                f"{n} fornecedores neste segmento; {sem_proposta} sem proposta na janela; "
                f"{recencia} dias de mediana desde o último acesso; "
                f"{bloqueados} com registro de bloqueio."
            ),
            **plano,
        })
    return recomendacoes
