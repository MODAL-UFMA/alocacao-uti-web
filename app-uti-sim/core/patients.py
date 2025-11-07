import streamlit as st
from typing import List, Tuple, Dict, Any

Paciente = Dict[str, Any]

def init_state() -> None:
    if 'pacientes' not in st.session_state:
        st.session_state.pacientes = {
            'neonatal': [],
            'criancas': [],
            'adultos': []
        }


def add_patient(tipo: str, nome: str, sofa: dict) -> None:
    sum_sofa = sum(sofa.values())
    if sum_sofa <= 5:
        prob_uti = 5
    elif 6 <= sum_sofa <= 9:
        prob_uti = 4
    elif 10 <= sum_sofa <= 11:
        prob_uti = 3
    else:
        prob_uti = 1

    if prob_uti <= 3 or sofa.get('respiratory', 0) >= 3 or sofa.get('cardiovascular', 0) >= 2:
        prob_fora = 1
    elif sum_sofa > 5:
        prob_fora = 2
    elif 3 in sofa.values():
        prob_fora = 3
    else:
        prob_fora = 4
    
    
    st.session_state.pacientes[tipo].append({
        'nome': nome,
        'prob_uti': prob_uti,
        'prob_fora': prob_fora,
        'alocado': False,
        'leito_tipo': tipo,
        'sofa': sofa
    })


def all_patients() -> Tuple[List[Paciente], List[str]]:
    pacientes_todos: List[Paciente] = []
    tipos_pacientes: List[str] = []
    for tipo, lista in st.session_state.pacientes.items():
        for p in lista:
            pacientes_todos.append(p)
            tipos_pacientes.append(tipo)
    return pacientes_todos, tipos_pacientes


def totals(q_neonatal: int, q_criancas: int, q_adultos: int) -> Tuple[int, int]:
    total_leitos = q_neonatal + q_criancas + q_adultos
    total_pacientes = sum(len(st.session_state.pacientes[t]) for t in ['neonatal','criancas','adultos'])
    return total_leitos, total_pacientes
