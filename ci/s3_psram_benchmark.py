#!/usr/bin/env python3
"""Physical-pin PSRAM BIST synthesis, P&R and evidence (not receiver fit)."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--seeds',type=int,nargs='+',default=[1,2,3])
p.add_argument('--bridge',action='store_true',help='Include SPI, page store and reader')
p.add_argument('--fec',action='store_true',help='Co-place independent S metric/TC8PSK/RS workload, not a receiver')
p.add_argument('--compact-output',action='store_true',help='Use one BSRAM for TC8PSK output instead of FF buffers')
p.add_argument('--compact-b1',action='store_true',help='Store four uncoded branch choices per row rather than 64 state choices')
p.add_argument('--compact-rs',action='store_true',help='Move serial RS omega/error tables into BSRAM')
p.add_argument('--acs22',action='store_true',help='Use 22 ACS lanes in three clocks per symbol')
p.add_argument('--metric-q15',action='store_true',help='Exact 12-bit path metrics under fixed Q15/SHIFT22 metric-unit contract')
p.add_argument('--folded-metric',action='store_true',help='Share exact metric arithmetic at one symbol/3 clocks')
p.add_argument('--cost-shift',type=int,choices=(22,23,24,25),default=22,
               help='Experimental FPGA-only branch quantizer; values above 22 change costs and require BER checks')
p.add_argument('--rs-offload',action='store_true',help='Partial host-RS split: 32 ACS + FPGA syndrome/Chien, no RPC/correction buffers')
p.add_argument('--split-acs22',action='store_true',help='Use 22 ACS/3 clocks in the partial RS offload workload')
p.add_argument('--rs-correction',action='store_true',help='Also co-place the byte correction stream, still without RPC/memory scheduling')
p.add_argument('--rs-rpc-guard',action='store_true',help='Also co-place the S3 response validator; no RPC storage/ownership/producer')
p.add_argument('--rpc-payload-flag',action='store_true',help='Register payload-region membership in the RPC guard')
p.add_argument('--rpc-bit-ranges',action='store_true',help='Use exact bit tests for RPC header/padding power-of-two bounds')
p.add_argument('--rpc-clock27',action='store_true',help='Independent 27 MHz validator with a backpressured 90 MHz byte FIFO')
p.add_argument('--syndrome-ready',action='store_true',help='Use a registered last-byte flag in the syndrome input-ready path')
p.add_argument('--syndrome4',action='store_true',help='Use four GF lookup ports/four clocks per byte')
p.add_argument('--rr-table',action='store_true',help='Elaborate constant round-robin grant priorities')
p.add_argument('--core-mhz',type=int,choices=(90,99),default=99,help='Static 27 MHz PLL target; 90 uses VCO 720 MHz')
p.add_argument('--wide-lut',action='store_true',help='Permit Gowin LUT5..8 mapping')
p.add_argument('--no-ce',action='store_true',help='Map FF enables to explicit feedback muxes')
p.add_argument('--pnr-timeout',type=int,default=180,help='Wall seconds per placement seed; timeout is NOT a fit proof')
p.add_argument('--placer',choices=('heap','sa'),default='heap')
p.add_argument('--heap-cell-timeout',type=int,default=8,help='nextpnr cell-placement divisor; larger bounds each search sooner')
args=p.parse_args()
if args.rpc_clock27:args.rpc_bit_ranges=True
if args.rpc_bit_ranges:args.rpc_payload_flag=True
if args.rpc_payload_flag:args.rs_rpc_guard=True
if args.rs_rpc_guard:args.rs_correction=True
if args.cost_shift!=22:args.folded_metric=True
if args.rs_correction:args.rs_offload=True
if args.split_acs22:args.rs_offload=True
if args.syndrome_ready:args.rs_offload=True
if args.syndrome4:args.rs_offload=True
if args.syndrome4 and args.syndrome_ready:p.error('choose one syndrome implementation')
if args.rs_offload:args.folded_metric=True
if args.folded_metric:args.metric_q15=True
if args.metric_q15:args.acs22=True
if args.acs22:args.compact_rs=True
if args.compact_rs:args.compact_b1=True
if args.compact_b1:args.compact_output=True
if args.compact_output:args.fec=True
if args.fec:args.bridge=True
if args.rs_offload:args.acs22=args.split_acs22;args.compact_rs=False
name='s3-memory-fec-compact' if args.compact_output else 's3-memory-fec' if args.fec else 's3-memory-bridge' if args.bridge else 's3-psram'
if args.wide_lut:name+='-wide'
if args.no_ce:name+='-noce'
if args.compact_b1:name+='-b1'
if args.compact_rs:name+='-rs'
if args.acs22:name+='-acs22'
if args.metric_q15:name+='-q15'
if args.folded_metric:name+='-folded'
if args.cost_shift!=22:name+=f'-shift{args.cost_shift}'
if args.rs_offload:name+='-rs-offload'
if args.rs_correction:name+='-correct'
if args.rs_rpc_guard:name+='-rpcguard'
if args.rpc_payload_flag:name+='-rpcflag'
if args.rpc_bit_ranges:name+='-rpcranges'
if args.rpc_clock27:name+='-rpc27'
if args.syndrome_ready:name+='-syready'
if args.syndrome4:name+='-sy4'
if args.rr_table:name+='-rr'
if args.core_mhz!=99:name+=f'-{args.core_mhz}MHz'
top='s3_memory_fec_benchmark' if args.fec else 's3_memory_bridge_benchmark' if args.bridge else 's3_psram_benchmark'
out=ROOT/f'build/{name}-pnr';out.mkdir(parents=True,exist_ok=True)
sources=['rtl/s3_psram_burst.sv','rtl/s3_psram_queue.sv','rtl/s3_psram_phy.sv',
         'rtl/s3_psram_clock.sv','experiments/s3_psram_benchmark.sv']
if args.bridge:
    sources=sources[:-1]+['rtl/s3_async_fifo.sv','rtl/s3_spi_rx.sv','rtl/s3_page_guard.sv',
        'rtl/s3_page_reorder.sv','rtl/s3_rx_page_store.sv','rtl/s3_psram_page_reader.sv',
        'rtl/s3_spi_memory_bridge.sv','experiments/s3_memory_bridge_benchmark.sv']
if args.fec:
    sources[-1]='experiments/s3_memory_fec_benchmark.sv'
    sys.path.insert(0,str(ROOT/'experiments'))
    from s3_tc8psk import source as tc_source
    from s3_rs_isdb import source as rs_source
    (out/'viterbi.sv').write_text(tc_source(args.compact_output,args.compact_b1,22 if args.acs22 else 32,args.metric_q15))
    (out/'rs.sv').write_text(rs_source(True,args.compact_rs))
    sources+=['rtl/s3_tc8psk_metric.sv',str((out/'viterbi.sv').relative_to(ROOT)),str((out/'rs.sv').relative_to(ROOT))]
    if args.folded_metric:
        template='experiments/s3_memory_rs_split_benchmark.sv' if args.rs_offload else 'experiments/s3_memory_fec_benchmark.sv'
        (out/'top.sv').write_text((ROOT/template).read_text().replace('s3_tc8psk_metric metric','s3_tc8psk_metric_folded metric'))
        sources=[str((out/'top.sv').relative_to(ROOT)) if s=='experiments/s3_memory_fec_benchmark.sv' else
                 'rtl/s3_tc8psk_metric_folded.sv' if s=='rtl/s3_tc8psk_metric.sv' else s for s in sources]
    if args.rs_offload:
        sources=[s for s in sources if s!=str((out/'rs.sv').relative_to(ROOT))]
        sources+=['rtl/s3_rs_syndrome.sv','rtl/s3_rs_chien.sv']
    if args.cost_shift!=22:
        from s3_tc8psk_precision import metric_source, viterbi_source
        (out/'metric.sv').write_text(metric_source(args.cost_shift))
        (out/'viterbi.sv').write_text(viterbi_source(args.cost_shift,22 if args.acs22 else 32))
        sources=[str((out/'metric.sv').relative_to(ROOT)) if s=='rtl/s3_tc8psk_metric_folded.sv' else s for s in sources]
    if args.rs_correction:
        top_text=(out/'top.sv').read_text()
        top_text=top_text.replace(' assign activity=', ''' wire correction_ready,correction_error,correction_in_ready;
 wire correction_valid,correction_last,correction_failed;wire[7:0] correction_data;
 s3_rs_correction correction(clk,rst,1'b1,correction_ready,syndromes[3:0],
  syndromes[63:0],syndromes[127:64],rs_fail,correction_error,
  1'b1,correction_in_ready,lfsr[31:24],correction_valid,1'b1,
  correction_data,correction_last,correction_failed);
 assign activity=''').replace('checksum,offset,',
 'correction_ready,correction_error,correction_in_ready,correction_valid,correction_data,correction_last,correction_failed,checksum,offset,')
        (out/'top.sv').write_text(top_text)
        sources+=['rtl/s3_rs_correction.sv']
    if args.rs_rpc_guard:
        top_text=(out/'top.sv').read_text()
        top_text=top_text.replace(' assign activity=', ''' // Independent validation workload; not a connected RPC protocol.
 wire guard_cfg_ready,guard_in_ready,guard_result;wire[5:0] guard_errors;
 s3_rs_rpc_guard guard(clk,rst,1'b1,guard_cfg_ready,lfsr[0]?8'd2:8'd4,
  lfsr[31:16],lfsr[63:32],lfsr[24],guard_in_ready,lfsr[7:0],lfsr[42],
  guard_result,lfsr[25],guard_errors);
 assign activity=''').replace('checksum,offset,',
 'guard_cfg_ready,guard_in_ready,guard_result,guard_errors,checksum,offset,')
        (out/'top.sv').write_text(top_text)
        sources+=['rtl/s3_rs_rpc_guard.sv']
        if args.rpc_payload_flag:
            from s3_rs_rpc_guard_registered import source as guard_source
            (out/'guard.sv').write_text(guard_source(args.rpc_bit_ranges))
            sources=[str((out/'guard.sv').relative_to(ROOT)) if s=='rtl/s3_rs_rpc_guard.sv' else s for s in sources]
        if args.rpc_clock27:
            top_text=(out/'top.sv').read_text()
            top_text=top_text.replace(' s3_rs_rpc_guard guard(clk,rst,1\'b1,guard_cfg_ready,lfsr[0]?8\'d2:8\'d4,\n  lfsr[31:16],lfsr[63:32],lfsr[24],guard_in_ready,lfsr[7:0],lfsr[42],\n  guard_result,lfsr[25],guard_errors);', ''' wire guard_clock;BUFG guard_global(.I(clk27),.O(guard_clock));
 // Descriptor and result controls stay in the 27 MHz domain. Real owner/
 // descriptor/result handshakes with the 90 MHz scheduler remain absent.
 reg[63:0] guard_lfsr;
 always @(posedge guard_clock or negedge rst)
  if(!rst)guard_lfsr<=64'h123fedab987ace02;
  else guard_lfsr<={guard_lfsr[62:0],guard_lfsr[63]^guard_lfsr[62]^guard_lfsr[60]^guard_lfsr[59]};
 s3_rs_rpc_guard_cdc guard(clk,guard_clock,rst,1'b1,guard_cfg_ready,
  guard_lfsr[0]?8'd2:8'd4,guard_lfsr[31:16],guard_lfsr[63:32],
  lfsr[24],guard_in_ready,lfsr[7:0],lfsr[42],guard_result,guard_lfsr[25],guard_errors);''')
            if 's3_rs_rpc_guard_cdc guard' not in top_text:raise ValueError('missing guard clock anchor')
            (out/'top.sv').write_text(top_text)
            sources+=['rtl/s3_rs_rpc_guard_cdc.sv']
    if args.syndrome_ready or args.syndrome4:
        if args.syndrome4:from s3_rs_syndrome_parallel import source as syndrome_source
        else:from s3_rs_syndrome_registered import source as syndrome_source
        (out/'syndrome.sv').write_text(syndrome_source())
        sources=[str((out/'syndrome.sv').relative_to(ROOT)) if s=='rtl/s3_rs_syndrome.sv' else s for s in sources]
if args.rr_table:
    sys.path.insert(0,str(ROOT/'experiments'))
    from s3_psram_queue_rotated import source as queue_source
    (out/'queue.sv').write_text(queue_source())
    sources=[str((out/'queue.sv').relative_to(ROOT)) if s=='rtl/s3_psram_queue.sv' else s for s in sources]
if args.core_mhz==90:
    clock_source=(ROOT/'rtl/s3_psram_clock.sv').read_text().replace('99 MHz','90 MHz').replace('792 MHz','720 MHz').replace('.FBDIV_SEL(10)','.FBDIV_SEL(9)')
    (out/'clock.sv').write_text(clock_source)
    sources=[str((out/'clock.sv').relative_to(ROOT)) if s=='rtl/s3_psram_clock.sv' else s for s in sources]
hashes={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources}
if (out/'result.json').exists():
    old=json.loads((out/'result.json').read_text())
    key=hashlib.sha256(json.dumps(old,sort_keys=True).encode()).hexdigest()[:12]
    trial=out/'trials'/key;trial.mkdir(parents=True,exist_ok=True)
    for f in ('result.json','synth.log','pnr.log','stat.json'):
        if (out/f).exists():shutil.copy2(out/f,trial/f)
synth_flags=('-nowidelut ' if not args.wide_lut else '')+('-nodffe ' if args.no_ce else '')
(out/'synth.ys').write_text('read_verilog -sv '+' '.join(sources)+'\n'+
    'synth_gowin -top '+top+' -family gw1n '+synth_flags+'-json '+str(out/'design.json')+'\n'+
    'tee -o '+str(out/'stat.json')+' stat -json\ncheck -assert\n')
with (out/'synth.log').open('w') as f:
    rc=subprocess.run(['yosys','-Q','-T','-s',str(out/'synth.ys')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT).returncode
if rc:
    # An interrupted/failed synthesis must leave reviewable evidence too.
    # In particular, never reuse a previous routed result after this failure.
    result=dict(scope=__doc__,variant=name,exit_code=rc,
        pipeline_stage='synthesis',sources=hashes,
        synthesis_flags=synth_flags.strip(),pnr_trials=[],
        logic_site_audit=None,physical_timing_proven=False,
        receiver_adopted=False,safe_to_flash=False,
        absent=['successful synthesis','placement and routing',
                'full receiver integration','real hardware BIST'])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/f'reports/{name}.json').write_text(json.dumps(result,indent=2)+'\n')
    raise RuntimeError(f'synthesis exited {rc}: {out / "synth.log"}')
modules=json.loads((out/'design.json').read_text())['modules']
tops=[m for m in modules.values() if int(str(m.get('attributes',{}).get('top','0')),2)]
if len(tops)!=1:raise ValueError('ambiguous top')
design=tops[0]
buf=[c for c in design['cells'].values() if c['type']=='IBUF' and c['connections']['I']==design['ports']['clk27']['bits']]
aliases=[n for n,v in design['netnames'].items() if v['bits']==buf[0]['connections']['O'] and not n.startswith('$')]
clock=min(aliases,key=len)
def net_alias(bits):
    aliases=[n for n,v in design['netnames'].items() if v['bits']==bits and not n.startswith('$')]
    if not aliases:raise ValueError('missing clock net alias')
    return min(aliases,key=len)
pll=[c for c in design['cells'].values() if c['type']=='rPLL']
if len(pll)!=1:raise ValueError('expected one PLL')
clock_pairs=[(clock,27)]+[(net_alias(pll[0]['connections'][port]),args.core_mhz) for port in ('CLKOUT','CLKOUTP')]
if args.rpc_clock27:
    # Flattening may retain only guard.check_clk, not the top-level alias.
    gb=[c for c in design['cells'].values() if c['type']=='BUFG' and c['connections']['I']==buf[0]['connections']['O']]
    if len(gb)!=1:raise ValueError('missing or ambiguous 27 MHz guard buffer')
    clock_pairs.append((net_alias(gb[0]['connections']['O']),27))
if args.bridge:
    for port in ('spi2_sclk','spi3_sclk'):
        ib=[c for c in design['cells'].values() if c['type']=='IBUF' and c['connections']['I']==design['ports'][port]['bits']]
        gb=[c for c in design['cells'].values() if c['type']=='BUFG' and c['connections']['I']==ib[0]['connections']['O']]
        clock_pairs.append((net_alias(gb[0]['connections']['O']),80))
clocks=''.join(f'ctx.addClock({net!r},{freq})\n' for net,freq in clock_pairs)
(out/'clocks.py').write_text(clocks)
cst='experiments/s3_psram_benchmark.cst'
if args.bridge:
    cst=str(out/'pins.cst')
    (out/'pins.cst').write_text((ROOT/'experiments/s3_spi_rx_benchmark.cst').read_text().replace('"clk"','"clk27"'))
site_audit=None
if not args.wide_lut:
    from s3_logic_site_audit import audit
    with (out/'pack-only.log').open('w') as f:
        pack_rc=subprocess.run(['nextpnr-himbaechel','--json',str(out/'design.json'),
            '--device','GW1NR-LV9QN88PC6/I5','--vopt','family=GW1N-9C',
            '--vopt','cst='+cst,'--pre-pack',str(out/'clocks.py'),
            '--pack-only','--write',str(out/'packed.json')],cwd=ROOT,
            stdout=f,stderr=subprocess.STDOUT).returncode
    if pack_rc:raise RuntimeError('packing failed: '+str(out/'pack-only.log'))
    site_audit=audit(out/'packed.json')
    (out/'logic-site-audit.json').write_text(json.dumps(site_audit,indent=2)+'\n')
trials=[];report={}
for seed in args.seeds:
    log=out/f'pnr-seed{seed}.log';rp=out/f'report-seed{seed}.json'
    rp.unlink(missing_ok=True)
    if site_audit and site_audit['mapped_netlist_ruled_out']:
        rc=126
        note=('ERROR: Mapped netlist needs at least '+str(site_audit['minimum_required_logic_sites'])+
              ' logic sites, exceeding 8640; placement skipped (not an RTL-wide impossibility claim)')
        log.write_text((out/'pack-only.log').read_text()+'\n'+note+'\n')
        trials.append(dict(seed=seed,exit_code=rc,notes=[note],placement_skipped=True))
        shutil.copy2(log,out/'pnr.log')
        break
    with log.open('w') as f:
        try:
            rc=subprocess.run(['nextpnr-himbaechel','--json',str(out/'design.json'),
                '--device','GW1NR-LV9QN88PC6/I5','--vopt','family=GW1N-9C',
                '--vopt','cst='+cst,'--freq',str(args.core_mhz),
                '--pre-pack',str(out/'clocks.py'),'--seed',str(seed),'--report',str(rp),
                '--placer',args.placer,'--placer-heap-cell-placement-timeout',str(args.heap_cell_timeout),
                '--write',str(out/'routed.json')],
                cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=args.pnr_timeout).returncode
        except subprocess.TimeoutExpired:
            rc=124;f.write(f'\nERROR: P&R timed out after {args.pnr_timeout} seconds; fit remains unknown\n')
    report=json.loads(rp.read_text()) if rp.exists() else {}
    notes=[l for l in log.read_text().splitlines() if l.startswith(('Warning:','ERROR:'))]
    packed={n:dict(used=int(u),available=int(v)) for n,u,v in re.findall(r'Info:\s+(\w+):\s+(\d+)/\s+(\d+)',log.read_text())}
    trials.append(dict(seed=seed,exit_code=rc,fmax=report.get('fmax'),notes=notes,
                       preplacement_utilization=packed,timeout_seconds=args.pnr_timeout,
                       placer=args.placer,heap_cell_timeout=args.heap_cell_timeout))
    shutil.copy2(log,out/'pnr.log')
    # A placement timeout says nothing about the remaining seeds. Try them;
    # otherwise --seeds 1 2 3 silently degenerates to a single failed trial.
    if rc==0 or (rc!=124 and any('ERROR:' in l and 'Max frequency' not in l for l in notes)):break
result=dict(scope=__doc__,variant=name,exit_code=rc,sources=hashes,clock_constraints=clock_pairs,
    synthesis_flags=synth_flags.strip(),
    logic_site_audit=site_audit,
    synthesis=json.loads((out/'stat.json').read_text()),pnr_trials=trials,
    utilization=report.get('utilization'),fmax=report.get('fmax'),
    physical_timing_proven=False,receiver_adopted=False,safe_to_flash=False,
    absent=['validated DQ/RWDS sampling eye','phase-related external IO STA','full receiver integration','real hardware BIST'])
if args.rs_offload:result['absent']+=['host RS WCET','RPC protocol/queues','coded-block memory and correction writes','TS output scheduler']
if args.cost_shift!=22:
    from s3_tc8psk_precision import bound
    result['experimental_FPGA_quantizer']=bound(args.cost_shift)
    result['absent']+=['receiver BER/CN acceptance for changed FPGA branch quantizer']
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(ROOT/f'reports/{name}.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('exit_code','pnr_trials','utilization')},indent=2))
