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


def mapped_netlist_evidence(root, proof, verified, stages, measured, resource_signed):
    """Cross-check declarations against independently counted Yosys mapped cells.

    This is only a physical *resource and instance-presence* check; it does
    not prove RF-to-TS signal connectivity, I/O timing, or real board fitness.
    """
    node = proof.get("mapped_netlist")
    top = proof.get("top_module")
    if not verified(node) or not isinstance(top, str) or not top:
        return False, False
    try:
        data = json.loads((root / node["path"]).read_text())
        module = data["modules"][top]
        cells = module["cells"]
        if not isinstance(cells, dict) or not cells:
            return False, False
        counts = {k: 0 for k in ("logic", "ff", "bsram", "distributed_ram", "dsp", "pll")}
        for cell in cells.values():
            kind = cell["type"]
            if re.fullmatch(r"LUT[1-4]|ALU", kind):
                counts["logic"] += 1
            elif kind.startswith("DFF"):
                counts["ff"] += 1
            elif kind in ("DPB", "SDPB", "DPX9B", "SDPX9B"):
                counts["bsram"] += 1
            elif kind == "RAM16SDP4":
                counts["distributed_ram"] += 1
            elif kind == "MULT18X18":
                counts["dsp"] += 1
            elif kind in ("rPLL", "PLLVR", "PLL", "RPLL"):
                counts["pll"] += 1
            elif kind in ("IBUF", "OBUF", "IOBUF", "TBUF", "GND", "VCC",
                          "BUFG", "CLKBUF", "$scopeinfo", "$buf"):
                pass  # Board I/O and constant/clock buffers are not LUT sites.
            else:
                # Do not silently drop other mapped/hierarchical resources.
                # The stage-2 resource comparison cannot qualify unknown cells.
                return False, False
        count_match = all(resource_signed.get(k) and measured.get(k) == value
                          for k, value in counts.items())
        instances = [proof.get("blocks", {}).get(item["id"], {}).get("rtl_instance")
                     for item in stages]
        unique_instances = (all(isinstance(x, str) and x for x in instances)
                            and len(instances) == len(set(instances)))
        if not unique_instances:
            return count_match, False
        # Exact hierarchy boundary, not raw startswith: foo and foobar
        # must never be treated as the same RTL instance.
        instance_presence = all(
            any(cellname == inst or cellname.startswith(inst + ".")
                or cellname.startswith(inst + "$")
                for cellname in cells)
            for inst in instances
        )
        return count_match, instance_presence
    except (KeyError, TypeError, ValueError, UnicodeError, OSError, AttributeError):
        return False, False


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
            detail = "N/A for declared capacity excess with hash-matched P&R log; independent log verification still required"
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
              "Declared full-top resource with matching report hash; report contents are not independently parsed")

    mapped_counts_ok, instance_presence_ok = mapped_netlist_evidence(
        root, proof, verified, stages, measured, resource_signed)
    check("independent mapped resource counts",
          basic and mapped_counts_ok,
          "Yosys mapped cells must match declared logic/FF/BSRAM/LUTRAM/DSP/PLL values")
    check("29 required instances in mapped top",
          basic and instance_presence_ok,
          "Unique full-top hierarchy instances must appear in the mapped cell names; "
          "presence alone does not establish functional connectivity")

    check("shared-component double counts",
          basic and complete_physical_outcome and proof.get("all_instance_ownership_unique") is True,
          "Shared resources must have one nonoverlapping owner")
    functions_complete = (proof.get("all_stage_connected") is True
                          and proof.get("all_stage_functional_checks") is True)
    check("full receiver fit or proven capacity excess",
          basic and complete_physical_outcome and functions_complete,
          "Require declared routed fit OR capacity excess with hash-matched log; independent physical verification remains required")

    # Structural consistency of declarations is NOT independent proof of a
    # measured complete receiver. Keep the synthetic-acceptance result visible
    # for diagnostics but fail closed on actual estimate/stage promotion.
    declared_checks_complete = all(c["ok"] for c in checks)
    declared_fit_status = (
        "fits" if declared_checks_complete and routed_success else
        "does_not_fit" if declared_checks_complete and negative_capacity
        else "unverified"
    )
    independent_report_values_verified = False
    independent_instance_connectivity_verified = False
    estimate_complete = (
        declared_checks_complete and independent_report_values_verified
        and independent_instance_connectivity_verified
    )
    fit_status = declared_fit_status if estimate_complete else "unverified"
    return {
        "stage": 2,
        "all_conditions_checked": len(checks),
        "ng": sum(not c["ok"] for c in checks),
        "declaration_checks_complete": declared_checks_complete,
        "declared_fit_status": declared_fit_status,
        "estimate_complete": estimate_complete,
        "completion": estimate_complete,
        "fit_status": fit_status,
        # Full receiver adoption also needs the later timing and RF/TS gates.
        # Stage 2 can qualify a resource-fit candidate, never a receiver.
        "mapped_resource_counts_verified": basic and mapped_counts_ok,
        "mapped_required_instances_present": basic and instance_presence_ok,
        "independent_report_values_verified": independent_report_values_verified,
        "independent_instance_connectivity_verified": independent_instance_connectivity_verified,
        "hardware_qualified": False,
        "declared_resource_fit_candidate": declared_fit_status == "fits",
        "stage2_resource_fit_candidate": estimate_complete and fit_status == "fits",
        "receiver_adoptable": False,
        "stage3_permitted": estimate_complete,
        "resource_excess": excess if basic else {},
        "checks": checks,
    }


def main():
    answer = audit()
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return int(not answer["completion"])


if __name__ == "__main__":
    sys.exit(main())
