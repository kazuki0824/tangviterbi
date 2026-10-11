"""Check real same-batch dependencies and retained leases from event traces."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
from s3_receiver_rpc_schedule import BATCH_US, RF_PAGE_US, simulate


class ReceiverScheduleTest(unittest.TestCase):
    def test_native_RF_and_all_RPC_batches_drain_across_release_phases(self):
        for phase in range(16):
            result = simulate(batches=128, phase_us=phase*BATCH_US/16)
            self.assertTrue(result['conditional_schedule_pass'], result)
            self.assertEqual(result['RPC_batches_completed'], 128)
            self.assertEqual(result['RF_pages_consumed'], result['RF_pages_generated'])
            self.assertEqual(sum(result['RF_pages_by_port']), result['RF_pages_generated'])
            self.assertLessEqual(result['peak_reserved_FPGA_pages'], 8)
            self.assertLessEqual(result['peak_host_RF_pages'], 16)
            self.assertLessEqual(result['peak_raw_codewords_held'], 512)
            self.assertLess(result['maximum_RPC_batch_completion_us'], BATCH_US)
            self.assertFalse(result['CPU_WCET_verified'])
            self.assertFalse(result['receiver_adopted'])

    def test_independent_trace_dependency_and_port_serialization(self):
        result = simulate(batches=8, trace=True)
        self.assertTrue(result['conditional_schedule_pass'])
        last_end = [0., 0.]
        stages = {}
        sequence = 0
        for transaction in result['transactions']:
            port = transaction['port']
            self.assertGreaterEqual(transaction['start_us']+1e-7, last_end[port])
            last_end[port] = transaction['end_us']
            if transaction['kind'] == 'RF':
                self.assertEqual(transaction['sequence'], sequence)
                sequence += transaction['pages']
            if transaction['kind'] == 'RPC':
                batch, stage = transaction['batch'], transaction['stage']
                if stage == 0:
                    self.assertGreaterEqual(transaction['start_us'], (batch+1)*BATCH_US+512-1e-7)
                else:
                    delay = (1000, 204*224/90, 1000)[stage-1]
                    self.assertGreaterEqual(transaction['start_us']+1e-7, stages[batch, stage-1]+delay)
                stages[batch, stage] = transaction['end_us']
        self.assertEqual(len(stages), 8*4)
        self.assertEqual(sequence, result['RF_pages_generated'])

    def test_slow_API_small_window_and_old_storage_are_rejected(self):
        for options, reason in [
            ({'spi_api_us': 40, 'lcd_api_us': 40}, 'host_RF_ring_overflow'),
            ({'window': 2}, 'host_RF_ring_overflow'),
            ({'raw_slots': 204}, 'raw_codeword_ring_overflow'),
        ]:
            result = simulate(batches=32, **options)
            self.assertFalse(result['conditional_schedule_pass'])
            self.assertEqual(result['failure']['kind'], reason)


if __name__ == '__main__':
    unittest.main()
