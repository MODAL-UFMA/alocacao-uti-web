"""Generate the four journal figures from the stored replication CSVs.

Data and calculations are unchanged from the reported results. Embedded
titles are omitted so that captions in the manuscript carry the description.
Multi-panel figures keep only the letters (A) and (B).
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results" / "dynamic_huufma"

POLICIES = ["FCFS", "MSF", "LSF", "MGS", "CMU_MGS", "AUSTERE"]
LABELS = {
    "FCFS": "FCFS",
    "MSF": "MSF",
    "LSF": "LSF",
    "MGS": "MGS",
    "CMU_MGS": "CMU-MGS",
    "AUSTERE": "CMU-DL",
}
COLORS = {
    "FCFS": "#7f7f7f",
    "MSF": "#d62728",
    "LSF": "#ff7f0e",
    "MGS": "#1f77b4",
    "CMU_MGS": "#2ca02c",
    "AUSTERE": "#9467bd",
    "LP_REAL": "#111111",
    "LP_EXP": "#444444",
}
DEMANDS = [0.7, 1.0, 1.3, 1.6]


def load_summary():
    summary = defaultdict(dict)
    with open(RESULTS / "summary.csv", newline="") as f:
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
    return summary


def load_paired():
    paired = defaultdict(dict)
    with open(RESULTS / "paired_statistical_summary.csv", newline="") as f:
        for r in csv.DictReader(f):
            d = float(r["demand_ratio"])
            p = r["policy"]
            paired[(d, p)] = {
                "mean": float(r["diff_mean"]),
                "ci95_low": float(r["ci95_low"]),
                "ci95_high": float(r["ci95_high"]),
                "se": float(r["se"]),
            }
    return paired


def fig_paired_gain(out: Path) -> None:
    paired = load_paired()
    fig, ax = plt.subplots(figsize=(7.2, 4.5), dpi=300)
    active = ["MSF", "LSF", "MGS", "CMU_MGS", "AUSTERE"]
    x = np.arange(len(DEMANDS))
    width = 0.15
    for idx, pol in enumerate(active):
        means = [paired[(d, pol)]["mean"] for d in DEMANDS]
        ci_err = [paired[(d, pol)]["se"] * 1.96 for d in DEMANDS]
        pos = x + (idx - 2) * width
        ax.bar(
            pos,
            means,
            width,
            yerr=ci_err,
            capsize=3,
            label=LABELS[pol],
            color=COLORS[pol],
            alpha=0.88,
        )
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_xlabel(r"Effective Traffic Intensity ($\rho$)", fontsize=10)
    ax.set_ylabel(r"Additional Expected Lives Saved ($\Delta S$ vs FCFS)", fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(["0.70", "1.00", "1.30", "1.60"])
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(frameon=True, facecolor="white", loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_waiting_times(out: Path, summary) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), dpi=300)
    for pol in POLICIES:
        adm_waits = [summary[(d, pol)]["mean_wait_admitted_hours"]["mean"] for d in DEMANDS]
        ax1.plot(
            DEMANDS,
            adm_waits,
            marker="s",
            label=LABELS[pol],
            color=COLORS[pol],
            linewidth=1.7,
        )
    ax1.set_title("(A)", fontsize=11, fontweight="bold", loc="left", pad=8)
    ax1.set_xlabel(r"Traffic Intensity ($\rho$)", fontsize=10)
    ax1.set_ylabel("Mean Queue Waiting Time (Hours)", fontsize=10)
    ax1.set_xticks(DEMANDS)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(frameon=True, facecolor="white", fontsize=8.5)

    for pol in POLICIES:
        ren_rates = [summary[(d, pol)]["reneging_rate"]["mean"] * 100.0 for d in DEMANDS]
        ax2.plot(
            DEMANDS,
            ren_rates,
            marker="^",
            label=LABELS[pol],
            color=COLORS[pol],
            linewidth=1.7,
        )
    ax2.set_title("(B)", fontsize=11, fontweight="bold", loc="left", pad=8)
    ax2.set_xlabel(r"Traffic Intensity ($\rho$)", fontsize=10)
    ax2.set_ylabel("Reneging Rate (%)", fontsize=10)
    ax2.set_xticks(DEMANDS)
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(frameon=True, facecolor="white", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_sensitivity(out: Path) -> None:
    fig, (ax_n, ax_h) = plt.subplots(1, 2, figsize=(11.2, 4.6), dpi=300)

    sens_data = defaultdict(lambda: defaultdict(list))
    with open(RESULTS / "sensitivity" / "sensitivity_noise.csv", newline="") as f:
        for r in csv.DictReader(f):
            sens_data[float(r["sigma_noise"])][r["policy"]].append(
                float(r["expected_survivors"])
            )

    sigmas = sorted(sens_data.keys())
    for pol in POLICIES:
        means = [np.mean(sens_data[s][pol]) for s in sigmas]
        stds = [
            np.std(sens_data[s][pol], ddof=1) / np.sqrt(len(sens_data[s][pol])) * 1.96
            for s in sigmas
        ]
        ax_n.errorbar(
            sigmas,
            means,
            yerr=stds,
            marker="D",
            capsize=3,
            label=LABELS[pol],
            color=COLORS[pol],
            linewidth=1.6,
            markersize=5,
        )

    ax_n.set_title("(A)", fontsize=11, fontweight="bold", loc="left", pad=8)
    ax_n.set_xlabel(r"Prognostic & LOS Noise ($\sigma_{\mathrm{noise}}$)", fontsize=10)
    ax_n.set_ylabel("Expected Survivors (60 Days)", fontsize=10)
    ax_n.set_xticks(sigmas)
    ax_n.set_xticklabels(["0.00", "0.05", "0.10", "0.20"])
    ax_n.grid(True, linestyle="--", alpha=0.5)
    ax_n.legend(frameon=True, facecolor="white", loc="lower left", fontsize=8, ncol=2)

    betas = [-0.6, 0.0, 0.6, 1.2, 1.8, 2.4]
    alphas = [0.05, 0.18, 0.35, 0.50]
    grid_mat = np.zeros((len(betas), len(alphas)))
    sig_mat = np.zeros((len(betas), len(alphas)), dtype=bool)
    with open(RESULTS / "sensitivity" / "sensitivity_grid_beta_alpha.csv", newline="") as f:
        for r in csv.DictReader(f):
            b_i = betas.index(float(r["beta"]))
            a_i = alphas.index(float(r["alpha"]))
            grid_mat[b_i, a_i] = float(r["cmu_vs_mgs_mean"])
            sig_mat[b_i, a_i] = r["significant_005"].strip().lower() == "true"

    im = ax_h.imshow(grid_mat, cmap="YlGnBu", aspect="auto", origin="lower")
    ax_h.set_title("(B)", fontsize=11, fontweight="bold", loc="left", pad=8)
    ax_h.set_xlabel(
        r"Queue Deterioration Rate $\alpha_{\mathrm{det}}$ ($\mathrm{day}^{-1}$)",
        fontsize=10,
    )
    ax_h.set_ylabel(r"Severity--LOS Coupling $\beta$", fontsize=10)
    ax_h.set_xticks(range(len(alphas)))
    ax_h.set_xticklabels([f"{a:.2f}" for a in alphas])
    ax_h.set_yticks(range(len(betas)))
    ax_h.set_yticklabels([f"{b:+.1f}" if b != 0 else "0.0" for b in betas])
    ax_h.grid(False)

    for i in range(len(betas)):
        for j in range(len(alphas)):
            val = grid_mat[i, j]
            star = "*" if sig_mat[i, j] else ""
            txt_color = "white" if val > 2.2 else "black"
            ax_h.text(
                j,
                i,
                f"{val:+.2f}{star}",
                ha="center",
                va="center",
                color=txt_color,
                fontsize=8.2,
                fontweight="bold",
            )

    fig.colorbar(
        im,
        ax=ax_h,
        fraction=0.046,
        pad=0.04,
        label="Paired Lives Gained (* Holm p < 0.05)",
    )
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir",
        type=Path,
        default=ROOT / "experiments" / "figures",
        help="Directory for the PNG files",
    )
    args = parser.parse_args()
    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    summary = load_summary()
    fig_paired_gain(outdir / "fig_paired_gain.png")
    fig_waiting_times(outdir / "fig_waiting_times.png", summary)
    fig_sensitivity(outdir / "fig_sensitivity.png")
    print(f"Wrote figures to {outdir}")


if __name__ == "__main__":
    main()
