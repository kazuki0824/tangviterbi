"""Stage 2 gate: distinguish synthetic accepted declarations from physical proof.

All tests use synthetic evidence in temporary directories; none asserts that
the real receiver is complete. Preserve the 49-condition non-fail-fast audit.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from ci.fpga_estimate_stage2 import audit, ROOT


class StageTwoGate(unittest.TestCase):
    def test_stage_two_remains_closed_without_measured_full_receiver(self):
        result = audit()
        self.assertEqual(result["stage"], 2)
        self.assertFalse(result["estimate_complete"])
        self.assertFalse(result["stage3_permitted"])
        self.assertEqual(result["fit_status"], "unverified")
        self.assertEqual(result["all_conditions_checked"], 49)
        self.assertEqual(result["all_conditions_checked"], len(result["checks"]))
        self.assertFalse(result["independent_report_values_verified"])
        self.assertFalse(result["independent_instance_connectivity_verified"])
        self.assertFalse(result["hardware_qualified"])
        self.assertEqual(result["ng"], sum(not item["ok"] for item in result["checks"]))
        failures = {item["name"] for item in result["checks"] if not item["ok"]}
        self.assertIn("full receiver fit or proven capacity excess", failures)
        self.assertIn("evidence file sha256:routed_netlist", failures)
        self.assertIn("area:t_fir_resample", failures)
        self.assertIn("area:s_ts", failures)

    def fixture(self, root, outcome, logic=20000, distributed_ram=0):
        report_dir = root / "reports/fpga-estimate-closure"
        report_dir.mkdir(parents=True)
        scope = json.loads((ROOT / "reports/fpga-estimate-closure/scope.json").read_text())
        reconciliation = (ROOT / "reports/fpga-estimate-closure/stage2-reconciliation.md").read_text()
        (report_dir / "scope.json").write_text(json.dumps(scope))
        (report_dir / "stage2-reconciliation.md").write_text(reconciliation)

        def file_entry(name):
            target = root / name
            target.write_text("synthetic test evidence " + name + "\n")
            return {"path": name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

        source = file_entry("source.sv")
        resource_report = file_entry("resource.txt")
        proof = {
            "source": source,
            "resource_report": resource_report,
            "constraints": file_entry("pins.cst"),
            "pnr_outcome": outcome,
            "legal_placement": outcome == "routed",
            "all_stage_connected": True,
            "all_stage_functional_checks": True,
            "all_instance_ownership_unique": True,
            "blocks": {},
            "resources": {},
        }
        if outcome == "routed":
            proof["routed_netlist"] = file_entry("routed.v")
            proof["timing_report"] = file_entry("timing.txt")
        else:
            proof["pnr_log"] = file_entry("failed-pnr.log")
            proof["no_routed_netlist_due_to_capacity"] = True
            proof["no_timing_report_due_to_capacity"] = True

        capacities = {
            "logic": logic, "ff": 10000, "bsram": 30, "distributed_ram": distributed_ram,
            "dsp": 20, "pll": 1, "pins": 34, "sdram_storage": 1000
        }
        for name, value in capacities.items():
            proof["resources"][name] = {
                "value": value,
                "evidence_hash": resource_report["sha256"],
            }
        stages = (scope["required_stages"]["t"] + scope["required_stages"]["s"]
                  + scope["required_support"])
        for item in stages:
            proof["blocks"][item["id"]] = {
                "rtl_instance": "dut." + item["id"],
                "placed_instance": "dut." + item["id"],
                "owned_resources": {"logic": 1},
                "source_path": source["path"],
                "source_sha256": source["sha256"],
            }

        # The mapped-cell file is deliberately synthetic and can only
        # exercise cross-check logic; it is not independent CAD evidence.
        mapped = {}
        for item in stages:
            mapped["dut." + item["id"] + ".logic"] = {"type": "LUT4"}
        for k in range(logic - len(stages)):
            mapped["extra_logic_" + str(k)] = {"type": "LUT4"}
        for kind, count in (
            ("DFF", capacities["ff"]),
            ("DPB", capacities["bsram"]),
            ("RAM16SDP4", capacities["distributed_ram"]),
            ("MULT18X18", capacities["dsp"]),
            ("rPLL", capacities["pll"]),
        ):
            for k in range(count):
                mapped[kind + "_" + str(k)] = {"type": kind}
        netlist_path = root / "mapped.json"
        netlist_path.write_text(json.dumps({"modules": {"full_top": {"cells": mapped}}}))
        proof["mapped_netlist"] = {
            "path": "mapped.json",
            "sha256": hashlib.sha256(netlist_path.read_bytes()).hexdigest(),
        }
        proof["top_module"] = "full_top"
        (report_dir / "full-top-proof.json").write_text(json.dumps(proof))
        return proof

    def test_complete_and_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "routed")
            result = audit(root)
            self.assertEqual(result["all_conditions_checked"], 49)
            self.assertEqual(result["ng"], 0)
            self.assertTrue(result["declaration_checks_complete"])
            self.assertFalse(result["estimate_complete"])
            self.assertFalse(result["stage3_permitted"])
            self.assertTrue(result["declared_resource_fit_candidate"])
            self.assertFalse(result["stage2_resource_fit_candidate"])
            self.assertFalse(result["hardware_qualified"])
            self.assertFalse(result["receiver_adoptable"])
            self.assertEqual(result["declared_fit_status"], "fits")
            self.assertEqual(result["fit_status"], "unverified")

    def test_complete_and_capacity_exceeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "capacity_exceeded", logic=21000)
            result = audit(root)
            self.assertEqual(result["all_conditions_checked"], 49)
            self.assertEqual(result["ng"], 0)
            self.assertTrue(result["declaration_checks_complete"])
            self.assertFalse(result["estimate_complete"])
            self.assertFalse(result["receiver_adoptable"])
            self.assertFalse(result["stage3_permitted"])
            self.assertEqual(result["declared_fit_status"], "does_not_fit")
            self.assertEqual(result["fit_status"], "unverified")
            self.assertEqual(result["resource_excess"]["logic"]["over"], 264)

    def test_distributed_ram_sites_reject_fake_routed_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "routed", logic=20000, distributed_ram=200)
            result = audit(root)
            self.assertEqual(result["all_conditions_checked"], 49)
            self.assertEqual(result["fit_status"], "unverified")
            self.assertFalse(result["stage2_resource_fit_candidate"])
            self.assertFalse(result["receiver_adoptable"])
            self.assertFalse(result["stage3_permitted"])
            self.assertEqual(
                result["resource_excess"]["logic_sites_including_distributed_ram"],
                {"used": 20800, "capacity": 20736, "over": 64},
            )

    def test_distributed_ram_sites_can_prove_capacity_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "capacity_exceeded", logic=20000, distributed_ram=200)
            result = audit(root)
            self.assertEqual(result["all_conditions_checked"], 49)
            self.assertEqual(result["ng"], 0)
            self.assertTrue(result["declaration_checks_complete"])
            self.assertFalse(result["estimate_complete"])
            self.assertEqual(result["declared_fit_status"], "does_not_fit")
            self.assertEqual(result["fit_status"], "unverified")
            self.assertFalse(result["receiver_adoptable"])
            self.assertEqual(
                result["resource_excess"]["logic_sites_including_distributed_ram"]["over"], 64
            )

    def test_distributed_ram_sites_at_exact_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "routed", logic=20000, distributed_ram=184)
            result = audit(root)
            self.assertEqual(result["all_conditions_checked"], 49)
            self.assertEqual(result["ng"], 0)
            self.assertTrue(result["declared_resource_fit_candidate"])
            self.assertFalse(result["stage2_resource_fit_candidate"])
            self.assertFalse(result["hardware_qualified"])
            self.assertEqual(result["declared_fit_status"], "fits")
            self.assertEqual(result["fit_status"], "unverified")
            self.assertFalse(result["receiver_adoptable"])


    def test_mapped_cell_count_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proof = self.fixture(root, "routed")
            proof["resources"]["logic"]["value"] -= 1
            (root / "reports/fpga-estimate-closure/full-top-proof.json").write_text(
                json.dumps(proof)
            )
            result = audit(root)
            self.assertFalse(result["estimate_complete"])
            self.assertFalse(result["mapped_resource_counts_verified"])
            self.assertFalse(result["stage3_permitted"])
            self.assertEqual(result["all_conditions_checked"], 49)

    def test_required_instance_missing_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proof = self.fixture(root, "routed")
            proof["blocks"]["t_fir_resample"]["rtl_instance"] = "dut.does_not_exist"
            (root / "reports/fpga-estimate-closure/full-top-proof.json").write_text(
                json.dumps(proof)
            )
            result = audit(root)
            self.assertFalse(result["estimate_complete"])
            self.assertFalse(result["mapped_required_instances_present"])
            self.assertEqual(result["all_conditions_checked"], 49)

    def test_yosys_bookkeeping_cells_do_not_count_as_fpga_logic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proof = self.fixture(root, "routed")
            netlist = root / "mapped.json"
            data = json.loads(netlist.read_text())
            data["modules"]["full_top"]["cells"]["bookkeeping"] = {"type": "$scopeinfo"}
            data["modules"]["full_top"]["cells"]["buffer"] = {"type": "$buf"}
            netlist.write_text(json.dumps(data))
            proof["mapped_netlist"]["sha256"] = hashlib.sha256(
                netlist.read_bytes()).hexdigest()
            (root / "reports/fpga-estimate-closure/full-top-proof.json").write_text(
                json.dumps(proof))
            result = audit(root)
            self.assertTrue(result["mapped_resource_counts_verified"])
            self.assertTrue(result["mapped_required_instances_present"])
            self.assertTrue(result["declaration_checks_complete"])
            self.assertFalse(result["estimate_complete"])
            self.assertEqual(result["all_conditions_checked"], 49)

    def test_unknown_mapped_primitive_does_not_disappear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proof = self.fixture(root, "routed")
            netlist = root / "mapped.json"
            data = json.loads(netlist.read_text())
            data["modules"]["full_top"]["cells"]["unknown"] = {"type": "UNMAPPED_MACRO"}
            netlist.write_text(json.dumps(data))
            proof["mapped_netlist"]["sha256"] = hashlib.sha256(
                netlist.read_bytes()).hexdigest()
            (root / "reports/fpga-estimate-closure/full-top-proof.json").write_text(
                json.dumps(proof))
            result = audit(root)
            self.assertFalse(result["mapped_resource_counts_verified"])
            self.assertFalse(result["estimate_complete"])
            self.assertFalse(result["stage3_permitted"])
            self.assertEqual(result["all_conditions_checked"], 49)

    def test_mapped_netlist_hash_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "routed")
            with (root / "mapped.json").open("a") as stream:
                stream.write(" ")
            result = audit(root)
            self.assertFalse(result["estimate_complete"])
            self.assertFalse(result["mapped_resource_counts_verified"])
            self.assertFalse(result["mapped_required_instances_present"])

    def test_negative_without_real_excess_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "capacity_exceeded", logic=20000)
            result = audit(root)
            self.assertEqual(result["fit_status"], "unverified")
            self.assertFalse(result["stage3_permitted"])
            self.assertGreater(result["ng"], 0)
            self.assertEqual(result["all_conditions_checked"], 49)

    def test_negative_without_verified_pnr_log_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "capacity_exceeded", logic=21000)
            (root / "failed-pnr.log").write_text("tampered")
            result = audit(root)
            self.assertFalse(result["estimate_complete"])
            self.assertEqual(result["fit_status"], "unverified")
            self.assertGreater(result["ng"], 0)

    def test_routed_with_inconsistent_capacity_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, "routed", logic=21000)
            result = audit(root)
            self.assertFalse(result["estimate_complete"])
            self.assertEqual(result["fit_status"], "unverified")
            self.assertGreater(result["ng"], 0)


if __name__ == "__main__":
    unittest.main()
