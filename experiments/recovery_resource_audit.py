"""Reconstruct allocations; expose conditional recovery budgets, never adoption."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('logic_sites_estimate', 'FF', 'BSRAM', 'DSP18')
CAP = dict(zip(KEYS, (20736, 15552, 46, 48)))
INPUTS = (
    'reports/20k-dual-s3/summary.json',
    'reports/shared-sdf-evidence/20k-hybrid/summary.json',
    'reports/folded-t-evidence/20k-16-erasure-registered/summary.json',
    'reports/folded-t-evidence/20k-baseline-erasure/summary.json',
)

def total(blocks):
    return {k: sum(v[k] for v in blocks.values()) for k in KEYS}

def kernel(p):
    return dict(zip(KEYS, (p['logic_positions'], p['FF'], p['BSRAM'],
                          p['utilization']['MULT18X18']['used'])))

def run():
    old, fft, folded, baseline = [json.loads((ROOT / p).read_text()) for p in INPUTS]
    old = next(x for x in old['candidates'] if x['id'] == 'B_tiled_shared_RS')
    assert total(old['blocks']) == old['resources']
    blocks = copy.deepcopy(old['blocks'])
    blocks['FFT_tiled'] = dict(zip(KEYS, (fft['routed_logic_positions'],
        fft['routed_utilization']['DFF']['used'],
        fft['routed_utilization']['BSRAM']['used'],
        fft['routed_utilization']['MULT18X18']['used'])))
    blocks['T_K7'] = kernel(folded)
    current = total(blocks)
    reserve_name = 'IO_SDRAM_TMCC_control_reserve'
    measured_names = ('FFT_tiled', 'T_K7')
    measured = total({k: blocks[k] for k in measured_names})
    estimates = total({k: v for k,v in blocks.items() if k not in measured_names and k != reserve_name})
    remaining = {k: CAP[k] - measured[k] - estimates[k] for k in KEYS}
    shared = copy.deepcopy(blocks)
    del shared['T_K7'], shared['S_BPSK_QPSK_K7_extra']
    shared['shared_K7_one_context_probe'] = kernel(baseline)
    shared_total = total(shared)
    rate_t = 4992 * 6 * (7 / 8) / 1039.5
    # Conservative S rate-7/8 QPSK demand; retain previous full-mode model.
    rate_s = 28.86 * 2 * (7 / 8)
    scenarios = []
    for mhz in (162, 180):
        required = 2 * (rate_t + rate_s)
        scenarios.append(dict(clock_MHz=mhz, required_MHz=required,
            arithmetic_utilization_percent=100*required/mhz,
            extra_cycles_per_second=(mhz-required)*1e6,
            full_context_implementation_verified=False))
    return dict(scope=__doc__, inputs_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in INPUTS},
        blocks=blocks, reconstructed=current, separately_measured=measured,
        inherited_stage_allocations=estimates, integration_reserve=blocks[reserve_name],
        maximum_integration_if_other_blocks_unchanged=remaining,
        duplicate_reserve_entries=0, proven_duplicate_savings=dict.fromkeys(KEYS,0),
        independent_kernel_missing=['T three-hierarchy context', 'S K7 correct full-mode implementation',
                                    'physical memory/transport/CDC/TMCC integration'],
        shared_K7=dict(conditional_resources=shared_total,
            maximum_additional_cost={k:CAP[k]-shared_total[k] for k in KEYS},
            rates_Mstep_s=dict(T=rate_t,S=rate_s), scenarios=scenarios,
            four_context_survivor_bits=4*256*64,
            additional_metric_bits_over_one_context=3*64*13,
            memory_warning='bit counts only; ports, packing, output banks and scheduling not implemented',
            adopted=False),
        formally_assigned_routes=0, adopted_receivers=0)

if __name__ == '__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
