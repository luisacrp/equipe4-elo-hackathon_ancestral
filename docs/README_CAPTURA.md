# Camada de captura demonstrável

Este documento descreve a camada responsável por demonstrar a captura de
eventos de ponta a ponta, respondendo a dois pontos identificados na
revisão do protótipo: a ausência de uma camada de captura funcional e a
necessidade de alinhar a viabilidade técnica à stack avaliada pela banca.
Diferentemente da versão inicial do dashboard, aqui um clique real é
registrado como uma linha real no CSV e refletido em `app.py` em poucos
segundos.

## Arquivos

| Arquivo | Descrição |
|---|---|
| `tracker.js` | Snippet de captura (~50 linhas): grava um cookie first-party (`anonymous_id`, validade de 2 anos) e um `session_id` (janela de 30 minutos), enviando cada pageview ao endpoint de captura. |
| `portal_demo.html` | Página de demonstração da área pública do Portal (home → lista → detalhe → "Tenho interesse" → login), com painel de debug visível. |
| `tracker_server.py` | Endpoint Flask (`POST /api/track`) responsável por registrar cada evento em `eventos_live.csv`, utilizando o mesmo esquema de colunas de `acessos_simulados.csv`. |
| `requirements_tracker.txt` | Dependência única: `flask`. |
| `diagrama_arquitetura.svg` | Diagrama da arquitetura de produção (React → API Gateway → Lambda Node → armazenamento → dashboard), comparado ao protótipo atual, mantendo o mesmo contrato de dados. |
| `app.py` | Dashboard original acrescido da aba **"Captura ao vivo"**, que lê `eventos_live.csv`. |

## Execução local (para gravação do vídeo)

Execute os comandos a partir da raiz do projeto (a pasta que contém
`app/`, `captura/`, `dados/` etc.):

```bash
pip install -r requirements_tracker.txt
python captura/tracker_server.py
```

O comando acima disponibiliza a aplicação em `http://localhost:5000`; o
próprio Flask serve `portal_demo.html` e `tracker.js` (ambos em
`captura/`), sem necessidade de um servidor adicional. Em outro
terminal, inicie o dashboard:

```bash
pip install -r requirements.txt   # requirements.txt original do projeto
streamlit run app/app.py
```

## Roteiro de demonstração em vídeo

1. Abra `http://localhost:5000` em uma aba e execute
   `streamlit run app/app.py` em outra, lado a lado.
2. No dashboard, acesse a aba **"Captura ao vivo"** e mantenha o
   alternador "Atualizar automaticamente" ativado.
3. Na aba do Portal de demonstração, clique na seguinte ordem: **Ver
   oportunidades publicadas → ver detalhes de uma oportunidade → Tenho
   interesse → Iniciar identificação/Login**.
4. Cada clique é refletido no dashboard em aproximadamente 2 segundos. No
   quarto clique, destaque a contagem "Sessões com identidade vinculada"
   subindo de 0 para 1 — o momento em que o visitante anônimo se torna um
   fornecedor identificado, em tempo real.
5. Encerre com `diagrama_arquitetura.svg`, explicando em uma frase que a
   versão atual utiliza Flask e CSV, enquanto a versão de produção
   utilizaria API Gateway, Lambda Node e DynamoDB, mantendo o mesmo
   contrato de dados e alterando apenas a camada de transporte.

Esse roteiro ocupa os cerca de 4 minutos de demonstração ao vivo
sugeridos, antes da apresentação da segmentação (RFM / clustering) já
existente no dashboard.

## Consistência de esquema com `acessos_simulados.csv`

Os nomes das colunas em `eventos_live.csv` são idênticos aos de
`acessos_simulados.csv` para que a mesma função de leitura
(`carregar_dados`, em `app.py`) sirva, com ajustes mínimos, para ambas as
fontes. Essa escolha sustenta a premissa de que o contrato de dados não
muda entre protótipo e produção.

## Deploy

A avaliação considera apenas o que está publicado; portanto, o dashboard
e o servidor de captura precisam estar hospedados em dois serviços
online gratuitos, em vez de dois processos em `localhost`. Como cada
serviço passa a rodar em um host diferente, não há mais disco
compartilhado entre eles — por esse motivo, o dashboard consulta os
eventos pela API do servidor de captura (`GET /api/events`) em vez de
ler `eventos_live.csv` diretamente do disco. Essa alternância já está
implementada no código; resta apenas publicar os dois serviços.

### 1. Publicar `tracker_server.py` na Render (camada gratuita)

1. Publique este projeto em um repositório no GitHub.
2. Em [render.com](https://render.com), crie um **New → Web Service**
   apontando para esse repositório.
3. Configure:
   - **Root Directory**: em branco (raiz do repositório).
   - **Build Command**: `pip install -r requirements_tracker.txt`
   - **Start Command**: `python captura/tracker_server.py`
4. Conclua o deploy. Ao final, a Render disponibiliza uma URL pública, no
   formato `https://conexao-ancestral-tracker.onrender.com`.
5. Valide o deploy acessando essa URL no navegador — a página
   `portal_demo.html` deve ser exibida.

> O plano gratuito da Render entra em modo de espera após um período sem
> acesso; o primeiro clique após esse intervalo pode levar cerca de 30
> segundos para reativar o serviço. Recomenda-se acessar a URL alguns
> minutos antes da gravação ou da apresentação.

### 2. Publicar `app.py` no Streamlit Community Cloud

1. No mesmo repositório, acesse
   [share.streamlit.io](https://share.streamlit.io) e crie um novo
   aplicativo apontando para `app/app.py`.
2. Em **Advanced settings**, selecione **Python 3.13** (versão validada
   localmente). Em **Secrets**, adicione:
   ```toml
   TRACKER_URL = "https://conexao-ancestral-tracker.onrender.com"
   ```
   (substitua pela URL real obtida na etapa anterior, sem barra ao
   final).
3. Conclua o deploy. Ao abrir a aba "Captura ao vivo", o dashboard consulta
   eventos dessa URL, sem necessidade de configuração manual adicional.

Inclua no commit `app/analise_jornada.py`, os três CSVs de `dados/`,
`requirements.txt` e `.streamlit/config.toml` na raiz. O histórico de envios
é salvo em arquivo local e pode se perder quando a instância for recriada.

### 3. Validação do fluxo completo já publicado

1. Abra a URL da Render (`portal_demo.html`) em uma aba.
2. Abra a URL do Streamlit Cloud em outra e acesse a aba **"Captura ao
   vivo"**.
3. Clique na seguinte ordem no Portal de demonstração: **Ver
   oportunidades publicadas → ver detalhes → Tenho interesse → Iniciar
   identificação/Login**.
4. Em poucos segundos, os eventos aparecem no dashboard, sem depender de
   `localhost` ou de execução local.

Para uma validação rápida sem alterar os Secrets, o campo "URL do
servidor de captura" na própria aba "Captura ao vivo" aceita a URL da
Render inserida manualmente — útil para testes antes da configuração
definitiva do Secret.

### Execução 100% local (sem deploy)

O fluxo local continua funcionando conforme descrito anteriormente: sem
a variável `TRACKER_URL` configurada, o dashboard volta a ler
`eventos_live.csv` diretamente do disco.

## Limitações declaradas

* `tracker_server.py` é um servidor de desenvolvimento (Flask embutido),
  não uma API de produção — por esse motivo, o diagrama de arquitetura
  prevê sua substituição por API Gateway e Lambda.
* O cookie é first-party e single-domain; a correlação entre dispositivos
  (o mesmo fornecedor acessando de dois aparelhos) não é tratada nesta
  camada — esse cenário é resolvido no gerador de dados históricos, por
  meio de `anonymous_ids_conhecidos`.
* `eventos_live.csv` cresce indefinidamente enquanto o servidor está em
  execução; em produção, esse papel seria desempenhado por DynamoDB/S3,
  com TTL e particionamento.
