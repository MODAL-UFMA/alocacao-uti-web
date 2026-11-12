"""Testes unitários e de integração para a simulação dinâmica de leitos de UTI."""
import unittest
from experiments.dynamic_simulation import (
    DynamicPatient,
    generate_patient_stream,
    simulate_policy,
    solve_offline_milp_bound,
    TYPES,
    POLICIES,
)


class DynamicSimulationTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "seed": 42,
            "warmup_days": 5.0,
            "horizon_days": 20.0,
            "capacities": {"neonatal": 4, "pediatric": 2, "adult": 6, "coronary": 3},
            "demand_ratios": [0.7, 1.2],
            "sev_los_beta": 1.2,
            "allow_overflow": True,
        }

    def test_patient_stream_generation(self):
        patients = generate_patient_stream(self.config, demand_ratio=1.0, replication=0)
        self.assertGreater(len(patients), 0)
        for i in range(len(patients) - 1):
            self.assertLessEqual(patients[i].arrival_time, patients[i + 1].arrival_time)
            self.assertIn(patients[i].bed_type, TYPES)
            self.assertLessEqual(patients[i].p_out, patients[i].p_in_0)
            self.assertGreater(patients[i].los, 0.0)
            self.assertGreater(patients[i].max_wait, 0.0)

    def test_crn_reproducibility(self):
        p1 = generate_patient_stream(self.config, demand_ratio=1.0, replication=0)
        p2 = generate_patient_stream(self.config, demand_ratio=1.0, replication=0)
        self.assertEqual(len(p1), len(p2))
        for a, b in zip(p1, p2):
            self.assertEqual(a.id, b.id)
            self.assertEqual(a.arrival_time, b.arrival_time)
            self.assertEqual(a.p_in_0, b.p_in_0)
            self.assertEqual(a.los, b.los)

    def test_capacity_and_occupancy_bounds(self):
        patients = generate_patient_stream(self.config, demand_ratio=1.5, replication=1)
        for pol in POLICIES:
            res = simulate_policy(
                patients,
                self.config["capacities"],
                policy=pol,
                warmup_days=self.config["warmup_days"],
                horizon_days=self.config["horizon_days"],
                allow_overflow=True,
            )
            self.assertEqual(res["admitted"] + res["reneged"], res["total_patients"])
            self.assertGreaterEqual(res["expected_survivors"], 0.0)
            self.assertLessEqual(res["expected_survivors"], res["total_patients"])
            self.assertGreaterEqual(res["mean_occupancy_global"], 0.0)
            self.assertLessEqual(res["mean_occupancy_global"], 1.0 + 1e-9)

    def test_controlled_triage_decision_mgs_vs_fcfs(self):
        initial = DynamicPatient(
            id=0, bed_type="adult", arrival_time=0.0, p_out=0.4, p_in_0=0.8,
            los=1.0, expected_los=1.0, max_wait=5.0, alpha_det=0.0, outcome_uniform=0.1,
            obs_p_out=0.4, obs_p_in_0=0.8, obs_expected_los=1.0
        )
        p1 = DynamicPatient(
            id=1, bed_type="adult", arrival_time=0.5, p_out=0.6, p_in_0=0.7,
            los=2.0, expected_los=2.0, max_wait=0.9, alpha_det=0.0, outcome_uniform=0.1,
            obs_p_out=0.6, obs_p_in_0=0.7, obs_expected_los=2.0
        )
        p2 = DynamicPatient(
            id=2, bed_type="adult", arrival_time=0.6, p_out=0.2, p_in_0=0.9,
            los=2.0, expected_los=2.0, max_wait=0.9, alpha_det=0.0, outcome_uniform=0.1,
            obs_p_out=0.2, obs_p_in_0=0.9, obs_expected_los=2.0
        )

        caps = {"neonatal": 0, "pediatric": 0, "adult": 1, "coronary": 0}
        res_fcfs = simulate_policy([initial, p1, p2], caps, policy="FCFS", warmup_days=0.0, horizon_days=10.0, allow_overflow=False)
        res_mgs = simulate_policy([initial, p1, p2], caps, policy="MGS", warmup_days=0.0, horizon_days=10.0, allow_overflow=False)

        self.assertAlmostEqual(res_fcfs["expected_survivors"], 1.7)
        self.assertAlmostEqual(res_mgs["expected_survivors"], 2.3)
        self.assertGreater(res_mgs["expected_survivors"], res_fcfs["expected_survivors"])

    def test_offline_ub_dominates_online_policies(self):
        patients = generate_patient_stream(self.config, demand_ratio=1.4, replication=2)
        ub_res = solve_offline_milp_bound(
            patients, self.config["capacities"],
            warmup_days=self.config["warmup_days"],
            horizon_days=self.config["horizon_days"],
            allow_overflow=True
        )
        for pol in POLICIES:
            res = simulate_policy(
                patients, self.config["capacities"], policy=pol,
                warmup_days=self.config["warmup_days"],
                horizon_days=self.config["horizon_days"],
                allow_overflow=True
            )
            self.assertGreaterEqual(ub_res["expected_survivors"] + 1.0, res["expected_survivors"])


if __name__ == "__main__":
    unittest.main()
