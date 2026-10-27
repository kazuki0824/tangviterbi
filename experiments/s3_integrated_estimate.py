"""Integrated conditional engineering estimate; no measured cycle interval."""
import gzip,json,hashlib
from pathlib import Path
from ci.s3_pack_path_audit import run
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/receiver-integrated-estimate'
def read(path):
    p=ROOT/path
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_text())
def main():
    coeff=read('reports/s3-pack-span/cfg/results.json')['coefficients'];cpu=[]
    for share,standard,rate,chunk in ((8,'T',16,32768),(5,'S',40,16384),(6,'S',40,16384)):
        paths=run(share,[11264,12288,12289,14288,14352]);assert all(c['passed'] for c in paths['checks'])
        paths.update(core0_sixteenths=share,bank_sizes=[11264,12288,12289,14288,14352])
        (OUT/f'paths-{standard}-{share}.json').write_text(json.dumps(paths,indent=2)+'\n')
        cases=[]
        for r in paths['rows']:
            if r['slice_pairs']!=512:continue
            work=[sum(coeff[c]*v[k] for c,k in [('block','blocks_s'),('run','runs_s'),('slow_pair','slow_pairs_s'),('slice','slices_s')])/1e6 for v in r['rates'][standard]]
            cases.append(dict(samples=r['bank_samples'],first=r['first'],packing_Minstructions_s=work,
                packing_only_average_bank_us=[v*1.1*r['bank_samples']/rate/240 for v in work]))
        # Initial short banks are transient examples, not a sustained bank rate.
        steady=[r for r in cases if r['samples']>=12288]
        pack=[[min(r['packing_Minstructions_s'][w] for r in steady),max(r['packing_Minstructions_s'][w] for r in steady)] for w in (0,1)]
        core=[[1.1*(v+21574*rate/12288)/2.4+(rate*2.5)*20/chunk*100+20/2.4 for v in pack[0]],[(1.1*v+10)/2.4 for v in pack[1]]]
        row=dict(standard=standard,share=share,chunk_bytes=chunk,cases=cases,core_percent_base=core)
        if standard=='S':
            row['additional_scan_cost_sensitivity']=[dict(additional_cycles_per_scan=c,core0_percent=[v+c/288 for v in core[0]]) for c in (0,500,1500,3000)]
            row['additional_scan_budget_cycles']=(100-core[0][1])*288
            fill_pct=1.1*21574*rate/12288/2.4
            row['fill_reduction_25pct_and_scan_1500_cycles_core0']=[v+1500/288-fill_pct*.25 for v in core[0]]
            row['minimum_fill_reduction_fraction_at_scan1500']=max(0,(core[0][1]+1500/288-100)/fill_pct)
        cpu.append(row)
    ledger=read('reports/partition-recheck-20261023/recomputed-k7-resource-variants.json')
    owners=read('reports/partition-recheck-20261023/all-ownerships.json.gz');raw=next(r for r in owners if r['id']=='S3-T-000');fir=next(r for r in owners if r['id']=='S3-T-001')
    saved={k:raw['stage_resources'][k]-fir['stage_resources'][k] for k in raw['stage_resources']}
    caps=dict(logic_sites_estimate=20736,FF=15552,BSRAM=46,DSP18=48);fpga=[]
    for r in ledger['cases']:
        for move in (False,True):
            area={k:r['R_H_replacement'][k]-(saved[k] if move else 0) for k in caps}
            fpga.append(dict(kernel=r['trial'],T_FIR_on_SoC=move,whole_ledger=area,remaining={k:caps[k]-area[k] for k in caps},standalone_kernel_MHz=next(iter(r['fmax'].values()))['achieved'],whole_PnR_verified=False))
    pnr=read('reports/controller-cursor-mask/pnr.json.gz')
    path=max(pnr['critical_paths'],key=lambda p:sum(x['delay'] for x in p['path']))
    routing=sorted([p['delay'] for p in path['path'] if p['type']=='routing'],reverse=True)
    actual=pnr['fmax']['dut.clk']['achieved'];minimum=2*(25.212121+50.505)*128/127;target=1080/7
    q=read('reports/s3-preprocess-break-even/qacc/qacc-audit.json')['rows'][0]
    optimistic=[v+q['optimistic_kernel_Mcycles_s']+q['separate_prepare_write_only_ideal_Mcycles_s'] for v in q['inherited_non_FIR_plus_API_Mcycles_s']]
    result=dict(scope=__doc__,cpu=cpu,FPGA=fpga,T_FIR_removed=saved,
        partial_timing=dict(MHz=actual,minimum_MHz=minimum,target_MHz=target,largest_routing_ns=routing[:2],minimum_path_reduction_ns=1000/actual-1000/minimum,target_path_reduction_ns=1000/actual-1000/target),
        T_FIR_optimistic_legacy_Mcycles_s=optimistic,T_FIR_optimistic_legacy_remaining=[480-v for v in optimistic],
        caveats=['Old whole-stage allocation plus replacement kernels, not a whole-top synthesis.',
        'CPU instruction coefficients are archived estimates; alpha=1.1, API=20us, U=20/10 Mcycles/s are assumptions.',
        'Extra scan cycles 500/1500/3000 are sensitivity points, not measured percentiles.',
        'T FIR optimistic aggregate mixes retained legacy non-FIR budget with compiled kernel instruction and preparation-write floor; gather reads, unpack, contention and quality unverified.',
        'Formal performance pass, route assignment and receiver adoption remain zero.'],receiver_adopted=False)
    result['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['experiments/s3_integrated_estimate.py','ci/s3_pack_path_audit.py','reports/partition-recheck-20261023/recomputed-k7-resource-variants.json','reports/controller-cursor-mask/pnr.json.gz','reports/s3-preprocess-break-even/qacc/qacc-audit.json']}
    (OUT/'estimate.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(cpu=[{k:v for k,v in r.items() if k!='cases'} for r in cpu],FIR_saved=saved,timing=result['partial_timing'],FIR_optimistic=optimistic),indent=2))
if __name__=='__main__':main()
