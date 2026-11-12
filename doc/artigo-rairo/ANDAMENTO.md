# Andamento da revisão

## Estado atual (revisão C&OR — major revision)

Streamlit foi deliberadamente deixado de fora.

### Concluído nesta rodada

1. **Simulador dinâmico revisado** (`experiments/dynamic_simulation.py`)
   - Deterioração de \(P_{in}\) na fila
   - LOS dependente de gravidade
   - Overflow adulto ↔ coronariana (55 leitos CNES)
   - Warm-up 15d + janela 60d
   - Políticas: FCFS, MSF, LSF, MGS, CMU_MGS, AUSTERE
   - Sensibilidade a ruído em \(\widehat{\Delta P}\)
   - CRN + IC + Holm–Bonferroni
2. **Experimentos** em `experiments/results/dynamic_huufma/` (2.400 trajetórias + sensitivity)
3. **11 testes** passando (`PYTHONPATH=. python3 -m unittest discover -s tests -v`)
4. **Manuscrito Elsevier reescrito** (`doc/artigo-elsevier/main.tex` → `main.pdf`, 7 pp.)
5. **Carta-resposta** (`doc/artigo-elsevier/RESPONSE_TO_REVIEWERS.md`)
6. **Figuras** regeneradas (`fig_survivors`, `fig_paired_gain`, `fig_waiting_times`, `fig_sensitivity`)
7. **`bib.bib`** corrigido (Mills DOI/páginas/autor; refs OR/MS; encoding)

### Resultado-chave (\(\rho=1.6\))

| Política | ΔS vs FCFS | Rel. % |
|---|---:|---:|
| CMU-MGS | +58.57 [57.45, 59.70] | +11.32% |
| MGS | +57.79 [56.71, 58.88] | +11.16% |
| LSF | +39.03 | +7.54% |
| AUSTERE | +32.07 | +6.20% |
| MSF | +29.06 | +5.61% |

Ocupação FCFS em \(\rho=1.6\): **99.9%** (bug M2 corrigido).

### Entregáveis principais

- PDF: `doc/artigo-elsevier/main.pdf` (cópia `doc/artigo-elsevier-final.pdf`)
- Fonte: `doc/artigo-elsevier/main.tex`
- Resposta aos revisores: `doc/artigo-elsevier/RESPONSE_TO_REVIEWERS.md`
- Código: `experiments/dynamic_simulation.py`
- Figuras: `doc/artigo-elsevier/fig_*.png`

### Fora de escopo (pedido do usuário)

- Atualização do app Streamlit (`app-uti-sim/`)
