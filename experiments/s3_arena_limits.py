"""Exact output-capacity obligation at acceptance; not a SPI service proof."""
import argparse
import json
import hashlib
import re
from pathlib import Path

from experiments.s3_settling_limits import limits
ROOT=Path(__file__).resolve().parents[1]
HEADER=(ROOT/'experiments/s3_parallel_pack.h').read_text()
CHUNK=int(re.search(r'S3_PP_CHUNK=(\d+)',HEADER)[1])
ARENAS=int(re.search(r'S3_PP_SLOTS=(\d+)',HEADER)[1])

def capacity(samples, retired_chunks):
    if any(type(v) is not int or v<0 for v in (samples,retired_chunks)):
        raise ValueError('nonnegative integer counts required')
    reserved=5*(samples//2)
    if retired_chunks*CHUNK>reserved:raise ValueError('cannot retire unreserved bytes')
    required=max(0,(reserved-ARENAS*CHUNK+CHUNK-1)//CHUNK)
    return dict(samples=samples,reserved_bytes=reserved,carry_samples=samples%2,
                ordered_retired_chunks=retired_chunks,minimum_ordered_retired_chunks=required,
                occupied_bytes=reserved-retired_chunks*CHUNK,
                free_bytes=ARENAS*CHUNK-reserved+retired_chunks*CHUNK,
                capacity_condition_met=retired_chunks>=required,
                SPI_service_verified=False,receiver_adopted=False)

def report():
    return dict(scope=__doc__,chunk_bytes=CHUNK,arenas=ARENAS,
                source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                               ('experiments/s3_parallel_pack.h','experiments/s3_parallel_pack.c','experiments/s3_native_capture.c')},
                rows=[dict(max_banks=n,**capacity(n*limits(40)["max_accepted_bank_samples"],0)) for n in range(1,9)],
                required_evidence=['at each native acceptance the required ordered prefix has retired',
                                   'publication, submission, wire service, completion ISR and reap elapsed bounds',
                                   'actual port allocation, command overhead, shared-memory contention and out-of-order completions'],
                caveat='rows are capacity arithmetic, not verified native arrival times or SPI schedules',
                receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report(),indent=2)+'\n')
