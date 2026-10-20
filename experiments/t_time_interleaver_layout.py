"""Compact delay-line reference and direct-BL8 traffic audit, not receiver RTL.
ARIB STD-B31 v2.2-E1 3.11.1, Fig.3-23, Table3-12.
https://www.arib.or.jp/english/html/overview/doc/6-STD-B31v2_2-E1.pdf
The transmitter delay I*((5*i)%96) is complemented to 95*I.
Six bytes per carrier means six existing 8-bit soft values, not raw I/Q.
"""
from fractions import Fraction as F
import json

LENGTHS = {1: (0,4,8,16), 2: (0,2,4,8), 3: (0,1,2,4)}


def layout(mode, lengths):
    if mode not in LENGTHS or len(lengths) != 13 or any(i not in LENGTHS[mode] for i in lengths):
        raise ValueError('13 segment lengths must match the mode')
    carriers = 96 << (mode-1)
    offset = 0
    entries = []
    for segment, length in enumerate(lengths):
        for carrier in range(carriers):
            depth = length * (95 - (5*carrier)%96)
            entries.append((segment, carrier, offset, depth))
            offset += depth
    return entries, offset


def direct_address(entry, symbol):
    _, _, base, depth = entry
    return None if depth == 0 else base + symbol % depth


def audit(mode):
    length = max(LENGTHS[mode])
    entries, slots = layout(mode, [length]*13)
    active = sum(depth != 0 for _,_,_,depth in entries)
    period_us = F('259.875') * (1 << (mode-1))
    # Most optimistic direct implementation: one BL8 read and one BL8 write
    # per carrier, ignoring alignment crossings, activate/precharge/refresh.
    transactions = active * 2
    payload_bytes = active * 12
    bus_bytes = transactions * 32
    bus_clocks = transactions * 8
    period_clocks = period_us * F(1080,7)
    return dict(mode=mode,I=length,carriers=len(entries),nonzero_delay_carriers=active,
                compact_six_byte_storage=slots*6,
                rectangular_six_byte_storage=len(entries)*95*length*6,
                per_carrier_pointer_bits=sum((depth-1).bit_length() for *_,depth in entries if depth),
                direct_min_BL8_transactions_per_symbol=transactions,
                useful_read_write_MB_s=float(F(payload_bytes)/period_us),
                direct_min_bus_MB_s=float(F(bus_bytes)/period_us),
                direct_min_data_bus_clock_fraction=float(F(bus_clocks)/period_clocks),
                includes_commands_or_other_clients=False,
                compact_layout_RTL_implemented=False,
                whole_receiver_verified=False)


def run():
    return dict(scope=__doc__,conditions=[audit(mode) for mode in LENGTHS],
                warning='The direct transaction bound is conditional on one read and one write burst per carrier. Cross-carrier/temporal coalescing is not covered and may reduce traffic. It is not a lower bound on every implementation.')

if __name__=='__main__':
    print(json.dumps(run(),indent=2))
