# Dados Públicos do HU-UFMA e CNES

Este diretório contém os dados coletados das fontes públicas oficiais referentes ao **Hospital Universitário da Universidade Federal do Maranhão (HU-UFMA / EBSERH)** e ao **DATASUS / CNES**.

## 1. Capacidade de Leitos Críticos (CNES)

- **Estabelecimento:** HOSPITAL UNIVERSITARIO DA UFMA (HU-UFMA)
- **Código CNES:** 2726653
- **Município:** São Luís - MA
- **Fonte Oficial:** DATASUS / CNES - Módulo Hospitalar
- **Competência Analisada:** 12/2024 (arquivo bruto: `raw/cnes_202412.html`)
- **Arquivo Estruturado:** `capacidade_cnes.json`

### Leitos Confirmados (100% SUS):
| Tipo de Leito CNES | Código/Descrição | Leitos Existentes | Leitos SUS | Categoria no Modelo |
| :--- | :--- | :---: | :---: | :--- |
| UTI Adulto | 76-UTI-A TIPO III | 15 | 15 | `adult` (15) |
| UTI Pediátrica | 79-UTI-PED TIPO III | 10 | 10 | `pediatric` (10) |
| UTI Neonatal | 81-UTI NEONATAL - TIPO II | 20 | 20 | `neonatal` (20) |
| Unidade Coronariana | 86-UCO TIPO III | 10 | 10 | `coronary_uco` (10) |
| **Total UTI Estrito Senso** | — | **45** | **45** | **45 leitos** |
| **Total Cuidados Críticos (+ UCO)** | — | **55** | **55** | **55 leitos** |

### Comparação com o Cenário do Artigo (Pandemia de COVID-19):
O manuscrito histórico (`main.tex`) refere uma capacidade de 77 leitos de UTI (35 neonatal, 16 pediátrico e 26 adulto), decorrente da expansão emergencial e de leitos de contingência COVID-19 habilitados durante a pandemia (2020-2022). A capacidade permanente atual confirmada no CNES é de 45 leitos de UTI (20 neonatal, 10 pediátrico, 15 adulto).

Ambas as configurações foram formalizadas para experimentação:
- `experiments/configs/huufma_cnes.json`: capacidade permanente oficial (45 leitos).
- `experiments/configs/huufma_covid.json`: capacidade emergencial histórica do artigo (77 leitos).

## 2. Auditoria dos Dados Abertos do HU-UFMA

Foram baixados e auditados os arquivos publicados no portal de dados abertos da EBSERH / HU-UFMA:
1. `raw/internacoes.xlsx`: Planilha de quantidade de internações realizadas. A estrutura está presente (anos 2020 a 2025), porém todas as células de dados mensais estão vazias (`None`).
2. `raw/permanencia.xlsx`: Planilha de média de permanência hospitalar geral. Apresenta médias de permanência em enfermarias gerais (Clínica Médica, Clínica Pediátrica, Clínica Cirúrgica), não contemplando tempo de permanência em leitos de UTI nem desfechos clínicos.

Por integridade científica, esses campos vazios e gerais **não foram utilizados** para inferir artificialmente demanda ou permanência de UTI.

## 3. Registro de Procedência e Hashes

Os metadados de requisição, URLs finais, tamanhos e hashes SHA-256 de todos os arquivos brutos estão registrados em `sources.json`.
