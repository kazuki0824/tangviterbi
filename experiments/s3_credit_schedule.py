"""Exact ingress-only schedule, not a complete RF/FEC/RS-RPC schedule.

RF stays native packed I10/Q10 at 40 MS/s (100 decimal MB/s).
Contract: 20 us SPI API/batch, .25 us SPI gap/page, 8 us LCD API/page,
80 MB/s payload wire, 3 us frame publication allowance, <=2054/90 us
consumer service/page. API costs and this downstream bound need silicon and
connected-receiver verification. SPI API before credit reservation is not
assumed to hold receiver credit; reservation timing is modeled explicitly.
"""
from fractions import Fraction as F
import argparse
import json
from pathlib import Path

PAGE=4096
PERIOD=F(4*PAGE,100)
SPI_PAGE=F(4106,80)+F(1,4)
LCD_PAGE=F(4112,80)
READ=F(2054,90)
PUBLICATION=F(3)
STATUS=F(42,80)+F(1,4)


def schedule(window=8,periods=256):
    # Shared sequence: LCD[0], Octal SCT[1,2], LCD[3]. The SPI
    # batch has contiguous sequence numbers, matching the actual SDK adapter.
    # Capture runs one four-page batch ahead; one scheduler reserves credits
    # before each submit. This is ingress only; no RS RPC is inserted here.
    finish=F(0);retire=[];snapshots=[];maximum_outstanding=0
    known_retired=0;next_sequence=0;first_failure=None;min_slack=None
    for batch in range(periods):
        base=batch*PERIOD
        # Reservation before the entire API cost is conservative. LCD3's
        # reservation occurs only after LCD0 DMA completion, not at entry.
        for when,count in ((base,1),(base,2),(base+8+LCD_PAGE,1)):
            used=next_sequence-known_retired
            maximum_outstanding=max(maximum_outstanding,used+count)
            if used+count>window and first_failure is None:
                first_failure=dict(batch=batch,time_us=float(when),used=used,
                                   request=count,window=window)
            next_sequence+=count
        ready=[base+8+LCD_PAGE,base+20+SPI_PAGE,
               base+20+2*SPI_PAGE,base+2*(8+LCD_PAGE)]
        for t in ready:
            finish=max(finish,t+PUBLICATION)+READ
            retire.append(finish)
        # Header reaches FPGA after 20 us API; toggle snapshot is delayed
        # a few core clocks. Snapshot at last-header edge is conservative:
        # an early frontier frees fewer slots and cannot grant extra credit.
        poll_start=base+20+2*SPI_PAGE+20
        snapshot=poll_start+F(10,80)
        known_retired=sum(t<=snapshot for t in retire)
        poll_finish=poll_start+STATUS
        slack=base+PERIOD-poll_finish
        min_slack=slack if min_slack is None else min(min_slack,slack)
        snapshots.append(known_retired)
    return dict(scope='ingress-only conditional schedule; RS RPC and downstream WCET absent',
        native_RF_MBps=100,page_bytes=PAGE,FPGA_pages=window,
        RF_pages_per_period=4,period_us=float(PERIOD),
        actual_SPI_contiguous_batch_pages=2,RF_octal_MBps=50,RF_LCD16_MBps=50,
        SPI_RF_service_us=float(20+2*SPI_PAGE),
        SPI_status_service_us=float(20+STATUS),LCD_RF_service_us=float(2*(8+LCD_PAGE)),
        octal_utilization=float((40+2*SPI_PAGE+STATUS)/PERIOD),
        LCD_utilization=float(2*(8+LCD_PAGE)/PERIOD),
        remaining_octal_interval_us=float(min_slack),
        consumer_service_contract_us=float(READ),publication_contract_us=float(PUBLICATION),
        tested_periods=periods,maximum_reserved_unretired_pages=maximum_outstanding,
        first_credit_failure=first_failure,conditional_ingress_contract_passes=first_failure is None and min_slack>=0,
        first_snapshot_frontiers=snapshots[:4],
        maximum_retirement_delay_from_period_start_us=float(max(t-(i//4)*PERIOD for i,t in enumerate(retire))),
        RS_RPC_scheduled=False,connected_receiver_WCET_verified=False,
        new_first_candidate_qualified=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps({'windows':[schedule(x) for x in (2,4,8)]},indent=2)+'\n')
