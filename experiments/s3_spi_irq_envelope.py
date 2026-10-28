"""Finite abstract model and inductive certificate for raw SPI IRQ arrivals.

Implementation refinement is conditional: each ISR entry consumes a pending
cause from REQ publication or DMA completion, coalesced into one pending bit.
No spurious/shared IRQ, lifecycle change, or extra device is modeled.
"""
import argparse
from collections import deque
import json
from pathlib import Path
from experiments.s3_native_spi_windows import wire_floor

# State: outstanding, started, published, completed, pending IRQ cause,
#        owner has not yet finished the post-OR conditional bg_enable.
INITIAL = (0, 0, 0, 0, 0, 0)


def successors(state):
    active, started, published, completed, pending, deferred = state
    if not active:
        yield 'enqueue', (1, 0, 0, 0, pending, 0), 0, 0
    else:
        if not started:
            # Overapproximation: may start before owner publishes REQ.
            yield 'start', (1, 1, published, 0, pending, deferred), 0, 0
        if not published:
            # req_core's atomic OR and later conditional bg_enable are
            # distinct operations; IRQ/completion may intervene.
            yield 'publish', (1, started, 1, completed, pending, 1), 0, 0
        if deferred:
            for wake in (0, 1):
                yield 'finish request', (1, started, published, completed, pending | wake, 0), 0, 0
        if started and not completed:
            yield 'complete', (1, 1, published, 1, 1, deferred), 0, 1
        if published and completed and not deferred:
            # Actual result publication/owner return constraints are relaxed.
            yield 'reap', (0, 0, 0, 0, pending, 0), 0, 0
    if pending:
        yield 'IRQ entry', (active, started, published, completed, 0, deferred), 1, 0


def potential(state):
    _, _, published, completed, pending, deferred = state
    return pending + deferred - (published - completed)


def certificate():
    seen = {INITIAL}
    queue = deque([INITIAL])
    edges = []
    while queue:
        source = queue.popleft()
        for label, target, irq, done in successors(source):
            # Telescopes over any finite path, regardless of its length:
            # IRQ - 2*completion <= potential(start)-potential(end).
            slack = 2*done - irq - (potential(target)-potential(source))
            assert slack >= 0
            edges.append(dict(source=list(source), event=label, target=list(target),
                              irq=irq, completion=done, certificate_slack=slack))
            if target not in seen:
                seen.add(target)
                queue.append(target)
    low = min(map(potential, seen)); high = max(map(potential, seen))
    assert (low, high) == (-1, 2)
    return dict(states=[list(s) for s in sorted(seen)], edges=edges,
                potential_min=low, potential_max=high,
                all_path_inequality='IRQ_entries <= 2 * completions + 3',
                irq_entry_burst=high-low)


def worker_event(lanes, isr_cost, *, transfer_bytes=32768):
    if type(isr_cost) is not int or isr_cost <= 0:
        raise ValueError('verified positive per-ISR execution cost required')
    rows = {row['lanes']:row for row in wire_floor(transfer_bytes)}
    if lanes not in rows:
        raise ValueError('lanes')
    # completions <= 1 + floor(R/L); plus 1 ISR carry-in:
    # execution demand <= (6 + 2*floor(R/L))*C.
    return dict(cost=2*isr_cost, period=rows[lanes]['wire_floor_cycles'], burst=3)


def report():
    cert = certificate()
    return dict(scope=__doc__, certificate=cert,
                wire=wire_floor(),
                execution_demand_formula='(6 + 2 * floor(R / L)) * C per host',
                affinities=[dict(host_cores=list(a),
                    core0_hosts=[i for i,c in enumerate(a) if c==0],
                    core1_hosts=[i for i,c in enumerate(a) if c==1])
                    for a in ((0,0),(0,1),(1,0),(1,1))],
                isr_execution_cost_cycles=None, actual_schedule_verified=False,
                implementation_refinement_proven=False, receiver_adopted=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report(),indent=2)+'\n')
