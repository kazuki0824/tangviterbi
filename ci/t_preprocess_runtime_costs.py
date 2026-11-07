#!/usr/bin/env python3
"""Fees recounted from the current linked T image, under explicit assumptions.

This is a reproducible instruction/control model, never hardware WCET. A
missing prerequisite blocks only its dependent groups. Fixed required events
are always enumerated; no historical fee is silently substituted.
"""
import argparse,collections,gzip,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ci.t_preprocess_sdk_audit import Checks,Resources,BlockedCondition,SOURCE_INPUTS,open_binary,sha,unpack,OUT,address,symdata
from ci.s3_sdk_cost_audit import Binary
from ci.s3_sdk_cost_paths import declarations,rom_declarations
from ci.t_halfband_capacity_audit import instructions,check_kernel,check_kernel_hazards

REQUIRED=['OWNER_PHASE','WORKER','CLOCK','HB_PRODUCE','HB_WORK','HB_REAP','HB_BUSY','HB_WORK_EMPTY','HB_REAP_EMPTY',
 'SPI_SUBMIT','SPI_REAP_EMPTY','SPI_REAP_DONE','IRQ_FIRST','IRQ_START','IRQ_COMPLETE','IRQ_CHAIN','TICK0','TICK1',
 'FEED','WDT_EXTRA','NATIVE_BASE','NATIVE_PREPARE_DELTA','NATIVE_SWITCH_DELTA','NATIVE_ACCEPT_DELTA','CLOCKED_OWNED',
 'COPY_CONTROL_ALLOWANCE','NATIVE_HEALTHY','NATIVE_AVAILABLE','NATIVE_RECLAIM','NATIVE_ACCEPT','ADAPTER_READ_CLOCK',
 'ADAPTER_PUBLISH','ADAPTER_ADVANCE','ADAPTER_STEP_IDLE','ADAPTER_STEP_ACTIVE','ADAPTER_STEP_PER_COPY_CHUNK']
class ResourceProxy:
    def __init__(self,res,key):self.res=res;self.key=key
    def __getattr__(self,key):return getattr(self.res.need(self.key),key)
    def __getitem__(self,key):return self.res.need(self.key)[key]
class Derived(dict):
    def __getitem__(self,key):
        if key not in self:raise BlockedCondition('unavailable derivation: '+str(key))
        return super().__getitem__(key)
def pair(instructions=0,known_cycles=None):return dict(instructions=instructions,known_cycles=instructions if known_cycles is None else known_cycles)
def charge(row):return max((11*row['instructions']+9)//10,row['known_cycles'])
def add(*rows):return pair(sum(r['instructions'] for r in rows),sum(r['known_cycles'] for r in rows))
def target(node):
    if not node['op'].startswith('call'):return None
    if node['op'].startswith('callx'):return 'INDIRECT:'+node['args'].strip()
    m=re.search(r'<([^>]+)>',node['args']);return m[1] if m else None
def resolve_target(g,pc):
    n=g[pc];t=target(n)
    if not t or not t.startswith('INDIRECT:'):return t
    reg=n['args'].strip();at=pc
    while True:
        preds=[k for k,v in g.items() if k+v['size']==at]
        if len(preds)!=1:return t
        at=preds[0];v=g[at]
        if v['op'].startswith('call'):return t
        if v['args'].split(',')[0].strip()==reg:
            m=re.search(r'\(([0-9a-f]+) <([^>]+)>\)',v['args'])
            return m[2] if v['op']=='l32r' and m else t
def scalar_load_use(left,right):
    if not left['op'].startswith(('l32i','l32r','l16','l8')):return 0
    reg=left['args'].split(',')[0].strip();op=right['op'];args=[x.strip() for x in right['args'].split(',')]
    if op.startswith(('s32','s16','s8','b','callx','moveqz','movnez')):uses=args
    elif op.startswith(('ret','call')) or op in ('j','jx'):uses=[]
    else:uses=args[1:]
    return int(reg in uses)
def path_pair(trace,callees=None):
    code=trace['path'];callees=callees or {};known=len(code);ins=len(code)
    for i,n in enumerate(code):
        pc=n['offset'];op=n['op'];child=callees.get(pc,pair());ins+=child['instructions'];known+=child['known_cycles']
        if op.startswith(('call','ret','rf')) or op in ('j','jx'):known+=2
        elif op.startswith('b') and i+1<len(code) and code[i+1]['offset']!=pc+n['size']:known+=2
        if i+1<len(code):known+=scalar_load_use(n,code[i+1])
    return pair(ins,known)
def normalized_function(binary,name,peer):
    """Permit only linker relaxation/relocation, never changed SDK logic."""
    g=binary.graph(name);order=sorted(g);rows=[];owner={};starts={}
    def literal(args):
        m=re.search(r'\(([0-9a-f]+) <([^>]+)>\)',args)
        if not m:return re.sub(r'\b[0-9a-f]+ <([^>]+)>',r'<\1>',args)
        raw,symbol=m.groups()
        base_symbol=symbol.split('+')[0]
        if base_symbol in binary.symbols and base_symbol in peer.symbols and (symbol==base_symbol or
            int(binary.symbols[base_symbol]['st_size'])>int(raw,16)-int(binary.symbols[base_symbol]['st_value'])>=0 and
            int(peer.symbols[base_symbol]['st_size'])>int(raw,16)-int(binary.symbols[base_symbol]['st_value'])):value='symbol:'+symbol
        else:
            addr=int(raw,16);value=raw
            for section in binary.elf.iter_sections():
                base=int(section['sh_addr'])
                if int(section['sh_flags'])&2 and base<=addr<base+int(section['sh_size']) and section['sh_type']!='SHT_NOBITS':
                    tail=section.data()[addr-base:addr-base+300]
                    if b'\0' in tail:
                        data=tail.split(b'\0')[0]
                        if data and all(9<=c<=126 for c in data):value='string:'+sha(data)
                    break
        return args.split(',')[0].strip()+','+value
    i=0
    def noop(n):
        args=[x.strip() for x in n['args'].split(',')]
        return n['op'] in ('nop','nop.n') or n['op'] in ('mov','mov.n') and len(args)==2 and args[0]==args[1] or n['op']=='or' and len(args)==3 and args[0]==args[1]==args[2]
    while i<len(order):
        pc=order[i];n=g[pc];op=n['op'];args=n['args'];physical=[pc]
        if noop(n):i+=1;continue
        if op=='l32r' and i+1<len(order):
            q=order[i+1];v=g[q]
            if q==pc+n['size'] and v['op'].startswith('callx') and v['args'].strip()==args.split(',')[0].strip():
                dest=resolve_target(g,q)
                if dest and not dest.startswith('INDIRECT:'):
                    op='call8';args='<'+dest+'>';physical.append(q);i+=1
        if op.startswith('call'):
            args='<'+(resolve_target(g,physical[-1]) or '')+'>';op='call8' if not args.startswith('<INDIRECT:') else op
        elif op=='l32r':args=literal(args)
        elif op.startswith('b') or op in ('j','loop','loopnez','loopgtz'):
            args=re.sub(r'\b[0-9a-f]+ <[^>]+>','TARGET',args)
        else:args=re.sub(r'\b[0-9a-f]+ <([^>]+)>',r'<\1>',args)
        op=op.removesuffix('.n');parts=[p.strip() for p in args.split(',')]
        if op=='or' and len(parts)==3 and parts[1]==parts[2]:op='mov';args=','.join(parts[:2])
        args=re.sub(r'\s+','',args)
        index=len(rows);rows.append((op,args));starts[index]=pc
        for p in physical:owner[p]=index
        i+=1
    def index_at(pc):
        while pc not in owner:
            if pc not in g:raise ValueError((name,'unknown edge',pc))
            if not noop(g[pc]):raise ValueError((name,'unmapped edge',pc))
            pc+=g[pc]['size']
        return owner[pc]
    edges={}
    for pc,n in g.items():
        if pc not in owner:continue
        index=owner[pc]
        if n['edges'] and len(n['edges'])==1 and index_at(n['edges'][0])==index:continue
        edges[index]=(tuple(index_at(x) for x in n['edges']),index_at(n['loop_end']) if n['loop_end'] is not None else None)
    return rows,owner,starts,edges
def relocation_map(old,new,name):
    a,ao,ast,ae=normalized_function(old,name,new);b,bo,bst,be=normalized_function(new,name,old)
    if a!=b:
        mismatch=[(i,x,y) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
        raise ValueError((name,'logical instructions differ',len(a),len(b),mismatch[:4]))
    if ae!=be:raise ValueError((name,'logical edges differ'))
    # Branch/loop declarations refer to the last physical instruction of a
    # logical node; destination entries include any required literal load.
    last={i:max(p for p,k in bo.items() if k==i) for i in bst}
    mapping={p:last[i] for p,i in ao.items()}
    entries={p:bst[i] for p,i in ao.items()}
    og=old.graph(name)
    for p,n in og.items():
        if p not in entries:
            q=p+n['size']
            while q in og and q not in ao:q+=og[q]['size']
            if q in ao:entries[p]=bst[ao[q]]
    return mapping,entries
def envelope(binary,name,callees=None,forced=None,blocked=(),backs=None,loops=None,entry=0,terminal_edge=None):
    """Two independent finite CFG maxima: instructions and stated controls.

    Bounds are explicit. The result can include infeasible branch combinations
    and is a conservative model envelope, not an observed path or WCET.
    """
    g=binary.graph(name);callees=callees or {};forced=forced or {};blocked=set(blocked);backs=dict(backs or {});loops=loops or {}
    for at,count in loops.items():
        n=g[at]
        if n['loop_end'] is None or count<1:raise ValueError((name,'bad hardware loop',at,count))
        forced=dict(forced);forced[at]=n['edges'][0]
        for pc,v in g.items():
            if at<pc<n['loop_end'] and n['loop_end'] in v['edges']:backs[(pc,n['edges'][0])]=count-1
    keys=sorted(backs);limits=tuple(backs[k] for k in keys);ki={k:i for i,k in enumerate(keys)}
    banned=('__assert_func','esp_log','esp_rom_printf','heap_caps_','cfree')
    def edges(pc,state):
        n=g[pc]
        if pc in blocked or n['op'] in ('ill','break') or any((resolve_target(g,pc) or '').startswith(t) for t in banned):return []
        if pc in forced:
            rule=forced[pc]
            wanted=rule if isinstance(rule,int) else rule['edges'][state[ki[tuple(rule['counter'])]]]
            es=[wanted]
            if wanted not in n['edges']:raise ValueError((name,'forced edge does not exist',pc,wanted))
        else:es=list(n['edges'])
        for at,count in loops.items():
            end=g[at]['loop_end'];key=(pc,g[at]['edges'][0])
            if at<pc<end and end in es and key in ki:
                idx=ki[key]
                if state[idx]<limits[idx]:es=[g[at]['edges'][0] if x==end else x for x in es]
        result=[]
        for nxt in es:
            if terminal_edge==(pc,nxt):result.append((None,nxt,state));continue
            k=(pc,nxt);ss=state
            if k in ki:
                idx=ki[k]
                if state[idx]>=limits[idx]:continue
                ss=state[:idx]+(state[idx]+1,)+state[idx+1:]
            result.append(((nxt,ss),nxt,ss))
        return result
    initial=(entry,tuple(0 for _ in keys));memo={};active=set();stack=[(initial,False)]
    while stack:
        state,done=stack.pop()
        if state in memo:continue
        pc,counters=state;n=g[pc]
        if pc in blocked or n['op'] in ('ill','break') or any((resolve_target(g,pc) or '').startswith(t) for t in banned):memo[state]=None;continue
        if n['op'].startswith('call') and pc not in callees:raise ValueError((name,'unpriced callee',hex(pc),resolve_target(g,pc)))
        if n['loop_end'] is not None and pc not in loops:raise ValueError((name,'unpriced hardware loop',hex(pc)))
        es=edges(pc,counters)
        if not n['edges']:
            if not n['op'].startswith('ret'):raise ValueError((name,'nonreturn terminal',pc))
            child=callees.get(pc,pair());memo[state]=((1+child['instructions'],None),(3+child['known_cycles'],None));continue
        if not done:
            if state in active:raise ValueError((name,'cyclic undeclared state',pc))
            active.add(state);stack.append((state,True))
            for nxt,_,_ in es:
                if nxt is not None and nxt not in memo:stack.append((nxt,False))
            continue
        active.remove(state);choices=[]
        for nxt,npc,_ in es:
            tail=((0,None),(0,None)) if nxt is None else memo.get(nxt)
            if tail is None:continue
            child=callees.get(pc,pair());control=2 if n['op'].startswith('call') or n['op'] in ('j','jx') else 2 if n['op'].startswith('b') and npc!=pc+n['size'] else 0
            hazard=scalar_load_use(n,g[npc]) if npc in g else 0
            choices.append(((1+child['instructions']+tail[0][0],nxt),
                            (1+child['known_cycles']+control+hazard+tail[1][0],nxt)))
        memo[state]=tuple(max((c[m] for c in choices),key=lambda x:x[0]) for m in (0,1)) if choices else None
    result=memo[initial]
    if result is None:raise ValueError((name,'no surviving path'))
    witnesses={}
    for metric_index,metric in enumerate(('instructions','known_cycles')):
        state=initial;visits=collections.Counter()
        while state is not None:
            visits[state[0]]+=1;state=memo[state][metric_index][1]
        witnesses[metric]={hex(k):v for k,v in sorted(visits.items())}
    return dict(function=name,**pair(result[0][0],result[1][0]),entry=entry,terminal_edge=terminal_edge,
        forced={hex(k):v for k,v in forced.items()},blocked=[hex(x) for x in sorted(blocked)],
        backedges={f'{a:x}->{z:x}':n for (a,z),n in backs.items()},hardware_loops={hex(k):v for k,v in loops.items()},
        callees={hex(k):pair(v['instructions'],v['known_cycles']) for k,v in callees.items()},witness_visits=witnesses)

def build(tc,elf,sdk_audit,rom,provenance=OUT/'provenance.json'):
    ck=Checks();res=Resources(ck);paths=Derived();fees={};meta={};traces={};closed={};maps={};irq_paths={}
    def object_json(path):
        value=json.loads(Path(path).read_text())
        if not isinstance(value,dict):raise ValueError('JSON object required: '+str(path))
        return value
    res.load('ELF',lambda:open_binary(tc,elf));res.load('ROM',lambda:open_binary(tc,rom,'tpre-v2-rom'))
    res.load('SDK audit',lambda:object_json(sdk_audit));res.load('provenance',lambda:object_json(provenance))
    res.load('SDK declarations ledger',lambda:object_json(ROOT/'reports/s3-sdk-cost-ledger/results.json'))
    res.load('comparison SDK ELF',lambda:Binary(tc))
    b=ResourceProxy(res,'ELF');rb=ResourceProxy(res,'ROM');a=ResourceProxy(res,'SDK audit');prov=ResourceProxy(res,'provenance')
    old=ResourceProxy(res,'comparison SDK ELF');saved=ResourceProxy(res,'SDK declarations ledger')
    ck.check('static SDK audit all conditions passed',lambda:a['all_static_checks_pass'])
    ck.check('static SDK audit refers to this ELF',lambda:a['elf_sha256']==b.sha)
    ck.check('static SDK audit uses current auditor',lambda:a['source_auditor_sha256']==sha((ROOT/'ci/t_preprocess_sdk_audit.py').read_bytes()))
    ck.check('static SDK audit uses exact build source manifest',lambda:a['source_sha256']==prov['source_sha256'])
    ck.check('fresh build provenance refers to this ELF',lambda:prov['provided_elf_sha256']==b.sha)
    def wire_geometry():
        sdk=(ROOT/'experiments/t_preprocess_integration_probe/tpre_sdk.c').read_text()
        header=(ROOT/'experiments/t_preprocess_integration_probe/tpre_runtime.h').read_text()
        expected={name:int(value) for name,value in re.findall(r'\.(command_bits|address_bits|clock_speed_hz)\s*=\s*(\d+)',sdk)}
        assert expected=={'command_bits':16,'address_bits':64,'clock_speed_hz':80000000},expected
        assigned=re.search(r'\*t\s*=\s*\(spi_transaction_t\)\s*\{\s*\.flags\s*=([^,]+),',sdk)
        assert assigned and assigned[1].strip()=='SPI_TRANS_MODE_QIO','transaction lane flags differ'
        assert re.search(r'TPRE_FRAME_BYTES\s*=\s*16384\b',header),'frame size differs'
        assert 'khz!=80000' in sdk and '.length=bytes*8' in sdk,'actual clock or bit length check differs'
        assert '.flags=SPI_DEVICE_HALFDUPLEX|SPI_DEVICE_NO_DUMMY' in sdk,'device mode differs'
        geometry=dict(command_bits=16,address_bits=64,command_lines=1,address_lines=1,data_lines=4,
                      clock_hz=80000000,core_hz=240000000,frame_bytes=16384,wire_cycles=98544)
        assert (geometry['frame_bytes']*8//geometry['data_lines']+geometry['command_bits']+geometry['address_bits'])*3==geometry['wire_cycles']
        meta['spi_wire']=geometry
        return dict(geometry=geometry,transaction_flags=assigned[1].strip(),
          source_basis='Pinned ESP-IDF spi_master.c spi_format_hal_trans_struct: data_lines derives from QIO; cmd_lines/addr_lines default1 without SPI_TRANS_MULTILINE_CMD/ADDR. The build source manifest and current static audit bind the target source.')
    ck.check('actual frozen SPI wire command address data geometry',wire_geometry)
    manifest=res.data.get('provenance',{}).get('source_sha256',{});manifest=manifest if isinstance(manifest,dict) else {}
    for name in sorted(set(SOURCE_INPUTS)|set(manifest)):
        ck.check('source dependency '+name,lambda name=name:sha((ROOT/name).read_bytes())==prov['source_sha256'][name])
    def E(key,name,**kw):
        row=envelope(b,name,**kw);paths[key]=row;return row
    def calls0(name):return {pc:pair() for pc,n in b.graph(name).items() if n['op'].startswith('call')}
    def blockcalls(name,*prefixes):return [pc for pc in b.graph(name) if any((resolve_target(b.graph(name),pc) or '').startswith(p) for p in prefixes)]
    def fee(key,row):fees[key]=charge(row);return row
    def mapping(name):
        if name not in maps:maps[name]=relocation_map(old,b,name)
        return maps[name]
    def rebound(name,forced=None,blocked=(),backs=None,callees=None,entry=0,terminal_edge=None):
        m,e=mapping(name);f={}
        for pc,rule in (forced or {}).items():
            f[m[pc]]=e[rule] if isinstance(rule,int) else {'counter':[m[rule['counter'][0]],e[rule['counter'][1]]],'edges':[e[x] for x in rule['edges']]}
        return envelope(b,name,forced=f,blocked=[e[x] for x in blocked],backs={(m[x],e[y]):n for (x,y),n in (backs or {}).items()},
                        callees={m[x]:v for x,v in (callees or {}).items()},entry=e[entry],terminal_edge=(m[terminal_edge[0]],e[terminal_edge[1]]) if terminal_edge else None)
    ck.check('official ROM ELF matches pinned previous ledger',lambda:rb.sha==saved['rom_elf_sha256'])
    decl=declarations();bindings={}
    name,ch,loops=decl['spi_irq_complete'];ch=dict(ch);ch[0x195]=0x1ad;ch[0x1b0]=0x276
    decl['spi_irq_chain']=(name,ch,loops)
    bindings['spi_irq_chain']={'spi_bus_lock_bg_entry':'bus_entry_complete','spi_bus_lock_bg_check_dev_req':'bus_check_req_start',
                             'spi_bus_lock_bg_exit':'bus_exit_start','xQueueReceiveFromISR':'queue_receive_isr'}
    envelopes={'validate':'check_trans_valid','device':'spi_hal_setup_device','hal_trans':'spi_hal_setup_trans','format':'spi_format_hal_trans_struct$isra$0'}
    def get(key):
        if key in traces:return traces[key]
        if key.startswith('rom_'):trace=rb.trace(*rom_declarations()[key]);binary=rb
        else:
            name=envelopes[key] if key in envelopes else decl[key][0];m,e=mapping(name)
            if key in envelopes:trace=b.acyclic_envelope(name)
            else:
                _,choices,loops=decl[key]
                trace=b.trace(name,{m[p]:([e[x] for x in v] if isinstance(v,list) else e[v]) for p,v in choices.items()},
                              {m[p]:count for p,count in loops.items()})
            binary=b
        if key in saved['paths']:
            prior=saved['paths'][key]
            if [c['target'] for c in trace['calls']]!=[c['target'] for c in prior['calls']]:raise ValueError((key,'linked callee sequence differs'))
            if key.startswith('rom_') and trace['own_instructions']!=prior['own_instructions']:raise ValueError((key,'ROM count differs'))
        traces[key]=(trace,binary);return trace,binary
    def thunk(public,destination):
        at=address(b,public);dest=address(rb,destination)
        dis=subprocess.check_output([rb.tool,'-d',f'--start-address={at}',f'--stop-address={at+6}',str(rb.path)],env=rb.env,text=True)
        if not re.search(r'l32r\s+a9,.*\('+format(dest,'x')+r' <',dis) or not re.search(r'jx\s+a9',dis):raise ValueError((public,'ROM thunk differs'))
        return pair(2,4)
    def close(key,desc=5,first=False,stack=()):
        cachekey=(key,desc,first)
        if cachekey in closed:return closed[cachekey]
        if key in stack:raise ValueError(('recursive SDK closure',stack,key))
        trace,binary=get(key);cs={};children=[]
        for c in trace['calls']:
            symbol=c['target'];child=bindings.get(key,saved['call_bindings'].get(key,{})).get(symbol,saved['default_bindings'].get(symbol))
            if symbol=='spicommon_dma_desc_setup_link':child='dma_descriptors_'+str(desc)
            if symbol=='spi_new_trans':child='spi_new_'+str(first)
            if not child:raise ValueError((key,'unbound SDK child',symbol))
            row=close(child,desc,first,stack+(key,))
            if child.startswith('rom_'):row=add(row,thunk(symbol,rom_declarations()[child][0]))
            cs[c['offset']]=row;children.append(dict(offset=c['offset'],target=symbol,path=child,**row))
        row=path_pair(trace,cs);row.update(function=trace['function'],own_instructions=trace['own_instructions'],calls=children,
                                          offsets=[p['offset'] for p in trace['path']])
        closed[cachekey]=row;return row
    for key in ('sdk_queue','sdk_result_False','sdk_result_True','spi_irq_start','spi_irq_complete','spi_irq_chain','wdt_feed_0','wdt_feed_1'):
        ck.check('SDK call closure '+key,lambda key=key:paths.__setitem__('sdk_'+key,close(key)) or paths['sdk_'+key])
    def request_envelope():
        r=rebound('spi_bus_lock_bg_request',callees={0x21:close('atomic_or'),0x38:close('atomic_or'),0x42:close('bus_intr_enable')})
        prior=close('bus_request');queue=paths['sdk_sdk_queue'];paths['sdk_request']=r
        paths['sdk_queue_adjusted']=pair(queue['instructions']+max(0,r['instructions']-prior['instructions']),
                                         queue['known_cycles']+max(0,r['known_cycles']-prior['known_cycles']))
        return r
    ck.check('SDK request while active counted',request_envelope)
    def irq_entry():
        from ci.s3_irq_entry_audit import trace
        specs={n:(None,None,None) for n in ('xthal_save_extra_nw','xthal_restore_extra_nw','_xt_context_restore','_xt_user_exit')}
        specs.update({'_xt_context_save':({0x52:0x55},None,None),'_frxt_int_enter':({0x1e:0x20,0x26:0x29,0x31:0x33},None,None),
          '_frxt_int_exit':({0x17:0x19,0x1f:0x21,0x29:0x2b,0x35:0x49},None,None),
          '_xt_lowint1':({0x41:[0x44,0x94],0x62:0x65},0x97,None),'_xt_user_exc':({3:6},None,'_xt_lowint1'),
          '_UserExceptionVector':(None,3,None)})
        def signature(row):
            args=row['args']
            if row['op']=='l32r':
                m=re.search(r'\(([0-9a-f]+) <([^>]+)>\)',args)
                if not m:raise ValueError(('IRQ literal unreadable',row))
                base_symbol=m[2].split('+')[0]
                args=args.split(',')[0]+','+(m[2] if base_symbol in b.symbols and base_symbol in old.symbols else m[1])
            else:args=re.sub(r'\b[0-9a-f]+ <([^>]+)>',r'<\1>',args)
            return row['offset'],row['op'],args
        for name,(ch,stop,dest) in specs.items():
            actual=trace(b,name,ch,stop,dest);previous=trace(old,name,ch,stop,dest)
            if [signature(x) for x in actual['path']]!=[signature(x) for x in previous['path']]:raise ValueError((name,'IRQ assembly changed beyond relocation'))
            for n in actual['path']:n['size']=2 if n['op'].endswith('.n') else 3
            irq_paths[name]=actual
        def inclusive(name):
            t=irq_paths[name];callees={c['offset']:pair() if c['target']=='handler' else inclusive(c['target']) for c in t['calls']}
            return path_pair(t,callees)
        row=add(inclusive('_UserExceptionVector'),inclusive('_xt_lowint1'),inclusive('_xt_user_exit'))
        paths['irq_entry_exit']=row;return row
    ck.check('normal nonnested IRQ entry and exit freshly counted',irq_entry)
    for fee_name,key,first in [('IRQ_FIRST','spi_irq_start',True),('IRQ_START','spi_irq_start',False),
                              ('IRQ_COMPLETE','spi_irq_complete',False),('IRQ_CHAIN','spi_irq_chain',False)]:
        ck.check('fee '+fee_name,lambda fee_name=fee_name,key=key,first=first:fee(fee_name,add(close(key,first=first),paths['irq_entry_exit'])))

    # More independent target groups are added below; no prerequisite above is
    # allowed to abort their enumeration.
    def clock_fee():
        row=rebound('s3_cycle_clock_read',forced={8:0xa,0xd:0xf},blocked=[0x28]);paths['clock']=row;return fee('CLOCK',row)
    ck.check('fee CLOCK',clock_fee)
    def native_control():
        paths['clock_now_own']=rebound('clock_now',forced={9:0xc},blocked=[0x41],callees={0xe:pair()})
        for name in ('mmio_read','mmio_write','mmio_bank'):E(name,name)
        cn=paths['clock_now_own'];bank=paths['mmio_bank']
        calls={0x24:cn,0x4e:pair(),0xf9:bank,0x161:bank,0x18d:bank,0x206:cn,0x223:bank,
          0x281:pair(),0x2d8:paths['mmio_read'],0x33e:paths['mmio_write'],0x343:cn,0x379:pair(),0x385:pair(),0x412:pair(),0x476:cn}
        valid={0xd:0x10,0x13:0x16,0x19:0x1c,0x1f:0x22,0x30:0x33,0x59:0x67}
        blocked=[0x61,0x97,0x183,0x28d,0x290,0x306,0x395,0x46d]
        modes={'quiet':{0x88:0x2c1,0x2ef:0x366,0x36a:0x474},'prepare':{0x88:0x2c1,0x2ef:0x366,0x36a:0x36d},
               'switch':{0x88:0x2c1,0x2ef:0x2f2},'accept':{0x88:0x8b}}
        for key,forced in modes.items():
            paths['native_'+key]=rebound('s3_native_poll_budget',forced=valid|forced,blocked=blocked,
                backs={(0x141,0x124):11,(0x1c5,0x1a8):11,(0x439,0x3f0):1},callees=calls)
        paths['native_wait']=rebound('s3_native_poll_budget',forced=valid|{0x88:0x8b},blocked=blocked+[0xd1],
                backs={(0x141,0x124):11,(0x1c5,0x1a8):11,(0x439,0x3f0):1},callees=calls)
        if charge(paths['native_wait'])>charge(paths['native_quiet']):raise ValueError('quiet fee does not cover settling wait')
        return {k:pair(paths['native_'+k]['instructions'],paths['native_'+k]['known_cycles']) for k in modes}
    ck.check('native control paths and bounded sentinel searches',native_control)
    ck.check('fee NATIVE_BASE',lambda:fee('NATIVE_BASE',paths['native_quiet']))
    for key,event in [('prepare','NATIVE_PREPARE_DELTA'),('switch','NATIVE_SWITCH_DELTA'),('accept','NATIVE_ACCEPT_DELTA')]:
        def native_delta(key=key,event=event):
            fees[event]=max(0,charge(paths['native_'+key])-charge(paths['native_quiet']));return dict(delta=fees[event])
        ck.check('fee '+event,native_delta)
    for event,name in [('NATIVE_HEALTHY','hbnative_healthy'),('NATIVE_AVAILABLE','hbnative_available'),
                       ('NATIVE_RECLAIM','hbnative_reclaim'),('NATIVE_ACCEPT','hbnative_accept')]:
        ck.check('fee '+event,lambda event=event,name=name:fee(event,E(name,name,callees=calls0(name))))
    def fill_formula():
        name='fill$isra$0';m,_=mapping(name);g=b.graph(name);og=old.graph(name)
        bulk={m[p] for p in og if 0x40<=p<0x6b};tail={m[p] for p in og if 0x91<=p<0x98};body=bulk|tail;nonbody=set(g)-body
        if any(g[p]['op'].startswith(('b','call')) for p in body):raise ValueError('fill body changed to explicit control')
        # Every nonbody instruction is charged once per ring span. Taking all
        # nonbody branches is an explicit over-envelope; body LOOPs add no
        # per-iteration branch. mmio_bank is charged once per fill invocation.
        known=len(nonbody)+sum(2 for p in nonbody if g[p]['op'].startswith(('call','ret','b')) or g[p]['op']=='j')
        known+=sum(scalar_load_use(g[p],g[q]) for p in nonbody for q in g[p]['edges'] if q in g)
        row=dict(fixed_instructions=paths['mmio_bank']['instructions'],fixed_known_cycles=paths['mmio_bank']['known_cycles'],
                 span_instructions=len(nonbody),span_known_cycles=known,bulk8_instructions=len(bulk),tail_instructions=len(tail),
                 maximum_words=1024,maximum_ring_spans=2,ring_words=16384,
                 convention='max(ceil(1.1*(fixed+sum(span+bulk8*(n//8)+tail*(n%8)))), fixed_known+sum(span_known+same bodies)); all nonbody paths counted once per span')
        meta['fill_words']=row;return row
    ck.check('linked native fill dynamic formula',fill_formula)
    def kernel():
        name='hb31_qacc4';dis=subprocess.check_output([b.tool,'-d','--disassemble='+name,str(b.path)],env=b.env,text=True)
        code=instructions(dis,name);meta['kernel_arithmetic']=check_kernel(code);meta['kernel_hazards']=check_kernel_hazards(code)
        return E('kernel',name)
    ck.check('linked PIE kernel arithmetic and operand schedule',kernel)
    def pipe_helpers():
        g=b.graph('hb31_copy_words');hw=[p for p,n in g.items() if n['loop_end'] is not None]
        if len(hw)!=1:raise ValueError('history copy hardware loop differs')
        for n in (8,15):E('history_copy_'+str(n),'hb31_copy_words',loops={hw[0]:n})
        g=b.graph('hbpipe_unpack');hw=[p for p,n in g.items() if n['loop_end'] is not None]
        if len(hw)!=1:raise ValueError('unpack hardware loop differs')
        E('unpack','hbpipe_unpack',loops={hw[0]:512})
        for name,repeats in [('hbpipe_prefix',8),('hbpipe_suffix',120)]:
            g=b.graph(name);backs={(p,d):repeats-1 for p,n in g.items() for d in n['edges'] if d<=p}
            if len(backs)!=1:raise ValueError((name,'unexpected loop'))
            calls={p:paths['kernel'] for p,n in g.items() if n['op'].startswith('call')}
            if len(calls)!=1 or any(resolve_target(g,p)!='hb31_qacc4' for p in calls):raise ValueError((name,'kernel callee differs'))
            E(name,name,backs=backs,callees=calls)
        return {n:pair(paths[n]['instructions'],paths[n]['known_cycles']) for n in ('unpack','hbpipe_prefix','hbpipe_suffix')}
    ck.check('linked pipeline helpers and loop counts',pipe_helpers)
    def producer():
        name='hbpipe_produce';g=b.graph(name);cs={};count=None;counts=[]
        for pc,n in sorted(g.items()):
            args=[x.strip() for x in n['args'].split(',')]
            if n['op'].startswith('movi') and args[0]=='a12':count=int(args[1],0)
            if n['op'].startswith('call'):
                t=resolve_target(g,pc)
                if t=='hb31_copy_words':
                    if count not in (8,15):raise ValueError(('unexpected history copy count',pc,count))
                    cs[pc]=paths['history_copy_'+str(count)];counts.append(count)
                elif t=='hbpipe_unpack':cs[pc]=paths['unpack']
                elif t=='hbpipe_prefix':cs[pc]=paths['hbpipe_prefix']
                else:raise ValueError(('unexpected producer callee',t))
                count=None
        if counts!=[15,8,15,8]:raise ValueError(('history copies',counts))
        return fee('HB_PRODUCE',E('producer',name,callees=cs))
    ck.check('fee HB_PRODUCE',producer)
    def worker_kernel():
        g=b.graph('hbpipe_work');cs={p:paths['hbpipe_suffix'] for p,n in g.items() if n['op'].startswith('call')}
        if any(resolve_target(g,p)!='hbpipe_suffix' for p in cs):raise ValueError('unexpected HB worker callee')
        return fee('HB_WORK',E('hb_worker','hbpipe_work',callees=cs))
    ck.check('fee HB_WORK',worker_kernel)
    ck.check('fee HB_REAP',lambda:fee('HB_REAP',E('hb_reap','hbpipe_reap')))
    ck.check('fee HB_BUSY',lambda:fee('HB_BUSY',E('hb_busy','hbpipe_produce',blocked=list(calls0('hbpipe_produce')))))
    ck.check('fee HB_WORK_EMPTY',lambda:fee('HB_WORK_EMPTY',E('hb_work_empty','hbpipe_work',forced={0x5:0x8,0x2a:0x6a},blocked=list(calls0('hbpipe_work')))))
    ck.check('fee HB_REAP_EMPTY',lambda:fee('HB_REAP_EMPTY',E('hb_reap_empty','hbpipe_reap',forced={0x14:0x17,0x1c:0x1f,0x44:0x87})))

    def fixed_hw_loops(name):
        known={};result={}
        for pc,n in sorted(b.graph(name).items()):
            args=[x.strip() for x in n['args'].split(',')]
            if n['op'].startswith('movi'):known[args[0]]=int(args[1],0)
            elif n['op'].startswith('loop'):
                if args[0] not in known:raise ValueError((name,'hardware loop is not a verified fixed immediate',pc))
                result[pc]=known[args[0]]
            elif args[0] and not n['op'].startswith(('s32','s16','s8','b','ret','call')) and n['op'] not in ('j','memw'):
                known.pop(args[0],None)
        return result
    def copy_table():
        name='hbnative_copy_words';g=b.graph(name)
        assert g[3]['op']=='bltui' and g[0x5d]['op']=='beqz.n' and g[0x21]['loop_end']==0x4a and g[0x6d]['loop_end']==0x78
        table=[0];rows={};instructions_by_words=[0]
        for n in range(1,1025):
            bulk,tail=divmod(n,8);choices={3:6 if bulk else 0x5d,0x5d:0x5f if tail else 0x78};loops={}
            if bulk:loops[0x21]=bulk
            if tail:loops[0x6d]=tail
            trace=b.trace(name,choices,loops);row=path_pair(trace)
            expected=(22 if bulk else 4)+(6 if tail else 0)+18*bulk+4*tail
            if row['instructions']!=expected:raise ValueError(('copy formula mismatch',n,row,expected))
            table.append(charge(row));instructions_by_words.append(row['instructions'])
            if n in (1,7,8,9,16,1023,1024):rows[str(n)]=dict(row,fee=table[-1],visits=dict(collections.Counter(x['offset'] for x in trace['path'])))
        meta['copy_words']=dict(fees_by_words=table,examples=rows,instruction_formula='(bulk8>0 ? 22 : 4)+(tail>0 ? 6 : 0)+18*bulk8+4*tail',
            maximum_words=1024,zero_words_not_called=True,derivation='Every count1..1024 is traced in the actual linked function; controls/load uses are recounted per path.')
        fees['COPY_CONTROL_ALLOWANCE']=0;return dict(entries=len(table),examples=rows)
    ck.check('linked copy table every word count1..1024',copy_table)
    for event,name in [('ADAPTER_READ_CLOCK','hbnative_read_clock'),('ADAPTER_PUBLISH','hbnative_publish'),('ADAPTER_ADVANCE','hbnative_advance')]:
        ck.check('fee '+event,lambda event=event,name=name:fee(event,E(name,name,callees=calls0(name))))
    def adapter_steps():
        name='hbnative_step';cs=calls0(name)
        idle=E('adapter_idle',name,callees=cs,forced={0x15:0x17,0x1a:0x1d,0x1d:0x150,0x150:0x153,0x153:0x156},blocked=list(cs))
        direct=E('adapter_active_nocopy',name,callees=cs,blocked=[0xea])
        prefix=E('adapter_copy_prefix',name,callees=cs,blocked=[0x86],terminal_edge=(0x11f,0x9d),
                 forced={0x1a:0x1d,0x1d:0x20,0x23:0x26,0x26:0x110,0x11c:0x11f})
        tail=E('adapter_copy_exit',name,callees=cs,blocked=[0xea,0x86],entry=0x105)
        active=pair(max(direct['instructions'],prefix['instructions']+tail['instructions']),
                    max(direct['known_cycles'],prefix['known_cycles']+tail['known_cycles']))
        paths['adapter_active_base']=active
        chunk=E('adapter_copy_chunk',name,callees=cs,entry=0x9d,terminal_edge=(0x11f,0x9d),
                forced={0x10b:0x10e,0x10e:0x110,0x11c:0x11f})
        fee('ADAPTER_STEP_IDLE',idle);fee('ADAPTER_STEP_ACTIVE',active);fee('ADAPTER_STEP_PER_COPY_CHUNK',chunk)
        return dict(idle=idle,active=active,per_copy_chunk=chunk,scope='active base covers direct and failed-direct eligibility plus fallback exit; full copy-loop body added per chunk')
    ck.check('adapter direct and carry-copy control decomposition',adapter_steps)
    for chunks in range(1,7):
        def check_chunks(chunks=chunks):
            row=E('adapter_whole_at_most_'+str(chunks),'hbnative_step',callees=calls0('hbnative_step'),backs={(0x11f,0x9d):chunks})
            modeled=charge(paths['adapter_active_base'])+chunks*charge(paths['adapter_copy_chunk'])
            assert charge(row)<=modeled,(chunks,charge(row),modeled)
            return dict(chunks=chunks,whole_fee=charge(row),decomposed_fee=modeled,copy_calls={k:v.get('0xea',0) for k,v in row['witness_visits'].items()})
        ck.check('adapter decomposition covers up to'+str(chunks)+' copy chunks',check_chunks)
    def owned_guards():
        import itertools
        name='hbnative_step_clocked';base={0x8:0xa,0x18:0x1b,0x1e:0x21,0x27:0x2a,0x2c:0x2e,0x36:0x38,0x3b:0x3d,
            0x4c:0x4e,0x59:0x5b,0x5b:0x5e,0x61:0x6e,0x80:0x83,0x114:0x117,
            0xf3:{'counter':[0xf3,0x9d],'edges':[0x9d,0x9d,0xf6]}}
        loops=fixed_hw_loops(name)
        if loops!={0x11:6}:raise ValueError(('result zeroing loop differs',loops))
        values=[]
        for owned in range(4):
            rows=[]
            for slots in itertools.combinations(range(3),owned):
                forced=base|{0xa0:{'counter':[0xf3,0x9d],'edges':[0xa3 if i in slots else 0xf0 for i in range(3)]}}
                rows.append(envelope(b,name,callees=calls0(name),forced=forced,blocked=[0x64,0x69,0xd0,0x138,0x155,0x158],
                                     backs={(0xf3,0x9d):2},loops=loops))
            row=max(rows,key=charge);paths['clocked_owned_'+str(owned)]=row;values.append(charge(row))
        fees['CLOCKED_OWNED']=values;return values
    ck.check('fee CLOCKED_OWNED all retained-bank combinations',owned_guards)
    def sdk_submit_fee():
        name='tpre_sdk_submit';g=b.graph(name);calls=[p for p in g if resolve_target(g,p)=='spi_device_queue_trans']
        if calls!=[0x8a]:raise ValueError(('submit call moved',calls))
        loops=fixed_hw_loops(name)
        if loops!={0x51:10}:raise ValueError(('transaction zeroing loop differs',loops))
        return fee('SPI_SUBMIT',E('sdk_submit_wrapper',name,callees={0x8a:paths['sdk_queue_adjusted']},loops=loops,
                                  blocked=blockcalls(name,'sdk_fail'),forced={0x8f:0xa2}))
    ck.check('fee SPI_SUBMIT',sdk_submit_fee)
    for done,event in [(False,'SPI_REAP_EMPTY'),(True,'SPI_REAP_DONE')]:
        def sdk_reap_fee(done=done,event=event):
            choices={0x8:0xb,0x12:0x14,0x17:0x1c,0x1f:0x26,0x35:0x38 if done else 0x21}
            if done:choices.update({0x38:0x3a,0x47:0x60})
            return fee(event,E('sdk_reap_'+str(done),'tpre_sdk_reap',forced=choices,blocked=blockcalls('tpre_sdk_reap','sdk_fail'),
                               callees={0x2c:paths['sdk_sdk_result_'+str(done)]}))
        ck.check('fee '+event,sdk_reap_fee)
    def feed_normal():
        name='tpre_sdk_feed';g=b.graph(name);cs=calls0(name);cs[0xc]=paths['clock'];blocked=blockcalls(name,'sdk_fail')
        normal=E('feed_normal',name,callees=cs,blocked=blocked+[0x3f])
        return fee('FEED',normal)
    ck.check('fee FEED',feed_normal)
    def feed_due():
        name='tpre_sdk_feed';cs=calls0(name);cs[0xc]=paths['clock'];blocked=blockcalls(name,'sdk_fail')
        due=E('feed_due',name,callees=cs|{0x3f:pair(max(paths['sdk_wdt_feed_0']['instructions'],paths['sdk_wdt_feed_1']['instructions']),
                                               max(paths['sdk_wdt_feed_0']['known_cycles'],paths['sdk_wdt_feed_1']['known_cycles']))},
              blocked=blocked)
        fees['WDT_EXTRA']=max(0,charge(due)-charge(paths['feed_normal']));return dict(due=due,extra=fees['WDT_EXTRA'])
    ck.check('fee WDT_EXTRA',feed_due)
    def task_shells():
        name='tpre_sdk_task';g=b.graph(name);stop=E('stopping','tpre_stopping')
        cs=calls0(name)
        for pc in cs:
            if resolve_target(g,pc)=='tpre_stopping':cs[pc]=stop
        # One complete steady iteration, excluding the runtime-step body.
        # The branch which returns to the next iteration is the explicit end.
        for key,start,edge,block in [('owner_shell',0x1ed,(0x200,0x1ed),[0x203]),('worker_shell',0x271,(0x284,0x271),[0x287,0x2a6])]:
            E(key,name,entry=start,terminal_edge=edge,callees=cs,blocked=block,
              forced={edge[0]:edge[1]})
        return dict(owner=paths['owner_shell'],worker=paths['worker_shell'])
    ck.check('steady task shells exclude separately charged runtime bodies',task_shells)
    def owner_phases():
        name='tpre_owner_step';g=b.graph(name);cs=calls0(name);inner={}
        allowed={'s3_native_poll_budget','hbpipe_reap','hbnative_step_clocked','INDIRECT:a8','INDIRECT:a9'}
        for pc in cs:
            symbol=resolve_target(g,pc)
            if symbol and symbol.startswith(('tpre_poll$','tpre_reap$','tpre_produce$','tpre_dma_reap$','tpre_dma_submit$')):
                cg=b.graph(symbol);sub={p:pair() for p,n in cg.items() if n['op'].startswith('call')}
                bad=blockcalls(symbol,'tpre_fail')
                for p in sub:
                    if p not in bad and resolve_target(cg,p) not in allowed:raise ValueError((symbol,'unclassified runtime callee',p,resolve_target(cg,p)))
                inner[symbol]=E(symbol,symbol,callees=sub,blocked=bad,loops=fixed_hw_loops(symbol));cs[pc]=inner[symbol]
            elif symbol!='INDIRECT:a8' and not (symbol or '').startswith('tpre_fail'):raise ValueError(('owner unclassified call',symbol))
        switch=[0x27,0x2a,0x2d,0x30,0x33,0x39,0x3c,0x3f,0x45]
        operations={'beqi':lambda a,z:a==z,'bnei':lambda a,z:a!=z,'bgeui':lambda a,z:a>=z,'bltui':lambda a,z:a<z}
        values=[];loops=fixed_hw_loops(name)
        if loops!={0xe:10}:raise ValueError(('event zeroing loop differs',loops))
        for phase in range(9):
            forced={0x5:0x8,0x15:0x17,0x20:0x22,0xec:0xef,0xcf:0xf1}
            for pc in switch:
                n=g[pc];parts=[s.strip() for s in n['args'].split(',')]
                if parts[0]!='a7' or n['op'] not in operations:raise ValueError(('owner phase selector changed',pc,n))
                forced[pc]=n['edges'][0 if operations[n['op']](phase,int(parts[1],0)) else 1]
            row=E('owner_phase_'+str(phase),name,callees=cs,loops=loops,forced=forced,blocked=blockcalls(name,'tpre_fail'))
            values.append(charge(add(row,paths['owner_shell'])))
        fees['OWNER_PHASE']=values;return dict(fees=values,internal_helpers=list(inner))
    ck.check('fee OWNER_PHASE every source switch phase',owner_phases)
    def worker_shell_fee():
        name='tpre_worker_step';g=b.graph(name);cs=calls0(name);bad=blockcalls(name,'tpre_fail')
        for pc in cs:
            if pc not in bad and resolve_target(g,pc) not in ('hbpipe_work','INDIRECT:a8'):raise ValueError(('unclassified worker callee',pc,resolve_target(g,pc)))
        row=E('worker_runtime_shell',name,callees=cs,blocked=bad,loops=fixed_hw_loops(name))
        return fee('WORKER',add(row,paths['worker_shell']))
    ck.check('fee WORKER',worker_shell_fee)

    # Tick fees use the previously declared normal receiving-state paths only
    # after their logical instructions and CFG are checked against this ELF.
    # The no-switch case assumes distinct caller-selected owner/worker/timer
    # priorities (23/21/22), no unblock, no rollover/catch-up and no new callback.
    # Actual ROM bodies and the SDK-address trampoline are both included.
    def tick_rom(name):
        body=envelope(rb,name,blocked=[0xa6] if name=='wdt_hal_config_stage' else [])
        paths['tick_rom_body_'+name]=body
        paths['tick_rom_'+name]=add(body,thunk(name,name))
        return paths['tick_rom_'+name]
    for name in ('__udivdi3','wdt_hal_feed','wdt_hal_write_protect_disable',
                 'wdt_hal_write_protect_enable','wdt_hal_config_stage'):
        ck.check('tick ROM body and linked thunk '+name,lambda name=name:tick_rom(name))
    for name in ('rtc_clk_bbpll_remove_consumer','rtc_clk_bbpll_add_consumer'):
        ck.check('tick USB clock helper '+name,
                 lambda name=name:paths.__setitem__('tick_'+name,rebound(name)) or paths['tick_'+name])
    def tick_usb_hook():
        row=rebound('usb_serial_jtag_sof_tick_hook',callees={
            0x38:paths['tick_rtc_clk_bbpll_remove_consumer'],
            0x44:paths['tick_rtc_clk_bbpll_add_consumer']})
        paths['tick_usb_hook']=row;return row
    ck.check('tick USB callback inclusive envelope',tick_usb_hook)
    def tick_iwdt(core):
        row=rebound('tick_hook',forced={9:0x19 if core==0 else 0xb},callees={
            0x2f:paths['tick_rom_wdt_hal_write_protect_disable'],
            0x3e:paths['tick_rom_wdt_hal_config_stage'],
            0x4d:paths['tick_rom_wdt_hal_config_stage'],
            0x55:paths['tick_rom_wdt_hal_feed'],
            0x5d:paths['tick_rom_wdt_hal_write_protect_enable']})
        paths['tick_iwdt_'+str(core)]=row;return row
    for core in (0,1):
        ck.check('tick IWDT callback core '+str(core),lambda core=core:tick_iwdt(core))
    def tick_dispatch_own(core):
        occupied=2 if core==0 else 1
        row=rebound('esp_vApplicationTickHook',
            forced={0x18:{'counter':[0x1f,0x16],'edges':[0x1a]*occupied+[0x1d]*(8-occupied)}},
            backs={(0x1f,0x16):7},callees={0x1a:pair()})
        row['assumed_callback_count']=occupied
        row['assumed_callbacks']=['IWDT','USB SOF'] if core==0 else ['IWDT']
        paths['tick_dispatch_own_'+str(core)]=row;return row
    for core in (0,1):
        ck.check('tick dispatcher own eight slots core '+str(core),lambda core=core:tick_dispatch_own(core))
    def tick_dispatch(core):
        children=[paths['tick_dispatch_own_'+str(core)],paths['tick_iwdt_'+str(core)]]
        if core==0:children.append(paths['tick_usb_hook'])
        row=add(*children);paths['tick_dispatch_'+str(core)]=row;return row
    for core in (0,1):
        ck.check('tick dispatcher inclusive core '+str(core),lambda core=core:tick_dispatch(core))
    def tick_kernel(core):
        enter=close('critical_enter');leave=close('critical_exit')
        if core==0:
            inisr=close('in_isr')
            row=rebound('xTaskIncrementTick',forced={9:0x1a,0x2d:0x30,0x42:0xbc,0xc1:0xc4},
                callees={0x1a:inisr,0x22:enter,0x2cd:inisr,0x2d3:leave})
        else:
            row=rebound('xTaskIncrementTickOtherCores',blocked=[0xb],callees={0x33:enter,0x52:leave})
        paths['tick_kernel_'+str(core)]=row;return row
    for core in (0,1):
        ck.check('tick kernel no unblock core '+str(core),lambda core=core:tick_kernel(core))
    def tick_counter():
        row=rebound('systimer_hal_get_counter_value',forced={0x1e:0x21,0x3d:0x40})
        paths['tick_counter_no_retry']=row;return row
    ck.check('tick counter first capture stable snapshot',tick_counter)
    def tick_handler(core):
        row=rebound('SysTickIsrHandler',
            forced={0x53:0x56,0x69:0x6b if core==0 else 0x74,0x77:0x7d,0x80:0x83,0x8b:0x8e},
            callees={0x33:paths['tick_counter_no_retry'],0x4b:paths['tick_rom___udivdi3'],
                     0x60:paths['tick_dispatch_'+str(core)],
                     0x6b if core==0 else 0x74:paths['tick_kernel_'+str(core)]})
        paths['tick_handler_'+str(core)]=row;return row
    for core in (0,1):
        ck.check('tick handler single alarm no switch core '+str(core),lambda core=core:tick_handler(core))
        ck.check('fee TICK'+str(core),lambda core=core:fee('TICK'+str(core),
            add(paths['tick_handler_'+str(core)],paths['irq_entry_exit'])))

    def priced_irq_no_pie():
        # All linked SDK traces that were call-closed above are checked,
        # including every SPI child; tick envelope graphs include every branch.
        # This covers the priced services, not arbitrary registered application
        # ISR/NMI callbacks, which remain an explicit integration precondition.
        for required in ('IRQ_FIRST','IRQ_START','IRQ_COMPLETE','IRQ_CHAIN','TICK0','TICK1'):
            if required not in fees:raise BlockedCondition('unavailable priced IRQ service '+required)
        functions={}
        for key,(row,binary) in traces.items():
            bad=[hex(n['offset']) for n in row['path'] if n['op'].startswith('ee.')]
            assert not bad,(key,bad)
            functions['SDK:'+row['function']]=dict(instructions=len(row['path']),pie=0)
        for key,row in paths.items():
            if key.startswith('tick_') and 'function' in row:
                binary=rb if key.startswith('tick_rom_body_') else b
                g=binary.graph(row['function']);bad=[hex(pc) for pc,n in g.items() if n['op'].startswith('ee.')]
                assert not bad,(key,bad)
                functions['tick:'+row['function']]=dict(instructions=len(g),pie=0)
        for name,row in irq_paths.items():
            bad=[hex(n['offset']) for n in row['path'] if n['op'].startswith('ee.')]
            assert not bad,(name,bad)
            functions['entry:'+name]=dict(instructions=len(row['path']),pie=0)
        return dict(scope='All priced SDK traces, entire tick envelope graphs, and selected normal IRQ entry/exit paths',functions=functions)
    ck.check('priced SPI tick and entry paths contain no PIE instructions',priced_irq_no_pie)

    def require_fee(name):
        if name not in fees:raise BlockedCondition('fee was not derived: '+name)
        value=fees[name]
        if name in ('OWNER_PHASE','CLOCKED_OWNED'):
            assert isinstance(value,list) and len(value)==(9 if name=='OWNER_PHASE' else 4) and all(type(v) is int and v>0 for v in value)
        else:assert type(value) is int and (value>=0 if name=='COPY_CONTROL_ALLOWANCE' else value>0)
        return value
    for name in REQUIRED:ck.check('required fee '+name,lambda name=name:require_fee(name))
    def dynamic(name):
        if name not in meta:raise BlockedCondition('missing dynamic derivation '+name)
        if name=='copy_words':assert len(meta[name]['fees_by_words'])==1025
        return True
    for name in ('copy_words','fill_words'):ck.check('required dynamic '+name,lambda name=name:dynamic(name))
    def repo_path(p):
        p=Path(p).resolve()
        return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
    support=[ROOT/n for n in sorted(set(SOURCE_INPUTS)|set(manifest))]+[
      Path(__file__),ROOT/'ci/t_preprocess_sdk_audit.py',ROOT/'ci/s3_sdk_cost_audit.py',ROOT/'ci/s3_sdk_cost_paths.py',
      ROOT/'ci/t_halfband_capacity_audit.py',ROOT/'ci/s3_irq_entry_audit.py',ROOT/'ci/s3_tick_cost_audit.py',
      ROOT/'reports/s3-sdk-cost-ledger/results.json',ROOT/'reports/s3-spi-running-guard/sdk-S/image/s3_raw_probe.elf.gz',
      ROOT/'reports/s3-spi-running-guard/sdk-S/image/result.json',
      Path(elf),Path(sdk_audit),Path(provenance)]
    hashes={}
    for path in support:
        def bind(path=path):
            hashes[repo_path(path)]=sha(path.read_bytes());return hashes[repo_path(path)]
        ck.check('bind support artifact '+repo_path(path),bind)
    return dict(schema_version=2,status='READY' if ck.passed else 'BLOCKED',fees=fees,paths=paths,
      copy_words=meta.get('copy_words'),fill_words=meta.get('fill_words'),checks=ck.rows,
      check_counts={s:sum(r['status']==s for r in ck.rows) for s in ('PASS','FAIL','BLOCKED')},
      linked_elf_sha256=res.data['ELF'].sha if 'ELF' in res.data else None,elf_sha256=res.data['ELF'].sha if 'ELF' in res.data else None,
      rom_elf_sha256=res.data['ROM'].sha if 'ROM' in res.data else None,
      linked_elf_path=repo_path(elf),sdk_audit_path=repo_path(sdk_audit),provenance_path=repo_path(provenance),
      source_sha256=hashes,non_fail_fast=True,target_executed=False,hardware_wcet=False,
      sdk_paths={'|'.join(map(str,k)):v for k,v in closed.items()},
      sdk_relocations={name:{'instruction_map':{hex(k):hex(v) for k,v in m.items()},'entry_map':{hex(k):hex(v) for k,v in e.items()}} for name,(m,e) in maps.items()},
      irq_paths=irq_paths,model=dict(alpha_numerator=11,alpha_denominator=10,fee='max(ceil(1.1*executed instructions), instruction/control estimate)',
         controls='taken branches/calls/returns/jumps +2; immediately consumed scalar loads +1; linked PIE interlocks audited separately',
         spi_wire=meta.get('spi_wire'),cache_placement=res.data.get('SDK audit',{}).get('cache_placement',{}),kernel_arithmetic=meta.get('kernel_arithmetic'),kernel_hazards=meta.get('kernel_hazards')),
      assumptions=['Reception runs with flash cache enabled: actual SPI ISR helpers can reside in flash even when the ISR root is IRAM.',
       'No flash/cache/MMIO/memw/bus latency bound is supplied. The multiplier and stated controls are an explicit model, not measured timing or WCET.',
       'SPI3 80MHz: QIO data uses4 lanes;16 command plus64 address bits use1 lane because MULTILINE flags are absent. A16KiB frame takes98,544 CPU cycles at240MHz before service gaps. Two descriptors, one device, no waiting tasks, aligned internal DMA payload and no receive buffer.',
       'Nominal critical sections are uncontended; CAS succeeds once; window traps/nested interrupts and other application work are excluded.',
       'One normal IRQ entry/exit is included per SPI/tick service; caller queue API excludes IRQ. Request while active is included in API fee.',
       'One tick per alarm, no catch-up, no task unblock/switch/counter retry; IWDT both cores and USB SOF callback on core0 only.',
       'Owner priority23, worker21 and timer22 are supplied caller assumptions; general launcher accepts caller priorities. PHY tracking is core1/1000ms with unbounded hardware wait.',
       'Startup/task creation, clock calibration and lazy CP3 warmup occur RF-off. stopped means quiescence, not task death or DMA release.',
       'Native/adapter fees exclude their separately charged callbacks/helpers; HB fees include kernel; owner/task shells exclude separately charged events.',
       'C hooks place costs at documented publication/lease boundaries. Finite model refusal is not a model-independent proof of physical overwrite or S3 impossibility.'])
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);ap.add_argument('--rom',type=Path,required=True)
    ap.add_argument('--elf',type=Path,default=OUT/'t_preprocess_integration_probe.elf.gz');ap.add_argument('--sdk-audit',type=Path,default=OUT/'audit.json')
    ap.add_argument('--provenance',type=Path,default=OUT/'provenance.json');ap.add_argument('--output',type=Path,default=ROOT/'reports/s3-t-preprocess-integration-v2/runtime/costs.json');a=ap.parse_args()
    r=build(a.toolchain.resolve(),a.elf,a.sdk_audit,a.rom,a.provenance);a.output.parent.mkdir(parents=True,exist_ok=True)
    # Keep the reviewable fee ledger small without discarding CFG witnesses.
    # The runtime verifier requires the selected gzip and its compressed hash.
    verbose={key:r.pop(key) for key in ('paths','sdk_paths','sdk_relocations','irq_paths')}
    verbose.update(schema_version=2,linked_elf_sha256=r['linked_elf_sha256'])
    evidence=a.output.with_name('cost-evidence.json.gz').resolve()
    evidence.write_bytes(gzip.compress((json.dumps(verbose,separators=(',',':'))+'\n').encode(),mtime=0))
    name=str(evidence.relative_to(ROOT)) if evidence.is_relative_to(ROOT) else str(evidence)
    digest=sha(evidence.read_bytes());r.update(evidence_path=name,evidence_sha256=digest)
    r['source_sha256'][name]=digest
    a.output.write_text(json.dumps(r,separators=(',',':'))+'\n');print(json.dumps(dict(status=r['status'],checks=r['check_counts'],fees=r['fees']),indent=2))
    return 0 if r['status']=='READY' else 1
if __name__=='__main__':raise SystemExit(main())
