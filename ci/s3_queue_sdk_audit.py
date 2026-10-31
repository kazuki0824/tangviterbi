"""Verify candidate SDK linkage, static metadata, IRAM and steady block code."""
import argparse,gzip,hashlib,io,json,os,re,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from experiments.s3_joint_runtime import ROOT
from ci.s3_pack_cfg_audit import graph,ROW

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args();tc=a.toolchain.resolve();env=dict(os.environ,XTENSA_GNU_CONFIG=str(tc/'lib/xtensa_esp32s3.so'))
 p=ROOT/'reports/s3-queue-study/sdk';raw=gzip.decompress((p/'s3_queue_probe.elf.gz').read_bytes());elf=ELFFile(io.BytesIO(raw));syms={s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
 path=ROOT/'build/queue-sdk.elf';path.parent.mkdir(exist_ok=True);path.write_bytes(raw);tool=str(tc/'bin/xtensa-esp-elf-objdump')
 rows={}
 for name in ('s3_raw_queue_submit','s3_raw_queue_reap','s3_pp_step_impl'):
  s=syms[name];start,size=int(s['st_value']),int(s['st_size']);section=elf.get_section(s['st_shndx']).name
  assert section=='.iram0.text',name
  dis=subprocess.check_output([tool,'-d','--disassemble='+name,str(path)],env=env,text=True)
  (p/(name+'.dis')).write_text(dis.replace(str(path),'queue-sdk.elf'))
  row={'address':hex(start),'bytes':size,'section':section}
  if name!='s3_pp_step_impl':
   nodes=graph(path,tool,env,start,size);memo={};active=set()
   def walk(pc):
    if pc in memo:return memo[pc]
    assert pc not in active;active.add(pc)
    edges=[int(d,16) for d in nodes[pc]['edges']]
    result=1+max((walk(d) for d in edges),default=0);active.remove(pc);memo[pc]=result;return result
   row['own_instruction_envelope_excluding_callees']=walk(start)
  else:
   code={int(m[1],16):(m[3],m[4],len(m[2])//2) for line in dis.splitlines() if (m:=ROW.match(line))}
   loops=[]
   for pc,(op,args,n) in code.items():
    if op!='loop':continue
    end=int(re.search(r'\b([0-9a-f]+)\s+<',args)[1],16)
    body=[v for k,v in code.items() if pc+n<=k<end]
    stores=sum(v[0] in ('s32i','s32i.n') and ', a1,' not in v[1] for v in body)
    if stores==5:loops.append({'instructions_per_eight_samples':len(body),'loads':sum(v[0] in ('l32i','l32i.n') for v in body),'stores':stores})
   assert len(loops)==1 and loops[0]=={'instructions_per_eight_samples':39,'loads':8,'stores':5}
   row.update(loops[0]);row['entry']=code[start][1]
  rows[name]=row
 config=json.loads(gzip.decompress((p/'sdkconfig.json.gz').read_bytes()))
 assert config['IDF_TARGET']=='esp32s3' and config['COMPILER_OPTIMIZATION_PERF']
 old=ELFFile(io.BytesIO(gzip.decompress((ROOT/'reports/s3-spi-running-guard/sdk-S/image/s3_raw_probe.elf.gz').read_bytes())));oldsyms={s.name:s for s in old.get_section_by_name('.symtab').iter_symbols()}
 old_metadata=sum(int(oldsyms[n]['st_size']) for n in ('raw_ports','raw_descriptors','raw_transfers'))
 metadata=int(syms['probe_queues']['st_size']);assert metadata==256 and old_metadata==224
 result={'symbols':rows,'queue_metadata_two_ports_bytes':metadata,'old_adapter_metadata_two_ports_bytes':old_metadata,'additional_static_adapter_metadata_bytes':metadata-old_metadata,'SDK_queue_allocations_included':False,'complete_receiver_fit_proven':False,'full_slice_cost_audited':False,'hardware_wcet':False,'elf_sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),p/'s3_queue_probe.elf.gz',p/'sdkconfig.json.gz',p/'provenance.json',ROOT/'experiments/s3_raw_queue.c',ROOT/'experiments/s3_raw_queue.h',ROOT/'experiments/s3_iq10_inline.h',ROOT/'experiments/s3_inline_pack.c']}}
 (p/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result['symbols']);print('metadata delta',metadata-old_metadata)
if __name__=='__main__':main()
