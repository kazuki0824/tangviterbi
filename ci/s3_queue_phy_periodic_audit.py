"""Locate periodic PHY work and its unresolved hardware-wait bound."""
import argparse,gzip,hashlib,io,json,os,re,subprocess,tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/s3-queue-owner'
def audit(tc):
 raw=gzip.decompress((OUT/'memory-sdk/s3_queue_memory_probe.elf.gz').read_bytes());elf=ELFFile(io.BytesIO(raw))
 symbols={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
 config=json.loads(gzip.decompress((OUT/'memory-sdk/sdkconfig.json.gz').read_bytes()))
 assert not config.get('ESP_PHY_DISABLE_PLL_TRACK') and config['ESP_PHY_PLL_TRACK_PERIOD_MS']==1000
 assert config['ESP_TIMER_TASK_AFFINITY']==0
 text={};env=dict(os.environ,XTENSA_GNU_CONFIG=str(tc/'lib/xtensa_esp32s3.so'))
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'queue-memory.elf';p.write_bytes(raw)
  for name in ('phy_track_pll_timer_callback','phy_param_track_tot','rfpll_cap_track','wait_hw_freq_busy','phy_get_romfunc_addr'):
   text[name]=subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'),'-d','--disassemble='+name,str(p)],env=env,text=True).replace(str(p),'queue-memory.elf')
  start=symbols['wait_hw_freq_busy']['st_value']
  # Whole-function linear disassembly starts in alignment padding before +12.
  # Re-decode at the observed backward branch target, not at that padding.
  target=int(re.search(r'bltz\s+a9, ([0-9a-f]+)',text['wait_hw_freq_busy'])[1],16)
  assert target==start+12
  loop=subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'),'-d','--start-address='+hex(target),'--stop-address='+hex(start+32),str(p)],env=env,text=True).replace(str(p),'queue-memory.elf')
 assert 'phy_param_track_tot>' in text['phy_track_pll_timer_callback']
 assert 'rfpll_cap_track>' in text['phy_param_track_tot'] and 'wait_hw_freq_busy>' in text['rfpll_cap_track']
 assert all(x in loop for x in ('movi.n','memw','l32i.n','bltz'))
 assert 'esp_rom_delay_us>' in loop and re.search(r'movi.n\s+a10, 50',loop)
 alltext='\n'.join(text.values())+'\nBRANCH-TARGET REDECODE\n'+loop
 (OUT/'phy-periodic.dis').write_text(alltext)
 result=dict(scope=__doc__,ELF_sha256=hashlib.sha256(raw).hexdigest(),period_us=config['ESP_PHY_PLL_TRACK_PERIOD_MS']*1000,nominal_releases_per_second=1,dispatch_core=0,
  callback='phy_track_pll_timer_callback',call_chain=['phy_track_pll_timer_callback','phy_param_track_tot','rfpll_cap_track','wait_hw_freq_busy'],
  conditional_path=True,hardware_wait=dict(register='0x6000e168',continue_when='bit31 remains set',loop_target=hex(target),software_iteration_limit=None,delay_after_observed_busy_us=50),
  costs_not_finalized=['Reachability and frequency of conditional PLL correction for raw RF configuration','busy-bit clearance bound','ROM function-table callees and PHY data state','timer IRQ/dispatch/context-switch and PHY mutex wait','interaction of PLL work with captured I/Q'],
  release_note='One nominal release per second; actual dispatch can be delayed/batched. No maximum callback burst inferred without a backlog bound.',
  all_SoC_costs_finalized=False,PLL_tracking_disabled=False,source_sha256={})
 paths=[Path(__file__),OUT/'memory-sdk/s3_queue_memory_probe.elf.gz',OUT/'memory-sdk/sdkconfig.json.gz',OUT/'allocation-sdk/sources.json',OUT/'phy-periodic.dis']
 result['source_sha256']={str(p.resolve().relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 (OUT/'phy-periodic.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);a=p.parse_args();print(json.dumps(audit(a.toolchain.resolve()),indent=2))
