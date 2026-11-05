#!/usr/bin/env python3
"""Fresh finite T integration reconstruction; virtual fees are not target WCET.

Execute recovered C control flow, enumerate independent technical conditions,
and require fresh linked SDK evidence before making a candidate decision.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'reports/s3-t-preprocess-integration-v2/runtime'
RECONSTRUCTION='fresh-2026-11-05'
CATEGORIES=['OWNER','WORKER','CLOCK','HB_PRODUCE','HB_WORK','HB_REAP','HB_BUSY',
            'HB_WORK_EMPTY','HB_REAP_EMPTY','NATIVE_BASE','NATIVE_PREPARE',
            'NATIVE_SWITCH','NATIVE_ACCEPT','FILL','NATIVE_HELPER','ADAPTER','COPY',
            'SPI_SUBMIT','SPI_REAP_EMPTY','SPI_REAP_DONE','SPI_IRQ','TICK','FEED','WDT','PHY']
# Semantic-development inputs only. The final audit cannot pass with these
# unbound historical estimates, even when --allow-provisional is requested.
PROVISIONAL={
    'OWNER_PHASE':[108,126,195,108,115,108,134,108,80],'WORKER':83,'CLOCK':26,
    'HB_PRODUCE':9721,'HB_WORK':14179,'HB_REAP':60,'HB_BUSY':40,
    'HB_WORK_EMPTY':22,'HB_REAP_EMPTY':33,
    'SPI_SUBMIT':1028,'SPI_REAP_EMPTY':288,'SPI_REAP_DONE':383,
    'IRQ_FIRST':3073,'IRQ_START':2807,'IRQ_COMPLETE':1357,'IRQ_CHAIN':3121,
    'TICK0':1099,'TICK1':804,'FEED':57,'WDT_EXTRA':381,
    'NATIVE_BASE':176,'NATIVE_PREPARE_DELTA':97,'NATIVE_SWITCH_DELTA':36,'NATIVE_ACCEPT_DELTA':589,
    'CLOCKED_OWNED':[159,189,219,249],'COPY_CONTROL_ALLOWANCE':8,
    'NATIVE_HEALTHY':12,'NATIVE_AVAILABLE':20,'NATIVE_RECLAIM':22,'NATIVE_ACCEPT':124,
    'ADAPTER_READ_CLOCK':34,'ADAPTER_PUBLISH':36,'ADAPTER_ADVANCE':42,
    'ADAPTER_STEP_IDLE':41,'ADAPTER_STEP_ACTIVE':76,'ADAPTER_STEP_PER_COPY_CHUNK':58,
}
FILL_FIELDS=('fixed_instructions','fixed_known_cycles','span_instructions',
             'span_known_cycles','bulk8_instructions','tail_instructions')
HOST_C_SOURCES=[
    'experiments/t_preprocess_capacity/native_adapter.c',
    'experiments/t_preprocess_capacity/native_adapter.h',
    'experiments/t_preprocess_capacity/halfband_pipeline.c',
    'experiments/t_preprocess_capacity/halfband_pipeline.h',
    'experiments/t_preprocess_capacity/halfband31.c',
    'experiments/t_preprocess_capacity/halfband31.h',
    'experiments/t_preprocess_integration_probe/tpre_runtime.c',
    'experiments/t_preprocess_integration_probe/tpre_runtime.h',
    'experiments/s3_native_capture.c','experiments/s3_native_capture.h',
]
# Mirrors ci/t_preprocess_sdk_audit.py::SOURCE_INPUTS. Require the whole
# canonical target recipe, not just whichever hashes a document supplies.
TARGET_SOURCES=[
    'experiments/s3_capture_bridge.c','experiments/s3_capture_bridge.h',
    'experiments/s3_cycle_clock.c','experiments/s3_cycle_clock.h',
    'experiments/s3_native_capture.c','experiments/s3_native_capture.h',
    'experiments/s3_transport.h',
    *['experiments/t_preprocess_capacity/'+name for name in
      ('halfband31.S','halfband31.c','halfband31.h','halfband_pipeline.c',
       'halfband_pipeline.h','native_adapter.c','native_adapter.h')],
    *['experiments/t_preprocess_integration_probe/'+name for name in
      ('.gitignore','CMakeLists.txt','build_probe.py','main/CMakeLists.txt',
       'main/hot.lf','main/integration_probe.c','main/sram_guard.ld','sdkconfig.defaults',
       'tpre_pie.S','tpre_runtime.c','tpre_runtime.h','tpre_sdk.c','tpre_sdk.h')],
]
COST_DEPENDENCIES=[
    'ci/t_preprocess_runtime_costs.py','ci/t_preprocess_sdk_audit.py',
    'ci/s3_sdk_cost_audit.py','ci/s3_sdk_cost_paths.py','ci/t_halfband_capacity_audit.py',
    'ci/s3_irq_entry_audit.py','ci/s3_tick_cost_audit.py',
    'reports/s3-sdk-cost-ledger/results.json',
    'reports/s3-spi-running-guard/sdk-S/image/s3_raw_probe.elf.gz',
]
MODEL_SOURCES=HOST_C_SOURCES+[
    'experiments/t_preprocess_capacity/halfband31_host.c',
    'experiments/t_preprocess_runtime.c','ci/t_preprocess_runtime_audit.py',
    'tests/test_t_preprocess_runtime.py',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer(value,minimum=1):
    return isinstance(value,int) and not isinstance(value,bool) and value>=minimum


def path_value(value,default):
    value=default if value is None else value
    if not isinstance(value,(str,Path)):
        raise ValueError('artifact path must be a string')
    return ROOT/Path(value)


def source_key(path):
    """Same artifact-key rule as the SDK cost builder, including CI paths."""
    path=Path(path).resolve()
    try:return path.relative_to(ROOT.resolve()).as_posix()
    except ValueError:return str(path)


def fee_schema_errors(fees):
    if not isinstance(fees,dict):return ['fees must be an object']
    errors=[]
    for name in PROVISIONAL:
        value=fees.get(name);valid=integer(value,0 if name=='COPY_CONTROL_ALLOWANCE' else 1)
        if name in ('OWNER_PHASE','CLOCKED_OWNED'):
            valid=isinstance(value,list) and len(value)==(9 if name=='OWNER_PHASE' else 4) and all(integer(n) for n in value)
        if not valid:errors.append('invalid or missing fee: '+name)
    return errors


def verify_costs(document):
    """No first mismatch suppresses later independent evidence checks."""
    errors=[]
    if not isinstance(document,dict):
        errors.append('cost document must be an object');document={}
    if document.get('source_read_error'):errors.append(document['source_read_error'])
    if document.get('schema_version')!=2:errors.append('schema_version must be 2')
    if document.get('status')!='READY':errors.append('linked cost evidence status is not READY')
    fees=document.get('fees',{})
    errors.extend(fee_schema_errors(fees))
    hashes=document.get('source_sha256',{})
    if not isinstance(hashes,dict):errors.append('source_sha256 must be an object');hashes={}
    for name in TARGET_SOURCES:
        if name not in hashes:errors.append('unbound target source: '+name)
    for name in COST_DEPENDENCIES:
        if name not in hashes:errors.append('unbound cost derivation input: '+name)
    sdk=ROOT/'reports/s3-t-preprocess-integration-v2/sdk'
    for field,default in [('linked_elf_path',sdk/'t_preprocess_integration_probe.elf.gz'),
                          ('sdk_audit_path',sdk/'audit.json'),('provenance_path',sdk/'provenance.json')]:
        try:
            name=source_key(path_value(document.get(field),default))
            if name not in hashes:errors.append('unbound selected artifact: '+name)
        except (OSError,ValueError) as exc:errors.append('invalid selected artifact path: '+field+': '+repr(exc))
    for name,expected in hashes.items():
        try:
            if sha(ROOT/name)!=expected:errors.append('stale source: '+name)
        except (OSError,TypeError) as exc:errors.append(f'missing source: {name}: {exc}')
    copy=document.get('copy_words',{})
    copy=copy if isinstance(copy,dict) else {}
    table=copy.get('fees_by_words')
    if not isinstance(table,list) or len(table)!=1025:
        errors.append('missing or invalid linked copy_words.fees_by_words table')
    else:
        invalid=[n for n,fee in enumerate(table) if not integer(fee,0 if n==0 else 1)]
        if invalid:errors.append('invalid copy fee indices: '+repr(invalid))
    fill=document.get('fill_words',{})
    fill=fill if isinstance(fill,dict) else {}
    for name in FILL_FIELDS:
        if not integer(fill.get(name),0):errors.append('invalid fill_words.'+name)
    derivations=document.get('checks',[])
    if not isinstance(derivations,list) or not derivations:
        errors.append('missing linked cost derivation checks')
    else:
        for n,row in enumerate(derivations):
            if not isinstance(row,dict) or row.get('status')!='PASS':
                errors.append('linked cost derivation not PASS: '+str(row.get('name',n) if isinstance(row,dict) else n))
    linked=document.get('linked_elf_sha256',document.get('elf_sha256'))
    try:
        path=path_value(document.get('linked_elf_path'),sdk/'t_preprocess_integration_probe.elf.gz')
        raw=path.read_bytes()
        actual=hashlib.sha256(gzip.decompress(raw) if path.suffix=='.gz' else raw).hexdigest()
        if actual!=linked:errors.append('costs do not bind the actual linked ELF bytes')
    except (OSError,ValueError,EOFError) as exc:errors.append('linked ELF unavailable: '+repr(exc))
    try:
        path=path_value(document.get('sdk_audit_path'),sdk/'audit.json')
        audit=json.loads(path.read_text())
        if not isinstance(audit,dict):raise ValueError('SDK audit must be an object')
        if audit.get('status')!='PASS' or audit.get('all_static_checks_pass') is not True or audit.get('elf_sha256')!=linked:
            errors.append('SDK static audit is not passing for this ELF')
    except (OSError,ValueError) as exc:errors.append('SDK audit unavailable: '+repr(exc))
    try:
        path=path_value(document.get('provenance_path'),sdk/'provenance.json')
        provenance=json.loads(path.read_text())
        if not isinstance(provenance,dict):raise ValueError('provenance must be an object')
        if provenance.get('provided_elf_sha256')!=linked:errors.append('build provenance does not bind this ELF')
    except (OSError,ValueError) as exc:errors.append('build provenance unavailable: '+repr(exc))
    return errors


def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('instrumentation anchor must occur once: '+repr(old))
    return text.replace(old,new)


def generated(fees):
    fill=fees.get('FILL_WORDS',dict(fixed_instructions=5,fixed_known_cycles=8,span_instructions=41,
                                 span_known_cycles=94,bulk8_instructions=17,tail_instructions=3))
    header=['#ifndef TPRE_MODEL_COSTS_H','#define TPRE_MODEL_COSTS_H',
            '#include "tpre_runtime.h"','#include <stdint.h>']
    for name,value in fees.items():
        if isinstance(value,int):header.append(f'#define COST_{name} {value}ULL')
    header += [
        'static const unsigned model_owner_fees[9]={'+','.join(map(str,fees['OWNER_PHASE']))+'};',
        'static const unsigned model_clocked_fees[4]={'+','.join(map(str,fees['CLOCKED_OWNED']))+'};',
        'enum {'+','.join('M_'+name for name in CATEGORIES)+',MODEL_CATEGORIES};',
        'void model_charge(unsigned,uint64_t);void model_poll(void);',
        'void model_fill(unsigned,unsigned,unsigned);void model_accept(hbnative*,unsigned);',
        'void model_release(hbnative*,unsigned);void model_copy(const uint32_t*,unsigned);',
        'void model_producer_input(hbpipe*,const uint32_t*,int16_t*);',
        'void model_worker_before(hbpipe_slot*);void model_done(hbpipe_slot*);',
        'void model_admission(hbnative*,unsigned,uint64_t);void model_step_interval(uint64_t);',
        ('static inline uint64_t model_fill_fee(unsigned at,unsigned n){uint64_t ins=FIXED_I,known=FIXED_K;at&=16383;while(n){unsigned span=16384-at;if(span>n)span=n;ins+=SPAN_I+BULK*(span/8)+TAIL*(span%8);known+=SPAN_K+BULK*(span/8)+TAIL*(span%8);n-=span;at=0;}uint64_t scaled=(11*ins+9)/10;return scaled>known?scaled:known;}'
         .replace('FIXED_I',str(fill['fixed_instructions'])).replace('FIXED_K',str(fill['fixed_known_cycles']))
         .replace('SPAN_I',str(fill['span_instructions'])).replace('SPAN_K',str(fill['span_known_cycles']))
         .replace('BULK',str(fill['bulk8_instructions'])).replace('TAIL',str(fill['tail_instructions']))),
    ]
    if 'COPY_WORDS_FEES' in fees:
        header += ['static const unsigned model_copy_fees[1025]={'+','.join(map(str,fees['COPY_WORDS_FEES']))+'};',
                   'static inline uint64_t model_copy_fee(unsigned n){return model_copy_fees[n];}']
    else:
        header += ['static inline uint64_t model_copy_fee(unsigned n){uint64_t ins=9+19*(n/8)+5*(n%8);return (11*ins+9)/10+COST_COPY_CONTROL_ALLOWANCE;}']
    header.append('#endif')
    native=(ROOT/'experiments/s3_native_capture.c').read_text()
    for old,new in [
        (' volatile uint32_t *p=s->io.bank(s->io.ctx,b);',' model_fill(b,at,n);\n volatile uint32_t *p=s->io.bank(s->io.ctx,b);'),
        (' if(!s||!prepare_words||!s->running||s->fault)return false;',' if(!s||!prepare_words||!s->running||s->fault)return false;\n model_poll();model_charge(M_NATIVE_BASE,COST_NATIVE_BASE);'),
        ('  unsigned f=first(s,b,','  model_charge(M_NATIVE_ACCEPT,COST_NATIVE_ACCEPT_DELTA);\n  unsigned f=first(s,b,'),
        ('  s->switch_earliest=now-s->clock_error;','  model_charge(M_NATIVE_SWITCH,COST_NATIVE_SWITCH_DELTA);\n  s->switch_earliest=now-s->clock_error;'),
        (' if(!s->prepared){',' if(!s->prepared){\n  model_charge(M_NATIVE_PREPARE,COST_NATIVE_PREPARE_DELTA);'),
    ]:native=replace(native,old,new)
    adapter=(ROOT/'experiments/t_preprocess_capacity/native_adapter.c').read_text()
    for old,new in [
        ('static bool HOT hbnative_healthy(void *ctx) {','static bool HOT hbnative_healthy(void *ctx) {\n    model_charge(M_NATIVE_HELPER,COST_NATIVE_HEALTHY);'),
        ('static bool HOT hbnative_available(void *ctx, unsigned bank) {','static bool HOT hbnative_available(void *ctx, unsigned bank) {\n    model_charge(M_NATIVE_HELPER,COST_NATIVE_AVAILABLE);'),
        ('static bool HOT hbnative_reclaim(void *ctx, unsigned bank) {','static bool HOT hbnative_reclaim(void *ctx, unsigned bank) {\n    model_charge(M_NATIVE_HELPER,COST_NATIVE_RECLAIM);'),
        ('    uint64_t now, uint64_t deadline) {','    uint64_t now, uint64_t deadline) {\n    model_charge(M_NATIVE_HELPER,COST_NATIVE_ACCEPT);'),
        ('    a->last_time = now;\n    return true;','    a->last_time = now;\n    model_accept(a,bank);\n    return true;'),
        ('    const uint32_t *restrict src, unsigned count) {','    const uint32_t *restrict src, unsigned count) {\n    model_copy(src,count);'),
        ('static void HOT AUDIT hbnative_advance(hbnative *a, unsigned taken) {','static void HOT AUDIT hbnative_advance(hbnative *a, unsigned taken) {\n    model_charge(M_ADAPTER,COST_ADAPTER_ADVANCE);'),
        ('        b->owned = false;','        model_release(a,a->fifo[a->head]);\n        b->owned = false;'),
        ('    int16_t *output, hbnative_result *result) {','    int16_t *output, hbnative_result *result) {\n    model_charge(M_ADAPTER,COST_ADAPTER_PUBLISH);'),
        ('    unsigned budget, hbnative_result *result) {','    unsigned budget, hbnative_result *result) {\n    model_charge(M_ADAPTER,(a->count||a->fill)?COST_ADAPTER_STEP_ACTIVE:COST_ADAPTER_STEP_IDLE);'),
        ('        hbnative_copy_words(a->carry + a->fill, b->words + at, n);','        model_charge(M_ADAPTER,COST_ADAPTER_STEP_PER_COPY_CHUNK);\n        hbnative_copy_words(a->carry + a->fill, b->words + at, n);'),
        ('    uint64_t t = clock(ctx);','    model_charge(M_ADAPTER,COST_ADAPTER_READ_CLOCK);\n    uint64_t t = clock(ctx);'),
        ('    uint64_t earliest = UINT64_MAX;','    model_charge(M_ADAPTER,model_clocked_fees[a->count]);\n    uint64_t earliest = UINT64_MAX;'),
        ('        if (now >= b->deadline || bound >= b->deadline - now) {','        if (now >= b->deadline || bound >= b->deadline - now) {\n            model_admission(a,n,now);'),
        ('    if (finished - now > bound - error) {','    model_step_interval(finished-now);\n    if (finished - now > bound - error) {'),
    ]:adapter=replace(adapter,old,new)
    pipeline=(ROOT/'experiments/t_preprocess_capacity/halfband_pipeline.c').read_text()
    for old,new in [
        ('        return HBPIPE_BUSY;','        {model_charge(M_HB_BUSY,COST_HB_BUSY);return HBPIPE_BUSY;}'),
        ('    hb31_workspace *w = &s->workspace;','    model_charge(M_HB_PRODUCE,COST_HB_PRODUCE);\n    model_producer_input(p,raw,output);\n    hb31_workspace *w = &s->workspace;'),
        ('    if (s->sequence != p->consume_next) return HBPIPE_ORDER;','    model_worker_before(s);\n    if (s->sequence != p->consume_next) return HBPIPE_ORDER;\n    model_charge(M_HB_WORK,COST_HB_WORK);'),
        ('    atomic_store_explicit(&s->status, HBPIPE_DONE, memory_order_release);','    model_done(s);\n    atomic_store_explicit(&s->status, HBPIPE_DONE, memory_order_release);'),
        ('        return HBPIPE_EMPTY;\n    model_worker_before(s);','        {model_charge(M_HB_WORK_EMPTY,COST_HB_WORK_EMPTY);return HBPIPE_EMPTY;}\n    model_worker_before(s);'),
        ('        return HBPIPE_EMPTY;\n    if (s->sequence != p->reap_next)','        {model_charge(M_HB_REAP_EMPTY,COST_HB_REAP_EMPTY);return HBPIPE_EMPTY;}\n    if (s->sequence != p->reap_next)'),
        ('    *output = s->output;','    model_charge(M_HB_REAP,COST_HB_REAP);\n    *output = s->output;'),
    ]:pipeline=replace(pipeline,old,new)
    return {
        'tpre_model_costs.h':'\n'.join(header)+'\n',
        'native.c':'#include "tpre_model_costs.h"\n'+native,
        'adapter.c':'#include "tpre_model_costs.h"\n'+adapter,
        'pipeline.c':'#include "tpre_model_costs.h"\n'+pipeline,
        'runtime.c':(ROOT/'experiments/t_preprocess_integration_probe/tpre_runtime.c').read_text(),
    }


def build(directory,fees,prepare=2048):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    sources=generated(fees)
    for name,content in sources.items():(directory/name).write_text(content)
    binary=directory/'runtime'
    command=['cc','-std=c11','-O2','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
             '-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections',
             f'-DTPRE_PREPARE_WORDS_PER_ITERATION={prepare}',
             '-I'+str(directory),'-I'+str(ROOT/'experiments'),
             '-I'+str(ROOT/'experiments/t_preprocess_capacity'),
             '-I'+str(ROOT/'experiments/t_preprocess_integration_probe'),
             str(ROOT/'experiments/t_preprocess_runtime.c'),
             *[str(directory/name) for name in ('native.c','adapter.c','pipeline.c','runtime.c')],
             str(ROOT/'experiments/t_preprocess_capacity/halfband31.c'),
             str(ROOT/'experiments/t_preprocess_capacity/halfband31_host.c'),'-o',str(binary)]
    result=subprocess.run(command,capture_output=True,text=True,cwd=ROOT)
    if result.returncode:raise RuntimeError(result.stderr)
    compiler=subprocess.run(['cc','--version'],capture_output=True,text=True).stdout.splitlines()
    return binary,{'command':command,'returncode':result.returncode,'stderr':result.stderr,
                   'host_compiler':compiler[0] if compiler else 'unavailable',
                   'generated_sha256':{name:hashlib.sha256(text.encode()).hexdigest() for name,text in sources.items()}}


def model_step_envelope(fees,clock_error=0):
    """Bound only for this finite event model, including one SPI and one tick.

    Enumerate all partitions of <=1024 words into <=6 nonempty physical copy
    chunks. Three retained banks can each cross one ring boundary. The owner
    does not submit SPI inside a producer step. One service of each IRQ is a
    valid model premise only if the derived interval is shorter than wire/tick
    periods. Unpriced IRQ/NMI, cache/bus stalls and silicon effects are excluded.
    """
    copy=fees.get('COPY_WORDS_FEES')
    if copy is None:
        copy=[0]+[((11*(9+19*(n//8)+5*(n%8))+9)//10)+fees['COPY_CONTROL_ALLOWANCE'] for n in range(1,1025)]
    chunks=[n+fees['ADAPTER_STEP_PER_COPY_CHUNK']+fees['ADAPTER_ADVANCE'] for n in copy]
    previous=[0]+[-10**12]*1024;maxima=[]
    for parts in range(1,7):
        current=[-10**12]*1025
        for n in range(parts,1025):current[n]=max(previous[n-k]+chunks[k] for k in range(1,n-parts+2))
        maxima.append(max(current));previous=current
    shared=max(fees['CLOCKED_OWNED'])+fees['ADAPTER_STEP_ACTIVE']+fees['ADAPTER_READ_CLOCK']+fees['CLOCK']
    direct=shared+fees['ADAPTER_PUBLISH']+fees['HB_PRODUCE']+fees['ADAPTER_ADVANCE']
    copied=shared+max(maxima)+fees['ADAPTER_PUBLISH']+max(fees['HB_PRODUCE'],fees['HB_BUSY'])
    spi=max(fees[n] for n in ('IRQ_FIRST','IRQ_START','IRQ_COMPLETE','IRQ_CHAIN'))
    total=max(direct,copied)+spi+fees['TICK0']+clock_error
    if total>=98364 or total>=2400000:raise ValueError('one-SPI/one-tick interval premise does not hold')
    return {'bound':total,'clock_error':clock_error,'max_copy_and_advance_by_chunk_count':maxima,
            'base_step_max':max(direct,copied),'direct_step_max':direct,'copied_step_max':copied,
            'spi_one_service_max':spi,'tick_one_service_max':fees['TICK0'],
            'copy_partition_words':1024,'max_copy_chunks':6,'wire_cycles':98364,'tick_period_cycles':2400000,
            'is_target_WCET':False,'includes_other_ISR_NMI_or_bus_stalls':False}


def execute(binary,case):
    args=[case.get(k,v) for k,v in [('banks',100),('stall',0),('phy',0),('bound',20000),
                                   ('inject',0),('destroy',1),('clock_error',0),('phy_first',240000)]]
    result=subprocess.run([str(binary),*map(str,args)],capture_output=True,text=True,timeout=60)
    if result.returncode:raise RuntimeError(f'host model exit {result.returncode}: {result.stderr}')
    row=json.loads(result.stdout);row['id']=case['id']
    row['candidate_pass']=row['banks']==row['requested_banks'] and not any(row[k] for k in ('native_fault','adapter_fault','task_fault','outcome'))
    row['observation_policy']='Stop after the requested accepted-bank count or the first fatal condition; accepted input, pending outputs and DMA are not fully drained.'
    row['unconsumed_accepted_words']=row['accepted_words']-row['consumed_words']
    row['unproduced_accepted_words']=row['accepted_words']-row['produced_words']
    row['complete_processing_and_dma_drain']=(row['accepted_words']==row['produced_words'] and
        row['blocks_reaped']==row['blocks_produced'] and row['frame_states']==[8,0,0,0] and
        row['retained_source_banks']==0 and row['carry_words']==0 and row['queue_count']==0)
    row['cost_ledger']=[{name:{'events':pair[0],'cycles':pair[1]} for name,pair in zip(CATEGORIES,core)} for core in row['cost_ledger']]
    row['ledger_identities']=[sum(v['cycles'] for v in core.values())==row['charged_cycles'][c] for c,core in enumerate(row['cost_ledger'])]
    row['elapsed_identities']=[row['charged_cycles'][c]+row['stall_cycles'][c]+row['post_stop_idle_cycles'][c]==row['accounted_until_cycles'][c] for c in (0,1)]
    row['pending_charged_cycles']=[max(0,row['accounted_until_cycles'][c]-row['observed_until_cycles']) for c in (0,1)]
    row['source_conservation']=row['accepted_words']>=row['consumed_words'] and row['consumed_words']==row['produced_words']+row['carry_words']
    row['output_conservation']=row['blocks_reaped']<=row['blocks_worked']<=row['blocks_produced']
    row['all_worked_blocks_oracle_checked']=row['blocks_worked']==row['blocks_oracle_checked']
    row['dma_lease_conservation']=row['frames_submitted']-row['frames_reaped']==row['dma_count']==row['frame_states'][3]
    row['source_destruction_checked']=not case.get('destroy',1) or row['released_banks']==row['destroyed_banks']
    row['steady_window']={
        'first_cycle':row['first_accept']['cycles'],'last_cycle':row['last_accept']['cycles'],
        'produced_blocks':row['last_accept']['blocks']-row['first_accept']['blocks'],
        'charged_cycles':[row['last_accept']['charged_cycles'][c]-row['first_accept']['charged_cycles'][c] for c in (0,1)],
        'cycles_per_raw_block_at_16M':15360,
    }
    w=row['steady_window'];w['charged_cycles_per_block']=[v/w['produced_blocks'] if w['produced_blocks'] else None for v in w['charged_cycles']]
    row['admission_failure']['next_path']={0:'none',1:'pipeline busy',2:'direct contiguous block',
        3:'carry/copy path',4:'empty',5:'no output frame available'}[row['admission_failure']['next_path_code']]
    row['admission_failure']['counterfactual_scope']='Base charged fees only, without injected task stalls or interrupts. Whole-step fee differs from the earlier source-copy release time; neither is a silicon bound.'
    row['stop_cause']=classify_stop(row)
    return row


CASES=[
    {'id':'nominal_finite_8','banks':8},
    {'id':'nominal_candidate_100','banks':100},
    {'id':'nominal_without_source_destruction','banks':100,'destroy':0},
    {'id':'stall_10_percent','banks':100,'stall':10},
    {'id':'clock_error_floor_240','banks':100,'clock_error':240},
    {'id':'clock_error_assumed_1024','banks':100,'clock_error':1024},
    {'id':'phy_cpu1_1000_cycles_phase_190000','banks':100,'phy':1000,'phy_first':190000},
    {'id':'phy_cpu1_10000_cycles_phase_190000','banks':100,'phy':10000,'phy_first':190000},
    {'id':'phy_cpu1_50000_cycles_phase_190000','banks':100,'phy':50000,'phy_first':190000},
    {'id':'phy_cpu1_50000_cycles_phase_2400000','banks':100,'phy':50000,'phy_first':2400000},
    {'id':'diagnostic_bound_10000','banks':100,'bound':10000},
    {'id':'submit_failure_retains_lease','banks':100,'inject':1},
    {'id':'wrong_completion_sequence','banks':100,'inject':2},
    {'id':'owner_feed_failure','banks':100,'inject':3},
    {'id':'worker_feed_failure','banks':100,'inject':4},
    {'id':'clock_failure','banks':100,'inject':6},
    {'id':'dma_corruption_detected','banks':100,'inject':7},
    {'id':'raw_corruption_detected','banks':100,'inject':8},
    {'id':'worker_sequence_failure','banks':100,'inject':9},
]


def classify_stop(row):
    """A functional error is not valid evidence of a capacity rejection."""
    native,adapter,task=(row[k] for k in ('native_fault','adapter_fault','task_fault'))
    answer={'kind':'unrecognized_functional_stop','capacity_stop':False,'acceptance_window_end':False,
            'faults':{'native':native,'adapter':adapter,'task':task,'invariant':row['outcome']}}
    if row['outcome']:
        answer['kind']='host_semantic_invariant_failure';return answer
    if (native,adapter,task)==(0,0,0):
        if row['banks']==row['requested_banks']:
            answer.update(kind='requested_acceptance_window_observed',acceptance_window_end=True)
        else:answer['kind']='unexplained_early_stop'
        return answer
    if (native,adapter,task)==(0,4,5):
        a=row['admission_failure']
        triggered=(a['sampled_cycles']>0 and (a['sampled_cycles']>=a['deadline'] or
                    row['declared_step_bound']>=a['deadline']-a['sampled_cycles']))
        answer.update(kind='whole_step_deadline_admission_guard',capacity_stop=triggered,
                      predicate={'observed':triggered,'remaining':a['remaining'],'declared_bound':row['declared_step_bound']})
    elif (native,adapter,task)==(0,6,5):
        triggered=row['max_sampled_core0_step']>row['declared_step_bound']-row['clock_error']
        answer.update(kind='post_publication_step_bound_exceeded',capacity_stop=triggered,
                      predicate={'observed':triggered,'max_step':row['max_sampled_core0_step'],
                                 'bound_minus_error':row['declared_step_bound']-row['clock_error']})
    elif adapter==0 and task==1 and native in (4,5,7):
        state=row['native_stop_state']
        if native==4:
            triggered=state['age_cycles']>(16384-128)*15
            kind='native_age_limit_exceeded'
        elif native==5:
            triggered=state['written']>=12288 and (not state['prepared'] or state['written']>12288+2000)
            kind='native_preparation_incomplete_or_switch_late'
        else:
            triggered=(not state['prepared'] and not state['preparing'] and state['next_bank_owned'] and
                       state['written']+20000//15+1024+2000>=12288)
            kind='next_source_bank_unavailable_before_switch'
        answer.update(kind=kind,capacity_stop=triggered,predicate={'observed':triggered,**state})
    return answer


def row_errors(row,case):
    errors=[]
    for key in ('ledger_identities','elapsed_identities'):
        if not all(row[key]):errors.append(key)
    for key in ('source_conservation','output_conservation','all_worked_blocks_oracle_checked',
                'dma_lease_conservation','source_destruction_checked','rf_stopped'):
        if not row[key]:errors.append(key)
    if row['stopped']!=[1,1]:errors.append('both task loops did not acknowledge stop')
    injection=case.get('inject',0)
    expected={1:('task_fault',10),2:('task_fault',7),3:('task_fault',11),4:('task_fault',14),
              7:('outcome',91),8:('outcome',99),9:('task_fault',13)}
    if injection:
        if not row['injection_executed']:errors.append('fault injection never reached')
        if injection in expected:
            key,value=expected[injection]
            if row[key]!=value:errors.append(f'expected {key}={value}, got {row[key]}')
        elif injection==6 and not (row['native_fault']==8 or row['adapter_fault']==7):errors.append('clock error not rejected')
        if injection==1 and row['frame_states'][3]!=1:errors.append('submit error released ambiguous DMA lease')
    else:
        cause=classify_stop(row)
        if not cause['capacity_stop'] and not cause['acceptance_window_end']:
            errors.append('non-injected stop is not a recognized, observed capacity condition: '+cause['kind'])
    if case['id']=='derived_bound_sensitivity' and row['adapter_fault']==6:
        errors.append('derived finite-model bound violated by an observed step')
    return errors


def run_audit(cost_document,allow_provisional=False):
    if not isinstance(cost_document,dict):
        cost_document={'schema_version':2,'status':'BLOCKED','fees':{},'source_sha256':{},
                       'source_read_error':'cost document must be a JSON object'}
    checks=[];rows=[];cost_errors=verify_costs(cost_document)
    usable=not cost_errors or allow_provisional
    checks.append({'id':'linked_cost_evidence','status':'PASS' if not cost_errors else 'BLOCKED','errors':cost_errors})
    original_fees=cost_document.get('fees',{})
    fees=dict(original_fees) if isinstance(original_fees,dict) else {}
    copy=cost_document.get('copy_words',{})
    if isinstance(copy,dict) and isinstance(copy.get('fees_by_words'),list) and len(copy['fees_by_words'])==1025:
        fees['COPY_WORDS_FEES']=copy['fees_by_words']
    fill=cost_document.get('fill_words',{})
    if isinstance(fill,dict) and all(k in fill for k in FILL_FIELDS):fees['FILL_WORDS']=fill
    fee_errors=fee_schema_errors(original_fees);complete=not fee_errors
    checks.append({'id':'fee_schema_complete','status':'PASS' if complete else 'FAIL','errors':fee_errors})
    envelope=None
    with tempfile.TemporaryDirectory(prefix='t-runtime-rebuilt-') as tmp:
        binary=None
        if usable and complete:
            try:
                binary,detail=build(Path(tmp)/'candidate',fees)
                checks.append({'id':'same_C_host_build_UBSan','status':'PASS','result':detail})
            except Exception as exc:checks.append({'id':'same_C_host_build_UBSan','status':'FAIL','reason':repr(exc)})
        else:checks.append({'id':'same_C_host_build_UBSan','status':'BLOCKED','reason':'linked costs unavailable or invalid'})
        if binary:
            try:
                result=subprocess.run([str(binary),'--selftest'],capture_output=True,text=True,timeout=60)
                detail=json.loads(result.stdout)
                checks.append({'id':'owner_init_and_fatal_contracts','status':'PASS' if result.returncode==0 else 'FAIL','result':detail})
            except Exception as exc:checks.append({'id':'owner_init_and_fatal_contracts','status':'FAIL','reason':repr(exc)})
        else:checks.append({'id':'owner_init_and_fatal_contracts','status':'BLOCKED'})
        if usable and complete:
            try:
                envelope=model_step_envelope(fees)
                checks.append({'id':'derived_model_step_envelope','status':'PASS','result':envelope})
            except Exception as exc:checks.append({'id':'derived_model_step_envelope','status':'FAIL','reason':repr(exc)})
        else:checks.append({'id':'derived_model_step_envelope','status':'BLOCKED'})
        cases=CASES+[{'id':'derived_bound_sensitivity','banks':100,'bound':envelope['bound'] if envelope else 20000}]
        for case in cases:
            if not binary:
                checks.append({'id':case['id'],'status':'BLOCKED','reason':'host executable unavailable'});continue
            if case['id']=='derived_bound_sensitivity' and envelope is None:
                checks.append({'id':case['id'],'status':'BLOCKED','reason':'derived bound unavailable'});continue
            try:
                row=execute(binary,case);rows.append(row);errors=row_errors(row,case)
                checks.append({'id':case['id'],'status':'FAIL' if errors else 'PASS','errors':errors,
                               'candidate_status':'INJECTED_FAULT' if case.get('inject') else 'FINITE_PASS' if row['candidate_pass'] else 'MODEL_NG'})
            except Exception as exc:checks.append({'id':case['id'],'status':'FAIL','reason':repr(exc)})
        if usable and complete:
            try:
                diagnostic,_=build(Path(tmp)/'prepare1024',fees,1024)
                case={'id':'diagnostic_prepare_1024','banks':100}
                row=execute(diagnostic,case);rows.append(row);errors=row_errors(row,case)
                checks.append({'id':case['id'],'status':'FAIL' if errors else 'PASS','errors':errors,
                               'candidate_status':'FINITE_PASS' if row['candidate_pass'] else 'MODEL_NG'})
            except Exception as exc:checks.append({'id':'diagnostic_prepare_1024','status':'FAIL','reason':repr(exc)})
        else:checks.append({'id':'diagnostic_prepare_1024','status':'BLOCKED'})
    destroyed=next((r for r in rows if r['id']=='nominal_candidate_100'),None)
    preserved=next((r for r in rows if r['id']=='nominal_without_source_destruction'),None)
    if destroyed is not None and preserved is not None:
        fields=[k for k in destroyed if k not in ('id','destroyed_banks')]
        differences=[k for k in fields if destroyed[k]!=preserved[k]]
        checks.append({'id':'source_destruction_preserves_complete_trace','status':'FAIL' if differences else 'PASS',
                       'fields_compared':len(fields),'differences':differences})
    else:checks.append({'id':'source_destruction_preserves_complete_trace','status':'BLOCKED','reason':'both lifetime variants are required'})
    hashes={};hash_errors=[]
    for name in MODEL_SOURCES:
        try:hashes[name]=sha(ROOT/name)
        except OSError as exc:hash_errors.append(f'{name}: {exc}')
    checks.append({'id':'all_model_source_hashes','status':'FAIL' if hash_errors else 'PASS','errors':hash_errors})
    counts={s:sum(c['status']==s for c in checks) for s in ('PASS','FAIL','BLOCKED')}
    nominal=next((r for r in rows if r['id']=='nominal_candidate_100'),None)
    floor=next((r for r in rows if r['id']=='clock_error_floor_240'),None)
    decision='BLOCKED' if cost_errors or counts['FAIL'] or counts['BLOCKED'] else 'FINITE_PASS' if nominal and nominal['candidate_pass'] and floor and floor['candidate_pass'] else 'MODEL_NG'
    return {
        'schema_version':2,'reconstruction':RECONSTRUCTION,'previous_lost_artifact_recovered_byte_exact':False,
        'non_fail_fast':True,'audit_status':'PASS' if not counts['FAIL'] and not counts['BLOCKED'] else 'FAIL' if counts['FAIL'] else 'BLOCKED',
        'candidate_status':decision,'candidate_decision_scenarios':['nominal_candidate_100','clock_error_floor_240'],
        'finite_pass_definition':'Requested accepted-bank observation window without faults; does not mean all accepted samples were processed or DMA drained.',
        'check_summary':counts,'checks':checks,'rows':rows,'source_sha256':hashes,
        'cost_document_canonical_sha256':hashlib.sha256(json.dumps(cost_document,sort_keys=True).encode()).hexdigest(),
        'derived_model_step_envelope':envelope,'target_timing_measured':False,'silicon_WCET_proven':False,
        'model_independent_overload_proven':False,'receiver_adopted':False,
        'scope_limits':[
            'New reconstruction and fresh execution; old hashes and old bank counts are not acceptance criteria.',
            'Virtual cycles from linked instruction/control envelopes. Host wall time is never target timing.',
            'Ideal undocumented RF ABI and non-sentinel input. Ideal-clock diagnostic has error0; minimum calibration floor240 and assumed1024 are separate scenarios. Actual launch error is measured only on hardware.',
            'Recovered nine-phase owner, actual native sentinel preparation, per-poll cap1024 and per-iteration budget2048; SDK queue callbacks are event models with linked fees.',
            'Source release and READY/DONE occur after charged work. This is operation-boundary interleaving, not instruction-level target simulation.',
            'SPI3 quad80MHz,16KiB+80bit wire,two descriptors. Core0 level1 SPI/tick services serialize; simultaneous new arrivals select tick first. An already finishing SPI service may publish at its completion boundary when a tick arrives.',
            'Cache-enabled reception assumed. No transitive cache-off ISR safety proof. Owner23,worker21,timer22 are caller-selected model priorities.',
            'Tick100Hz no-switch paths. PHY sensitivity uses CPU1 timer task,1000ms period,explicit first phase and supplied task dispatch/context/callback duration; ticks preempt it. CPU0 timer ISR/IPI and other ISR/NMI are unpriced. No PHY WCET is established.',
            'Declared core0 admission bound20000 is not an execution lower bound. Counterfactual BASE fees exclude both task stalls and interrupts; source-copy release may precede whole-step completion.',
            'Derived bound enumerates up-to-six copy chunks and one SPI/tick service only within this discrete model. It excludes unpriced interrupts,bus contention and silicon effects.',
            'RF-off start/stop,task deletion and complete DMA drain are unpriced. Worker finishes any operation already begun before acknowledgment; remaining leases are retained.',
            'Task0 stops at the requested accepted-bank count, before all accepted input necessarily reaches preprocessing or DMA. A finite pass covers that observation window only.',
            'Fee ledgers include polling and pending operations. Per-block charge averages do not establish intrinsic utilization or a model-independent overload lower bound.',
            'Finite pass is not sustained hardware feasibility. Model failure rejects this candidate/policy and supplied costs, not all T implementations on S3.',
        ],
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--costs',type=Path,default=DEST/'costs.json')
    parser.add_argument('--output',type=Path,default=DEST/'results.json')
    parser.add_argument('--allow-provisional',action='store_true')
    args=parser.parse_args()
    try:
        if args.costs.exists():document=json.loads(args.costs.read_text())
        else:document={'schema_version':2,'status':'PROVISIONAL','fees':PROVISIONAL,'source_sha256':{}}
    except (OSError,ValueError) as exc:
        document={'schema_version':2,'status':'BLOCKED','fees':{},'source_sha256':{},'source_read_error':repr(exc)}
    result=run_audit(document,args.allow_provisional)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    for check in result['checks']:print(check['status'],check['id'],check.get('errors',check.get('reason','')))
    for row in result['rows']:print(row['id'],{k:row[k] for k in ('banks','adapter_fault','native_fault','task_fault','outcome','max_sampled_core0_step')})
    print(result['candidate_status'],result['check_summary'])
    return 0 if result['audit_status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
