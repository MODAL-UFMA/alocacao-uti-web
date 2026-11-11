"""Verificações da auditoria, sem executar Streamlit ou instalar dependências.

Executar da raiz do repositório:
python3 doc/artigo-rairo/auditoria/verificar_achados.py

As funções puras/de cadastro são extraídas por AST dos arquivos originais.
O estado Streamlit é substituído somente para testar o cadastro. Isto não
testa a interface, o solver nem reproduz os experimentos do artigo.
"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import List

ROOT = Path(__file__).resolve().parents[3]


def extract_function(relative_path, name, namespace):
    tree = ast.parse((ROOT / relative_path).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), relative_path, "exec"), namespace)
    return namespace[name]


def main():
    findings = {}
    state = {"pacientes": {"neonatal": [], "criancas": [], "adultos": []}}
    add = extract_function("app-uti-sim/core/patients.py", "add_patient", {"st": SimpleNamespace(session_state=SimpleNamespace(**state))})
    add("adultos", "caso_sintetico", dict.fromkeys(["respiratory", "coagulation", "liver", "cardiovascular", "cns", "renal"], 0))
    patient = state["pacientes"]["adultos"][0]
    assert patient["prob_uti"] == 5 and patient["prob_fora"] == 4
    findings["escores_fora_do_intervalo_probabilistico"] = {k: patient[k] for k in ("prob_uti", "prob_fora")}

    compatible = extract_function("app-uti-sim/core/allocation.py", "compatible_beds", {"List": List})
    assert compatible("criancas") == [1, 2]
    findings["crianca_aceita_leito_adulto"] = compatible("criancas")

    # Enumeração independente da fórmula MSF escrita no manuscrito.
    # Um paciente, um leito, P_in=0.9, M=1 e OR=0.8.
    values = {x: x * 0.9 - (x - 0.8) ** 2 for x in (0, 1)}
    assert min(values, key=values.get) == 0
    findings["msf_manuscrito_prefere_nao_admitir_neste_exemplo"] = values

    app_tree = ast.parse((ROOT / "app-uti-sim/app.py").read_text())
    # Localiza o dicionário enviado a resultados.append sem executar a aplicação.
    append = next(n for n in ast.walk(app_tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr == "append"
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == "resultados")
    keys = [k.value for k in append.args[0].keys if isinstance(k, ast.Constant)]
    assert "Gravidade" not in keys
    findings["coluna_gravidade_ausente_no_resultado"] = keys
    baseline = json.loads(Path(__file__).with_name("manifesto_base.json").read_text())
    original = next(f for f in baseline["files"] if f["path"] == "monte-carlo-simulation.py")
    assert original["bytes"] == 0
    findings["simulador_monte_carlo_vazio_na_base_auditada"] = True
    findings["simulador_atual_bytes"] = (ROOT / "monte-carlo-simulation.py").stat().st_size
    output = Path(__file__).with_name("verificacoes.json")
    output.write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n")
    print("5 verificações concluídas; evidências em", output.relative_to(ROOT))


if __name__ == "__main__":
    main()
