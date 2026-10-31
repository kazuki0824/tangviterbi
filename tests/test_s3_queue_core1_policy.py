import subprocess
import tempfile
import unittest
from pathlib import Path
from experiments.s3_joint_runtime import ROOT
from experiments.s3_queue_core1_probe import generate


class Core1Policy(unittest.TestCase):
    def test_priority_and_configuration_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'esp_task.h').write_text('#define ESP_TASK_TIMER_PRIO 22\n')
            (path / 'sdkconfig.h').write_text('')
            (path / 'test.c').write_text('''#include <assert.h>
#include "s3_queue_core1_policy.h"
int main(void){
 assert(!s3_queue_core1_priorities_valid(0));
 for(unsigned a=0;a<26;++a)for(unsigned b=0;b<26;++b){
  unsigned p[2]={a,b};
  assert(s3_queue_core1_priorities_valid(p)==(a>0&&a<22&&b>0&&b<22));
 }
}''')
            configurations = [(1, 1, 0, 0), (0, 1, 0, 0), (1, 0, 0, 0), (1, 1, 1, 0), (1, 1, 0, 1)]
            for core, irq, unicore, disable in configurations:
                with self.subTest(core=core, irq=irq, unicore=unicore, disable=disable):
                    command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                               '-I'+str(path), '-I'+str(ROOT/'experiments'),
                               f'-DCONFIG_ESP_TIMER_TASK_AFFINITY={core}',
                               f'-DCONFIG_ESP_TIMER_ISR_AFFINITY_CPU1={irq}',
                               f'-DCONFIG_FREERTOS_UNICORE={unicore}',
                               f'-DCONFIG_ESP_PHY_DISABLE_PLL_TRACK={disable}',
                               str(path/'test.c'), '-o', str(path/'test')]
                    result = subprocess.run(command, capture_output=True, text=True)
                    valid = (core, irq, unicore, disable) == configurations[0]
                    self.assertEqual(result.returncode == 0, valid, result.stderr)
                    if valid:
                        subprocess.run([str(path/'test')], check=True)

    def test_generated_candidate_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            generate(path)
            cmake = (path/'main/CMakeLists.txt').read_text()
            self.assertIn('S3_PP_CORE0_SIXTEENTHS=6', cmake)
            self.assertIn('s3_queue_core1_priorities_valid(priorities)', (path/'main/queue_memory_probe.c').read_text())
            self.assertIn('S3_PP_CORE0_SIXTEENTHS=5', (ROOT/'experiments/s3_queue_memory_probe/main/CMakeLists.txt').read_text())

if __name__ == '__main__':
    unittest.main()
