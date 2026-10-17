"""Overlay measured standalone FFT cost on every old ownership assignment.

Mixed measured/estimated budgets are NOT integrated synthesis or area lower
bounds. Preserve every ownership and all unknown full-receiver gates.
"""
import argparse
import copy
import itertools
import json
from pathlib import Path

from control_only_estimate import CAPS,KEYS,ORDER,gz_json,occupancy,read,rows

ROOT=Path(__file__).resolve().parents[1]
OLD_FFT=dict(zip(KEYS,(656,256,18,4)))
EVIDENCE=ROOT/"reports/shared-sdf-evidence"


def measured(board,kind):
    result=json.loads((EVIDENCE/f"{board}-{kind}"/"summary.json").read_text())
    use=result["routed_utilization"]
    return result,dict(zip(KEYS,(result["routed_logic_positions"],use["DFF"]["used"],
                                use["BSRAM"]["used"],use["MULT18X18"]["used"])))


def updated(board):
    result=[]
    for original in rows(board):
        variants=("hybrid","resident") if original["standard"]=="T" and original["owners"]["FFT"]=="FPGA" else ("unchanged",)
        for variant in variants:
            row=copy.deepcopy(original)
            row["ownership_id"]=row["id"]
            row["id"]+=":"+variant
            row["FFT_variant"]=variant
            if variant!="unchanged":
                proof,resources=measured(board,variant)
                row["stage_resources"]={k:row["stage_resources"][k]-OLD_FFT[k]+resources[k] for k in KEYS}
                row["stage_occupancy_percent"]=occupancy(row["stage_resources"],board)
                row["FFT_block_resources_with_benchmark_harness"]=resources
                row["FFT_block_timing_target_pass"]=proof["timing_target_pass"]
                row["FFT_external_memory_is_ideal"]=variant=="hybrid"
                row["selected_stage_required_MHz"]["FFT"]=13*(512/63)*32/33
                row["FFT_active_sample_required_MHz"]=13*(512/63)
                row["resource_scope"]="FFT measured with harness; all other stages retain incomplete inherited estimates"
                if not proof["timing_target_pass"]:
                    row["reasons"].append("FFT_COMPONENT_TARGET_NOT_PASSED")
                if any(row["stage_resources"][k]>c for k,c in zip(KEYS,CAPS[board])):
                    row["reasons"].append("REPLACEMENT_BUDGET_EXCEEDS_DEVICE")
            row["whole_resources"]=None
            row["whole_performance_pass"]=None
            row["formal_routes"]=[]
            row["adopted"]=False
            row["route_catalog"]=f'{row["forward_MBps"]:.9f}'
            result.append(row)
    return result


def run(board,output):
    output.mkdir(parents=True,exist_ok=True)
    assignments=updated(board)
    allowed=[r for r in assignments if r["command_only_return_compatible"]]
    ts=[r for r in allowed if r["standard"]=="T"]
    ss=[r for r in allowed if r["standard"]=="S"]
    pairs=[]
    for t,s in itertools.product(ts,ss):
        resources={k:(max(t["stage_resources"][k],s["stage_resources"][k]) if board=="9k" else
                      t["stage_resources"][k]+s["stage_resources"][k]) for k in KEYS}
        pairs.append(dict(T=t["id"],S=s["id"],stage_resources=resources,
                          stage_occupancy_percent=occupancy(resources,board),
                          aggregation="separate_images_max" if board=="9k" else "simultaneous_sum",
                          whole_resources=None,performance_pass=None,formal_routes=[],adopted=False))
    gz_json(output/"ownership-variants.json.gz",assignments)
    gz_json(output/"allowed-pairs.json.gz",pairs)
    table=["| ID | SoC prefix＋RF | CPU低/高 % | logic/FF/BSRAM/DSP（混合予算） | ↑ MB/s |",
           "|---|---|---:|---|---:|"]
    for r in allowed:
        prefix=", ".join(k for k in ORDER[r["standard"]] if r["owners"][k]=="SoC") or "RF only"
        cpu="/".join(f"{x:.3f}" for x in r["CPU_before_driver_percent"])
        resource="/".join(str(r["stage_resources"][k]) for k in KEYS)
        table.append(f'| {r["id"]} | {prefix} | {cpu} | {resource} | {r["forward_MBps"]:.6f} |')
    (output/"boundaries.md").write_text("\n".join(table)+"\n")
    summary=dict(board=board,ownership_variants=len(assignments),allowed_boundaries=len(allowed),
                 allowed_pairs=len(pairs),old_FFT_stage_replaced=OLD_FFT,
                 adoption_count=0,formal_route_count=0,full_receiver_measured=False,
                 link_types_and_rates_unchanged=True,
                 bandwidth_catalog=f"reports/control-only-{board}/bandwidth-catalog.json.gz",
                 warning=__doc__)
    if board=="20k":
        old=next(r for r in read("reports/20k-dual-s3/summary.json")["candidates"] if r["id"]=="B_tiled_shared_RS")
        old_fft=old["blocks"]["FFT"] if "FFT" in old["blocks"] else next(
            v for k,v in old["blocks"].items() if "fft" in k.lower())
        summary["old_shared_RS_B_replacement"]={variant:{k:old["resources"][k]-old_fft[k]+measured(board,variant)[1][k]
                                                        for k in KEYS} for variant in ("hybrid","resident")}
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--board",choices=CAPS,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.board,args.output),ensure_ascii=False))
