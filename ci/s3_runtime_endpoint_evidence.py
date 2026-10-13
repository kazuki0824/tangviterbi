#!/usr/bin/env python3
"""Connected RF/FFT/IQ/control endpoint plus isolated FEC load, NOT a receiver.

Synthetic IQ and independent FEC stimuli deliberately preserve their cells.
No FIR/sync/equalizer/interleavers, real FEC coupling, TS or external IO STA.
Preserve capacity failures, timing failures and unknown timeouts separately.
"""
import argparse,gzip,hashlib,json,subprocess
from pathlib import Path
from s3_logic_site_audit import audit
from s3_direct_stream_evidence import ROOT,top as old_top,generate,tc_source,rs_source,syndrome_source

def top(mode):
 fec=old_top(mode).split('wire vr,vv' if mode=='T' else 'wire mr,mv',1)[1]
 fec=('wire vr,vv' if mode=='T' else 'wire mr,mv')+fec
 return '''module top(input wire clk27,resetn,
 input wire spi2_sclk,spi2_cs_n,input wire[7:0]spi2_d,
 input wire spi3_sclk,spi3_cs_n,inout wire[3:0]spi3_d,output wire activity,
 output wire[2:0]RF_credit_gray,output wire[1:0]IQ_publish_gray);
 wire clk,unused,rst;s3_psram_clock clocks(clk27,resetn,clk,unused,rst);
 wire spi2_clock,spi3_clock;
 BUFG global2(.I(spi2_sclk),.O(spi2_clock));BUFG global3(.I(spi3_sclk),.O(spi3_clock));
 wire v,last,fault,fftv,fftl,en,ibr,iwr;wire[31:0]data,offset,fftd,ffto;wire[15:0]ep;
 reg[31:0]checksum,iqoff;reg[9:0]iqidx;reg loading;reg[63:0]lfsr;
 wire ib='''+('!loading&&en' if mode=='T' else "1'b0")+''';
 wire iw='''+('loading&&en' if mode=='T' else "1'b0")+''';
 s3_spi_runtime_endpoint #(.IMAGE_ID('''+('0' if mode=='T' else '1')+''')) bridge(clk,rst,1'b1,1'b1,1'b0,
 spi2_clock,spi2_cs_n,spi2_d,spi3_clock,spi3_cs_n,spi3_d,
 v,1'b1,data,offset,last,fftv,1'b1,fftd,ffto,fftl,
 ib,ibr,iqoff,iw,iwr,lfsr[31:0],en,fault,ep,RF_credit_gray,IQ_publish_gray);
 always @(posedge clk or negedge rst)
 if(!rst)begin checksum<=0;lfsr<=64'hc14fb4391aceb00c;iqoff<=0;iqidx<=0;loading<=0;end
 else begin
  if(v)checksum<={checksum[30:0],checksum[31]}^data;
  if(fftv)checksum<=checksum^fftd;
  lfsr<={lfsr[62:0],lfsr[63]^lfsr[62]^lfsr[60]^lfsr[59]};
  if(ib&&ibr)begin loading<=1;iqidx<=0;end
  if(iw&&iwr)begin iqidx<=iqidx+1'b1;if(iqidx==1023)begin loading<=0;iqoff<=iqoff+4096;end end
 end
'''+fec.replace('checksum,offset,last,fault','checksum,offset,last,fault,ffto,fftl,en,ep')

def measure(mode,output,timeout,seed,placer='heap'):
 b=ROOT/'build'/('s3-runtime-endpoint-'+mode+(f'-{placer}-seed{seed}' if placer!='heap' or seed!=1 else ''));b.mkdir(parents=True,exist_ok=True)
 mhz=99 if mode=='S-all-RS' else 90
 (b/'top.sv').write_text(top(mode))
 (b/'clock.sv').write_text((ROOT/'rtl/s3_psram_clock.sv').read_text().replace('.FBDIV_SEL(10)',f'.FBDIV_SEL({10 if mhz==99 else 9})'))
 (b/'vit.sv').write_text(generate('modulo13-pipe') if mode=='T' else tc_source(True,True,32,True))
 (b/'fec.sv').write_text(rs_source(True,True) if mode in ('T','S-all-RS') else syndrome_source())
 sources=[ROOT/'rtl'/(n+'.sv') for n in ('s3_async_fifo','s3_spi_rx','s3_page_guard','s3_pooled_page_store','s3_spi_control','s3_spi_iq_pingpong','s3_rf_credit','s3_spi_runtime_endpoint')]
 sources += [b/n for n in ('top.sv','clock.sv','vit.sv','fec.sv')]
 if mode!='T':sources+=[ROOT/'rtl/s3_tc8psk_metric_folded.sv']
 if mode=='S':sources+=[ROOT/'rtl'/(n+'.sv') for n in ('s3_rs_chien','s3_rs_forney')]
 frozen_sources={str(p.relative_to(ROOT)):p.read_bytes() for p in sources}
 (b/'pnr.json').unlink(missing_ok=True)
 (b/'synth.ys').write_text('read_verilog -sv '+' '.join(map(str,sources))+'\nsynth_gowin -top top -family gw1n -nowidelut -json '+str(b/'design.json')+'\ncheck -assert\n')
 with (b/'synth.log').open('w') as log:subprocess.run(['yosys','-Q','-T','-s',str(b/'synth.ys')],stdout=log,stderr=subprocess.STDOUT,check=True)
 m=json.loads((b/'design.json').read_text())['modules']['top']
 def alias(bits):return min((n for n,v in m['netnames'].items() if v['bits']==bits and not n.startswith('$')),key=len)
 clocks=[]
 for c in m['cells'].values():
  if c['type']=='rPLL':clocks.append((alias(c['connections']['CLKOUT']),mhz))
  if c['type']=='IBUF' and c['connections']['I']==m['ports']['clk27']['bits']:clocks.append((alias(c['connections']['O']),27))
  if c['type']=='BUFG':clocks.append((alias(c['connections']['O']),80))
 (b/'clocks.py').write_text(''.join(f'ctx.addClock({n!r},{v})\n' for n,v in clocks))
 pins=(ROOT/'experiments/s3_spi_rx_benchmark.cst').read_text().replace('"clk"','"clk27"')
 for n,p in [('RF_credit_gray[0]',55),('RF_credit_gray[1]',56),('RF_credit_gray[2]',57),('IQ_publish_gray[0]',37),('IQ_publish_gray[1]',38)]:pins+=f'IO_LOC "{n}" {p};\nIO_PORT "{n}" IO_TYPE=LVCMOS33 PULL_MODE=NONE;\n'
 (b/'pins.cst').write_text(pins)
 base=['nextpnr-himbaechel','--json',str(b/'design.json'),'--device','GW1NR-LV9QN88PC6/I5','--vopt','family=GW1N-9C','--vopt','cst='+str(b/'pins.cst'),'--pre-pack',str(b/'clocks.py')]
 with (b/'pack.log').open('w') as log:subprocess.run(base+['--pack-only','--write',str(b/'packed.json')],stdout=log,stderr=subprocess.STDOUT,check=True)
 sites=audit(b/'packed.json')
 if sites['mapped_netlist_ruled_out']:rc=126;(b/'pnr.log').write_text('Mapped netlist exceeds 8640 sites. No placement attempted.\n')
 else:
  with (b/'pnr.log').open('w') as log:
   try:rc=subprocess.run(base+['--freq',str(mhz),'--seed',str(seed),'--placer',placer,'--report',str(b/'pnr.json')],stdout=log,stderr=subprocess.STDOUT,timeout=timeout).returncode
   except subprocess.TimeoutExpired:rc=124;log.write('\nWall-time limit: timing/fit unknown.\n')
 p=json.loads((b/'pnr.json').read_text()) if (b/'pnr.json').exists() else {}
 r=dict(mode=mode,seed=seed,placer=placer,pnr_wall_limit_s=timeout,target_core_MHz=mhz,CAD_exit_code=rc,logic_site_audit=sites,clock_constraints=clocks,fmax=p.get('fmax'),utilization=p.get('utilization'),
  source_sha256={n:hashlib.sha256(data).hexdigest() for n,data in frozen_sources.items()},scope=__doc__,receiver_adopted=False,whole_receiver_resources_verified=False,external_IO_STA_verified=False,
  tool_versions={n:subprocess.check_output([n,'--version'],text=True,stderr=subprocess.STDOUT).strip() for n in ('yosys','nextpnr-himbaechel')})
 d=output/mode/f'seed{seed}';d.mkdir(parents=True,exist_ok=True)
 (d/'inputs').mkdir(exist_ok=True)
 for n,data in frozen_sources.items():(d/'inputs'/Path(n).name).write_bytes(data)
 for n in ('top.sv','clock.sv','vit.sv','fec.sv','synth.ys','pins.cst','clocks.py'):(d/n).write_bytes((b/n).read_bytes())
 for n in ('synth.log','pack.log','pnr.log'):(d/(n+'.gz')).write_bytes(gzip.compress((b/n).read_bytes(),mtime=0))
 (d/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(dict(mode=mode,sites=sites['minimum_required_logic_sites'],CAD_exit_code=rc,fmax=r['fmax'],utilization=r['utilization'])))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=('T','S','S-all-RS'),required=True);p.add_argument('--output',type=Path,default=ROOT/'reports/s3-runtime-endpoint-evidence');p.add_argument('--pnr-timeout',type=int,default=180);p.add_argument('--seed',type=int,default=1);p.add_argument('--placer',choices=('heap','sa','static'),default='heap');a=p.parse_args();measure(a.mode,a.output,a.pnr_timeout,a.seed,a.placer)
