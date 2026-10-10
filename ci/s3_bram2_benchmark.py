"""Reproduce the partial S transport/FEC co-placement experiment.

This does not implement the RF receiver, full producer scheduler, or all page deadlines.
No placement wall-time cap is imposed. nextpnr failure remains a failed result.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
sys.path.insert(0, str(ROOT / 'ci'))
from s3_tc8psk import source as tc_source
from s3_rs_isdb import source as rs_source
from s3_rs_syndrome_registered import source as registered_syndrome
from s3_logic_site_audit import audit


def run(args, log):
    with log.open('w') as f:
        return subprocess.run(args, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='build/s3-bram2-fec-repro')
    ap.add_argument('--slot-bits',type=int,choices=(1,2,3),default=1)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--chunked-compare', action='store_true',
                    help='experimental logically equivalent 4+4+3-bit borrow comparison')
    ap.add_argument('--rs-split', action='store_true',
                    help='independent syndrome/Chien workload; host BM and RPC absent')
    ap.add_argument('--acs32', action='store_true',
                    help='32 ACS lanes / 2 clocks per Viterbi input')
    ap.add_argument('--core-mhz', type=int, choices=(90, 99), default=99)
    ap.add_argument('--correction', action='store_true',
                    help='add byte correction independent workload to RS split')
    ap.add_argument('--syndrome-address-pipeline',action='store_true')
    ap.add_argument('--syndrome-ready', action='store_true',
                    help='register syndrome end-of-input ready flag')
    ap.add_argument('--pipe-window', action='store_true',
                    help='pipeline page window subtraction before range reduction')
    ap.add_argument('--parallel-traceback-choice', action='store_true')
    ap.add_argument('--fixed-arbiter', action='store_true')
    ap.add_argument('--page-status', action='store_true',
                    help='connect Octal retired-frontier snapshot endpoint')
    args = ap.parse_args()
    if (args.correction or args.syndrome_ready or args.syndrome_address_pipeline) and not args.rs_split:
        ap.error('--correction and --syndrome-ready require --rs-split')
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    for stale in ('result.json','routed.json','report.json','packed.json'):
        (out/stale).unlink(missing_ok=True)
    vit = tc_source(True, True, 32 if args.acs32 else 22, True, args.parallel_traceback_choice)
    if args.chunked_compare:
        vit = vit.replace('    reg signed [METRIC_W-1:0] metric_difference;',
                          '    reg [METRIC_W-1:0] metric_difference;\n'
                          '    reg borrow0, borrow1, borrow2;')
        vit = vit.replace(
            '            metric_difference = cand1[METRIC_W-1:0] - cand0[METRIC_W-1:0];',
            '''            borrow0 = cand1[3:0] < cand0[3:0];
            borrow1 = (cand1[7:4] < cand0[7:4]) || ((cand1[7:4] == cand0[7:4]) && borrow0);
            borrow2 = (cand1[10:8] < cand0[10:8]) || ((cand1[10:8] == cand0[10:8]) && borrow1);
            metric_difference = {cand1[11] ^ cand0[11] ^ borrow2, 11'b0};''')
        vit = vit.replace('if (metric_difference < 0)',
                          'if (metric_difference[METRIC_W-1])')
    (out / 'viterbi.sv').write_text(vit)
    (out / 'rs.sv').write_text(rs_source(True, True))
    clock_source = (ROOT / 'rtl/s3_psram_clock.sv').read_text()
    if args.core_mhz == 90:
        clock_source = (clock_source.replace('99 MHz', '90 MHz')
                        .replace('792 MHz', '720 MHz')
                        .replace('.FBDIV_SEL(10)', '.FBDIV_SEL(9)'))
    (out / 'clock.sv').write_text(clock_source)
    (out / 'clocks.py').write_text(
        (ROOT / 'experiments/s3_bram2_clocks.py').read_text().replace(
            "'bridge.clk',99", f"'bridge.clk',{args.core_mhz}").replace(
            "'clk_ck',99", f"'clk_ck',{args.core_mhz}"))
    top = (ROOT / 'experiments/s3_memory_bram2_fec_benchmark.sv').read_text()
    top=top.replace('s3_bram2_memory_bridge bridge',
        f's3_bram2_memory_bridge #(.PIPE_WINDOW({int(args.pipe_window)}),.SLOT_BITS({args.slot_bits}),.FIXED_ARBITER({int(args.fixed_arbiter)})) bridge')
    if args.page_status:
        top=top.replace('input wire [7:0] spi2_d','inout wire [7:0] spi2_d')
        top=top.replace(' assign activity=', ''' wire [7:0] status_data;wire status_oe,status_fault;
 s3_spi_page_status #(.WINDOW(WINDOW_VALUE)) status(clk,rst,16'd1,retired_sequence,fault,
  spi2_clock_global,spi2_cs_n,spi2_d,status_data,status_oe,status_fault);
 assign spi2_d=status_oe?status_data:8'bz;
 assign activity=''' ).replace('WINDOW_VALUE',str(1<<args.slot_bits)).replace('checksum,offset,','status_fault,checksum,offset,')
    if args.rs_split:
        top = top.replace('rs204_188_compact rs(clk,rst,rs_ready,rs_ready,lfsr[23:16],rs_valid,rs_out,rs_fail);',
          '''wire [127:0] syndromes;wire synd_valid,chien_ready,done_valid;wire [3:0] roots;
 s3_rs_syndrome syndrome(clk,rst,1'b1,rs_ready,lfsr[23:16],synd_valid,chien_ready,syndromes);
 s3_rs_chien chien(clk,rst,synd_valid,chien_ready,{syndromes[71:8],8'd1},4'd8,
  rs_valid,1'b1,rs_out,done_valid,1'b1,rs_fail,roots);''')
        top = top.replace('vit_valid,rs_out,rs_valid,rs_fail};',
                          'vit_valid,rs_out,rs_valid,rs_fail,syndromes,synd_valid,done_valid,roots};')
        if args.correction:
            top = top.replace(' assign activity=', ''' wire correction_ready,correction_error,correction_in_ready;
 wire correction_valid,correction_last,correction_failed;wire [7:0] correction_data;
 s3_rs_correction correction(clk,rst,1'b1,correction_ready,syndromes[3:0],
  syndromes[63:0],syndromes[127:64],rs_fail,correction_error,
  1'b1,correction_in_ready,lfsr[31:24],correction_valid,1'b1,
  correction_data,correction_last,correction_failed);
 assign activity=''' ).replace('WINDOW_VALUE',str(1<<args.slot_bits)).replace('checksum,offset,',
                'correction_ready,correction_error,correction_in_ready,correction_valid,correction_data,correction_last,correction_failed,checksum,offset,')
    (out / 'top.sv').write_text(top)
    if args.syndrome_address_pipeline:
        (out / 'syndrome.sv').write_text((ROOT/'rtl/s3_rs_syndrome_pipelined.sv').read_text())
    elif args.syndrome_ready:
        (out / 'syndrome.sv').write_text(registered_syndrome())
    sources = [
        str((out / 'clock.sv').relative_to(ROOT)), 'rtl/s3_async_fifo.sv', 'rtl/s3_spi_rx.sv',
        'rtl/s3_lcd16_rx.sv', 'rtl/s3_page_guard.sv',
        'rtl/s3_page_reorder.sv', 'rtl/s3_rx_page_store.sv',
        'rtl/s3_bram2_memory_bridge.sv', 'rtl/s3_tc8psk_metric_folded.sv',
        str((out / 'viterbi.sv').relative_to(ROOT)),
        str((out / 'rs.sv').relative_to(ROOT)) if not args.rs_split else
        str((out / 'syndrome.sv').relative_to(ROOT)) if (args.syndrome_ready or args.syndrome_address_pipeline)
        else 'rtl/s3_rs_syndrome.sv',
        str((out / 'top.sv').relative_to(ROOT)),
    ]
    if args.rs_split:
        sources.append('rtl/s3_rs_chien.sv')
        if args.correction:
            sources.append('rtl/s3_rs_correction.sv')
    if args.page_status:
        sources.append('rtl/s3_spi_page_status.sv')
    script = ('read_verilog -sv ' + ' '.join(sources) + '\n'
              'synth_gowin -top s3_memory_bram2_fec_benchmark -family gw1n '
              f'-nowidelut -json {out.relative_to(ROOT)}/design.json\n'
              f'tee -o {out.relative_to(ROOT)}/stat.json stat -json\ncheck -assert\n')
    (out / 'synth.ys').write_text(script)
    source_hashes={s:sha(ROOT/s) for s in sources}
    constraint_hashes={s:sha(s) for s in (ROOT/'experiments/s3_bram2_pins.cst',out/'clocks.py')}
    benchmark_hash=sha(Path(__file__))
    synth_rc = run(['yosys', '-s', str(out / 'synth.ys')], out / 'synth.log')
    result = {'scope': 'partial independent FEC/transport area experiment; no RF-to-TS connection',
              'synth_exit_code': synth_rc, 'seed': args.seed,
              'chunked_compare': args.chunked_compare,
              'rs_split': args.rs_split,
              'acs32': args.acs32,
              'core_mhz': args.core_mhz,
              'correction': args.correction,
              'syndrome_ready': args.syndrome_ready,'syndrome_address_pipeline':args.syndrome_address_pipeline,
              'pipe_window': args.pipe_window,
              'page_status': args.page_status,'page_window':1<<args.slot_bits,'fixed_arbiter':args.fixed_arbiter,'parallel_traceback_choice':args.parallel_traceback_choice,
              'source_sha256': source_hashes,
              'constraints_sha256':{str(p.relative_to(ROOT)):v for p,v in constraint_hashes.items()},
              'benchmark_script_sha256':benchmark_hash,
              'synth_script_sha256': sha(out / 'synth.ys')}
    if synth_rc:
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        raise SystemExit(synth_rc)
    common = ['nextpnr-himbaechel', '--json', str(out / 'design.json'),
              '--device', 'GW1NR-LV9QN88PC6/I5', '--vopt', 'family=GW1N-9C',
              '--vopt', 'cst=experiments/s3_bram2_pins.cst',
              '--pre-pack', str(out / 'clocks.py')]
    pack_rc = run(common + ['--pack-only', '--write', str(out / 'packed.json')],
                  out / 'pack.log')
    result['pack_exit_code'] = pack_rc
    if pack_rc == 0:
        result['site_audit'] = audit(out / 'packed.json')
        pnr_args = common + ['--freq', str(args.core_mhz), '--seed', str(args.seed),
                    '--report', str(out / 'report.json'), '--placer', 'heap',
                    '--placer-heap-cell-placement-timeout', '0',
                    '--write', str(out / 'routed.json')]
        result['pnr_exit_code'] = run(pnr_args, out / 'pnr.log')
        result['pnr_command'] = pnr_args
        log = (out / 'pnr.log').read_text()
        result['pnr_log_sha256'] = sha(out / 'pnr.log')
        result['route_completed']=(out/'routed.json').exists() and (out/'report.json').exists()
        observed = {
            clock: float(value) for clock, value in re.findall(
                r'(?:Info:|ERROR:) Max frequency for clock\s+\'([^\']+)\': '
                r'([0-9.]+) MHz', log)}
        result['final_fmax_mhz']=observed if result['route_completed'] else None
        result['pre_route_fmax_mhz']=observed if not result['route_completed'] else None
        result['errors'] = [line for line in log.splitlines()
                            if line.startswith('ERROR:')]
    result['sources_unchanged_during_run']=(source_hashes=={s:sha(ROOT/s) for s in sources}
        and constraint_hashes=={s:sha(s) for s in constraint_hashes}
        and benchmark_hash==sha(Path(__file__)))
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(out / 'result.json')
    if pack_rc or result.get('pnr_exit_code') or not result['sources_unchanged_during_run']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
