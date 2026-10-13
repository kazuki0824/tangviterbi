#!/usr/bin/env python3
"""Conditional simulation of the implemented 4-KiB / 80-bit-header transport.

API batch overhead and actual SCT segment gap are PARAMETERS, not WCET claims.
20 us samples the official SPI interrupt-overhead guidance; no source promises
this bound for the private SCT API. CPU/RF bank acquisition and Quad IQ arrival
are not jointly simulated. No sample is discarded to make an overload pass.
"""
import argparse
import json
import math
from pathlib import Path

PAGE = 4096
RING = 32768
PERIOD = 1039.5


def service(pages, lanes=8, batch_us=20, segment_us=.25):
    # 16 command bits + 64 address bits, all using the selected line width.
    return pages * (PAGE / (80 * lanes / 8) + 80 / (80 * lanes) + segment_us) + batch_us


def terrestrial(fft_us=500, batch_us=20, segment_us=.25, phase_us=0, symbols=512,
                admission=True):
    t = 0.
    retired = 0
    next_frame = 0
    peak = 0.
    worst = 0.
    misses = 0
    bursts = {str(n): 0 for n in (1, 2, 3)}
    fft_service = service(8, batch_us=batch_us, segment_us=segment_us)
    for _ in range(symbols * 30 + 100):
        peak = max(peak, t * 40 - retired * PAGE)
        release = phase_us + next_frame * PERIOD + fft_us
        deadline = phase_us + (next_frame + 1) * PERIOD
        if t >= release - 1e-9:
            t += fft_service
            peak = max(peak, t * 40 - retired * PAGE)
            elapsed = t - phase_us - next_frame * PERIOD
            worst = max(worst, elapsed)
            misses += elapsed > PERIOD + 1e-7
            next_frame += 1
            if next_frame == symbols:
                break
            continue
        available = math.floor((t * 40 + 1e-7) / PAGE) - retired
        n = min(3, available)
        full_at = max(t, (retired + 3) * PAGE / 40)

        def allowed(start, pages):
            end = start + service(pages, batch_us=batch_us, segment_us=segment_us)
            return not admission or max(end, release) + fft_service <= deadline + 1e-7

        # Amortize API overhead with three RF pages, except when waiting for
        # or starting that batch could violate the known FFT slot deadline.
        if n < 3 and full_at < release and allowed(full_at, 3):
            t = full_at
            continue
        while n and not allowed(t, n):
            n -= 1
        if n:
            t += service(n, batch_us=batch_us, segment_us=segment_us)
            peak = max(peak, t * 40 - retired * PAGE)  # still DMA-owned
            retired += n
            bursts[str(n)] += 1
        else:
            one_at = (retired + 1) * PAGE / 40
            t = min(release, one_at) if one_at > t + 1e-7 else release
    else:
        raise RuntimeError("event bound exhausted")
    peak_reserved = math.ceil((peak - 1e-7) / PAGE) * PAGE
    return {"standard": "T", "FFT_assumed_us": fft_us, "API_batch_assumed_us": batch_us,
            "SCT_segment_assumed_us": segment_us, "phase_us": phase_us,
            "admission_guard": admission, "symbols": next_frame,
            "maximum_slot_release_us": worst, "deadline_misses": misses,
            "peak_RF_live_bytes": math.ceil(peak), "peak_RF_page_reservation": peak_reserved,
            "ring_bytes": RING, "RF_batches": bursts,
            "conditional_pass": misses == 0 and peak_reserved <= RING,
            "silicon_WCET_verified": False}


def satellite(batch_us=20, segment_us=.25, quad_gap_us=20, duration_us=100000):
    t = 0.
    claimed = retired = 0
    done = set()
    ports = [None, None]
    peak_pages = reorder = 0
    transferred = [0, 0]
    while t < duration_us:
        # Reap both completions before submitting more work. Retire only the
        # contiguous prefix, exactly as s3_tx_ring does for unequal SPI ports.
        for i, p in enumerate(ports):
            if p and p[0] <= t + 1e-7:
                done.update(range(p[1], p[1] + p[2]))
                transferred[i] += p[2] * PAGE
                ports[i] = None
        while retired in done:
            done.remove(retired)
            retired += 1
        reorder = max(reorder, len(done))
        peak_pages = max(peak_pages, math.ceil(t * 100 / PAGE - 1e-9) - retired)
        available = math.floor(t * 100 / PAGE + 1e-9) - claimed
        for i, n in ((0, 3), (1, 1)):
            if ports[i] is None and available >= n:
                duration = (service(n, batch_us=batch_us, segment_us=segment_us) if i == 0 else
                            service(1, lanes=4, batch_us=quad_gap_us, segment_us=0))
                ports[i] = (t + duration, claimed, n)
                claimed += n
                available -= n
        next_times = [p[0] for p in ports if p]
        for i, n in ((0, 3), (1, 1)):
            if ports[i] is None:
                next_times.append((claimed + n) * PAGE / 100)
        nxt = min(next_times)
        # Producer fills a partial page too. Count DMA-held pages up to the
        # event BEFORE release; do not hide in-flight storage in a rate sum.
        peak_pages = max(peak_pages, math.ceil(nxt * 100 / PAGE - 1e-9) - retired)
        t = nxt
    capacities = [3 * PAGE / service(3, batch_us=batch_us, segment_us=segment_us),
                  PAGE / service(1, lanes=4, batch_us=quad_gap_us, segment_us=0)]
    return {"standard": "S", "API_batch_assumed_us": batch_us,
            "SCT_segment_assumed_us": segment_us, "Quad_API_assumed_us": quad_gap_us,
            "duration_us": duration_us, "port_capacity_MBps": capacities,
            "aggregate_spare_MBps": sum(capacities) - 100,
            "peak_RF_page_reservation": peak_pages * PAGE, "ring_bytes": RING,
            "maximum_out_of_order_completed_bytes": reorder * PAGE,
            "transferred_bytes": transferred,
            "conditional_pass": peak_pages * PAGE <= RING and sum(capacities) >= 100,
            "silicon_WCET_verified": False}


def report():
    sweep = [terrestrial(phase_us=i*PERIOD/256, symbols=256) for i in range(256)]
    return {"scope": __doc__, "payload_bytes": PAGE, "header_bits": 80,
            "T_phase_samples": [terrestrial(phase_us=p) for p in (0, 1, 51.2, 173.975, 519.75)],
            "T_phase_sweep": {"phases": len(sweep), "symbols_per_phase": 256,
                "failed_phase_count": sum(not x["conditional_pass"] for x in sweep),
                "maximum_slot_release_us": max(x["maximum_slot_release_us"] for x in sweep),
                "maximum_live_RF_bytes": max(x["peak_RF_live_bytes"] for x in sweep),
                "maximum_page_reservation": max(x["peak_RF_page_reservation"] for x in sweep)},
            "T_without_admission": terrestrial(admission=False, phase_us=519.75),
            "T_slow_API": terrestrial(batch_us=30),
            "T_slow_SCT": terrestrial(segment_us=2),
            "S": satellite(), "S_slow_API": satellite(batch_us=40, quad_gap_us=40),
            "ordinary_IRQ_capacity_MBps": {"Octal": PAGE / service(1, segment_us=0),
                                           "Quad": PAGE / service(1, lanes=4, segment_us=0)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
