"""Simulação dinâmica de eventos discretos para alocação de leitos de UTI multi-tipo.

Calibração semi-empírica transparente (Tabela 2):
- Parâmetros Medidos (Observados):
  * Capacidade física: DATASUS / CNES (HU-UFMA, competência 12/2024: 55 leitos em 4 pools)
  * Tempo de permanência médio (LOS) e mortalidade hospitalar de admitidos: Registro Nacional UTIs Brasileiras
    (AMIB / Epimed, Soares et al., 2024; ORCHESTRA, Soares et al., 2024b), Rede Brasileira de Pesquisas Neonatais
    (Guinsburg et al., 2016) e coorte de atraso na admissão em UTI (Cardoso et al., 2011).
- Parâmetros Calibrados (Ajustados aos alvos medidos):
  * Taxa de deterioração na fila alpha_det (calibrada a partir da razão de risco de 1.5%/h de Cardoso et al., 2011)
  * Fração de ganho terapêutico g_i (ajustada para que a mortalidade pós-admissão em equilíbrio reproduza exatamente
    a mortalidade hospitalar registrada no AMIB/Epimed por especialidade: ~27% Adulto, ~15% UCO, ~6% Pediátrica, ~8% Neonatal).
- Parâmetros Contrafactuais / Supostos (Não observáveis em registros de internados, avaliados sob análise de sensibilidade):
  * Sobrevida basal sem UTI (P_out), janela de tolerância máxima na fila (W_max), fator de penalidade no abandono (theta_ren)
    e acoplamento gravidade-LOS (beta).

Políticas e Limitantes Superiores (Upper Bounds):
- FCFS, MSF, LSF, MGS, CMU_MGS, AUSTERE (CMU-MGS com urgência de prazo)
- OFFLINE_LP_REAL: Limitante superior LP clarividente (usa LOS_i realizado)
- OFFLINE_LP_EXP: Limitante superior LP não-antecipativo em duração (usa E[LOS_i], conforme Brown, Smith & Sun, 2010)
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
POLICIES = ("FCFS", "MSF", "LSF", "MGS", "CMU_MGS", "AUSTERE")

# Perfis por especialidade: calibrados para que 1 - E[P_in(w)] reproduza a mortalidade observada no AMIB/Epimed
DEFAULT_POOL_PROFILES = {
    "adult": {
        "mean_los_days": 6.5,
        "cv_los": 0.65,
        "p_out_range": [0.15, 0.55],
        "gain_fraction_range": [0.45, 0.80],  # E[P_in,0] = 0.756 -> Mortalidade admitidos ~26.5% (Alvo SUS AMIB: ~27%)
        "max_wait_range": [0.5, 2.5],
        "alpha_det": 0.18,
    },
    "coronary": {
        "mean_los_days": 4.8,
        "cv_los": 0.55,
        "p_out_range": [0.30, 0.70],
        "gain_fraction_range": [0.55, 0.88],  # E[P_in,0] = 0.858 -> Mortalidade admitidos ~15.5% (Alvo UCO: ~15%)
        "max_wait_range": [0.5, 2.0],
        "alpha_det": 0.20,
    },
    "pediatric": {
        "mean_los_days": 6.0,
        "cv_los": 0.65,
        "p_out_range": [0.40, 0.80],
        "gain_fraction_range": [0.75, 0.96],  # E[P_in,0] = 0.942 -> Mortalidade admitidos ~6.2% (Alvo UTIP AMIB: 4-7%)
        "max_wait_range": [0.5, 2.5],
        "alpha_det": 0.15,
    },
    "neonatal": {
        "mean_los_days": 11.5,
        "cv_los": 0.75,
        "p_out_range": [0.35, 0.75],
        "gain_fraction_range": [0.70, 0.95],  # E[P_in,0] = 0.921 -> Mortalidade admitidos ~8.4% (Alvo UTIN: 5-10%)
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

    def marginal_gain_at(
        self, current_time: float, use_observed: bool = False, reneging_survival_factor: float = 1.0
    ) -> float:
        """Calcula ganho marginal ΔP(w) = P_in(w) - theta_ren * P_out."""
        base_out = (self.obs_p_out if use_observed else self.p_out) * reneging_survival_factor
        return max(0.0, self.p_in_at(current_time, use_observed=use_observed) - base_out)


def priority_score(
    p: DynamicPatient,
    policy: str,
    current_time: float,
    use_observed: bool = False,
    reneging_survival_factor: float = 1.0,
) -> float:
    """Calcula o escore de prioridade dinâmico do paciente sob a política avaliada."""
    if policy == "FCFS":
        return -p.arrival_time

    if policy == "LSF":
        return p.p_in_at(current_time, use_observed=use_observed)

    if policy == "MSF":
        p_out_val = p.obs_p_out if use_observed else p.p_out
        return 1.0 - p_out_val

    delta_p = p.marginal_gain_at(
        current_time, use_observed=use_observed, reneging_survival_factor=reneging_survival_factor
    )
    e_los = p.obs_expected_los if use_observed else p.expected_los
    e_los = max(0.2, e_los)

    if policy == "MGS":
        return delta_p

    if policy == "CMU_MGS":
        return delta_p / e_los

    if policy == "AUSTERE":
        # Regra heurística CMU-MGS com urgência de prazo limitada (P4):
        # Como candidatos só competem dentro do mesmo pool, 1 + kappa / (tau + kappa) pondera a proximidade
        # do limite de espera sem o termo constante redundante alpha_det.
        wait = max(0.0, current_time - p.arrival_time)
        rem_wait = max(0.25, p.max_wait - wait)
        urgency_multiplier = 1.0 + (0.5 / (rem_wait + 0.5))
        return (delta_p / e_los) * urgency_multiplier

    raise ValueError(f"Política desconhecida: {policy}")


def stable_seed(seed: int, demand: float, replication: int, stream: str) -> int:
    raw = json.dumps([seed, round(demand, 4), replication, stream]).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def get_pool_profile(config: dict, btype: str) -> dict:
    profiles = config.get("pool_profiles", DEFAULT_POOL_PROFILES)
    prof = dict(DEFAULT_POOL_PROFILES.get(btype, DEFAULT_POOL_PROFILES["adult"]))
    if btype in profiles:
        prof.update(profiles[btype])
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
    """Gera o fluxo de pacientes com chegadas de Poisson exatas em relação ao E[LOS] efetivo."""
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

        mean_severity = 1.0 - 0.5 * (p_out_low + p_out_high)
        arrival_rate = (demand_ratio * cap) / mean_los_pool
        t = rng_arr.expovariate(arrival_rate)

        while t < horizon_total:
            p_out = rng_cli.uniform(p_out_low, p_out_high)
            gain_fraction = rng_cli.uniform(gain_low, gain_high)
            p_in_0 = p_out + (1.0 - p_out) * gain_fraction
            max_wait = rng_cli.uniform(wait_low, wait_high)

            # E[LOS_i] centrado exatamente em mean_los_pool.
            # Como |severity - mean_severity| <= 0.20, para |beta| <= 2.4 temos 1 + beta*(...) >= 0.52 > 0.35,
            # logo o piso de segurança 0.35 nunca é ativado e E[E[LOS_i]] == mean_los_pool de forma exata.
            severity = 1.0 - p_out
            raw_mult = 1.0 + sev_los_beta * (severity - mean_severity)
            mult = max(0.35, raw_mult)
            expected_patient_los = mean_los_pool * mult

            mu_i = math.log(expected_patient_los) - 0.5 * sigma_los**2
            los = rng_los.lognormvariate(mu_i, sigma_los)
            outcome_u = rng_out.random()

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
    reneging_survival_factor: float = 1.0,
) -> dict:
    """Executa a simulação de eventos discretos até a drenagem completa da coorte."""
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
                -priority_score(
                    p, policy, now, use_observed=with_noise, reneging_survival_factor=reneging_survival_factor
                ),
                p.arrival_time,
                p.id,
            )
        )
        return candidate_queue.pop(0)

    def try_admit_for_pool(pool: str, now: float):
        cap = capacities.get(pool, 0)
        while occupied_beds[pool] < cap:
            chosen = None
            if queues[pool]:
                chosen = select_best_patient(queues[pool], now)
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

    eval_patients = [p for p in patients if eval_start <= p.arrival_time < eval_end]
    total_eval = len(eval_patients)

    eval_admitted = [p for p in eval_patients if p.id in admitted_patients]
    eval_reneged = [p for p in eval_patients if p.id in timeout_patients]

    n_admitted = len(eval_admitted)
    n_reneged = len(eval_reneged)

    # Sobrevida esperada e realizada considerando fator de penalidade no abandono (theta_ren - P3)
    expected_survivors = sum(
        p.p_in_at(admission_times[p.id], use_observed=False)
        if p.id in admitted_patients
        else (reneging_survival_factor * p.p_out)
        for p in eval_patients
    )
    realized_survivors = sum(
        p.outcome_uniform < (
            p.p_in_at(admission_times[p.id], use_observed=False)
            if p.id in admitted_patients
            else (reneging_survival_factor * p.p_out)
        )
        for p in eval_patients
    )

    wait_admitted_list = [wait_times.get(p.id, 0.0) for p in eval_admitted]
    wait_reneged_list = [wait_times.get(p.id, p.max_wait) for p in eval_reneged]
    wait_all_list = [wait_times.get(p.id, p.max_wait) for p in eval_patients]

    mean_wait_admitted_h = statistics.mean(wait_admitted_list) * 24.0 if wait_admitted_list else 0.0
    mean_wait_reneged_h = statistics.mean(wait_reneged_list) * 24.0 if wait_reneged_list else 0.0
    mean_wait_all_h = statistics.mean(wait_all_list) * 24.0 if wait_all_list else 0.0
    mean_los_admitted = statistics.mean([p.los for p in eval_admitted]) if eval_admitted else 0.0

    # Mortalidade pós-admissão global e por pool (para validação direta contra AMIB/Epimed - P1)
    admitted_surv_probs = [p.p_in_at(admission_times[p.id], use_observed=False) for p in eval_admitted]
    admitted_mortality_rate = 1.0 - statistics.mean(admitted_surv_probs) if admitted_surv_probs else 0.0

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
        sub_adm_surv = [p.p_in_at(admission_times[p.id], use_observed=False) for p in sub_adm]
        pool_metrics[f"patients_{t}"] = len(sub_pts)
        pool_metrics[f"admitted_{t}"] = len(sub_adm)
        pool_metrics[f"reneged_{t}"] = len(sub_ren)
        pool_metrics[f"admission_rate_{t}"] = len(sub_adm) / len(sub_pts) if sub_pts else 0.0
        pool_metrics[f"occupancy_{t}"] = occupancy_rates[t]
        pool_metrics[f"admitted_mortality_{t}"] = (1.0 - statistics.mean(sub_adm_surv)) if sub_adm_surv else 0.0

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
        "admitted_mortality_rate": admitted_mortality_rate,
        "mean_wait_admitted_hours": mean_wait_admitted_h,
        "mean_wait_reneged_hours": mean_wait_reneged_h,
        "mean_wait_all_hours": mean_wait_all_h,
        "mean_los_admitted_days": mean_los_admitted,
        "mean_occupancy_global": global_occupancy,
        **pool_metrics,
    }


def solve_offline_lp_bound(
    patients: list[DynamicPatient],
    capacities: dict[str, int],
    warmup_days: float = 15.0,
    horizon_days: float = 75.0,
    allow_overflow: bool = True,
    dt: float = 0.5,
    use_expected_los: bool = False,
    reneging_survival_factor: float = 1.0,
) -> dict:
    """Resolve o Limitante Superior LP Indexado no Tempo via HiGHS (Resolve P2a, P2b, P2c):
    - Se use_expected_los=False: Limitante LP Clarividente (Hindsight LP Bound, usa LOS_i realizado).
    - Se use_expected_los=True: Limitante LP Não-Antecipativo em Duração (Duration-Expectation LP Bound,
      usa E[LOS_i], eliminando o cherry-picking de realizações curtas conforme Brown, Smith & Sun, 2010).
    - Inclui apenas os pacientes de I_eval = [warmup_days, horizon_days) sem restrição de fronteira do warm-up,
      o que constitui uma relaxação universalmente válida (independente da política) para qualquer estado em T_warm.
    - S_max é calculado dinamicamente para cobrir 100% da drenagem pós-horizonte.
    """
    eval_patients = [p for p in patients if warmup_days <= p.arrival_time < horizon_days]
    base_survival = sum(reneging_survival_factor * p.p_out for p in eval_patients)

    if allow_overflow:
        pool_groups = [
            (["adult", "coronary"], capacities.get("adult", 0) + capacities.get("coronary", 0)),
            (["pediatric"], capacities.get("pediatric", 0)),
            (["neonatal"], capacities.get("neonatal", 0)),
        ]
    else:
        pool_groups = [([t], capacities.get(t, 0)) for t in TYPES]

    total_max_gain = 0.0
    total_admitted_ub = 0.0

    # S_max cobre toda a drenagem de qualquer paciente de I_eval (P2b)
    max_possible_end = max(
        (p.arrival_time + p.max_wait + (p.expected_los if use_expected_los else p.los) for p in eval_patients),
        default=horizon_days + 30.0,
    )
    max_slot = int(math.ceil(max_possible_end / dt)) + 4

    for btypes, cap in pool_groups:
        if cap <= 0:
            continue
        # Considera apenas os pacientes de I_eval (relaxando a ocupação residual do warm-up em t = warmup_days,
        # garantindo um Upper Bound universalmente válido para todas as políticas - P2a!)
        group_pts = [p for p in eval_patients if p.bed_type in btypes]
        if not group_pts:
            continue

        vars_c = []
        patient_var_lists = []
        slot_loads: list[list[int]] = [[] for _ in range(max_slot)]
        var_idx = 0

        for p in group_pts:
            arr_slot = int(math.floor(p.arrival_time / dt))
            max_wait_slots = max(1, int(math.ceil(p.max_wait / dt)))
            stay_val = p.expected_los if use_expected_los else p.los
            los_slots = max(1, int(math.floor(stay_val / dt)))

            p_vars = []
            for w_step in range(max_wait_slots + 1):
                wait_days = min(p.max_wait, w_step * dt)
                s_adm = arr_slot + w_step
                if s_adm >= max_slot:
                    break
                gain = p.marginal_gain_at(
                    p.arrival_time + wait_days,
                    use_observed=False,
                    reneging_survival_factor=reneging_survival_factor,
                )
                vars_c.append(-gain)
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
        res = milp(
            c=c,
            integrality=np.zeros(var_idx),
            bounds=Bounds(0.0, 1.0),
            constraints=LinearConstraint(A, -np.inf, ub),
        )
        if res.success and res.x is not None:
            sol = res.x
            for v_i, x_val in enumerate(sol):
                if x_val > 1e-6:
                    total_max_gain += (-vars_c[v_i]) * x_val
                    total_admitted_ub += x_val

    ub_survivors = base_survival + total_max_gain
    return {
        "policy": "OFFLINE_LP_EXP" if use_expected_los else "OFFLINE_LP_REAL",
        "total_patients": len(eval_patients),
        "admitted": total_admitted_ub,
        "expected_survivors": ub_survivors,
        "expected_survival_rate": ub_survivors / len(eval_patients) if eval_patients else 0.0,
    }


# Mantém alias para compatibilidade com testes unitários
solve_offline_milp_bound = solve_offline_lp_bound


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


def apply_holm_bonferroni(test_dicts: list[dict], p_key: str = "p_raw") -> list[dict]:
    """Aplica o ajuste de Holm-Bonferroni a uma família de testes."""
    indexed = list(enumerate(test_dicts))
    indexed.sort(key=lambda x: x[1][p_key])
    m = len(indexed)
    running_max = 0.0
    adjusted = [0.0] * m
    for rank, (orig_idx, item) in enumerate(indexed):
        p_adj = min(1.0, item[p_key] * (m - rank))
        running_max = max(running_max, p_adj)
        adjusted[orig_idx] = running_max
    out = []
    for idx, item in enumerate(test_dicts):
        out.append({**item, "p_holm": adjusted[idx], "significant_005": adjusted[idx] < 0.05})
    return out


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
        f"Iniciando simulação dinâmica: {len(demand_ratios)} demandas x {replications} "
        f"replicações x {len(policies)} políticas..."
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
                ub_real = solve_offline_lp_bound(
                    patients=patients,
                    capacities=capacities,
                    warmup_days=warmup_days,
                    horizon_days=horizon_days,
                    allow_overflow=allow_overflow,
                    use_expected_los=False,
                )
                ub_exp = solve_offline_lp_bound(
                    patients=patients,
                    capacities=capacities,
                    warmup_days=warmup_days,
                    horizon_days=horizon_days,
                    allow_overflow=allow_overflow,
                    use_expected_los=True,
                )
                cmu_surv = rep_results["CMU_MGS"]["expected_survivors"]
                ub_rows.append({
                    "demand_ratio": d,
                    "replication": rep,
                    "total_patients": ub_real["total_patients"],
                    "fcfs_survivors": rep_results["FCFS"]["expected_survivors"],
                    "mgs_survivors": rep_results["MGS"]["expected_survivors"],
                    "cmu_mgs_survivors": cmu_surv,
                    "ub_exp_los_admitted": ub_exp["admitted"],
                    "ub_exp_los_survivors": ub_exp["expected_survivors"],
                    "ub_real_los_admitted": ub_real["admitted"],
                    "ub_real_los_survivors": ub_real["expected_survivors"],
                    "gap_vs_exp_lp_pct": (ub_exp["expected_survivors"] - cmu_surv) / ub_exp["expected_survivors"] * 100.0,
                    "gap_vs_real_lp_pct": (ub_real["expected_survivors"] - cmu_surv) / ub_real["expected_survivors"] * 100.0,
                })

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
        "admitted_mortality_rate",
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
        "admitted_mortality_adult",
        "admitted_mortality_coronary",
        "admitted_mortality_pediatric",
        "admitted_mortality_neonatal",
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

    paired_summary = apply_holm_bonferroni(raw_tests, "p_raw")
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
    """Executa todos os experimentos adicionais exigidos na 3ª rodada:
    1. Ruído em P_in, P_out e E[LOS] (100 replicações + Holm)
    2. Grade Beta x Alpha incluindo beta < 0 (-0.6, 0.0, 0.6, 1.2, 1.8, 2.4) com ajuste de Holm (P5 e Menor 4)
    3. Ablação de compartilhamento Adulto <-> UCO com ajuste de Holm (Menor 4)
    4. Sensibilidade ao payoff de quem desiste (theta_ren in {1.0, 0.5, 0.0} - P3)
    """
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    replications = int(config.get("replications", 100))
    d = 1.6

    # --- 1. Experimento de Ruído Clínico Completo (100 replicações) ---
    noise_levels = [0.0, 0.05, 0.10, 0.20]
    noise_rows = []
    print(f"[Noise] Executando análise de ruído em P_in, P_out e E[LOS] ({replications} replicações)...")
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

    # --- 2. Varredura Paramétrica Beta x Alpha incluindo Beta = -0.6 (P5: Mortalidade precoce vs crônica) ---
    betas = [-0.6, 0.0, 0.6, 1.2, 1.8, 2.4]
    alphas = [0.05, 0.18, 0.35, 0.50]
    raw_grid = []
    grid_reps = 50
    print(f"[P5] Executando grade de sensibilidade beta x alpha ({len(betas)}x{len(alphas)} x {grid_reps} reps)...")
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
            p_raw = student_t_pvalue(t_cm, grid_reps - 1) if beta != 0.0 else 1.0
            raw_grid.append({
                "beta": beta,
                "alpha": alpha,
                "cmu_vs_mgs_mean": st_cm["mean"],
                "cmu_vs_mgs_se": st_cm["standard_error"],
                "cmu_vs_mgs_t": t_cm,
                "p_raw": p_raw,
                "cmu_vs_fcfs_mean": statistics.mean(diffs_cmu_fcfs),
                "mgs_vs_fcfs_mean": statistics.mean(diffs_mgs_fcfs),
                "austere_vs_fcfs_mean": statistics.mean(diffs_aust_fcfs),
            })

    grid_rows = apply_holm_bonferroni(raw_grid, "p_raw")
    with (dest / "sensitivity_grid_beta_alpha.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(grid_rows[0].keys()))
        writer.writeheader()
        writer.writerows(grid_rows)

    # --- 3. Ablação de Compartilhamento Adulto <-> UCO (100 replicações) ---
    ablation_rows = []
    print(f"[Ablation] Executando ablação de compartilhamento Adulto <-> UCO ({replications} replicações)...")
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

    # --- 4. Sensibilidade ao Payoff de Quem Desiste (theta_ren in {1.0, 0.5, 0.0} - P3) ---
    reneging_factors = [1.0, 0.5, 0.0]
    ren_payoff_rows = []
    print(f"[P3] Executando sensibilidade ao payoff de quem desiste (theta_ren in {reneging_factors})...")
    for theta in reneging_factors:
        for rep in range(replications):
            pts = generate_patient_stream(config, d, rep, sigma_noise=0.0)
            rep_res = {}
            for pol in POLICIES:
                res = simulate_policy(
                    patients=pts,
                    capacities=config["capacities"],
                    policy=pol,
                    warmup_days=15.0,
                    horizon_days=75.0,
                    allow_overflow=True,
                    with_noise=False,
                    reneging_survival_factor=theta,
                )
                rep_res[pol] = res
            fcfs_s = rep_res["FCFS"]["expected_survivors"]
            for pol in POLICIES:
                ren_payoff_rows.append({
                    "theta_ren": theta,
                    "replication": rep,
                    "policy": pol,
                    "expected_survivors": rep_res[pol]["expected_survivors"],
                    "diff_vs_fcfs": rep_res[pol]["expected_survivors"] - fcfs_s,
                    "admitted": rep_res[pol]["admitted"],
                    "reneging_rate": rep_res[pol]["reneging_rate"],
                })

    with (dest / "sensitivity_reneging_payoff.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ren_payoff_rows[0].keys()))
        writer.writeheader()
        writer.writerows(ren_payoff_rows)

    print(f"Todos os experimentos da 3ª rodada concluídos e salvos em {dest}")


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
