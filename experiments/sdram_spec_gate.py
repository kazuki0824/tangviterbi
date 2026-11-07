"""Primary-source clock limits and remaining PHY gates; no invented IO delays."""
from fractions import Fraction as F
import json


def audit():
    clock = F(1080,7)
    period = 1000/clock
    pfd = F(27,7)
    vco = clock*4
    refresh = F(64000,4096)
    old_refresh = F(1203,1)/clock
    assert clock < 166 and 3 <= pfd <= 500 and 500 <= vco <= 1250
    assert 3.90625 <= clock <= 625
    assert old_refresh < refresh
    return dict(
        sources=dict(device='https://cdn.gowinsemi.com.cn/DS226E.pdf',
                     controller='https://cdn.gowinsemi.com.cn/IPUG279E.pdf'),
        versions=dict(device='DS226-2.7E 2026-07-31',controller='IPUG279-1.4E 2025-05-09'),
        core_MHz=float(clock),period_ns=float(period),published_SDRAM_MHz=166,
        frequency_headroom_MHz=float(166-clock),frequency_gate=True,
        PLL=dict(IDIV_SEL=6,FBDIV_SEL=39,ODIV_SEL=4,PFD_MHz=float(pfd),
                 VCO_MHz=float(vco),arithmetic_ranges_pass=True,placement_pass=None),
        published_refresh_interval_us=float(refresh),
        retained_refresh_interval_us=float(old_refresh),
        published_access_time_ns=5.4,
        period_minus_published_access_time_ns=float(period-F('5.4')),
        access_time_warning='Subtraction is NOT setup slack: capture phase, clock skew, package delay, setup/hold and uncertainty still missing.',
        unqualified=['tRCD','tRP','tRFC','tWR','tMRD','tRAS','tRC','tRRD',
                     'CL3 detailed timing','DQ output hold/min delay','input setup/hold',
                     'package/IO delays','PLL phase and uncertainty','reset/lock release'],
        physical_timing_pass=None,whole_receiver_pass=None,
        decision='continue common-clock digital integration; do not claim PHY closure')

if __name__ == '__main__':
    print(json.dumps(audit(),indent=2))
