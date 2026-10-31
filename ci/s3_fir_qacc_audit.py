"""Actual target compilation plus finite four-output QACC cost model."""
import argparse,gzip,hashlib,json,math,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.s3_fir_accx_model import instructions

def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    tc=args.toolchain.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so');prefix=str(tc/'bin/xtensa-esp-elf-')
    src=ROOT/'experiments/s3_fir_qacc.S';obj=out/'qacc.o'
    subprocess.run([prefix+'gcc','-c',str(src),'-o',str(obj)],env=env,check=True)
    subprocess.run([prefix+'gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'experiments/s3_fir_qacc_prepare.c'),'-o',str(out/'prepare.o')],env=env,check=True)
    dis=subprocess.check_output([prefix+'objdump','-d',str(obj)],env=env,text=True).replace(str(obj),'qacc.o');(out/'qacc.dis').write_text(dis)
    rows=[];checks=[]
    previous=json.loads((ROOT/'reports/s3-preprocess-break-even/results.json').read_text())
    source=json.loads(gzip.decompress((ROOT/'reports/s3-partition-audit/inputs.json.gz').read_bytes()))
    for standard,k,up,down,input_rate in [('T',32,32,63,16),('S',16,1443,2000,40)]:
        code=instructions(dis,'s3_fir_qacc_'+str(k));n=len(code);rate=input_rate*up/down;groups=up//math.gcd(up,4)
        ident='S3-'+standard+'-001'
        old=next(r for r in previous['rows'] if r['id']==ident)
        original=next(r for r in source['assignments'] if r['id']==ident)
        old_fir=original['stage_CPU_models']['FIR']['known_model_Mcycles_per_s']
        fixed=[v-old_fir[j]+old['API_Mcycles_s'] for j,v in enumerate(old['CPU_before_link_Mcycles_s'])]
        total=[v+n*rate/4 for v in fixed]
        checks.extend([dict(name=standard+'_instructions',passed=n==2*k+8),dict(name=standard+'_MAC',passed=sum(op.startswith('ee.vmulas') for op,_ in code)==k),dict(name=standard+'_phase_groups',passed=len({4*j*down%up for j in range(groups)})==groups)])
        rows.append(dict(standard=standard,taps=k,instructions_per_four_outputs=n,optimistic_kernel_Mcycles_s=n*rate/4,
            optimistic_kernel_two_core_percent=n*rate/4/480*100,
            ideal_MAC_only_Mcycles_s=k*rate/4,
            all_setup_and_result_save_removed_Mcycles_s=(2*k+1)*rate/4,
            tap_sample_bytes_per_batch=16*k,tap_coeff_bytes_per_batch=16*k,output_buffer_bytes=64,output_written_bytes=40,
            reference_gather_sample_read_bytes_per_steady_batch=16*k,reference_gather_coeff_read_bytes_per_batch=8*k,
            reference_gather_total_write_bytes_per_batch=32*k,
            reference_gather_writes_MB_s=32*k*rate/4,
            expanded_coeff_table_groups=groups,expanded_coeff_table_bytes=groups*16*k,
            original_phase_table_bytes=up*k*2,
            nominal_three_output_intervals_us=3/rate,
            input_arrival_span_us_min=min(((4*j+3)*down//up-4*j*down//up)/input_rate for j in range(groups)),
            input_arrival_span_us_max=max(((4*j+3)*down//up-4*j*down//up)/input_rate for j in range(groups)),
            inherited_non_FIR_plus_API_Mcycles_s=fixed,
            inherited_fixed_plus_new_kernel_Mcycles_s=total,
            exceeds_480_with_gather_free=[v>480 for v in total],
            separate_prepare_write_only_ideal_Mcycles_s=2*k*rate/4,
            gather_cost_included_in_kernel=False,performance_qualified=False))
    r=dict(scope=__doc__,compiler=subprocess.check_output([prefix+'gcc','--version'],env=env,text=True).splitlines()[0],source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),disassembly_sha256=hashlib.sha256((out/'qacc.dis').read_bytes()).hexdigest(),rows=rows,checks=checks,target_execution_verified=False,all_QACC_layouts_excluded=False)
    (out/'qacc-audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())
