# LGPD & Privacidade

Este documento não substitui uma análise jurídica formal. É o ponto de
partida sobre como o protótipo trata dados pessoais, para orientar uma
eventual implementação em produção.

## Base legal

O tratamento apoia-se em legítimo interesse do controlador (melhorar a
comunicação com fornecedores já cadastrados) e em execução do
relacionamento comercial B2B existente. O contato (nome, e-mail) é uma
pessoa física dentro da pessoa jurídica — é dado pessoal mesmo em contexto
B2B, e precisa ser tratado como tal.

## Minimização e pseudonimização

O CNPJ nunca trafega em claro: é armazenado como hash truncado
(`cnpj_hash`, ver `DICIONARIO_DADOS.md`). Este protótipo não coleta nome
de pessoa física, apenas razão social — em produção, o e-mail e o
telefone do contato também deveriam ser pseudonimizados em qualquer base
analítica que não seja o CRM principal.

## Retenção

Proposta: eventos brutos de navegação por até 18 meses; métricas
agregadas (contagens por segmento, funil) podem ser mantidas por mais
tempo, já que não identificam ninguém. Revisão do prazo a cada 12 meses.

## Direitos do titular e opt-out

Toda mensagem de reengajamento gerada pelo dashboard termina com uma
linha de opt-out. Em produção, o opt-out precisa gravar um estado real e
suprimir a pessoa de disparos futuros — hoje é só texto na mensagem. O
canal "Apoio ao usuário", que já existe no Portal, é o ponto natural para
pedidos de acesso, correção ou eliminação de dados.

## Consentimento de cookies

O protótipo grava um cookie de identificação (`_pn_aid`, ver
`tracker.js`) na primeira visita, antes de qualquer interação. Em
produção, isso precisa vir depois de um banner de consentimento na área
pública, com opção de recusar cookies não essenciais sem bloquear a
navegação — a consulta a oportunidades continua sendo "somente consulta,
sem login".
