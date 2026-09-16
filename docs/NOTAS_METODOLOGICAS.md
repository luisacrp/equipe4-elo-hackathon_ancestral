# Notas metodológicas

Contexto e decisões por trás de cada aba do dashboard (`app.py`). Fica aqui
para não poluir a tela — quem só quer usar o dashboard não precisa disso.

## Tendência de acessos & Páginas mais acessadas

Os dois gráficos incluem os acessos anônimos, que hoje o Google Analytics
não consegue atribuir a ninguém. É o que permite responder "quando e onde"
os fornecedores acessam, não só "quantos cliques" aconteceram.

## Funil & Sessionização

Considera sessões anônimas e identificadas. O funil conta prefixos completos
na ordem temporal dentro da mesma sessão, permitindo páginas intermediárias
e contando cada sessão uma vez por etapa. Empates de horário usam a ordem
do evento na sessão. O denominador percentual é quem alcançou a primeira
etapa. Alcance independente conta visitas sem exigir as etapas anteriores.
Entradas diretas e jornadas já autenticadas podem converter fora deste funil.
O maior gargalo usa o volume absoluto perdido, não uma atribuição causal.

## Visão executiva

Apresenta recomendações por segmento, com evidência agregada, ação sugerida,
equipe responsável e indicador para acompanhamento. A prioridade segue a mesma
regra da fila: bloqueados, inativos, novos, exploradores e esporádicos. Dentro
do segmento, maior recência em dias vem primeiro; empates usam o identificador.
Essa ordem é uma política de negócio, não uma estimativa de impacto ou resposta.

A interface destaca os dois primeiros grupos em cartões e reúne as demais
frentes em uma área expansível. A distribuição por segmento e o funil aparecem
lado a lado. No painel de revisão, o filtro de grupo controla a lista, a seleção
de fornecedor e o CSV exportado. Evidências detalhadas e mensagens ficam sob
demanda. Os gráficos representam contagens observadas, sem alterar a prioridade.

Os candidatos à revisão são os fornecedores identificados com prioridade maior
que zero. Cada fornecedor integra apenas um grupo, conforme a segmentação
existente. A lista não confirma elegibilidade: preferências e histórico devem
ser revisados antes do contato. Engajados permanecem no acompanhamento de
relacionamento. Cadastros sem eventos identificados não recebem recomendação.

Permite revisar a mensagem, selecionar o fornecedor na aba de ação e exportar
os candidatos com suas evidências. Selecionar não registra nem envia comunicação.
Reutiliza o funil para recomendar investigação de Produto no maior gargalo.
Os indicadores de retorno/proposta em 7 dias são sugestões para avaliação futura,
não resultados medidos. A hipótese ajustável de recuperação foi removida.

## Segmentação por regras

O segmento "Novo cadastro" usa a data real de cadastro do fornecedor
(`fornecedores.csv`), não o primeiro acesso dentro da janela observada —
isso evita rotular como "novo" um cliente antigo que só voltou a acessar
recentemente.

## Segmentação por clustering

As features usadas no K-means são recência, total de eventos e propostas
enviadas. "Dias ativos" foi deixado de fora de propósito: tem correlação
de 0,94 com "total de eventos" nesta base, então não acrescenta
informação nova ao agrupamento.

## Validação

O "perfil real" usado na matriz de confusão é o *ground truth* do gerador
de dados simulados — não existiria em produção, mas permite medir a
qualidade da segmentação em vez de apenas declará-la.

## Fila & simulação de grupo de controle

As taxas de resposta da simulação são fictícias, só para demonstrar como
o cálculo funcionaria. Em produção, o fluxo correto é: sortear o grupo no
momento do envio real, registrar a resposta observada (abriu proposta,
fez login, converteu) em vez de sorteá-la, e repetir o cálculo
semanalmente por segmento.

## Histórico de envios

Em produção, este registro alimentaria um CRM ou um disparo real de
e-mail. Aqui ele só demonstra o fechamento do ciclo dado → ação, persistido
em `historico_envios.csv` para sobreviver a um refresh da página.

## Captura ao vivo

`tracker.js` + `portal_demo.html` + `tracker_server.py` provam que a
camada de captura funciona de ponta a ponta, sem depender da base
pré-gerada em CSV — uma versão em miniatura de uma camada que hoje não
existe em produção.
