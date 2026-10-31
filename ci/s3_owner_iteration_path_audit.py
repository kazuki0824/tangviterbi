"""Declared owner iteration paths from SDK ELF, excluding packing; not WCET."""
import argparse,gzip,hashlib,io,json,os
from collections import Counter
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import graph
ROOT=Path(__file__).resolve().parents[1]

def trace(nodes,start,choices,stop=None):
    used=Counter();path=[];pc=start
    while True:
        n=nodes[pc];path.append(dict(offset=pc,op=n['op'],operands=n['operands']))
        edges=n['edges']
        if not edges:
            assert stop is None and n['op']=='retw.n'
            break
        if len(edges)==2:
            options=choices[pc]
            if not isinstance(options,list):options=[options]
            assert used[pc]<len(options)
            nxt=options[used[pc]];used[pc]+=1
            assert nxt in edges
        else:
            assert len(edges)==1
            nxt=edges[0]
        if nxt==stop:break
        pc=nxt
    assert set(used)==set(choices)
    assert all(used[k]==(len(v) if isinstance(v,list) else 1) for k,v in choices.items())
    return path

def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);a=p.parse_args()
    tc=a.toolchain.resolve();env=dict(os.environ,XTENSA_GNU_CONFIG=str(tc/'lib/xtensa_esp32s3.so'))
    profile=ROOT/'reports/s3-spi-running-guard/sdk-S/image'
    raw=gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes())
    rec=json.loads((profile/'result.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==rec['ELF_sha256'] and rec['all_static_checks_pass']
    sources=('experiments/s3_raw_tasks.c','experiments/s3_parallel_pack.c','experiments/s3_cycle_clock.c')
    for s in sources:assert hashlib.sha256((ROOT/s).read_bytes()).hexdigest()==rec['build']['source_sha256'][s]
    quiet=json.loads((ROOT/'reports/s3-owner-quiet-path/results.json').read_text())
    assert quiet['ELF_sha256']==rec['ELF_sha256']
    e=ELFFile(io.BytesIO(raw));sy={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
    temp=ROOT/'build/owner-iteration.elf';temp.write_bytes(raw);graphs={}
    for name in ('s3_raw_task_entry','feed','s3_pp_collect'):
        s=sy[name];base=s['st_value']
        g=graph(temp,str(tc/'bin/xtensa-esp-elf-objdump'),env,base,s['st_size'])
        graphs[name]={pc-base:dict(n,edges=[int(x,16)-base for x in n['edges']]) for pc,n in g.items()}
    paths={}
    paths['owner_loop']=trace(graphs['s3_raw_task_entry'],0x233,{
        0x23c:0x23f,0x24d:0x250,0x258:0x25d,0x266:0x269,0x271:0x274,
        0x27c:0x27e,0x288:0x2bc,0x2c2:0x2dd,0x2e5:0x2e8,
        0x2f8:[0x2fb]*2,0x309:[0x30b]*2,0x30b:[0x311]*2,0x325:[0x328]*2,
        0x32e:[0x35d]*2,0x36f:[0x371]*2,0x371:[0x374,0x377],0x381:0x233},stop=0x233)
    paths['feed_not_due']=trace(graphs['feed'],0,{
        0x16:0x32,0x32:0x34,0x3c:0x3f,0x3f:0x42,0x45:0x48})
    paths['collect_empty']=trace(graphs['s3_pp_collect'],0,{
        5:8,0x14:0x17,0x22:[0x61]*3,0x64:[0x1d,0x1d,0x67],0x6a:0x6c})
    paths['collect_one_pending']=trace(graphs['s3_pp_collect'],0,{
        5:8,0x14:0x17,0x22:[0x24,0x61,0x61],0x64:[0x1d,0x1d,0x67],
        0x2c:0x2f,0x31:0x34,0x34:0x37,0x39:0x49,
        0x51:0x54,0x56:0x59,0x59:0x5c,0x5e:0x61,0x6a:0x71,0x9c:0x6c})
    calls=Counter(n['operands'].split('<')[-1].rstrip('>') for n in paths['owner_loop'] if n['op'].startswith('call'))
    assert calls==Counter({'s3_native_poll_budget':2,'poll_rf':5,'pack_slice':1,
        's3_cycle_clock_read':1,'s3_pp_collect':1,'s3_pp_spi_reap':2,'feed':1})
    assert [n['operands'].split('<')[-1].rstrip('>') for n in paths['feed_not_due'] if n['op'].startswith('call')]==['s3_cycle_clock_read']
    assert all(not n['op'].startswith('call') for k in ('collect_empty','collect_one_pending') for n in paths[k])
    clock=quiet['traces']['s3_cycle_clock_read']['own_instructions']
    # Two polls are inlined in the task function. Their wrapper instructions
    # are already in owner_loop; do not count seven standalone wrappers.
    rf=quiet['seven_RF_polls_instructions']-2*quiet['traces']['poll_rf']['own_instructions']
    common=dict(owner_loop=len(paths['owner_loop']),RF=rf,SPI=quiet['two_running_SPI_reaps_instructions'],
        collect_clock=clock,feed=len(paths['feed_not_due'])+clock)
    rows=[]
    for name in ('collect_empty','collect_one_pending'):
        count=sum(common.values())+len(paths[name])
        rows.append(dict(case=name,parts=dict(common,collect=len(paths[name])),instructions=count,
            cycles_at_alpha1_1=count*1.1,us_at_240MHz_alpha1_1=count*1.1/240,
            remaining_from_scan2225_54564486_cycles=2225.5456448602454-count*1.1))
    tradeoff=json.loads((ROOT/'reports/s3-owner-slice-tradeoff/results.json').read_text())
    for row in rows:
        row['if_assumed_average_extra_scan_cost']={}
        for size in (256,512):
            cases=next(r['cases'] for r in tradeoff['rows'] if r['slice_pairs']==size)
            row['if_assumed_average_extra_scan_cost'][str(size)]=max(
                c['core0_percent_by_management_cycles']['200']+
                (row['cycles_at_alpha1_1']-1500)*(c['assumed_owner_iterations_s']-25000)/2.4e6
                for c in cases)
    result=dict(scope=__doc__,ELF_sha256=rec['ELF_sha256'],paths=paths,rows=rows,
        owner_calls=dict(calls),conditions=quiet['conditions']+[
            'Owner stop=false, pack_slice returns success, SPI reaps return TIMEOUT, no submit.',
            'Clock low word is not UINT32_MAX; watchdog not due and next_feed has same high word.',
            'collect_empty: no banks owned/count=0. collect_one_pending: bank0 owned, both jobs not DONE, deadline same high word and later; FIFO front bank0.',
            'No concurrent state transitions during declared trace; examples, not all interleavings.'],
        exclusions=['Entire pack_slice body (including wrapper/clock), fill, switch/settling/accept, SPI complete/submit, watchdog reset.',
            'Other collect states and concurrent worker transitions; average path frequencies.',
            'Stalls, interrupts, window exceptions and measured elapsed time.',
            'Sensitivity substitutes each example for average additional scan cost, not a measured/derived path mixture.'],
        inline_wrapper_correction_instructions=-28,CPU_estimate_reduced=False,
        source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources+('ci/s3_owner_iteration_path_audit.py',)})
    out=ROOT/'reports/s3-owner-iteration-path';out.mkdir(exist_ok=True)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
