"""Instruction-count screen for direct s16 FIR, not all FIR algorithms or WCET."""
from fractions import Fraction as F
from pathlib import Path
import hashlib,json,argparse
ROOT=Path(__file__).resolve().parents[1]

def direct_mac_cycles(rate,taps):
    # Optimistically allow all eight lanes useful; exclude loads/reduction/control.
    return 2*rate*taps/8

def report():
    budget=json.loads((ROOT/'reports/s3-preprocess-break-even/fir-replacement-budget.json').read_text())
    rows=[];checks=[]
    for ident,rate,raw,taps,old in [('S3-T-001',F(512,63),16,32,[F(36)*F(512,63)+48,F(48)*F(512,63)+80]),('S3-S-001',F(1443,50),40,16,[F(26)*F(1443,50)+120,F(36)*F(1443,50)+200])]:
        b=next(x for x in budget['rows'] if x['id']==ident)
        floor=direct_mac_cycles(rate,taps)
        limit=[F(str(v)) for v in b['replacement_FIR_including_unpack_must_be_below_Mcycles_s']]
        checks.extend(dict(name=ident+'_original_formula_'+str(k),passed=abs(float(old[k])-b['old_FIR_including_unpack_Mcycles_s'][k])<1e-9) for k in range(2))
        remaining=[v-floor for v in limit]
        rows.append(dict(id=ident,taps_per_I_or_Q_output=taps,complex_output_Msample_s=float(rate),
            MAC_Moperations_s=float(2*rate*taps),ideal_MAC_only_Mcycles_s=float(floor),
            break_even_budget_Mcycles_s=list(map(float,limit)),
            remaining_for_unpack_loads_reduce_control_Mcycles_s=list(map(float,remaining)),
            remaining_cycles_per_input_complex_sample=[float(v/raw) for v in remaining],
            MAC_only_excludes_beating_raw=[v<=0 for v in remaining],
            with_old_unpack_3_or_5_cycles_per_input_Mcycles_s=[float(floor+raw*c) for c in (3,5)],
            preserve_old_unpack_excludes_beating_raw=[floor+raw*c>=limit[k] for k,c in enumerate((3,5))],
            all_same_quality_algorithms_excluded=False,receiver_adopted=False))
    # Independent integer-output count cross-check over complete rational periods.
    checks.append(dict(name='T_32_outputs_need_256_SIMD_MACs',passed=direct_mac_cycles(F(32),32)==256))
    checks.append(dict(name='S_1443_outputs_need_5772_SIMD_MACs',passed=direct_mac_cycles(F(1443),16)==5772))
    return dict(scope=__doc__,assumptions=['Direct real-coefficient dot products for both I and Q; 32 T or 16 S non-eliminated tap products/output/component','8 signed16 products per SIMD instruction; optimistic one issue/cycle','No memory, unpack, phase, accumulation-readout, output-store, RTOS or DMA cost in MAC-only count','Other receiver costs fixed as previous break-even calculation','Does not cover symmetry, zero coefficients, convolution/phase reuse, FFT convolution or fusion changing other costs','Tap count alone does not certify channel quality'],rows=rows,checks=checks)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=report()
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));raise SystemExit(any(not c['passed'] for c in r['checks']))
