# Plano de execução da revisão do artigo

## Objetivo e situação inicial

Preparar uma versão cientificamente consistente, reproduzível e adequada a uma nova submissão. O plano não pressupõe aceitação nem convite para revisão pela RAIRO: a carta de 14/01/2025 registra rejeição antes de avaliação aprofundada.

Fontes principais: `name.tex` (decisão e comentários relativos ao artigo de UTI) e `main.tex` (manuscrito atual). O arquivo `arquivos/comentarios do revisor.pdf` trata de outro artigo e não deve orientar esta revisão.

Status: auditoria inicial concluída, com diagnóstico e matriz em `auditoria/`. O usuário confirmou que não dispõe de outro repositório e autorizou implementar o necessário. Foi implementada uma base estática sintética independente em `../../experiments/`, com testes e piloto executados. Isso não reproduz os resultados históricos, não valida o protocolo clínico e não conclui a revisão científica. Detalhes em `ANDAMENTO.md`.

## Etapa 1 — Auditoria e rastreabilidade

- [x] Preservar a versão recebida e registrar a versão do código utilizada na auditoria.
- [x] Criar uma matriz com cada comentário: problema, evidência, ação, arquivo afetado e critério de atendimento.
- [x] Mapear `monte-carlo-simulation.py` e `app-uti-sim/core/` às equações, políticas, tabelas e figuras do artigo.
- [x] Identificar qual implementação produziu os resultados publicados no manuscrito; se não estiver disponível, registrar a lacuna.
- [x] Conferir nomes das políticas, solver, penalização, parâmetros, métricas e origem das figuras. O código atual pode diferir da versão experimental do artigo.
- Reprodução histórica: indisponível por ausência dos insumos; não foi marcada como realizada. A execução sintética nova é registrada separadamente.

**Entregáveis:** matriz de atendimento ao parecer e relatório de divergências entre texto, código e resultados.

**Critério de conclusão:** cada resultado tem origem identificada ou uma lacuna explicitamente documentada; cada comentário tem uma ação associada.

## Etapa 2 — Definir escopo e contribuição

Depende da etapa 1.

- [ ] Atualizar a revisão da literatura e construir uma comparação com os trabalhos mais próximos: decisões, tipos de leitos, ocupação, dinâmica temporal, dados e validação.
- [ ] Separar contribuição metodológica de contribuição aplicada.
- [ ] Formular a pergunta de pesquisa e hipóteses verificáveis antes dos novos experimentos.
- [ ] Escolher um dos caminhos abaixo conforme dados, implementação e contribuição possível.

**Caminho A — Estático:** rodadas independentes, alocação de um conjunto conhecido de pacientes e capacidades fixas. Retirar alegações de dinâmica efetivamente simulada. Avaliar se a contribuição resultante é suficiente para o periódico pretendido.

**Caminho B — Dinâmico, recomendado para avaliação:** decisões sucessivas com chegadas, permanência, liberação de leitos e fila. Avaliar metas de ocupação por tipo e comparar políticas nas mesmas condições temporais. Adotar esse caminho apenas se houver dados ou hipóteses defensáveis e capacidade de validação.

**Entregável:** especificação do estudo com pergunta de pesquisa, contribuição pretendida, escopo e limitações.

**Critério de conclusão:** o estudo proposto é executável com os insumos disponíveis e suas alegações podem ser verificadas experimentalmente. Não afirmar novidade sem a comparação bibliográfica.

## Etapa 3 — Corrigir e validar o modelo

Depende da etapa 2.

- [ ] Unificar conjuntos, índices, tipos de leitos e notação de capacidade total e disponível.
- [ ] Definir compatibilidade paciente–leito e domínio das variáveis.
- [ ] Explicitar o ganho incremental de sobrevivência na MGS e distingui-lo da sobrevivência penalizada por ocupação.
- [ ] Redefinir a MSF de acordo com o critério clínico escolhido; verificar o sinal da penalização na minimização e a possibilidade de soluções sem admissões.
- [ ] Definir quantidade de admissões, prioridades e desempates nas quatro políticas.
- [ ] Especificar como a FCFS trata incompatibilidade, indisponibilidade e espera.
- [ ] Definir se a ocupação inclui pacientes já internados e distinguir ocupação observada de meta.
- [ ] Justificar escala e interpretação de M, unidade da ocupação e forma da penalização. Não tratar M apenas como uma constante arbitrariamente grande.
- [ ] Examinar metas globais versus metas por tipo, penalização linear versus quadrática e o efeito de reservar capacidade.
- [ ] Classificar corretamente a formulação final e documentar eventual linearização.
- [ ] Validar em exemplos pequenos, incluindo falta de demanda, excesso de demanda, ausência de leitos compatíveis, empate e ganho de sobrevivência nulo.

**Entregáveis:** formulação corrigida, implementação correspondente e testes pequenos com solução verificável por enumeração ou cálculo independente.

**Critério de conclusão:** texto e código representam o mesmo problema; as soluções respeitam compatibilidade e capacidade; os exemplos demonstram o comportamento pretendido de cada política.

## Etapa 4 — Documentar dados e geração de pacientes

Pode avançar em paralelo às etapas 2 e 3, sem fixar pressupostos incompatíveis com o escopo escolhido.

- [ ] Identificar período, tamanho da amostra, variáveis, dados faltantes e tratamento dos dados do HU-UFMA.
- [ ] Separar dados observados, parâmetros estimados, valores da literatura e hipóteses sintéticas.
- [ ] Documentar distribuições de idade, gravidade, SOFA e suas dependências relevantes.
- [ ] Especificar integralmente o protocolo que produz P_in e P_out, incluindo fonte, calibração e limitações.
- [ ] Verificar a aplicabilidade clínica do protocolo a adultos, crianças e neonatos; ajustar ou limitar o escopo se necessário.
- [ ] Definir capacidades, níveis de demanda, intervalos de geração e valores de todos os parâmetros.
- [ ] Verificar o tratamento de casos em que P_in < P_out, pois a regra de simulação de desfechos descrita pressupõe a ordenação oposta.
- [ ] Documentar disponibilidade dos dados e exigências institucionais aplicáveis; preparar instâncias sintéticas compartilháveis quando os dados reais não puderem ser publicados.

**Entregáveis:** dicionário de dados, tabela de parâmetros e especificação reproduzível do gerador.

**Critério de conclusão:** um pesquisador consegue reconstruir os cenários sem depender de informações implícitas ou de funções não descritas.

## Etapa 5 — Implementar o protocolo experimental

Depende das etapas 3 e 4.

- [ ] Separar geração de cenários, políticas, simulação, métricas e apresentação.
- [ ] Usar as mesmas instâncias e realizações aleatórias pertinentes para comparar políticas de forma pareada.
- [ ] Registrar sementes, versões, configuração do solver, status de solução, limites de tempo e gaps quando aplicáveis.
- [ ] Definir o desfecho principal e métricas secundárias antes de analisar os resultados.
- [ ] Distinguir sobrevivência esperada, sobrevivência realizada, sobrevivência entre admitidos e sobrevivência de toda a população elegível.
- [ ] Registrar admissões, recusas e ocupação por tipo; no caminho dinâmico, acrescentar espera e evolução temporal.
- [ ] Documentar denominadores, horizonte, número de replicações e método de cálculo da incerteza.

**Se o caminho dinâmico for escolhido:**

- [ ] Implementar relógio de simulação, chegadas, permanência, altas, óbitos e fila.
- [ ] Definir ordem dos eventos e frequência das decisões.
- [ ] Preservar internações em curso, salvo se outra regra for explicitamente modelada e justificada.
- [ ] Definir o destino de pacientes não admitidos e o encerramento do horizonte para evitar viés por desfechos ainda não observados.
- [ ] Garantir que todas as políticas recebam a mesma informação disponível no momento da decisão.

**Entregáveis:** experimento executável por configuração, instruções de reprodução e resultados brutos rastreáveis.

**Critério de conclusão:** reexecutar uma configuração com a mesma semente reproduz o resultado, e as políticas são comparadas sob condições equivalentes.

## Etapa 6 — Executar experimentos e avaliar a contribuição

Depende da etapa 5.

- [ ] Executar um piloto para detectar inconsistências e dimensionar replicações pela precisão desejada.
- [ ] Comparar MGS, LSF, MSF e FCFS sob as definições validadas.
- [ ] Isolar o efeito dos componentes: sem penalização, meta global e metas por tipo, quando fizerem parte do escopo.
- [ ] Analisar sensibilidade a M, metas, demanda, capacidades e probabilidades de sobrevivência; incluir parâmetros temporais no caminho dinâmico.
- [ ] Estimar diferenças pareadas, intervalos de confiança e relevância prática, sem concluir superioridade apenas por pequenas diferenças de médias.
- [ ] Verificar robustez por tipo de leito e cenários desfavoráveis, além do resultado agregado.
- [ ] Explicar os mecanismos dos resultados e registrar achados que contrariem as hipóteses.

**Entregáveis:** base de resultados, tabelas e figuras geradas automaticamente e síntese dos achados sustentados pelos dados.

**Critério de conclusão:** nenhuma tabela ou figura contradiz outra por erro de métrica ou origem; a contribuição e seus limites são demonstrados, não apenas afirmados.

## Etapa 7 — Reescrever o manuscrito

Métodos podem ser redigidos após a etapa 5; resultados e conclusões dependem da etapa 6.

- [ ] Revisar título e resumo; usar “target occupancy rate” se a meta não for otimizada pelo estudo.
- [ ] Apresentar lacuna da literatura e contribuição de forma específica.
- [ ] Reescrever modelagem, dados e algoritmos com entradas, saídas e parâmetros completos.
- [ ] Explicar os resultados com métricas consistentes e discutir limitações clínicas e operacionais.
- [ ] Retirar alegações de equidade, superioridade clínica ou aplicabilidade dinâmica que não foram avaliadas.
- [ ] Atualizar referências, eliminar duplicatas e corrigir capitalização e metadados.
- [ ] Revisar inglês, siglas, legendas, referências cruzadas e resíduos do template.
- [ ] Compilar e inspecionar o PDF final, incluindo equações, tabelas, algoritmos e figuras.

**Entregáveis:** LaTeX revisado, bibliografia e PDF compilado.

**Critério de conclusão:** resumo, resultados e conclusão concordam; cada alegação principal tem suporte; o documento não apresenta referências ou elementos editoriais pendentes.

## Etapa 8 — Preparar nova submissão

Depende da etapa 7.

- [ ] Escolher o periódico conforme a contribuição efetivamente obtida e suas regras atuais.
- [ ] Não pressupor que uma nova submissão à RAIRO seja uma revisão convidada; verificar a política aplicável antes de optar por esse destino.
- [ ] Preparar carta de apresentação e documento interno de resposta ponto a ponto aos comentários anteriores; enviar resposta formal somente quando apropriado ao processo editorial.
- [ ] Preparar materiais suplementares e instruções para reproduzir os resultados publicados.
- [ ] Conferir autoria, afiliações, declarações, disponibilidade de dados e código e demais itens exigidos pelo periódico.
- [ ] Fazer uma conferência final da matriz do parecer, explicitando itens não atendidos e sua justificativa.

**Entregável:** pacote pronto para avaliação dos autores e posterior submissão.

**Critério de conclusão:** todos os comentários têm resposta verificável e o pacote está adequado ao periódico escolhido. O envio ao periódico é uma ação posterior, não incluída na preparação deste plano.

## Insumos a confirmar durante a execução

1. Qual código e quais dados produziram a versão submetida em 2025?
2. Existem dados de chegada, permanência e liberação de leitos para sustentar um estudo dinâmico?
3. Qual é a implementação completa do protocolo de sobrevivência e quais populações ele cobre?
4. Quais dados e artefatos podem ser compartilhados para reprodução?
5. O destino desejado continua sendo a RAIRO ou será escolhido conforme a contribuição obtida?

A auditoria e a matriz do parecer podem começar sem essas respostas. Estimativas de prazo devem ser feitas após a auditoria e a escolha do escopo, pois o caminho dinâmico pode exigir coleta ou calibração adicional.

## Primeira entrega de execução

Concluir a etapa 1: matriz de atendimento ao parecer e diagnóstico do código existente. Essa entrega determina quais mudanças são correções de texto, quais são correções da implementação e quais exigem novos dados ou experimentos.
