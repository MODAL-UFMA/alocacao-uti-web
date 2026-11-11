# Response to Reviewers

**Manuscript:** Dynamic ICU Bed Allocation Under Resource Scarcity: A Discrete-Event Simulation Integrating Multi-Type Beds and Triage Policies  
**Journal:** Computers & Operations Research  
**Recommendation addressed:** Major revision

We thank the reviewer for a precise and constructive report. Below we map each comment to the revision. All numerical claims refer to the revised simulator (warm-up, deterioration, severity-dependent LOS, adult–coronary overflow, six policies, Holm–Bonferroni).

---

## Major comments

### M1 — Near-tautological main result; weak benchmarks
**Action taken.**
- (a) Waiting-time deterioration: \(P_{\mathrm{in}}(t)\) decays exponentially in waiting time (Eq. 2 in the revised manuscript).
- (b) Severity-dependent LOS: \(\mathbb{E}[\mathrm{LOS}]\) increases with \((1-P_{\mathrm{out}})\), creating an explicit \(\Delta P\) vs bed-day trade-off.
- (c) Stronger benchmarks: CMU-MGS (\(\Delta P/\mathbb{E}[\mathrm{LOS}]\)) and AUSTERE (deadline-weighted \(c\mu\)-style index inspired by Sun, Argon & Ziya, 2018).

**Result.** Under \(\rho=1.6\), CMU-MGS (+58.57 expected lives vs FCFS) slightly edges MGS (+57.79) and clearly beats AUSTERE (+32.07), MSF (+29.06) and LSF (+39.03). The contribution is no longer “greedy \(\Delta P\) beats weak heuristics.”

### M2 — Occupancy vs Little’s law
**Root cause of the old bug.** The previous runs started empty with no warm-up, truncated effective LOS in the occupancy integral inconsistently, and used 45 beds while reporting a mismatched evaluation window.

**Fix.** 15-day warm-up, 60-day evaluation window, occupancy integrated only on \([T_w,T]\), and inclusion of the 10-bed coronary unit (total 55 beds).

**Revised numbers (FCFS):**
| \(\rho\) | Admitted | Occupancy | Implied mean LOS from bed-days/admissions |
|---:|---:|---:|---:|
| 0.7 | 457.0 | 77.7% | ≈5.61 d |
| 1.6 | 590.1 | 99.9% | ≈5.59 d |

At \(\rho=1.6\), beds are essentially full while patients still queue, as expected.

### M3 — Abstract vs Table 3; multiple comparisons; practical magnitude
**Fix.** The abstract no longer claims indistinguishability at \(\rho=0.7\). Paired tables now report mean difference, 95% CI, relative %, \(t\), and Holm–Bonferroni \(p\) over 20 tests. At \(\rho=0.7\), relative gains are \(<0.3\%\) (detectable under CRN, negligible in practice). At \(\rho=1.6\), CMU-MGS relative gain is \(+11.32\%\).

### M4 — Overstated calibration
**Fix.** Every calibration claim is narrowed: only CNES bed capacities are empirical. Clinical distributions are labeled synthetic, shared across pools unless noted, and stress-tested via noise sensitivity. Highlights/abstract/contributions were rewritten accordingly.

### M5 — Multi-type structure without coupling; coronary unit; per-pool results
**Fix.** Coronary (UCO, 10 beds) is included. Bidirectional adult–coronary overflow is implemented. Pediatric/neonatal pools remain exclusive. Per-pool admissions and occupancy are reported (Table 4).

### M6 — Incomplete simulation methodology; reproducibility
**Fix.** The manuscript now states: warm-up \(T_w=15\); end-of-horizon accounting for queued/bed patients; dedicated random streams for arrivals, clinical covariates, LOS, outcomes and noise; Python 3.12; stream-specific SHA-256 seeds; code/data availability section.

### M7 — Misinterpreted waiting-time mechanism
**Fix.** We no longer claim that MGS “releases beds efficiently.” LOS is exogenous to policy. Admitted waits and reneging rates are reported separately. Shorter admitted waits under priority rules come from queue jumping / reneging of low-priority patients.

### M8 — Normative over-reach; imperfect information; equity; limitations
**Fix.** Conclusions are conditional on maximizing expected survivors under known/noisy salvage margins. Added sensitivity to noisy \(\widehat{\Delta P}\) (\(\sigma\in\{0,0.05,0.1,0.2\}\)). Added a Limitations section discussing equity, estimation error and synthetic clinical inputs.

### M9 — Literature gaps
**Fix.** Added and discussed Kim et al. (2015), Chan et al. (2012), Mills et al. (2013), Sun et al. (2018), Argon & Ziya (2009). Removed inappropriate Dantzig/Wolsey ICU-allocation citations. Updated Table 1. Corrected Mills bibliographic metadata (author, pages, DOI).

---

## Minor comments

| Comment | Resolution |
|---|---|
| Highlights >85 characters; “lives” vs expected lives | Rewritten; all highlights shortened; wording uses expected lives |
| Leftover Markdown `**...**` | Removed |
| MGS acronym mismatch; MSF vs rule of rescue | Renamed explanation to Marginal Gain for Survival; MSF clarified as urgency score, not ethical rule of rescue |
| Notation (\(Q\neq\emptyset\), \(i\notin\mathcal{A}\), benefit definition) | Corrected |
| Single \(\rho\) for all pools | Stated explicitly |
| Bed cleaning / early discharge | Acknowledged as omitted |
| Table 1 fidelity | Rebuilt against cited papers |
| References (duplicates, thesis venue, encoding, DOIs) | Cleaned `bib.bib` |
| Email `dicente` → `discente` | Corrected |
| Missing Limitations / Data-Code / CRediT / COI | Added |
| Figures under-discussed; Fig.1 vs Table 2 | Each figure has an interpretive paragraph; tables and figures now complementary |
| Length/depth / no sensitivity | Expanded methods/results; added noise sensitivity figure |

---

## Direct answers to the reviewer’s questions

1. **Why was occupancy at \(\rho=1.6\) far below 100%?** It was a simulator/definition issue (no warm-up / inconsistent occupancy accounting / capacity mismatch). Revised occupancy is 99.9% under FCFS at \(\rho=1.6\).
2. **Patients still queued at \(T\); LOS beyond \(T\)?** Queued non-admitted patients contribute \(P_{\mathrm{out}}\). Occupancy integrates only on \([T_w,T]\); residual LOS after \(T\) does not inflate occupancy.
3. **Ranking if \(P_{\mathrm{in}}\) decays and LOS depends on severity?** CMU-MGS ≳ MGS ≫ LSF > AUSTERE > MSF ≫ FCFS under severe surge.
4. **Robustness of MGS under noisy \(\Delta P\)?** At \(\sigma=0.2\), MGS/CMU-MGS still save ~+39 expected lives over FCFS and remain ahead of AUSTERE.
