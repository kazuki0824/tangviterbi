"""Compare selected subassemblies with and without CAD scan stimulus.

Neither top represents a complete T/S receiver. New no-scan top exports
virtual interfaces for FFT/SDRAM/K7; they are NOT board pins.
"""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/stage2-no-scan-compare"
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from ci.shared_receiver_fft_metadata_refresh_evidence import FILES
sys.path.insert(0,str(ROOT/"experiments"))
from s3_rs_isdb import source
from ci.stage2_mapped_cell_owners import audit as mapped_owners, diagnose_unclassified, diagnose_port_cone_ownership,owner as named_owner,source_owner,resolved_owner
from ci.stage2_net_provenance import label_from_named_outputs
rs=OUT/"rs_isdb_verified.sv"
rs.write_text(source(True,True))
common=list(dict.fromkeys([*(str(ROOT/p) for p in FILES),
 *(str(p) for p in sorted((ROOT/"rtl").glob("s3_*.sv"))),
 *(str(ROOT/"rtl"/(n+".sv")) for n in ["dual_s3_26pin_transport_candidate","dual_s3_26pin_iq_ingress_candidate","isdb_complex_fir33","dual_s3_ingress_to_fir_candidate","isdb_serial_ts_sink","shared_rs2_dual_ts"]),str(rs)]))
top_by_case={
 "with_scan":("experiments/stage2_cocurrent_selected_subassemblies_area_top.sv","stage2_cocurrent_selected_subassemblies_area_top"),
 "no_scan":("experiments/stage2_core_without_scan_selected_area_top.sv","stage2_core_without_scan_selected_area_top")
}
result={"scope":"two disconnected partial co-resident tops: compare scan fixture only","full_receiver":False,"io_constraints_verified":False,"no_scan_virtual_ports_are_board_pins":False,"cases":{}}
failed=False
for name,(file,top) in top_by_case.items():
 sources=common+[str(ROOT/file)]
 netlist=OUT/(name+"-mapped.json")
 script="read_verilog -sv "+" ".join(sources)+f"; hierarchy -check -top {top}; synth_gowin -family gw2a -top {top} -nowidelut -json {netlist}; check -assert"
 p=subprocess.run(["yosys","-Q","-p",script],cwd=ROOT/"reports/pr7-fft-archive",capture_output=True,text=True)
 (OUT/(name+"-yosys.log")).write_text(p.stdout+"\n"+p.stderr)
 d={"synthesis_exit":p.returncode,"top":top,"top_sha256":hashlib.sha256((ROOT/file).read_bytes()).hexdigest()}
 if p.returncode:
  failed=True;print(f"{name} synthesis failed:",(p.stdout+p.stderr)[-4000:])
 else:
  cells=json.loads(netlist.read_text())["modules"][top]["cells"]
  c=collections.Counter(cell["type"] for cell in cells.values())
  memory_sources=collections.Counter()
  memory_examples={}
  for cell_name,cell in cells.items():
   if cell["type"]=="RAM16SDP4":
    src=cell.get("attributes",{}).get("src","unattributed")
    src=str(src).split("|")[0]
    memory_sources[src]+=1
    memory_examples.setdefault(src,cell_name)
  d["distributed_ram_source_counts"]=dict(sorted(memory_sources.items()))
  d["distributed_ram_instance_example"]=memory_examples
  # Yosys RAM16SDP4 primitive source points to gowin/lutrams_map.v.
  # Use flattened hierarchy names to identify the actual RTL owner instead.
  owner_prefixes=(
   "candidate_fft_k7_core.k7", "candidate_fft_k7_core.memory",
   "candidate_fft_k7_core.fft", "candidate_fft_k7_core.s_fifo",
   "candidate_input_fir", "candidate_rs_ts"
  )
  owner_count=collections.Counter()
  examples={}
  for cell_name,cell in cells.items():
   if cell["type"]!="RAM16SDP4":continue
   owner=next((prefix for prefix in owner_prefixes if cell_name.startswith(prefix)),"other")
   owner_count[owner]+=1
   examples.setdefault(owner,cell_name)
  d["mapped_cell_ownership"]=mapped_owners(cells)
  pending={name:cell for name,cell in cells.items() if resolved_owner(name,cell)=="top_level_or_unclassified"}
  alias,summary=label_from_named_outputs(pending,json.loads(netlist.read_text())["modules"][top].get("netnames",{}),
   lambda name: None if named_owner(name)=="top_level_or_unclassified" else named_owner(name))
  d["named_output_net_provenance"]={"pending_before":len(pending),
   "candidate_owner_counts":dict(collections.Counter(x for x in alias.values() if x)),
   "still_unresolved":sum(v is None for v in alias.values()),
   "status":"candidate-only; named RTL output net, not verified actual receiver ownership"}
  d["unclassified_diagnostic"]=diagnose_unclassified(cells,json.loads(netlist.read_text())["modules"][top]["ports"])
  d["port_cone_candidate_diagnostic"]=diagnose_port_cone_ownership(
   cells,json.loads(netlist.read_text())["modules"][top]["ports"],(ROOT/file).read_text())
  d["distributed_ram_hierarchy_count"]=dict(sorted(owner_count.items()))
  d["distributed_ram_hierarchy_example"]=examples
  if sum(owner_count.values())!=c["RAM16SDP4"]:raise AssertionError("RAM ownership accounting mismatch")
  d.update(logic_lut_alu=sum(v for k,v in c.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),ff=sum(v for k,v in c.items() if k.startswith("DFF")),bsram=sum(c[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),distributed_ram=c["RAM16SDP4"],dsp=c["MULT18X18"])
  d["logic_with_ram_blockers"]=d["logic_lut_alu"]+4*d["distributed_ram"]
 result["cases"][name]=d
if not failed:
 result["difference_no_scan_minus_scan"]={k:result["cases"]["no_scan"][k]-result["cases"]["with_scan"][k] for k in ("logic_lut_alu","ff","bsram","distributed_ram","dsp","logic_with_ram_blockers")}
 result["no_scan_screen_over_20736"]=max(0,result["cases"]["no_scan"]["logic_with_ram_blockers"]-20736)
(OUT/"comparison.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
sys.exit(int(failed))
