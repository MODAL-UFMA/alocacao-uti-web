"""Simulação dinâmica de eventos discretos para alocação de leitos de UTI multi-tipo.

Calibração empírica baseada em registros nacionais brasileiros:
- Capacidade física: DATASUS / CNES (HU-UFMA, competência 12/2024: 55 leitos em 4 pools)
- Tempo de permanência (LOS) e mortalidade basal: Registro Nacional UTIs Brasileiras (AMIB / Epimed,
  Soares et al., 2024; Zampieri et al., 2019), Rede Brasileira de Pesquisas Neonatais (Guinsburg et al., 2016)
  e coorte brasileira de atraso na admissão em UTI (Cardoso et al., 2011).

Políticas e Benchmarks:
- FCFS: First-Come, First-Served
- MSF: Most Serious First (maior risco basal de óbito 1 - P_out)
- LSF: Least Serious First (maior probabilidade absoluta de sobrevida P_in(w))
- MGS: Marginal Gain in Survival (maior ganho marginal imediato ΔP(w))
- CMU_MGS: Regra cμ adaptada (ΔP(w) / E[LOS])
- AUSTERE: Índice de perda marginal por deterioração e abandono (Sun, Argon & Ziya, 2018)
- OFFLINE_UB: Limitante superior clarividente (MILP indexado no tempo via HiGHS)
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

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csc_matrix

TYPES = ("neonatal", "pediatric", "adult", "coronary")
POLICIES = ("FCFS", "LSF", "MSF", "MGS", "CMU_MGS", "AUSTERE")

# Perfis epidemiológicos empíricos por especialidade (AMIB/Epimed, RBPN, Cardoso et al.)
DEFAULT_POOL_PROFILES = {
    "adult": {
        "mean_los_days": 6.5,
        "cv_los": 0.65,
        "p_out_range": [0.10, 0.55],
        "gain_fraction_range": [0.25, 0.75],
        "max_wait_range": [0.5, 2.5],
        "alpha_det": 0.18,
    },
    "coronary": {
        "mean_los_days": 4.8,
        "cv_los": 0.55,
        "p_out_range": [0.20, 0.65],
        "gain_fraction_range": [0.30, 0.80],
        "max_wait_range": [0.5, 2.0],
        "alpha_det": 0.20,
    },
    "pediatric": {
        "mean_los_days": 6.0,
        "cv_los": 0.65,
        "p_out_range": [0.25, 0.70],
        "gain_fraction_range": [0.35, 0.85],
        "max_wait_range": [0.5, 2.5],
        "alpha_det": 0.15,
    },
    "neonatal": {
        "mean_los_days": 11.5,
        "cv_los": 0.75,
        "p_out_range": [0.15, 0.65],
        "gain_fraction_range": [0.30, 0.85],
        "max_wait_range": [0.5, 2.0],
        "alpha_det": 0.20,
    },
}


@dataclass(frozen=True)
class DynamicPatient:
    id: int
    bed_type: str
    arrival_time: float
    p_out: float
    p_in_0: float
    los: float
    expected_los: float
    max_wait: float
    alpha_det: float
    outcome_uniform: float
    # Atributos observados com ruído clínico (para análise de informação imperfeita - M6)
    obs_p_out: float
    obs_p_in_0: float
    obs_expected_los: float
    can_overflow: bool = False

    def p_in_at(self, current_time: float, use_observed: bool = False) -> float:
        """Calcula P_in(w) com decaimento exponencial por deterioração clínica na fila."""
        wait = max(0.0, current_time - self.arrival_time)
        base_out = self.obs_p_out if use_observed else self.p_out
        base_in0 = self.obs_p_in_0 if use_observed else self.p_in_0
        return base_out + (base_in0 - base_out) * math.exp(-self.alpha_det * wait)

    def marginal_gain_at(self, current_time: float, use_observed: bool = False) -> float:
        """Calcula ganho marginal ΔP(w) = P_in(w) - P_out."""
        base_out = self.obs_p_out if use_observed else self.p_out
        return max(0.0, self.p_in_at(current_time, use_observed=use_observed) - base_out)


def priority_score(
    p: DynamicPatient,
    policy: str,
    current_time: float,
    use_observed: bool = False,
) -> float:
    """Calcula o escore de prioridade dinâmico do paciente sob a política avaliada."""
    if policy == "FCFS":
        return -p.arrival_time

    if policy == "LSF":
        return p.p_in_at(current_time, use_observed=use_observed)

    if policy == "MSF":
        p_out_val = p.obs_p_out if use_observed else p.p_out
        return 1.0 - p_out_val

    delta_p = p.marginal_gain_at(current_time, use_observed=use_observed)
    e_los = p.obs_expected_los if use_observed else p.expected_los
    e_los = max(0.2, e_los)

    if policy == "MGS":
        return delta_p

    if policy == "CMU_MGS":
        return delta_p / e_los

    if policy == "AUSTERE":
        # Regra fundamentada em Sun, Argon & Ziya (2018):
        # Taxa de perda marginal esperada por atraso (deterioração contínua + risco de abandono)
        # Normalizada pelo tempo esperado de ocupação do leito E[LOS].
        wait = max(0.0, current_time - p.arrival_time)
        rem_wait = max(0.25, p.max_wait - wait)
        # Taxa instantânea de perda de sobrevida se postergado: alpha_det * delta_p + delta_p / (rem_wait + 1.0)
        urgency_multiplier = 1.0 + p.alpha_det + (0.5 / (rem_wait + 0.5))
        return (delta_p / e_los) * urgency_multiplier

    raise ValueError(f"Política desconhecida: {policy}")


def stable_seed(seed: int, demand: float, replication: int, stream: str) -> int:
    raw = json.dumps([seed, round(demand, 4), replication, stream]).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def get_pool_profile(config: dict, btype: str) -> dict:
    """Retorna os parâmetros calibrados para o pool específico."""
    profiles = config.get("pool_profiles", DEFAULT_POOL_PROFILES)
    prof = dict(DEFAULT_POOL_PROFILES.get(btype, DEFAULT_POOL_PROFILES["adult"]))
    if btype in profiles:
        prof.update(profiles[btype])
    # Sobrescritas globais opcionais (para varreduras de sensibilidade M3)
    if "override_alpha_det" in config:
        prof["alpha_det"] = float(config["override_alpha_det"])
    if "override_cv_los" in config:
        prof["cv_los"] = float(config["override_cv_los"])
    if "override_max_wait_scale" in config:
        scale = float(config["override_max_wait_scale"])
        prof["max_wait_range"] = [prof["max_wait_range"][0] * scale, prof["max_wait_range"][1] * scale]
    return prof


def generate_patient_stream(
    config: dict,
    demand_ratio: float,
    replication: int,
    sigma_noise: float = 0.0,
) -> list[DynamicPatient]:
    """Gera o fluxo de pacientes com chegadas de Poisson exatas em relação ao E[LOS] efetivo (M2)."""
    seed_base = config["seed"]
    rng_arr = random.Random(stable_seed(seed_base, demand_ratio, replication, "arrivals"))
    rng_cli = random.Random(stable_seed(seed_base, demand_ratio, replication, "clinical"))
    rng_los = random.Random(stable_seed(seed_base, demand_ratio, replication, "los"))
    rng_out = random.Random(stable_seed(seed_base, demand_ratio, replication, "outcomes"))
    rng_noi = random.Random(stable_seed(seed_base, demand_ratio, replication, "noise"))

    horizon_total = float(config.get("horizon_days", 75.0))
    sev_los_beta = float(config.get("sev_los_beta", 1.2))
    capacities = config["capacities"]

    patients = []
    patient_id = 0

    for btype in TYPES:
        cap = capacities.get(btype, 0)
        if cap <= 0:
            continue

        prof = get_pool_profile(config, btype)
        mean_los_pool = float(prof["mean_los_days"])
        cv_los = float(prof["cv_los"])
        sigma_los = math.sqrt(math.log(1.0 + cv_los**2))
        p_out_low, p_out_high = prof["p_out_range"]
        gain_low, gain_high = prof["gain_fraction_range"]
        wait_low, wait_high = prof["max_wait_range"]
        alpha_det = float(prof["alpha_det"])

        # Média da gravidade (1 - P_out) para normalização exata de E[LOS_i] = mean_los_pool (Resolve M2!)
        mean_severity = 1.0 - 0.5 * (p_out_low + p_out_high)

        # Taxa de chegada exata por Little's Law: rho_efetivo == demand_ratio
        arrival_rate = (demand_ratio * cap) / mean_los_pool
        t = rng_arr.expovariate(arrival_rate)

        while t < horizon_total:
            p_out = rng_cli.uniform(p_out_low, p_out_high)
            gain_fraction = rng_cli.uniform(gain_low, gain_high)
            p_in_0 = p_out + (1.0 - p_out) * gain_fraction
            max_wait = rng_cli.uniform(wait_low, wait_high)

            # E[LOS_i] cresce com a gravidade (1 - p_out), mas normalizado para que E[E[LOS_i]] == mean_los_pool
            severity = 1.0 - p_out
            raw_mult = 1.0 + sev_los_beta * (severity - mean_severity)
            mult = max(0.35, raw_mult)
            expected_patient_los = mean_los_pool * mult

            mu_i = math.log(expected_patient_los) - 0.5 * sigma_los**2
            los = rng_los.lognormvariate(mu_i, sigma_los)
            outcome_u = rng_out.random()

            # Geração de atributos observados com ruído para todas as variáveis clínicas (Resolve M6!)
            if sigma_noise > 0.0:
                obs_p_out = min(0.95, max(0.01, p_out + rng_noi.gauss(0.0, sigma_noise)))
                obs_p_in_0 = min(0.99, max(obs_p_out, p_in_0 + rng_noi.gauss(0.0, sigma_noise)))
                los_noise_mult = max(0.4, 1.0 + rng_noi.gauss(0.0, sigma_noise))
                obs_expected_los = expected_patient_los * los_noise_mult
            else:
                obs_p_out = p_out
                obs_p_in_0 = p_in_0
                obs_expected_los = expected_patient_los

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
                    alpha_det=alpha_det,
                    outcome_uniform=outcome_u,
                    obs_p_out=obs_p_out,
                    obs_p_in_0=obs_p_in_0,
                    obs_expected_los=obs_expected_los,
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
    allow_overflow: bool = True,
    with_noise: bool = False,
) -> dict:
    """Executa a simulação de eventos discretos sem truncar pacientes na fila em T (Resolve M7 e M8)."""
    patients_by_id = {p.id: p for p in patients}
    queues: dict[str, list[DynamicPatient]] = {t: [] for t in TYPES}
    occupied_beds: dict[str, int] = {t: 0 for t in TYPES}

    admitted_patients: set[int] = set()
    timeout_patients: set[int] = set()
    admission_times: dict[int, float] = {}
    admission_pool: dict[int, str] = {}
    wait_times: dict[int, float] = {}

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
        candidate_queue.sort(
            key=lambda p: (
                -priority_score(p, policy, now, use_observed=with_noise),
                p.arrival_time,
                p.id,
            )
        )
        return candidate_queue.pop(0)

    def try_admit_for_pool(pool: str, now: float):
        """Aloca leitos livres no pool com prioridade primária para a fila nativa e overflow secundário (M8)."""
        cap = capacities.get(pool, 0)
        while occupied_beds[pool] < cap:
            chosen = None
            # Regra hierárquica estrita (M8):
            # 1. Atende sempre os pacientes da própria especialidade primeiro
            if queues[pool]:
                chosen = select_best_patient(queues[pool], now)
            # 2. Somente se a fila nativa estiver vazia, aceita transbordamento compatível (Adulto <-> UCO)
            elif allow_overflow and pool == "coronary" and queues["adult"]:
                chosen = select_best_patient(queues["adult"], now)
            elif allow_overflow and pool == "adult" and queues["coronary"]:
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

    # Processa todos os eventos até o esvaziamento completo das filas da coorte (Resolve M7!)
    while event_queue:
        ev = heapq.heappop(event_queue)
        update_occupancy_area(ev.time)
        current_time = ev.time

        if ev.event_type == "ARRIVAL":
            p = patients_by_id[ev.patient_id]
            queues[ev.bed_type].append(p)
            try_admit_for_pool(ev.bed_type, current_time)
            if allow_overflow and ev.patient_id not in admitted_patients:
                if ev.bed_type == "adult":
                    try_admit_for_pool("coronary", current_time)
                elif ev.bed_type == "coronary":
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

    # Coorte de avaliação: todos os pacientes que chegaram em [warmup_days, horizon_days)
    eval_patients = [p for p in patients if eval_start <= p.arrival_time < eval_end]
    total_eval = len(eval_patients)

    eval_admitted = [p for p in eval_patients if p.id in admitted_patients]
    eval_reneged = [p for p in eval_patients if p.id in timeout_patients]

    n_admitted = len(eval_admitted)
    n_reneged = len(eval_reneged)

    # Sobrevivência calculada sempre com os parâmetros reais (verdade-terreno) do paciente
    expected_survivors = sum(
        p.p_in_at(admission_times[p.id], use_observed=False) if p.id in admitted_patients else p.p_out
        for p in eval_patients
    )
    realized_survivors = sum(
        p.outcome_uniform < (
            p.p_in_at(admission_times[p.id], use_observed=False) if p.id in admitted_patients else p.p_out
        )
        for p in eval_patients
    )

    wait_admitted_list = [wait_times.get(p.id, 0.0) for p in eval_admitted]
    wait_reneged_list = [wait_times.get(p.id, p.max_wait) for p in eval_reneged]
    wait_all_list = [wait_times.get(p.id, p.max_wait) for p in eval_patients]

    mean_wait_admitted_h = statistics.mean(wait_admitted_list) * 24.0 if wait_admitted_list else 0.0
    mean_wait_reneged_h = statistics.mean(wait_reneged_list) * 24.0 if wait_reneged_list else 0.0
    mean_wait_all_h = statistics.mean(wait_all_list) * 24.0 if wait_all_list else 0.0

    # LOS médio dos pacientes admitidos vs todos os pacientes
    mean_los_admitted = statistics.mean([p.los for p in eval_admitted]) if eval_admitted else 0.0

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

    pool_metrics = {}
    for t in TYPES:
        sub_pts = [p for p in eval_patients if p.bed_type == t]
        sub_adm = [p for p in sub_pts if p.id in admitted_patients]
        sub_ren = [p for p in sub_pts if p.id in timeout_patients]
        pool_metrics[f"patients_{t}"] = len(sub_pts)
        pool_metrics[f"admitted_{t}"] = len(sub_adm)
        pool_metrics[f"reneged_{t}"] = len(sub_ren)
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
        "mean_los_admitted_days": mean_los_admitted,
        "mean_occupancy_global": global_occupancy,
        **pool_metrics,
    }


def solve_offline_milp_bound(
    patients: list[DynamicPatient],
    capacities: dict[str, int],
    warmup_days: float = 15.0,
    horizon_days: float = 75.0,
    allow_overflow: bool = True,
    dt: float = 0.5,
) -> dict:
    """Resolve o MILP Clarividente (Hindsight Upper Bound - M5) indexado no tempo via HiGHS."""
    eval_patients = [p for p in patients if warmup_days <= p.arrival_time < horizon_days]
    base_survival = sum(p.p_out for p in eval_patients)

    # Agrupamento de pools (Adulto + UCO acoplados se allow_overflow=True; Pediátrico e Neonatal separados)
    if allow_overflow:
        pool_groups = [
            (["adult", "coronary"], capacities.get("adult", 0) + capacities.get("coronary", 0)),
            (["pediatric"], capacities.get("pediatric", 0)),
            (["neonatal"], capacities.get("neonatal", 0)),
        ]
    else:
        pool_groups = [([t], capacities.get(t, 0)) for t in TYPES]

    total_max_gain = 0.0
    total_admitted_ub = 0
    max_slot = int(math.ceil((horizon_days + 45.0) / dt)) + 2

    for btypes, cap in pool_groups:
        if cap <= 0:
            continue
        # Inclui todos os pacientes que chegaram desde t=0 para respeitar a ocupação na fronteira warmup_days
        group_pts = [p for p in patients if p.bed_type in btypes]
        if not group_pts:
            continue

        vars_c = []
        vars_is_eval = []
        patient_var_lists = []
        slot_loads: list[list[int]] = [[] for _ in range(max_slot)]
        var_idx = 0

        for p in group_pts:
            is_eval = warmup_days <= p.arrival_time < horizon_days
            arr_slot = int(math.floor(p.arrival_time / dt))
            max_wait_slots = max(1, int(math.ceil(p.max_wait / dt)))
            los_slots = max(1, int(math.floor(p.los / dt)))

            p_vars = []
            for w_step in range(max_wait_slots + 1):
                wait_days = min(p.max_wait, w_step * dt)
                s_adm = arr_slot + w_step
                if s_adm >= max_slot:
                    break
                # Se paciente é da janela de avaliação, contribui para o objetivo;
                # se for do warm-up, pequeno incentivo positivo para ocupar leitos realisticamente
                if is_eval:
                    gain = p.marginal_gain_at(p.arrival_time + wait_days, use_observed=False)
                else:
                    gain = 1e-4 * p.marginal_gain_at(p.arrival_time + wait_days, use_observed=False)

                vars_c.append(-gain)
                vars_is_eval.append(1 if is_eval else 0)
                p_vars.append(var_idx)

                s_end = min(max_slot, s_adm + los_slots)
                for s_occ in range(s_adm, s_end):
                    slot_loads[s_occ].append(var_idx)

                var_idx += 1
                if wait_days >= p.max_wait:
                    break

            if p_vars:
                patient_var_lists.append(p_vars)

        if var_idx == 0:
            continue

        rows, cols, vals, ub = [], [], [], []
        r_idx = 0
        for p_vars in patient_var_lists:
            for v in p_vars:
                rows.append(r_idx)
                cols.append(v)
                vals.append(1.0)
            ub.append(1.0)
            r_idx += 1

        for s_list in slot_loads:
            if s_list:
                for v in s_list:
                    rows.append(r_idx)
                    cols.append(v)
                    vals.append(1.0)
                ub.append(float(cap))
                r_idx += 1

        A = csc_matrix((vals, (rows, cols)), shape=(r_idx, var_idx))
        c = np.array(vars_c, dtype=float)
        # Relaxação LP do MILP indexado no tempo (fornece um Upper Bound válido e estrito para o ótimo!)
        res = milp(
            c=c,
            integrality=np.zeros(var_idx),
            bounds=Bounds(0.0, 1.0),
            constraints=LinearConstraint(A, -np.inf, ub),
        )
        if res.success and res.x is not None:
            sol = res.x
            for v_i, x_val in enumerate(sol):
                if vars_is_eval[v_i] and x_val > 1e-6:
                    total_max_gain += (-vars_c[v_i]) * x_val
                    total_admitted_ub += x_val

    ub_survivors = base_survival + total_max_gain
    return {
        "policy": "OFFLINE_UB",
        "total_patients": len(eval_patients),
        "admitted": total_admitted_ub,
        "expected_survivors": ub_survivors,
        "expected_survival_rate": ub_survivors / len(eval_patients) if eval_patients else 0.0,
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
    if df <= 0 or math.isnan(t_stat):
        return 1.0
    if df >= 30:
        z = abs(t_stat) * (1.0 - 1.0 / (4.0 * df))
        return math.erfc(z / math.sqrt(2.0))
    return math.erfc(abs(t_stat) / math.sqrt(2.0))


def run_dynamic_experiment(config: dict, destination: str | Path):
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)

    runs_rows = []
    paired_rows = []
    ub_rows = []

    demand_ratios = config.get("demand_ratios", [0.7, 1.0, 1.3, 1.6])
    replications = config.get("replications", 100)
    capacities = config["capacities"]
    warmup_days = float(config.get("warmup_days", 15.0))
    horizon_days = float(config.get("horizon_days", 75.0))
    allow_overflow = bool(config.get("allow_overflow", True))
    policies = config.get("policies", list(POLICIES))
    compute_ub = bool(config.get("compute_offline_ub", True))

    print(
        f"Iniciando simulação dinâmica calibrada: {len(demand_ratios)} demandas x {replications} "
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
                    allow_overflow=allow_overflow,
                    with_noise=False,
                )
                res["demand_ratio"] = d
                res["replication"] = rep
                runs_rows.append(res)
                rep_results[pol] = res

            if compute_ub:
                ub_res = solve_offline_milp_bound(
                    patients=patients,
                    capacities=capacities,
                    warmup_days=warmup_days,
                    horizon_days=horizon_days,
                    allow_overflow=allow_overflow,
                )
                ub_res["demand_ratio"] = d
                ub_res["replication"] = rep
                ub_res["cmu_mgs_survivors"] = rep_results["CMU_MGS"]["expected_survivors"]
                ub_res["mgs_survivors"] = rep_results["MGS"]["expected_survivors"]
                ub_res["fcfs_survivors"] = rep_results["FCFS"]["expected_survivors"]
                ub_res["cmu_optimality_gap_pct"] = (
                    (ub_res["expected_survivors"] - rep_results["CMU_MGS"]["expected_survivors"])
                    / ub_res["expected_survivors"]
                    * 100.0
                )
                # Fração do ganho máximo possível sobre o FCFS capturada pelo CMU-MGS
                max_gain_over_fcfs = ub_res["expected_survivors"] - rep_results["FCFS"]["expected_survivors"]
                cmu_gain_over_fcfs = rep_results["CMU_MGS"]["expected_survivors"] - rep_results["FCFS"]["expected_survivors"]
                ub_res["cmu_captured_gain_pct"] = (
                    (cmu_gain_over_fcfs / max_gain_over_fcfs * 100.0) if max_gain_over_fcfs > 0.1 else 100.0
                )
                ub_rows.append(ub_res)

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
                    "diff_cmu_vs_mgs": (
                        rep_results["CMU_MGS"]["expected_survivors"] - rep_results["MGS"]["expected_survivors"]
                        if pol == "CMU_MGS" else 0.0
                    ),
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

    if ub_rows:
        with (dest / "offline_ub.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(ub_rows[0].keys()))
            writer.writeheader()
            writer.writerows(ub_rows)

    summary_rows = []
    metrics = (
        "total_patients",
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
        "mean_los_admitted_days",
        "mean_occupancy_global",
        "occupancy_adult",
        "occupancy_coronary",
        "occupancy_pediatric",
        "occupancy_neonatal",
        "admitted_adult",
        "admitted_coronary",
        "admitted_pediatric",
        "admitted_neonatal",
        "patients_adult",
        "patients_coronary",
        "patients_pediatric",
        "patients_neonatal",
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
    print(f"Simulação principal concluída. Resultados salvos em {dest}")


def run_comprehensive_extensions(config: dict, destination: str | Path):
    """Executa todos os experimentos adicionais exigidos na revisão:
    1. Ruído em P_in, P_out e E[LOS] para todas as políticas com 100 replicações e Holm (M6)
    2. Varredura paramétrica (Mapa de calor beta x alpha) demonstrando onde CMU-MGS supera MGS (M3)
    3. Ablação do acoplamento de overflow Adulto <-> UCO (M8)
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    replications = int(config.get("replications", 100))
    d = 1.6

    # --- 1. Experimento de Ruído Clínico Completo (M6: 100 replicações, todas as políticas) ---
    noise_levels = [0.0, 0.05, 0.10, 0.20]
    noise_rows = []
    print(f"[M6] Executando análise de ruído em P_in, P_out e E[LOS] ({replications} replicações)...")
    for sigma in noise_levels:
        for rep in range(replications):
            patients = generate_patient_stream(config, d, rep, sigma_noise=sigma)
            rep_res = {}
            for pol in POLICIES:
                res = simulate_policy(
                    patients=patients,
                    capacities=config["capacities"],
                    policy=pol,
                    warmup_days=config.get("warmup_days", 15.0),
                    horizon_days=config.get("horizon_days", 75.0),
                    allow_overflow=True,
                    with_noise=(sigma > 0.0),
                )
                rep_res[pol] = res
            fcfs_surv = rep_res["FCFS"]["expected_survivors"]
            for pol in POLICIES:
                noise_rows.append({
                    "sigma_noise": sigma,
                    "replication": rep,
                    "policy": pol,
                    "expected_survivors": rep_res[pol]["expected_survivors"],
                    "realized_survivors": rep_res[pol]["realized_survivors"],
                    "diff_vs_fcfs": rep_res[pol]["expected_survivors"] - fcfs_surv,
                    "admitted": rep_res[pol]["admitted"],
                })

    with (dest / "sensitivity_noise.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(noise_rows[0].keys()))
        writer.writeheader()
        writer.writerows(noise_rows)

    # --- 2. Varredura Paramétrica Beta x Alpha (M3: Tensão Benefício vs Leito-Dia) ---
    betas = [0.0, 0.6, 1.2, 1.8, 2.4]
    alphas = [0.05, 0.18, 0.35, 0.50]
    grid_rows = []
    grid_reps = 50
    print(f"[M3] Executando grade de sensibilidade beta x alpha ({len(betas)}x{len(alphas)} x {grid_reps} reps)...")
    for beta in betas:
        for alpha in alphas:
            cfg_grid = dict(config)
            cfg_grid["sev_los_beta"] = beta
            cfg_grid["override_alpha_det"] = alpha
            diffs_cmu_mgs = []
            diffs_cmu_fcfs = []
            diffs_mgs_fcfs = []
            diffs_aust_fcfs = []
            for rep in range(grid_reps):
                pts = generate_patient_stream(cfg_grid, d, rep, sigma_noise=0.0)
                r_cmu = simulate_policy(pts, config["capacities"], "CMU_MGS", 15.0, 75.0, True, False)
                r_mgs = simulate_policy(pts, config["capacities"], "MGS", 15.0, 75.0, True, False)
                r_aus = simulate_policy(pts, config["capacities"], "AUSTERE", 15.0, 75.0, True, False)
                r_fcf = simulate_policy(pts, config["capacities"], "FCFS", 15.0, 75.0, True, False)
                diffs_cmu_mgs.append(r_cmu["expected_survivors"] - r_mgs["expected_survivors"])
                diffs_cmu_fcfs.append(r_cmu["expected_survivors"] - r_fcf["expected_survivors"])
                diffs_mgs_fcfs.append(r_mgs["expected_survivors"] - r_fcf["expected_survivors"])
                diffs_aust_fcfs.append(r_aus["expected_survivors"] - r_fcf["expected_survivors"])

            st_cm = interval(diffs_cmu_mgs)
            t_cm = st_cm["mean"] / st_cm["standard_error"] if st_cm["standard_error"] > 0 else 0.0
            grid_rows.append({
                "beta": beta,
                "alpha": alpha,
                "cmu_vs_mgs_mean": st_cm["mean"],
                "cmu_vs_mgs_se": st_cm["standard_error"],
                "cmu_vs_mgs_t": t_cm,
                "cmu_vs_mgs_p": student_t_pvalue(t_cm, grid_reps - 1),
                "cmu_vs_fcfs_mean": statistics.mean(diffs_cmu_fcfs),
                "mgs_vs_fcfs_mean": statistics.mean(diffs_mgs_fcfs),
                "austere_vs_fcfs_mean": statistics.mean(diffs_aust_fcfs),
            })

    with (dest / "sensitivity_grid_beta_alpha.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(grid_rows[0].keys()))
        writer.writeheader()
        writer.writerows(grid_rows)

    # --- 3. Ablação de Compartilhamento Adulto <-> UCO (M8) ---
    ablation_rows = []
    print(f"[M8] Executando ablação de compartilhamento Adulto <-> UCO ({replications} replicações)...")
    for d_abl in [0.7, 1.0, 1.3, 1.6]:
        for rep in range(replications):
            pts = generate_patient_stream(config, d_abl, rep, sigma_noise=0.0)
            for pol in ("FCFS", "MGS", "CMU_MGS"):
                r_on = simulate_policy(pts, config["capacities"], pol, 15.0, 75.0, allow_overflow=True, with_noise=False)
                r_off = simulate_policy(pts, config["capacities"], pol, 15.0, 75.0, allow_overflow=False, with_noise=False)
                ablation_rows.append({
                    "demand_ratio": d_abl,
                    "replication": rep,
                    "policy": pol,
                    "surv_overflow_on": r_on["expected_survivors"],
                    "surv_overflow_off": r_off["expected_survivors"],
                    "diff_overflow": r_on["expected_survivors"] - r_off["expected_survivors"],
                    "adm_overflow_on": r_on["admitted"],
                    "adm_overflow_off": r_off["admitted"],
                    "wait_adm_on": r_on["mean_wait_admitted_hours"],
                    "wait_adm_off": r_off["mean_wait_admitted_hours"],
                })

    with (dest / "ablation_overflow.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ablation_rows[0].keys()))
        writer.writeheader()
        writer.writerows(ablation_rows)

    print(f"Todos os experimentos estendidos concluídos e salvos em {dest}")


def main():
    parser = argparse.ArgumentParser(description="Simulação Dinâmica de Leitos de UTI Multi-Tipo")
    parser.add_argument("--config", required=True, help="Caminho para o JSON de configuração")
    parser.add_argument("--output", required=True, help="Diretório de saída dos resultados")
    parser.add_argument("--sensitivity", action="store_true", help="Executa baterias de sensibilidade e ablação")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    run_dynamic_experiment(config, args.output)
    if args.sensitivity:
        run_comprehensive_extensions(config, Path(args.output) / "sensitivity")


if __name__ == "__main__":
    main()
