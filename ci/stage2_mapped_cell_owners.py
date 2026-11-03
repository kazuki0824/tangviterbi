"""Attribute mapped Gowin cells to exclusive instance prefixes.

This is a partial-design attribution tool. A flattened synthesis cell is
assigned to exactly one bucket; a missing connection to actual downstream
logic remains out of scope, and the buckets are not full-receiver owners.
"""
from collections import Counter
import re
PREFIXES=(
 ("candidate_fft_k7_core.k7","shared_k7"),
 ("candidate_fft_k7_core.memory","sdram_service"),
 ("candidate_fft_k7_core.fft","fft"),
 ("candidate_fft_k7_core.s_fifo","s_ingress_fifo"),
 ("candidate_fft_k7_core","shared_core_other"),
 ("candidate_input_fir","ingress_fir"),
 ("candidate_rs_ts","shared_rs_dual_ts")
)
RESOURCE_KEYS=("logic","ff","bsram","distributed_ram","dsp","other")
def category(cell_type):
 if re.fullmatch(r"LUT[1-4]|ALU",cell_type):return "logic"
 if cell_type.startswith("DFF"):return "ff"
 if cell_type in ("DPB","SDPB","DPX9B","SDPX9B"):return "bsram"
 if cell_type=="RAM16SDP4":return "distributed_ram"
 if cell_type=="MULT18X18":return "dsp"
 return "other"
def owner(name):
 return next((bucket for prefix,bucket in PREFIXES if name.startswith(prefix)),"top_level_or_unclassified")
def audit(cells):
 result={};totals=Counter()
 for name,cell in cells.items():
  bucket=owner(name);typ=category(cell["type"])
  if bucket not in result:result[bucket]=Counter()
  result[bucket][typ]+=1
  totals[typ]+=1
 per={bucket:{k:counts[k] for k in RESOURCE_KEYS} for bucket,counts in sorted(result.items())}
 summed={k:sum(v[k] for v in per.values()) for k in RESOURCE_KEYS}
 total={k:totals[k] for k in RESOURCE_KEYS}
 assert summed==total,"Per-owner resources must exactly sum to mapped cell counts"
 return {"owner_resources":per,"total_resources":total,"all_mapped_cells_attributed_once":True,
         "has_unclassified_cells":sum(per.get("top_level_or_unclassified",{}).values())>0,
         "full_receiver":False}
