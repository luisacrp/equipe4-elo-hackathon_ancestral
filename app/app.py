"""
Protótipo — Conexão Ancestral / Hackathon Petronect
----------------------------------------------------
Dashboard que lê os acessos simulados ao Portal Petronect, identifica
o comportamento de cada fornecedor (por regras e por clustering), mede
essa segmentação contra o comportamento real simulado, mostra o funil
de navegação, prioriza a fila de reengajamento e permite gerar e
"registrar" o envio de uma comunicação personalizada.

Rodar localmente:
    pip install -r requirements.txt
    streamlit run app.py
"""

import csv
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

# ------------------------------------------------------------------
# 0. Caminhos (independentes do diretório de onde o Streamlit é
#    executado — sempre relativos à localização deste arquivo, dentro
#    da pasta app/, com os dados em ../dados/).
# ------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from analise_jornada import calcular_funil, maior_gargalo
from recomendacoes import priorizar_fornecedores
from visao_executiva import renderizar_visao_executiva

DADOS_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "dados"))

# Camada de captura (tracker.js -> tracker_server.py -> eventos_live.csv)
# Ver tracker.js, portal_demo.html, tracker_server.py e
# diagrama_arquitetura.svg (pasta captura/ e docs/). eventos_live.csv usa
# as mesmas colunas de acessos_simulados.csv, por isso não precisa de
# nenhuma transformação para ser lido aqui.
CAMINHO_EVENTOS_LIVE = os.path.join(DADOS_DIR, "eventos_live.csv")

# Quando app.py e tracker_server.py rodam na mesma máquina (uso local, como
# no roteiro de gravação do vídeo), o dashboard lê eventos_live.csv direto
# do disco. Mas quando a banca só testa o que está deployado, cada serviço
# vira um processo em um host diferente (ex.: Streamlit Community Cloud +
# Render) e não existe mais disco compartilhado — por isso o dashboard
# passa a buscar os eventos pela própria API do tracker_server
# (GET /api/events) sempre que uma URL de servidor de captura é informada.
# Prioridade: st.secrets (produção) > variável de ambiente > campo manual
# na própria aba (para testar rápido sem mexer em configuração).
def _tracker_url_dos_secrets():
    # st.secrets lança exceção se não existir NENHUM secrets.toml
    # configurado — o que é normal ao rodar local sem esse arquivo. Por
    # isso o acesso fica protegido, em vez de travar o app inteiro.
    try:
        return st.secrets.get("TRACKER_URL", "")
    except Exception:
        return ""


TRACKER_URL_PADRAO = _tracker_url_dos_secrets() or os.environ.get("TRACKER_URL", "")

st.set_page_config(
    page_title="Portal Petronect — Comportamento & Reengajamento",
    layout="wide",
)

# ------------------------------------------------------------------
# 1. Carregar dados
# ------------------------------------------------------------------


@st.cache_data
def carregar_dados():
    df = pd.read_csv(
        os.path.join(DADOS_DIR, "acessos_simulados.csv"), parse_dates=["timestamp"]
    )
    fornecedores = pd.read_csv(
        os.path.join(DADOS_DIR, "fornecedores.csv"), parse_dates=["data_cadastro"]
    )
    oportunidades = pd.read_csv(
        os.path.join(DADOS_DIR, "oportunidades.csv"),
        parse_dates=["data_publicacao", "data_fim"],
    )
    return df, fornecedores, oportunidades


df, fornecedores, oportunidades = carregar_dados()

# ------------------------------------------------------------------
# 1b. Rótulos legíveis (os nomes técnicos das páginas e das colunas
#     nunca aparecem crus na tela — só aqui, para consulta)
# ------------------------------------------------------------------

NOMES_PAGINAS = {
    "home_publica": "Início (área pública)",
    "busca_publica": "Busca pública",
    "lista_oportunidades_publicas": "Lista de oportunidades (pública)",
    "detalhe_oportunidade_publica": "Detalhe da oportunidade (pública)",
    "tenho_interesse": "Tenho interesse",
    "login": "Login",
    "iniciar_identificacao": "Iniciar identificação",
    "quer_se_cadastrar": "Quero me cadastrar",
    "modelo_cobranca_socio": "Modelo de cobrança do Sócio Fornecedor",
    "ajuda_treinamentos": "Ajuda e treinamentos",
    "avisos": "Avisos",
    "painel_oportunidades": "Painel de oportunidades",
    "detalhe_oportunidade": "Detalhe da oportunidade",
    "taxa_acesso_bloqueio": "Taxa de acesso (bloqueio)",
    "envio_proposta": "Envio de proposta",
    "minhas_participacoes": "Minhas participações",
    "sala_colaboracao": "Sala de colaboração",
    "cadastro_fornecedor": "Cadastro de fornecedor",
    "assinatura_eletronica": "Assinatura eletrônica",
    "meus_dados": "Meus dados",
}


def nome_pagina(codigo):
    """Nome de página amigável para exibição (em vez do identificador técnico)."""
    if pd.isna(codigo):
        return codigo
    return NOMES_PAGINAS.get(codigo, codigo.replace("_", " ").capitalize())


COLUNAS_LEGIVEIS = {
    "usuario_id": "Fornecedor",
    "empresa": "Empresa",
    "segmento_regra": "Segmento (regra)",
    "segmento_cluster": "Segmento (cluster)",
    "ultimo_acesso": "Último acesso",
    "recencia_dias": "Dias desde o último acesso",
    "dias_ativos": "Dias ativos",
    "total_eventos": "Eventos",
    "propostas_enviadas": "Propostas enviadas",
    "pagina_mais_acessada": "Página mais acessada",
    "prioridade": "Prioridade",
    "canal_sugerido": "Canal sugerido",
    "mensagem_sugerida": "Mensagem sugerida",
    "data_registro": "Data do registro",
    "segmento": "Segmento",
    "canal": "Canal",
    "mensagem": "Mensagem",
    "timestamp": "Data e hora",
    "area": "Área",
    "pagina": "Página",
    "anonymous_id": "Identificador do visitante",
    "identificado": "Identificado",
    "oportunidade_id": "Oportunidade",
}

# DATA_REFERENCIA é o último evento da base simulada — fica "congelada" no
# tempo porque o CSV é estático. Em produção, "hoje" seria sempre a data
# real; aqui documentamos explicitamente o porquê para não repetir o erro
# apontado na revisão (recência que nunca se move).
DATA_REFERENCIA = df["timestamp"].max()

# ------------------------------------------------------------------
# 2. Métricas por usuário (só para quem já foi identificado alguma vez —
#    é a limitação real do negócio, não escondemos isso)
# ------------------------------------------------------------------


@st.cache_data
def calcular_metricas(df, fornecedores, data_ref):
    identificado = df.dropna(subset=["usuario_id"])

    agrupado = (
        identificado.groupby(["usuario_id", "empresa"])
        .agg(
            primeiro_acesso=("timestamp", "min"),
            ultimo_acesso=("timestamp", "max"),
            dias_ativos=("timestamp", lambda x: x.dt.date.nunique()),
            total_eventos=("timestamp", "count"),
            propostas_enviadas=("enviou_proposta", "sum"),
            bateu_bloqueio=("pagina", lambda s: (s == "taxa_acesso_bloqueio").any()),
        )
        .reset_index()
    )
    agrupado["recencia_dias"] = (data_ref - agrupado["ultimo_acesso"]).dt.days

    pagina_top = (
        identificado.groupby(["usuario_id", "pagina"])
        .size()
        .reset_index(name="qtd")
        .sort_values("qtd", ascending=False)
        .drop_duplicates("usuario_id")
        .set_index("usuario_id")["pagina"]
    )
    agrupado["pagina_mais_acessada"] = agrupado["usuario_id"].map(pagina_top)

    # Junta com o cadastro real — é isso que corrige o bug de v1 em que
    # "novo cadastro" era confundido com "primeiro acesso dentro da janela".
    metricas = agrupado.merge(
        fornecedores[
            [
                "usuario_id",
                "data_cadastro",
                "socio_fornecedor",
                "perfil_real",
                "categorias_interesse",
            ]
        ],
        on="usuario_id",
        how="left",
    )
    metricas["antiguidade_cadastro_dias"] = (
        data_ref.normalize() - metricas["data_cadastro"]
    ).dt.days

    return metricas


metricas = calcular_metricas(df, fornecedores, DATA_REFERENCIA)

FORNECEDORES_SEM_EVENTO_NA_JANELA = len(fornecedores) - metricas["usuario_id"].nunique()

# ------------------------------------------------------------------
# 3. Segmentação por regras (interpretável, fácil de explicar no pitch)
# ------------------------------------------------------------------
#
# Correções em relação à v1:
#  - "Novo cadastro" agora usa data_cadastro REAL (fornecedores.csv), não
#    mais o primeiro acesso dentro da janela observada.
#  - Novo segmento "Bloqueado — taxa de acesso": quem manifestou interesse
#    e bateu no cadeado de Sócio Fornecedor sem concluir proposta. Era o
#    lead de maior valor apontado na revisão e não existia como segmento.

LIMIAR_NOVO_CADASTRO_DIAS = 30
LIMIAR_INATIVO_DIAS = 20


def segmentar_por_regra(row):
    if (
        pd.notna(row["antiguidade_cadastro_dias"])
        and row["antiguidade_cadastro_dias"] <= LIMIAR_NOVO_CADASTRO_DIAS
    ):
        return "Novo cadastro"
    if row["bateu_bloqueio"] and row["propostas_enviadas"] == 0:
        return "Bloqueado — taxa de acesso"
    if row["recencia_dias"] > LIMIAR_INATIVO_DIAS:
        return "Inativo — risco de perda"
    if row["propostas_enviadas"] >= 1 and row["recencia_dias"] <= 7:
        return "Engajado convertendo"
    if row["propostas_enviadas"] == 0 and row["dias_ativos"] >= 3:
        return "Explorador sem conversão"
    return "Esporádico"


metricas["segmento_regra"] = metricas.apply(segmentar_por_regra, axis=1)

# Mapeamento usado na aba de Validação para comparar com o ground truth
# (perfil_real) via matriz de confusão.
MAPA_REGRA_PARA_PERFIL_REAL = {
    "Novo cadastro": "novo_cadastro",
    "Bloqueado — taxa de acesso": "bloqueado_taxa_acesso",
    "Inativo — risco de perda": "inativo_em_risco",
    "Engajado convertendo": "ativo_convertendo",
    "Explorador sem conversão": "explorador_sem_conversao",
    "Esporádico": "esporadico",
}
PERFIS_REAIS_LEGIVEIS = {v: k for k, v in MAPA_REGRA_PARA_PERFIL_REAL.items()}

# ------------------------------------------------------------------
# 4. Segmentação por clustering (mais sofisticada, orientada a dados)
# ------------------------------------------------------------------
# Correção: v1 usava dias_ativos E total_eventos, que têm correlação de
# 0,94 nesta base (feature redundante, apontada na revisão). Usamos só
# total_eventos. A curva de silhueta que justifica k=4 está na aba
# "Validação".

FEATURES_CLUSTERING = ["recencia_dias", "total_eventos", "propostas_enviadas"]


@st.cache_data
def calcular_curva_silhueta(metricas):
    features = metricas[FEATURES_CLUSTERING].fillna(0)
    X = StandardScaler().fit_transform(features)
    scores = {}
    for k in range(2, 7):
        km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(X)
        scores[k] = silhouette_score(X, km.labels_)
    return scores


@st.cache_data
def segmentar_por_clustering(metricas, n_clusters=4):
    features = metricas[FEATURES_CLUSTERING].fillna(0)

    scaler = StandardScaler()
    features_norm = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(features_norm)

    resultado = metricas.copy()
    resultado["cluster"] = clusters

    resumo = resultado.groupby("cluster")[
        ["recencia_dias", "total_eventos", "propostas_enviadas"]
    ].mean()

    resumo["score"] = (
        resumo["propostas_enviadas"] * 10
        - resumo["recencia_dias"]
        + resumo["total_eventos"] * 0.1
    )
    ranking = resumo["score"].rank(ascending=False)

    nomes = {}
    for cluster_id, linha in resumo.iterrows():
        posicao = ranking[cluster_id]
        if posicao == 1:
            nomes[cluster_id] = "Cluster de alta conversão"
        elif posicao == len(resumo):
            nomes[cluster_id] = "Cluster de baixo engajamento"
        elif linha["total_eventos"] >= resumo["total_eventos"].median():
            nomes[cluster_id] = "Cluster explorador frequente"
        else:
            nomes[cluster_id] = "Cluster ocasional"

    resultado["segmento_cluster"] = resultado["cluster"].map(nomes)
    return resultado, resumo, nomes


metricas, resumo_clusters, nomes_clusters = segmentar_por_clustering(metricas, n_clusters=4)
curva_silhueta = calcular_curva_silhueta(metricas)


# ------------------------------------------------------------------
# 5. Regras de ação / comunicação sugerida
# ------------------------------------------------------------------
# Correção: as mensagens não afirmam mais nada que o dado não sustenta
# ("há novas oportunidades na sua categoria" só aparece quando existe,
# de fato, uma oportunidade aberta compatível — ver buscar_oportunidades).
# Todas as mensagens agora terminam com uma linha de opt-out (LGPD).

RODAPE_OPTOUT = (
    '\n\n_Se preferir não receber esse tipo de comunicação, responda "sair" '
    "a qualquer momento — o cadastro será atualizado em até 2 dias úteis._"
)

ACOES = {
    "Novo cadastro": {
        "canal": "E-mail de boas-vindas",
        "mensagem": (
            "Olá {empresa}, vimos que você começou a explorar o Portal Petronect "
            "recentemente. Preparamos um guia rápido de como buscar oportunidades "
            "e enviar sua primeira proposta — quer que te enviemos o passo a passo?"
        ),
    },
    "Bloqueado — taxa de acesso": {
        "canal": "E-mail sobre Sócio Fornecedor",
        "mensagem": (
            "Olá {empresa}, vimos que você demonstrou interesse em uma "
            "oportunidade, mas ainda não conta com o Sócio Fornecedor — a taxa "
            "que dá acesso à participação em pregões e concorrências (dispensas "
            "abaixo de R$ 50 mil são isentas). Posso te ajudar a regularizar isso?"
        ),
    },
    "Inativo — risco de perda": {
        "canal": "E-mail de reativação",
        "mensagem": (
            "Olá {empresa}, notamos que faz {recencia_dias} dias desde seu "
            "último acesso ao Portal Petronect."
        ),
    },
    "Engajado convertendo": {
        "canal": "Comunicação de relacionamento",
        "mensagem": (
            "Olá {empresa}, obrigado por continuar ativo no Portal! Separamos "
            "oportunidades similares às que você já teve sucesso para acelerar "
            "suas próximas propostas."
        ),
    },
    "Explorador sem conversão": {
        "canal": "E-mail de suporte proativo",
        "mensagem": (
            "Olá {empresa}, percebemos que você tem explorado bastante o Portal, "
            "mas ainda não enviou nenhuma proposta. Precisa de ajuda com o processo "
            "de envio? Nosso time de atendimento pode te orientar."
        ),
    },
    "Esporádico": {
        "canal": "Comunicação informativa",
        "mensagem": (
            "Olá {empresa}, para não perder oportunidades relevantes, você pode "
            "ativar alertas por categoria no Portal Petronect."
        ),
    },
}


def buscar_oportunidades_compativeis(categorias_interesse, top_n=1):
    """Oportunidades abertas (na data de referência) que batem com o
    interesse declarado do fornecedor. Só existe porque v2 do gerador
    passou a incluir oportunidade_id/categoria em cada evento e um
    catálogo (oportunidades.csv) — não existia em v1."""
    if not isinstance(categorias_interesse, str) or not categorias_interesse:
        return oportunidades.iloc[0:0]
    cats = categorias_interesse.split("|")
    abertas = oportunidades[oportunidades["data_fim"] >= DATA_REFERENCIA.normalize()]
    match = abertas[abertas["categoria"].isin(cats)]
    return match.sort_values("data_fim").head(top_n)


def gerar_mensagem(row):
    template = ACOES[row["segmento_regra"]]["mensagem"]
    base = template.format(empresa=row["empresa"], recencia_dias=row["recencia_dias"])

    if row["segmento_regra"] in {
        "Inativo — risco de perda",
        "Explorador sem conversão",
        "Esporádico",
    }:
        match = buscar_oportunidades_compativeis(row.get("categorias_interesse"))
        if len(match):
            op = match.iloc[0]
            categoria_legivel = op["categoria"].replace("_", " ")
            base += (
                f"\n\nA oportunidade **{op['oportunidade_id']}** ({categoria_legivel}, "
                f"{op['modalidade'].replace('_', ' ')}) está aberta até "
                f"{op['data_fim'].date().strftime('%d/%m/%Y')} e é compatível com o "
                "seu perfil de interesse."
            )
        else:
            base += (
                "\n\nNão há, no momento, oportunidades abertas na categoria de "
                "interesse deste fornecedor — vale um alerta assim que surgir uma."
            )

    return base + RODAPE_OPTOUT


metricas["canal_sugerido"] = metricas["segmento_regra"].map(lambda s: ACOES[s]["canal"])
metricas["mensagem_sugerida"] = metricas.apply(gerar_mensagem, axis=1)

# ------------------------------------------------------------------
# 6. Histórico de comunicações enviadas
# ------------------------------------------------------------------
# Correção: a v2 anterior guardava isto só em st.session_state, que o
# Streamlit zera a cada reload do navegador (comportamento documentado
# da própria ferramenta) — exatamente o bug "some no refresh e não mede
# nada" apontado na revisão original, só que reintroduzido. Persistimos
# em CSV, no mesmo espírito de eventos_live.csv, para sobreviver a
# refresh e a reinício do processo.

HISTORICO_ENVIOS_PATH = os.path.join(DADOS_DIR, "historico_envios.csv")
COLUNAS_HISTORICO = [
    "data_registro", "usuario_id", "empresa", "segmento", "canal", "mensagem",
]


def carregar_historico_envios() -> list[dict]:
    if not os.path.exists(HISTORICO_ENVIOS_PATH):
        return []
    with open(HISTORICO_ENVIOS_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def registrar_envio(registro: dict) -> None:
    os.makedirs(DADOS_DIR, exist_ok=True)
    novo_arquivo = not os.path.exists(HISTORICO_ENVIOS_PATH)
    with open(HISTORICO_ENVIOS_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_HISTORICO)
        if novo_arquivo:
            w.writeheader()
        w.writerow(registro)


if "historico_envios" not in st.session_state:
    st.session_state["historico_envios"] = carregar_historico_envios()

# ------------------------------------------------------------------
# 7. Interface
# ------------------------------------------------------------------

st.title("Portal Petronect")
st.caption("Comportamento de acesso e reengajamento")
st.caption(
    f"Base simulada · {len(df):,} eventos · janela de "
    f"{df['timestamp'].min().date().strftime('%d/%m/%Y')} a "
    f"{DATA_REFERENCIA.date().strftime('%d/%m/%Y')} · "
    f"{metricas['usuario_id'].nunique()} fornecedores identificados "
    f"({FORNECEDORES_SEM_EVENTO_NA_JANELA} cadastrados sem evento nesta janela)."
)

with st.expander("Indicadores gerais da base"):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Eventos totais", f"{len(df):,}")
    col2.metric(
        "Eventos sem usuário identificado",
        f"{df['usuario_id'].isna().mean() * 100:.0f}%",
        help="Eventos que não foram associados a um usuário identificado nesta base.",
    )
    col3.metric(
        "Em risco de perda",
        int((metricas["segmento_regra"] == "Inativo — risco de perda").sum()),
    )
    col4.metric(
        "Bloqueados na taxa de acesso",
        int((metricas["segmento_regra"] == "Bloqueado — taxa de acesso").sum()),
    )

funil_sequencial = calcular_funil(df)
gargalo = maior_gargalo(funil_sequencial)

(
    aba_resumo,
    aba_geral,
    aba_funil,
    aba_regra,
    aba_cluster,
    aba_validacao,
    aba_acao,
    aba_fila,
    aba_historico,
    aba_ao_vivo,
) = st.tabs(
    [
        "Visão executiva",
        "Tendência de acessos",
        "Funil & Sessionização",
        "Segmentação por regras",
        "Segmentação por clustering",
        "Validação",
        "Ação de reengajamento",
        "Fila & Próxima ação",
        "Histórico de envios",
        "Captura ao vivo",
    ]
)

with aba_resumo:
    renderizar_visao_executiva(
        metricas, df, DATA_REFERENCIA, FORNECEDORES_SEM_EVENTO_NA_JANELA,
        funil_sequencial, gargalo,
    )

# --- Aba: Tendência de acessos ao longo do tempo -------------------
with aba_geral:
    st.subheader("Evolução diária dos acessos ao Portal")

    acessos_por_dia = (
        df.set_index("timestamp").resample("D").size().rename("acessos").reset_index()
    )
    st.line_chart(acessos_por_dia, x="timestamp", y="acessos")

    st.subheader("Páginas mais acessadas")
    top_paginas = (
        df["pagina"]
        .map(nome_pagina)
        .value_counts()
        .rename_axis("Página")
        .rename("Acessos")
    )
    st.bar_chart(top_paginas, horizontal=True, height=600)

# --- Aba: Funil & Sessionização -------------------------------------
with aba_funil:
    st.subheader("Onde a sessão começa, e onde ela se perde")
    st.caption("Calculado sobre todas as sessões, anônimas e identificadas.")

    total_sessoes = df["session_id"].nunique()

    colA, colB = st.columns([1, 1.4])

    with colA:
        st.markdown("**Página de entrada mais comum**")
        entrada = (
            df[df["pagina_entrada"] == 1]["pagina"]
            .map(nome_pagina)
            .value_counts(normalize=True)
            .mul(100)
            .round(1)
            .rename_axis("Página")
            .reset_index(name="% das sessões")
            .head(8)
        )
        st.dataframe(entrada, hide_index=True, width="stretch")

    funil_df = funil_sequencial

    with colB:
        st.markdown("**Funil sequencial na mesma sessão**")
        st.dataframe(
            funil_df,
            hide_index=True,
            width="stretch",
        )

    st.bar_chart(
        funil_df.set_index("Etapa")["Sessões na sequência"],
        horizontal=True,
    )

    st.caption(
        "Cada etapa exige as anteriores em ordem na mesma sessão. Alcance independente "
        "inclui também entradas diretas e outras jornadas, como usuários já autenticados. "
        "Abandono significa não avançar nesta sessão; não comprova desistência definitiva."
    )
    if gargalo:
        st.warning(
            f"Maior perda em volume: {gargalo['origem']} → {gargalo['destino']} "
            f"({gargalo['perdas']:,} sessões). Investigue essa transição e teste uma "
            "intervenção com grupo de controle antes de atribuir causa ou impacto."
        )
    else:
        st.info("Não há abandonos mensuráveis neste funil.")
    st.download_button(
        "Exportar diagnóstico do funil", funil_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="diagnostico_funil.csv", mime="text/csv",
    )

    st.divider()
    st.markdown("**Sessionização**")
    paginas_por_sessao = df.groupby("session_id")["ordem_na_sessao"].max()
    colX, colY, colZ = st.columns(3)
    colX.metric("Sessões no período", f"{total_sessoes:,}")
    colY.metric("Páginas por sessão (média)", f"{paginas_por_sessao.mean():.1f}")
    colZ.metric(
        "Sessões de 1 página só",
        f"{(paginas_por_sessao == 1).mean() * 100:.0f}%",
    )
    st.caption(
        "Sessão: eventos do mesmo visitante com no máximo 30 minutos de "
        "intervalo entre páginas vistas."
    )

# --- Aba: Segmentação por regras -----------------------------------
with aba_regra:
    st.subheader("Fornecedores segmentados por regras de negócio")
    st.caption(
        "Regras simples e explicáveis, fáceis de ajustar com o time de "
        "Marketing/Atendimento."
    )

    segmento_filtro = st.multiselect(
        "Filtrar por segmento",
        options=sorted(metricas["segmento_regra"].unique()),
        default=sorted(metricas["segmento_regra"].unique()),
        key="filtro_regra",
    )
    tabela_filtrada = metricas[metricas["segmento_regra"].isin(segmento_filtro)]

    tabela_regra = tabela_filtrada[
        [
            "usuario_id",
            "empresa",
            "segmento_regra",
            "ultimo_acesso",
            "recencia_dias",
            "dias_ativos",
            "propostas_enviadas",
            "pagina_mais_acessada",
        ]
    ].copy()
    tabela_regra["pagina_mais_acessada"] = tabela_regra["pagina_mais_acessada"].map(nome_pagina)

    st.dataframe(
        tabela_regra.rename(columns=COLUNAS_LEGIVEIS),
        width="stretch",
        hide_index=True,
    )

    st.bar_chart(
        metricas["segmento_regra"]
        .value_counts()
        .rename_axis("Segmento")
        .rename("Fornecedores"),
        horizontal=True,
    )

# --- Aba: Segmentação por clustering ---------------------------------
with aba_cluster:
    st.subheader("Segmentação orientada a dados (K-means, k=4)")
    st.caption(
        "Agrupamento automático por similaridade de comportamento: "
        "recência, volume de eventos e propostas enviadas."
    )

    st.dataframe(
        resumo_clusters.drop(columns=["score"])
        .rename(index=nomes_clusters)
        .rename_axis("Segmento")
        .rename(
            columns={
                "recencia_dias": "Recência média (dias)",
                "total_eventos": "Eventos (média)",
                "propostas_enviadas": "Propostas enviadas (média)",
            }
        )
        .round(1),
        width="stretch",
    )

    st.bar_chart(
        metricas["segmento_cluster"]
        .value_counts()
        .rename_axis("Segmento")
        .rename("Fornecedores"),
        horizontal=True,
    )

    with st.expander("Ver tabela completa por cluster"):
        tabela_cluster = metricas[
            [
                "usuario_id",
                "empresa",
                "segmento_cluster",
                "recencia_dias",
                "total_eventos",
                "propostas_enviadas",
            ]
        ]
        st.dataframe(
            tabela_cluster.rename(columns=COLUNAS_LEGIVEIS),
            width="stretch",
            hide_index=True,
        )

# --- Aba: Validação ----------------------------------------------------
with aba_validacao:
    st.subheader("As regras batem com o comportamento real?")
    st.caption(
        "Compara a segmentação por regras com o perfil de comportamento "
        "real da base simulada, usado aqui só para medir a qualidade da "
        "segmentação."
    )

    validos = metricas.dropna(subset=["perfil_real"]).copy()
    validos["perfil_previsto"] = validos["segmento_regra"].map(MAPA_REGRA_PARA_PERFIL_REAL)
    validos["acertou"] = validos["perfil_previsto"] == validos["perfil_real"]
    acuracia = validos["acertou"].mean() * 100 if len(validos) else 0

    colA, colB, colC = st.columns(3)
    colA.metric("Acurácia das regras vs. perfil real", f"{acuracia:.1f}%")
    colB.metric("Fornecedores avaliados", len(validos))
    colC.metric(
        "Sem evento na janela (não avaliados)",
        FORNECEDORES_SEM_EVENTO_NA_JANELA,
        help="Cadastrados que não geraram nenhum evento identificado nesta janela — não têm como ser segmentados por comportamento.",
    )

    st.markdown("**Matriz de confusão** — linha: regra aplicada · coluna: perfil real")
    matriz = pd.crosstab(
        validos["segmento_regra"], validos["perfil_real"].map(PERFIS_REAIS_LEGIVEIS)
    )
    matriz.index.name = "Segmento (regra aplicada)"
    matriz.columns.name = "Perfil real"
    st.dataframe(matriz, width="stretch")

    st.divider()
    st.markdown("**Escolha do número de grupos (k) para o K-means**")
    sil_df = pd.DataFrame(
        {
            "Número de grupos (k)": list(curva_silhueta.keys()),
            "Índice de silhueta": list(curva_silhueta.values()),
        }
    ).set_index("Número de grupos (k)")
    st.bar_chart(sil_df)

    melhor_k = max(curva_silhueta, key=curva_silhueta.get)
    st.caption(
        f"O valor k={melhor_k} maximiza o índice de silhueta "
        f"({curva_silhueta[melhor_k]:.3f}), mas o dashboard usa k=4 porque, "
        "com menos grupos, o modelo deixa de diferenciar fornecedores "
        "'esporádicos' de fornecedores 'em risco' — segmentos que pedem "
        "ações diferentes."
    )

# --- Aba: Ação de reengajamento -------------------------------------
with aba_acao:
    st.subheader("Gerar e registrar uma ação de reengajamento")

    usuario_escolhido = st.selectbox(
        "Escolha um fornecedor",
        options=metricas["usuario_id"],
        key="select_usuario_acao",
    )

    linha = metricas[metricas["usuario_id"] == usuario_escolhido].iloc[0]

    colA, colB = st.columns(2)
    with colA:
        st.markdown(f"**Empresa:** {linha['empresa']}")
        st.markdown(f"**Segmento (regra):** {linha['segmento_regra']}")
        st.markdown(f"**Segmento (cluster):** {linha['segmento_cluster']}")
    with colB:
        st.markdown(f"**Recência:** {linha['recencia_dias']} dias")
        st.markdown(f"**Propostas enviadas:** {linha['propostas_enviadas']}")
        st.markdown(f"**Página mais acessada:** {nome_pagina(linha['pagina_mais_acessada'])}")

    st.markdown(f"**Canal sugerido:** {linha['canal_sugerido']}")
    st.info(linha["mensagem_sugerida"])

    if st.button("Registrar envio desta comunicação"):
        registro = {
            "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "usuario_id": linha["usuario_id"],
            "empresa": linha["empresa"],
            "segmento": linha["segmento_regra"],
            "canal": linha["canal_sugerido"],
            "mensagem": linha["mensagem_sugerida"],
        }
        registrar_envio(registro)  # grava em historico_envios.csv — sobrevive a refresh
        st.session_state["historico_envios"].append(registro)
        st.success("Comunicação registrada no histórico! Veja a aba 'Histórico de envios'.")

# --- Aba: Fila & Próxima melhor ação ---------------------------------
with aba_fila:
    st.subheader("Fila priorizada de próxima melhor ação")
    st.caption("Prioriza quem contatar primeiro e exporta um CSV pronto para o CRM.")

    fila = priorizar_fornecedores(metricas)

    st.caption(
        "Ordem: Bloqueado > Inativo > Novo cadastro > Explorador > Esporádico > "
        "Engajado (com atividade e conversão recentes, destinado ao relacionamento)."
    )
    st.dataframe(
        fila[
            [
                "usuario_id",
                "empresa",
                "segmento_regra",
                "prioridade",
                "recencia_dias",
                "canal_sugerido",
            ]
        ]
        .head(25)
        .rename(columns=COLUNAS_LEGIVEIS),
        hide_index=True,
        width="stretch",
    )

    csv_bytes = fila[
        [
            "usuario_id",
            "empresa",
            "segmento_regra",
            "prioridade",
            "recencia_dias",
            "canal_sugerido",
            "mensagem_sugerida",
        ]
    ].to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        "Exportar fila completa (CSV pronto para o CRM)",
        data=csv_bytes,
        file_name=f"fila_reengajamento_{DATA_REFERENCIA.date()}.csv",
        mime="text/csv",
    )

    st.divider()
    st.markdown("### Simulação: grupo de controle e ganho de resposta")
    st.warning(
        "**Simulação ilustrativa.** As taxas de resposta abaixo são "
        "fictícias, porque ainda não existe histórico real de respostas. "
        "Servem para mostrar como o ganho de resposta seria calculado "
        "assim que houver envios de verdade."
    )

    semente = st.number_input("Semente da simulação", value=42, step=1, key="semente_sim")
    rng = np.random.default_rng(int(semente))

    BASE_RESPOSTA = {
        "Bloqueado — taxa de acesso": 0.30,
        "Inativo — risco de perda": 0.08,
        "Novo cadastro": 0.25,
        "Explorador sem conversão": 0.15,
        "Esporádico": 0.10,
        "Engajado convertendo": 0.35,
    }
    FATOR_UPLIFT_TRATAMENTO = 1.4

    sim = fila.copy()
    sim["grupo"] = rng.choice(["Tratamento", "Controle"], size=len(sim))
    base_prob = sim["segmento_regra"].map(BASE_RESPOSTA).fillna(0.10)
    prob = np.where(
        sim["grupo"] == "Tratamento",
        (base_prob * FATOR_UPLIFT_TRATAMENTO).clip(upper=0.95),
        base_prob,
    )
    sim["respondeu_simulado"] = rng.random(len(sim)) < prob

    resumo_sim = sim.groupby("grupo")["respondeu_simulado"].mean().mul(100).round(1)
    taxa_trat = resumo_sim.get("Tratamento", 0.0)
    taxa_ctrl = resumo_sim.get("Controle", 0.0)

    colT, colC, colU = st.columns(3)
    colT.metric("Taxa de resposta simulada — Tratamento", f"{taxa_trat:.1f}%")
    colC.metric("Taxa de resposta simulada — Controle", f"{taxa_ctrl:.1f}%")
    colU.metric("Ganho simulado", f"{taxa_trat - taxa_ctrl:+.1f} p.p.")

# --- Aba: Histórico de envios ----------------------------------------
with aba_historico:
    st.subheader("Histórico de comunicações registradas nesta sessão")
    st.caption("Registro local desta demonstração — não substitui um CRM.")

    historico_atual = carregar_historico_envios()  # lê do CSV — não perde nada num refresh
    if historico_atual:
        st.dataframe(
            pd.DataFrame(historico_atual).rename(columns=COLUNAS_LEGIVEIS).iloc[::-1],
            width="stretch",
            hide_index=True,
        )
        st.caption(f"{len(historico_atual)} comunicação(ões) registrada(s) até agora.")
    else:
        st.write("Nenhuma comunicação registrada ainda. Use a aba 'Ação de reengajamento'.")

# --- Aba: Captura ao vivo (tracker.js -> tracker_server.py) ----------
with aba_ao_vivo:
    st.subheader("Eventos capturados em tempo real")

    COLUNAS_EVENTOS_LIVE = [
        "timestamp", "session_id", "anonymous_id", "usuario_id",
        "identificado", "area", "pagina", "pagina_entrada", "oportunidade_id",
    ]

    with st.expander(
        "Endereço do servidor de captura (necessário quando dashboard e "
        "servidor estão deployados em serviços diferentes)",
        expanded=not TRACKER_URL_PADRAO,
    ):
        st.caption(
            "Em produção, o dashboard e o tracker_server.py rodam em hosts "
            "diferentes (ex.: Streamlit Community Cloud + Render) — não há "
            "mais disco compartilhado, então os eventos são buscados pela "
            "API do servidor de captura (GET /api/events) em vez do CSV "
            "local. Configure TRACKER_URL em st.secrets para não precisar "
            "preencher isso toda vez."
        )
        tracker_url = st.text_input(
            "URL pública do tracker_server (https://nexo-t2cn.onrender.com/)",
            value=TRACKER_URL_PADRAO,
            key="tracker_url_input",
        ).strip().rstrip("/")

    def carregar_eventos_live(url_servidor: str):
        """Busca os eventos pela API do servidor (deploy) ou, na ausência
        de URL configurada, cai para o CSV local (uso local/vídeo)."""
        if url_servidor:
            try:
                resposta = requests.get(f"{url_servidor}/api/events", timeout=5)
                resposta.raise_for_status()
                dados = resposta.json()
                return pd.DataFrame(dados) if dados else pd.DataFrame(columns=COLUNAS_EVENTOS_LIVE), None
            except Exception as erro:
                return pd.DataFrame(columns=COLUNAS_EVENTOS_LIVE), str(erro)

        if not os.path.exists(CAMINHO_EVENTOS_LIVE):
            return pd.DataFrame(columns=COLUNAS_EVENTOS_LIVE), None
        return pd.read_csv(CAMINHO_EVENTOS_LIVE), None

    modo_ao_vivo = st.toggle("Atualizar automaticamente (a cada 2 segundos)", value=False)
    if st.button("Atualizar agora"):
        st.rerun()

    eventos_live, erro_busca = carregar_eventos_live(tracker_url)

    if erro_busca:
        st.error(
            f"Não foi possível buscar eventos em `{tracker_url}/api/events`: "
            f"{erro_busca}. Confira se o servidor de captura está no ar."
        )
    elif tracker_url:
        st.caption(f"Buscando eventos em `{tracker_url}` — abra a URL acima em outra aba para gerar cliques.")
    else:
        st.caption(
            "Nenhuma URL configurada: lendo eventos_live.csv local. Rode "
            "`python captura/tracker_server.py` e abra http://localhost:5000 "
            "em outra aba para gerar eventos."
        )
    identificado_bool = (
        eventos_live["identificado"].astype(str).isin(["1", "1.0", "True"])
        if len(eventos_live)
        else pd.Series(dtype=bool)
    )

    colx, coly, colz, colw = st.columns(4)
    colx.metric("Eventos recebidos", len(eventos_live))
    coly.metric("Sessões únicas", int(eventos_live["session_id"].nunique()) if len(eventos_live) else 0)
    colz.metric("Eventos identificados", int(identificado_bool.sum()) if len(eventos_live) else 0)
    colw.metric(
        "Sessões com identidade vinculada",
        int(eventos_live.loc[identificado_bool, "session_id"].nunique()) if len(eventos_live) else 0,
    )

    if len(eventos_live):
        tabela_eventos = eventos_live.tail(30)[
            ["timestamp", "area", "pagina", "anonymous_id", "usuario_id", "identificado", "oportunidade_id"]
        ].iloc[::-1].copy()
        tabela_eventos["pagina"] = tabela_eventos["pagina"].map(nome_pagina)
        tabela_eventos["area"] = tabela_eventos["area"].replace(
            {"publica": "Pública", "interna": "Interna"}
        )
        tabela_eventos["identificado"] = (
            tabela_eventos["identificado"].astype(str).isin(["1", "1.0", "True"])
        ).map({True: "Sim", False: "Não"})
        st.dataframe(
            tabela_eventos.rename(columns=COLUNAS_LEGIVEIS),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info(
            "Nenhum evento ainda. Rode `python tracker_server.py` e abra "
            "http://localhost:5000 em outra aba para gerar eventos."
        )

    if modo_ao_vivo:
        time.sleep(2)
        st.rerun()
