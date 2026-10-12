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


def report(sdk_path=None):
    current=ROOT/'reports/s3-runtime-control-union-evidence/results.json'
    runtime_path = current if current.exists() else ROOT / "reports/s3-runtime-union-evidence/results.json"
    union_path = runtime_path if runtime_path.exists() else ROOT / "reports/s3-mode-union-evidence/results.json"
    use_union = sdk_path is None and union_path.exists()
    sdk_path = union_path if use_union else (sdk_path or ROOT / "reports/s3-fft-simd-evidence/worker-sdk-ci.json")
    sdk = json.loads(sdk_path.read_text())
    saved_hashes=sdk.get('source_sha256',{})
    runtime_files=[ROOT/'experiments'/(name+suffix) for name in ('s3_pipeline_esp','s3_spi_transport','s3_transport','s3_rf_pump','s3_control','s3_iq_credit','s3_mode_switch','s3_reconfig_esp') for suffix in ('.c','.h')]
    mismatches=[str(p.relative_to(ROOT)) for p in runtime_files if saved_hashes.get(str(p.relative_to(ROOT)))!=hashlib.sha256(p.read_bytes()).hexdigest()]
    if "link" in sdk:
        sdk = {"startup_bound": sdk["startup_bound"], "link_result": sdk["link"],
               "head_sha": sdk.get("repository_base_commit", "unknown")}
        if not sdk["link_result"]["link_succeeded"]:
            raise ValueError("union SDK profile did not link")
    startup = sdk["startup_bound"]["allocator_refinement"]
    free = startup["free_before_DMA_pool_upper_bound_bytes"] - startup["DMA_pool_target_bytes"]
    board = proposal()
    pins = board["nets"]
    memory = {
        'current_runtime_sources_match_saved_SDK':not mismatches,
        'saved_SDK_differs_from_current_sources':mismatches,
        'historical_memory_bound_must_not_certify_changed_firmware':bool(mismatches),
        "sdk_evidence_HEAD": sdk["head_sha"], "SDK_profile_is_integrated_receiver": False,
        "latest_evidence_is_same_binary_T_S_union": use_union,
        "SDK_union_includes_RS_code": sdk["link_result"]["RS_offload_mode_union"],
        "source_sha256": hashlib.sha256(sdk_path.read_bytes()).hexdigest(),
        "RF_raw_three_banks_bytes": 3 * 65536,
        "RF_lossless_packed_ring_bytes": sdk["link_result"].get("ring_pages",16)*4096,
        "SDK_profile": sdk["link_result"].get("profile"),
        "runtime_task_driver_adapters_retained": sdk["link_result"].get("runtime_task_driver_linked",False),
        "mode_slots_bytes": [32768, 32768], "T_SIMD_coefficients_bytes": 16384,
        "slots_are_mutually_exclusive_T_FFT_or_S_RS": True,
        "RS_slot_layout_verified": False,
        "free_after_startup_and_pool_upper_bound_bytes": free,
        "worker_profiles": {
            "two_extra_2KiB_workers": worker_memory(free, [2048, 2048], False),
            "main_RF_owner_one_extra_2KiB_worker": worker_memory(free, [2048], True),
            "two_extra_1KiB_workers": worker_memory(free, [1024, 1024], False),
            "main_RF_owner_one_extra_1KiB_worker": worker_memory(free, [1024], True),
        },
        "not_counted": ["actual worker call-chain stack bound", "SPI/SCT driver objects and configuration",
                        "PHY/calibration", "allocation fragmentation"],
    }
    if sdk["link_result"].get("runtime_task_driver_linked",False):
        memory['selected_runtime_task_configuration']={
            'core0':'existing main task; RF poll/preparation/packing/SPI owner',
            'core1':'one static T FFT task',
            'static_stack_bytes':2048,'target_StaticTask_t_bytes':340,
            'stack_TCB_and_pipeline_state_already_in_ELF_BSS':True,
            'additional_dynamic_task_allocation_bytes':0,
            'internal_spare_upper_bound_before_driver_bytes':free,
            'declared_worker_capacity_necessary_pass':free>=0,
            'all_runtime_memory_verified':False,
            'do_not_subtract_static_stack_TCB_a_second_time':True}
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
