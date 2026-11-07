"""Source-operation accounting for the fused scalar comparison kernel; not WCET."""
from fractions import Fraction as F
from pathlib import Path
import json,argparse,hashlib
ROOT=Path(__file__).resolve().parents[1]
def report():
    rows=[];checks=[]
    for name,raw,out,taps in [('T',16,F(512,63),32),('S',40,F(1443,50),16)]:
        iterations=out*taps
        rows.append(dict(standard=name,taps=taps,raw_Msample_s=raw,output_Msample_s=float(out),
            loop_iterations_M_s=float(iterations),signed10_decodes_M_s=float(2*iterations),real_MAC_M_s=float(2*iterations),
            logical_raw_word_reads_MB_s=float(4*iterations),logical_coefficient_reads_MB_s=float(2*iterations),
            separate_unpack_input_read_and_array_write_removed_MB_s=8*raw,
            two_core_240MHz_optimistic_one_scalar_MAC_per_cycle_percent=float(2*iterations/480*100),
            scalar_one_MAC_per_cycle_scenario_fits=False,actual_target_instructions_verified=False,
            scratch_I16_Q16_array_bytes=0,
            accumulator_output_is_not_transport_Q15=True,RF_bus_BW_inferred=False,adopted=False))
        checks.append(dict(name=name+'_MAC_pair_count',passed=2*iterations==out*2*taps))
        checks.append(dict(name=name+'_scalar_scenario_exceeds_480M',passed=2*iterations>480))
    files=['experiments/s3_fir_fused_reference.c','experiments/s3_fir_fused_reference.h']
    return dict(scope=__doc__,assumptions=['Scalar kernel consumes each dot-product window independently; no input-window or coefficient reuse modeled','logical reads are C source accesses, not measured physical SRAM/cache traffic','one scalar real MAC/cycle is an optimistic scenario, not target disassembly or universal CPU lower bound','accumulators returned before rounding; output conversion and whole receiver costs omitted'],rows=rows,checks=checks,source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files})
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=report();a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));raise SystemExit(any(not c['passed'] for c in r['checks']))
