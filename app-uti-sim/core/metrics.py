import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Any, Optional


def compute_survivors(alocacao: np.ndarray, pacientes_todos, tipos_pacientes) -> pd.DataFrame:
    # prob de sobrevivencia conforme alocado (se nao alocado, prob_fora)
    surv = []
    for i, (pac, tipo) in enumerate(zip(pacientes_todos, tipos_pacientes)):
        if alocacao.shape[1] != 3:
            raise ValueError('Alocacao deve ter 3 colunas (neo, cri, adu)')
        if alocacao[i].sum() == 0:
            p = pac['prob_fora']
            dest = 'fora'
        else:
            j = int(np.argmax(alocacao[i]))
            p = pac['prob_uti']
            dest = ['neo','cri','adu'][j]
        surv.append({'paciente': pac['nome'], 'tipo': tipo, 'destino': dest, 'p_sobrevive': p})
    return pd.DataFrame(surv)


def occupancy(caps: Tuple[int,int,int], alocacao: np.ndarray) -> Tuple[float, float, float]:
    o = alocacao.sum(0)
    qn, qc, qa = caps
    on = o[0] / max(qn, 1)
    oc = o[1] / max(qc, 1)
    oa = o[2] / max(qa, 1)
    return float(on), float(oc), float(oa)


def compute_objective(pacientes_todos: List[Dict[str, Any]], alocacao: np.ndarray) -> Tuple[float, float]:
    """Retorna (valor_objetivo_total, beneficio_medio)."""
    n = len(pacientes_todos)
    total = 0.0
    for i in range(n):
        if np.sum(alocacao[i, :]) > 0:
            total += pacientes_todos[i]['prob_uti']
        else:
            total += pacientes_todos[i]['prob_fora']
    beneficio_medio = (total / n) if n else 0.0
    return float(total), float(beneficio_medio)


def equidade_lsf(pacientes_todos: List[Dict[str, Any]], alocacao: np.ndarray) -> Optional[float]:
    """Calcula 1/(1+variancia) das diferenças (uti - fora) dos pacientes alocados."""
    difs = []
    n = len(pacientes_todos)
    for i in range(n):
        if np.sum(alocacao[i, :]) > 0:
            difs.append(pacientes_todos[i]['prob_uti'] - pacientes_todos[i]['prob_fora'])
    if not difs:
        return None
    var = float(np.var(difs))
    return 1.0 / (1.0 + var)
