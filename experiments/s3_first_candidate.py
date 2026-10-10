"""First-candidate necessary-condition audit, not receiver qualification.

No alternate ownership, RF rate reduction, host RS, or changed branch
quantizer is admitted here. Decimal MB/s means bytes per microsecond.
"""
from fractions import Fraction as F
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNERS = {
    'T': {'RF_capture': 'S3', 'FIR': 'FPGA', 'sync': 'FPGA', 'FFT': 'S3',
          'equalize_demap': 'S3', 'time_deinterleave': 'FPGA',
          'Viterbi': 'FPGA', 'RS': 'FPGA', 'TS': 'FPGA'},
    'S': {'RF_capture': 'S3', 'FIR': 'FPGA', 'sync': 'FPGA',
          'TC8PSK': 'FPGA', 'frame_deinterleave': 'FPGA',
          'RS': 'FPGA', 'TS': 'FPGA'},
}

def spi_time(pages):
    return 20 + pages * (F(4106, 80) + F(1, 4))

def route(raw, upstream=F(0), llr=F(0)):
    octal_rf = F(12288) / spi_time(3)
    octal_up = F(4096) / spi_time(1)
    lcd = F(4096) / (F(4112, 80) + 8)
    # Minimax solution for this fixed topology; account for upstream's
    # one-page SPI batches separately from RF's three-page batches.
    rf_o = (raw + llr - lcd * upstream / octal_up) / (1 + lcd / octal_rf)
    rf_l = raw - rf_o
    uo = rf_o / octal_rf + upstream / octal_up
    ul = (rf_l + llr) / lcd
    feasible = 0 <= rf_o <= raw and uo <= 1 and ul <= 1
    return dict(feasible_under_contract=feasible,
                RF_octal_MBps=float(rf_o), RF_LCD16_MBps=float(rf_l),
                IQ_octal_up_MBps=float(upstream), LLR_LCD16_MBps=float(llr),
                octal_utilization=float(uo), LCD16_utilization=float(ul),
                octal_RF_equivalent_spare_MBps=float((1-uo)*octal_rf),
                LCD16_spare_MBps=float((1-ul)*lcd))

def rs_service(mhz, cycles=2667):
    deadline = F(203 * 8, 2) / F('28.86')
    service = F(cycles, mhz)
    return dict(clock_MHz=mhz, serial_RS_engines=1,
                minimum_parallel_engines_for_continuous_rate=math.ceil(service/deadline),
                maximum_tested_cycles=cycles,
                deadline_us=float(deadline), service_us=float(service),
                margin_us=float(deadline-service), passes=service <= deadline,
                required_MHz=float(F(cycles)/deadline))

def evaluate(partial=None):
    r = dict(candidate='S3-T-00c/v2 + S3-S-000/v0', owners=OWNERS,
        ranking_status='former first candidate; physical feasibility and all-candidate ranking require reassessment',
        transport='SPI2 octal 80 MHz half duplex + LCD16 40 MHz down',
        transport_contract=dict(payload_bytes=4096, SPI_header_bytes=10,
            SPI_batch_gap_us=20, SPI_page_gap_us=.25,
            LCD_header_bytes=16, LCD_page_gap_us=8, communication_signals=29),
        RF_formats=dict(T='native 32-bit capture word, 16 MS/s',
                        S='lossless native I10/Q10 packed20, 40 MS/s'),
        T_route=route(F(64), F(32768)/F('1039.5'), F(4992*6)/F('1039.5')),
        S_route=route(F(100)), RS=[rs_service(x) for x in (90,99)],
        TC8PSK_required_MHz=float(F('28.86')*3),
        all_receiver_implemented=False, all_deadlines_verified=False,
        receiver_adopted=False, safe_to_flash=False,
        unclosed=['connected T/S receiver RTL and firmware',
            'T FIR/sync/equalizer/demapper/time deinterleaver/TS',
            'S FIR/sync/frame deinterleaver/TS',
            'LCD16 receiver integration, bidirectional octal endpoint and pin/CDC closure',
            'S3 RF capture + FFT/equalizer/demapper WCET and memory contention',
            'PSRAM arbitration/interleaver deadline and external IO STA',
            'two-image NOR boot/reconfiguration and uninterrupted stream ownership',
            'complete top-level routed timing and RF-to-TS conformance vectors'])
    if partial is not None:
        if partial.get('variant') not in ('s3-memory-fec-compact-b1-rs-acs22-q15-folded-rr',
                                          's3-memory-fec-compact-b1-rs-acs22-q15-folded-rr-lcd16'):
            raise ValueError('not the fixed full-FPGA-RS/SHIFT22/99MHz prerequisite')
        r['partial_FEC_memory_PnR'] = dict(exit_code=partial['exit_code'],
            logic_site_audit=partial.get('logic_site_audit'),
            pnr_trials=partial['pnr_trials'], scope=partial['scope'],
            proves_full_receiver=False)
    return r

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--partial', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = evaluate(json.loads(a.partial.read_text()) if a.partial else None)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
