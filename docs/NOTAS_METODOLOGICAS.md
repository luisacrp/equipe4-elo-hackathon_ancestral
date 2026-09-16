# Notas metodológicas

Contexto e decisões por trás de cada aba do dashboard (`app.py`). Fica aqui
para não poluir a tela — quem só quer usar o dashboard não precisa disso.

## Tendência de acessos & Páginas mais acessadas

Os dois gráficos incluem os acessos anônimos, que hoje o Google Analytics
não consegue atribuir a ninguém. É o que permite responder "quando e onde"
os fornecedores acessam, não só "quantos cliques" aconteceram.

## Funil & Sessionização

Calculado sobre todas as sessões — anônimas e identificadas — porque a
pergunta "onde o visitante clica primeiro" não pode ser respondida olhando
só quem já fez login.

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
