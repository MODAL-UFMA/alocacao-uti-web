# Alocação de leitos de UTI

Repositório com simulação de alocação dinâmica de leitos de UTI multi-tipo (HU-UFMA/CNES), experimentos reproduzíveis e manuscrito para *Computers & Operations Research*.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `experiments/` | Simuladores estático e dinâmico, configs, resultados e figuras |
| `data/huufma/` | Capacidades CNES e auditoria de fontes públicas |
| `doc/artigo-elsevier/` | Manuscrito Elsevier (`main.tex` / `main.pdf`) e carta-resposta |
| `doc/artigo-rairo/` | Material histórico da submissão RAIRO e plano de revisão |
| `tests/` | Testes unitários e de integração |
| `app-uti-sim/` | Aplicação Streamlit legada (fora do escopo da revisão atual) |

## Experimentos

```bash
# Testes
PYTHONPATH=. python3 -m unittest discover -s tests -v

# Simulação dinâmica + sensibilidade
python3 experiments/dynamic_simulation.py \
  --config experiments/configs/dynamic_huufma.json \
  --output experiments/results/dynamic_huufma \
  --sensitivity

# Figuras do artigo
python3 experiments/generate_plots.py
```

Documentação detalhada: [experiments/README.md](experiments/README.md) e [data/huufma/README.md](data/huufma/README.md).

## Manuscrito

- PDF: [doc/artigo-elsevier/main.pdf](doc/artigo-elsevier/main.pdf)
- Resposta aos revisores: [doc/artigo-elsevier/RESPONSE_TO_REVIEWERS.md](doc/artigo-elsevier/RESPONSE_TO_REVIEWERS.md)
- Andamento: [doc/artigo-rairo/ANDAMENTO.md](doc/artigo-rairo/ANDAMENTO.md)
