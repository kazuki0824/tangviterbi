"""Elaborate fixed five-way round-robin priorities, without runtime modulo."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def source():
 s=(ROOT/'rtl/s3_psram_queue.sv').read_text()
 a=s.index(' reg found;reg [2:0] pick;integer k,candidate;')
 b=s.index(' integer p;',a)
 lines=[' reg found;reg [2:0] pick;', ' always @* begin',
        '  found=|full || read_pending;pick=0;', '  case(round_robin)']
 for start in range(5):
  lines.append(f"   3'd{start}:begin")
  for n in range(5):
   j=(start+n)%5;condition='read_pending' if j==4 else f'full[{j}]'
   lines.append(f"    {'if' if n==0 else 'else if'}({condition})pick=3'd{j};")
  lines.append('   end')
 lines+=['   default:begin found=0;pick=0;end','  endcase',' end','']
 return s[:a]+'\n'.join(lines)+s[b:]
if __name__=='__main__':print(source())
