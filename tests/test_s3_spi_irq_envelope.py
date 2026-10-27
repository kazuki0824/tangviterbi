import unittest
from experiments.s3_spi_irq_envelope import certificate, successors, potential, worker_event
from experiments.s3_worker_response import fixed_point


class IRQEnvelopeTest(unittest.TestCase):
    def test_inductive_certificate_all_reachable_edges(self):
        result=certificate()
        states={tuple(s) for s in result['states']}
        self.assertEqual({potential(s) for s in states},{-1,0,1,2})
        for source in states:
            for _,target,irq,done in successors(source):
                self.assertIn(target,states)
                self.assertLessEqual(irq-2*done,potential(source)-potential(target))

    def test_delayed_publication_permits_two_publications_without_completion(self):
        # Initial transfer already completed, but its queue API has not
        # published REQ yet. A window may contain both its publication and
        # the replacement's publication, with no completion inside the window.
        state=(1,1,0,1,1)
        for event in ('publish','reap','enqueue','publish'):
            state=next(s for label,s,_,_ in successors(state) if label==event)
        self.assertEqual(state[2:4],(1,0))

    def test_worker_event_exact_formula_and_fixed_point_interface(self):
        for lanes,L in ((8,98334),(4,196668)):
            event=worker_event(lanes,7)
            self.assertEqual(event['period'],L)
            for R in (0,1,L-1,L,L+1,10*L):
                demand=(event['burst']+R//event['period'])*event['cost']
                self.assertEqual(demand,(6+2*(R//L))*7)
            self.assertEqual(fixed_point(100,[event],1000)['response_cycles'],142)
        for bad in (None,0,-1,True,1.5):
            with self.assertRaises(ValueError):worker_event(8,bad)


if __name__=='__main__':unittest.main()
