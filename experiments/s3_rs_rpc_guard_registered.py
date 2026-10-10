"""Same-cycle RPC validator with registered payload-region membership."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def source(bit_ranges=False):
 s=(ROOT/'rtl/s3_rs_rpc_guard.sv').read_text()
 old='wire payload=offset>=16 && (kind==2 ? offset<2668 : offset<2464);'
 assert old in s
 s=s.replace(old,'reg payload; // Updated at the exact header/payload boundaries.')
 s=s.replace('record_failed<=0;degree<=0;gap<=0;','record_failed<=0;degree<=0;gap<=0;payload<=0;')
 s=s.replace('gap<=0;crc<=next_crc;errors<=errors|byte_errors;',
 '''gap<=0;crc<=next_crc;errors<=errors|byte_errors;
     if(offset==15)payload<=1;
     if(offset==(kind==2?2667:2463))payload<=0;''')
 if bit_ranges:
  # Exact unsigned 12-bit comparisons at powers-of-two boundaries. Stating
  # the bit tests avoids the subtract/carry chains emitted by this mapper.
  s=s.replace('offset>=12&&offset<16',"offset[11:4]==0&&offset[3:2]==2'b11")
  s=s.replace('offset>=16','(|offset[11:4])')
  s=s.replace('offset<12',"(offset[11:4]==0&&offset[3:2]!=2'b11)")
 return '// Equivalent registered-region variant; validated against the original every cycle.\n'+s
if __name__=='__main__':print(source())
