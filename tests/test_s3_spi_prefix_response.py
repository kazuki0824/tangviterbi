import itertools
import unittest
from experiments.s3_spi_prefix_response import prefix_response, connect, submission_horizon


def simulate(publications, widths, period, phases):
    # Independent discrete owner scans; each port reaps then takes FIFO work.
    active=[None,None];taken=0;done=set();prefix=[]
    horizon=max(publications)+len(publications)*(max(widths)+2*period)+1
    for t in range(horizon):
        for port in range(2):
            if t%period!=phases[port]:continue
            if active[port] is not None and active[port][1]<=t:
                done.add(active[port][0]);active[port]=None
            if active[port] is None and taken<len(publications) and publications[taken]<=t:
                active[port]=(taken,t+widths[port]);taken+=1
        while len(prefix) in done:prefix.append(t)
        if len(prefix)==len(publications):return prefix
    raise AssertionError('simulation horizon insufficient')


class PrefixResponseTest(unittest.TestCase):
    def test_all_port_phases_asymmetry_and_publication_bursts(self):
        for period in range(1,5):
            for phases in itertools.product(range(period),repeat=2):
                for widths in itertools.product(range(1,5),repeat=2):
                    for pub in ([0]*8,[0,1,3,3,10,11,11,20]):
                        actual=simulate(pub,widths,period,phases)
                        bound=prefix_response(pub,period,list(widths),period)
                        self.assertTrue(all(a<=b for a,b in zip(actual,bound['ordered_retired_upper_cycles'])))

    def test_connect_and_strict_accept_boundary(self):
        # Four maximum banks: prefix chunk 0 must retire before fourth accept.
        banks=[dict(samples=14352,accept_earliest=a,publish_latest=p)
               for a,p in [(0,10),(10,20),(20,30),(50,60)]]
        r=connect(banks,scan_bound=10,completion_bounds=[20,10],reap_bound=10)
        self.assertEqual(r['obligations'][-1]['retirement_upper'],50)
        self.assertEqual(r['status'],'capacity_not_certified_by_bounds')
        banks[-1]['accept_earliest']=51
        r=connect(banks,scan_bound=10,completion_bounds=[20,10],reap_bound=10)
        self.assertEqual(r['obligations'][-1]['margin_cycles'],0)
        self.assertEqual(r['status'],'capacity_certified_within_declared_bounds')
        self.assertFalse(r['receiver_adopted'])
        self.assertEqual(connect(banks)['status'],'unproved')

    def test_asymmetric_opportunities_and_long_burst(self):
        for periods in itertools.product(range(1,9),repeat=2):
            for n in range(1,30):
                t=submission_horizon(n,periods)
                self.assertGreaterEqual(sum(t//p for p in periods),n)
                self.assertLess(sum((t-1)//p for p in periods),n)
        r=prefix_response([0]*128,0,[10,20],0)
        self.assertLess(r['ordered_retired_upper_cycles'][-1],r['pair_only_upper_cycles'][-1])
        actual=simulate([0]*128,[10,20],1,[0,0])
        r=prefix_response([0]*128,1,[10,20],1)
        self.assertTrue(all(a<=b for a,b in zip(actual,r['ordered_retired_upper_cycles'])))

    def test_missing_or_invalid_bounds(self):
        self.assertEqual(prefix_response([1])['status'],'unproved')
        with self.assertRaises(ValueError):prefix_response([2,1],1,[1,1],1)
        with self.assertRaises(ValueError):prefix_response([1],1,[1],1)
        with self.assertRaises(ValueError):prefix_response([1],-1,[1,1],1)

if __name__=='__main__':unittest.main()
