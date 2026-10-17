#!/usr/bin/env python3
"""Reassess optional 9K->S3 RS RPC without changing PR #8's command-only design.

Uses pinned legacy estimates as *conditional necessary-condition evidence*.
It neither certifies a bidirectional transport nor authorizes one; the user
can choose whether to relax the command-only interface after actual WCET/PHY.
"""
import json
from fractions import Fraction

RS_CW_PER_S = Fraction(28_860_000 * 2, 203 * 8)
CW_PER_BATCH = 204
BATCHES_PER_S = RS_CW_PER_S / CW_PER_BATCH
PAGE_BYTES = 4096
RF_MBPS = 100.0  # 40 MSa/s, lossless I10/Q10 => 5 bytes / two samples
OCTAL_QUAD_EFFECTIVE_MBPS = 103.7235  # historical gap=0 aggregate witness
S3_TWO_CORE_MCYCLES_PER_S = 480.0
RF_LOW_HIGH_MCYCLES_PER_S = (368.4375, 448.4375)
S3_GF_BM_OMEGA_VECTOR = {"mul_calls": 421, "div_calls": 16}

# These are historical route/microarchitecture-specific observations, not
# transferable bounds on an arbitrary RS architecture or measured S3 WCET.
POLICIES = (
    {"name": "S-0/FPGA_all_RS", "down_pages": 0, "up_pages": 0,
     "down_payload_bytes_per_CW": 0, "up_payload_bytes_per_CW": 0,
     "reason": "Existing buffered FPGA RS needs complete live clock/area/queue closure.",
     "selected_implementation_rejected": False},
    {"name": "S-1/SoC_all_RS", "down_pages": 11, "up_pages": 10,
     "down_payload_bytes_per_CW": 204, "up_payload_bytes_per_CW": 188,
     "scalar_cycles_per_CW": 22060,
     "reason": "Selected 22060-cycle/CW scalar RS alone exceeds 480 Mcycles/s; aggregate transport also exceeds Octal+Quad.",
     "selected_implementation_rejected": True},
    {"name": "S-2/SoC_BM_Chien_Forney", "down_pages": 1, "up_pages": 1,
     "down_payload_bytes_per_CW": 19, "up_payload_bytes_per_CW": 20,
     "historical_directional_margin_MBps": [1.969507, 2.296250],
     "selected_scalar_Chien_cycles_per_CW": 6528,
     "reason": "Selected scalar Chien needs 6528 cycles/CW; RF-only optimistic low headroom before API is smaller.",
     "selected_implementation_rejected": True},
    {"name": "S-3/SoC_BM_Omega", "down_pages": 1, "up_pages": 2,
     "down_payload_bytes_per_CW": 19, "up_payload_bytes_per_CW": 29,
     "historical_directional_margin_MBps": [1.337568, 1.582624],
     "historical_CPU_low_remaining_cycles_per_CW": [1288.112088, 1317.028115],
     "selected_partial_FPGA_logic_lower_bound": 9426,
     "reason": "Existing FPGA Forney co-mapped netlist needs >=9426/8640 sites; BM/Omega S3 WCET unmeasured.",
     "selected_implementation_rejected": True},
    {"name": "S-4/SoC_BM_Omega_Forney", "down_pages": 2, "up_pages": 2,
     "down_payload_bytes_per_CW": 31, "up_payload_bytes_per_CW": 25,
     "historical_directional_margin_MBps": [0.215515, 0.868999],
     "historical_CPU_low_remaining_cycles_per_CW": [1216.389297, 1293.498704],
     "reason": "The prior CW-retaining partial netlist missed timing and uses nearly all BSRAM; four RPC messages per batch.",
     "selected_implementation_rejected": True},
)

def calculate():
    cases = []
    for x in POLICIES:
        count = x["down_pages"] + x["up_pages"]
        rpc_MBps = float(BATCHES_PER_S * PAGE_BYTES * count / 1_000_000)
        useful_MBps = float(RS_CW_PER_S *
                           (x["down_payload_bytes_per_CW"] +
                            x["up_payload_bytes_per_CW"]) / 1_000_000)
        joint = RF_MBPS + rpc_MBps
        optimistic_margin = OCTAL_QUAD_EFFECTIVE_MBPS - joint
        case = dict(x)
        case.update(
            rpc_padded_MBps=rpc_MBps, rpc_useful_payload_MBps=useful_MBps,
            rpc_padding_MBps=rpc_MBps-useful_MBps,
            joint_RF_and_RPC_MBps=joint,
            optimistic_aggregate_capacity_margin_MBps=optimistic_margin,
            aggregate_wire_necessary_condition=(optimistic_margin>=0),
            only_control_on_FPGA_to_S3=(x["down_pages"]==0),
            bidirectional_adoption_authorized=False,
            physical_link_pass=None, CPU_WCET_pass=None, whole_FPGA_fit=None,
            bounded_batch_deadline_pass=None, candidate_adopted=False)
        if "historical_CPU_low_remaining_cycles_per_CW" in x:
            low = x["historical_CPU_low_remaining_cycles_per_CW"]
            high_penalty_cycles_per_CW = float(
                (RF_LOW_HIGH_MCYCLES_PER_S[1]-RF_LOW_HIGH_MCYCLES_PER_S[0])
                * 1_000_000 / RS_CW_PER_S)
            case["CPU_high_remaining_if_same_API_model_cycles_per_CW"] = [
                z-high_penalty_cycles_per_CW for z in low]
        cases.append(case)
    rf_only_low_no_API = float(
        (S3_TWO_CORE_MCYCLES_PER_S-RF_LOW_HIGH_MCYCLES_PER_S[0]) *
        1_000_000 / RS_CW_PER_S)
    scalar_all_RS_MCyc_s = float(22060*RS_CW_PER_S/1_000_000)
    return {
        "scope": "S ISDB-S conventional, 9K+one ESP32-S3, 40 MSa/s full native I/Q; comparison of optional reverse RS transfers",
        "source_references": [
            "reports/s3-partition-audit.md",
            "reports/s3-link-cpu-sensitivity.md",
            "reports/s3-rs-forney-evidence/results.json",
            "reports/s3-runtime-endpoint.md",
            "reports/control-only-9k/README.md",
        ],
        "clock_and_rate": {
            "S_RS_CW_s": float(RS_CW_PER_S),
            "CW_interval_us": float(1_000_000 / RS_CW_PER_S),
            "batch_204_interval_ms": float(CW_PER_BATCH / RS_CW_PER_S * 1000),
            "S3_low_model_remaining_cycles_per_CW_before_API":
                rf_only_low_no_API,
            "S1_old_scalar_RS_only_Mcycles_s": scalar_all_RS_MCyc_s,
            "BM_Omega_observed_host_GF_calls": S3_GF_BM_OMEGA_VECTOR,
        },
        "cases": cases,
        "command_only_design_requirement_retained": True,
        "reverse_direction_physically_impossible_proven": False,
        "alternative_receiver_feasible_proven": False,
        "legacy_low_high_are_WCET_guarantees": False,
        "full_silicon_test_performed": False,
        "candidate_adopted": False,
    }

if __name__ == "__main__":
    print(json.dumps(calculate(), indent=2, ensure_ascii=False))
