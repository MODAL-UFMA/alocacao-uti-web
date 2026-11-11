# Matriz de atendimento ao parecer

Fonte: `../name.tex`, decisão de 14/01/2025. Identificadores E, R e O correspondem à decisão editorial, comentários principais e observações adicionais. A coluna “Situação” avalia a versão recebida, não representa correções já executadas. Evidências adicionais estão em `DIAGNOSTICO.md`.

| ID | Solicitação/problema | Evidência e situação atual | Ação e entregável | Critério de atendimento |
|---|---|---|---|---|
| E1 | Contribuição científica insuficiente | Carta, linhas 15–17; contribuição pretendida centrada em tipos e ocupação | Etapa 2: revisão atualizada, lacuna, pergunta e hipóteses | Diferenciar dos trabalhos próximos e demonstrar benefício dos componentes propostos |
| R1 | Momento das decisões e ligação com a prática | `main.tex:276`; descrição dinâmica sem algoritmo temporal; pendente | Etapas 2/5: escopo estático explícito ou simulador de eventos | Especificar chegadas, decisões, fila e liberação; todas as políticas sob a mesma informação |
| R2a | Cálculo das probabilidades e pressupostos clínicos | `main.tex:302`; função apply_protocol não definida; escores 1–5 na aplicação | Etapa 4: protocolo completo e origem dos parâmetros | Produzir P_in/P_out interpretáveis e reproduzíveis, com limites clínicos documentados |
| R2b | Índices e conjuntos inconsistentes | `main.tex:209` e `260`; somas 1..J e tipos 0/1/2 | Etapa 3: notação e compatibilidade únicas | Todas as variáveis/restrições usam os mesmos conjuntos e correspondem ao código |
| R2c | Distribuições e características da população | Algoritmo usa random sem especificação; dados ausentes no checkout | Etapa 4: dicionário, estatísticas e gerador | Reconstruir cenários a partir de parâmetros publicados, distinguindo dados reais e sintéticos |
| R2d | Significado de cenário, d, G e rodadas | `main.tex:300` e `375`; intervalos e unidades não definidos | Etapas 4/5: tabela de demanda e definição temporal | Explicar cada variável e se rodadas são independentes ou períodos sucessivos |
| R3 | Resumo, figuras e interpretação inconsistentes | `main.tex:97`, `414`, `441`; bases e denominadores não rastreáveis | Etapas 6/7: regenerar saídas e revisar narrativa | Resumo e conclusões apoiados na mesma base, com métricas explícitas e incerteza |
| O1 | Unidades, valor e sensibilidade de M; penalização linear | Artigo quadrático, aplicação absoluta com M=1000; não equivalentes | Etapas 3/6: definir escala, justificar função e variar M | Explicar trade-off e demonstrar robustez; código corresponde à formulação |
| O2 | Justificar recusa de admissão por ocupação | Não há avaliação do benefício futuro da reserva | Etapas 2/6/7: justificar reserva e medir seus efeitos | Quantificar custo/benefício ou limitar a interpretação a um cenário hipotético |
| O3 | Valor de OR e meta global versus metas por tipo | OR experimental desconhecido; padrão da interface não prova configuração histórica | Etapas 3/6: publicar metas e comparar alternativas | Avaliar ocupação e efeitos por tipo de leito, sem ocultar saturação no agregado |
| O4 | Compatibilidade FCFS, indisponibilidade e espera | FCFS sem implementação disponível; aplicação permite criança em leito adulto | Etapas 3/5: regras de compatibilidade, fila e desempate | Algoritmo completo, determinístico dados eventos/semente, validado em casos mínimos |
| O5 | Trecho malformado do intervalo de demanda | `main.tex:300`; ainda presente | Etapa 7: corrigir depois de definir intervalos | Texto e fórmula compilam e refletem o gerador |
| O6 | Erros no algoritmo 1 | `cenario`, `scenario`, retorno `instance`, índices inconsistentes | Etapas 5/7: reescrever pseudocódigo conforme implementação | Entradas, variáveis, índices e retorno consistentes e definidos |
| O7 | Entradas e parâmetros de todos os algoritmos | A, Q, OR e chamadas sem instanciação completa | Etapas 4/5/7: especificações e configurações executáveis | Leitor consegue executar o experimento sem preencher lacunas por suposição |
| O8 | Referências, duplicatas e capitalização | Auditoria bibliográfica detalhada ainda não realizada | Etapa 7: revisar bib.bib e referências renderizadas | Metadados completos, duplicatas resolvidas e siglas preservadas; conferir numeração no PDF final |

## Achados próprios que também precisam de tratamento

| ID | Achado | Prioridade | Evidência | Próxima ação |
|---|---|---|---|---|
| A1 | Escores ordinais tratados como probabilidades | Crítica | `core/patients.py:15`, teste mínimo | Recuperar protocolo; não normalizar arbitrariamente |
| A2 | Simulador vazio, MSF/FCFS e resultados brutos ausentes | Crítica | Inventário do checkout | Recuperar insumos ou declarar novo experimento |
| A3 | CBC/penalização absoluta/compatibilidade diferentes do artigo | Alta | `core/allocation.py` | Fixar formulação e registrar versões |
| A4 | MSF do manuscrito pode preferir nenhuma admissão | Crítica | Contraexemplo e argumento no diagnóstico | Reformular política e validar independentemente |
| A5 | Interface LSF acessa coluna inexistente | Alta para uso da aplicação | `app.py:280`, `core/visuals.py:30` | Corrigir contrato de dados e verificar o fluxo |
| A6 | Status do solver não verificado | Alta | `core/allocation.py:78` | Validar status antes de extrair/usar solução |
| A7 | Métrica chamada objetivo não coincide com objetivo penalizado | Alta | `core/metrics.py:32` | Separar utilidade/sobrevivência e objetivo penalizado |

Nenhum item científico foi marcado como resolvido nesta fase: a entrega é o diagnóstico rastreável e o encaminhamento das correções.
