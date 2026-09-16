# Portal Petronect — Comportamento de Acesso & Reengajamento

Protótipo desenvolvido pela Elo para o desafio **Conexão Ancestral** (Hackathon Petronect × KODIE Academy).

## 🚀 Solução Online (Deploy)

O projeto já se encontra em produção e pode ser acessado através dos links abaixo:

- **Dashboard / Interface (Streamlit):** [Acessar a Aplicação](https://elo-hackathonancestral-petronect.streamlit.app/)
- **Servidor / API (Render):** [Acessar o Ambiente Render](https://equipe4-elo-hackathon-ancestral.onrender.com/)

---

## 🎥 Materiais de Apresentação

- **Pitch / Vídeo de Apresentação:** [🔗 Inserir Link do YouTube aqui]
- **Apresentação de Slides:** [🔗 Inserir Link dos Slides aqui]
- **Arquivos Adicionais:** [🔗 Inserir Link do Google Drive aqui]

## O problema

Atualmente, o Google Analytics indica apenas *quantos* cliques ocorrem no
Portal Petronect — não é possível identificar *quem* acessa, *em que
ponto* interage pela primeira vez, nem *com que frequência* retorna. Essa
limitação compromete decisões de melhoria e mantém a comunicação com o
fornecedor genérica.

## A solução

Protótipo construído a partir de uma base de acessos simulada (não há
integração real com o Portal neste desafio) que cobre o ciclo completo,
da análise à ação:

1. **Modelagem fiel do Portal** — área pública anônima, momento de
   identificação ("Tenho Interesse" → login), área interna e taxa de
   acesso do Sócio Fornecedor, em vez de uma lista de páginas isoladas.
2. **Camada de captura funcional de ponta a ponta**: `tracker.js` +
   `portal_demo.html` + `tracker_server.py` geram e registram eventos
   reais em tempo real, visíveis na aba "Captura ao vivo" do dashboard.
3. **Resposta à pergunta "onde o visitante clica primeiro"**: aba "Funil
   & Sessionização", com página de entrada, funil por etapa e
   identificação do maior ponto de perda.
4. **Segmentação do comportamento por duas abordagens complementares** —
   regras de negócio (interpretáveis) e clustering K-means (orientado a
   dados) —, avaliadas frente ao comportamento real simulado na aba
   "Validação" (matriz de confusão e curva de silhueta).
5. **Conversão em ação**: geração de comunicação de reengajamento
   personalizada (com opção de opt-out e, quando existente, a
   oportunidade real compatível com o interesse do fornecedor),
   priorização de uma fila de próxima melhor ação exportável em CSV, e
   simulação de medição de impacto por grupo de controle.
6. **Conformidade com a LGPD**: base legal, pseudonimização, retenção,
   opt-out e consentimento de cookies — ver [`docs/LGPD.md`](docs/LGPD.md).

## Como executar localmente

A primeira aba, **Visão executiva**, resume a conversão sequencial e permite
explorar um cenário hipotético de recuperação do maior gargalo. O funil distingue
alcance por página de avanço ordenado na mesma sessão e exporta o diagnóstico.
Veja o [roteiro de pitch e próximos passos](docs/MELHORIAS_E_PITCH.md).

> Execute todos os comandos abaixo a partir da **raiz do projeto** (a
> pasta que contém `app/`, `captura/`, `dados/` etc.). Os scripts
> localizam seus próprios arquivos automaticamente (usam o caminho do
> módulo, não o diretório de trabalho atual) e funcionam mesmo quando
> chamados a partir de outro diretório.

### Apenas o dashboard, com a base histórica já gerada

```bash
pip install -r requirements.txt
streamlit run app/app.py
```

### Dashboard com a camada de captura ao vivo (para gravação do vídeo)

O passo a passo completo está descrito em
[`docs/README_CAPTURA.md`](docs/README_CAPTURA.md). Em resumo:

```bash
# Terminal 1 — inicia a página de demonstração do Portal e o endpoint de captura
pip install -r requirements_tracker.txt
python captura/tracker_server.py

# Terminal 2 — inicia o dashboard
pip install -r requirements.txt
streamlit run app/app.py
# Acesse a aba "Captura ao vivo" e clique nos links em http://localhost:5000
```

### Gerar uma nova base simulada (outra semente, mais fornecedores etc.)

```bash
python scripts/gerar_dados_simulados.py --seed 42
```

Esse comando sobrescreve os arquivos CSV em `dados/`.

O dicionário de dados completo está em
[`docs/DICIONARIO_DADOS.md`](docs/DICIONARIO_DADOS.md), a documentação de
privacidade em [`docs/LGPD.md`](docs/LGPD.md) e as decisões metodológicas
por trás de cada aba em
[`docs/NOTAS_METODOLOGICAS.md`](docs/NOTAS_METODOLOGICAS.md).

## Configuração da solução online

O dashboard (Streamlit Community Cloud) e o servidor de captura
(`tracker_server.py`, hospedado separadamente, por exemplo na Render)
precisam estar ambos publicados para que a aba "Captura ao vivo" funcione
sem depender de `localhost`. O passo a passo completo está em
[`docs/README_CAPTURA.md`](docs/README_CAPTURA.md#deploy).

## Estrutura do repositório

Os arquivos estão organizados por categoria; a lógica de execução não é
afetada — cada script localiza suas pastas vizinhas de forma
independente (`app/app.py` lê de `../dados`, `captura/tracker_server.py`
grava em `../dados`, e assim por diante).

```
.
├── app/
│   ├── app.py                    # Dashboard Streamlit (10 abas — ver seção "A solução")
│   ├── analise_jornada.py        # Funil sequencial e diagnóstico de abandono
├── .streamlit/config.toml        # Tema visual customizado (raiz exigida pelo Cloud)
├── captura/                      # Camada de captura ao vivo (ver docs/README_CAPTURA.md)
│   ├── tracker.js                # Snippet de captura (cookie + session_id)
│   ├── tracker_server.py         # Endpoint Flask que grava dados/eventos_live.csv
│   └── portal_demo.html          # Página de demonstração da área pública, usada na gravação
├── dados/
│   ├── acessos_simulados.csv     # Base de eventos simulada já gerada
│   ├── fornecedores.csv          # Cadastro (data_cadastro real, perfil_real, sócio fornecedor)
│   ├── oportunidades.csv         # Catálogo de oportunidades
│   ├── eventos_live.csv          # Gerado em tempo de execução pela camada de captura
│   └── historico_envios.csv      # Gerado em tempo de execução — registro de comunicações (persiste entre atualizações da página)
├── docs/
│   ├── DICIONARIO_DADOS.md       # Dicionário de dados completo
│   ├── LGPD.md                   # Base legal, retenção, opt-out e cookies
│   ├── NOTAS_METODOLOGICAS.md    # Decisões e justificativas de cada aba
│   ├── README_CAPTURA.md         # Roteiro de gravação da demonstração de captura
│   └── diagrama_arquitetura.svg  # Protótipo atual × arquitetura de produção
├── scripts/
│   └── gerar_dados_simulados.py  # Gerador da base de acessos (cadeia de Markov)
├── requirements.txt              # Dependências do dashboard (versões fixadas)
├── requirements_tracker.txt      # Dependência exclusiva da camada de captura (Flask)
└── Procfile                      # Comando de inicialização para deploy do tracker_server (Render/Railway)
```

## Critérios de avaliação — onde cada um é respondido

| Critério | Onde |
|---|---|
| Aderência ao desafio | Abas "Funil & Sessionização" (onde o visitante clica primeiro) e "Captura ao vivo" (como os acessos são identificados) |
| Viabilidade técnica | `docs/diagrama_arquitetura.svg` (protótipo → stack de produção) e rigor da base de dados (`docs/DICIONARIO_DADOS.md`) |
| Qualidade do pitch | Aba "Validação" apresenta os números que sustentam a segmentação em tempo real |

## Equipe

- Luísa Costa Rodrigues Pereira
- Caroline Gabrielly Campos do Nascimento
- Ingrid de Oliveira Braga
- Maria Arielly Lima de Oliveira
- Mariana Alves Santana
