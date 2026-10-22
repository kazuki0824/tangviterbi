"""Necessary average stall limits; not sufficient deadlines or arrival bounds."""
from fractions import Fraction as F
import json


def evaluate(clock_mhz, s_steps_million):
    clock = F(str(clock_mhz)) * 1000000
    t = F(26208) * 1000000 / F('1039.5')
    s = F(str(s_steps_million)) * 1000000
    demand = t + s
    capacity = clock * F(127, 256)
    # A lost useful slot costs two clocks, in addition to scheduled maintenance.
    spare_slots = capacity - demand
    return {
        'clock_MHz': float(clock / 1000000),
        'demand_Msteps_s': float(demand / 1000000),
        'capacity_Msteps_s': float(capacity / 1000000),
        'necessary_average_condition_pass': spare_slots >= 0,
        'spare_steps_per_second': float(spare_slots),
        'maximum_additional_lost_clocks_per_second': float(2 * spare_slots),
        'maximum_additional_lost_clock_fraction': float(2 * spare_slots / clock),
        'T_mode3_symbol_clocks': float(clock * F('1039.5') / 1000000),
        'maximum_additional_lost_clocks_per_T_mode3_symbol': float(2 * spare_slots * F('1039.5') / 1000000),
        'minimum_clock_MHz_without_extra_stalls': float(demand * F(256,127) / 1000000),
        'whole_receiver_verified': False,
    }


def run():
    return {
        'scope': __doc__,
        'assumptions': ['Two clocks per K7 step; one maintenance slot in 128.',
                        'T maximum 26208 steps per 1039.5 us.',
                        'Binary S 50.505 Msteps/s; TC8 S 28.86 Msteps/s.',
                        'Fmax is a single routed probe result, not an operating guarantee.',
                        'Positive allowance does not prove bounded queues or per-symbol deadlines.',
                        'Negative allowance rejects sustained operation of this fixed core at that clock, even with ideal ingress.'],
        'conditions': {name: evaluate(clock, s)
                       for name, clock, s in [
                           ('target_binary', F(1080,7), F('50.505')),
                           ('target_tc8', F(1080,7), F('28.86')),
                           ('best_actual_fft_binary', F('146.22019958496094'), F('50.505')),
                           ('best_actual_fft_tc8', F('146.22019958496094'), F('28.86'))]},
    }

if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
