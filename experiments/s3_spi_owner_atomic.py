"""Conservative owner REQ CAS interference envelope, NOT a cycle bound.

Single device/owner, no acquire_bus or lifecycle changes, serialized ISRs.
Until the owner's OR succeeds, nobody sets REQ. ISR may clear an already
pending PEND, move the one existing REQ to PEND, then clear that PEND.
Any value-changing trace is a subsequence of C(P), S(P), C(R), C(P).
No-op writes can be erased: compare-value CAS does not fail on those alone.
This envelope intentionally includes unreachable initial/trace combinations.
"""
import argparse
import itertools
import json
from pathlib import Path

OPS = (("clear PEND", "and", ~2), ("set PEND", "or", 2),
       ("clear REQ", "and", ~1), ("clear PEND", "and", ~2))


def explore(initial, operations):
    memo = {}
    def visit(index, value, expected):
        key = (index, value, expected)
        if key in memo:
            return memo[key]
        choices = []
        if index < len(operations):
            label, op, mask = operations[index]
            new = value | mask if op == "or" else value & mask
            count, path = visit(index + 1, new, expected)
            choices.append((count, [label] + path))
        if expected is None:
            count, path = visit(index, value, value)
            choices.append((count, ["owner load"] + path))
        elif expected == value:
            choices.append((0, ["owner CAS success"]))
        else:
            # S32C1I returns the actual value, reused as next expected value.
            count, path = visit(index, value, value)
            choices.append((count + 1, ["owner CAS failure"] + path))
        result = max(choices, key=lambda item: item[0])
        memo[key] = result
        return result
    retries, witness = visit(0, initial, None)
    return dict(max_failed_attempts=retries, witness=witness, states=len(memo))


def report():
    rows = []
    for initial in range(4):
        for enabled in itertools.product((False, True), repeat=len(OPS)):
            ops = tuple(op for op, keep in zip(OPS, enabled) if keep)
            rows.append(dict(initial=initial, operations=[op[0] for op in ops],
                             **explore(initial, ops)))
    return dict(scope=__doc__, rows=rows,
                max_failed_attempts=max(row['max_failed_attempts'] for row in rows),
                max_total_attempts=1+max(row['max_failed_attempts'] for row in rows),
                bound_is_tight_for_runtime=False, elapsed_upper_cycles=None,
                receiver_adopted=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report(), indent=2) + '\n')
