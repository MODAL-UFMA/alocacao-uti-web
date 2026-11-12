"""Alocação estática com probabilidades sintéticas; não é um modelo clínico."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
import platform
import sys

TYPES = ("neonatal", "pediatric", "adult")
POLICIES = ("MGS", "LSF", "MSF", "FCFS")


@dataclass(frozen=True)
class Patient:
    id: int
    bed_type: str
    p_in: float
    p_out: float
    arrival_order: int


def validate(patients, capacities):
    if set(capacities) != set(TYPES):
        raise ValueError("Capacidades devem definir exatamente os três tipos de leito")
    if any(type(v) is not int or v < 0 for v in capacities.values()):
        raise ValueError("Capacidades devem ser inteiros não negativos")
    if len({p.id for p in patients}) != len(patients):
        raise ValueError("Identificadores de pacientes devem ser únicos")
    for p in patients:
        if p.bed_type not in TYPES or not 0 <= p.p_out <= p.p_in <= 1:
            raise ValueError("Tipo inválido ou probabilidades fora de 0 <= P_out <= P_in <= 1")


def priority(p, policy):
    if policy == "MGS":
        return p.p_in - p.p_out
    if policy == "LSF":
        return p.p_in
    if policy == "MSF":
        return 1 - p.p_out
    raise ValueError("Política sem escore de otimização")


def penalty(counts, capacities, targets, mode, weight, power):
    if mode == "none":
        return 0.0
    if mode == "global":
        total = sum(capacities.values())
        return weight * abs(sum(counts.values()) / total - targets["global"]) ** power if total else 0.0
    # Média dos desvios entre tipos com capacidade positiva: evita multiplicar
    # automaticamente a escala de M pelo número de tipos.
    active = [t for t in TYPES if capacities[t] > 0]
    return weight * sum(abs(counts[t] / capacities[t] - targets[t]) ** power for t in active) / len(active) if active else 0.0


def allocate(patients, capacities, policy, targets, mode="none", weight=0.0, power=2):
    """Ótimo exato das políticas por escore, sob compatibilidade exclusiva.

    Empates de escore: chegada e id. Empates de objetivo: mais admissões.
    FCFS é a referência sem reserva: admite em ordem até a capacidade.
    """
    validate(patients, capacities)
    if policy not in POLICIES or mode not in ("none", "global", "per_type"):
        raise ValueError("Política ou modo de penalização inválido")
    if not math.isfinite(weight) or weight < 0 or power not in (1, 2):
        raise ValueError("Peso deve ser finito e não negativo; potência deve ser 1 ou 2")
    if any(k not in targets or not 0 <= targets[k] <= 1 for k in (*TYPES, "global")):
        raise ValueError("Metas devem estar entre zero e um")
    if policy == "FCFS":
        counts = dict.fromkeys(TYPES, 0)
        chosen = set()
        for p in sorted(patients, key=lambda p: (p.arrival_order, p.id)):
            if counts[p.bed_type] < capacities[p.bed_type]:
                chosen.add(p.id)
                counts[p.bed_type] += 1
        return chosen

    groups = {t: sorted((p for p in patients if p.bed_type == t),
                        key=lambda p: (-priority(p, policy), p.arrival_order, p.id))[:capacities[t]] for t in TYPES}
    if mode == "per_type":
        chosen = set()
        active_count = sum(capacities[t] > 0 for t in TYPES)
        for t in TYPES:
            if capacities[t] == 0:
                continue
            best = (-weight / active_count * targets[t] ** power, 0)
            score = 0.0
            for k, p in enumerate(groups[t], 1):
                score += priority(p, policy)
                value = score - weight / active_count * abs(k / capacities[t] - targets[t]) ** power
                best = max(best, (value, k))
            chosen.update(p.id for p in groups[t][:best[1]])
        return chosen

    # Para k fixo, os k maiores escores da união dos prefixos limitados pelas
    # capacidades formam uma solução ótima. Examinar todos os k resolve a
    # penalização global (linear ou quadrática), sem solver externo.
    candidates = sorted((p for group in groups.values() for p in group),
                        key=lambda p: (-priority(p, policy), p.arrival_order, p.id))
    counts = dict.fromkeys(TYPES, 0)
    best = (-penalty(counts, capacities, targets, mode, weight, power), 0)
    score = 0.0
    for k, p in enumerate(candidates, 1):
        counts[p.bed_type] += 1
        score += priority(p, policy)
        best = max(best, (score - penalty(counts, capacities, targets, mode, weight, power), k))
    return {p.id for p in candidates[:best[1]]}


def stable_seed(seed, demand, replication, stream):
    raw = json.dumps([seed, demand, replication, stream]).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def generate(config, demand, replication):
    """Distribuições artificiais explícitas, sem conversão de SOFA."""
    rng = random.Random(stable_seed(config["seed"], demand, replication, "patients"))
    count = math.floor(demand * sum(config["capacities"].values()) + 0.5)
    patients = []
    for i in range(count):
        bed_type = rng.choices(TYPES, weights=[config["type_weights"][t] for t in TYPES])[0]
        p_out = rng.uniform(*config["p_out_range"])
        gain_fraction = rng.uniform(*config["gain_fraction_range"])
        patients.append(Patient(i, bed_type, p_out + (1 - p_out) * gain_fraction, p_out, i))
    outcome_rng = random.Random(stable_seed(config["seed"], demand, replication, "outcomes"))
    return patients, {p.id: outcome_rng.random() for p in patients}


def evaluate(patients, chosen, draws, capacities, targets, spec, policy):
    counts = {t: sum(p.id in chosen and p.bed_type == t for p in patients) for t in TYPES}
    expected = sum(p.p_in if p.id in chosen else p.p_out for p in patients)
    actual = sum(draws[p.id] < (p.p_in if p.id in chosen else p.p_out) for p in patients)
    loss = penalty(counts, capacities, targets, spec["mode"], spec["weight"], spec["power"])
    score = sum(priority(p, policy) for p in patients if p.id in chosen) if policy != "FCFS" else None
    result = {"patients": len(patients), "admitted": len(chosen), "expected_survivors": expected,
              "realized_survivors": actual, "expected_survival_fraction": expected / len(patients) if patients else None,
              "occupancy": len(chosen) / sum(capacities.values()) if sum(capacities.values()) else None,
              "penalty": loss, "policy_score": score,
              "penalized_objective": (score + (sum(p.p_out for p in patients) if policy == "MGS" else 0) - loss) if score is not None else None,
              "admitted_ids": json.dumps(sorted(chosen))}
    for t in TYPES:
        result[f"admitted_{t}"] = counts[t]
        result[f"occupancy_{t}"] = counts[t] / capacities[t] if capacities[t] else None
    return result


def interval(values):
    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else None
    return {"n": len(values), "mean": mean, "standard_error": se,
            "ci95_low": mean - 1.96 * se if se is not None else None,
            "ci95_high": mean + 1.96 * se if se is not None else None}


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_config(config):
    validate([], config["capacities"])
    if sum(config["capacities"].values()) == 0:
        raise ValueError("Experimento exige capacidade total positiva")
    if type(config["replications"]) is not int or config["replications"] < 2:
        raise ValueError("Use pelo menos duas replicações")
    if not config["demand_ratios"] or len(set(config["demand_ratios"])) != len(config["demand_ratios"]):
        raise ValueError("Razões de demanda devem ser não vazias e distintas")
    if any(not math.isfinite(d) or d <= 0 for d in config["demand_ratios"]):
        raise ValueError("Razão de demanda deve ser positiva e finita")
    for key in ("p_out_range", "gain_fraction_range"):
        if len(config[key]) != 2 or not 0 <= config[key][0] <= config[key][1] <= 1:
            raise ValueError(f"Intervalo inválido: {key}")
    weights = [config["type_weights"][t] for t in TYPES]
    if any(not math.isfinite(w) or w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("Pesos de tipos inválidos")
    specs = config["penalties"]
    if not specs or len({s["id"] for s in specs}) != len(specs):
        raise ValueError("Identificadores de configurações devem ser únicos")
    for spec in specs:
        allocate([], config["capacities"], "MGS", config["targets"], spec["mode"], spec["weight"], spec["power"])


def run(config, destination):
    validate_config(config)
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Diretório de saída deve estar vazio para preservar resultados anteriores")
    destination.mkdir(parents=True, exist_ok=True)
    rows, input_rows = [], []
    for demand in config["demand_ratios"]:
        for replication in range(config["replications"]):
            patients, draws = generate(config, demand, replication)
            for p in patients:
                input_rows.append({"demand_ratio": demand, "replication": replication, **asdict(p), "outcome_uniform": draws[p.id]})
            for spec in config["penalties"]:
                for policy in POLICIES:
                    chosen = allocate(patients, config["capacities"], policy, config["targets"], spec["mode"], spec["weight"], spec["power"])
                    rows.append({"demand_ratio": demand, "replication": replication, "penalty_id": spec["id"], "policy": policy,
                                 **evaluate(patients, chosen, draws, config["capacities"], config["targets"], spec, policy)})
    write_csv(destination / "runs.csv", rows)
    if input_rows:
        write_csv(destination / "patients.csv", input_rows)
    summary, paired = [], []
    index = {(r["demand_ratio"], r["replication"], r["penalty_id"], r["policy"]): r for r in rows}
    for demand in config["demand_ratios"]:
        for spec in config["penalties"]:
            for policy in POLICIES:
                for metric in ("expected_survivors", "realized_survivors", "admitted", "occupancy"):
                    values = [index[demand, r, spec["id"], policy][metric] for r in range(config["replications"])]
                    summary.append({"demand_ratio": demand, "penalty_id": spec["id"], "policy": policy, "metric": metric, **interval(values)})
                    if policy != "MGS":
                        differences = [index[demand, r, spec["id"], "MGS"][metric] - index[demand, r, spec["id"], policy][metric] for r in range(config["replications"])]
                        paired.append({"demand_ratio": demand, "penalty_id": spec["id"], "contrast": f"MGS-{policy}", "metric": metric, **interval(differences)})
    write_csv(destination / "summary.csv", summary)
    write_csv(destination / "paired_differences.csv", paired)
    (destination / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    metadata = {"data_kind": "synthetic_not_clinically_calibrated", "model": "static_exclusive_compatibility_v1",
                "python": sys.version, "platform": platform.platform(),
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "confidence_interval": "normal approximation mean +/- 1.96*SE across independent replications; exploratory, no multiplicity adjustment",
                "fcfs": "capacity-only baseline; ignores occupancy penalty when admitting; repeated unchanged across penalty settings",
                "outputs_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.iterdir()) if p.is_file()}}
    (destination / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = run(json.loads(args.config.read_text()), args.output)
    print(f"{count} avaliações sintéticas gravadas em {args.output}")


if __name__ == "__main__":
    main()
