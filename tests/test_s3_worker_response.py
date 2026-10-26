import itertools
import unittest
from experiments.s3_worker_response import fixed_point, worker, bank_response, report


def simulate(base,streams,horizon,carry=0):
    # Independent integer-time priority schedule: interrupts run before the
    # worker and arrivals may coincide with a prospective completion boundary.
    pending=carry;remaining=base
    for t in range(horizon):
        pending+=sum(cost for period,cost,phase in streams if t>=phase and (t-phase)%period==0)
        if pending:pending-=1
        else:remaining-=1
        if remaining==0:return t+1
    return None


class WorkerResponseTest(unittest.TestCase):
    def test_envelope_dominates_all_periodic_phases_with_carry(self):
        events=[dict(cost=1,period=5,burst=2),dict(cost=2,period=7,burst=2)]
        r=fixed_point(11,events,200)
        self.assertEqual(r['status'],'closed_within_declared_bounds')
        for phases in itertools.product(range(5),range(7)):
            for carry in range(4):
                actual=simulate(11,[(5,1,phases[0]),(7,2,phases[1])],200,carry)
                self.assertIsNotNone(actual)
                self.assertLessEqual(actual,r['response_cycles'])

    def test_no_arbitrary_iteration_cap_and_no_false_impossibility(self):
        r=fixed_point(3,[dict(cost=2,period=2,burst=1)],50)
        self.assertEqual(r['status'],'not_closed_by_deadline')
        self.assertIsNone(r['response_cycles'])
        self.assertGreater(r['last_iterate_cycles'],50)
        self.assertTrue(all(a<b for a,b in zip(r['trace'],r['trace'][1:])))

    def test_backlog_and_admission_reserve_are_both_charged(self):
        cfg=dict(release_delay=100,clock_error=5,ordinary_iteration=100,
                 sampled_slice=90,slice_bound=500,older_banks=0,slice_pairs=512,events=[])
        r=worker(40,cfg)
        self.assertEqual(r['max_slices_per_bank'],8)
        self.assertEqual(r['response_cycles'],4100)
        self.assertEqual(worker(40,dict(cfg,older_banks=2))['response_cycles'],12100)
        self.assertEqual(r['deadline_horizon_cycles'],109312-100-5-1)
        self.assertFalse(r['receiver_adopted']);self.assertFalse(r['WCET_proven'])
        self.assertEqual(worker(40,dict(cfg,slice_bound=94))['status'],'sampled_slice_not_certified')
        # Strict deadline: completion exactly at the sampled deadline is late.
        edge=109312-cfg['clock_error']-4100
        self.assertEqual(worker(40,dict(cfg,release_delay=edge))['status'],'not_closed_by_deadline')
        self.assertEqual(worker(40,dict(cfg,release_delay=edge-1))['margin_cycles'],0)

    def test_unknowns_cannot_become_zero_cost_evidence(self):
        r=report()
        self.assertEqual(len(r['rows']),12)
        self.assertTrue(all(row['result']['status']=='unproved' for row in r['rows']))
        self.assertFalse(r['actual_schedule_verified'])
        with self.assertRaises(ValueError):fixed_point(1,[dict(cost=1,period=0,burst=1)],5)
        with self.assertRaises(ValueError):worker(40,dict(unrecognized=1))

    def test_peer_done_can_miss_collect_and_reclaim_budget(self):
        c=dict(release_delay=100,clock_error=5,ordinary_iteration=100,
               sampled_slice=90,slice_bound=100,older_banks=0,slice_pairs=512,events=[])
        # Both DONE by 1000; coordinator can require up to two ordinary iterations (200) before release.
        self.assertEqual(bank_response(40,[c,c])['status'],'unproved')
        self.assertEqual(bank_response(40,[c,c],1200)['status'],'not_closed_by_reclaim_budget')
        r=bank_response(40,[c,c],1201)
        self.assertEqual(r['bank_released_from_switch_cycles'],1200)
        self.assertEqual(r['reclaim_margin_cycles'],0)
        self.assertFalse(r['receiver_adopted'])

if __name__=='__main__':unittest.main()
