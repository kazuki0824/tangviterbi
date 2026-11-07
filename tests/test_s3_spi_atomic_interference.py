import unittest

class AtomicInterferenceTest(unittest.TestCase):
    def test_one_foreign_store_can_force_only_one_retry_across_ISR(self):
        # Six RMWs overapproximate two outer rounds (set PEND, clear REQ,
        # clear PEND). Every read/CAS boundary admits the sole producer OR.
        ops=[('or',2),('and',~1),('and',~2)]*2
        maxima=[]
        for initial in range(8):
            seen=set();terminal=[]
            def visit(i,value,expected,used,retries):
                state=(i,value,expected,used,retries)
                if state in seen:return
                seen.add(state)
                if i==len(ops):terminal.append(retries);return
                if not used:visit(i,value|1,expected,True,retries)
                if expected is None:visit(i,value,value,used,retries)
                elif value==expected:
                    op,mask=ops[i]
                    visit(i+1,value|mask if op=='or' else value&mask,None,used,retries)
                else:
                    # Real helper reuses value returned by S32C1I, without
                    # another separate load before the next attempt.
                    visit(i,value,value,used,retries+1)
            visit(0,initial,None,False,0)
            self.assertTrue(terminal);self.assertLessEqual(max(terminal),1)
            maxima.append(max(terminal))
        self.assertEqual(max(maxima),1)

if __name__=='__main__':unittest.main()
