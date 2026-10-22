"""Exact clock conversion, preserving prior *assumed* SDRAM timing bounds.

This does not qualify those bounds for the fitted SDRAM or prove PHY timing.
"""
import json
from fractions import Fraction as F
from math import ceil, floor


def audit():
    old = F(135)
    new = F(1080, 7)
    minimum = {'INIT_CYCLES': 27000, 'TRP': 3, 'TRCD': 3,
               'TRFC': 10, 'TWR': 3, 'TMRD': 3}
    converted = {k: ceil(v * new / old) for k, v in minimum.items()}
    converted['REFRESH_CYCLES'] = floor(1053 * new / old)
    assert all(F(converted[k], 1) / new >= F(v, 1) / old for k, v in minimum.items())
    assert F(converted['REFRESH_CYCLES'], 1) / new <= F(1053, 1) / old
    demand = F('75.717121')  # rounded published bound, Msteps/s
    capacity = new / 2 * F(127, 128)
    return dict(
        clock_MHz=float(new), old_clock_MHz=float(old),
        parameters=converted, CL=3, CL_speed_grade_verified=False,
        old_init_if_reused_us=float(27000/new),
        converted_init_us=float(converted['INIT_CYCLES']/new),
        old_TRFC_if_reused_ns=float(1000*10/new),
        converted_TRFC_ns=float(1000*converted['TRFC']/new),
        common_135_K7_capacity_Msteps_s=float(old/2*F(127,128)),
        common_154_K7_capacity_Msteps_s=float(capacity),
        published_K7_demand_Msteps_s=float(demand),
        common_154_K7_spare_Msteps_s=float(capacity-demand),
        confirmed_CDC_resource_savings=0,
        physical_memory_clock_verified=False, whole_receiver_verified=False,
        source='reports/20k-dual-s3-fft-sdram.md; reports/shared-k7-stream-results.md',
        qualification='Preserve old assumed durations only; CL and device timings need qualification. No bandwidth scaling from old traces.')


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
