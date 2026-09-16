"""Resumo visual das recomendações, sem alterar a política de prioridade."""

from html import escape

import streamlit as st

from recomendacoes import evidencia_fornecedor, priorizar_fornecedores, resumir_recomendacoes


CORES = {
    "Bloqueado — taxa de acesso": "#B54708",
    "Inativo — risco de perda": "#A12A4C",
    "Novo cadastro": "#2858A5",
    "Explorador sem conversão": "#6B4BA5",
    "Esporádico": "#526477",
    "Engajado convertendo": "#167568",
}
ROTULOS = {
    "Bloqueado — taxa de acesso": "Bloqueados",
    "Inativo — risco de perda": "Inativos",
    "Novo cadastro": "Novos cadastros",
    "Explorador sem conversão": "Exploradores",
    "Esporádico": "Esporádicos",
    "Engajado convertendo": "Engajados",
}


def numero(valor):
    return f"{int(valor):,}".replace(",", ".")


def renderizar_visao_executiva(metricas, eventos, data_ref, sem_eventos, funil, gargalo):
    st.html("""<style>
    .elo-exec {color:#16305c;font-family:inherit;line-height:1.5}
    .elo-exec * {box-sizing:border-box}
    .elo-exec h2,.elo-exec h3,.elo-exec p {margin:0}
    .elo-exec .eyebrow {font-size:.76rem;font-weight:750;letter-spacing:.09em;text-transform:uppercase}
    .elo-exec .muted {color:#526477;font-size:.88rem}
    .elo-exec .hero {padding:26px 30px;background:#16305c;color:white;border-radius:16px}
    .elo-exec .hero h2 {font-size:1.9rem;color:white;margin:6px 0 8px;line-height:1.2}
    .elo-exec .hero p {color:#e0e9f5;max-width:850px}
    .elo-exec .hero .eyebrow {color:#ffd0b5}
    .elo-exec .kpis {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}
    .elo-exec .kpi {background:#f5f8fc;border:1px solid #dce4ef;border-radius:12px;padding:18px}
    .elo-exec .value {font-size:2rem;font-weight:750;line-height:1.2;margin:8px 0}
    .elo-exec .focus {border-left:5px solid #b54708;background:#fff5ed;border-radius:10px;padding:18px 22px;margin:4px 0 20px}
    .elo-exec .focus h3 {font-size:1.1rem;margin:5px 0}
    .elo-exec .section {margin:20px 0 12px}
    .elo-exec .section h3 {font-size:1.2rem}
    .elo-exec .stack {display:flex;height:14px;border-radius:8px;overflow:hidden;margin:16px 0}
    .elo-exec .legend {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 20px}
    .elo-exec .legend-row {display:flex;align-items:center;gap:8px;font-size:.88rem}
    .elo-exec .legend-row strong {margin-left:auto}
    .elo-exec .dot {width:9px;height:9px;border-radius:50%;flex-shrink:0}
    .elo-exec .badge {display:inline-block;font-size:.76rem;font-weight:700;border-radius:5px;background:#edf2f8;padding:3px 8px}
    .elo-exec .plan-title {font-size:1.15rem;font-weight:700;margin:10px 0}
    .elo-exec .count {font-size:1.6rem;font-weight:750}
    .elo-exec .fact {background:#f5f8fc;padding:12px;border-radius:8px;margin:12px 0;font-size:.9rem}
    .elo-exec .journey-row {margin:12px 0}
    .elo-exec .journey-label {display:flex;justify-content:space-between;gap:10px;font-size:.83rem;margin-bottom:4px}
    .elo-exec .track {height:8px;background:#edf2f8;border-radius:5px;overflow:hidden}
    .elo-exec .fill {height:100%;background:#2858a5;border-radius:5px}
    @media(max-width:700px) {
      .elo-exec .kpis {grid-template-columns:repeat(2,minmax(0,1fr))}
      .elo-exec .hero {padding:20px}.elo-exec .hero h2 {font-size:1.5rem}
      .elo-exec .legend {grid-template-columns:1fr}
    }
    </style>""")

    fila = priorizar_fornecedores(metricas)
    candidatos = fila[fila.prioridade > 0]
    planos = resumir_recomendacoes(metricas)
    contagens = metricas.segmento_regra.value_counts()
    total = len(metricas)
    st.html(f"""<div class="elo-exec"><div class="hero">
      <div class="eyebrow">Visão executiva · {data_ref.strftime('%d/%m/%Y')} · Base simulada</div>
      <h2>Da leitura dos dados à decisão.</h2>
      <p>Priorize a revisão dos fornecedores, direcione a equipe e acompanhe a jornada no portal.</p>
    </div></div>""")
    indicadores = [
        ("Para revisar", len(candidatos), "Candidatos a contato"),
        ("Bloqueados", contagens.get("Bloqueado — taxa de acesso", 0), "Primeira prioridade de revisão"),
        ("Inativos", contagens.get("Inativo — risco de perda", 0), "Segunda prioridade de revisão"),
        ("Engajados", contagens.get("Engajado convertendo", 0), "Manter relacionamento"),
    ]
    st.html('<div class="elo-exec"><div class="kpis">' + ''.join(
        f'<div class="kpi"><div class="eyebrow">{titulo}</div><div class="value">{numero(n)}</div>'
        f'<div class="muted">{legenda}</div></div>' for titulo, n, legenda in indicadores
    ) + '</div></div>')
    if planos:
        primeiro = planos[0]
        st.html(f"""<div class="elo-exec"><div class="focus">
          <div class="eyebrow">Comece por aqui · {escape(primeiro['responsavel'])}</div>
          <h3>{escape(primeiro['decisao'])}</h3>
          <p>Revisar os <strong>{primeiro['quantidade']} fornecedores</strong> do grupo
          {escape(primeiro['segmento'])} antes do contato.</p>
        </div></div>""")
    else:
        st.info("Sem candidatos à revisão de contato. Manter o acompanhamento da base.")

    distribuicao, jornada = st.columns([1.1, 1], gap="large")
    with distribuicao, st.container(border=True):
        st.markdown("#### Como a base se distribui")
        st.caption(f"{numero(total)} fornecedores identificados · grupos sem sobreposição")
        st.html('<div class="elo-exec"><div class="stack" aria-hidden="true">' + ''.join(
            f'<span style="width:{int(contagens.get(s, 0)) / total * 100 if total else 0}%;background:{cor}"></span>'
            for s, cor in CORES.items()
        ) + '</div><div class="legend">' + ''.join(
            f'<div class="legend-row"><span class="dot" style="background:{cor}"></span>'
            f'<span>{ROTULOS[s]}</span><strong>{int(contagens.get(s, 0))}</strong></div>'
            for s, cor in CORES.items()
        ) + '</div></div>')
        st.caption("A prioridade segue regras de negócio; não é uma previsão de resposta.")
    with jornada, st.container(border=True):
        st.markdown("#### Onde investigar a jornada")
        topo = int(funil.iloc[0]["Sessões na sequência"])
        st.html('<div class="elo-exec">' + ''.join(
            f'<div class="journey-row"><div class="journey-label"><span>{escape(row["Etapa"])}</span>'
            f'<strong>{numero(row["Sessões na sequência"])}</strong></div><div class="track">'
            f'<div class="fill" style="width:{row["Sessões na sequência"] / topo * 100 if topo else 0}%"></div></div></div>'
            for _, row in funil.iterrows()
        ) + '</div>')
        if gargalo:
            st.caption(f"Maior perda: {numero(gargalo['perdas'])} sessões · {gargalo['origem']} → {gargalo['destino']}.")
        with st.expander("Recomendação para Produto"):
            st.write("Revisar a clareza da transição com maior perda e observar fornecedores em um teste de uso antes de escolher a intervenção." if gargalo else "Não há perda mensurável que justifique priorizar uma transição.")
            st.write("Acompanhar: sessões que avançam / sessões na etapa anterior. Comparar a mudança com a experiência atual em um teste controlado.")
            st.caption("Etapas em ordem na mesma sessão. A perda não comprova a causa; entradas diretas e retornos em outra sessão ficam fora da conversão da jornada.")

    st.html('<div class="elo-exec"><div class="section"><div class="eyebrow">01 · Direcionar</div><h3>Plano de ação por prioridade</h3><p class="muted">Ação em destaque. Evidência e indicador disponíveis em cada cartão.</p></div></div>')

    def cartao(plano, posicao):
        with st.container(border=True):
            cor = CORES[plano["segmento"]]
            st.html(f"""<div class="elo-exec">
              <span class="badge" style="color:{cor}">Prioridade {posicao} · {escape(ROTULOS[plano['segmento']])}</span>
              <div class="plan-title">{escape(plano['decisao'])}</div>
              <div><span class="count">{plano['quantidade']}</span> <span class="muted">fornecedores · {escape(plano['responsavel'])}</span></div>
              <div class="fact">{escape(plano['acao'])}</div>
            </div>""")
            with st.expander("Por que agir e como acompanhar"):
                st.write(f"**Evidência:** {plano['evidencia']}")
                st.write(f"**Indicador sugerido:** {plano['indicador']}")

    colunas_planos = st.columns(2, gap="medium")
    for i, plano in enumerate(planos[:2]):
        with colunas_planos[i]:
            cartao(plano, i + 1)
    if len(planos) > 2:
        with st.expander(f"Outras frentes de atuação · {sum(p['quantidade'] for p in planos[2:])} fornecedores"):
            for i, plano in enumerate(planos[2:], start=3):
                cartao(plano, i)

    st.html('<div class="elo-exec"><div class="section"><div class="eyebrow">02 · Preparar o contato</div><h3>Da prioridade ao fornecedor</h3><p class="muted">Filtre um grupo, revise a recomendação e selecione quem será atendido.</p></div></div>')
    if not candidatos.empty:
        grupos = [p["segmento"] for p in planos]
        grupo = st.selectbox("Grupo para revisão", ["Todos os grupos"] + grupos, key="grupo_resumo")
        filtrados = candidatos if grupo == "Todos os grupos" else candidatos[candidatos.segmento_regra == grupo]
        lista, detalhe = st.columns([1.25, 1], gap="large")
        with lista:
            st.caption(f"Mostrando os primeiros {min(6, len(filtrados))} de {len(filtrados)} candidatos · maior tempo sem acesso primeiro em cada prioridade")
            st.dataframe(
                filtrados.head(6)[["usuario_id", "segmento_regra", "recencia_dias"]].rename(columns={
                    "usuario_id": "Fornecedor", "segmento_regra": "Grupo", "recencia_dias": "Dias sem acesso",
                }), hide_index=True, width="stretch",
            )
            exportacao = filtrados[["usuario_id", "empresa", "segmento_regra", "canal_sugerido"]].copy()
            exportacao["evidencia"] = filtrados.apply(evidencia_fornecedor, axis=1)
            st.download_button("Exportar este grupo (CSV)", exportacao.rename(columns={
                "usuario_id": "Fornecedor", "empresa": "Empresa", "segmento_regra": "Grupo",
                "canal_sugerido": "Canal sugerido", "evidencia": "Evidência para revisão",
            }).to_csv(index=False).encode("utf-8-sig"), file_name=f"revisao_contatos_{data_ref.date()}.csv", mime="text/csv")
        with detalhe, st.container(border=True):
            empresas = filtrados.set_index("usuario_id")["empresa"]
            if st.session_state.get("fornecedor_resumo") not in empresas.index:
                st.session_state["fornecedor_resumo"] = empresas.index[0]
            uid = st.selectbox("Fornecedor para revisar", empresas.index.tolist(),
                               format_func=lambda x: f"{x} — {empresas.loc[x]}", key="fornecedor_resumo")
            fornecedor = filtrados[filtrados.usuario_id == uid].iloc[0]
            st.caption(fornecedor["segmento_regra"])
            c1, c2 = st.columns(2)
            c1.metric("Dias sem acesso", int(fornecedor["recencia_dias"]))
            c2.metric("Propostas na janela", int(fornecedor["propostas_enviadas"]))
            st.write(f"**Canal sugerido:** {fornecedor['canal_sugerido']}")
            with st.expander("Evidência e mensagem sugerida"):
                st.write(evidencia_fornecedor(fornecedor))
                st.write(fornecedor["mensagem_sugerida"])
            if st.button("Preparar ação de reengajamento", key="preparar_acao_executiva", type="primary", width="stretch"):
                st.session_state["select_usuario_acao"] = uid
                st.success("Seleção pronta. Abra ‘Ação de reengajamento’ para continuar.")
            st.caption("Antes de contatar: conferir preferências, opt-out e histórico. Este botão apenas seleciona o fornecedor.")

    with st.expander("Sobre os dados e a avaliação das recomendações"):
        percentual = eventos.usuario_id.isna().mean() * 100 if len(eventos) else 0
        st.write(f"{percentual:.0f}% dos eventos não têm usuário identificado. {sem_eventos} cadastrados não têm evento identificado na janela e não integram estas recomendações.")
        st.write("Anônimos entram na jornada, não na lista de contato. Os indicadores são sugestões para um piloto e não resultados medidos. Comparar contato e controle sorteados no mesmo segmento, entre fornecedores elegíveis, por 7 dias.")
