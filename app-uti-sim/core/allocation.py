from typing import List, Tuple
import numpy as np

# Compatibilidade de leitos por tipo de paciente
# indices: 0=neonatal, 1=criancas, 2=adultos

def compatible_beds(tipo: str) -> List[int]:
    if tipo == 'neonatal':
        return [0]
    if tipo == 'criancas':
        return [1, 2]
    return [2]


# ---------------------- Modelos PuLP (MILP) ----------------------

def _solve_mip(pacientes_todos, tipos_pacientes, caps: Tuple[int,int,int], TO: float, M_penalty: float, objective: str) -> np.ndarray:
    """
    objective: 'MSG' ou 'LSF'
    Penalidade implementada como M * |(sum x)/|Q| - TO| (aproximação linear ao termo quadrático).
    """
    try:
        import pulp as pl
    except Exception as e:
        raise ImportError("pulp não está instalado. Adicione 'pulp' ao requirements e instale as dependências.") from e

    qn, qc, qa = caps
    Q = int(qn + qc + qa) if (qn + qc + qa) > 0 else 1
    n = len(pacientes_todos)
    J = [0, 1, 2]

    model = pl.LpProblem("Alocacao_UTI", pl.LpMaximize)

    # Variáveis x_{ij} somente quando compatível
    x = {}
    for i in range(n):
        tipo = tipos_pacientes[i]
        comp = set(compatible_beds(tipo))
        for j in J:
            if j in comp:
                x[(i, j)] = pl.LpVariable(f"x_{i}_{j}", lowBound=0, upBound=1, cat=pl.LpBinary)

    # Soma alocados (para penalidade de ocupação)
    s = pl.lpSum(x.values()) if x else 0

    # Variáveis para |s/Q - TO|
    d_pos = pl.LpVariable("d_pos", lowBound=0)
    d_neg = pl.LpVariable("d_neg", lowBound=0)
    # s/Q - TO = d_pos - d_neg
    model += (s / Q) - TO == d_pos - d_neg
    dev = d_pos + d_neg

    # Objetivo
    if objective == 'MSG':
        # Constante: sum_i P_out^i
        const_out = sum(p['prob_fora'] for p in pacientes_todos)
        # Termo variável: sum_{i,j} x_{ij} * (P_in^i - P_out^i)
        term = pl.lpSum(x[(i, j)] * (pacientes_todos[i]['prob_uti'] - pacientes_todos[i]['prob_fora'])
                        for (i, j) in x)
        model += const_out + term - M_penalty * dev
    elif objective == 'LSF':
        # Termo variável: sum_{i,j} x_{ij} * P_in^i
        term = pl.lpSum(x[(i, j)] * (pacientes_todos[i]['prob_uti']) for (i, j) in x)
        model += term - M_penalty * dev
    else:
        raise ValueError("objective deve ser 'MSG' ou 'LSF'")

    # Restrições de capacidade
    cap = {0: qn, 1: qc, 2: qa}
    for j in J:
        model += pl.lpSum(x[(i, j)] for (i, jj) in x if jj == j) <= cap[j]

    # Exclusividade: cada paciente em no máx. um leito
    for i in range(n):
        model += pl.lpSum(x[(ii, j)] for (ii, j) in x if ii == i) <= 1

    # Resolver
    model.solve(pl.PULP_CBC_CMD(msg=False))

    # Extrair solução
    aloc = np.zeros((n, 3))
    for (i, j), var in x.items():
        if var.value() is not None and var.value() > 0.5:
            aloc[i, j] = 1
    return aloc


def allocate_msg_pulp(pacientes_todos, tipos_pacientes, caps: Tuple[int,int,int], target_occupancy: float, M_penalty: float = 1000.0) -> np.ndarray:
    """Modelo MSG (Maximizar sobrevivência geral) com penalização de ocupação."""
    return _solve_mip(pacientes_todos, tipos_pacientes, caps, TO=target_occupancy, M_penalty=M_penalty, objective='MSG')


def allocate_lsf_pulp(pacientes_todos, tipos_pacientes, caps: Tuple[int,int,int], target_occupancy: float, M_penalty: float = 1000.0) -> np.ndarray:
    """Modelo LSF com penalização de ocupação."""
    return _solve_mip(pacientes_todos, tipos_pacientes, caps, TO=target_occupancy, M_penalty=M_penalty, objective='LSF')
