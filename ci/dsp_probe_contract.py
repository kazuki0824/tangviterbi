"""Verify unused-input removal and preserve the unchanged receiver core evidence."""
import collections,gzip,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):
 p=ROOT/p
 return json.loads(p.read_bytes()if p.exists()else gzip.decompress(Path(str(p)+'.gz').read_bytes()))
def main():
 base='reports/shared-receiver-fft-tile-heldearly-pack/core-mapped.json'
 m=read(base)['modules']['shared_receiver_fft_tile'];cells=m['cells']
 users=collections.Counter(b for c in cells.values()for name,bits in c['connections'].items()if c.get('port_directions',{}).get(name)=='input'for b in bits)
 ibufs={c['connections']['I'][0]:c['connections']['O'][0]for c in cells.values()if c['type']=='IBUF'}
 removed={'bg_valid':[2],'bg_write':[2],'bg_address':list(range(42,63)),'bg_data':list(range(512,768)),'bg_dqm':list(range(64,96)),'bg_rsp_ready':[2]}
 checks={}
 for name,ids in removed.items():
  counts=[users[ibufs[m['ports'][name]['bits'][i]]]for i in ids]
  assert not any(counts),(name,counts)
  checks[name]=dict(bits=ids,total_internal_consumers=sum(counts))
 assert sum(len(x)for x in removed.values())==312
 old=(ROOT/'experiments/shared_receiver_fft_tile_probe.sv').read_text()
 refs=[]
 for hi,lo in re.findall(r'stimulus\[(\d+):(\d+)\]',old[old.index(' shared_receiver_fft_tile dut'):]):refs.extend(range(int(lo),int(hi)+1))
 for bit in re.findall(r'stimulus\[(\d+)\]',old[old.index(' shared_receiver_fft_tile dut'):]):refs.append(int(bit))
 assert not set(range(36,59))&set(refs)
 unchanged={}
 for name in ['dsp-probe','compact-dsp-probe','compact-bram-probe']:
  p=f'reports/shared-receiver-fft-tile-{name}-pack/core-mapped.json'
  same=read(p)==read(base);assert same,p;unchanged[name]=same
 # Verify the compact scan expansion is a bijection onto the retained inputs.
 s=(ROOT/'experiments/shared_receiver_fft_tile_compact_dsp_probe.sv').read_text()
 pairs=[tuple(map(int,x))for x in re.findall(r'assign stimulus\[(\d+)\]=scan_state\[(\d+)\];',s)]
 excluded=set(range(36,59))|{61,65,1305}|set(range(109,130))|set(range(663,919))|set(range(1239,1271))
 assert [i for i,j in pairs]==[i for i in range(1632)if i not in excluded]
 assert [j for i,j in pairs]==list(range(1297))
 bram=(ROOT/'experiments/shared_receiver_fft_tile_compact_bram_probe.sv').read_text()
 assert s.split(' wire[383:0]observed;')[0].split(' wire[1631:0]stimulus;')[1]==bram.split(' wire[383:0]observed;')[0].split(' wire[1631:0]stimulus;')[1]
 files=['experiments/shared_receiver_fft_tile_compact_bram_probe.sv','tests/test_bram_observation_probe.py','experiments/shared_receiver_fft_tile_probe.sv','experiments/shared_receiver_fft_tile_dsp_probe.sv','experiments/shared_receiver_fft_tile_compact_dsp_probe.sv','tests/test_dsp_scan_probe.py','tests/test_compact_dsp_scan_probe.py','ci/dsp_probe_contract.py']
 result=dict(unused_receiver_input_bits=312,unconnected_scan_bits=23,retained_independent_input_bits=1297,unused_input_checks=checks,standalone_core_netlists_identical=unchanged,compact_mapping_bijective=True,BRAM_variant_scan_logic_identical=True,
  DSP_contract=dict(source='https://cdn.gowinsemi.com.cn/UG287J.pdf',document='UG287-1.4J',section='4.1 ALU54',mode=2,A='scan next word',B=0,CASI=0,OUT_REG=1,AREG=0,BREG=0,simulation='Restricted model derived from documentation; not vendor model or hardware validation'),
  source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in files})
 (ROOT/'reports/dsp-probe-contract.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['source_sha256','unused_input_checks','DSP_contract']}))
if __name__=='__main__':main()
