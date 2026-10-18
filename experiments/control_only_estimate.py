#!/usr/bin/env python3
"""Recheck the 2026-10-17 control-only-return request. Stdlib; no CAD claims.

Units: decimal MB/s, MHz, microseconds. A capacity witness is NEVER a
performance pass. Every unknown gate stays unknown, including after routing.
"""
import argparse
import copy
import csv
import gzip
import hashlib
import io
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = '9a5b5d28d2350a312bf0d73d264ac5af6fe83dd6'
CAPS = {'9k': [8640, 6480, 26, 20], '20k': [20736, 15552, 46, 48]}
KEYS = ['logic_sites_estimate', 'FF', 'BSRAM', 'DSP18']
ORDER = {'T': ['FIR', 'sync', 'FFT', 'equalize_demap', 'time_deinterleave', 'Viterbi', 'RS', 'TS'],
         'S': ['FIR', 'sync', 'TC8PSK', 'frame_deinterleave', 'RS', 'TS']}
T_PERIOD = 1039.5
T_RS = 4992 * 6 * 7 / 8 / T_PERIOD * 1e6 / (204 * 8)
S_RS = 28.86e6 * 2 / (203 * 8)
TMCC_RS = 28.86e6 / (39936 * 8)
PAGE = 4096
INPUTS = ['reports/s3-partition-audit/inputs.json.gz',
          'reports/s3-partition-audit/estimate.json.gz',
          'reports/four-soc-comparison/inputs.json.gz',
          'reports/20k-dual-s3/summary.json',
          'reports/20k-dual-s3/components/summary.json']


def read(path):
    data = (ROOT / path).read_bytes()
    return json.loads(gzip.decompress(data) if path.endswith('.gz') else data)


def gz_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    path.write_bytes(gzip.compress(data, mtime=0))


def occupancy(values, board):
    return {k: 100 * values[k] / c for k, c in zip(KEYS, CAPS[board])}


def cpu_before_driver(row):
    """Independent reproduction of the old sensitivity model, with one fix.

    The old audit charged FFT_reorder_unpack in its stage sum AND once again
    as an FFT surcharge. Count it once. All other inherited assumptions stay
    explicit; none becomes a measured instruction count or an upper bound.
    """
    own, st = row['owners'], row['standard']
    flows = corrected_flows(row)
    out = []
    for high in (0, 1):
        if own['FIR'] == 'FPGA':
            total = (153.375 + 32 * high if st == 'T' else 368.4375 + 80 * high)
        else:
            total = (36.54166666666667 + 20.833333333333334 if st == 'T'
                     else 76.35416666666667 + 52.083333333333336)
        for node, values in row['stage_CPU_models'].items():
            if node == 'TS':
                continue
            if node == 'RS':
                cost = 22060 * (T_RS if st == 'T' else S_RS) / 1e6
            elif node == 'frame_deinterleave':
                cost = (20 if high else 14) * S_RS * 204 / 1e6
            else:
                cost = values['known_model_Mcycles_per_s'][high]
            total += cost
        if own['sync'] == 'SoC':
            total += (16 if high else 8) * (8192 / 1008 if st == 'T' else 28.86)
        total += sum(f['MBps'] for f in flows if f['source'] != 'RF') * (2 if high else 1)
        out.append(total)
    return out


def corrected_flows(row):
    flows = copy.deepcopy(row['crossings'])
    for f in flows:
        if row['standard'] == 'T' and f['source'] == 'sync' and f['target'] == 'FFT':
            f['MBps'] = 8192 * 4 / T_PERIOD
            f['format'] = 'all useful complex Q15 samples after GI removal'
        if row['standard'] == 'S' and f['format'] == 'RS204 codewords':
            f['MBps'] = S_RS * 204 / 1e6
        if row['standard'] == 'S' and f['format'] == 'coded-frame byte stream':
            f['MBps'] = 28.86 * 2 / 8
        if f['source'] == 'RF':
            f['format'] = 'native I10/Q10, lossless packing, 5 bytes / 2 samples'
    return flows


def rows(board):
    source = read(INPUTS[0])
    previous = {r['id']: r for r in read(INPUTS[1])['assignments']}
    profiles_by_id = {r['id']: r for r in read(INPUTS[2])['mode_profiles']}
    out = []
    for row in source['assignments']:
        if row['SoC'] != 'S3':
            continue
        st, own = row['standard'], row['owners']
        flows = corrected_flows(row)
        reverse = [f for f in flows if f['direction'] == 'FPGA→SoC']
        profile = next(p for p in profiles_by_id[row['id']]['profiles']
                       if not p['high'] and p['FPGA_MHz'] == 125
                       and (p['RF_format'] == 'lossless20' or own['FIR'] == 'SoC'))
        stage = {k: sum(v[k] for v in profile['FPGA_stage_estimates'].values()) for k in KEYS}
        cpu = cpu_before_driver(row)
        total_crossing = sum(f['MBps'] for f in flows)
        old_reproduced = [x + total_crossing * 200 / PAGE for x in cpu]
        correction = [0., 0.]
        if st == 'T' and own['FFT'] == 'SoC':
            correction = [46791.72679172679 / 1000, 93583.45358345358 / 1000]
        delta = [old_reproduced[i] + correction[i] - previous[row['id']]['CPU_low_high_Mcycles_s'][i]
                 for i in (0, 1)]
        req = dict(profile['stage_required_MHz'])
        if 'RS' in req:
            req['RS'] = 2667 * (T_RS if st == 'T' else S_RS) / 1e6
        if st == 'S' and 'trellis' in req:
            req['trellis'] = 86.58
        reasons = []
        if reverse:
            reasons.append('FORBIDDEN_FPGA_TO_SOC_PAYLOAD')
        if cpu[0] > 480:
            reasons.append('INHERITED_LOW_CPU_MODEL_EXCEEDS_TWO_CORES')
        if st == 'S' and any('ARITHMETIC' in r for r in row['stage1_reasons']):
            reasons.append('SELECTED_TC8PSK_ARITHMETIC_MODEL_FAIL')
        if st == 'T' and own['time_deinterleave'] == 'SoC' and board == '9k':
            reasons.append('N16_NO_PSRAM_CANNOT_HOLD_5690880_BYTE_TIME_DEINTERLEAVER')
        out.append(dict(id=row['id'], standard=st, owners=own, flows=flows,
                        forward_MBps=sum(f['MBps'] for f in flows if f['direction'] == 'SoC→FPGA'),
                        reverse_payload_MBps=sum(f['MBps'] for f in reverse),
                        command_only_return_compatible=not reverse,
                        stage_resources=stage, stage_occupancy_percent=occupancy(stage, board),
                        stage_resources_are_incomplete=True,
                        missing_resources=['physical receiver frontend and all TMCC paths',
                                           'transport, CDC, memory PHY, arbitration, queues',
                                           'S BPSK/QPSK and T hierarchical contexts'],
                        whole_resources=None, CPU_before_driver_Mcycles_s=cpu,
                        CPU_before_driver_percent=[100 * x / 480 for x in cpu],
                        CPU_model_recheck_error_Mcycles_s=delta,
                        removed_duplicate_reorder_Mcycles_s=correction,
                        selected_stage_required_MHz=req,
                        RS_arrival_deadline_us=1e6 / (T_RS if st == 'T' else S_RS),
                        T_symbol_deadlines_us=[259.875, 519.75, 1039.5] if st == 'T' else None,
                        CPU_WCET=None, whole_performance_pass=None, reasons=reasons,
                        route_catalog=None, formal_routes=[], adopted=False))
    return out


def ports():
    """Finite declared native-peripheral catalogue. No undocumented high clock.

    All 18 historical profiles are retained; return-only bulk paths are marked
    not required, since the dedicated command wire carries no received data.
    """
    values = []
    for ctl in (2, 3):
        for w in ((1, 2, 4, 8) if ctl == 2 else (1, 2, 4)):
            batch = 3 if w == 8 else 1
            duration = batch * (PAGE / (10 * w) + 1 / w + (.25 if w == 8 else 0)) + 20
            values.append(dict(name=f'SPI{ctl}_{w}bit_80', group=f'SPI{ctl}', pins=10 if w == 8 else 6 if w == 4 else 4,
                               capacity_MBps=batch * PAGE / duration, batch_bytes=batch * PAGE,
                               API_active_us=20, dma_tx=1, dma_rx=1, direction='forward'))
    for prefix in ('LCD', 'CAM'):
        for width in (8, 16):
            c = width * 40 / 8
            values.append(dict(name=f'{prefix}{width}_40', group=prefix, pins=width + 3,
                               capacity_MBps=PAGE / ((PAGE + 16) / c + 8), batch_bytes=PAGE,
                               API_active_us=8, dma_tx=int(prefix == 'LCD'), dma_rx=int(prefix == 'CAM'),
                               direction='forward' if prefix == 'LCD' else 'return_only'))
    for name, c, pins in [('SDIO4_SDR40', 20, 6), ('eMMC8_SDR40', 40, 10), ('eMMC4_DDR40', 40, 6)]:
        values.append(dict(name=name, group='SDHOST', pins=pins,
                           capacity_MBps=PAGE / ((PAGE + 16) / c + (96 + 18 * 9) / 40 + 20),
                           batch_bytes=PAGE, API_active_us=20, dma_tx=0, dma_rx=0, direction='forward'))
    for ctl in (0, 1):
        for direction in ('TX', 'RX'):
            values.append(dict(name=f'I2S{ctl}_{direction}40', group=f'I2S{ctl}', pins=3,
                               capacity_MBps=PAGE / ((PAGE + 16) / 5), batch_bytes=PAGE,
                               API_active_us=0, dma_tx=int(direction == 'TX'), dma_rx=int(direction == 'RX'),
                               direction='forward' if direction == 'TX' else 'return_only'))
    return values


def port_sets():
    ps = [p for p in ports() if p['direction'] == 'forward']
    result = []
    for n in range(1, len(ps) + 1):
        for group in itertools.combinations(ps, n):
            if len({p['group'] for p in group}) != len(group):
                continue
            pins = sum(p['pins'] for p in group)
            if pins + 1 > 30 or sum(p['dma_tx'] for p in group) > 5 or sum(p['dma_rx'] for p in group) > 5:
                continue
            result.append(group)
    return result


def bandwidth_routes(rate, sets):
    """Equal-utilization capacity witness, not a finite-page DMA schedule.

    0.01 MB/s forward configuration is included in data framing. Separate
    1-Mbaud 8N1 FPGA->S3 command-only wire: 0.1 MB/s, 0.01 MB/s demand.
    """
    need = rate + .01
    result = []
    for group in sets:
        c = sum(p['capacity_MBps'] for p in group)
        if c < need:
            continue
        links = []
        api = 0
        for p in group:
            load = need * p['capacity_MBps'] / c
            api += load * 240 * p['API_active_us'] / p['batch_bytes']
            links.append(dict(name=p['name'], forward_MBps=load, capacity_MBps=p['capacity_MBps'],
                              spare_MBps=p['capacity_MBps'] - load, spare_percent=100 * (1 - need / c)))
        alternatives = []
        # Enumerate alternative command paths as factored records, rather
        # than multiplying identical bulk-transport rows. 10 kB/s is a
        # reservation, not a guarantee of command latency/packet overhead.
        for p in group:
            if p['name'].startswith(('SPI', 'SDIO', 'eMMC')):
                cap_after = c - .01
                if cap_after >= need:
                    alternatives.append(dict(route=p['name'] + ':half_duplex_return', extra_pins=0,
                        return_MBps=.01, capacity_reservation_MBps=.01,
                        forward_spare_MBps=cap_after - need,
                        forward_assignment=[dict(name=q['name'], MBps=need * (q['capacity_MBps'] - (.01 if p is q else 0)) / cap_after)
                                            for q in group], physical_and_packet_timing_verified=False))
        # Dedicated low-rate command paths; upward configuration stays on
        # the data path. I2C's 40 kB/s is a rounded scenario below 400k/9.
        for name, pins, capacity in [('UART_1M_8N1', 1, .1), ('I2C_400k', 2, .04)]:
            if sum(p['pins'] for p in group) + pins <= 30:
                alternatives.append(dict(route=name, extra_pins=pins, return_MBps=.01,
                    command_spare_MBps=capacity - .01, forward_spare_MBps=c - need,
                    physical_and_packet_timing_verified=False))
        result.append(dict(id=len(result), ports=[p['name'] for p in group],
                           data_pins=sum(p['pins'] for p in group),
                           capacity_MBps=c, required_MBps=need, spare_MBps=c - need,
                           spare_percent=100 * (1 - need / c), links=links,
                           driver_active_model_Mcycles_s=api,
                           command_return=dict(route='UART_1M_8N1', pins=1, required_MBps=.01,
                                               capacity_MBps=.1, spare_MBps=.09, spare_percent=90),
                           command_alternatives=alternatives,
                           GPIO_mapping_verified=False, endpoint_WCET=None, formally_assigned=False))
    return result


def dedicated_gpio():
    """eSpDR source timing + declared 600/2400-cycle non-payload budgets.

    Sweep every legal bank length and all 16 alignment offsets. Upstream
    reports 80 MSa/s on Artix-7; this model is NOT its measured WCET.
    """
    result = []
    for rate, lanes in [(16, 1), (16, 2), (40, 1), (40, 2), (80, 2)]:
        worst = max(((math.ceil((n + align) / 16) * 91 + 600 + 2400) / 240 / (lanes * n / rate), n, align)
                    for n in range(15360, 16289) for align in range(16))
        duty, n, align = worst
        result.append(dict(rate_Msamples_s=rate, lanes=lanes, payload_MBps=rate * 2.5,
                           loop_capacity_MBps=lanes * 240 * 40 / 91,
                           framed_budget_capacity_MBps=rate * 2.5 / duty,
                           spare_MBps=rate * 2.5 * (1 / duty - 1), spare_percent=100 * (1 - duty),
                           each_active_core_useful_service_percent=100 * duty,
                           busy_polling_core_percent=100,
                           CPU_aggregate_useful_percent=100 * duty * lanes / 2,
                           worst_n=n, worst_alignment=align,
                           service_us=(math.ceil((n + align) / 16) * 91 + 3000) / 240,
                           same_core_arrival_us=lanes * n / rate,
                           data_clock_pins=8 * lanes + 1, command_pins=1,
                           framing_budget_cycles=600, capture_service_budget_cycles=2400,
                           all_budgets_unmeasured_on_Tang=True,
                           max_ahead_unit_packed_bytes=math.ceil((16288 + 15) / 16) * 40,
                           reorder_full_spill_memory_MBps=2 * rate * 2.5 if lanes == 2 else 0,
                           full_receiver_fit=None, assigned=False))
    return result


def technical_rechecks():
    d = read(INPUTS[3])
    # Preserve original allocation status; independently add every block.
    revised = []
    for c in d['candidates']:
        sums = {k: sum(b[k] for b in c['blocks'].values()) for k in KEYS}
        revised.append(dict(id=c['id'], recomputed=sums, stored=c['resources'],
                            arithmetic_equal=sums == c['resources'], allocation_not_synthesis=True))
    fft = []
    for n in (2048, 4096, 8192):
        period = n / (512 / 63) * 33 / 32
        cycles = n * (int(math.log2(n)) + 4)
        fft.append(dict(n=n, period_us=period, tiled_cycles=cycles,
                        target162_utilization=cycles / (162 * period),
                        resident_delay_bytes=(n - 1) * 4,
                        hybrid_internal_delay_bytes=(n // 2 - 1) * 4,
                        hybrid_external_traffic_MBps=8 * n / period))
    return dict(archived_20k_allocations=revised, fft=fft,
                T_TS_Mbit_s=T_RS * 188 * 8 / 1e6,
                S_RS_deadline_us=1e6 / S_RS, T_RS_deadline_us=1e6 / T_RS,
                shared_RS_required_MHz=(T_RS + S_RS + TMCC_RS) * 2672 / 1e6,
                S_compact_RS_required_MHz=S_RS * 2667 / 1e6,
                S_best_partial_recorded_MHz=93.1532,
                K7_shared_T_plus_QPSK_required_MHz=2 * (T_RS * 204 * 8 + 28.86e6 * 2 * 7 / 8) / 1e6,
                K7_context_switch_and_T_hierarchical_contexts_included=False,
                T_time_deinterleave_bytes=5690880,
                PSRAM_equal_read_write_pin_model_MBps=512 * 99 / (82 + 87),
                old_tiled_SDRAM_MBps=6 * 8192 * 4 / T_PERIOD + 2 * 4992 * 6 / T_PERIOD + 2 * S_RS * 204 / 1e6 + 10,
                eSpDR_source='f279bf823eee41796dfd1ac21f13e1ed9b418c82',
                GPIO_internal_memory_reserved_bytes=(16 + 32 + 64 + 64 + 256) * 1024,
                GPIO_memory_fraction_of_512KiB=432 / 512)


def run(board, output):
    output.mkdir(parents=True, exist_ok=True)
    all_rows = rows(board)
    allowed = [r for r in all_rows if r['command_only_return_compatible']]
    sets = port_sets()
    catalog = {}
    for row in allowed:
        rate = row['forward_MBps']
        key = f'{rate:.9f}'
        if key not in catalog:
            catalog[key] = bandwidth_routes(rate, sets)
        row['route_catalog'] = key
        # Auxiliary capacity computation, never step 2 of the acceptance gate.
        row['auxiliary_bandwidth_routes'] = len(catalog[key])
        row['CPU_after_driver_best_low_percent'] = min(
            (row['CPU_before_driver_Mcycles_s'][0] + r['driver_active_model_Mcycles_s']) / 4.8
            for r in catalog[key]) if catalog[key] else None
    ts = [r for r in allowed if r['standard'] == 'T']
    ss = [r for r in allowed if r['standard'] == 'S']
    pairs = []
    for t, s in itertools.product(ts, ss):
        res = {k: (max(t['stage_resources'][k], s['stage_resources'][k]) if board == '9k'
                   else t['stage_resources'][k] + s['stage_resources'][k]) for k in KEYS}
        pairs.append(dict(T=t['id'], S=s['id'], stage_resources=res,
                          stage_occupancy_percent=occupancy(res, board),
                          aggregation='separate_images_max' if board == '9k' else 'simultaneous_sum',
                          CPU_models_separate=True, whole_resources=None,
                          performance_pass=None, formal_routes=[], adopted=False))
    # Complete compatibility table for the two raw-data paths. For 9K use a
    # fixed wiring *union*, not max of pin counts for incompatible peripherals.
    raw_t = catalog['40.000000000']
    raw_s = catalog['100.000000000']
    by_name = {p['name']: p for p in ports()}
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(['T_route', 'S_route', 'signal_pins_including_TS_commands', 'T_spare_MBps', 'S_spare_MBps'])
    raw_pairs = 0
    for t, s in itertools.product(raw_t, raw_s):
        if board == '20k':
            pins = t['data_pins'] + s['data_pins'] + 6 + 2
        else:
            names = set(t['ports']) | set(s['ports'])
            # Different width variants can share wires; reserve the maximum
            # pins per controller and remap only between stopped images.
            group_pins = {}
            for name in names:
                p = by_name[name]
                group_pins[p['group']] = max(group_pins.get(p['group'], 0), p['pins'])
            pins = sum(group_pins.values()) + 3 + 1
        if pins <= (35 if board == '9k' else 34):
            writer.writerow([t['id'], s['id'], pins, t['spare_MBps'], s['spare_MBps']])
            raw_pairs += 1
    (output / 'raw-route-pairs.csv.gz').write_bytes(gzip.compress(text.getvalue().encode(), mtime=0))
    gz_json(output / 'all-ownerships.json.gz', all_rows)
    gz_json(output / 'all-allowed-pairs.json.gz', pairs)
    gz_json(output / 'bandwidth-catalog.json.gz', catalog)
    summary = dict(base_commit=BASE, board=board, capacity=dict(zip(KEYS, CAPS[board])),
                   source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in INPUTS},
                   all_stage_ownership_count=len(all_rows), forbidden_return_count=len(all_rows) - len(allowed),
                   allowed_T_count=len(ts), allowed_S_count=len(ss), allowed_pair_count=len(pairs),
                   all_stage_pair_count=256 * 64, profile_count=len(ports()),
                   auxiliary_port_set_count=len(sets), auxiliary_raw_pair_count=raw_pairs,
                   maximum_legacy_CPU_recheck_error=max(abs(x) for r in all_rows for x in r['CPU_model_recheck_error_Mcycles_s']),
                   profiles=ports(), dedicated_gpio=dedicated_gpio(), rechecks=technical_rechecks(),
                   performance_confirmed_count=0, formally_assigned_count=0, adopted_count=0,
                   complete_feasibility_estimate=False,
                   stage1_unknowns=['complete FPGA allocation/placement/STA', 'per-core joint WCET',
                                    'RF continuous acquisition and channel bandwidth', 'memory arbitration and finite queue bounds'],
                   control_rule='FPGA->S3: commands only; no IQ/FFT/LLR/syndrome/coefficients/TS',
                   lossless_rule='No additional software decimation or precision reduction for transport')
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    # Readable complete monotone boundary table, no hidden rows.
    table = ['| ID | SoC prefix (plus RF) | CPU low/high before link % | stage logic/FF/BSRAM/DSP | forward MB/s |',
             '|---|---|---:|---|---:|']
    for r in allowed:
        prefix = ', '.join(k for k in ORDER[r['standard']] if r['owners'][k] == 'SoC') or 'RF only'
        cpu = '/'.join(f'{x:.3f}' for x in r['CPU_before_driver_percent'])
        resources = '/'.join(str(r['stage_resources'][k]) for k in KEYS)
        table.append(f"| {r['id']} | {prefix} | {cpu} | {resources} | {r['forward_MBps']:.6f} |")
    (output / 'all-boundaries.md').write_text('\n'.join(table) + '\n')
    print(json.dumps({k: summary[k] for k in ['board', 'allowed_T_count', 'allowed_S_count', 'allowed_pair_count',
                                             'auxiliary_port_set_count', 'auxiliary_raw_pair_count',
                                             'maximum_legacy_CPU_recheck_error', 'adopted_count']}))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', choices=CAPS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.board, args.output)
