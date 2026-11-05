import unittest
from experiments.s3_task_gap_limits import report, OPERATIONS

class TaskGapTest(unittest.TestCase):
    def test_unknown_is_not_free_or_passed(self):
        r=report()
        for row in r['rows']:
            self.assertFalse(row['all_local_constraints_within_declared_bounds'])
            self.assertTrue(all(g['sum_upper_cycles'] is None and g['verdict']=='unproved' for g in row['gaps']))

    def test_single_reset_bound_exceeds_S_budget_even_if_rare(self):
        b={op:1 for op in OPERATIONS};b.update({'poll_edges_'+str(i):1 for i in range(7)})
        b['feed_and_loop']=12000
        t,s=report(b)['rows']
        self.assertTrue(t['all_local_constraints_within_declared_bounds'])
        self.assertEqual(s['gaps'][-1]['verdict'],'bound_exceeds_budget')
        self.assertEqual(s['gaps'][-1]['slack_cycles'],-1)
        self.assertTrue(all(g['verdict']=='within_declared_bounds' for g in s['gaps'][:-1]))
        # Even without the unknown edge, one declared upper bound can already exceed the budget.
        self.assertEqual(report({'worker0_slice':12001})['rows'][1]['gaps'][0]['verdict'],'bound_exceeds_budget')

    def test_exact_limit_includes_poll_tails_and_does_not_prove_receiver(self):
        b={op:11999 for op in OPERATIONS};b.update({'poll_edges_'+str(i):1 for i in range(7)})
        r=report(b)
        self.assertTrue(r['rows'][1]['all_local_constraints_within_declared_bounds'])
        self.assertFalse(r['receiver_adopted']);self.assertFalse(r['WCET_proven'])
        for b in ({'unknown':1},{'worker0_slice':-1},{'worker0_slice':1.0},{'worker0_slice':True}):
            with self.assertRaises(ValueError):report(b)

if __name__=='__main__':unittest.main()
