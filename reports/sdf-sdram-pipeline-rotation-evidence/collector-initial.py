"""CAD probe of cache/arbiter/controller. No PHY or whole-receiver closure."""
import argparse,collections,gzip,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
FILES=['rtl/sdf_delay_cache.sv','rtl/sdram_client_arbiter.sv','rtl/dual_sdram_burst.sv','rtl/sdf_sdram_service.sv','experiments/sdf_sdram_service_probe.sv']

def counts(cells):return dict(collections.Counter(v['type'] for v in cells.values()))
def logic(c):return sum(v for k,v in c.items() if re.fullmatch('LUT[1-4]|ALU',k))
def ff(c):return sum(v for k,v in c.items() if k.startswith('DFF'))
def read(p):
 return json.loads(p.read_text()) if p.exists() else json.loads(gzip.decompress(Path(str(p)+'.gz').read_bytes()))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--collect-only',action='store_true');p.add_argument('--rotation',action='store_true');a=p.parse_args();d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
 files=FILES.copy()
 if a.rotation:files[:2]=['experiments/rotation_sdf_delay_cache.sv','experiments/rotation_sdram_client_arbiter.sv']
 commands=[]
 for prefix,top,files in [('core-','sdf_sdram_service',files[:-1]),('','sdf_sdram_service_probe',files)]:
  script='read_verilog -sv '+' '.join(str(ROOT/f) for f in files)+'\n'
  script+=f'synth_gowin -family gw2a -top {top} -nowidelut -json {d}/{prefix}mapped.json\ncheck -assert\n'
  (d/f'{prefix}synth.ys').write_text(script);cmd=['yosys','-Q','-s',str(d/f'{prefix}synth.ys')];commands.append(cmd)
  if not a.collect_only:
   code=run(cmd,ROOT,d/f'{prefix}synth.log',600)
   if code:raise SystemExit(f'{prefix}synthesis failed: {code}')
 pins=[('clk',4),('resetn',87),('scan_enable',73),('scan_in',74),('signature',75)]
 (d/'pins.cst').write_text(''.join(f'IO_LOC "{s}" {n};\nIO_PORT "{s}" IO_TYPE=LVCMOS33;\n'for s,n in pins))
 cmd=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst','--freq',str(1080/7),'--seed','1','--report',str(d/'pnr.json'),'--write',str(d/'routed.json')];commands.append(cmd)
 if not a.collect_only:
  code=run(cmd,ROOT,d/'pnr.log',600)
  (d/'pnr-exit.json').write_text(json.dumps(code)+'\n')
 (d/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 if not (d/'routed.json').exists() and not (d/'routed.json.gz').exists():
  log=(d/'pnr.log').read_text()
  result=dict(scope=__doc__,route_completed=False,service_logic_positions=None,
   pnr_exit=read(d/'pnr-exit.json') if (d/'pnr-exit.json').exists() else None,
   pnr_errors=[line for line in log.splitlines() if line.startswith('ERROR:')],
   source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files+['ci/sdf_sdram_service_evidence.py']},
   qualified_receiver=False)
  (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result,indent=2));return
 mapped=read(d/'mapped.json')['modules']['sdf_sdram_service_probe']['cells'];routed=read(d/'routed.json')['modules']['top']['cells']
 regs={k for k,v in mapped.items() if v['type'].startswith('DFF') and files[-1] in v.get('attributes',{}).get('src','')}
 assert 1652<=len(regs)<=2019, 'scan/signature registers outside expected range'
 harness_register_count=len(regs)
 harness={k:v for k,v in routed.items() if k in regs or k.startswith(('digest','observed_capture')) or k.removesuffix('_passthrough_lut$') in regs}
 service={k:v for k,v in routed.items() if k not in harness}
 hc,sc,tc=counts(harness),counts(service),counts(routed)
 assert ff(hc)==harness_register_count
 report=read(d/'pnr.json');u=report['utilization']
 assert logic(tc)==u['LUT4']['used']+u['ALU']['used']
 assert ff(tc)==u['DFF']['used']
 core=counts(read(d/'core-mapped.json')['modules']['sdf_sdram_service']['cells'])
 log=(d/'pnr.log').read_text();excess=logic(sc)-2231
 result=dict(scope=__doc__,variant="rotation" if a.rotation else "current",harness_register_count=harness_register_count,target_MHz=1080/7,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files+['ci/sdf_sdram_service_evidence.py']},
  yosys_version=subprocess.check_output(['yosys','-V'],text=True).strip(),
  pnr_version=subprocess.check_output(['nextpnr-himbaechel','--version'],stderr=subprocess.STDOUT,text=True).strip(),
  core_mapped_cells=core,core_mapped_logic=logic(core),core_mapped_FF=ff(core),
  routed_total_cells=tc,harness_cells=hc,service_cells=sc,
  routed_total_logic=logic(tc),harness_logic=logic(hc),service_logic_positions=logic(sc),service_FF=ff(sc),
  utilization=u,fmax=report['fmax'],route_completed='Routing complete.' in log,
  pnr_errors=[s for s in log.splitlines() if s.startswith('ERROR:')],
  reserve_logic=2231,reserve_excess=excess,old_mixed_budget_logic=20472,
  updated_mixed_logic_other_unimplemented_cost_zero=20472+excess,
  device_logic=20736,updated_mixed_excess=20472+excess-20736,
  classification='mapped src identifies scan/signature FF; routed digest*/observed_capture* logic and per-FF passthrough LUTs are harness. All other logic charged to service.',
  PHY_verified=False,whole_receiver_verified=False,external_IO_STA_verified=False)
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if 'cells' not in k and k not in ('source_sha256','utilization')},indent=2))
 for name in ('mapped.json','core-mapped.json','routed.json','synth.log','core-synth.log'):
  p=d/name
  if p.exists():Path(str(p)+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
if __name__=='__main__':main()
