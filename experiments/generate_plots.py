import matplotlib.pyplot as plt
import csv
from collections import defaultdict
import numpy as np

fig_dir = 'alocacao-uti-web/doc/artigo-elsevier'

# 1. Carrega dados de summary.csv e offline_ub.csv
summary = defaultdict(dict)
with open('alocacao-uti-web/experiments/results/dynamic_huufma/summary.csv') as f:
    for r in csv.DictReader(f):
        d = float(r['demand_ratio'])
        p = r['policy']
        m = r['metric']
        summary[(d, p)][m] = {
            'mean': float(r['mean']),
            'ci95_low': float(r['ci95_low']),
            'ci95_high': float(r['ci95_high']),
            'se': float(r['standard_error'])
        }

ub_data = defaultdict(list)
with open('alocacao-uti-web/experiments/results/dynamic_huufma/offline_ub.csv') as f:
    for r in csv.DictReader(f):
        ub_data[float(r['demand_ratio'])].append(float(r['expected_survivors']))

demands = [0.7, 1.0, 1.3, 1.6]
policies = ['FCFS', 'MSF', 'LSF', 'AUSTERE', 'MGS', 'CMU_MGS']
colors = {
    'FCFS': '#7f7f7f',
    'MSF': '#d62728',
    'LSF': '#ff7f0e',
    'AUSTERE': '#9467bd',
    'MGS': '#1f77b4',
    'CMU_MGS': '#2ca02c',
    'OFFLINE_UB': '#111111'
}

# --- FIGURA 1: fig_survivors.png (Inclui Hindsight MILP/LP Upper Bound) ---
fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
ub_means = [np.mean(ub_data[d]) for d in demands]
ub_yerr = [np.std(ub_data[d]) / np.sqrt(len(ub_data[d])) * 1.96 for d in demands]
ax.errorbar(demands, ub_means, yerr=ub_yerr, marker='*', linestyle='--', capsize=4,
            label='Hindsight LP/MILP Upper Bound', color=colors['OFFLINE_UB'], linewidth=2.0, markersize=8)

for pol in policies:
    means = [summary[(d, pol)]['expected_survivors']['mean'] for d in demands]
    yerr = [summary[(d, pol)]['expected_survivors']['se'] * 1.96 for d in demands]
    ax.errorbar(demands, means, yerr=yerr, marker='o', capsize=4, label=pol, color=colors[pol], linewidth=1.8)

ax.set_title('Expected Survivors vs. Hindsight Upper Bound (60-Day Window)', fontsize=11.5, fontweight='bold')
ax.set_xlabel(r'Effective Traffic Intensity ($\rho = \lambda_j \cdot \mathbb{E}[\mathrm{LOS}_j] / C_j$)', fontsize=10)
ax.set_ylabel('Expected Total Survivors (Lives Saved)', fontsize=10)
ax.set_xticks(demands)
ax.set_xticklabels(['0.70 (Normal)', '1.00 (Balanced)', '1.30 (Moderate Surge)', '1.60 (Severe Surge)'])
ax.grid(True, linestyle='--', alpha=0.5)
ax.legend(frameon=True, facecolor='white', loc='upper left', fontsize=8.5)
plt.tight_layout()
plt.savefig(f'{fig_dir}/fig_survivors.png')
plt.close()

# --- FIGURA 2: fig_paired_gain.png ---
paired = defaultdict(dict)
with open('alocacao-uti-web/experiments/results/dynamic_huufma/paired_statistical_summary.csv') as f:
    for r in csv.DictReader(f):
        d = float(r['demand_ratio'])
        p = r['policy']
        paired[(d, p)] = {
            'mean': float(r['diff_mean']),
            'ci95_low': float(r['ci95_low']),
            'ci95_high': float(r['ci95_high']),
            'se': float(r['se'])
        }

fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
active_pols = ['MSF', 'LSF', 'MGS', 'AUSTERE', 'CMU_MGS']
x = np.arange(len(demands))
width = 0.15

for idx, pol in enumerate(active_pols):
    means = [paired[(d, pol)]['mean'] for d in demands]
    ci_err = [paired[(d, pol)]['se'] * 1.96 for d in demands]
    pos = x + (idx - 2) * width
    ax.bar(pos, means, width, yerr=ci_err, capsize=3, label=pol, color=colors[pol], alpha=0.88)

ax.axhline(0, color='black', linestyle='--', linewidth=0.8)
ax.set_title('CRN Paired Survival Gain Relative to FCFS Hospital Baseline', fontsize=11.5, fontweight='bold')
ax.set_xlabel(r'Effective Traffic Intensity ($\rho$)', fontsize=10)
ax.set_ylabel(r'Additional Expected Lives Saved ($\Delta S$ vs FCFS)', fontsize=10)
ax.set_xticks(x)
ax.set_xticklabels(['0.70', '1.00', '1.30', '1.60'])
ax.grid(True, linestyle='--', alpha=0.5)
ax.legend(frameon=True, facecolor='white', loc='upper left', fontsize=9)
plt.tight_layout()
plt.savefig(f'{fig_dir}/fig_paired_gain.png')
plt.close()

# --- FIGURA 3: fig_waiting_times.png ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), dpi=300)

for pol in policies:
    adm_waits = [summary[(d, pol)]['mean_wait_admitted_hours']['mean'] for d in demands]
    ax1.plot(demands, adm_waits, marker='s', label=pol, color=colors[pol], linewidth=1.7)
ax1.set_title('(A) Admitted Patients Waiting Time', fontsize=11, fontweight='bold')
ax1.set_xlabel(r'Traffic Intensity ($\rho$)', fontsize=10)
ax1.set_ylabel('Mean Queue Waiting Time (Hours)', fontsize=10)
ax1.set_xticks(demands)
ax1.grid(True, linestyle='--', alpha=0.5)
ax1.legend(frameon=True, facecolor='white', fontsize=8.5)

for pol in policies:
    ren_rates = [summary[(d, pol)]['reneging_rate']['mean'] * 100.0 for d in demands]
    ax2.plot(demands, ren_rates, marker='^', label=pol, color=colors[pol], linewidth=1.7)
ax2.set_title('(B) Queue Reneging / Abandonment Rate', fontsize=11, fontweight='bold')
ax2.set_xlabel(r'Traffic Intensity ($\rho$)', fontsize=10)
ax2.set_ylabel('Reneging Rate (%)', fontsize=10)
ax2.set_xticks(demands)
ax2.grid(True, linestyle='--', alpha=0.5)
ax2.legend(frameon=True, facecolor='white', fontsize=8.5)

plt.tight_layout()
plt.savefig(f'{fig_dir}/fig_waiting_times.png')
plt.close()

# --- FIGURA 4: fig_sensitivity.png (Painel Duplo: Ruído M6 + Heatmap Beta x Alpha M3) ---
fig, (ax_n, ax_h) = plt.subplots(1, 2, figsize=(11, 4.4), dpi=300)

sens_data = defaultdict(lambda: defaultdict(list))
with open('alocacao-uti-web/experiments/results/dynamic_huufma/sensitivity/sensitivity_noise.csv') as f:
    for r in csv.DictReader(f):
        sens_data[float(r['sigma_noise'])][r['policy']].append(float(r['expected_survivors']))

sigmas = sorted(sens_data.keys())
for pol in ['FCFS', 'MSF', 'LSF', 'AUSTERE', 'MGS', 'CMU_MGS']:
    means = [np.mean(sens_data[s][pol]) for s in sigmas]
    stds = [np.std(sens_data[s][pol]) / np.sqrt(len(sens_data[s][pol])) * 1.96 for s in sigmas]
    ax_n.errorbar(sigmas, means, yerr=stds, marker='D', capsize=3, label=pol, color=colors[pol], linewidth=1.6, markersize=5)

ax_n.set_title(r'(A) Robustness to Clinical Noise ($\rho = 1.6$)', fontsize=11, fontweight='bold')
ax_n.set_xlabel(r'Prognostic & LOS Noise ($\sigma_{\mathrm{noise}}$)', fontsize=10)
ax_n.set_ylabel('Expected Survivors (60 Days)', fontsize=10)
ax_n.set_xticks(sigmas)
ax_n.set_xticklabels(['0.00', '0.05', '0.10', '0.20'])
ax_n.grid(True, linestyle='--', alpha=0.5)
ax_n.legend(frameon=True, facecolor='white', loc='lower left', fontsize=8, ncol=2)

# Painel B: Heatmap Beta x Alpha (CMU_MGS minus MGS)
betas = [0.0, 0.6, 1.2, 1.8, 2.4]
alphas = [0.05, 0.18, 0.35, 0.50]
grid_mat = np.zeros((len(betas), len(alphas)))
with open('alocacao-uti-web/experiments/results/dynamic_huufma/sensitivity/sensitivity_grid_beta_alpha.csv') as f:
    for r in csv.DictReader(f):
        b_i = betas.index(float(r['beta']))
        a_i = alphas.index(float(r['alpha']))
        grid_mat[b_i, a_i] = float(r['cmu_vs_mgs_mean'])

im = ax_h.imshow(grid_mat, cmap='YlGnBu', aspect='auto', origin='lower')
ax_h.set_title(r'(B) CMU-MGS Gain Over MGS ($\Delta S_{\mathrm{CMU}-\mathrm{MGS}}$)', fontsize=11, fontweight='bold')
ax_h.set_xlabel(r'Queue Deterioration Rate $\alpha_{\mathrm{det}}$ ($\mathrm{day}^{-1}$)', fontsize=10)
ax_h.set_ylabel(r'Severity--LOS Coupling $\beta$', fontsize=10)
ax_h.set_xticks(range(len(alphas)))
ax_h.set_xticklabels([f'{a:.2f}' for a in alphas])
ax_h.set_yticks(range(len(betas)))
ax_h.set_yticklabels([f'{b:.1f}' for b in betas])
ax_h.grid(False)

for i in range(len(betas)):
    for j in range(len(alphas)):
        val = grid_mat[i, j]
        txt_color = 'white' if val > 2.2 else 'black'
        ax_h.text(j, i, f'{val:+.2f}', ha='center', va='center', color=txt_color, fontsize=8.5, fontweight='bold')

fig.colorbar(im, ax=ax_h, fraction=0.046, pad=0.04, label='Paired Lives Gained (CMU-MGS vs MGS)')
plt.tight_layout()
plt.savefig(f'{fig_dir}/fig_sensitivity.png')
plt.close()

print('Todas as 4 figuras atualizadas com sucesso!')
