import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from experiments.static_simulation import Patient, TYPES, allocate, evaluate, generate, run

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"global": 0.7, "neonatal": 0.6, "pediatric": 0.8, "adult": 0.7}


def independent_objective(patients, chosen, capacities, policy, mode, weight, power):
    # Fórmula de referência independente do algoritmo por prefixos.
    values = {"MGS": lambda p: p.p_in - p.p_out,
              "LSF": lambda p: p.p_in, "MSF": lambda p: 1 - p.p_out}
    score = sum(values[policy](p) for p in patients if p.id in chosen)
    if mode == "global" and sum(capacities.values()):
        score -= weight * abs(len(chosen) / sum(capacities.values()) - TARGETS["global"]) ** power
    elif mode == "per_type":
        active = [t for t in TYPES if capacities[t]]
        if active:
            score -= weight / len(active) * sum(abs(sum(p.id in chosen and p.bed_type == t for p in patients) / capacities[t] - TARGETS[t]) ** power for t in active)
    return score


class StaticSimulationTests(unittest.TestCase):
    def test_exact_against_exhaustive_enumeration(self):
        rng = random.Random(92)
        for _ in range(15):
            caps = {t: rng.randrange(3) for t in TYPES}
            patients = []
            for i in range(6):
                p_out = rng.random()
                patients.append(Patient(i, rng.choice(TYPES), p_out + (1-p_out)*rng.random(), p_out, i))
            feasible = []
            for flags in itertools.product((False, True), repeat=len(patients)):
                chosen = {p.id for p, flag in zip(patients, flags) if flag}
                if all(sum(p.id in chosen and p.bed_type == t for p in patients) <= caps[t] for t in TYPES):
                    feasible.append(chosen)
            for policy, mode, power, weight in itertools.product(("MGS", "LSF", "MSF"), ("none", "global", "per_type"), (1, 2), (0, 2, 100)):
                actual = allocate(patients, caps, policy, TARGETS, mode, weight, power)
                expected = max(independent_objective(patients, c, caps, policy, mode, weight, power) for c in feasible)
                self.assertIn(actual, feasible)
                self.assertAlmostEqual(independent_objective(patients, actual, caps, policy, mode, weight, power), expected)

    def test_priority_and_ties(self):
        caps = {"neonatal": 0, "pediatric": 0, "adult": 1}
        patients = [Patient(1, "adult", .9, .8, 0), Patient(2, "adult", .8, .1, 1)]
        self.assertEqual(allocate(patients, caps, "MGS", TARGETS), {2})
        self.assertEqual(allocate(patients, caps, "LSF", TARGETS), {1})
        self.assertEqual(allocate(patients, caps, "MSF", TARGETS), {2})
        self.assertEqual(allocate(patients, caps, "FCFS", TARGETS), {1})
        ties = [Patient(2, "adult", .5, .5, 1), Patient(1, "adult", .5, .5, 0)]
        self.assertEqual(allocate(ties, caps, "MGS", TARGETS), {1})

    def test_zero_capacity_incompatibility_and_empty(self):
        patient = Patient(1, "pediatric", .9, .2, 0)
        for policy in ("MGS", "LSF", "MSF", "FCFS"):
            self.assertEqual(allocate([patient], {t: 0 for t in TYPES}, policy, TARGETS), set())
            self.assertEqual(allocate([patient], {"neonatal": 0, "pediatric": 0, "adult": 2}, policy, TARGETS), set())
            self.assertEqual(allocate([], {t: 1 for t in TYPES}, policy, TARGETS), set())

    def test_invalid_probabilities_rejected(self):
        for p_in, p_out in ((5, 4), (.2, .8), (float("nan"), .1)):
            with self.assertRaises(ValueError):
                allocate([Patient(1, "adult", p_in, p_out, 0)], {t: 1 for t in TYPES}, "MGS", TARGETS)

    def test_metrics_and_common_outcomes(self):
        patients = [Patient(1, "adult", .9, .1, 0), Patient(2, "adult", .5, .2, 1)]
        row = evaluate(patients, {1}, {1: .4, 2: .3}, {t: 1 for t in TYPES}, TARGETS,
                       {"mode": "none", "weight": 0, "power": 2}, "MGS")
        self.assertAlmostEqual(row["expected_survivors"], 1.1)
        self.assertEqual(row["realized_survivors"], 1)

    def test_reproduction_and_fcfs_invariance(self):
        config = json.loads((ROOT / "experiments/configs/pilot.json").read_text())
        config["replications"] = 2
        patients, _ = generate(config, 2.0, 0)
        fcfs = [allocate(patients, config["capacities"], "FCFS", config["targets"], s["mode"], s["weight"], s["power"]) for s in config["penalties"]]
        self.assertTrue(all(c == fcfs[0] for c in fcfs))
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            run(config, a)
            run(config, b)
            for name in ("patients.csv", "runs.csv", "summary.csv", "paired_differences.csv", "metadata.json"):
                self.assertEqual((a/name).read_bytes(), (b/name).read_bytes())
            with self.assertRaises(ValueError):
                run(config, a)


if __name__ == "__main__":
    unittest.main()
