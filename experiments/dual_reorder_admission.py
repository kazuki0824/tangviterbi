"""Reject specific full-symbol SDRAM staging plans, never all T implementations."""
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from dual_memory_contract import audit, groups, dense_traffic, S_CW_RATE
from dual_s_frame_contract import traffic


def report():
    rows=[]
    for mode in (1,2,3):
        r=1<<(mode-1)
        layers=[(3,4//r),(3,8//r),(7,16//r)]
        base=audit(mode,layers,'compact_group_masked')
        # Store a natural-order full symbol once, read it in grouped order once.
        # Ignore output reorder and assume perfectly packed BL8 / row hits:
        # this is an optimistic LOWER demand bound for this staging strategy.
        payload=13*96*r*6
        extra=Fraction(2*payload,1)/Fraction(2079*r,8)
        period=Fraction(2079*r,8)
        ring=sum(dense_traffic(delay,size) for delay,size in groups(mode,layers).items() if delay)
        demand=(6*4*(1<<(mode+10))+ring)/period + S_CW_RATE*traffic()['bytes_per_codeword']/1000000 + 10 + extra
        # The controller cannot service a BL8 in less than 12 clocks. Each
        # refresh must reserve tRP+tRFC=13 non-transfer clocks at least every
        # 1053 clocks. Ignore every other stall: an optimistic UPPER ceiling.
        upper=Fraction(135*32,12)*Fraction(1053-13,1053)
        rows.append(dict(mode=mode,layers=layers,symbol_LLR_bytes=payload,
                         base_MBps=base['total_bus_MBps'],input_staging_MBps=float(extra),
                         staged_total_MBps=float(demand),optimistic_refresh_ceiling_MBps=float(upper),
                         rejected=demand>upper,minimum_queue_growth_bytes_per_ms=float(max(0,demand-upper)*1000),
                         output_reorder_traffic_included=False))
    return dict(S=traffic(),input_staging_cases=rows,
                scope='Specific full-symbol off-chip input staging, actual S DMA, 135 MHz controller. Not exclusion of every grouping algorithm or partition.',
                full_receiver_adopted=False,
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               [Path(__file__),Path(__file__).with_name('dual_memory_contract.py'),Path(__file__).with_name('dual_s_frame_contract.py')]})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.write_text(json.dumps(report(),indent=2)+'\n')
