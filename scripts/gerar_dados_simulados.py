"""
Gerador de dados simulados de acesso ao Portal Petronect — v2
==============================================================

Por que existe
--------------
O desafio pergunta "como identificar os acessos ao Portal e reengajar o
usuário certo". Uma base em que todo evento já vem com `usuario_id`
preenchido responde à pergunta antes de fazê-la. Este gerador simula o
Portal como ele funciona de verdade:

* **Área pública (anônima)** — consulta de oportunidades sem login. Aqui
  só existe `anonymous_id` (cookie primário). É exatamente a população que
  hoje é invisível.
* **Momento de identificação** — ao clicar em "Tenho Interesse", o visitante
  faz login (se já tem cadastro) ou inicia a identificação. É o ponto de
  *stitching* anônimo → identificado.
* **Área interna** — painel de oportunidades, proposta, sala de colaboração,
  assinatura. Aqui a identidade já existe no SAP.
* **Taxa de acesso / Sócio Fornecedor** — quem não é sócio bate no bloqueio
  ao tentar participar de oportunidade pública. É um abandono de alto valor
  para reengajamento, e precisa existir no dado.

Como a navegação é gerada
-------------------------
Cadeia de Markov de primeira ordem sobre as páginas do Portal, com estado
absorvente `__fim__`. A matriz de transição é *parametrizada pelo contexto*
(perfil de comportamento, se está logado, se é sócio fornecedor), então o
mesmo grafo produz jornadas diferentes por perfil — em vez de páginas
sorteadas de forma independente, que destroem qualquer análise de jornada.

Saídas (gravadas em ../dados, relativo a este script)
------------------------------------------------------
* `acessos_simulados.csv`  — eventos (pageviews), grão: 1 linha por página vista
* `oportunidades.csv`      — catálogo de oportunidades publicadas
* `fornecedores.csv`       — cadastro (inclui `data_cadastro` real e `perfil_real`)

Uso
---
    python scripts/gerar_dados_simulados.py
    python scripts/gerar_dados_simulados.py --seed 7 --fornecedores 150 --dias 120

Sem dependências externas: apenas biblioteca padrão.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# ==================================================================
# 1. Parâmetros gerais
# ==================================================================

DATA_FIM_PADRAO = datetime(2026, 9, 15, 23, 59)
DIAS_HISTORICO_PADRAO = 90
N_FORNECEDORES_PADRAO = 120          # visitantes que possuem (ou criarão) cadastro
N_VISITANTES_ANONIMOS_PADRAO = 70    # nunca se identificam — o "ponto cego" de hoje
N_OPORTUNIDADES_PADRAO = 90

TIMEOUT_SESSAO_MIN = 30              # regra de sessionização (padrão de mercado)
MAX_PASSOS_SESSAO = 25               # trava de segurança da cadeia de Markov

FIM = "__fim__"

# ------------------------------------------------------------------
# Catálogo de páginas e a que área do Portal cada uma pertence.
# Nomes espelham a navegação real: área externa (pública) x área interna.
# ------------------------------------------------------------------

AREA_DA_PAGINA: dict[str, str] = {
    # --- área pública / externa (sem login) ---
    "home_publica": "publica",
    "busca_publica": "publica",
    "lista_oportunidades_publicas": "publica",
    "detalhe_oportunidade_publica": "publica",
    "tenho_interesse": "publica",
    "login": "publica",
    "iniciar_identificacao": "publica",
    "quer_se_cadastrar": "publica",
    "modelo_cobranca_socio": "publica",
    "ajuda_treinamentos": "publica",
    "avisos": "publica",
    # --- área interna (exige login) ---
    "painel_oportunidades": "interna",
    "detalhe_oportunidade": "interna",
    "taxa_acesso_bloqueio": "interna",
    "envio_proposta": "interna",
    "minhas_participacoes": "interna",
    "sala_colaboracao": "interna",
    "cadastro_fornecedor": "interna",
    "assinatura_eletronica": "interna",
    "meus_dados": "interna",
}

# Páginas em que o visitante ESCOLHE qual oportunidade olhar.
PAGINAS_ESCOLHA_OPORTUNIDADE = {
    "detalhe_oportunidade_publica",
    "detalhe_oportunidade",
}

# Páginas que CONTINUAM a oportunidade já em foco. Sem essa distinção, a
# proposta acaba vinculada a uma oportunidade diferente da que foi vista —
# e aí funil por oportunidade e "viu X e não propôs" viram ficção.
PAGINAS_CONTINUACAO_OPORTUNIDADE = {
    "tenho_interesse",
    "taxa_acesso_bloqueio",
    "envio_proposta",
    "sala_colaboracao",
    "assinatura_eletronica",
}

PAGINAS_COM_OPORTUNIDADE = PAGINAS_ESCOLHA_OPORTUNIDADE | PAGINAS_CONTINUACAO_OPORTUNIDADE

CATEGORIAS = [
    "valvulas",
    "bombas_compressores",
    "tubulacao_conexoes",
    "eletrica_instrumentacao",
    "servicos_manutencao",
    "servicos_engenharia",
    "epi_seguranca",
    "logistica_transporte",
]

# Modalidade influencia a exigência de taxa de acesso:
# dispensa (valores baixos) é isenta; pregão/concorrência exigem Sócio Fornecedor.
MODALIDADES = {
    "pregao_eletronico": {"peso": 0.45, "exige_socio": True},
    "concorrencia": {"peso": 0.20, "exige_socio": True},
    "dispensa_eletronica": {"peso": 0.35, "exige_socio": False},
}

UFS = ["RJ", "SP", "BA", "RS", "SE", "PR", "MG", "ES", "AM", "RN", "PE", "SC"]
PORTES = ["MEI", "Pequeno", "Medio", "Grande"]
DEVICES = {"desktop": 0.74, "mobile": 0.22, "tablet": 0.04}

# Origem de tráfego por sessão. `identifica_direto=True` significa que o link
# carrega um identificador (campanha de e-mail com uid) — a sessão nasce
# identificada mesmo na área pública. É um dos caminhos de captura de identidade.
ORIGENS = {
    "direto": {"peso": 0.34, "utm_source": "(direct)", "utm_medium": "(none)", "utm_campaign": "", "identifica_direto": False},
    "organico_google": {"peso": 0.26, "utm_source": "google", "utm_medium": "organic", "utm_campaign": "", "identifica_direto": False},
    "email_campanha": {"peso": 0.14, "utm_source": "petronect_crm", "utm_medium": "email", "utm_campaign": "reengajamento_2026q3", "identifica_direto": True},
    "email_aviso": {"peso": 0.08, "utm_source": "petronect_crm", "utm_medium": "email", "utm_campaign": "aviso_oportunidade", "identifica_direto": True},
    "linkedin": {"peso": 0.07, "utm_source": "linkedin", "utm_medium": "social", "utm_campaign": "marca_empregadora", "identifica_direto": False},
    "google_ads": {"peso": 0.06, "utm_source": "google", "utm_medium": "cpc", "utm_campaign": "fornecedores_oleo_gas", "identifica_direto": False},
    "referral_petrobras": {"peso": 0.05, "utm_source": "petrobras.com.br", "utm_medium": "referral", "utm_campaign": "", "identifica_direto": False},
}

# ==================================================================
# 2. Perfis de comportamento (ground truth)
# ==================================================================
#
# `perfil_real` é salvo no CSV de propósito: permite validar a segmentação
# (matriz de confusão das regras / clusters contra o comportamento real).
#
# prob_dia .............. probabilidade de abrir uma sessão num dia útil
# p_interesse ........... chance de clicar "Tenho Interesse" no detalhe
# p_conclui_proposta .... chance de concluir o envio quando chega na página
# socio_fornecedor ...... pagou a taxa de acesso (senão bate no bloqueio)
# cadastrado ............ já possui usuário no Portal no início da janela
# janela ................ "toda", "inicial" (cessa atividade) ou "final" (novo)

PERFIS: dict[str, dict] = {
    "ativo_convertendo": {
        "peso": 0.14,
        "prob_dia": 0.30,
        "p_interesse": 0.70,
        "p_conclui_proposta": 0.62,
        "socio_fornecedor": True,
        "cadastrado": True,
        "janela": "toda",
        "prob_sessao_ja_logada": 0.75,
    },
    "explorador_sem_conversao": {
        "peso": 0.24,
        "prob_dia": 0.22,
        "p_interesse": 0.45,
        "p_conclui_proposta": 0.04,
        "socio_fornecedor": True,
        "cadastrado": True,
        "janela": "toda",
        "prob_sessao_ja_logada": 0.55,
    },
    "bloqueado_taxa_acesso": {
        "peso": 0.14,
        "prob_dia": 0.20,
        "p_interesse": 0.75,
        "p_conclui_proposta": 0.35,   # só consegue em dispensa (isenta)
        "socio_fornecedor": False,
        "cadastrado": True,
        "janela": "toda",
        "prob_sessao_ja_logada": 0.50,
    },
    "esporadico": {
        "peso": 0.18,
        "prob_dia": 0.05,
        "p_interesse": 0.30,
        "p_conclui_proposta": 0.20,
        "socio_fornecedor": True,
        "cadastrado": True,
        "janela": "toda",
        "prob_sessao_ja_logada": 0.45,
    },
    "inativo_em_risco": {
        # Tem atividade REAL e depois cessa. Na v1 esse perfil tinha
        # prob_dia=0.0 e não gerava evento nenhum: o segmento mais
        # importante do caso de negócio simplesmente não existia na base.
        "peso": 0.18,
        "prob_dia": 0.26,
        "p_interesse": 0.50,
        "p_conclui_proposta": 0.25,
        "socio_fornecedor": True,
        "cadastrado": True,
        "janela": "inicial",
        "prob_sessao_ja_logada": 0.60,
    },
    "novo_cadastro": {
        # Chega anônimo pela área pública nos últimos dias e se identifica.
        "peso": 0.12,
        "prob_dia": 0.42,
        "p_interesse": 0.60,
        "p_conclui_proposta": 0.18,
        "socio_fornecedor": False,
        "cadastrado": False,
        "janela": "final",
        "prob_sessao_ja_logada": 0.35,
    },
}

PERFIL_ANONIMO = {
    "peso": 1.0,
    "prob_dia": 0.12,
    "p_interesse": 0.22,
    "p_conclui_proposta": 0.0,
    "socio_fornecedor": False,
    "cadastrado": False,
    "janela": "toda",
    "prob_sessao_ja_logada": 0.0,
}


# ==================================================================
# 3. Estruturas
# ==================================================================


@dataclass
class Oportunidade:
    oportunidade_id: str
    categoria: str
    modalidade: str
    data_publicacao: date
    data_fim: date

    def aberta_em(self, momento: datetime) -> bool:
        return self.data_publicacao <= momento.date() <= self.data_fim


@dataclass
class Visitante:
    anonymous_id: str
    usuario_id: str          # "" enquanto não identificado
    empresa: str
    cnpj_hash: str
    perfil_real: str
    categorias_interesse: list[str]
    uf: str
    porte: str
    device: str
    params: dict
    cadastrado: bool
    socio_fornecedor: bool
    dia_inicio: int
    dia_fim: int
    ja_identificado: bool = False           # já se identificou em algum momento
    data_cadastro: date | None = None
    anonymous_ids: list[str] = field(default_factory=list)


# ==================================================================
# 4. Cadeia de Markov: matriz de transição parametrizada
# ==================================================================


def matriz_transicao(ctx: dict) -> dict[str, dict[str, float]]:
    """Matriz de transição condicionada ao contexto da sessão.

    `ctx` traz p_interesse, socio_fornecedor, cadastrado, oportunidade_exige_socio.
    Pesos não precisam somar 1 — são normalizados na hora do sorteio.
    """
    p_int = ctx["p_interesse"]
    tem_conta = ctx["cadastrado"] or ctx["ja_identificado"]

    # No detalhe da oportunidade interna, o caminho depende da taxa de acesso:
    # sócio (ou dispensa isenta) segue para envio; senão bate no bloqueio.
    pode_propor = ctx["socio_fornecedor"] or not ctx["oportunidade_exige_socio"]

    m: dict[str, dict[str, float]] = {
        # ---------------- área pública ----------------
        "home_publica": {
            "busca_publica": 0.34,
            "lista_oportunidades_publicas": 0.22,
            "avisos": 0.09,
            "ajuda_treinamentos": 0.07,
            "quer_se_cadastrar": 0.06,
            "modelo_cobranca_socio": 0.03,
            "login": 0.09 if tem_conta else 0.0,
            FIM: 0.19,
        },
        "busca_publica": {
            "lista_oportunidades_publicas": 0.56,
            "busca_publica": 0.14,            # refinar a busca
            "detalhe_oportunidade_publica": 0.09,
            "home_publica": 0.04,
            FIM: 0.17,
        },
        "lista_oportunidades_publicas": {
            "detalhe_oportunidade_publica": 0.52,
            "busca_publica": 0.13,
            "lista_oportunidades_publicas": 0.09,   # paginação
            "modelo_cobranca_socio": 0.03,
            FIM: 0.23,
        },
        "detalhe_oportunidade_publica": {
            "tenho_interesse": p_int,
            "lista_oportunidades_publicas": 0.26 * (1 - p_int) + 0.10,
            "detalhe_oportunidade_publica": 0.12 * (1 - p_int),
            "ajuda_treinamentos": 0.04 * (1 - p_int),
            FIM: 0.38 * (1 - p_int),
        },
        "tenho_interesse": {
            "login": 0.88 if tem_conta else 0.0,
            "iniciar_identificacao": 0.0 if tem_conta else 0.62,
            "quer_se_cadastrar": 0.0 if tem_conta else 0.10,
            FIM: 0.12 if tem_conta else 0.28,
        },
        "login": {
            "painel_oportunidades": 0.90,
            "meus_dados": 0.04,
            FIM: 0.06,
        },
        "iniciar_identificacao": {
            "cadastro_fornecedor": 0.58,
            "ajuda_treinamentos": 0.08,
            FIM: 0.34,
        },
        "quer_se_cadastrar": {
            "iniciar_identificacao": 0.34,
            "ajuda_treinamentos": 0.14,
            "home_publica": 0.08,
            FIM: 0.44,
        },
        "modelo_cobranca_socio": {
            "lista_oportunidades_publicas": 0.18,
            "ajuda_treinamentos": 0.12,
            "login": 0.14 if tem_conta else 0.0,
            FIM: 0.56,
        },
        "ajuda_treinamentos": {
            "home_publica": 0.16,
            "busca_publica": 0.12,
            "avisos": 0.06,
            FIM: 0.66,
        },
        "avisos": {
            "home_publica": 0.18,
            "lista_oportunidades_publicas": 0.14,
            FIM: 0.68,
        },
        # ---------------- área interna ----------------
        "painel_oportunidades": {
            "detalhe_oportunidade": 0.48,
            "minhas_participacoes": 0.14,
            "sala_colaboracao": 0.09,
            "cadastro_fornecedor": 0.07,
            "meus_dados": 0.04,
            "painel_oportunidades": 0.06,
            FIM: 0.12,
        },
        "detalhe_oportunidade": {
            "envio_proposta": (0.46 * p_int) if pode_propor else 0.0,
            "taxa_acesso_bloqueio": 0.0 if pode_propor else (0.52 * p_int),
            "sala_colaboracao": 0.14,
            "painel_oportunidades": 0.22,
            "detalhe_oportunidade": 0.07,
            FIM: 0.16,
        },
        "taxa_acesso_bloqueio": {
            # Abandono de altíssimo valor para reengajamento.
            "modelo_cobranca_socio": 0.22,
            "painel_oportunidades": 0.16,
            "ajuda_treinamentos": 0.08,
            FIM: 0.54,
        },
        "envio_proposta": {
            "minhas_participacoes": 0.30,
            "painel_oportunidades": 0.18,
            "sala_colaboracao": 0.08,
            FIM: 0.44,
        },
        "minhas_participacoes": {
            "detalhe_oportunidade": 0.20,
            "sala_colaboracao": 0.16,
            "assinatura_eletronica": 0.06,
            "painel_oportunidades": 0.18,
            FIM: 0.40,
        },
        "sala_colaboracao": {
            "detalhe_oportunidade": 0.26,
            "minhas_participacoes": 0.12,
            "painel_oportunidades": 0.14,
            FIM: 0.48,
        },
        "cadastro_fornecedor": {
            "cadastro_fornecedor": 0.22,      # formulário em várias telas
            "meus_dados": 0.10,
            "painel_oportunidades": 0.20,
            "ajuda_treinamentos": 0.06,
            FIM: 0.42,
        },
        "assinatura_eletronica": {
            "minhas_participacoes": 0.24,
            "painel_oportunidades": 0.14,
            FIM: 0.62,
        },
        "meus_dados": {
            "painel_oportunidades": 0.30,
            "cadastro_fornecedor": 0.14,
            FIM: 0.56,
        },
    }
    return m


def sortear_proximo(estado: str, matriz: dict, rng: random.Random) -> str:
    destinos = {k: p for k, p in matriz[estado].items() if p > 0}
    if not destinos:
        return FIM
    nomes = list(destinos)
    pesos = [destinos[n] for n in nomes]
    return rng.choices(nomes, weights=pesos, k=1)[0]


# ==================================================================
# 5. Geração de catálogo, fornecedores e visitantes anônimos
# ==================================================================


def sortear_ponderado(mapa: dict, rng: random.Random, chave_peso: str = "peso") -> str:
    nomes = list(mapa)
    pesos = [mapa[n][chave_peso] if isinstance(mapa[n], dict) else mapa[n] for n in nomes]
    return rng.choices(nomes, weights=pesos, k=1)[0]


def gerar_oportunidades(n: int, inicio: date, fim: date, rng: random.Random) -> list[Oportunidade]:
    total_dias = (fim - inicio).days
    ops = []
    for i in range(1, n + 1):
        publicacao = inicio + timedelta(days=rng.randint(-20, total_dias - 5))
        duracao = rng.choice([7, 10, 12, 15, 20, 25, 30])
        ops.append(
            Oportunidade(
                oportunidade_id=f"OP-2026-{i:04d}",
                categoria=rng.choice(CATEGORIAS),
                modalidade=sortear_ponderado(MODALIDADES, rng),
                data_publicacao=publicacao,
                data_fim=publicacao + timedelta(days=duracao),
            )
        )
    return ops


def hash_cnpj(semente: str) -> str:
    """Pseudonimização: o dado que trafega é hash, não o CNPJ (LGPD)."""
    return hashlib.sha256(f"cnpj::{semente}".encode()).hexdigest()[:16]


def alocar_perfis(n: int, rng: random.Random) -> list[str]:
    """Distribui os perfis por cota (maior resto), não por sorteio.

    Sortear perfil a perfil deixa a composição da base à mercê do seed: com
    n=120 o desvio chegou a 3 sigma num teste, esvaziando o perfil
    `ativo_convertendo`. A demo não pode depender de sorte.
    """
    nomes = list(PERFIS)
    exatos = {nome: PERFIS[nome]["peso"] * n for nome in nomes}
    cotas = {nome: int(valor) for nome, valor in exatos.items()}
    resto = n - sum(cotas.values())
    for nome in sorted(nomes, key=lambda x: exatos[x] - cotas[x], reverse=True)[:resto]:
        cotas[nome] += 1

    perfis = [nome for nome, qtd in cotas.items() for _ in range(qtd)]
    rng.shuffle(perfis)
    return perfis


def gerar_visitantes(
    n_fornecedores: int,
    n_anonimos: int,
    total_dias: int,
    inicio: date,
    rng: random.Random,
) -> list[Visitante]:
    visitantes: list[Visitante] = []
    perfis_alocados = alocar_perfis(n_fornecedores, rng)

    def janela(tipo: str) -> tuple[int, int]:
        if tipo == "inicial":
            # Atividade real que CESSA: some entre o dia 20 e o dia 55.
            return 0, rng.randint(20, min(55, total_dias - 25))
        if tipo == "final":
            return rng.randint(total_dias - 14, total_dias - 6), total_dias
        return 0, total_dias

    for i in range(1, n_fornecedores + 1):
        perfil = perfis_alocados[i - 1]
        p = PERFIS[perfil]
        d_ini, d_fim = janela(p["janela"])
        cadastrado = p["cadastrado"]
        visitantes.append(
            Visitante(
                anonymous_id=f"anon_{rng.getrandbits(40):010x}",
                usuario_id=f"U{i:04d}",
                empresa=f"Fornecedor {i:04d} LTDA",
                cnpj_hash=hash_cnpj(f"U{i:04d}"),
                perfil_real=perfil,
                categorias_interesse=rng.sample(CATEGORIAS, k=rng.randint(1, 3)),
                uf=rng.choice(UFS),
                porte=rng.choice(PORTES),
                device=rng.choices(list(DEVICES), weights=list(DEVICES.values()), k=1)[0],
                params=p,
                cadastrado=cadastrado,
                socio_fornecedor=p["socio_fornecedor"],
                dia_inicio=d_ini,
                dia_fim=d_fim,
                # Quem já era cadastrado tem data anterior à janela observada.
                data_cadastro=None if not cadastrado else inicio - timedelta(days=rng.randint(30, 2200)),
            )
        )

    for j in range(1, n_anonimos + 1):
        visitantes.append(
            Visitante(
                anonymous_id=f"anon_{rng.getrandbits(40):010x}",
                usuario_id="",
                empresa="",
                cnpj_hash="",
                perfil_real="anonimo_recorrente",
                categorias_interesse=rng.sample(CATEGORIAS, k=rng.randint(1, 3)),
                uf=rng.choice(UFS),
                porte="",
                device=rng.choices(list(DEVICES), weights=list(DEVICES.values()), k=1)[0],
                params=PERFIL_ANONIMO,
                cadastrado=False,
                socio_fornecedor=False,
                dia_inicio=0,
                dia_fim=total_dias,
                data_cadastro=None,
            )
        )

    return visitantes


# ==================================================================
# 6. Simulação de sessões
# ==================================================================


def horario_inicio(dia: date, rng: random.Random) -> datetime:
    """Horário comercial com pico 9–11h e 14–17h; cauda noturna pequena."""
    faixas = [
        (range(7, 9), 0.10),
        (range(9, 12), 0.34),
        (range(12, 14), 0.12),
        (range(14, 18), 0.33),
        (range(18, 22), 0.11),
    ]
    faixa = rng.choices([f for f, _ in faixas], weights=[p for _, p in faixas], k=1)[0]
    hora = rng.choice(list(faixa))
    return datetime(dia.year, dia.month, dia.day, hora, rng.randint(0, 59), rng.randint(0, 59))


def tempo_na_pagina(pagina: str, rng: random.Random) -> int:
    """Segundos até a próxima página. Sempre < timeout de sessão."""
    base = {
        "detalhe_oportunidade_publica": (45, 400),
        "detalhe_oportunidade": (60, 480),
        "envio_proposta": (180, 900),
        "cadastro_fornecedor": (120, 700),
        "sala_colaboracao": (60, 420),
        "modelo_cobranca_socio": (40, 300),
        "taxa_acesso_bloqueio": (20, 180),
        "busca_publica": (20, 150),
        "lista_oportunidades_publicas": (25, 200),
    }.get(pagina, (15, 180))
    return rng.randint(*base)


def escolher_oportunidade(
    visitante: Visitante,
    momento: datetime,
    oportunidades: list[Oportunidade],
    atual: Oportunidade | None,
    rng: random.Random,
    travada: bool,
) -> Oportunidade | None:
    """Seleciona a oportunidade em foco.

    * 70% das visualizações caem nas categorias de interesse do visitante.
    * Depois de "Tenho Interesse" a oportunidade fica travada (92%): o
      fornecedor está conduzindo aquele processo específico até o fim.
    """
    continuidade = 0.92 if travada else 0.70
    if atual is not None and rng.random() < continuidade:
        return atual
    abertas = [o for o in oportunidades if o.aberta_em(momento)]
    if not abertas:
        return atual
    do_interesse = [o for o in abertas if o.categoria in visitante.categorias_interesse]
    if do_interesse and rng.random() < 0.70:
        return rng.choice(do_interesse)
    return rng.choice(abertas)


def estado_inicial(ja_logado: bool, origem: str, rng: random.Random) -> str:
    if ja_logado:
        return rng.choices(
            ["painel_oportunidades", "home_publica", "minhas_participacoes"],
            weights=[0.72, 0.18, 0.10],
            k=1,
        )[0]
    if origem in ("email_campanha", "email_aviso"):
        return rng.choices(
            ["lista_oportunidades_publicas", "detalhe_oportunidade_publica", "avisos", "home_publica"],
            weights=[0.34, 0.34, 0.16, 0.16],
            k=1,
        )[0]
    if origem in ("organico_google", "google_ads"):
        return rng.choices(
            ["lista_oportunidades_publicas", "busca_publica", "home_publica", "quer_se_cadastrar"],
            weights=[0.34, 0.24, 0.30, 0.12],
            k=1,
        )[0]
    return rng.choices(
        ["home_publica", "busca_publica", "lista_oportunidades_publicas", "avisos"],
        weights=[0.52, 0.18, 0.22, 0.08],
        k=1,
    )[0]


def simular_sessao(
    visitante: Visitante,
    inicio: datetime,
    oportunidades: list[Oportunidade],
    rng: random.Random,
) -> list[dict]:
    p = visitante.params
    origem = sortear_ponderado(ORIGENS, rng)
    cfg_origem = ORIGENS[origem]

    ja_logado = visitante.ja_identificado and rng.random() < p["prob_sessao_ja_logada"]

    # Link de campanha com uid identifica a sessão mesmo na área pública.
    identificado = ja_logado or (
        cfg_origem["identifica_direto"] and visitante.ja_identificado
    )

    estado = estado_inicial(ja_logado, origem, rng)
    momento = inicio
    op_atual: Oportunidade | None = None
    op_travada = False
    eventos: list[dict] = []

    for _ in range(MAX_PASSOS_SESSAO):
        if estado == FIM:
            break

        # Voltar para uma listagem/busca libera a escolha de outra oportunidade.
        # O painel NÃO libera: é a tela onde o fornecedor cai depois do login
        # para continuar justamente o processo em que manifestou interesse.
        if estado in ("lista_oportunidades_publicas", "busca_publica"):
            op_travada = False

        # A oportunidade em foco define se a taxa de acesso é exigida.
        if estado in PAGINAS_ESCOLHA_OPORTUNIDADE:
            op_atual = escolher_oportunidade(visitante, momento, oportunidades, op_atual, rng, op_travada)
        elif estado in PAGINAS_CONTINUACAO_OPORTUNIDADE:
            if op_atual is None:
                op_atual = escolher_oportunidade(visitante, momento, oportunidades, None, rng, False)
            if estado == "tenho_interesse":
                op_travada = True

        # Login / identificação: é AQUI que o anônimo vira identificado.
        if estado in ("login", "iniciar_identificacao"):
            identificado = True
            visitante.ja_identificado = True
            if visitante.data_cadastro is None:
                visitante.data_cadastro = momento.date()

        enviou = 0
        if estado == "envio_proposta" and rng.random() < p["p_conclui_proposta"]:
            enviou = 1

        eventos.append(
            {
                "timestamp": momento,
                "anonymous_id": visitante.anonymous_id,
                "usuario_id": visitante.usuario_id if identificado else "",
                "empresa": visitante.empresa if identificado else "",
                "cnpj_hash": visitante.cnpj_hash if identificado else "",
                "identificado": int(identificado),
                "perfil_real": visitante.perfil_real,
                "area": AREA_DA_PAGINA[estado],
                "pagina": estado,
                "oportunidade_id": op_atual.oportunidade_id if (op_atual and estado in PAGINAS_COM_OPORTUNIDADE) else "",
                "categoria": op_atual.categoria if (op_atual and estado in PAGINAS_COM_OPORTUNIDADE) else "",
                "modalidade": op_atual.modalidade if (op_atual and estado in PAGINAS_COM_OPORTUNIDADE) else "",
                "enviou_proposta": enviou,
                "utm_source": cfg_origem["utm_source"],
                "utm_medium": cfg_origem["utm_medium"],
                "utm_campaign": cfg_origem["utm_campaign"],
                "device": visitante.device,
                "uf": visitante.uf,
                "porte_empresa": visitante.porte,
            }
        )

        ctx = {
            "p_interesse": p["p_interesse"],
            "socio_fornecedor": visitante.socio_fornecedor,
            "cadastrado": visitante.cadastrado,
            "ja_identificado": visitante.ja_identificado,
            "oportunidade_exige_socio": (
                MODALIDADES[op_atual.modalidade]["exige_socio"] if op_atual else True
            ),
        }
        estado = sortear_proximo(estado, matriz_transicao(ctx), rng)
        momento = momento + timedelta(seconds=tempo_na_pagina(eventos[-1]["pagina"], rng))

    return eventos


def gerar_eventos(
    visitantes: list[Visitante],
    oportunidades: list[Oportunidade],
    inicio: date,
    total_dias: int,
    rng: random.Random,
) -> list[dict]:
    eventos: list[dict] = []

    for visitante in visitantes:
        visitante.anonymous_ids = [visitante.anonymous_id]
        # ~12% dos visitantes perdem o cookie no meio do histórico e passam a
        # ser contados como um "novo" visitante anônimo. É a razão de existir
        # o stitching por login/uid — e precisa estar no dado.
        dia_reset = rng.randint(20, total_dias - 10) if rng.random() < 0.12 else None

        for d in range(visitante.dia_inicio, visitante.dia_fim + 1):
            dia = inicio + timedelta(days=d)

            if dia_reset is not None and d == dia_reset:
                visitante.anonymous_id = f"anon_{rng.getrandbits(40):010x}"
                visitante.anonymous_ids.append(visitante.anonymous_id)

            # Fim de semana tem volume muito menor num portal B2B.
            fator_dia = 0.18 if dia.weekday() >= 5 else 1.0
            if rng.random() > visitante.params["prob_dia"] * fator_dia:
                continue

            n_sessoes = 1 if rng.random() > 0.18 else 2
            horarios = sorted(horario_inicio(dia, rng) for _ in range(n_sessoes))
            ultimo_fim: datetime | None = None

            for h in horarios:
                # Garante separação > timeout entre sessões do mesmo dia,
                # senão a sessionização iria fundi-las.
                if ultimo_fim is not None and h <= ultimo_fim + timedelta(minutes=TIMEOUT_SESSAO_MIN + 5):
                    h = ultimo_fim + timedelta(minutes=TIMEOUT_SESSAO_MIN + rng.randint(6, 180))
                if h.date() != dia:
                    break
                sessao = simular_sessao(visitante, h, oportunidades, rng)
                if not sessao:
                    continue
                eventos.extend(sessao)
                ultimo_fim = sessao[-1]["timestamp"]

    # Garantia: nenhum visitante fica com zero eventos. Janelas curtas
    # (novo_cadastro) podem não sortear nenhum dia; sem esta rede, um perfil
    # inteiro some da base — foi exatamente assim que a v1 perdeu os inativos.
    com_evento = {e["anonymous_id"] for e in eventos}
    for visitante in visitantes:
        if any(a in com_evento for a in visitante.anonymous_ids):
            continue
        dia = inicio + timedelta(days=rng.randint(visitante.dia_inicio, visitante.dia_fim))
        sessao = simular_sessao(visitante, horario_inicio(dia, rng), oportunidades, rng)
        eventos.extend(sessao)

    eventos.sort(key=lambda e: (e["timestamp"], e["anonymous_id"]))
    return eventos


# ==================================================================
# 7. Sessionização (regra de 30 minutos) e IDs
# ==================================================================


def atribuir_sessoes(eventos: list[dict]) -> None:
    """Aplica a regra padrão: gap > 30 min no mesmo anonymous_id = nova sessão.

    A sessão é derivada do dado, não carimbada na geração — é exatamente o
    cálculo que o pipeline de produção teria que fazer.
    """
    por_visitante: dict[str, list[dict]] = {}
    for e in eventos:
        por_visitante.setdefault(e["anonymous_id"], []).append(e)

    for anon_id, lista in por_visitante.items():
        lista.sort(key=lambda e: e["timestamp"])
        n_sessao = 0
        anterior: datetime | None = None
        ordem = 0
        for e in lista:
            if anterior is None or (e["timestamp"] - anterior) > timedelta(minutes=TIMEOUT_SESSAO_MIN):
                n_sessao += 1
                ordem = 0
            ordem += 1
            e["session_id"] = f"{anon_id}-S{n_sessao:03d}"
            e["ordem_na_sessao"] = ordem
            e["pagina_entrada"] = 0  # ajustado abaixo
            anterior = e["timestamp"]

    # Marca a página de entrada (o "onde clica primeiro" do enunciado).
    por_sessao: dict[str, list[dict]] = {}
    for e in eventos:
        por_sessao.setdefault(e["session_id"], []).append(e)
    for lista in por_sessao.values():
        lista.sort(key=lambda e: e["ordem_na_sessao"])
        lista[0]["pagina_entrada"] = 1

    for i, e in enumerate(sorted(eventos, key=lambda x: (x["timestamp"], x["anonymous_id"])), start=1):
        e["event_id"] = f"EV{i:07d}"


# ==================================================================
# 8. Persistência
# ==================================================================

COLUNAS_EVENTOS = [
    "event_id",
    "timestamp",
    "session_id",
    "ordem_na_sessao",
    "pagina_entrada",
    "anonymous_id",
    "usuario_id",
    "identificado",
    "empresa",
    "cnpj_hash",
    "perfil_real",
    "area",
    "pagina",
    "oportunidade_id",
    "categoria",
    "modalidade",
    "enviou_proposta",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "device",
    "uf",
    "porte_empresa",
]


def salvar_eventos(eventos: list[dict], caminho: str) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_EVENTOS)
        w.writeheader()
        for e in eventos:
            linha = dict(e)
            linha["timestamp"] = e["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            w.writerow({c: linha.get(c, "") for c in COLUNAS_EVENTOS})


def salvar_oportunidades(ops: list[Oportunidade], caminho: str) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["oportunidade_id", "categoria", "modalidade", "exige_socio_fornecedor", "data_publicacao", "data_fim"])
        for o in ops:
            w.writerow([
                o.oportunidade_id,
                o.categoria,
                o.modalidade,
                int(MODALIDADES[o.modalidade]["exige_socio"]),
                o.data_publicacao.isoformat(),
                o.data_fim.isoformat(),
            ])


def salvar_fornecedores(visitantes: list[Visitante], caminho: str) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "usuario_id", "empresa", "cnpj_hash", "perfil_real", "data_cadastro",
            "socio_fornecedor", "categorias_interesse", "uf", "porte_empresa",
            "anonymous_ids_conhecidos",
        ])
        for v in visitantes:
            # Entra no cadastro quem já tinha conta ou se identificou na janela.
            # Visitante que nunca se identificou não é fornecedor conhecido —
            # é exatamente o ponto cego que o desafio quer iluminar.
            if not v.usuario_id or not (v.cadastrado or v.ja_identificado):
                continue
            w.writerow([
                v.usuario_id,
                v.empresa,
                v.cnpj_hash,
                v.perfil_real,
                v.data_cadastro.isoformat() if v.data_cadastro else "",
                int(v.socio_fornecedor),
                "|".join(v.categorias_interesse),
                v.uf,
                v.porte,
                "|".join(v.anonymous_ids),
            ])


# ==================================================================
# 9. Relatório de sanidade
# ==================================================================


def relatorio(eventos: list[dict], visitantes: list[Visitante], oportunidades: list[Oportunidade]) -> None:
    from collections import Counter

    sessoes = {e["session_id"] for e in eventos}
    identificados = sum(1 for e in eventos if e["identificado"] == 1)
    print("=" * 66)
    print("BASE GERADA")
    print("=" * 66)
    print(f"Eventos (pageviews)......... {len(eventos):,}")
    print(f"Sessões (timeout 30 min).... {len(sessoes):,}")
    print(f"anonymous_id distintos...... {len({e['anonymous_id'] for e in eventos}):,}")
    print(f"Oportunidades no catálogo... {len(oportunidades):,}")
    print(f"Eventos identificados....... {identificados:,} ({identificados/len(eventos):.1%})")
    print(f"Período..................... {min(e['timestamp'] for e in eventos)} → {max(e['timestamp'] for e in eventos)}")

    print("\nEventos por área:")
    for area, n in Counter(e["area"] for e in eventos).most_common():
        print(f"  {area:<10} {n:>7,}  ({n/len(eventos):.1%})")

    print("\nPáginas mais vistas:")
    for pag, n in Counter(e["pagina"] for e in eventos).most_common(10):
        print(f"  {pag:<32} {n:>6,}")

    print("\nPáginas de entrada mais comuns (o 'onde clica primeiro'):")
    entradas = Counter(e["pagina"] for e in eventos if e["pagina_entrada"] == 1)
    for pag, n in entradas.most_common(6):
        print(f"  {pag:<32} {n:>6,}  ({n/len(sessoes):.1%} das sessões)")

    print("\nFunil (sessões que passaram por cada etapa):")
    etapas = [
        ("lista/busca pública", {"lista_oportunidades_publicas", "busca_publica"}),
        ("detalhe público", {"detalhe_oportunidade_publica"}),
        ("tenho interesse", {"tenho_interesse"}),
        ("login/identificação", {"login", "iniciar_identificacao"}),
        ("detalhe interno", {"detalhe_oportunidade"}),
        ("bloqueio taxa acesso", {"taxa_acesso_bloqueio"}),
        ("envio de proposta", {"envio_proposta"}),
    ]
    for nome, paginas in etapas:
        s = {e["session_id"] for e in eventos if e["pagina"] in paginas}
        print(f"  {nome:<24} {len(s):>6,} sessões ({len(s)/len(sessoes):.1%})")

    print("\nVisitantes por perfil_real (com pelo menos 1 evento):")
    com_evento = {e["perfil_real"]: set() for e in eventos}
    for e in eventos:
        com_evento[e["perfil_real"]].add(e["anonymous_id"])
    contagem_perfil = Counter(v.perfil_real for v in visitantes)
    for perfil, total in contagem_perfil.most_common():
        ativos = len(com_evento.get(perfil, set()))
        print(f"  {perfil:<26} {total:>4} gerados | {ativos:>4} anonymous_id com eventos")

    print("\nPropostas enviadas.......... "
          f"{sum(e['enviou_proposta'] for e in eventos):,}")
    print("Sessões com bloqueio de taxa "
          f"{len({e['session_id'] for e in eventos if e['pagina'] == 'taxa_acesso_bloqueio'}):,}")

    # ---- asserts de sanidade: o que quebrou na v1 não pode voltar ----
    perfis_sem_evento = [p for p, t in contagem_perfil.items() if len(com_evento.get(p, set())) == 0]
    assert not perfis_sem_evento, f"perfis sem nenhum evento: {perfis_sem_evento}"

    ids_com_evento = {e["anonymous_id"] for e in eventos}
    mudos = [v for v in visitantes if not any(a in ids_com_evento for a in v.anonymous_ids)]
    assert not mudos, f"{len(mudos)} visitantes sem nenhum evento"

    inativos = [v for v in visitantes if v.perfil_real == "inativo_em_risco"]
    fim_base = max(e["timestamp"] for e in eventos)
    recencias = []
    for v in inativos:
        evs = [e["timestamp"] for e in eventos if e["anonymous_id"] in v.anonymous_ids]
        assert evs, f"inativo {v.usuario_id} sem eventos — o bug da v1 voltou"
        recencias.append((fim_base - max(evs)).days)
    print(f"\nInativos: {len(inativos)} fornecedores, recência de "
          f"{min(recencias)} a {max(recencias)} dias (todos COM atividade real antes de cessar)")

    # Sessionização: nenhum gap dentro de sessão pode passar do timeout.
    por_sessao: dict[str, list[datetime]] = {}
    for e in eventos:
        por_sessao.setdefault(e["session_id"], []).append(e["timestamp"])
    pior_gap = 0
    for ts in por_sessao.values():
        ts.sort()
        for a, b in zip(ts, ts[1:]):
            pior_gap = max(pior_gap, (b - a).total_seconds() / 60)
    assert pior_gap <= TIMEOUT_SESSAO_MIN, f"gap intra-sessão de {pior_gap:.1f} min"
    print(f"Maior intervalo dentro de uma sessão: {pior_gap:.1f} min (limite {TIMEOUT_SESSAO_MIN})")

    # Coerência da jornada: a proposta tem que ser da oportunidade que o
    # fornecedor estava olhando, senão o funil por oportunidade é ficção.
    por_sessao_ev: dict[str, list[dict]] = {}
    for e in eventos:
        por_sessao_ev.setdefault(e["session_id"], []).append(e)
    coerentes = incoerentes = 0
    for lista in por_sessao_ev.values():
        lista.sort(key=lambda x: x["ordem_na_sessao"])
        anterior_op = ""
        for e in lista:
            if e["pagina"] == "envio_proposta":
                if anterior_op and e["oportunidade_id"] == anterior_op:
                    coerentes += 1
                else:
                    incoerentes += 1
            if e["pagina"] in ("detalhe_oportunidade", "detalhe_oportunidade_publica", "tenho_interesse"):
                anterior_op = e["oportunidade_id"]
    total_envios = coerentes + incoerentes
    if total_envios:
        print(f"Propostas cuja oportunidade bate com o detalhe visto antes: "
              f"{coerentes}/{total_envios} ({coerentes/total_envios:.1%})")
        assert coerentes / total_envios > 0.85, "jornada incoerente: proposta em oportunidade não visitada"

    multi_cookie = [v for v in visitantes if len(v.anonymous_ids) > 1]
    print(f"Visitantes que trocaram de cookie: {len(multi_cookie)} "
          f"(viram {sum(len(v.anonymous_ids) for v in multi_cookie)} 'visitantes' distintos sem stitching)")
    print("=" * 66)


# ==================================================================
# 10. CLI
# ==================================================================


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Este script fica em scripts/; os CSVs gerados vão para ../dados, onde
# app.py e tracker_server.py esperam encontrá-los.
DADOS_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "dados"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera a base simulada de acessos ao Portal Petronect.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fornecedores", type=int, default=N_FORNECEDORES_PADRAO)
    ap.add_argument("--anonimos", type=int, default=N_VISITANTES_ANONIMOS_PADRAO)
    ap.add_argument("--oportunidades", type=int, default=N_OPORTUNIDADES_PADRAO)
    ap.add_argument("--dias", type=int, default=DIAS_HISTORICO_PADRAO)
    ap.add_argument(
        "--saida",
        default=os.path.join(DADOS_DIR, "acessos_simulados.csv"),
        help="Caminho do CSV de eventos de saída (padrão: dados/acessos_simulados.csv)",
    )
    args = ap.parse_args()

    os.makedirs(DADOS_DIR, exist_ok=True)

    rng = random.Random(args.seed)

    data_fim = DATA_FIM_PADRAO.date()
    data_inicio = data_fim - timedelta(days=args.dias)

    oportunidades = gerar_oportunidades(args.oportunidades, data_inicio, data_fim, rng)
    visitantes = gerar_visitantes(args.fornecedores, args.anonimos, args.dias, data_inicio, rng)
    eventos = gerar_eventos(visitantes, oportunidades, data_inicio, args.dias, rng)
    atribuir_sessoes(eventos)

    caminho_oportunidades = os.path.join(DADOS_DIR, "oportunidades.csv")
    caminho_fornecedores = os.path.join(DADOS_DIR, "fornecedores.csv")

    salvar_eventos(eventos, args.saida)
    salvar_oportunidades(oportunidades, caminho_oportunidades)
    salvar_fornecedores(visitantes, caminho_fornecedores)

    relatorio(eventos, visitantes, oportunidades)
    print(f"\nArquivos: {args.saida}, {caminho_oportunidades}, {caminho_fornecedores}")


if __name__ == "__main__":
    main()
