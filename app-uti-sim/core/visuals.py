from typing import List, Tuple, Optional
import plotly.graph_objects as go
import pandas as pd



def make_fig_ocupacao(tipos_leitos_nomes: List[str], ocupacao_por_tipo: List[float], caps: Tuple[int,int,int]) -> go.Figure:
    q_neonatal, q_criancas, q_adultos = caps
    fig = go.Figure(data=[
        go.Bar(name='Ocupados', x=tipos_leitos_nomes, y=ocupacao_por_tipo,
               marker_color=['lightblue', 'lightgreen', 'lightcoral']),
        go.Bar(name='Disponíveis', x=tipos_leitos_nomes,
               y=[q_neonatal - ocupacao_por_tipo[0],
                  q_criancas - ocupacao_por_tipo[1],
                  q_adultos - ocupacao_por_tipo[2]],
               marker_color=['white', 'white', 'white'],
               marker_line_color=['lightblue', 'lightgreen', 'lightcoral'],
               marker_line_width=2)
    ])
    fig.update_layout(
        title="Ocupação dos Leitos por Tipo",
        barmode='stack',
        height=400,
        yaxis_title="Número de Leitos"
    )
    return fig


def make_fig_gravidade(df_analise: pd.DataFrame) -> Optional[go.Figure]:
    alocacao_gravidade = df_analise.groupby(['Gravidade', 'Status']).size().unstack(fill_value=0)
    if alocacao_gravidade.empty:
        return None
    fig = go.Figure()
    if '✅ Alocado' in alocacao_gravidade.columns:
        fig.add_trace(go.Bar(
            name='Alocados',
            x=alocacao_gravidade.index,
            y=alocacao_gravidade['✅ Alocado'],
            marker_color='lightgreen'
        ))
    if '❌ Lista de espera' in alocacao_gravidade.columns:
        fig.add_trace(go.Bar(
            name='Lista de Espera',
            x=alocacao_gravidade.index,
            y=alocacao_gravidade['❌ Lista de espera'],
            marker_color='lightcoral'
        ))
    fig.update_layout(
        title="Alocação por Nível de Gravidade (LSF)",
        xaxis_title="Nível de Gravidade",
        yaxis_title="Número de Pacientes",
        barmode='stack',
        height=400
    )
    return fig
