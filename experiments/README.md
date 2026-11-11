# Experimento estático reproduzível — versão inicial

Esta implementação é nova. Não reproduz os experimentos submetidos em 2025 e não usa dados do HU-UFMA. Os pacientes e probabilidades são inteiramente sintéticos, sem calibração clínica. O usuário confirmou que o repositório disponível é todo o material de código que possui e autorizou implementar o que falta.

## Execução

Requer Python 3.10 ou superior, sem bibliotecas externas. Na raiz do repositório:

```bash
# Executar suíte de testes completa (estática e dinâmica):
python3 -m unittest discover -s tests -v

# Simulação estática de referência:
python3 monte-carlo-simulation.py --config experiments/configs/pilot.json --output experiments/results/pilot

# Simulação dinâmica (CNES HU-UFMA + overflow + sensibilidade):
PYTHONPATH=. python3 experiments/dynamic_simulation.py \
  --config experiments/configs/dynamic_huufma.json \
  --output experiments/results/dynamic_huufma \
  --sensitivity

# Figuras do manuscrito Elsevier:
python3 experiments/generate_plots.py
```

Use outra pasta vazia para repetir a execução se quiser preservar saídas anteriores. Parâmetros, versões e hashes são registrados. Sementes determinísticas por fluxo (CRN) mantêm os mesmos pacientes entre políticas.

## Simulação dinâmica (revisão C&OR)

Implementada em `dynamic_simulation.py`:

1. **Chegadas Poisson** por pool, com \(\rho\) comum via Little; warm-up 15d + avaliação 60d.
2. **LOS log-normal** dependente de gravidade; **deterioração** exponencial de \(P_{\mathrm{in}}\) na fila.
3. **Reneging** com \(W_{\max}\sim U(1,3)\) dias.
4. **Capacidades CNES:** neonatal 20, pediátrico 10, adulto 15, coronária 10 (55 leitos) com overflow adulto↔UCO.
5. **Políticas:** FCFS, MSF, LSF, MGS, CMU-MGS (\(c\mu\)) e AUSTERE (deadline-aware).
6. **CRN + Holm–Bonferroni** e sensibilidade a ruído em \(\widetilde{\Delta P}\).


## Hipóteses e decisões

- Cada replicação é uma alocação estática independente, não um dia ou período consecutivo.
- Todos os leitos começam disponíveis; não há internações preexistentes, permanência, altas, espera temporal, transferências ou reinternações.
- Compatibilidade exclusiva: neonatal, pediátrico e adulto só recebem pacientes do respectivo grupo. Não se adota a flexibilização criança–adulto da aplicação legada.
- A ordem de chegada é uma permutação aleatória implícita pela geração sequencial de pacientes independentes; FCFS percorre essa ordem. Pacientes incompatíveis com leitos restantes são não admitidos, sem bloquear os demais.
- Não admitidos permanecem fora da UTI e recebem probabilidade P_out; não se simula fila posterior.
- `demand_ratios` é N/Q. N é arredondado por floor(d*Q+0,5). Esses valores não são os níveis d=1..6 do artigo antigo.
- O gerador sorteia o tipo segundo `type_weights`, P_out uniformemente no intervalo configurado e uma fração g uniformemente em outro intervalo. Define P_in = P_out + (1-P_out)*g. Tipo, P_out e g são independentes. Essa escolha assegura probabilidades válidas, mas não constitui protocolo clínico e não modela idade, SOFA ou comorbidades.
- Capacidades e metas do piloto são exemplos operacionais, não estimativas hospitalares. As distribuições independentes e idênticas entre tipos são uma simplificação para validar o programa.

## Políticas e formulação

Seja a_i binário, indicando admissão, e t(i) o único tipo compatível. Para todo tipo t, a soma de a_i com t(i)=t não pode exceder Q_t. Não há mínimo obrigatório de admissões.

As três políticas por escore maximizam soma_i a_i*s_i menos a penalização configurada:

- **MGS:** s_i = P_in - P_out. A soma de P_out de todos os pacientes é constante; ela é incluída no valor do objetivo reportado.
- **LSF:** s_i = P_in. É a definição operacional por prognóstico na UTI usada aqui, não uma equivalência clínica universal entre maior P_in e menor gravidade.
- **MSF:** s_i = 1-P_out. Define-se gravidade operacional pela menor sobrevivência fora da UTI. Esta é uma reformulação explícita, não a fórmula defeituosa do manuscrito. O escore não é uma probabilidade de sobrevivência da população.
- **FCFS:** admite na ordem de chegada até esgotar cada capacidade. É referência sem reserva de leitos; não otimiza nem respeita uma meta suave de ocupação. Sua alocação se repete entre configurações de penalização. A penalização registrada para FCFS é apenas descritiva; seu objetivo penalizado fica vazio.

Modos de penalização:

1. `none`: sem penalização; permite comparar as prioridades sem o efeito da meta.
2. `global`: M * |n_admitidos / Q_total - meta_global|^p.
3. `per_type`: M vezes a média de |n_t/Q_t - meta_t|^p entre tipos com capacidade positiva.

`power=1` usa desvio absoluto e `power=2` usa quadrado. Ocupações e metas são frações, não percentuais. M tem escala de pontos do objetivo; em MGS, equivale a unidades de sobreviventes esperados por unidade de penalização. A mesma magnitude de M não implica o mesmo trade-off clínico nas outras políticas. A média por tipo mantém a penalização limitada por M, mas dá igual peso aos tipos, não aos leitos. Isso é uma hipótese a estudar, não uma escolha ótima demonstrada.

Penalização suave pode recusar admissão mesmo com vagas. Em um estudo estático não se representa benefício futuro de reservar essas vagas: o piloto mede esse trade-off, sem recomendá-lo clinicamente. Comparações com FCFS misturam efeitos de prioridade e reserva; o modo sem penalização é o controle necessário. Resultados entre políticas não devem ser interpretados apenas por seus objetivos internos, que são distintos.

## Solução exata sob estas hipóteses

Para um número fixo de admissões por tipo, basta selecionar os maiores escores daquele tipo. Sem penalização ou com penalização global, limitar cada lista pela capacidade e ordenar a união fornece a melhor solução para cada cardinalidade total. O algoritmo examina todos esses prefixos e escolhe o melhor objetivo penalizado. Com penalização por tipo, a função separa-se por tipo e cada prefixo pode ser otimizado independentemente.

Logo, não é necessário um solver MIP para esta formulação restrita. Não se deve apresentar essa implementação como nova contribuição algorítmica sem análise da literatura. Essa propriedade deixa de justificar o algoritmo se houver compatibilidade cruzada, recursos acoplados ou dinâmica temporal. Empates de escore usam ordem de chegada e id; empates exatos do objetivo favorecem mais admissões.

## Saídas e interpretação

- `patients.csv`: pacientes sintéticos e uniforme de desfecho por cenário.
- `runs.csv`: alocação por ids, admissões, ocupação por tipo, sobrevivência esperada/realizada e penalização.
- `summary.csv`: médias, erros padrão e intervalos aproximados de 95% entre replicações.
- `paired_differences.csv`: diferenças MGS menos cada outra política, calculadas dentro da mesma replicação antes do intervalo.
- `config.json` e `metadata.json`: configuração, ambiente, identificação do código e hashes das saídas.

Desfecho principal para esta fase: soma das probabilidades de sobrevivência de toda a população elegível, admitida ou não. Sobrevivência realizada usa U_i < P_in quando admitido e U_i < P_out quando não admitido. O mesmo U_i é usado em todas as políticas, representando um acoplamento monotônico dos desfechos potenciais. Isso reduz ruído das comparações; não é inferência causal baseada em dados observacionais.

Os intervalos usam média +/- 1,96*erro padrão, aproximação normal entre replicações independentes. São exploratórios, não ajustados por comparações múltiplas e não representam incerteza na calibração das probabilidades. As repetições FCFS entre configurações não são amostras independentes adicionais. O piloto não define tamanho amostral definitivo nem testa eficácia clínica.

## Validação e próximos passos

Os testes confrontam as soluções com enumeração de todos os subconjuntos viáveis em instâncias pequenas, cobrem probabilidades inválidas, desempate, incompatibilidade, capacidade zero, métricas e reexecução idêntica. A interface Streamlit permanece uma aplicação legada separada: esta etapa não corrige seus escores nem lhe atribui validação clínica.

Próximos trabalhos: revisão bibliográfica para decidir a contribuição; análise de sensibilidade de M/metas/composição; eventual protocolo clínico fundamentado; somente depois, escolha e validação de uma extensão dinâmica. Os resultados antigos e `main.tex` não foram substituídos por resultados sintéticos.
