"""Gera figuras do artigo Elsevier a partir dos resultados dinâmicos."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import csv

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results" / "dynamic_huufma"
FIG_DIR = ROOT / "doc" / "artigo-elsevier"

summary = defaultdict(dict)
with (RESULTS / "summary.csv").open() as f:
    for r in csv.DictReader(f):
        d = float(r["demand_ratio"])
        p = r["policy"]
        m = r["metric"]
        summary[(d, p)][m] = {
            "mean": float(r["mean"]),
            "ci95_low": float(r["ci95_low"]),
            "ci95_high": float(r["ci95_high"]),
            "se": float(r["standard_error"]),
        }

demands = [0.7, 1.0, 1.3, 1.6]
policies = ["FCFS", "MSF", "LSF", "AUSTERE", "MGS", "CMU_MGS"]
colors = {
    "FCFS": "#7f7f7f",
    "MSF": "#d62728",
    "LSF": "#ff7f0e",
    "AUSTERE": "#9467bd",
    "MGS": "#1f77b4",
    "CMU_MGS": "#2ca02c",
}

fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
for pol in policies:
    means = [summary[(d, pol)]["expected_survivors"]["mean"] for d in demands]
    yerr = [summary[(d, pol)]["expected_survivors"]["se"] * 1.96 for d in demands]
    ax.errorbar(demands, means, yerr=yerr, marker="o", capsize=4, label=pol, color=colors[pol], linewidth=1.8)

ax.set_title("Expected Survivors Across Congestion Levels (60-Day Horizon)", fontsize=12, fontweight="bold")
ax.set_xlabel(r"Demand Congestion Ratio ($\rho = \lambda \cdot \mathbb{E}[\mathrm{LOS}] / C$)", fontsize=10)
ax.set_ylabel("Expected Total Survivors (Lives Saved)", fontsize=10)
ax.set_xticks(demands)
ax.set_xticklabels(["0.70 (Normal)", "1.00 (Balanced)", "1.30 (Moderate Surge)", "1.60 (Severe Surge)"])
ax.grid(True, linestyle="--", alpha=0.5)
ax.legend(frameon=True, facecolor="white", loc="upper left")
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_survivors.png")
plt.close()

paired = defaultdict(dict)
with (RESULTS / "paired_statistical_summary.csv").open() as f:
    for r in csv.DictReader(f):
        d = float(r["demand_ratio"])
        p = r["policy"]
        paired[(d, p)] = {
            "mean": float(r["diff_mean"]),
            "ci95_low": float(r["ci95_low"]),
            "ci95_high": float(r["ci95_high"]),
            "se": float(r["se"]),
        }

fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
active_pols = ["MSF", "LSF", "AUSTERE", "MGS", "CMU_MGS"]
x = np.arange(len(demands))
width = 0.15
for idx, pol in enumerate(active_pols):
    means = [paired[(d, pol)]["mean"] for d in demands]
    ci_err = [paired[(d, pol)]["se"] * 1.96 for d in demands]
    pos = x + (idx - 2) * width
    ax.bar(pos, means, width, yerr=ci_err, capsize=3, label=pol, color=colors[pol], alpha=0.85)

ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
ax.set_title("CRN Paired Survival Gain Relative to FCFS Hospital Baseline", fontsize=12, fontweight="bold")
ax.set_xlabel(r"Demand Congestion Ratio ($\rho$)", fontsize=10)
ax.set_ylabel(r"Additional Expected Lives Saved ($\Delta S$ vs FCFS)", fontsize=10)
ax.set_xticks(x)
ax.set_xticklabels(["0.70", "1.00", "1.30", "1.60"])
ax.grid(True, linestyle="--", alpha=0.5)
ax.legend(frameon=True, facecolor="white", loc="upper left")
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_paired_gain.png")
plt.close()

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), dpi=300)
for pol in policies:
    adm_waits = [summary[(d, pol)]["mean_wait_admitted_hours"]["mean"] for d in demands]
    ax1.plot(demands, adm_waits, marker="s", label=pol, color=colors[pol], linewidth=1.6)
ax1.set_title("(A) Admitted Patients Waiting Time", fontsize=11, fontweight="bold")
ax1.set_xlabel(r"Demand Ratio ($\rho$)", fontsize=10)
ax1.set_ylabel("Mean Queue Waiting Time (Hours)", fontsize=10)
ax1.set_xticks(demands)
ax1.grid(True, linestyle="--", alpha=0.5)
ax1.legend(frameon=True, facecolor="white")

for pol in policies:
    ren_rates = [summary[(d, pol)]["reneging_rate"]["mean"] * 100.0 for d in demands]
    ax2.plot(demands, ren_rates, marker="^", label=pol, color=colors[pol], linewidth=1.6)
ax2.set_title("(B) Queue Reneging Rate", fontsize=11, fontweight="bold")
ax2.set_xlabel(r"Demand Ratio ($\rho$)", fontsize=10)
ax2.set_ylabel("Reneging Rate (%)", fontsize=10)
ax2.set_xticks(demands)
ax2.grid(True, linestyle="--", alpha=0.5)
ax2.legend(frameon=True, facecolor="white")

plt.tight_layout()
plt.savefig(FIG_DIR / "fig_waiting_times.png")
plt.close()

sens_data = defaultdict(lambda: defaultdict(list))
with (RESULTS / "sensitivity" / "sensitivity_noise.csv").open() as f:
    for r in csv.DictReader(f):
        sens_data[float(r["sigma_noise"])][r["policy"]].append(float(r["expected_survivors"]))

sigmas = sorted(sens_data.keys())
fig, ax = plt.subplots(figsize=(6.5, 4.2), dpi=300)
for pol in ["FCFS", "AUSTERE", "MGS", "CMU_MGS"]:
    means = [np.mean(sens_data[s][pol]) for s in sigmas]
    stds = [np.std(sens_data[s][pol]) / np.sqrt(len(sens_data[s][pol])) * 1.96 for s in sigmas]
    ax.errorbar(sigmas, means, yerr=stds, marker="D", capsize=4, label=pol, color=colors[pol], linewidth=1.8)

ax.set_title(r"Triage Robustness Under Clinical Estimation Noise ($\rho = 1.6$)", fontsize=11, fontweight="bold")
ax.set_xlabel(r"Clinical Observation Noise ($\sigma$ in $\widetilde{\Delta P}=\Delta P+\varepsilon$)", fontsize=10)
ax.set_ylabel("Expected Total Survivors (60 Days)", fontsize=10)
ax.set_xticks(sigmas)
ax.set_xticklabels(["0.0 (Exact)", "0.05 (Low Noise)", "0.10 (Moderate)", "0.20 (High Noise)"])
ax.grid(True, linestyle="--", alpha=0.5)
ax.legend(frameon=True, facecolor="white", loc="lower left")
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_sensitivity.png")
plt.close()

print(f"Figuras geradas em {FIG_DIR}")
