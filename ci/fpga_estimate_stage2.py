"""Stage 2 all-resource audit. Enumeration must never fail fast.

A fully-accounted design may be physically *infeasible*: preserve that
negative engineering result independently of estimate completeness.
A green diagnostic CI is never itself evidence that stage 2 is complete.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIMIT_KEYS = {
    "logic": "logic_positions",
    "ff": "ff_positions",
    "bsram": "bsram_blocks",
    "dsp": "dsp18_units",
    "pll": "pll_count",
    "pins": "board_available_header_signals_upper",
    "sdram_storage": "sdram_bytes",
}
RESOURCE_KEYS = ("logic", "ff", "bsram", "distributed_ram", "dsp",
                 "pll", "pins", "sdram_storage")
EVIDENCE_KEYS = ("source", "routed_netlist", "timing_report",
                 "resource_report", "constraints")


def audit(root=ROOT):
    root = Path(root).resolve()
    scope = json.loads((root / "reports/fpga-estimate-closure/scope.json").read_text())
    reconciliation = (root / "reports/fpga-estimate-closure/stage2-reconciliation.md").read_text()
    proof_path = root / "reports/fpga-estimate-closure/full-top-proof.json"
    proof = json.loads(proof_path.read_text()) if proof_path.exists() else {}
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def verified(node):
        if not isinstance(node, dict):
            return False
        rel = node.get("path")
        digest = node.get("sha256")
        if not isinstance(rel, str) or not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            return False
        target = (root / rel).resolve()
        return (target.is_relative_to(root) and target.is_file()
                and hashlib.sha256(target.read_bytes()).hexdigest() == digest)

    evidence = {key: proof.get(key) for key in EVIDENCE_KEYS}
    resource_report_ok = verified(evidence["resource_report"])
    source_ok = verified(evidence["source"])
    constraints_ok = verified(evidence["constraints"])
    pnr_log_ok = verified(proof.get("pnr_log"))
    resources = proof.get("resources", {})
    capacities = scope["capacity"]
    measured = {}
    resource_signed = {}
    for name in RESOURCE_KEYS:
        node = resources.get(name) if isinstance(resources, dict) else None
        value = node.get("value") if isinstance(node, dict) else None
        good = (type(value) is int and value >= 0
                and node.get("evidence_hash") == (evidence["resource_report"] or {}).get("sha256")
                and resource_report_ok)
        resource_signed[name] = good
        if good:
            measured[name] = value

    excess = {}
    for resource, limit_name in LIMIT_KEYS.items():
        if resource_signed[resource]:
            limit = capacities[limit_name]
            if measured[resource] > limit:
                excess[resource] = {"used": measured[resource],
                                    "capacity": limit,
                                    "over": measured[resource] - limit}

    # A RAM16SDP4 consumes four Gowin logic-site positions. The separate
    # `logic` measurement must count LUT/ALU sites without these RAM cells.
    # Checking LUT/ALU alone would incorrectly accept an overfull 20K layout.
    if resource_signed["logic"] and resource_signed["distributed_ram"]:
        occupied = measured["logic"] + 4 * measured["distributed_ram"]
        limit = capacities["logic_positions"]
        if occupied > limit:
            excess["logic_sites_including_distributed_ram"] = {
                "used": occupied, "capacity": limit,
                "over": occupied - limit,
            }

    result_kind = proof.get("pnr_outcome")
    routed_success = (result_kind == "routed"
                      and verified(evidence["routed_netlist"])
                      and verified(evidence["timing_report"])
                      and proof.get("legal_placement") is True
                      and not excess)
    negative_capacity = (
        result_kind == "capacity_exceeded"
        and pnr_log_ok
        and bool(excess)
        and proof.get("no_routed_netlist_due_to_capacity") is True
        and proof.get("no_timing_report_due_to_capacity") is True
        and proof.get("legal_placement") is False
    )
    complete_physical_outcome = routed_success or negative_capacity

    check("reconciliation evidence recorded",
          all(x in reconciliation for x in ("20726", "22002", "1276", "1266", "22977")),
          "Different incompatible area experiments must stay separate")
    check("capacity correctly reported",
          capacities["logic_positions"] == 20736 and capacities["bsram_blocks"] == 46,
          "Board limits are fixed by stage 1")
    probe = scope["physical_probes"]
    check("no partial P&R upgraded to full",
          probe["partial_pnr"]["classification"].startswith("routed partial fixture")
          and probe["full_top_area"]["value"] is None and probe["full_top_timing"]["value"] is None,
          "Frozen stage-1 partial probe must remain explicitly partial")

    for name in EVIDENCE_KEYS:
        if name in ("routed_netlist", "timing_report") and negative_capacity:
            ok = True
            detail = "N/A only: signed P&R log proves a full-top capacity overrun; no routed artifact exists"
        else:
            ok = verified(evidence[name])
            detail = "Require an actual file with matching SHA-256"
        check("evidence file sha256:" + name, ok, detail)

    basic = source_ok and constraints_ok and resource_report_ok
    stages = scope["required_stages"]["t"] + scope["required_stages"]["s"] + scope["required_support"]
    stage_blocks = proof.get("blocks", {})
    for item in stages:
        node = stage_blocks.get(item["id"], {}) if isinstance(stage_blocks, dict) else {}
        installed = node.get("placed_instance") if routed_success else node.get("rtl_instance")
        owner = node.get("owned_resources")
        source_rel = node.get("source_path")
        source_sha = node.get("source_sha256")
        stage_source_verified = verified({"path": source_rel, "sha256": source_sha})
        check("area:" + item["id"],
              basic and complete_physical_outcome and bool(installed)
              and isinstance(owner, dict) and bool(owner) and stage_source_verified,
              "Actual named RTL instance, owned resource entries and hashed source required")

    for name in RESOURCE_KEYS:
        check("full-top physical resource:" + name,
              basic and complete_physical_outcome and resource_signed[name],
              "Measured full-top resource, signed by common resource-report hash")

    check("shared-component double counts",
          basic and complete_physical_outcome and proof.get("all_instance_ownership_unique") is True,
          "Shared resources must have one nonoverlapping owner")
    functions_complete = (proof.get("all_stage_connected") is True
                          and proof.get("all_stage_functional_checks") is True)
    check("full receiver fit or proven capacity excess",
          basic and complete_physical_outcome and functions_complete,
          "Require legal routed fit OR documented actual overcapacity with hashed failed P&R log")

    complete = all(c["ok"] for c in checks)
    fit_status = ("fits" if complete and routed_success else
                  "does_not_fit" if complete and negative_capacity else "unverified")
    return {
        "stage": 2,
        "all_conditions_checked": len(checks),
        "ng": sum(not c["ok"] for c in checks),
        "estimate_complete": complete,
        "completion": complete,
        "fit_status": fit_status,
        # Full receiver adoption also needs the later timing and RF/TS gates.
        # Stage 2 can qualify a resource-fit candidate, never a receiver.
        "stage2_resource_fit_candidate": complete and fit_status == "fits",
        "receiver_adoptable": False,
        "stage3_permitted": complete,
        "resource_excess": excess if basic else {},
        "checks": checks,
    }


def main():
    answer = audit()
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return int(not answer["completion"])


if __name__ == "__main__":
    sys.exit(main())
