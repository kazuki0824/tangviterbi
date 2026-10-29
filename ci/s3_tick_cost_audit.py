"""Tick handler body costs for no-unblock/no-switch receiving configuration."""
import argparse,json,hashlib,re,subprocess
from pathlib import Path
from ci.s3_sdk_cost_audit import Binary,ROOT
from ci.s3_receiver_cost_audit import bounded
from ci.s3_irq_entry_audit import trace

def audit(tc):
 b=Binary(tc);rom=Binary(tc,True);out={}
 sdk=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())
 paths=sdk['paths'];defaults=sdk['default_bindings'];bindings=sdk['call_bindings']
 def inclusive(key):
  t=paths[key];total=t['own_instructions']
  for call in t['calls']:
   child=bindings.get(key,{}).get(call['target'],defaults.get(call['target']));assert child
   total+=inclusive(child)+(2 if child.startswith('rom_') else 0)
  return total
 enter=inclusive('critical_enter');leave=inclusive('critical_exit');inisr=inclusive('in_isr')
 for name in ['__udivdi3','wdt_hal_feed','wdt_hal_write_protect_disable','wdt_hal_write_protect_enable','wdt_hal_config_stage']:
  out[name]=bounded(rom,name,blocked=[0xa6] if name=='wdt_hal_config_stage' else [])
  addr=int(b.symbols[name]['st_value']);dest=int(rom.symbols[name]['st_value'])
  dis=subprocess.check_output([rom.tool,'-d',f'--start-address={addr}',f'--stop-address={addr+6}',str(rom.path)],env=rom.env,text=True)
  assert re.search(r'l32r\s+a9,.*\('+format(dest,'x')+r' <',dis) and re.search(r'jx\s+a9',dis)
  out[name]['thunk_instructions']=2
 n=lambda name:out[name]['instructions']+out[name].get('thunk_instructions',0)
 for name in ['rtc_clk_bbpll_remove_consumer','rtc_clk_bbpll_add_consumer']:
  out[name]=bounded(b,name)
 out['usb_hook']=bounded(b,'usb_serial_jtag_sof_tick_hook',callees={0x38:n('rtc_clk_bbpll_remove_consumer'),0x44:n('rtc_clk_bbpll_add_consumer')})
 wcalls={0x2f:n('wdt_hal_write_protect_disable'),0x3e:n('wdt_hal_config_stage'),0x4d:n('wdt_hal_config_stage'),0x55:n('wdt_hal_feed'),0x5d:n('wdt_hal_write_protect_enable')}
 for core in (0,1):
  out[f'iwdt_{core}']=bounded(b,'tick_hook',forced={9:0x19 if core==0 else 0xb},callees=wcalls)
  # Two known types (IWDT and optional USB) only. Dispatcher own count covers
  # two occupied entries independent of positions; callbacks counted separately.
  count=2 if core==0 else 1
  dispatch=bounded(b,'esp_vApplicationTickHook',forced={0x18:dict(counter=[0x1f,0x16],edges=[0x1a]*count+[0x1d]*(8-count))},backedges={(0x1f,0x16):7},callees={0x1a:0})
  dispatch['instructions']+=n(f'iwdt_{core}')+(n('usb_hook') if core==0 else 0)
  dispatch['separate_callbacks']=[f'iwdt_{core}']+(['usb_hook'] if core==0 else [])
  out[f'dispatch_{core}']=dispatch
 out['kernel_0']=bounded(b,'xTaskIncrementTick',forced={9:0x1a,0x2d:0x30,0x42:0xbc,0xc1:0xc4},callees={0x1a:inisr,0x22:enter,0x2cd:inisr,0x2d3:leave})
 out['kernel_1']=bounded(b,'xTaskIncrementTickOtherCores',blocked=[0xb],callees={0x33:enter,0x52:leave})
 out['scheduler_same_task']=bounded(b,'vTaskSwitchContext',forced={0x24:0x35},blocked=[0x62,0x85,0x210],backedges={(0x20b,0x104):1},callees={3:inisr,0xc:enter,0x222:inisr,0x228:leave})
 out['setup_switch']=trace(b,'_frxt_setup_switch');out['setup_switch']['instructions']=out['setup_switch']['own_instructions']
 out['counter_no_retry']=bounded(b,'systimer_hal_get_counter_value',forced={0x1e:0x21,0x3d:0x40})
 for core in (0,1):
  out[f'handler_{core}']=bounded(b,'SysTickIsrHandler',forced={0x53:0x56,0x69:0x6b if core==0 else 0x74,0x77:0x7d,0x80:0x83,0x8b:0x8e},callees={0x33:n('counter_no_retry'),0x4b:n('__udivdi3'),0x60:n(f'dispatch_{core}'),0x6b:n('kernel_0'),0x74:n('kernel_1')})
  out[f'handler_switch_{core}']=bounded(b,'SysTickIsrHandler',forced={0x53:0x56,0x69:0x6b if core==0 else 0x74,0x77:0x7a,0x80:0x83,0x8b:0x8e},callees={0x33:n('counter_no_retry'),0x4b:n('__udivdi3'),0x60:n(f'dispatch_{core}'),0x6b:n('kernel_0'),0x74:n('kernel_1'),0x7a:n('setup_switch')})
 return dict(paths=out,hardware_wcet=False,conditions=['No delayed-task unblock, no scheduler suspension, no tick counter rollover. Both no-switch and switch-request paths are counted.','Scheduler bound: two same-priority pinned receiving tasks, no other runnable task above that priority, current core candidate found within two visits; valid stack canary. The launcher accepts caller-selected priorities; same priority is an estimate assumption, not an implemented fixed configuration. Under this assumption a switch can be requested even with different core affinities.','One elapsed tick and one alarm processing round per IRQ; source permits catch-up.','IWDT callback on both cores; USB SOF callback at most once on core0; no application tick callbacks. Registration is a receiving-configuration assumption, not proven by this link-only probe.','Critical locks uncontended. Counter capture ready on first check; high/low snapshot stable.'],excluded=['Level-1 entry/dispatch/exit and register-window exceptions','Kernel-lock contention','Counter readiness/stability retries and missed-alarm/catch-up rounds','Additional runnable-task/wake-up paths and callback registrations'],source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_receiver_cost_audit.py',ROOT/'ci/s3_irq_entry_audit.py',ROOT/'reports/s3-sdk-cost-ledger/results.json']})
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args();r=audit(a.toolchain.resolve());out=ROOT/'reports/s3-receiver-cost-ledger/tick.json';out.write_text(json.dumps(r,indent=2)+'\n');print({k:v['instructions'] for k,v in r['paths'].items()})
