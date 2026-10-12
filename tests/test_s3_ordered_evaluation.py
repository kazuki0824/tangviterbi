"""Capacity and performance-first adoption regressions; no silicon claim."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from s3_ordered_constraints import report, worker_memory
from s3_ordered_evaluation import adoption_gate, calculate


class OrderedEvaluationTest(unittest.TestCase):
    def test_additional_tasks_exceed_existing_free_upper_bound(self):
        x = report(Path(__file__).resolve().parents[1] / "reports/s3-fft-simd-evidence/worker-sdk-ci.json")["memory"]
        self.assertEqual(x["free_after_startup_and_pool_upper_bound_bytes"], 3416)
        self.assertEqual(x["RS_target_ABI_used_bytes"], [30688, 25344])
        two = x["worker_profiles"]["two_extra_2KiB_workers"]
        self.assertEqual(two["internal_spare_upper_bound_before_driver_bytes"], -1376)
        self.assertTrue(two["configuration_rejected_by_capacity"])
        one = x["worker_profiles"]["main_RF_owner_one_extra_2KiB_worker"]
        self.assertEqual(one["internal_spare_upper_bound_before_driver_bytes"], 1020)
        self.assertFalse(one["all_runtime_memory_verified"])

    def test_union_code_retention_reduces_worker_budget(self):
        x = report(Path(__file__).resolve().parents[1] / "reports/s3-mode-union-evidence/results.json")["memory"]
        self.assertTrue(x["SDK_union_includes_RS_code"])
        self.assertEqual(x["free_after_startup_and_pool_upper_bound_bytes"], 1416)
        one = x["worker_profiles"]["main_RF_owner_one_extra_2KiB_worker"]
        self.assertEqual(one["internal_spare_upper_bound_before_driver_bytes"], -980)
        self.assertTrue(one["configuration_rejected_by_capacity"])
        small = x["worker_profiles"]["main_RF_owner_one_extra_1KiB_worker"]
        self.assertEqual(small["internal_spare_upper_bound_before_driver_bytes"], 44)
        self.assertFalse(small["all_runtime_memory_verified"])

    def test_runtime32_static_worker_is_not_allocated_again(self):
        x=report()['memory']
        self.assertEqual(x['RF_lossless_packed_ring_bytes'],32768)
        self.assertTrue(x['runtime_task_driver_adapters_retained'])
        selected=x['selected_runtime_task_configuration']
        self.assertTrue(selected['stack_TCB_and_pipeline_state_already_in_ELF_BSS'])
        self.assertEqual(selected['additional_dynamic_task_allocation_bytes'],0)
        self.assertGreater(selected['internal_spare_upper_bound_before_driver_bytes'],27000)
        self.assertFalse(selected['all_runtime_memory_verified'])

    def test_unknown_performance_and_quality_rescue_do_not_assign_routes(self):
        for status in (False, None):
            self.assertEqual(adoption_gate(status, ["SPI2/SPI3"])["assigned_routes"], [])
        self.assertFalse(adoption_gate(True, [], True)["adopted"])
        self.assertFalse(adoption_gate(True, ["SPI2/SPI3"], False)["adopted"])
        self.assertTrue(adoption_gate(True, ["SPI2/SPI3"], True)["adopted"])

    def test_every_ownership_retains_its_flows_without_partial_promotion(self):
        x = calculate()
        self.assertEqual(len(x["ownerships"]), 320)
        self.assertEqual(len({r["id"] for r in x["ownerships"]}), 320)
        self.assertTrue(all(r["performance_pass"] is None and not r["assigned_routes"] and not r["adopted"]
                            for r in x["ownerships"]))
        self.assertTrue(all(not p["whole_receiver"] for p in x["partial_FPGA_implementations"]))
        self.assertEqual(x["communication"]["performance_verified_candidates"], 0)


if __name__ == "__main__":
    unittest.main()
