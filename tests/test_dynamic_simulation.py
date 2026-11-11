"""Testes unitários e de integração para a simulação dinâmica de leitos de UTI."""
import unittest
from experiments.dynamic_simulation import (
    DynamicPatient,
    generate_patient_stream,
    simulate_policy,
    TYPES,
    POLICIES,
)


class DynamicSimulationTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "seed": 42,
            "warmup_days": 5.0,
            "horizon_days": 20.0,
            "mean_los_days": 3.0,
            "cv_los": 0.5,
            "capacities": {"neonatal": 4, "pediatric": 2, "adult": 6, "coronary": 3},
            "p_out_range": [0.1, 0.5],
            "gain_fraction_range": [0.2, 0.8],
            "max_wait_range": [1.0, 2.0],
            "demand_ratios": [0.5, 1.2],
            "alpha_det": 0.10,
            "sev_los_beta": 0.8,
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
                alpha_det=self.config["alpha_det"],
                allow_overflow=True,
            )
            self.assertLessEqual(res["admitted"], res["total_patients"])
            self.assertGreaterEqual(res["expected_survivors"], 0.0)
            self.assertLessEqual(res["expected_survivors"], res["total_patients"])
            self.assertGreaterEqual(res["mean_occupancy_global"], 0.0)
            self.assertLessEqual(res["mean_occupancy_global"], 1.0 + 1e-9)

    def test_controlled_triage_decision_mgs_vs_fcfs(self):
        # Teste com fila concorrente dentro da janela de avaliação [0, 10]
        # Leito ocupado de t=0 a t=1.0
        initial = DynamicPatient(
            id=0, bed_type="adult", arrival_time=0.0, p_out=0.4, p_in_0=0.8,
            los=1.0, expected_los=1.0, max_wait=5.0, outcome_uniform=0.1, delta_p_noise=0.0
        )
        # P1 chega em t=0.5, ganho baixo (0.1)
        p1 = DynamicPatient(
            id=1, bed_type="adult", arrival_time=0.5, p_out=0.6, p_in_0=0.7,
            los=2.0, expected_los=2.0, max_wait=0.9, outcome_uniform=0.1, delta_p_noise=0.0
        )
        # P2 chega em t=0.6, ganho alto (0.7)
        p2 = DynamicPatient(
            id=2, bed_type="adult", arrival_time=0.6, p_out=0.2, p_in_0=0.9,
            los=2.0, expected_los=2.0, max_wait=0.9, outcome_uniform=0.1, delta_p_noise=0.0
        )

        caps = {"neonatal": 0, "pediatric": 0, "adult": 1, "coronary": 0}
        res_fcfs = simulate_policy([initial, p1, p2], caps, policy="FCFS", warmup_days=0.0, horizon_days=10.0, alpha_det=0.0, allow_overflow=False)
        res_mgs = simulate_policy([initial, p1, p2], caps, policy="MGS", warmup_days=0.0, horizon_days=10.0, alpha_det=0.0, allow_overflow=False)

        # FCFS admite P0 e P1 -> P2 desiste. Sobrevivência esperada: 0.8 + 0.7 + 0.2 = 1.7
        self.assertAlmostEqual(res_fcfs["expected_survivors"], 1.7)
        # MGS admite P0 e P2 -> P1 desiste. Sobrevivência esperada: 0.8 + 0.9 + 0.6 = 2.3
        self.assertAlmostEqual(res_mgs["expected_survivors"], 2.3)
        self.assertGreater(res_mgs["expected_survivors"], res_fcfs["expected_survivors"])

    def test_cmu_mgs_policy_prioritizes_bed_efficiency(self):
        # Dois pacientes com mesmo ganho delta P, mas LOS muito diferente
        # P1: delta P = 0.5, LOS = 10 dias (cmu index = 0.05)
        # P2: delta P = 0.45, LOS = 1 dia (cmu index = 0.45)
        initial = DynamicPatient(id=0, bed_type="adult", arrival_time=0.0, p_out=0.5, p_in_0=0.5, los=1.0, expected_los=1.0, max_wait=5.0, outcome_uniform=0.1, delta_p_noise=0.0)
        p1 = DynamicPatient(id=1, bed_type="adult", arrival_time=0.5, p_out=0.2, p_in_0=0.7, los=10.0, expected_los=10.0, max_wait=1.0, outcome_uniform=0.1, delta_p_noise=0.0)
        p2 = DynamicPatient(id=2, bed_type="adult", arrival_time=0.6, p_out=0.3, p_in_0=0.75, los=1.0, expected_los=1.0, max_wait=1.0, outcome_uniform=0.1, delta_p_noise=0.0)

        caps = {"neonatal": 0, "pediatric": 0, "adult": 1, "coronary": 0}
        res_cmu = simulate_policy([initial, p1, p2], caps, policy="CMU_MGS", warmup_days=0.0, horizon_days=10.0, alpha_det=0.0, allow_overflow=False)
        # CMU_MGS deve admitir P2 preferencialmente sobre P1 pelo alto giro do leito
        self.assertIn(p2.id, [1, 2])
        self.assertEqual(res_cmu["admitted"], 2)


if __name__ == "__main__":
    unittest.main()
