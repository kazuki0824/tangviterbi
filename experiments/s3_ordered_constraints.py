"""Board and simultaneous-memory preconditions before S3/9K stage evaluation.

Capacity failures apply to the declared worker configuration, never all
implementations. Passing a necessary capacity bound cannot certify runtime.
"""
import argparse
import hashlib
import json
from pathlib import Path
from s3_board_pins import proposal
from s3_nor_images import CAPACITY, OFFSETS, SLOT

ROOT = Path(__file__).resolve().parents[1]


def worker_memory(free_after_pool, workers, reuse_main, driver_bytes=None):
    # Target StaticTask_t=340 from the pinned SDK ELF. Four-byte heap allocation
    # headers are lower bounds; alignment, locks and fragmentation are omitted.
    stacks = sum(workers)
    tcbs = 340 * len(workers)
    headers = 8 * len(workers)
    cost = stacks + tcbs + headers
    spare = free_after_pool - cost
    return {
        "additional_worker_stack_bytes": workers, "RF_owner_reuses_main_task": reuse_main,
        "additional_stack_TCB_allocation_lower_bound_bytes": cost,
        "internal_spare_upper_bound_before_driver_bytes": spare,
        "declared_worker_capacity_necessary_pass": spare >= 0,
        "driver_runtime_bytes": driver_bytes,
        "all_runtime_memory_verified": False,
        "configuration_rejected_by_capacity": spare < 0,
    }


def report():
    sdk_path = ROOT / "reports/s3-fft-simd-evidence/worker-sdk-ci.json"
    sdk = json.loads(sdk_path.read_text())
    startup = sdk["startup_bound"]["allocator_refinement"]
    free = startup["free_before_DMA_pool_upper_bound_bytes"] - startup["DMA_pool_target_bytes"]
    board = proposal()
    pins = board["nets"]
    memory = {
        "sdk_evidence_HEAD": sdk["head_sha"], "SDK_profile_is_integrated_receiver": False,
        "SDK_union_includes_RS_code": sdk["link_result"]["RS_offload_mode_union"],
        "source_sha256": hashlib.sha256(sdk_path.read_bytes()).hexdigest(),
        "RF_raw_three_banks_bytes": 3 * 65536,
        "RF_lossless_packed_ring_bytes": 65536,
        "mode_slots_bytes": [32768, 32768], "T_SIMD_coefficients_bytes": 16384,
        "slots_are_mutually_exclusive_T_FFT_or_S_RS": True,
        "RS_slot_layout_verified": False,
        "free_after_startup_and_pool_upper_bound_bytes": free,
        "worker_profiles": {
            "two_extra_2KiB_workers": worker_memory(free, [2048, 2048], False),
            "main_RF_owner_one_extra_2KiB_worker": worker_memory(free, [2048], True),
            "two_extra_1KiB_workers": worker_memory(free, [1024, 1024], False),
        },
        "not_counted": ["actual worker call-chain stack bound", "SPI/SCT driver objects and configuration",
                        "PHY/calibration", "RS code in simultaneous T/S SDK link", "allocation fragmentation"],
    }
    # Read the actual S3 ABI, not the host's struct sizes or the narrative budget.
    abi = json.loads((ROOT / "reports/s3-rs-offload-evidence/target-compile.json").read_text())
    layout = abi["workspace_variants"]["O3"]["target_ABI_layout"]
    memory["RS_target_ABI_used_bytes"] = [layout["slot0_RS_used"], layout["slot1_RS_used"]]
    memory["RS_slot_layout_verified"] = all(layout[f"slot{i}_RS_used"] <= 32768 for i in (0, 1))
    return {
        "scope": __doc__, "module": "ESP32-S3-WROOM-1U-N16R8",
        "board_revision": board["board_revision_reference"],
        "board": board,
        "fixed_Octal_Quad_nets_shared_by_T_S": True,
        "data_control_GPIO_count": sum(n["ESP_GPIO"] is not None for n in pins),
        "RECONFIG_GPIO_additional": board["reconfig"]["ESP_GPIO"],
        "physical_IO_STA_verified": False,
        "LCD_alternative_pin_mapping_verified": False,
        "NOR": {"capacity_bytes": CAPACITY, "slots": OFFSETS, "slot_bytes": SLOT,
                "reserved_bytes": len(OFFSETS) * SLOT,
                "capacity_condition_pass": max(OFFSETS.values()) + SLOT <= CAPACITY,
                "actual_receiver_images_available": False, "stock_board_without_modification_supported": False,
                "background_programming_scope": "board external SPI NOR only"},
        "memory": memory,
        "phase_order": ["board/NOR/communication preconditions", "simultaneous memory and explicit budgets",
                        "CPU/FPGA implementation costs", "per-core/memory/buffer schedule",
                        "performance-gated communication assignment", "fixed T/S configuration"],
        "performance_stage_completed": False, "communication_adopted": False,
        "receiver_adopted": False, "complete_estimate": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/s3-ordered-constraints.json")
    args = parser.parse_args()
    result = report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["memory"]["worker_profiles"], indent=2))
