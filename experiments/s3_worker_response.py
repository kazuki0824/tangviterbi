"""Conditional per-bank worker response envelope; no measured WCET inputs.

FIFO scan serves older sequence numbers first. The standalone packing API
allows two older banks. The single-owner native adapter keeps the current RF
write bank unowned, so successful native acceptance has at most one older bank. Charge their remaining work as full maximum banks, plus one
partial ordinary iteration. Extraordinary work uses explicit arrival envelopes
burst + floor(R/period); their bounds must cover carry-in and all interference.
"""
import argparse
import hashlib
import json
from pathlib import Path
from experiments.s3_settling_limits import limits
from experiments.s3_reclaim_limits import reclaim_limits
ROOT=Path(__file__).resolve().parents[1]


def integer(value,name,minimum=0):
    if type(value) is not int or value<minimum:raise ValueError(name)
    return value


def fixed_point(base,events,horizon):
    integer(base,'base');integer(horizon,'horizon')
    for e in events:
        integer(e['cost'],'cost');integer(e['period'],'period',1);integer(e['burst'],'burst',1)
    r=base;trace=[r]
    # No arbitrary solver timeout: the integer sequence either reaches a fixed
    # point or strictly increases past the deadline-derived finite horizon.
    while r<=horizon:
        new=base+sum((e['burst']+r//e['period'])*e['cost'] for e in events)
        if new==r:return dict(status='closed_within_declared_bounds',response_cycles=r,iterations=len(trace),trace=trace)
        if new<r:raise ValueError('nonmonotone envelope')
        r=new;trace.append(r)
    return dict(status='not_closed_by_deadline',response_cycles=None,last_iterate_cycles=r,iterations=len(trace),trace=trace)


def worker(rate,config):
    timing=limits(rate)
    required=('release_delay','clock_error','ordinary_iteration','sampled_slice',
              'slice_bound','older_banks','slice_pairs','events')
    if set(config)-set(required):raise ValueError('unknown worker input')
    missing=[k for k in required if config.get(k) is None]
    if missing:return dict(status='unproved',missing=missing,receiver_adopted=False)
    for k in required:
        if k!='events':integer(config[k],k,1 if k in ('ordinary_iteration','slice_bound','slice_pairs') else 0)
    if config['older_banks']>2 or config['slice_pairs']>8192:raise ValueError('bank/slice range')
    if config['sampled_slice']+config['clock_error']>config['slice_bound'] or config['clock_error']>=config['slice_bound']:
        return dict(status='sampled_slice_not_certified',receiver_adopted=False)
    pairs=(timing['max_accepted_bank_samples']+1)//2
    per_worker=(pairs+1)//2
    slices=(per_worker+config['slice_pairs']-1)//config['slice_pairs']
    # max(..., slice_bound) also covers the admission test before the final
    # slice; passing execution duration alone does not guarantee admission.
    charged=max(config['ordinary_iteration'],config['slice_bound'])
    base=config['ordinary_iteration']+(config['older_banks']+1)*slices*charged
    horizon=timing['packing_deadline_from_switch_earliest_cycles']-config['release_delay']-config['clock_error']-1
    if horizon<0:return dict(status='no_positive_deadline_budget',receiver_adopted=False)
    result=fixed_point(base,config['events'],horizon)
    result.update(rate_Msample_s=rate,max_slices_per_bank=slices,older_banks=config['older_banks'],
                  charged_slice_iteration_cycles=charged,base_cycles=base,deadline_horizon_cycles=horizon,
                  margin_cycles=None if result['response_cycles'] is None else horizon-result['response_cycles'],
                  scope='declared worker DONE response only; collect/reclaim/DMA/INDEX constraints remain separate',
                  actual_schedule_verified=False,WCET_proven=False,receiver_adopted=False)
    return result


def bank_response(rate,configs,reclaim_budget=None,*,native_reclaim_model=False):
    if len(configs)!=2:raise ValueError('two worker configurations required')
    if type(native_reclaim_model) is not bool:raise ValueError('native_reclaim_model')
    if native_reclaim_model and reclaim_budget is not None:
        raise ValueError('choose explicit budget or conditional native model')
    if native_reclaim_model and any(c.get('older_banks',0)>1 for c in configs):
        raise ValueError('native model excludes standalone three-owned-bank stress')
    workers=[worker(rate,c) for c in configs]
    result=dict(workers=workers,status='unproved',receiver_adopted=False,
                actual_schedule_verified=False,WCET_proven=False)
    if native_reclaim_model:
        result['conditional_native_reclaim_model']=reclaim_limits(rate)
        reclaim_budget=result['conditional_native_reclaim_model']['conservative_reclaim_strict_budget_cycles']
    result['reclaim_strict_budget_cycles']=reclaim_budget
    if any(w['status']!='closed_within_declared_bounds' for w in workers):return result
    done=max(c['release_delay']+w['response_cycles'] for c,w in zip(configs,workers))
    result['both_DONE_from_switch_cycles']=done
    # DONE does not release a bank. If peer publication misses collect, owner
    # may need the remainder of this iteration and the next collect. Charge two
    # complete ordinary iterations: a maximum whole-loop measurement alone
    # does not bound every rotated tail+head pair by one loop.
    if reclaim_budget is None:
        result['missing']=['verified reclaim budget from switch_earliest'];return result
    integer(reclaim_budget,'reclaim_budget',1)
    if done>=reclaim_budget:
        result['status']='not_closed_by_reclaim_budget';return result
    collect=fixed_point(2*configs[0]['ordinary_iteration'],configs[0]['events'],reclaim_budget-done-1)
    result['collect_delay']=collect
    if collect['response_cycles'] is None:
        result['status']='not_closed_by_reclaim_budget';return result
    result.update(status='closed_within_declared_bounds',
                  bank_released_from_switch_cycles=done+collect['response_cycles'],
                  reclaim_margin_cycles=reclaim_budget-done-collect['response_cycles']-1)
    return result


def report():
    unknown={k:None for k in ('release_delay','clock_error','ordinary_iteration','sampled_slice','slice_bound','events')}
    # Current allocation limit is 3 banks; 512 is a reference case, not a newly
    # adopted production default. Include all possible older-bank counts.
    rows=[dict(standard=standard,worker=w,older_banks=q,native_success_path=q<=1,standalone_API_stress=q==2,result=worker(rate,dict(unknown,older_banks=q,slice_pairs=512)))
          for standard,rate in (('T',16),('S',40)) for w in (0,1) for q in (0,1,2)]
    return dict(scope=__doc__,rows=rows,
        required_evidence=['ordinary iteration elapsed upper bound, including usual poll/collect/SPI/feed work on core0',
                           'sampled slice bound and actual calibrated E for each worker',
                           'extra preparation/settlement/watchdog/IRQ arrival and elapsed envelopes, without omissions or double counting',
                           'release delay relative to switch_earliest, not relative to accept',
                           'upper bounds include cross-core/shared-memory/DMA effects',
                           'q<=1 assumes only the current native adapter publishes banks and the RF write bank stays unowned'],
        limitations=['bank_response requires an independently verified reclaim budget; worker DONE alone does not release a bank',
                     'does not prove 4-arena output capacity or SPI retirement throughput',
                     'positive local margin is not receiver adoption',
                     'failure to close a pessimistic envelope is not proof of physical impossibility'],
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('experiments/s3_raw_tasks.c','experiments/s3_parallel_pack.c','experiments/s3_native_capture.c')},
        actual_schedule_verified=False,WCET_proven=False,receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--config',type=Path);p.add_argument('--rate',type=int,choices=(16,40))
    a=p.parse_args()
    if bool(a.config)!=bool(a.rate):p.error('--config and --rate must be supplied together')
    if a.config:
        config=json.loads(a.config.read_text())
        r=bank_response(a.rate,config['workers'],config.get('reclaim_budget'),native_reclaim_model=config.get('native_reclaim_model',False)) if 'workers' in config else worker(a.rate,config)
    else:r=report()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
