# Alocação de leitos de UTI

Código de simulação de eventos discretos, testes e resultados brutos para regras de admissão em um departamento de cuidados críticos com vários tipos de leito, calibrado com dados públicos do HU-UFMA (CNES) e de registros nacionais de UTI.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `experiments/` | Simuladores estático e dinâmico, configurações, resultados e script das figuras |
| `experiments/figures/` | Figuras do manuscrito, geradas a partir dos CSVs |
| `data/huufma/` | Capacidades CNES e auditoria de fontes públicas (dados agregados) |
| `tests/` | Testes unitários e de integração |
| `app-uti-sim/` | Aplicação Streamlit legada, fora do escopo dos experimentos do artigo |

No código, a regra CMU-DL aparece com o rótulo `AUSTERE`.

## Reprodução

```bash
# Testes
PYTHONPATH=. python3 -m unittest discover -s tests -v

# Simulação dinâmica e análise de sensibilidade
python3 experiments/dynamic_simulation.py \
  --config experiments/configs/dynamic_huufma.json \
  --output experiments/results/dynamic_huufma \
  --sensitivity

# Figuras do artigo (a partir dos CSVs já depositados)
python3 experiments/generate_plots.py
```

Documentação: [experiments/README.md](experiments/README.md) e [data/huufma/README.md](data/huufma/README.md).

A aplicação Streamlit, se for usada, pode ser protegida definindo a variável de ambiente `UTI_SIM_PASSWORD`. Sem essa variável, a autenticação fica desligada.
