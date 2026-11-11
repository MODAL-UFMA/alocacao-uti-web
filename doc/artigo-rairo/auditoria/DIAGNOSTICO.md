# Diagnóstico da auditoria inicial

## Resultado

O repositório disponível não é suficiente para reproduzir os experimentos descritos no manuscrito. A aplicação atual pode ser aproveitada como protótipo, mas não constitui evidência de reprodução da tabela e das figuras do artigo. Antes de interpretar os resultados existentes como validação do modelo, é necessário recuperar os insumos originais ou construir e declarar um novo protocolo experimental.

Base auditada: commit `ec4da9ca9a581cf04424bab547bcb1690a951622`. O histórico local contém um commit, datado de 07/11/2025, posterior à decisão de 14/01/2025 em `name.tex`. Isso não prova quando o código foi escrito, mas não há histórico local que vincule uma implementação à submissão. Arquivos e hashes estão em `manifesto_base.json`; o manuscrito e o código da aplicação foram mantidos sem alterações.

## Achados prioritários

### A1 — Escores ordinais são usados como se fossem probabilidades

**Confirmado no código.** `app-uti-sim/core/patients.py:15` atribui valores de 1 a 5 a `prob_uti` e de 1 a 4 a `prob_fora`. O cadastro com todos os componentes SOFA iguais a zero produz 5 e 4. Esses valores entram diretamente nos objetivos em `allocation.py:54` e nas métricas em `metrics.py:32`.

Consequência: a soma não pode ser interpretada como número esperado de sobreviventes. O algoritmo de desfechos do artigo, com um uniforme em (0,1], tampouco pode receber esses valores diretamente. A interface apresenta categorias qualitativas, mas não há uma conversão calibrada para probabilidades no código disponível. Dividir os valores por 5 não resolve a falta de calibração clínica e não deve ser feito como correção automática.

**Ação:** recuperar o protocolo original e sua conversão para probabilidades, ou reformular explicitamente o objetivo como utilidade baseada em escores, com interpretação e validação próprias.

### A2 — MSF e FCFS não estão implementadas no código disponível

**Confirmado por inventário.** `allocation.py` implementa apenas MSG (nome usado no código para MGS) e LSF; a interface oferece somente essas duas políticas. `monte-carlo-simulation.py` tem zero bytes. Não foram encontrados gerador de cenários, execução das 1.000 rodadas, sementes, dados HU-UFMA ou saídas brutas no checkout atual.

**Ação:** localizar a implementação original. Na ausência dela, implementar um novo experimento e identificá-lo como tal, sem alegar reprodução histórica.

### A3 — O modelo implementado difere do descrito

- `main.tex:209`, `221` e `240`: penalização quadrática. `allocation.py:46`: desvio absoluto com variáveis auxiliares. É outra função de penalização, não uma reformulação equivalente do quadrado.
- `main.tex:364`: Gurobi. `allocation.py:78`: CBC via PuLP.
- `main.tex:260`: compatibilidade exclusiva por grupo etário. `allocation.py:7`: crianças também podem ocupar leitos adultos.
- Artigo: M não quantificado e OR apenas com intervalo genérico. Aplicação: M padrão 1000, meta padrão 80% e capacidades padrão 5/10/15. Esses valores da interface não comprovam os parâmetros dos experimentos publicados.
- `app.py:66` chama o parâmetro de taxa mínima; o código penaliza desvios para os dois lados de uma meta, sem impor uma ocupação mínima.

**Ação:** escolher e justificar uma especificação científica única; registrar separadamente a aplicação atual e a futura implementação experimental.

### A4 — A fórmula MSF escrita permite comportamento contrário à intenção

**Confirmado na formulação do manuscrito, não em uma implementação MSF.** Em `main.tex:240`, minimiza-se a soma de P_in dos admitidos menos M vezes o desvio quadrático de ocupação. Não há obrigação de admitir pacientes.

Contraexemplo: um paciente compatível, um leito, P_in=0,9, M=1 e OR=0,8. Não admitir produz objetivo -0,64; admitir produz 0,86. A minimização prefere não admitir.

Mais geralmente, com probabilidades não negativas, M positivo, ocupação entre 0 e 1 e OR ≥ 0,5, a solução vazia é uma solução ótima dessa fórmula: o desvio quadrático é no máximo OR², e o termo de sobrevivência é não negativo. Isso é uma propriedade matemática da equação, não uma conclusão sobre os resultados históricos, cuja implementação não foi localizada.

**Ação:** definir prioridade MSF e quantidade de admissões; corrigir e validar o modelo antes de novos experimentos. Não basta trocar um sinal sem definir o comportamento desejado.

### A5 — Não há dinâmica temporal demonstrada

`main.tex:276` afirma que a simulação contempla dinâmica, enquanto os algoritmos não especificam estado temporal, chegadas, permanência e altas. `main.tex:475` trata tempo de permanência como trabalho futuro. A aplicação cadastra pacientes manualmente e resolve uma alocação estática; não simula a operação de uma UTI ao longo do tempo.

**Ação:** adotar um estudo estático com limites claros ou construir um simulador temporal validado. Não considerar a adição de parágrafos descritivos como atendimento ao parecer.

### A6 — Resultados do artigo não têm rastreabilidade suficiente

A tabela em `main.tex:414` contém valores fixos; as figuras são `d1.jpeg`, `d2.jpeg` e `d3.jpeg`. Não há código nem resultados brutos que permitam regenerá-las. O texto da tabela menciona sobreviventes por rodada; as legendas das figuras usam sobrevivência por total de admitidos. A aparente divergência entre conclusões pode decorrer de denominadores diferentes, erro de cálculo ou origem diferente; não foi possível decidir entre essas hipóteses.

**Ação:** definir os indicadores, recuperar saídas por cenário/política e reconstruir tabelas e gráficos a partir da mesma base. Não escolher a conclusão apenas pelo resultado mais favorável.

### A7 — Problemas adicionais de implementação

- `app.py:280` não inclui a coluna `Gravidade` no dicionário de resultados, mas `visuals.py:30` e `app.py:317` a acessam. O caminho LSF contém uma falha identificável por inspeção; a interface completa não foi executada nesta auditoria.
- `visuals.py:34` espera status com símbolos e lista de espera, diferentes dos textos produzidos pela aplicação.
- `app.py:204` descreve LSF como prioridade pela menor diferença entre probabilidades, mas `allocation.py:61` maximiza P_in com penalização.
- `metrics.py:32` calcula uma soma sem penalização, embora a função se chame `compute_objective`; ela não é o objetivo completo do solver, nem representa o objetivo LSF.
- `allocation.py:78` extrai variáveis sem verificar o status da solução. Isso impede distinguir adequadamente solução ótima de falha ou interrupção.
- O índice denominado equidade usa a variância dos ganhos dos admitidos; não há justificativa no material examinado de que ele mede equidade clínica ou distributiva.

**Ação:** tratar essas correções na implementação após fixar a especificação. A interface não deve ser usada como validação dos experimentos históricos.

## Organização das fontes

`name.tex` é texto de uma carta editorial, não um arquivo LaTeX do artigo. Os cinco arquivos de `backups/` têm título de um artigo sobre Prize-Collecting Travelling Salesman Problem. O PDF de comentários também é desse outro tema, conforme a leitura anterior. Esses materiais foram preservados, mas não servem como versões anteriores ou pareceres do estudo de UTI.

## Verificação realizada e limites

Executado `python3 doc/artigo-rairo/auditoria/verificar_achados.py`. O script registra cinco evidências em `verificacoes.json`: escores fora do intervalo probabilístico, compatibilidade criança–adulto, contraexemplo independente da fórmula MSF, ausência da coluna Gravidade e arquivo Monte Carlo vazio.

O script usa a biblioteca padrão e extrai funções específicas por AST com estado de cadastro simulado. Não executa Streamlit, CBC ou Gurobi e não reproduz resultados do estudo. NumPy, pandas, PuLP e Streamlit não estavam instalados no Python inspecionado. Instalar essas dependências não supriria o simulador e os dados ausentes; por isso não foi apresentado um teste da aplicação como se fosse reprodução científica.

## Próxima decisão

**Atualização após a auditoria:** o usuário confirmou que este é todo o repositório disponível e autorizou adaptar ou implementar. Foi criada uma implementação estática nova em `experiments/`, e o arquivo Monte Carlo antes vazio passou a ser seu ponto de entrada. Os achados acima descrevem a base original registrada no manifesto; não devem ser confundidos com o estado da nova implementação. A aplicação Streamlit e o manuscrito permanecem como recebidos. Ver `../ANDAMENTO.md`.

A etapa de inventário e diagnóstico está concluída com lacunas explícitas. A reprodução histórica permanece indisponível. É possível avançar na especificação matemática e nos exemplos sintéticos; a escolha de um estudo dinâmico e a alegação de validação com dados reais dependem dos insumos correspondentes.

Prioridade imediata: localizar o código original e o protocolo probabilístico; em paralelo, preparar uma especificação estática consistente que sirva de base testável para eventual extensão dinâmica. Esta recomendação não fixa o escopo final nem valida clinicamente os escores existentes.
