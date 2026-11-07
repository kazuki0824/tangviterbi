"""Actual tile DMA connected to FFT/service/K7 for resource and timing measurement. Global descriptor supplier, other demodulation stages and PHY remain absent; no end-to-end functional proof."""
import argparse,collections,gzip,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
FILES=['experiments/sdram_client_arbiter_tile_grace_metadata.sv', 'experiments/sdf_sdram_service_metadata.sv', 'experiments/t_soft_sdram_service_metadata.sv', 'rtl/shared_sdf_fft.sv', 'reports/pr7-fft-archive/rtl/research_sdf_twiddle.sv', 'rtl/sdf_delay_cache.sv', 'rtl/sdram_client_arbiter.sv', 'experiments/dual_sdram_refresh_predecode.sv', 'rtl/sdf_sdram_service.sv', 'experiments/t_soft_reader_buffered.sv', 'experiments/t_soft_sdram_service_buffered.sv', 'experiments/shared_tc8_k7_context.sv', 'experiments/s3_depuncture_isolated.sv', 'rtl/s3_tc8psk_metric_folded.sv', 'experiments/shared_tc8_k7_stream.sv', 'experiments/shared_tc8_k7_depuncture_isolated_stream.sv', 'experiments/s_input_fifo.sv', 'experiments/t_time_tile_store.sv', 'experiments/t_time_tile_dma_direct.sv', 'experiments/shared_receiver_fft_tile.sv', 'experiments/shared_receiver_fft_tile_probe.sv']
def count(c):return dict(collections.Counter(x['type'] for x in c.values()))
def logic(c):return sum(v for k,v in c.items() if re.fullmatch('LUT[1-4]|ALU',k))
def ff(c):return sum(v for k,v in c.items() if k.startswith('DFF'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--reuse',type=Path);a=p.parse_args();d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
 if a.reuse:
  prior=json.loads((a.reuse/'packed-budget.json').read_text())
  for f,h in prior['source_sha256'].items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h,f
  for name in ('mapped.json','core-mapped.json'):
   source=a.reuse/(name+'.gz');(d/name).write_bytes(gzip.decompress(source.read_bytes()))
  (d/'reuse.json').write_text(json.dumps(dict(directory=str(a.reuse),source_sha256=prior['source_sha256']),indent=2)+'\n')
 else:
  for prefix,top,files in [('core-','shared_receiver_fft_tile',FILES[:-1]),('','shared_receiver_fft_tile_probe',FILES)]:
   (d/(prefix+'synth.ys')).write_text('read_verilog -sv '+' '.join(str(ROOT/f) for f in files)+f'\nsynth_gowin -family gw2a -top {top} -nowidelut -json {d}/{prefix}mapped.json\ncheck -assert\n')
   assert run(['yosys','-Q','-s',str(d/(prefix+'synth.ys'))],ROOT/'reports/pr7-fft-archive',d/(prefix+'synth.log'),600)==0
 pins=[('clk',4),('resetn',87),('scan_enable',73),('scan_in',74),('signature',75)]
 (d/'pins.cst').write_text(''.join(f'IO_LOC "{s}" {n};\nIO_PORT "{s}" IO_TYPE=LVCMOS33;\n'for s,n in pins))
 cmd=['nextpnr-himbaechel','--placer','heap','--placer-heap-cell-placement-timeout','10000','--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst','--freq',str(1080/7),'--seed','1','--report',str(d/'pnr.json'),'--write',str(d/'routed.json')]
 (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');code=run(cmd,ROOT,d/'pnr.log',600)
 mapped=json.loads((d/'mapped.json').read_text())['modules']['shared_receiver_fft_tile_probe']['cells']
 regs={k for k,v in mapped.items() if v['type'].startswith('DFF') and FILES[-1] in v.get('attributes',{}).get('src','')}
 assert len(regs)>1900,len(regs)
 result=dict(scope=__doc__,target_MHz=1080/7,pnr_exit=code,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES+['ci/shared_receiver_fft_tile_grace_heap.py']},harness_register_count=len(regs),whole_receiver_verified=False,external_IO_STA_verified=False,service_included=True,K7_included=True)
 core=count(json.loads((d/'core-mapped.json').read_text())['modules']['shared_receiver_fft_tile']['cells']);result['mapped_core_cells']=core
 if (d/'routed.json').exists():
  routed=json.loads((d/'routed.json').read_text())['modules']['top']['cells']
  harness={k:v for k,v in routed.items() if k in regs or k.startswith('digest') or k.removesuffix('_passthrough_lut$') in regs}
  actual={k:v for k,v in routed.items() if k not in harness};hc,ac,tc=count(harness),count(actual),count(routed)
  report=json.loads((d/'pnr.json').read_text());u=report['utilization'];assert logic(tc)==u['LUT4']['used']+u['ALU']['used'];assert ff(hc)==len(regs)
  ram=ac.get('RAM16SDP4',0)
  result.update(joint_cells=ac,harness_cells=hc,logic_with_ram_blockers=logic(ac)+4*ram,FF_sites_with_ram_blockers=ff(ac)+6*ram,BSRAM=u['BSRAM']['used'],DSP18=u['MULT18X18']['used'],RAM16SDP4=ram,fmax=report['fmax'],utilization=u)
 log=(d/'pnr.log').read_text();result['route_completed']='Routing complete.'in log;result['partial_target_pass']=code==0 and result['route_completed'];result['errors']=[x for x in log.splitlines()if x.startswith('ERROR:')]
 result['yosys_version']=subprocess.check_output(['yosys','-V'],text=True).strip();result['pnr_version']=subprocess.check_output(['nextpnr-himbaechel','--version'],stderr=subprocess.STDOUT,text=True).strip()
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if not k.endswith('cells') and k not in ('utilization','source_sha256')},indent=2))
 for name in ('mapped.json','core-mapped.json','routed.json','synth.log','core-synth.log'):
  p=d/name
  if p.exists():Path(str(p)+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
if __name__=='__main__':main()
