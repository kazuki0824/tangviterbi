"""Conservatively infer cell owner from directly named output nets."""
from collections import Counter,defaultdict
def label_from_named_outputs(cells,netnames,name_owner):
 bitowner=defaultdict(set)
 for name,net in netnames.items():
  x=name_owner(name)
  if x is not None:
   for bit in net.get("bits",[]):
    if isinstance(bit,int):bitowner[bit].add(x)
 results={};stats=Counter()
 for name,cell in cells.items():
  labels=set()
  for pin,direction in cell.get("port_directions",{}).items():
   if direction!="output":continue
   for bit in cell.get("connections",{}).get(pin,[]):
    if isinstance(bit,int):labels.update(bitowner.get(bit,()))
  found=next(iter(labels)) if len(labels)==1 else None
  results[name]=found
  stats[("unique_output_net",found) if found else ("ambiguous_or_unnamed",None)]+=1
 return results,stats
