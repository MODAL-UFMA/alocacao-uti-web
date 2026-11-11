"""Simulação dinâmica de eventos discretos para alocação de leitos de UTI multi-tipo.

Incorpora:
- 4 tipos de leitos calibrados pelo CNES/HU-UFMA (Neonatal, Pediátrico, Adulto, Coronariana/UCO)
- Acoplamento entre leitos adultos e coronarianos (transbordamento/overflow flexível)
- Deterioração clínica do paciente durante a espera na fila (P_in decresce com o tempo de espera)
- Tempo de permanência (LOS) estocástico (Log-Normal) correlacionado com a gravidade do paciente
- Período de aquecimento (warm-up) e cálculo rigoroso da taxa de ocupação segundo a Lei de Little
- Políticas de triagem concorrentes: FCFS, LSF, MSF, MGS, cμ-MGS e AUSTERE (Deadline-Aware)
- Avaliação sob ruído de observação clínica (informação imperfeita em ΔP)
- Números Aleatórios Comuns (CRN) pareados com intervalos de confiança e correção de Holm-Bonferroni
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import platform
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

TYPES = ("neonatal", "pediatric", "adult", "coronary")
POLICIES = ("FCFS", "LSF", "MSF", "MGS", "CMU_MGS", "AUSTERE")


@dataclass(frozen=True)
class DynamicPatient:
    id: int
    bed_type: str              # Tipo primário de leito: neonatal, pediatric, adult, coronary
    arrival_time: float        # Tempo de chegada no sistema (dias)
    p_out: float               # Sobrevivência basal na enfermaria / sem UTI [0.05, 0.65]
    p_in_0: float              # Sobrevivência inicial imediata se admitido no tempo 0
    los: float                 # Tempo de permanência efetivo (dias)
    expected_los: float        # E[LOS] esperado para cálculo de índices cμ
    max_wait: float            # Tolerância máxima na fila antes de abandono/óbito (dias)
    outcome_uniform: float     # Semente uniforme para realização de sobrevivência
    delta_p_noise: float       # Ruído de observação clínica ~ N(0, sigma^2)
    can_overflow: bool = False # Se paciente adulto pode transbordar para UCO ou vice-versa

    @property
    def initial_gain(self) -> float:
        return self.p_in_0 - self.p_out

    def p_in_at(self, current_time: float, alpha_det: float) -> float:
        """Calcula P_in(w) com decaimento exponencial por deterioração clínica na fila."""
        wait = max(0.0, current_time - self.arrival_time)
        return self.p_out + (self.p_in_0 - self.p_out) * math.exp(-alpha_det * wait)

    def marginal_gain_at(self, current_time: float, alpha_det: float, with_noise: bool = False) -> float:
        """Calcula ganho marginal delta P(w). Se with_noise=True, adiciona erro de estimação clínica."""
        gain = self.p_in_at(current_time, alpha_det) - self.p_out
        if with_noise:
            gain = max(0.0, min(1.0, gain + self.delta_p_noise))
        return gain


def priority_score(
    p: DynamicPatient,
    policy: str,
    current_time: float,
    alpha_det: float,
    with_noise: bool = False,
) -> float:
    """Calcula o escore de prioridade dinâmico do paciente sob a política avaliada."""
    if policy == "FCFS":
        # Prioridade estritamente cronológica: mais antigo na fila primeiro
        return -p.arrival_time

    if policy == "LSF":
        # Least Serious First: maior probabilidade de sobrevida absoluta
        return p.p_in_at(current_time, alpha_det)

    if policy == "MSF":
        # Most Serious First: menor sobrevida basal (Regra do Resgate / Maior gravidade)
        return 1.0 - p.p_out

    delta_p = p.marginal_gain_at(current_time, alpha_det, with_noise=with_noise)

    if policy == "MGS":
        # Maximizing Survival Gain: maior ganho marginal imediato
        return delta_p

    if policy == "CMU_MGS":
        # Regra cμ adaptada à UTI: ganho marginal por dia de leito consumido
        return delta_p / max(0.1, p.expected_los)

    if policy == "AUSTERE":
        # Política para condições austeras (Sun, Argon & Ziya, 2018):
        # Combina benefício/leito-dia ponderado pela proximidade do deadline de abandono
        time_left = max(0.05, (p.arrival_time + p.max_wait) - current_time)
        urgency_weight = 1.0 + (1.0 / time_left)
        return (delta_p / max(0.1, p.expected_los)) * urgency_weight

    raise ValueError(f"Política desconhecida: {policy}")


def stable_seed(seed: int, demand: float, replication: int, stream: str) -> int:
    raw = json.dumps([seed, round(demand, 4), replication, stream]).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def generate_patient_stream(
    config: dict,
    demand_ratio: float,
    replication: int,
    sigma_noise: float = 0.0,
) -> list[DynamicPatient]:
    """Gera o fluxo de pacientes com chegadas de Poisson e sementes independentes por fluxo."""
    seed_base = config["seed"]
    rng_arr = random.Random(stable_seed(seed_base, demand_ratio, replication, "arrivals"))
    rng_cli = random.Random(stable_seed(seed_base, demand_ratio, replication, "clinical"))
    rng_los = random.Random(stable_seed(seed_base, demand_ratio, replication, "los"))
    rng_out = random.Random(stable_seed(seed_base, demand_ratio, replication, "outcomes"))
    rng_noi = random.Random(stable_seed(seed_base, demand_ratio, replication, "noise"))

    horizon_total = float(config.get("horizon_days", 75.0))
    mean_los_base = float(config.get("mean_los_days", 5.0))
    cv_los = float(config.get("cv_los", 0.6))
    sigma_los = math.sqrt(math.log(1.0 + cv_los**2))

    capacities = config["capacities"]
    p_out_range = config.get("p_out_range", [0.05, 0.65])
    gain_range = config.get("gain_fraction_range", [0.10, 0.80])
    max_wait_range = config.get("max_wait_range", [1.0, 3.0])
    sev_los_beta = float(config.get("sev_los_beta", 0.8))  # Impacto da gravidade no LOS

    patients = []
    patient_id = 0

    for btype in TYPES:
        cap = capacities.get(btype, 0)
        if cap <= 0:
            continue

        # Taxa de chegada ajustada por Little's Law para a capacidade nominal do pool
        arrival_rate = (demand_ratio * cap) / mean_los_base
        t = rng_arr.expovariate(arrival_rate)

        while t < horizon_total:
            p_out = rng_cli.uniform(*p_out_range)
            gain_fraction = rng_cli.uniform(*gain_range)
            p_in_0 = p_out + (1.0 - p_out) * gain_fraction
            max_wait = rng_cli.uniform(*max_wait_range)

            # E[LOS] dependente da gravidade do paciente (1 - p_out): pacientes mais graves ficam mais tempo
            # Normalizado para manter a média global próxima a mean_los_base
            severity = 1.0 - p_out
            expected_patient_los = mean_los_base * (0.6 + sev_los_beta * severity)
            mu_i = math.log(expected_patient_los) - 0.5 * sigma_los**2
            los = rng_los.lognormvariate(mu_i, sigma_los)

            outcome_u = rng_out.random()
            noise = rng_noi.gauss(0.0, sigma_noise) if sigma_noise > 0.0 else 0.0

            # Pacientes adultos ou coronarianos possuem acoplamento potencial para overflow
            can_overflow = btype in ("adult", "coronary")

            patients.append(
                DynamicPatient(
                    id=patient_id,
                    bed_type=btype,
                    arrival_time=t,
                    p_out=p_out,
                    p_in_0=p_in_0,
                    los=los,
                    expected_los=expected_patient_los,
                    max_wait=max_wait,
                    outcome_uniform=outcome_u,
                    delta_p_noise=noise,
                    can_overflow=can_overflow,
                )
            )
            patient_id += 1
            t += rng_arr.expovariate(arrival_rate)

    patients.sort(key=lambda p: (p.arrival_time, p.id))
    return patients


@dataclass
class SimulationEvent:
    time: float
    event_type: str  # "ARRIVAL", "DISCHARGE", "TIMEOUT"
    patient_id: int
    bed_type: str
    assigned_pool: str = ""

    def __lt__(self, other: SimulationEvent) -> bool:
        return (self.time, self.event_type) < (other.time, other.event_type)


def simulate_policy(
    patients: list[DynamicPatient],
    capacities: dict[str, int],
    policy: str,
    warmup_days: float = 15.0,
    horizon_days: float = 75.0,
    alpha_det: float = 0.10,
    allow_overflow: bool = True,
    with_noise: bool = False,
) -> dict:
    """Executa a simulação de eventos discretos com janela de observação e warm-up."""
    patients_by_id = {p.id: p for p in patients}
    queues: dict[str, list[DynamicPatient]] = {t: [] for t in TYPES}
    occupied_beds: dict[str, int] = {t: 0 for t in TYPES}

    admitted_patients: set[int] = set()
    timeout_patients: set[int] = set()
    admission_times: dict[int, float] = {}
    admission_pool: dict[int, str] = {}
    wait_times: dict[int, float] = {}

    # Acúmulo de ocupação restrito à janela de avaliação [warmup_days, horizon_days]
    eval_start = warmup_days
    eval_end = horizon_days
    eval_duration = max(1e-6, eval_end - eval_start)

    last_time = 0.0
    accumulated_occupancy_area = {t: 0.0 for t in TYPES}

    def update_occupancy_area(new_time: float):
        nonlocal last_time
        if new_time <= eval_start:
            last_time = new_time
            return
        # Intervalo [t_prev, t_curr] interceptado com [eval_start, eval_end]
        t_from = max(eval_start, min(eval_end, last_time))
        t_to = max(eval_start, min(eval_end, new_time))
        dt = t_to - t_from
        if dt > 0:
            for t in TYPES:
                accumulated_occupancy_area[t] += occupied_beds[t] * dt
        last_time = new_time

    event_queue: list[SimulationEvent] = []
    for p in patients:
        heapq.heappush(
            event_queue,
            SimulationEvent(time=p.arrival_time, event_type="ARRIVAL", patient_id=p.id, bed_type=p.bed_type),
        )
        heapq.heappush(
            event_queue,
            SimulationEvent(
                time=p.arrival_time + p.max_wait,
                event_type="TIMEOUT",
                patient_id=p.id,
                bed_type=p.bed_type,
            ),
        )

    def select_best_patient(candidate_queue: list[DynamicPatient], now: float) -> DynamicPatient:
        if policy == "FCFS":
            return candidate_queue.pop(0)
        # Ordena por escore decrescente; desempate por tempo de chegada e id
        candidate_queue.sort(
            key=lambda p: (
                -priority_score(p, policy, now, alpha_det, with_noise),
                p.arrival_time,
                p.id,
            )
        )
        return candidate_queue.pop(0)

    def try_admit_for_pool(pool: str, now: float):
        """Tenta alocar leitos desocupados no pool especificado."""
        cap = capacities.get(pool, 0)
        while occupied_beds[pool] < cap:
            chosen = None
            # 1. Candidatos prioritários da fila do próprio pool
            if queues[pool]:
                chosen = select_best_patient(queues[pool], now)
            # 2. Acoplamento de overflow entre Adulto e Coronariana
            elif allow_overflow and pool == "coronary" and queues["adult"]:
                # Transbordamento de adulto para UCO se UCO tiver vaga livre
                chosen = select_best_patient(queues["adult"], now)
            elif allow_overflow and pool == "adult" and queues["coronary"]:
                # Transbordamento de coronariano para Adulto se Adulto tiver vaga livre
                chosen = select_best_patient(queues["coronary"], now)

            if chosen is None:
                break

            admitted_patients.add(chosen.id)
            admission_times[chosen.id] = now
            admission_pool[chosen.id] = pool
            wait_times[chosen.id] = now - chosen.arrival_time
            occupied_beds[pool] += 1

            discharge_time = now + chosen.los
            heapq.heappush(
                event_queue,
                SimulationEvent(
                    time=discharge_time,
                    event_type="DISCHARGE",
                    patient_id=chosen.id,
                    bed_type=chosen.bed_type,
                    assigned_pool=pool,
                ),
            )

    while event_queue:
        ev = heapq.heappop(event_queue)
        update_occupancy_area(ev.time)
        current_time = ev.time

        if ev.event_type == "ARRIVAL":
            p = patients_by_id[ev.patient_id]
            queues[ev.bed_type].append(p)
            try_admit_for_pool(ev.bed_type, current_time)
            # Se for adulto ou coronariano, tenta também pool acoplado
            if allow_overflow:
                if ev.bed_type == "adult" and ev.patient_id not in admitted_patients:
                    try_admit_for_pool("coronary", current_time)
                elif ev.bed_type == "coronary" and ev.patient_id not in admitted_patients:
                    try_admit_for_pool("adult", current_time)

        elif ev.event_type == "DISCHARGE":
            pool_freed = ev.assigned_pool or ev.bed_type
            occupied_beds[pool_freed] = max(0, occupied_beds[pool_freed] - 1)
            try_admit_for_pool(pool_freed, current_time)

        elif ev.event_type == "TIMEOUT":
            p = patients_by_id[ev.patient_id]
            if p.id not in admitted_patients and p.id not in timeout_patients:
                if p in queues[p.bed_type]:
                    queues[p.bed_type].remove(p)
                    timeout_patients.add(p.id)
                    wait_times[p.id] = p.max_wait

    update_occupancy_area(eval_end)

    # Filtragem estrita para a janela de avaliação [eval_start, eval_end]
    eval_patients = [p for p in patients if eval_start <= p.arrival_time < eval_end]
    total_eval = len(eval_patients)

    eval_admitted = [p for p in eval_patients if p.id in admitted_patients]
    eval_reneged = [p for p in eval_patients if p.id in timeout_patients]
    eval_unadmitted = [p for p in eval_patients if p.id not in admitted_patients]

    n_admitted = len(eval_admitted)
    n_reneged = len(eval_reneged)

    # Cálculo da sobrevida com decaimento exponencial por espera
    expected_survivors = sum(
        p.p_in_at(admission_times[p.id], alpha_det) if p.id in admitted_patients else p.p_out
        for p in eval_patients
    )
    realized_survivors = sum(
        p.outcome_uniform < (
            p.p_in_at(admission_times[p.id], alpha_det) if p.id in admitted_patients else p.p_out
        )
        for p in eval_patients
    )

    wait_admitted_list = [wait_times.get(p.id, 0.0) for p in eval_admitted]
    wait_reneged_list = [wait_times.get(p.id, p.max_wait) for p in eval_reneged]
    wait_all_list = [wait_times.get(p.id, p.max_wait) for p in eval_patients]

    mean_wait_admitted_h = statistics.mean(wait_admitted_list) * 24.0 if wait_admitted_list else 0.0
    mean_wait_reneged_h = statistics.mean(wait_reneged_list) * 24.0 if wait_reneged_list else 0.0
    mean_wait_all_h = statistics.mean(wait_all_list) * 24.0 if wait_all_list else 0.0

    total_capacity = sum(capacities.values())
    occupancy_rates = {}
    for t in TYPES:
        cap = capacities.get(t, 0)
        occupancy_rates[t] = (
            accumulated_occupancy_area[t] / (eval_duration * cap) if cap > 0 else 0.0
        )
    global_occupancy = (
        sum(accumulated_occupancy_area.values()) / (eval_duration * total_capacity)
        if total_capacity > 0
        else 0.0
    )

    # Métricas desagregadas por pool
    pool_metrics = {}
    for t in TYPES:
        sub_pts = [p for p in eval_patients if p.bed_type == t]
        sub_adm = [p for p in sub_pts if p.id in admitted_patients]
        pool_metrics[f"patients_{t}"] = len(sub_pts)
        pool_metrics[f"admitted_{t}"] = len(sub_adm)
        pool_metrics[f"admission_rate_{t}"] = len(sub_adm) / len(sub_pts) if sub_pts else 0.0
        pool_metrics[f"occupancy_{t}"] = occupancy_rates[t]

    return {
        "policy": policy,
        "total_patients": total_eval,
        "admitted": n_admitted,
        "reneged": n_reneged,
        "admission_rate": n_admitted / total_eval if total_eval else 0.0,
        "reneging_rate": n_reneged / total_eval if total_eval else 0.0,
        "expected_survivors": expected_survivors,
        "realized_survivors": realized_survivors,
        "expected_survival_rate": expected_survivors / total_eval if total_eval else 0.0,
        "realized_survival_rate": realized_survivors / total_eval if total_eval else 0.0,
        "mean_wait_admitted_hours": mean_wait_admitted_h,
        "mean_wait_reneged_hours": mean_wait_reneged_h,
        "mean_wait_all_hours": mean_wait_all_h,
        "mean_occupancy_global": global_occupancy,
        **pool_metrics,
    }


def interval(values: list[float]) -> dict:
    n = len(values)
    mean = statistics.mean(values) if n > 0 else 0.0
    se = statistics.stdev(values) / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n,
        "mean": mean,
        "standard_error": se,
        "ci95_low": mean - 1.96 * se,
        "ci95_high": mean + 1.96 * se,
    }


def student_t_pvalue(t_stat: float, df: int) -> float:
    """Aproximação precisa do p-valor bilateral para distribuição t de Student."""
    if df <= 0 or math.isnan(t_stat):
        return 1.0
    x = df / (df + t_stat**2)
    # Aproximação da função beta incompleta regularizada I_x(a, b)
    # Para df grande (ex: df=99), aproximação padrão normal via math.erfc
    if df >= 30:
        z = abs(t_stat) * (1.0 - 1.0 / (4.0 * df))
        return math.erfc(z / math.sqrt(2.0))
    # Para df pequeno: fallback normal
    return math.erfc(abs(t_stat) / math.sqrt(2.0))


def run_dynamic_experiment(config: dict, destination: str | Path):
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)

    runs_rows = []
    paired_rows = []

    demand_ratios = config.get("demand_ratios", [0.7, 1.0, 1.3, 1.6])
    replications = config.get("replications", 100)
    capacities = config["capacities"]
    warmup_days = float(config.get("warmup_days", 15.0))
    horizon_days = float(config.get("horizon_days", 75.0))
    alpha_det = float(config.get("alpha_det", 0.10))
    allow_overflow = bool(config.get("allow_overflow", True))
    policies = config.get("policies", list(POLICIES))

    print(
        f"Iniciando simulação dinâmica: {len(demand_ratios)} demandas x {replications} "
        f"replicações x {len(policies)} políticas (Janela {horizon_days - warmup_days}d pós {warmup_days}d warm-up)..."
    )

    for d in demand_ratios:
        for rep in range(replications):
            patients = generate_patient_stream(config, d, rep)

            rep_results = {}
            for pol in policies:
                res = simulate_policy(
                    patients=patients,
                    capacities=capacities,
                    policy=pol,
                    warmup_days=warmup_days,
                    horizon_days=horizon_days,
                    alpha_det=alpha_det,
                    allow_overflow=allow_overflow,
                    with_noise=False,
                )
                res["demand_ratio"] = d
                res["replication"] = rep
                runs_rows.append(res)
                rep_results[pol] = res

            fcfs_exp = rep_results["FCFS"]["expected_survivors"]
            fcfs_real = rep_results["FCFS"]["realized_survivors"]
            fcfs_wait_adm = rep_results["FCFS"]["mean_wait_admitted_hours"]
            fcfs_wait_all = rep_results["FCFS"]["mean_wait_all_hours"]

            for pol in policies:
                if pol == "FCFS":
                    continue
                paired_rows.append({
                    "demand_ratio": d,
                    "replication": rep,
                    "policy": pol,
                    "baseline": "FCFS",
                    "diff_expected_survivors": rep_results[pol]["expected_survivors"] - fcfs_exp,
                    "diff_realized_survivors": rep_results[pol]["realized_survivors"] - fcfs_real,
                    "diff_wait_admitted_hours": rep_results[pol]["mean_wait_admitted_hours"] - fcfs_wait_adm,
                    "diff_wait_all_hours": rep_results[pol]["mean_wait_all_hours"] - fcfs_wait_all,
                })

    with (dest / "runs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(runs_rows[0].keys()))
        writer.writeheader()
        writer.writerows(runs_rows)

    if paired_rows:
        with (dest / "paired_differences.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(paired_rows[0].keys()))
            writer.writeheader()
            writer.writerows(paired_rows)

    summary_rows = []
    metrics = (
        "expected_survivors",
        "realized_survivors",
        "admitted",
        "reneged",
        "admission_rate",
        "reneging_rate",
        "expected_survival_rate",
        "realized_survival_rate",
        "mean_wait_admitted_hours",
        "mean_wait_reneged_hours",
        "mean_wait_all_hours",
        "mean_occupancy_global",
        "occupancy_adult",
        "occupancy_coronary",
        "occupancy_pediatric",
        "occupancy_neonatal",
    )
    for d in demand_ratios:
        for pol in policies:
            pol_runs = [r for r in runs_rows if r["demand_ratio"] == d and r["policy"] == pol]
            for m in metrics:
                if m in pol_runs[0]:
                    vals = [r[m] for r in pol_runs]
                    stats = interval(vals)
                    summary_rows.append({
                        "demand_ratio": d,
                        "policy": pol,
                        "metric": m,
                        **stats,
                    })

    with (dest / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    # Tabela pareada com Holm-Bonferroni
    paired_summary = []
    raw_tests = []
    for d in demand_ratios:
        for pol in policies:
            if pol == "FCFS":
                continue
            sub_diffs = [
                r["diff_expected_survivors"]
                for r in paired_rows
                if r["demand_ratio"] == d and r["policy"] == pol
            ]
            fcfs_runs = [r["expected_survivors"] for r in runs_rows if r["demand_ratio"] == d and r["policy"] == "FCFS"]
            fcfs_mean = statistics.mean(fcfs_runs)
            stats = interval(sub_diffs)
            t_stat = stats["mean"] / stats["standard_error"] if stats["standard_error"] > 0 else 0.0
            p_val = student_t_pvalue(t_stat, len(sub_diffs) - 1)
            pct_gain = (stats["mean"] / fcfs_mean * 100.0) if fcfs_mean > 0 else 0.0

            raw_tests.append({
                "demand_ratio": d,
                "policy": pol,
                "diff_mean": stats["mean"],
                "se": stats["standard_error"],
                "ci95_low": stats["ci95_low"],
                "ci95_high": stats["ci95_high"],
                "t_stat": t_stat,
                "p_raw": p_val,
                "relative_pct": pct_gain,
            })

    # Correção de Holm-Bonferroni sobre todos os testes de hipótese pareados
    raw_tests.sort(key=lambda x: x["p_raw"])
    m_tests = len(raw_tests)
    for rank, test in enumerate(raw_tests):
        adjusted_p = min(1.0, test["p_raw"] * (m_tests - rank))
        paired_summary.append({
            **test,
            "p_holm": adjusted_p,
            "significant_005": adjusted_p < 0.05,
        })
    paired_summary.sort(key=lambda x: (x["demand_ratio"], x["policy"]))

    with (dest / "paired_statistical_summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(paired_summary[0].keys()))
        writer.writeheader()
        writer.writerows(paired_summary)

    # Salva configuração e metadados
    (dest / "config.json").write_text(json.dumps(config, indent=2))
    metadata = {
        "platform": platform.platform(),
        "python_version": sys.version,
        "capacities": capacities,
        "total_evaluations": len(runs_rows),
        "warmup_days": warmup_days,
        "horizon_days": horizon_days,
        "effective_observation_window_days": horizon_days - warmup_days,
    }
    (dest / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Simulação concluída com sucesso. Resultados salvos em {dest}")


def run_sensitivity_experiment(config: dict, destination: str | Path):
    """Executa análise de sensibilidade variando ruído clínico, deterioração e LOS."""
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)

    noise_levels = [0.0, 0.05, 0.10, 0.20]
    sens_rows = []

    print(f"Iniciando análise de sensibilidade ao ruído de estimação clínica (sigma in {noise_levels})...")
    d = 1.6  # Cenário de escassez crítica
    replications = 50

    for sigma in noise_levels:
        for rep in range(replications):
            patients = generate_patient_stream(config, d, rep, sigma_noise=sigma)
            for pol in ("MGS", "CMU_MGS", "AUSTERE", "FCFS"):
                res = simulate_policy(
                    patients=patients,
                    capacities=config["capacities"],
                    policy=pol,
                    warmup_days=config.get("warmup_days", 15.0),
                    horizon_days=config.get("horizon_days", 75.0),
                    alpha_det=config.get("alpha_det", 0.10),
                    allow_overflow=True,
                    with_noise=(sigma > 0.0),
                )
                sens_rows.append({
                    "sigma_noise": sigma,
                    "replication": rep,
                    "policy": pol,
                    "expected_survivors": res["expected_survivors"],
                    "admitted": res["admitted"],
                    "mean_occupancy_global": res["mean_occupancy_global"],
                })

    with (dest / "sensitivity_noise.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(sens_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sens_rows)

    print(f"Análise de sensibilidade gravada em {dest / 'sensitivity_noise.csv'}")


def main():
    parser = argparse.ArgumentParser(description="Simulação Dinâmica de Leitos de UTI Multi-Tipo")
    parser.add_argument("--config", required=True, help="Caminho para o JSON de configuração")
    parser.add_argument("--output", required=True, help="Diretório de saída dos resultados")
    parser.add_argument("--sensitivity", action="store_true", help="Executa também análise de sensibilidade")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    run_dynamic_experiment(config, args.output)
    if args.sensitivity:
        run_sensitivity_experiment(config, Path(args.output) / "sensitivity")


if __name__ == "__main__":
    main()
