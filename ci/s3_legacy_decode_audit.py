#!/usr/bin/env python3
"""Reproduce the legacy benchmark's independent no-noise decode counterexample.

A failed receiver decode is an expected measurement here, not a reason to
rewrite/approve the production benchmark. The new decoder has separate tests.
"""
import hashlib
import json
from pathlib import Path
import random
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_s3_viterbi_decode import run

if __name__=='__main__':
    src=(ROOT/'rtl/viterbi_k7_32acs.sv').read_text()
    seed=0x171133;rng=random.Random(seed)
    bits=[rng.randrange(2) for _ in range(4096)]
    output=run(src,'viterbi_k7_32acs',bits)
    if len(output)<2304:raise SystemExit('insufficient decoder output')
    errors,offset=min((sum(output[i]!=bits[i+off] for i in range(512,2304)),off)
                      for off in range(-256,257))
    result={'source_sha256':hashlib.sha256(src.encode()).hexdigest(),'seed':seed,
        'input_bits':len(bits),'outputs':len(output),'noise':False,
        'compared_output_range':[512,2304],'alignment_search':[-256,256],
        'minimum_errors_over_alignment_search':errors,'best_offset':offset,
        'receiver_decoding_pass':errors==0}
    dest=ROOT/'build/s3-viterbi';dest.mkdir(parents=True,exist_ok=True)
    (dest/'legacy-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
