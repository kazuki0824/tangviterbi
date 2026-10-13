#!/usr/bin/env python3
"""Deterministic T Octal-bus simulation under explicit service contracts.

RF payload is continuous (40 B/us). FFT frames become ready periodically after
the ASSUMED two-core WCET; they have priority after the current RF transaction.
This tests output-buffer ownership and RF queue capacity, not CPU WCET, RF bank
polling, clock-domain crossing, Quad RX scheduling or silicon bus arbitration.
"""
import argparse
import json
import math
from pathlib import Path

PERIOD_US = 1039.5
PAYLOAD = 4092
FFT_BYTES = 32768
RF_B_PER_US = 40


def simulate(fft_us=500, gap_us=2, symbols=256, phase_us=0):
    # Reserve one 4092-B RF DMA descriptor outside the queue occupancy below.
    time = 0.0
    sent_rf = 0
    next_frame = 0
    active_frame = None
    fft_remaining = 0
    peak_queue = 0.0
    worst_release = 0.0
    misses = 0
    completed = 0
    transactions = {"RF": 0, "FFT": 0}
    for _ in range(symbols * 30 + 100):
        peak_queue = max(peak_queue, time * RF_B_PER_US - sent_rf)
        release = phase_us + next_frame * PERIOD_US + fft_us
        if active_frame is None and next_frame < symbols and time >= release:
            active_frame = next_frame
            next_frame += 1
            fft_remaining = FFT_BYTES
        if active_frame is not None:
            amount = min(PAYLOAD, fft_remaining)
            duration = (amount + 16) / 80 + .3 + gap_us
            time += duration
            transactions["FFT"] += 1
            peak_queue = max(peak_queue, time * RF_B_PER_US - sent_rf)
            fft_remaining -= amount
            if fft_remaining == 0:
                relative = time - (phase_us + active_frame * PERIOD_US)
                worst_release = max(worst_release, relative)
                misses += relative > PERIOD_US + 1e-9
                completed += 1
                active_frame = None
                if completed == symbols:
                    break
        elif time * RF_B_PER_US - sent_rf >= PAYLOAD - 1e-9:
            # Payload ownership passes to DMA at START, not completion.
            sent_rf += PAYLOAD
            time += (PAYLOAD + 16) / 80 + .3 + gap_us
            transactions["RF"] += 1
        else:
            have_packet = (sent_rf + PAYLOAD) / RF_B_PER_US
            time = min(have_packet, release if next_frame < symbols else math.inf)
    else:
        raise RuntimeError("event bound exhausted")
    return {"FFT_assumed_WCET_us": fft_us, "transaction_gap_us": gap_us,
            "phase_us": phase_us, "symbols": completed,
            "maximum_slot_release_us": worst_release,
            "slot_deadline_us": PERIOD_US, "deadline_misses": misses,
            "maximum_RF_queue_plus_descriptor_bytes": math.ceil(peak_queue) + PAYLOAD,
            "queue_capacity_bytes": 32768, "transactions": transactions,
            "conditional_schedule_pass": misses == 0 and math.ceil(peak_queue) + PAYLOAD <= 32768,
            "hardware_or_CPU_timing_verified": False}


def report():
    # Sweep phase as a stress sample, not a proof over continuous real time.
    scenarios = [simulate(phase_us=phase) for phase in (0, 1, 26.825, 53.65, 102.3, 519.75)]
    fft_service = sum((min(PAYLOAD, FFT_BYTES - i) + 16) / 80 + .3 + 2
                      for i in range(0, FFT_BYTES, PAYLOAD))
    return {"scope": __doc__, "nominal_phase_samples": scenarios,
            "analytic_slot_bound_us": 500 + (PAYLOAD + 16) / 80 + .3 + 2 + fft_service,
            "analytic_additional_total_slack_us": PERIOD_US - 500 - (PAYLOAD + 16) / 80 - .3 - 2 - fft_service,
            "stress_over_WCET": simulate(fft_us=600),
            "stress_over_transaction_gap": simulate(gap_us=10)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
