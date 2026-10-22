"""Actual tile DMA connected to FFT/service/K7 for resource and timing measurement. Global descriptor supplier, other demodulation stages and PHY remain absent; no end-to-end functional proof."""
import argparse,collections,gzip,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
FILES=['experiments/sdram_client_arbiter_direct_metadata.sv', 'experiments/sdf_sdram_service_metadata.sv', 'experiments/t_soft_sdram_service_metadata.sv', 'rtl/shared_sdf_fft.sv', 'reports/pr7-fft-archive/rtl/research_sdf_twiddle.sv', 'rtl/sdf_delay_cache.sv', 'rtl/sdram_client_arbiter.sv', 'experiments/dual_sdram_refresh_predecode.sv', 'rtl/sdf_sdram_service.sv', 'experiments/t_soft_reader_buffered.sv', 'experiments/t_soft_sdram_service_buffered.sv', 'experiments/shared_tc8_k7_context.sv', 'experiments/s3_depuncture_isolated.sv', 'rtl/s3_tc8psk_metric_folded.sv', 'experiments/shared_tc8_k7_stream.sv', 'experiments/shared_tc8_k7_depuncture_isolated_stream.sv', 'experiments/s_input_fifo.sv', 'experiments/t_time_tile_store.sv', 'experiments/t_time_tile_dma_shared.sv', 'experiments/shared_receiver_fft_tile.sv', 'experiments/shared_receiver_fft_tile_probe.sv']
def count(c):return dict(collections.Counter(x['type'] for x in c.values()))
def logic(c):return sum(v for k,v in c.items() if re.fullmatch('LUT[1-4]|ALU',k))
def ff(c):return sum(v for k,v in c.items() if k.startswith('DFF'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
 for prefix,top,files in [('core-','shared_receiver_fft_tile',FILES[:-1]),('','shared_receiver_fft_tile_probe',FILES)]:
  (d/(prefix+'synth.ys')).write_text('read_verilog -sv '+' '.join(str(ROOT/f) for f in files)+f'\nsynth_gowin -family gw2a -top {top} -nowidelut -json {d}/{prefix}mapped.json\ncheck -assert\n')
  assert run(['yosys','-Q','-s',str(d/(prefix+'synth.ys'))],ROOT/'reports/pr7-fft-archive',d/(prefix+'synth.log'),600)==0
 pins=[('clk',4),('resetn',87),('scan_enable',73),('scan_in',74),('signature',75)]
 (d/'pins.cst').write_text(''.join(f'IO_LOC "{s}" {n};\nIO_PORT "{s}" IO_TYPE=LVCMOS33;\n'for s,n in pins))
 cmd=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst','--pack-only','--write',str(d/'packed.json')]
 (d/'pack-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 assert run(cmd,ROOT,d/'pack.log',120)==0
 import ci.t_time_tile_packed_budget as budget
 budget.FILES=FILES
 sys.argv=[sys.argv[0],str(d)]
 budget.main()
 result=json.loads((d/'packed-budget.json').read_text())
 result['source_sha256']={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES+['ci/shared_receiver_fft_tile_shared_evidence.py','ci/t_time_tile_packed_budget.py']}
 result['route_completed']=False
 (d/'packed-budget.json').write_text(json.dumps(result,indent=2)+'\n')
 for name in ('mapped.json','core-mapped.json','packed.json','synth.log','core-synth.log'):
  p=d/name
  if p.exists():Path(str(p)+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
if __name__=='__main__':main()
