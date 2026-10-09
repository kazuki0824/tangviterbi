"""Capacity/lifetime checks; target ABI is provided as evidence, not host sizeof."""
import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('startup_bound', ROOT/'ci/s3_startup_memory_bound.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class StartupBoundTest(unittest.TestCase):
    def audit(self, gap=21000, pool=8192, tcb=340, timer="timers"):
        config = dict(FREERTOS_NUMBER_OF_CORES=2, ESP_IPC_ENABLE=True,
                      ESP32S3_DATA_CACHE_32KB=True, SPIRAM_MODE_OCT=True,
                      ESP_SYSTEM_MEMPROT_FEATURE=True, ESP32S3_INSTRUCTION_CACHE_16KB=True,
                      ESP_SYSTEM_ALLOW_RTC_FAST_MEM_AS_HEAP=True,
                      ESP_MAIN_TASK_STACK_SIZE=8192, ESP_TIMER_TASK_STACK_SIZE=3584,
                      ESP_IPC_TASK_STACK_SIZE=1280, FREERTOS_IDLE_TASK_STACKSIZE=1536,
                      FREERTOS_USE_TIMERS=True, FREERTOS_TIMER_TASK_STACK_DEPTH=2048,
                      SPIRAM_MALLOC_RESERVE_INTERNAL=pool, ESP_SYSTEM_EVENT_TASK_STACK_SIZE=2304,
                      LIBC_NEWLIB_NANO_FORMAT=False)
        symbols = dict(_heap_start=0x3fcb0000-gap, _data_start=0x3fc99700,
                       _iram_end=0x40389700, fft_slot1=0x3fc9cfe0,
                       fft_twiddle_reservation=0x3fc9bfd0, _rtc_force_fast_end=0x600fe000,
                       _rtc_reserved_start=0x60100000, _rtc_reserved_end=0x60100000)
        text = ''.join(f'  0x{value:08x} {key}\n' for key,value in symbols.items())
        text += '.text.xTimerCreateTimerTask\n 0x4038271c 0x7 esp-idf/freertos/libfreertos.a('+timer+'.c.obj)\n'
        return m.audit(text, config, 'native-quarter-fft', tcb)

    def test_pool_must_fit_after_live_stacks_not_before_them(self):
        r=self.audit()
        self.assertEqual(r['total_stack_lower_bound_bytes'],20480)
        self.assertEqual(r['startup_TCB_lower_bound_bytes'],2380)
        self.assertTrue(r['startup_necessary_capacity_pass'])
        self.assertTrue(r['internal_DMA_pool_has_distinct_byte_capacity'])
        self.assertEqual(r['internal_free_before_DMA_pool_upper_bound_bytes'],6332)
        self.assertFalse(r['startup_pool_necessary_capacity_pass'])
        self.assertEqual(r['startup_pool_shortage_lower_bound_bytes'],1860)
        self.assertEqual(r['headroom_after_startup_tasks_and_native_event_upper_bound_bytes'],3176)

    def test_disabling_pool_is_not_full_receiver_proof_or_extra_heap(self):
        r=self.audit(pool=0)
        self.assertTrue(r['startup_pool_necessary_capacity_pass'])
        self.assertFalse(r['startup_sufficient_capacity_proven'])
        self.assertEqual(r['headroom_after_startup_tasks_and_native_event_upper_bound_bytes'],3176)
        self.assertFalse(r['receiver_adopted'])

    def test_weak_timer_constructor_does_not_allocate_a_task(self):
        r=self.audit(timer='tasks')
        self.assertFalse(r['FreeRTOS_timer_task_created'])
        self.assertEqual(r['startup_task_count'],6)
        self.assertEqual(r['total_stack_lower_bound_bytes'],18432)
        self.assertEqual(r['startup_TCB_lower_bound_bytes'],2040)

    def test_target_layout_requires_unique_dwarf_evidence(self):
        valid='    DW_AT_name : xSTATIC_TCB\n    DW_AT_byte_size : 340\n'
        self.assertEqual(m.tcb_size_from_dwarf(valid*2),340)
        for bad in ('', valid+valid.replace('340','344')):
            with self.assertRaises(ValueError):m.tcb_size_from_dwarf(bad)

if __name__=='__main__':unittest.main()
