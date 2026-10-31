"""Conditional native arrival windows linked to ordered SPI retirement.

Origin: physical initial-bank switch INDEX observation, not RF enable or accept.
Assume continuous unwrapped indices at cpp cycles/sample, source boundary
semantics, and physical clock-error guarantees used by native. No RF ABI proof.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from experiments.s3_raw_schedule_limits import native_constants
from experiments.s3_settling_limits import limits
from experiments.s3_spi_prefix_response import connect, integer
from experiments.s3_arena_limits import CHUNK
ROOT=Path(__file__).resolve().parents[1]


def windows(rate, counts, publication_offsets=None):
    if rate not in (16,40):raise ValueError('rate')
    if not counts:raise ValueError('empty arrival list')
    c=native_constants();cpp=240//rate
    text=(ROOT/'experiments/s3_native_capture.c').read_text()
    initial_guard=int(re.search(r's->unit\?END:(\d+)',text)[1])
    settle=int(re.search(r'\(uint64_t\)(\d+)\*s->cpp\+s->clock_error',text)[1])
    maximum=limits(rate)['max_accepted_bank_samples']
    if publication_offsets is not None and len(counts)!=len(publication_offsets):raise ValueError('one publication offset per bank')
    prior=0;rows=[];last_publication=0
    for k,count in enumerate(counts):
        integer(count,'count')
        if not c['THRESHOLD']-(initial_guard if k==0 else 0)<=count<=maximum:raise ValueError('native count range')
        lower=0 if k==0 else (prior+c['THRESHOLD']-1)*cpp+1
        # Initial e0-w0 <= initial_guard-1. Later switches satisfy
        # w_k <= e_(k-1)+THRESHOLD+LATE. Arbitrary sample phase is retained.
        switch_upper=0 if k==0 else (initial_guard+prior+c['THRESHOLD']+c['LATE'])*cpp-1
        h=None if publication_offsets is None else publication_offsets[k]
        publication=None
        if h is not None:
            integer(h,'physical publication offset')
            publication=max(last_publication,switch_upper+h)
            if publication<lower+settle*cpp:raise ValueError('contradictory publication upper bound')
            last_publication=publication
        rows.append(dict(bank=k,samples=count,accept_earliest=lower+settle*cpp,
                         switch_upper=switch_upper,publish_latest=publication))
        if k:prior+=count
    return rows


def wire_floor(transfer_bytes=CHUNK):
    if type(transfer_bytes) is not int or transfer_bytes not in (16384,32768):
        raise ValueError("supported transfer size required")
    text=(ROOT/'experiments/s3_spi_transport.c').read_text()
    command=int(re.search(r'\.command_bits = (\d+)',text)[1])
    address=int(re.search(r'\.address_bits = (\d+)',text)[1])
    frequency=int(re.search(r'\.clock_speed_hz = (\d+)',text)[1])
    assert 'SPI_TRANS_MULTILINE_CMD | SPI_TRANS_MULTILINE_ADDR' in text
    assert '.dummy_bits = 0' in text
    bits=transfer_bytes*8+command+address
    return [dict(transfer_bytes=transfer_bytes,lanes=lanes,header_bits=command+address,clock_hz=frequency,
                 serial_clock_count=bits//lanes,
                 wire_floor_cycles=(bits*240000000+lanes*frequency-1)//(lanes*frequency),
                 completion_upper_cycles=None,
                 is_lower_bound_from_queue_return=False) for lanes in (8,4)]


def evaluate(rate,counts,publication_offsets=None,scan_bound=None,completion_bounds=None,reap_bound=None,*,transfer_bytes=CHUNK):
    rows=windows(rate,counts,publication_offsets)
    if completion_bounds is not None:
        if len(completion_bounds)!=2:raise ValueError('8lane/4lane bounds required')
        for value in completion_bounds:integer(value,'completion bound')
        # queue_trans can start DMA before returning. Wire duration is not
        # automatically a lower bound on the remaining post-return W.
    result=dict(windows=rows,wire=wire_floor(transfer_bytes),receiver_adopted=False,hardware_RF_model_verified=False)
    if any(r['publish_latest'] is None for r in rows):
        return dict(result,status='unproved',missing=['verified physical publication offsets from switch_earliest'])
    banks=[{k:r[k] for k in ('samples','accept_earliest','publish_latest')} for r in rows]
    return dict(result,spi_response=connect(banks,transfer_bytes=transfer_bytes,scan_bound=scan_bound,completion_bounds=completion_bounds,reap_bound=reap_bound))


def report():
    return dict(scope=__doc__,conditions=[dict(rate=rate,result=evaluate(rate,[12288]*8)) for rate in (16,40)],
                caveat='nominal-count examples only; arbitrary accepted counts are parameters, not all arrival patterns proved',
                source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                    ('experiments/s3_native_capture.c','experiments/s3_spi_transport.c')},receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--config',type=Path);a=p.parse_args()
    data=report() if a.config is None else evaluate(**json.loads(a.config.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(data,indent=2)+'\n')
