"""Instrument pinned slice_valid returns; preserve every returned boolean."""
import hashlib,json,sys
from pathlib import Path
PIN='e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641'
LABELS=['alu_lut_same_site','ram_ff_block','ram_ff67_block','ram_lut_block','ram_alu_block','adjacent_alu_mode','ff_data_source','ff_type','ff_lsr','ff_clock','ff_enable','ff67_lsr','ff67_clock','ff67_enable']
def patch(source):
 start=source.index('bool GowinImpl::slice_valid(');end=source.index('\n/*',start)
 old=source[start:end];assert old.count('return false;')==len(LABELS)
 helper='''
#include <atomic>
#include <cstdio>
#include <cstdlib>
namespace {
struct TangPlacementCounters {
 std::atomic<unsigned long long> all[15]{};
 std::atomic<unsigned long long> target[15]{};
 ~TangPlacementCounters() {
  const char *labels[15]={LABELS};
  for(int i=0;i<15;++i) std::fprintf(stderr,"TANG_REJECT %s all=%llu target=%llu\\n",labels[i],all[i].load(),target[i].load());
 }
 bool result(int index,bool target_cell,bool value) {
  all[index].fetch_add(1,std::memory_order_relaxed);
  if(target_cell) target[index].fetch_add(1,std::memory_order_relaxed);
  return value;
 }
} tang_placement_counters;
}
'''.replace('LABELS',','.join('"'+x+'"'for x in LABELS+['accepted']))
 new=old
 marker='    const CellInfo *ramw = bels.at(BelZ::RAMW_Z);'
 new=new.replace(marker,marker+'\n    static const IdString target_id = ctx->id(std::getenv("TANG_DIAG_TARGET") ? std::getenv("TANG_DIAG_TARGET") : "dut.fft.in_valid_DFFRE_Q");\n    const bool target_cell = ff && ff->name == target_id;')
 for i in range(len(LABELS)):new=new.replace('return false;',f'return tang_placement_counters.result({i}, target_cell, false);',1)
 new=new.replace('return true;','return tang_placement_counters.result(14, target_cell, true);')
 # Inverse substitution checks the only function change is counting returns.
 inverse=new.replace(marker+'\n    static const IdString target_id = ctx->id(std::getenv("TANG_DIAG_TARGET") ? std::getenv("TANG_DIAG_TARGET") : "dut.fft.in_valid_DFFRE_Q");\n    const bool target_cell = ff && ff->name == target_id;',marker)
 for i in range(15):inverse=inverse.replace(f'return tang_placement_counters.result({i}, target_cell, '+('true'if i==14 else'false')+');','return '+('true'if i==14 else'false')+';')
 assert inverse==old
 # Includes must precede the source's namespaces.
 return helper+source[:start]+new+source[end:]
def main():
 root=Path(sys.argv[1]);p=root/'himbaechel/uarch/gowin/gowin.cc'
 original=p.read_text();expected=Path(__file__).resolve().parents[1]/'reports/placement-control-audit/gowin.cc'
 assert p.read_bytes()==expected.read_bytes(),'wrong base source'
 p.write_text(patch(original))
 print(json.dumps(dict(pin=PIN,original_sha256=hashlib.sha256(original.encode()).hexdigest(),instrumented_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),labels=LABELS,return_values_preserved=True)))
if __name__=='__main__':main()
