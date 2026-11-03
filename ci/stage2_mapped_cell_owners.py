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
 unclassified_by_head=Counter()
 unclassified_source=Counter()
 unclassified_examples={}
 for name,cell in cells.items():
  bucket=owner(name);typ=category(cell["type"])
  if bucket not in result:result[bucket]=Counter()
  result[bucket][typ]+=1
  totals[typ]+=1
  if bucket=="top_level_or_unclassified":
   # Capture source evidence before deciding whether an unmatched cell
   # is an RTL block, technology I/O primitive, or anonymous mapping glue.
   head=name.split(".",2)[0]
   source=str(cell.get("attributes",{}).get("src","unknown")).split("|")[0]
   unclassified_by_head[(head,typ)]+=1
   unclassified_source[(source,typ)]+=1
   unclassified_examples.setdefault((head,typ),name)
 per={bucket:{k:counts[k] for k in RESOURCE_KEYS} for bucket,counts in sorted(result.items())}
 summed={k:sum(v[k] for v in per.values()) for k in RESOURCE_KEYS}
 total={k:totals[k] for k in RESOURCE_KEYS}
 assert summed==total,"Per-owner resources must exactly sum to mapped cell counts"
 return {"owner_resources":per,"total_resources":total,"all_mapped_cells_attributed_once":True,
         "has_unclassified_cells":sum(per.get("top_level_or_unclassified",{}).values())>0,
         "unclassified_heads":[{"prefix":k[0],"resource":k[1],"count":v,
                                "example":unclassified_examples[k]}
                               for k,v in unclassified_by_head.most_common(18)],
         "unclassified_sources":[{"src":k[0],"resource":k[1],"count":v}
                                  for k,v in unclassified_source.most_common(18)],
         "full_receiver":False}

def diagnose_unclassified(cells, ports):
 """Expose verifiable origins, do not force an attribution of ambiguous cells.

 A matched top-level port indicates an output cone, not sole RTL ownership:
 do not turn this diagnostic into ownership without examining the netlist.
 """
 port_names=sorted(ports, key=len, reverse=True)
 port_hits=Counter(); sources=Counter(); attribute_keys=Counter(); types=Counter()
 example_by_port={}; example_by_source={}; no_port_examples={}
 for name,cell in cells.items():
  if owner(name)!="top_level_or_unclassified":continue
  typ=category(cell["type"])
  attrs=cell.get("attributes",{})
  matched=next((p for p in port_names if name==p or name.startswith(p+"_") or name.startswith(p+"$")),None)
  label=matched or "<none>"
  port_hits[(label,typ)]+=1
  src=str(attrs.get("src","unknown")).split("|")[0]
  sources[(src,typ)]+=1
  attribute_keys.update(attrs.keys())
  types[cell["type"]]+=1
  example_by_port.setdefault((label,typ),{"cell":name,"src":src,"attributes":dict(attrs)})
  example_by_source.setdefault((src,typ),name)
  if matched is None and len(no_port_examples)<10:no_port_examples.setdefault(typ,name)
 return {
  "unclassified_total":sum(port_hits.values()),
  "port_cones":[{"port":k[0],"resource":k[1],"count":count,
                 "example":example_by_port[k]}
                for k,count in port_hits.most_common(48)],
  "no_matching_port":sum(v for k,v in port_hits.items() if k[0]=="<none>"),
  "source_summaries":[{"source":k[0],"resource":k[1],"count":v,
                        "example":example_by_source[k]}
                      for k,v in sources.most_common(28)],
  "attribute_keys":dict(attribute_keys),
  "cell_types":dict(types),
  "no_port_examples":no_port_examples,
 }
