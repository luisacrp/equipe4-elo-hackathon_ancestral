"""Métricas de jornada independentes da interface e de serviços externos."""

import pandas as pd


ETAPAS_FUNIL = {
    "1. Lista/busca pública": {
        "lista_oportunidades_publicas", "busca_publica", "home_publica",
    },
    "2. Detalhe da oportunidade": {
        "detalhe_oportunidade_publica", "detalhe_oportunidade",
    },
    "3. Tenho interesse": {"tenho_interesse"},
    "4. Login / Identificação": {"login", "iniciar_identificacao"},
    "5. Envio de proposta": {"envio_proposta"},
}


def calcular_funil(eventos):
    """Conta prefixos ordenados na mesma sessão, permitindo páginas intermediárias.

    Empates de timestamp usam ordem_na_sessao e, por fim, a ordem da entrada.
    Sessões que entram em etapas posteriores aparecem somente no alcance.
    """
    ordem = ["timestamp"]
    if "ordem_na_sessao" in eventos.columns:
        ordem.append("ordem_na_sessao")
    validos = eventos.dropna(subset=["session_id", "timestamp", "pagina"])
    etapas = list(ETAPAS_FUNIL.values())
    contagens = [0] * len(etapas)
    for _, sessao in validos.sort_values(ordem, kind="stable").groupby("session_id"):
        proxima = 0
        for pagina in sessao["pagina"]:
            if proxima < len(etapas) and pagina in etapas[proxima]:
                contagens[proxima] += 1
                proxima += 1
    topo = contagens[0]
    linhas = []
    for i, (nome, paginas) in enumerate(ETAPAS_FUNIL.items()):
        anterior = contagens[i - 1] if i else None
        linhas.append({
            "Etapa": nome,
            "Sessões na sequência": contagens[i],
            "Alcance independente": validos.loc[validos.pagina.isin(paginas), "session_id"].nunique(),
            "% da entrada": round(contagens[i] / topo * 100, 1) if topo else 0.0,
            "Abandonos da etapa anterior": anterior - contagens[i] if i else 0,
            "Conversão da etapa anterior (%)": round(contagens[i] / anterior * 100, 1) if anterior else None,
        })
    return pd.DataFrame(linhas)


def maior_gargalo(funil):
    """Prioriza volume de sessões perdidas; não implica efeito causal."""
    perdas = funil.iloc[1:]
    if perdas.empty or perdas["Abandonos da etapa anterior"].max() <= 0:
        return None
    indice = perdas["Abandonos da etapa anterior"].idxmax()
    return {
        "origem": funil.loc[indice - 1, "Etapa"],
        "destino": funil.loc[indice, "Etapa"],
        "perdas": int(funil.loc[indice, "Abandonos da etapa anterior"]),
    }
