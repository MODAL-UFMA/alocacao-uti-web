# Point-by-Point Response to Referees (Round 2)

**Manuscript:** *Dynamic ICU Bed Allocation Under Resource Scarcity: A Discrete-Event Simulation Integrating Multi-Type Beds and Triage Policies*  
**Journal:** *Computers & Operations Research*  
**Authors:** Carlos Eduardo Veras Gomes, João Augusto Ferreira Nunes de Carvalho, Francisco Glaubos Nunes Clímaco  

We thank the Referee for the insightful and constructive second-round evaluation. In this revision, we have eliminated all synthetic uniform parameter assumptions by calibrating specialty-specific distributions (Adult ICU, Coronary Care Unit, Pediatric ICU, and Neonatal ICU) directly from published Brazilian multicenter intensive care registries (AMIB/Epimed, ORCHESTRA, and the Brazilian Neonatal Research Network), combined with the verified DATASUS/CNES bed capacities of HU-UFMA (55 beds). Furthermore, we implemented all requested simulation and optimization enhancements—including exact effective traffic intensity normalization ($\rho_{\text{eff}} = \rho$), complete post-horizon cohort drainage, a clairvoyant time-indexed LP/MILP upper bound via HiGHS, a two-parameter sensitivity heatmap ($\beta \times \alpha_{\text{det}}$), a multi-parameter clinical noise study across 100 replications, and an explicit ablation of adult–coronary bed pooling.

Below we provide a point-by-point response detailing how each Major Comment (M1–M8), Minor Comment (1–12), and Question for the Authors has been resolved in the revised manuscript (`doc/artigo-elsevier/main.tex` and `main.pdf`).

---

## Response to Major Comments

### M1. Remove response-to-reviewer language from the manuscript
> *“Remove from the article the language written for the reviewers... The contribution must be rewritten in affirmative terms.”*

* **Response:** Fully corrected. We purged all meta-commentary and reviewer-directed phrases from the Abstract, Introduction, Section 5.2, and Conclusions. The Abstract and Contributions list (Section 1) are now framed strictly in affirmative scientific terms for the reader.

### M2. Nominal $\rho$ underestimates congestion ($\rho_{\text{eff}} \approx 1.12\rho$)
> *“By Eq. (3), $E[\text{LOS}] = \mu_{\text{los}}(0.6 + \beta(1 - P_{\text{out}}))$... Hence effective $\rho$ is approximately $1.12\rho$... Either compute $\lambda$ with the effective mean LOS, or rename the regimes.”*

* **Response:** Resolved exactly in both the mathematical formulation and the simulation engine (`generate_patient_stream` in `experiments/dynamic_simulation.py`). In Eq. (4) of the revised manuscript, the severity multiplier is centered around the pool's mean baseline severity $\mathbb{E}[1 - P_{\text{out}}^{j}]$:
  $$\mathbb{E}[\text{LOS}_i] = \mu_{\text{los}, j(i)} \cdot \max\!\left\{ 0.35,\; 1 + \beta \Big( (1 - P_{\text{out}}^i) - \mathbb{E}[1 - P_{\text{out}}^{j(i)}] \Big) \right\}$$
  This guarantees that the unconditional expected length of stay in each pool $j$ equals $\mathbb{E}[\text{LOS}_i] = \mu_{\text{los}, j}$ for all $\beta \ge 0$, so $\lambda_j(\rho) = \rho C_j / \mu_{\text{los}, j}$ yields an exact effective traffic intensity $\rho_{\text{eff}} = \rho$. As shown in Table 3, at $\rho = 0.70$ the observed steady-state occupancy is now $68.8\%$–$68.9\%$ with $1.3\%$–$1.4\%$ reneging ($0.70 \times (1 - 0.014) = 69.0\%$), and at $\rho = 1.00$ occupancy is $88.7\%$–$89.4\%$ with $9.8\%$–$10.8\%$ reneging, in exact agreement with Little's Law.

### M3. Trade-off between benefit and bed-days is too weak; sensitivity heatmap needed
> *“A sensitivity analysis over $\beta$, $\alpha$, $CV_{\text{los}}$ and the range of $W_{\max}$ (e.g., a heatmap) is needed to show where CMU-MGS separates from MGS and where AUSTERE or MSF become competitive.”*

* **Response:** Conducted and reported in Section 5.4 and Figure 4B (`fig_sensitivity.png`). First, our empirical calibration from Brazilian ICU registries (Table 2, with $\beta = 1.2$) already establishes a statistically significant separation between CMU-MGS and MGS at $\rho = 1.60$ ($+0.81 \pm 0.25$ expected lives, paired $t = 3.25, p = 0.0016$). Second, we executed a 20-cell parametric sensitivity grid over $\beta \in \{0.0, 0.6, 1.2, 1.8, 2.4\}$ and $\alpha_{\text{det}} \in \{0.05, 0.18, 0.35, 0.50\}\text{ day}^{-1}$ (Figure 4B):
  - At $\beta = 0.0$ (severity-independent LOS), CMU-MGS and MGS produce identical rankings ($\Delta S_{\text{CMU}-\text{MGS}} = 0.00$).
  - At $\beta = 1.8$, CMU-MGS saves $+1.98$ to $+2.94$ more expected lives than MGS ($t \in [5.47, 7.77], p < 0.001$).
  - At $\beta = 2.4$, CMU-MGS saves $+3.37$ to $+4.21$ more expected lives than MGS ($t \in [8.32, 10.20], p < 0.001$).

### M4. Principled formulation of AUSTERE policy
> *“Eq. (11) multiplies the $c\mu$ index by $(1 + 1/\tau)$ with $\tau$ floored at $0.05$ day, multiplying priority by up to 21... Implement their index adapted to this setting, or calibrate the functional form and floor of $\tau$.”*

* **Response:** Reformulated in Section 3.2, Eq. (12). Following Sun, Argon & Ziya (2018), our revised AUSTERE policy prioritizes patients according to the instantaneous rate of marginal survival loss (combining continuous exponential deterioration $\alpha_{\text{det}}^{j(i)}$ and bounded deadline hazard with $\tau_i(t) = \max(0.25, t_{\text{arr}}^i + W_{\max}^i - t)$) normalized by expected stay $\mathbb{E}[\text{LOS}_i]$:
  $$s_i^{\text{AUST}}(t) = \frac{\Delta P_i(t - t_{\text{arr}}^i)}{\max(0.2, \mathbb{E}[\text{LOS}_i])} \left( 1 + \alpha_{\text{det}}^{j(i)} + \frac{0.5}{\tau_i(t) + 0.5} \right)$$
  As shown in Table 3, this principled formulation eliminates pathological deadline chasing: AUSTERE achieves a low admitted wait time of $10.89$ hours at $\rho = 1.60$ (comparable to $9.56$ hours for CMU-MGS, rather than $32.4$ hours previously) and is the top-performing policy at $\rho = 0.70$ ($238.75$ lives) and $\rho = 1.30$ ($389.22$ lives).

### M5. Offline Hindsight Upper Bound (Time-Indexed LP/MILP)
> *“An OR journal will expect some measure of distance to optimality... An offline (clairvoyant) time-indexed allocation MILP or its linear relaxation maximizing Eq. (12)... Reporting the gap of CMU-MGS relative to this bound turns ‘dominates heuristics’ into a quantitative statement.”*

* **Response:** Formulated in Section 3.4, Eqs. (17)–(20), and solved for every single replication across all congestion regimes using the HiGHS optimization solver (`solve_offline_milp_bound` in `experiments/dynamic_simulation.py`). The hindsight upper bound $S_{\text{UB}}$ is reported in Table 3 and plotted in Figure 1 (`fig_survivors.png`). Across $\rho \in \{0.70, 1.00, 1.30, 1.60\}$, the optimality gap $(S_{\text{UB}} - S_{\text{exp}}^{\text{CMU-MGS}})/S_{\text{UB}}$ of online CMU-MGS is $0.52\%$, $3.51\%$, $7.47\%$, and $9.93\%$, respectively.

### M6. Fair multi-parameter noise across all policies (100 replications)
> *“Noise only enters $\Delta P$... To compare informational requirements fairly, noise must be applied to $P_{\text{in}}$ and $P_{\text{out}}$ (so all clinical rules degrade) and also to $E[\text{LOS}]$, using 100 replications with Holm adjustment.”*

* **Response:** Implemented in Section 3.2.1, Eq. (13), and Section 5.4.1 (Figure 4A). Independent Gaussian perturbations $\mathcal{N}(0, \sigma_{\text{noise}}^2)$ are now applied simultaneously to $P_{\text{out}}^i$, $P_{\text{in},0}^i$, and $\mathbb{E}[\text{LOS}_i]$ across all 100 replications for $\sigma_{\text{noise}} \in \{0.00, 0.05, 0.10, 0.20\}$. Consequently, MSF, LSF, MGS, CMU-MGS, and AUSTERE all degrade under imperfect information. At $\sigma_{\text{noise}} = 0.20$, MGS ($444.00$ survivors) and CMU-MGS ($443.40$ survivors) still save $+12.87$ and $+12.27$ more expected lives than FCFS ($431.14$ survivors, $p_{\text{Holm}} < 0.001$).

### M7. End-of-horizon truncation distortion
> *“Patients still in the queue at $T$ are counted with $P_{\text{out}}$... Since the cohort arriving in $[T_w, T)$ is fixed, the simulation should continue after $T$ until every evaluated patient is admitted or reneges.”*

* **Response:** Fixed in `simulate_policy` (`experiments/dynamic_simulation.py`) and documented in Section 3.3. The simulation engine now processes all discharge, admission, and timeout events beyond $T_{\text{warm}} + T$ until every patient in the evaluation cohort $\mathcal{I}_{\text{eval}} = \{i : T_{\text{warm}} \le t_{\text{arr}}^i < T_{\text{warm}} + T\}$ has either been admitted or reached their reneging deadline $W_{\max}^i$. Thus, $\mathcal{A}^\pi \cup \mathcal{R}^\pi = \mathcal{I}_{\text{eval}}$ holds without artificial truncation.

### M8. Specification and ablation of Adult–Coronary bed sharing
> *“Specify clearly when a coronary bed serves an adult patient and how candidates compete... An ablation without this sharing is needed to show whether it changes the results.”*

* **Response:** Clarified in Section 3.1.3 and tested via a 100-replication paired ablation across all regimes in Section 5.3 and Table 5 (`ablation_overflow.csv`).
  - **Rule Specification:** Adult and coronary pools follow a strict hierarchical partial-pooling rule: native queue candidates always hold primary priority ($\mathcal{Q}_j(t) \ne \emptyset$ is served first); cross-unit overflow occurs only when the native queue of the vacant bed's unit is empty ($\mathcal{Q}_j(t) = \emptyset$). Thus, native and overflow candidates never compete simultaneously for the same bed.
  - **Ablation Findings:** Table 5 shows that adult–coronary overflow is highly beneficial at moderate and balanced traffic intensities ($\rho = 1.00$), admitting $+11.78$ more patients and saving $+3.46 \pm 0.14$ expected lives under CMU-MGS ($t = 25.38, p < 0.001$) and $+3.90 \pm 0.18$ lives under FCFS. Under extreme overload ($\rho = 1.60$), both units are nearly $100\%$ occupied with persistent native queues, so the overflow gain diminishes to $+0.39 \pm 0.20$ lives ($p = 0.052$).

---

## Response to Minor Comments

1. **Eq. (3) Log-Normal parameters:** Restored explicitly in Eq. (5): $\sigma_j = \sqrt{\ln(1 + CV_{\text{los}, j}^2)}$ and $\mu_i = \ln(\mathbb{E}[\text{LOS}_i]) - \frac{1}{2}\sigma_j^2$.
2. **Eq. (12) notation and complement set:** Defined the reneged/unadmitted complement set $\mathcal{R}^\pi = \mathcal{I}_{\text{eval}} \setminus \mathcal{A}^\pi$ explicitly in Section 3.3 and used $i \in \mathcal{R}^\pi$ in Eqs. (14)–(15).
3. **Realized survivors metric:** Now explicitly reported for every regime and policy in Table 3 (“Realized Survivors” column).
4. **Formatting of $p$-values:** Replaced astronomical tiny $p$-values with $p_{\text{Holm}} < 0.001$ throughout the text and Table 4, alongside $95\%$ paired confidence intervals and relative percentage effects.
5. **Total arrivals in Table 2 (now Table 3):** Included the “Total Arrivals” column in Table 3 for every regime, as well as pool-specific arrivals in Table 5.
6. **Discussion of LSF admission volume:** Discussed in Section 5.1 (item 2), highlighting that LSF admits the most patients ($473.4$ at $\rho = 1.60$) because milder patients have shorter stays ($6.92$ days vs. $7.43$ days under MSF) via Eq. (4).
7. **Citations supporting claims:**
   - Replaced King et al. with Valeva et al. \cite{Valeva_2023} for cross-unit flexible bed sharing (keeping King et al. \cite{king2019modelling} and Guinsburg et al. \cite{guinsburg2016death} for pediatric/neonatal specialization).
   - Cited Cardoso et al. \cite{cardoso2011impact} and Sun et al. \cite{sun2018patient} for pre-ICU waiting deterioration and abandonment.
   - Replaced Smith (1956) with Buyukkoc, Varaiya & Walrand (1985, *Advances in Applied Probability*, DOI: `10.2307/1427064`) \cite{buyukkoc1985cmu} for the $c\mu$ rule.
8. **Bibliography fixes:** Added issue number `number={3}` to Craxì et al. \cite{craxi2020rationing}; replaced the broken thesis DOI on Bilbao (2022) with the official Universidad Pública de Navarra repository handle URL; updated access dates on CNES and EBSERH records.
9. **Data and Code Availability URL:** Provided the full public GitHub repository URL (`https://github.com/MODAL-UFMA/alocacao-uti-web`).
10. **Expanded Related Work section:** Expanded Section 2 into a four-paragraph critical synthesis explicitly contrasting our framework against Chan et al. (2012), Kim et al. (2015), Mills et al. (2013), and Sun et al. (2018).
11. **Empirical differentiation across pools:** Replaced synthetic identical distributions with empirical specialty-specific parameters from AMIB/Epimed \cite{soares2024update, zampieri2019icu}, the Brazilian Neonatal Research Network \cite{guinsburg2016death}, and Cardoso et al. \cite{cardoso2011impact} in Table 2 (with neonatal mean LOS of $11.5$ days, adult $6.5$ days, pediatric $6.0$ days, and coronary $4.8$ days).
12. **Highlights phrasing:** Rewritten as `"CMU-MGS saves 20.8 more expected lives than FCFS at \rho=1.6 (p_Holm<0.001)."` (all 5 highlights strictly $\le 85$ characters).
