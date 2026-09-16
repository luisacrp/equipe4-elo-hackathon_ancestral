# Dicionário de dados — base simulada do Portal Petronect

Base gerada por `gerar_dados_simulados.py`. Não há integração real com o
Portal: os dados reproduzem o **modelo de funcionamento** do Portal (área
pública anônima, momento de identificação, área interna, taxa de acesso)
para que o protótipo possa ser demonstrado ponta a ponta.

Reprodutível: `python gerar_dados_simulados.py --seed 42`

---

## `acessos_simulados.csv` — eventos

Grão: **1 linha por página vista** (pageview).

| Coluna | Tipo | Descrição |
|---|---|---|
| `event_id` | texto | Identificador único do evento (`EV0000001`). |
| `timestamp` | datetime | Momento da visualização. |
| `session_id` | texto | Sessão derivada pela regra de 30 min de inatividade sobre o `anonymous_id`. |
| `ordem_na_sessao` | inteiro | Posição da página dentro da sessão (1 = primeira). |
| `pagina_entrada` | 0/1 | 1 na primeira página da sessão — responde ao "onde clica primeiro". |
| `anonymous_id` | texto | Identificador de dispositivo/cookie primário. **Existe sempre**, inclusive na área pública. |
| `usuario_id` | texto | Usuário do Portal. **Vazio enquanto a sessão não é identificada.** |
| `identificado` | 0/1 | Se naquele evento a identidade já era conhecida. |
| `empresa` | texto | Razão social. Vazio enquanto anônimo. |
| `cnpj_hash` | texto | CNPJ pseudonimizado (SHA-256 truncado). O CNPJ em claro nunca trafega. |
| `perfil_real` | texto | **Ground truth** do comportamento simulado. Serve para validar a segmentação (matriz de confusão). Não existiria em produção. |
| `area` | `publica` / `interna` | Área do Portal. A pública é anônima por natureza. |
| `pagina` | texto | Página vista (ver estados abaixo). |
| `oportunidade_id` | texto | Oportunidade em foco, quando aplicável. |
| `categoria` | texto | Categoria/família de material da oportunidade. |
| `modalidade` | texto | `pregao_eletronico`, `concorrencia` ou `dispensa_eletronica`. |
| `enviou_proposta` | 0/1 | 1 apenas quando o envio foi concluído. Visitar `envio_proposta` não é converter. |
| `utm_source` / `utm_medium` / `utm_campaign` | texto | Origem da sessão. Links de campanha de e-mail carregam identificação. |
| `device` | texto | `desktop`, `mobile`, `tablet`. |
| `uf`, `porte_empresa` | texto | Atributos firmográficos. Vazios para visitante anônimo. |

### Estados de navegação (páginas)

**Área pública (sem login):** `home_publica`, `busca_publica`,
`lista_oportunidades_publicas`, `detalhe_oportunidade_publica`,
`tenho_interesse`, `login`, `iniciar_identificacao`, `quer_se_cadastrar`,
`modelo_cobranca_socio`, `ajuda_treinamentos`, `avisos`.

**Área interna (com login):** `painel_oportunidades`, `detalhe_oportunidade`,
`taxa_acesso_bloqueio`, `envio_proposta`, `minhas_participacoes`,
`sala_colaboracao`, `cadastro_fornecedor`, `assinatura_eletronica`,
`meus_dados`.

O caminho `detalhe_oportunidade_publica → tenho_interesse → login |
iniciar_identificacao` é o **momento de stitching**: onde um visitante
anônimo vira um fornecedor conhecido.

---

## `oportunidades.csv` — catálogo

| Coluna | Descrição |
|---|---|
| `oportunidade_id` | `OP-2026-0001`. |
| `categoria` | Família de material/serviço. |
| `modalidade` | Pregão, concorrência ou dispensa. |
| `exige_socio_fornecedor` | 1 quando a participação exige a taxa de acesso; dispensas são isentas. |
| `data_publicacao`, `data_fim` | Janela em que a oportunidade aparece nas listas. |

## `fornecedores.csv` — cadastro

| Coluna | Descrição |
|---|---|
| `usuario_id`, `empresa`, `cnpj_hash` | Identificação do fornecedor. |
| `perfil_real` | Ground truth do perfil. |
| `data_cadastro` | **Data real de cadastro**, anterior à janela observada para quem já era cliente. Evita rotular como "novo cadastro" quem apenas teve o primeiro acesso dentro da janela. |
| `socio_fornecedor` | 1 se pagou a taxa de acesso. |
| `categorias_interesse` | Categorias separadas por `\|`. |
| `uf`, `porte_empresa` | Firmografia. |
| `anonymous_ids_conhecidos` | Todos os cookies já vinculados a este usuário (resultado do stitching). Mais de um = o visitante trocou de dispositivo ou perdeu o cookie. |

---

## Decisões de modelagem que valem no pitch

1. **Metade dos eventos não tem `usuario_id`.** Não é falha da base: é o
   tamanho do ponto cego atual. O GA contabiliza esses cliques sem saber de
   quem são.
2. **A navegação vem de uma cadeia de Markov**, não de páginas sorteadas de
   forma independente. Por isso existe funil, página de entrada e abandono.
3. **A oportunidade é coerente ao longo da jornada**: a proposta enviada é
   sempre da oportunidade que o fornecedor estava analisando (validado em
   100% dos envios).
4. **O bloqueio da taxa de acesso é um estado do dado.** Quem manifesta
   interesse, faz login e bate no cadeado é o lead de reengajamento mais
   valioso da base.
5. **Perfis são alocados por cota**, não sorteados: a composição da base é a
   mesma em qualquer seed.
6. **`perfil_real` vai no CSV** para permitir medir a segmentação em vez de
   apenas afirmá-la.

## Limitações declaradas

* Dados sintéticos. Volumes e taxas são plausíveis, não reais.
* Uma sessão pertence a um único `anonymous_id`: troca de dispositivo no meio
  da sessão não é modelada.
* Não há consulta a resultados de licitação, leilão eletrônico nem minutas
  contratuais — o escopo cobre a jornada de descoberta até a proposta.
