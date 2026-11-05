"""Generate the S6/16 core1 timer candidate without changing saved S5 evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from experiments.s3_joint_runtime import ROOT, replace
from experiments.s3_queue_tasks_source import main as tasks


def generate(out):
    out = out.resolve()
    main = out / 'main'
    main.mkdir(parents=True, exist_ok=True)
    baseline = ROOT / 'experiments/s3_queue_memory_probe'
    source = (baseline / 'main/queue_memory_probe.c').read_text()
    source = replace(source, '"../../s3_queue_owner_probe/main/queue_owner_probe.c"',
                     json.dumps(str(ROOT / 'experiments/s3_queue_owner_probe/main/queue_owner_probe.c')))
    source = replace(source, '#include "esp_phy_init.h"',
                     '#include "esp_phy_init.h"\n#include "s3_queue_core1_policy.h"')
    source = replace(source, 'static bool create_tasks(const unsigned priorities[2]){',
                     'static bool create_tasks(const unsigned priorities[2]){\n if(!s3_queue_core1_priorities_valid(priorities))return false;')
    source = replace(source, 'void app_main(void){', '''const volatile unsigned s3_queue_core1_contract[]={
 CONFIG_ESP_TIMER_TASK_AFFINITY,CONFIG_ESP_TIMER_ISR_AFFINITY_CPU1,
 ESP_TASK_TIMER_PRIO,S3_PP_CORE0_SIXTEENTHS,S3_RAW_PREPARE_WORDS_PER_ITERATION,
 CONFIG_ESP_PHY_PLL_TRACK_PERIOD_MS,S3_RAW_TRANSFER_BYTES};
void app_main(void){
 printf("CORE1 LINK ONLY: timer core=%u; no RF startup or WCET measurement\\n",s3_queue_core1_contract[0]);''')
    (main / 'queue_memory_probe.c').write_text(source)
    cmake = (baseline / 'main/CMakeLists.txt').read_text()
    cmake = cmake.replace('"../../', '"' + str(ROOT / 'experiments') + '/')
    cmake = replace(cmake, '"../.."', json.dumps(str(ROOT / 'experiments')))
    cmake = replace(cmake, 'S3_PP_CORE0_SIXTEENTHS=5', 'S3_PP_CORE0_SIXTEENTHS=6')
    (main / 'CMakeLists.txt').write_text(cmake)
    (main / 'sram_guard.ld').write_bytes((baseline / 'main/sram_guard.ld').read_bytes())
    (out / 'CMakeLists.txt').write_text((baseline / 'CMakeLists.txt').read_text())
    defaults = (baseline / 'sdkconfig.defaults').read_text() + '''
# Move BOTH timer task and timer IRQ; this affects all esp_timer callbacks.
CONFIG_ESP_TIMER_SHOW_EXPERIMENTAL=y
CONFIG_ESP_TIMER_TASK_AFFINITY_CPU1=y
CONFIG_ESP_TIMER_ISR_AFFINITY_CPU1=y
CONFIG_ESP_PHY_PLL_TRACK_PERIOD_MS=1000
# CONFIG_ESP_PHY_DISABLE_PLL_TRACK is not set
'''
    (out / 'sdkconfig.defaults').write_text(defaults)
    tasks(main / 'generated')
    paths = [Path(__file__), ROOT / 'experiments/s3_queue_core1_policy.h',
             baseline / 'main/queue_memory_probe.c', baseline / 'main/CMakeLists.txt',
             baseline / 'main/sram_guard.ld', baseline / 'CMakeLists.txt', baseline / 'sdkconfig.defaults']
    (out / 'provenance.json').write_text(json.dumps({
        'scope': __doc__, 'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'generated_sha256': {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [main / 'queue_memory_probe.c', main / 'CMakeLists.txt', out / 'sdkconfig.defaults']},
        'hardware_executed': False, 'safe_to_flash': False}, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    generate(parser.parse_args().output)
