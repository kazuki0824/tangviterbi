"""Periodic main/TMCC service check, explicitly NOT actual deinterleaver arrivals.

ITU-R BO.1408-1 Table 3: 48 slots, 39936 symbols/frame, 8 frames/superframe.
28.86 MBd and 2667 clocks/CW are existing repository inputs. TMCC is charged
one full 204-byte decoder service (a conservative work allocation, not proof
that the existing decoder correctly accepts RS(64,48)). All discrete event
phases immediately before/after ideal main arrivals are checked. Real DMA
bursts, decode-release jitter and output stalls remain separate contracts.
"""
from fractions import Fraction
import argparse
import json
from pathlib import Path

SYMBOLS = 39936*8
MAIN = [f*39936+192+s*828-4 for f in range(8) for s in range(1,49)]


def run(clock, tmcc_phase, periods=8, tmcc_first=False):
    # Integer time ticks: one symbol costs ratio.numerator, one clock costs
    # ratio.denominator. Exact event ordering without floating point ties.
    ratio=Fraction(str(clock))/Fraction('28.86')
    period=SYMBOLS*ratio.numerator; service=2667*ratio.denominator
    phase=int(tmcc_phase)*ratio.numerator
    events=[(s*ratio.numerator,1,'main') for s in MAIN]
    events.append((phase,0 if tmcc_first else 2,'tmcc')); events.sort()
    free=0;max_wait=0;max_waiting=0;max_response=0;ends=[];profiles=[]
    for k in range(periods):
        waits=[]
        for t,_,kind in events:
            arrival=k*period+t;wait=max(0,free-arrival)
            # Queue excludes the job in service, includes this arriving job
            # if it must wait. Exact ceiling of remaining work/service.
            waiting=(wait+service-1)//service if wait else 0
            free=max(free,arrival)+service
            waits.append(wait)
            if k>=2:
                max_wait=max(max_wait,wait);max_waiting=max(max_waiting,waiting)
                max_response=max(max_response,wait+service)
        profiles.append(waits);ends.append(max(0,free-(k+1)*period))
    tick_us=1/(28.86*ratio.numerator)
    return dict(clock_MHz=float(clock),TMCC_phase_symbols=tmcc_phase,TMCC_first_at_tie=tmcc_first,
        max_wait_us=max_wait*tick_us,max_response_us=max_response*tick_us,
        max_waiting_jobs=int(max_waiting),periodic_tail_repeats=profiles[-1]==profiles[-2],
        tail_backlog_ticks=ends[-2:],capacity_pass=385*service<=period,
        service_us=2667/float(clock),receiver_adopted=False)


def report():
    rows=[]
    # Non-preemptive workload changes piecewise between arrivals; both tie
    # orders bracket limits at the event boundaries for this ideal schedule.
    phases=[0,*MAIN,SYMBOLS-1]
    for clock in (90,93.1532,99):
        cases=[run(clock,p,tmcc_first=tie) for p in phases for tie in (False,True)]
        rows.append(dict(clock_MHz=clock,phase_cases=len(cases),
            worst_wait=max(cases,key=lambda r:r['max_wait_us']),
            worst_response_us=max(c['max_response_us'] for c in cases),
            max_waiting_jobs=max(c['max_waiting_jobs'] for c in cases),
            all_periodic_tails_repeat=all(c['periodic_tail_repeats'] for c in cases),
            all_capacity_pass=all(c['capacity_pass'] for c in cases)))
    return dict(scope=__doc__,source='https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf',
        symbol_rate_MBd=28.86,main_jobs_per_superframe=384,TMCC_jobs_per_superframe=1,
        cycles_per_job=2667,superframe_us=SYMBOLS/28.86,
        mean_required_MHz=385*2667/(SYMBOLS/28.86),scenarios=rows,
        real_deinterleaver_DMA_arrivals_verified=False,output_backpressure_included=False,
        actual_clock_generator_verified=False,receiver_adopted=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
 a.output.write_text(json.dumps(report(),indent=2)+'\n')
