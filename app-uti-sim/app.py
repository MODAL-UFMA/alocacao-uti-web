import streamlit as st
import pandas as pd
import numpy as np
import warnings
import os
from pathlib import Path
warnings.filterwarnings('ignore')

from core.patients import init_state, add_patient as add_patient_core, all_patients, totals
from core.allocation import allocate_msg_pulp, allocate_lsf_pulp
from core.visuals import make_fig_ocupacao, make_fig_gravidade
from core.metrics import compute_objective, equidade_lsf

# Configuração da página
st.set_page_config(
    page_title="Sistema de Gestão de UTI",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# --- Autenticação ---
def require_auth():
    pw_expected = "sistemaleitosuti01234"
    print(pw_expected)
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        with st.sidebar:
            st.subheader("🔐 Autenticação")
            pwd = st.text_input("Senha", type="password", key="__auth_pwd__")
            if st.button("Entrar", key="__auth_login_btn__"):
                if pwd == pw_expected:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Senha incorreta")
        if not st.session_state.authenticated:
            st.stop()

require_auth()

# Inicializa estado de pacientes (modular)
init_state()

# Título principal
st.markdown('<h1 class="main-header">Sistema de Gestão de Alocação de Leitos de UTI</h1>', unsafe_allow_html=True)

# Sidebar para configurações
st.sidebar.header("Configurações do Sistema")

# Configuração de leitos
st.sidebar.subheader("Capacidade de Leitos")
q_neonatal = st.sidebar.number_input("Leitos Neonatal", min_value=0, max_value=100, value=5)
q_criancas = st.sidebar.number_input("Leitos Crianças", min_value=0, max_value=100, value=10)
q_adultos = st.sidebar.number_input("Leitos Adultos", min_value=0, max_value=100, value=15)

total_leitos, total_pacientes = totals(q_neonatal, q_criancas, q_adultos)

# Taxa mínima de ocupação
taxa_ocupacao = st.sidebar.slider("Taxa Mínima de Ocupação (%)", 0, 100, 80)

# Seção principal - Dados dos pacientes

st.subheader("Gerenciamento de Pacientes - Escore SOFA")

# Tabs para diferentes tipos de pacientes
tab1, tab2, tab3 = st.tabs(["Neonatal", "Criança", "Adulto"])

with tab1:
    st.write("**Adicionar Paciente Neonatal**")
    with st.form("form_neonatal"):
        nome_neo = st.text_input("Nome do Paciente")
        c1, c2 = st.columns(2)
        with c1:
            neo_resp = st.radio("Respiratório", [0,1,2,3,4], key="neo_sofa_resp", horizontal=True)
            neo_coag = st.radio("Coagulação", [0,1,2,3,4], key="neo_sofa_coag", horizontal=True)
            neo_liver = st.radio("Fígado", [0,1,2,3,4], key="neo_sofa_liver", horizontal=True)

        with c2:
            neo_cns = st.radio("SNC", [0,1,2,3,4], key="neo_sofa_cns", horizontal=True)
            neo_renal = st.radio("Renal", [0,1,2,3,4], key="neo_sofa_renal", horizontal=True)
            neo_cardio = st.radio("Cardiovascular", [0,1,2,3,4], key="neo_sofa_cardio", horizontal=True)

        if st.form_submit_button("Adicionar Paciente Neonatal"):
            if nome_neo:
                sofa = {
                    'respiratory': neo_resp,
                    'coagulation': neo_coag,
                    'liver': neo_liver,
                    'cardiovascular': neo_cardio,
                    'cns': neo_cns,
                    'renal': neo_renal
                }
                add_patient_core('neonatal', nome_neo, sofa)
                st.success(f"Paciente {nome_neo} adicionado!")

with tab2:
    st.write("**Adicionar Paciente Criança**")
    with st.form("form_criancas"):
        nome_cri = st.text_input("Nome do Paciente")
        c1, c2 = st.columns(2)
        with c1:
            cri_resp = st.radio("Respiratório", [0,1,2,3,4], key="cri_sofa_resp", horizontal=True)
            cri_coag = st.radio("Coagulação", [0,1,2,3,4], key="cri_sofa_coag", horizontal=True)
            cri_liver = st.radio("Fígado", [0,1,2,3,4], key="cri_sofa_liver", horizontal=True)
        with c2:
            cri_cns = st.radio("SNC", [0,1,2,3,4], key="cri_sofa_cns", horizontal=True)
            cri_renal = st.radio("Renal", [0,1,2,3,4], key="cri_sofa_renal", horizontal=True)
            cri_cardio = st.radio("Cardiovascular", [0,1,2,3,4], key="cri_sofa_cardio", horizontal=True)

        
        if st.form_submit_button("Adicionar Paciente Criança"):
            if nome_cri:
                sofa = {
                    'respiratory': cri_resp,
                    'coagulation': cri_coag,
                    'liver': cri_liver,
                    'cardiovascular': cri_cardio,
                    'cns': cri_cns,
                    'renal': cri_renal,
                }
                add_patient_core('criancas', nome_cri, sofa)
                st.success(f"Paciente {nome_cri} adicionado!")

with tab3:
    st.write("**Adicionar Paciente Adulto**")
    with st.form("form_adultos"):
        nome_adu = st.text_input("Nome do Paciente")
        c1, c2 = st.columns(2)
        with c1:
            adu_resp = st.radio("Respiratório", [0,1,2,3,4], key="adu_sofa_resp", horizontal=True)
            adu_coag = st.radio("Coagulação", [0,1,2,3,4], key="adu_sofa_coag", horizontal=True)
            adu_liver = st.radio("Fígado", [0,1,2,3,4], key="adu_sofa_liver", horizontal=True)
            
        with c2:
            adu_cns = st.radio("SNC", [0,1,2,3,4], key="adu_sofa_cns", horizontal=True)
            adu_renal = st.radio("Renal", [0,1,2,3,4], key="adu_sofa_renal", horizontal=True)
            adu_cardio = st.radio("Cardiovascular", [0,1,2,3,4], key="adu_sofa_cardio", horizontal=True)

        if st.form_submit_button("Adicionar Paciente Adulto"):
            if nome_adu:
                sofa = {
                    'respiratory': adu_resp,
                    'coagulation': adu_coag,
                    'liver': adu_liver,
                    'cardiovascular': adu_cardio,
                    'cns': adu_cns,
                    'renal': adu_renal,
                }
                add_patient_core('adultos', nome_adu, sofa)
                st.success(f"Paciente {nome_adu} adicionado!")

# --- Tabela de pacientes cadastrados ---
st.markdown("\n")
st.subheader("Pacientes Cadastrados")

linhas = []
rotulos_tipo = {
    'neonatal': 'Neonatal',
    'criancas': 'Criança',
    'adultos': 'Adulto'
}

for tipo_key, tipo_label in rotulos_tipo.items():
    for p in st.session_state.pacientes.get(tipo_key, []):
        sofa = p.get('sofa', {}) if isinstance(p, dict) else {}
        linhas.append({
            'Nome': p.get('nome', '') if isinstance(p, dict) else '',
            'Tipo': tipo_label,
            'Respiratório': sofa.get('respiratory', ''),
            'Coagulação': sofa.get('coagulation', ''),
            'Fígado': sofa.get('liver', ''),
            'Cardiovascular': sofa.get('cardiovascular', ''),
            'SNC': sofa.get('cns', ''),
            'Renal': sofa.get('renal', ''),
        })

if linhas:
    df_pacientes = pd.DataFrame(linhas)
    st.dataframe(df_pacientes, use_container_width=True, hide_index=True)
else:
    st.info("Nenhum paciente cadastrado até o momento.")

# Seção de Otimização
st.subheader("Otimização de Alocação")

# Escolha do algoritmo de otimização
algoritmo_escolhido = st.selectbox(
    "Escolha o Algoritmo de Alocação:",
    [
        "Maximizar Sobrevivência Geral",
        "Least Serious First (Menos Graves Primeiro)"
    ],
    index=0
)

if algoritmo_escolhido == "Least Serious First (Menos Graves Primeiro)":
    st.info("**Least Serious First:** Prioriza pacientes com menores diferenças entre probabilidades de sobrevivência na UTI vs. fora da UTI, tratando primeiro os casos menos críticos.")
else:
    st.info("**Maximizar Sobrevivência:** Prioriza pacientes com maiores benefícios de estar na UTI, maximizando a sobrevivência geral.")

if st.button("Executar Otimização", type="primary"):
    if total_pacientes > 0:
        # Preparar dados para otimização (usa core)
        pacientes_todos, tipos_pacientes = all_patients()
        
        n_pacientes = len(pacientes_todos)
        n_tipos_leitos = 3  # neonatal, crianças, adultos
        
        if n_pacientes > 0:
            # Algoritmo de otimização baseado na escolha do usuário (usa core.allocation - PuLP)
            if algoritmo_escolhido == "Least Serious First (Menos Graves Primeiro)":
                # LSF via PuLP
                alocacao = allocate_lsf_pulp(pacientes_todos, tipos_pacientes, (q_neonatal, q_criancas, q_adultos), target_occupancy=taxa_ocupacao/100)
            else:
                # MSG via PuLP
                alocacao = allocate_msg_pulp(pacientes_todos, tipos_pacientes, (q_neonatal, q_criancas, q_adultos), target_occupancy=taxa_ocupacao/100)
            
            # Calcular métricas da solução
            pacientes_alocados = int(np.sum(alocacao))
            taxa_ocupacao_atual = (pacientes_alocados / total_leitos) * 100 if total_leitos else 0
            
            # Função objetivo e benefício médio (via core.metrics)
            valor_objetivo, beneficio_medio = compute_objective(pacientes_todos, alocacao)

            # SOFA médio dos alocados (para MSG)
            sofa_alocados = []
            for i, paciente in enumerate(pacientes_todos):
                if np.sum(alocacao[i, :]) > 0:
                    sofa_dict = paciente.get('sofa', {}) if isinstance(paciente, dict) else {}
                    total_sofa = sum(v for v in sofa_dict.values() if isinstance(v, (int, float)))
                    sofa_alocados.append(total_sofa)
            sofa_medio_alocados = float(np.mean(sofa_alocados)) if len(sofa_alocados) > 0 else None
            
            col_res1, col_res2, col_res3 = st.columns(3)
            
            with col_res1:
                st.metric("Pacientes Alocados", int(pacientes_alocados), 
                         delta=f"{pacientes_alocados}/{total_pacientes}")
            
            with col_res2:
                st.metric("Taxa de Ocupação", f"{taxa_ocupacao_atual:.1f}%")
            
            with col_res3:
                if algoritmo_escolhido == "Least Serious First (Menos Graves Primeiro)":
                    eq = equidade_lsf(pacientes_todos, alocacao)
                    st.metric("Equidade LSF", f"{eq:.3f}" if eq is not None else "N/A", help="Medida de equidade na alocação (0-1, maior é melhor)")
                else:
                    st.metric(
                        "Escore SOFA Médio (alocados)",
                        f"{sofa_medio_alocados:.1f}" if sofa_medio_alocados is not None else "N/A",
                        help="Média do escore SOFA dos pacientes alocados"
                    )
            
            # Visualização da alocação
            st.subheader("📋 Resultado da Alocação")
            
            # Criar DataFrame para visualização
            resultados = []
            tipos_leitos_nomes = ['Neonatal', 'Crianças', 'Adultos']

            def _label(score:int) -> str:
                mapa = {1: "Muito Baixa", 2: "Baixa", 3: "Média", 4: "Alta", 5: "Muito Alta"}
                return mapa.get(int(score), "Média")
            
            for i, (paciente, tipo) in enumerate(zip(pacientes_todos, tipos_pacientes)):
                alocado_em = np.argmax(alocacao[i, :]) if np.sum(alocacao[i, :]) > 0 else None
                rot_uti = _label(paciente['prob_uti'])
                rot_fora = _label(paciente['prob_fora'])
                
                # Definir gravidade como a categoria do escore UTI
                gravidade = rot_uti
                
                resultados.append({
                    'Paciente': paciente['nome'],
                    'Tipo': tipo.capitalize(),
                    'Prob. UTI': rot_uti,
                    'Prob. Fora': rot_fora,
                    'Alocado em': tipos_leitos_nomes[alocado_em] if alocado_em is not None else 'Não alocado',
                    'Status': 'Alocado' if alocado_em is not None else 'Não alocado'
                })
            
            df_resultados = pd.DataFrame(resultados)
            st.dataframe(df_resultados, width='stretch')
            
            # Gráfico de ocupação por tipo de leito
            ocupacao_por_tipo = [
                np.sum(alocacao[:, 0]),  # Neonatal
                np.sum(alocacao[:, 1]),  # Crianças
                np.sum(alocacao[:, 2])   # Adultos
            ]
            
            fig_ocupacao = make_fig_ocupacao(tipos_leitos_nomes, ocupacao_por_tipo, (q_neonatal, q_criancas, q_adultos))
            
            st.plotly_chart(fig_ocupacao, width='stretch')
            
            # Gráfico adicional para análise do algoritmo escolhido
            if algoritmo_escolhido == "Least Serious First (Menos Graves Primeiro)":
                st.subheader("📊 Análise da Estratégia Least Serious First")
                
                # Criar gráfico de gravidade vs alocação
                df_analise = pd.DataFrame(resultados)
                
                fig_gravidade = make_fig_gravidade(df_analise)
                if fig_gravidade is not None:
                    st.plotly_chart(fig_gravidade, width='stretch')
                
                # Estatísticas LSF (sem usar diferença)
                col_lsf1, col_lsf2 = st.columns(2)
                
                alocados_baixa = df_analise[(df_analise['Gravidade'].isin(['Muito Baixa','Baixa'])) & (df_analise['Status'] == 'Alocado')].shape[0]
                total_baixa = df_analise[df_analise['Gravidade'].isin(['Muito Baixa','Baixa'])].shape[0]
                alocados_alta = df_analise[(df_analise['Gravidade'].isin(['Alta','Muito Alta'])) & (df_analise['Status'] == 'Alocado')].shape[0]
                
                with col_lsf1:
                    if total_baixa > 0:
                        pct_baixa_alocada = (alocados_baixa / total_baixa) * 100
                        st.metric("% Casos Gravidade Baixa/Muito Baixa Alocados", f"{pct_baixa_alocada:.1f}%")
                    else:
                        st.metric("% Casos Gravidade Baixa/Muito Baixa Alocados", "N/A")
                
                with col_lsf2:
                    st.metric("Casos Gravidade Alta/Muito Alta Alocados", alocados_alta)
        else:
            st.warning("Nenhum paciente cadastrado para otimização.")
    else:
        st.warning("Adicione pacientes antes de executar a otimização.")

# Botão para limpar dados
if st.sidebar.button("🗑️ Limpar Todos os Dados"):
    st.session_state.pacientes = {
        'neonatal': [],
        'criancas': [],
        'adultos': []
    }
    st.rerun()

# Footer
st.markdown("---")
st.markdown("*Sistema de Gestão de UTI - UTISim*")