#!/usr/bin/env python3
"""Enumerate linked T SDK static conditions, including unavailable inputs.

Each criterion records PASS/FAIL/BLOCKED independently. These checks establish
the specified source, linkage and ownership conditions, not measured hardware
timing, stack high-water, physical RF validity or receiver quality.
"""
import argparse,gzip,hashlib,io,json,os,re,struct,subprocess,sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ci.s3_sdk_cost_audit import Binary
PIN='fcae32885b0296b32044cb99ecbdc50d98dddb83'
OUT=ROOT/'reports/s3-t-preprocess-integration-v2/sdk'
def sha(data):return hashlib.sha256(data).hexdigest()
def unpack(path):
    data=Path(path).read_bytes()
    return gzip.decompress(data) if str(path).endswith('.gz') else data
def open_binary(tc,path,tag='tpre-v2'):
    b=Binary.__new__(Binary);b.raw=unpack(path);b.sha=sha(b.raw);b.elf=ELFFile(io.BytesIO(b.raw))
    b.symbols={s.name:s for s in b.elf.get_section_by_name('.symtab').iter_symbols()}
    build=ROOT/'build';build.mkdir(exist_ok=True);b.path=build/(tag+'.elf');b.path.write_bytes(b.raw)
    b.tool=str(Path(tc)/'bin/xtensa-esp-elf-objdump');b.env=dict(os.environ,XTENSA_GNU_CONFIG=str(Path(tc)/'lib/xtensa_esp32s3.so'))
    b.cache=build/(tag+'-graphs.json');b.graphs={}
    if b.cache.exists():
        cached=json.loads(b.cache.read_text())
        if cached.get('sha')==b.sha:b.graphs=cached['graphs']
    return b
def symdata(b,name):
    s=b.symbols[name];section=b.elf.get_section(s['st_shndx']);start=int(s['st_value'])-int(section['sh_addr'])
    return section.data()[start:start+int(s['st_size'])]
def address(b,name):return int(b.symbols[name]['st_value'])
def allocation(raw):
    elf=ELFFile(io.BytesIO(raw))
    return [dict(name=s.name,address=int(s['sh_addr']),size=int(s['sh_size']),flags=int(s['sh_flags']),
                 type=s['sh_type'],sha256=sha(s.data())) for s in elf.iter_sections() if int(s['sh_flags'])&2]
class BlockedCondition(RuntimeError):pass
class Checks:
    def __init__(self):self.rows=[]
    def check(self,name,fn):
        try:
            detail=fn()
            if detail is False:raise AssertionError('condition false')
            self.rows.append(dict(name=name,status='PASS',detail=detail));return detail
        except BlockedCondition as exc:self.rows.append(dict(name=name,status='BLOCKED',detail=str(exc)))
        except Exception as exc:self.rows.append(dict(name=name,status='FAIL',detail=f'{type(exc).__name__}: {exc}'))
        return None
    @property
    def passed(self):return all(r['status']=='PASS' for r in self.rows)
class Resources:
    def __init__(self,checks):self.checks=checks;self.data={}
    def load(self,name,fn):
        def perform():self.data[name]=fn();return {'available':True}
        return self.checks.check('input '+name,perform)
    def need(self,name):
        if name not in self.data:raise BlockedCondition('unavailable input: '+name)
        return self.data[name]
CONFIG_EXPECTATIONS=[('IDF_TARGET','esp32s3'),('SPIRAM',True),('SPIRAM_MODE_OCT',True),('SPIRAM_SPEED',80),
 ('ESPTOOLPY_FLASHSIZE','16MB'),('ESP_DEFAULT_CPU_FREQ_MHZ',240),('COMPILER_OPTIMIZATION_PERF',True),
 ('STDATOMIC_S32C1I_SPIRAM_WORKAROUND',True),('SPI_MASTER_IN_IRAM',True),('SPI_MASTER_ISR_IN_IRAM',True),
 ('HEAP_PLACE_FUNCTION_INTO_FLASH',True),('FREERTOS_FPU_IN_ISR',False),('ESP_TIMER_TASK_AFFINITY',1),
 ('ESP_PHY_DISABLE_PLL_TRACK',False),('ESP_PHY_PLL_TRACK_PERIOD_MS',1000),('ESP_PHY_CALIBRATION_AND_DATA_STORAGE',False),
 ('FREERTOS_UNICORE',False),('FREERTOS_HZ',100),('PM_ENABLE',False)]
MAIN_UNITS=['integration_probe.c','tpre_runtime.c','tpre_sdk.c','tpre_pie.S','native_adapter.c',
 'halfband_pipeline.c','halfband31.c','halfband31.S','s3_native_capture.c','s3_capture_bridge.c','s3_cycle_clock.c']
SOURCE_INPUTS=['experiments/s3_capture_bridge.c','experiments/s3_capture_bridge.h','experiments/s3_cycle_clock.c',
 'experiments/s3_cycle_clock.h','experiments/s3_native_capture.c','experiments/s3_native_capture.h','experiments/s3_transport.h',
 *['experiments/t_preprocess_capacity/'+n for n in ('halfband31.S','halfband31.c','halfband31.h','halfband_pipeline.c','halfband_pipeline.h','native_adapter.c','native_adapter.h')],
 *['experiments/t_preprocess_integration_probe/'+n for n in ('.gitignore','CMakeLists.txt','build_probe.py','main/CMakeLists.txt',
 'main/hot.lf','main/integration_probe.c','main/sram_guard.ld','sdkconfig.defaults','tpre_pie.S','tpre_runtime.c','tpre_runtime.h','tpre_sdk.c','tpre_sdk.h')]]
SDK_INPUTS=['components/xtensa/esp32s3/include/xtensa/config/tie.h','components/xtensa/xtensa_vectors.S',
 'components/freertos/FreeRTOS-Kernel/portable/xtensa/portasm.S','components/xtensa/include/xtensa_context.h',
 'components/esp_driver_spi/src/gpspi/spi_master.c','components/esp_hw_support/spi_bus_lock.c',
 'components/esp_driver_spi/Kconfig','components/esp_timer/Kconfig']
ARTIFACT_INPUTS=['compile_commands.json.gz','sdkconfig.gz','sdkconfig.h.gz','sdkconfig.json.gz','project_description.json.gz',
 'build.log.gz','stack-usage.json','idf-submodules.txt','python-packages.txt','t_preprocess_integration_probe.map.gz','t_preprocess_integration_probe.elf.gz']
def audit(tc,elf,config,idf,provenance):
    ck=Checks();res=Resources(ck);folder=Path(provenance).parent;idf=Path(idf);layout={};ih={};cache_placement={}
    def object_json(path):
        value=json.loads(unpack(path))
        if not isinstance(value,dict):raise ValueError('expected JSON object: '+str(path))
        return value
    res.load('ELF',lambda:open_binary(tc,elf));res.load('provenance',lambda:object_json(provenance))
    res.load('configuration',lambda:object_json(config));res.load('compile commands',lambda:json.loads(unpack(folder/'compile_commands.json.gz')))
    res.load('SDK implementation',lambda:(ROOT/'experiments/t_preprocess_integration_probe/tpre_sdk.c').read_text())
    res.load('SDK header',lambda:(ROOT/'experiments/t_preprocess_integration_probe/tpre_sdk.h').read_text())
    res.load('application',lambda:(ROOT/'experiments/t_preprocess_integration_probe/main/integration_probe.c').read_text())
    for name in SDK_INPUTS:res.load(name,lambda name=name:(idf/name).read_text())
    def b():return res.need('ELF')
    def p():return res.need('provenance')
    def cfg():return res.need('configuration')
    def sdk():return res.need('SDK implementation')
    def header():return res.need('SDK header')
    def app():return res.need('application')
    def value(test,detail):
        if not test:raise AssertionError(detail)
        return detail
    ck.check('provided ELF SHA256 binds fresh build',lambda:value(b().sha==p()['provided_elf_sha256'],b().sha))
    ck.check('ELF retains target symbols',lambda:bool(b().elf.get_section_by_name('.symtab')))
    ck.check('provided ELF has no DWARF debug sections',lambda:not any(s.name.startswith('.debug') for s in b().elf.iter_sections()))
    ck.check('IDF build commit pinned',lambda:p()['idf_commit']==PIN)
    ck.check('installed IDF commit pinned',lambda:subprocess.check_output(['git','-C',str(idf),'rev-parse','HEAD'],text=True,stderr=subprocess.STDOUT).strip()==PIN)
    ck.check('compiler build identity pinned',lambda:'esp-14.2.0_20241119' in p()['compiler'])
    ck.check('installed compiler identity pinned',lambda:'esp-14.2.0_20241119' in subprocess.check_output([str(Path(tc)/'bin/xtensa-esp-elf-gcc'),'--version'],text=True,stderr=subprocess.STDOUT))
    for name,want in CONFIG_EXPECTATIONS:
        ck.check('config '+name,lambda name=name,want=want:value(cfg().get(name,False)==want,dict(actual=cfg().get(name,False),expected=want)))
    saved=res.data.get('provenance',{});sources=saved.get('source_sha256',{});sources=sources if isinstance(sources,dict) else {}
    names=sorted(set(SOURCE_INPUTS)|set(sources))
    for name in names:ck.check('compiled source/header '+name,lambda name=name:sha((ROOT/name).read_bytes())==p()['source_sha256'][name])
    artifacts=saved.get('artifact_sha256',{});artifacts=artifacts if isinstance(artifacts,dict) else {}
    for name in sorted(set(ARTIFACT_INPUTS)|set(artifacts)):
        ck.check('saved artifact '+name,lambda name=name:sha((folder/name).read_bytes())==p()['artifact_sha256'][name])
    ck.check('sdkconfig text binds build',lambda:sha(unpack(folder/'sdkconfig.gz'))==p()['config_sha256'])
    def units():return [r for r in res.need('compile commands') if 'esp-idf/main/' in r.get('output',r.get('command',''))]
    def command(name):
        rows=[r for r in units() if Path(r['file']).name==name]
        if len(rows)!=1:raise AssertionError(f'{name}: expected one compiled unit, got {len(rows)}')
        return rows[0]['command']
    ck.check('main component has expected compiled units',lambda:sorted(Path(r['file']).name for r in units())==sorted(MAIN_UNITS))
    for name in MAIN_UNITS:
        ck.check('main hardware atomics override '+name,lambda name=name:command(name).rfind('-mno-disable-hardware-atomics')>command(name).rfind('-mdisable-hardware-atomics'))
        ck.check('SLP disabled '+name,lambda name=name:'-fno-tree-slp-vectorize' in command(name))
    ck.check('main sentinel unroll is eight',lambda:all('-DS3_NATIVE_FILL_UNROLL=8' in command(name) for name in MAIN_UNITS))
    chunks={};manifest=saved.get('full_elf_chunks');pn=[r.get('path') for r in manifest if isinstance(r,dict)] if isinstance(manifest,list) else []
    pn=pn if pn and all(isinstance(n,str) for n in pn) else [f'full-elf.parts/part-{i:03d}' for i in range(7)]
    ck.check('full ELF chunk manifest nonempty and unique',lambda:bool(p()['full_elf_chunks']) and len({r['path'] for r in p()['full_elf_chunks']})==len(p()['full_elf_chunks']))
    def read_part(name):
        row=next(r for r in p()['full_elf_chunks'] if r['path']==name);data=(folder/name).read_bytes()
        assert 0<len(data)<=240000 and len(data)==row['bytes'] and sha(data)==row['sha256'],name
        chunks[name]=data;return dict(bytes=len(data),sha256=sha(data))
    for name in pn:ck.check('full ELF chunk '+name,lambda name=name:read_part(name))
    def fullcheck():
        rows=p()['full_elf_chunks'];missing=[r['path'] for r in rows if r['path'] not in chunks]
        if missing:raise BlockedCondition('unverified full ELF chunks: '+', '.join(missing))
        data=b''.join(chunks[r['path']] for r in rows);assert sha(data)==p()['full_elf_gzip_sha256']
        raw=gzip.decompress(data);assert sha(raw)==p()['full_elf_sha256']
        assert allocation(raw)==allocation(b().raw)==p()['allocated_sections']
        return dict(full_sha256=sha(raw),chunks=len(chunks),allocated_sections=len(p()['allocated_sections']))
    ck.check('full ELF chunks and debug stripping preserve all allocated bytes',fullcheck)
    def readlayout():
        raw=symdata(b(),'tpre_target_layout');vals=struct.unpack('<'+'I'*(len(raw)//4),raw)
        fields=['version','sdk_bytes','runtime_bytes','capture_bytes','pipe_bytes','adapter_bytes','tcb_bytes','transaction_bytes','clock_bytes',
                'adapter_banks','adapter_count','adapter_fill','adapter_last_time','pipe_slots','slot_bytes','slot_status','slot_output',
                'pipe_address','adapter_address','stack0_address','stack1_address','late_end']
        assert len(vals)==len(fields);candidate=dict(zip(fields,vals));assert candidate['version']==2
        layout.update(candidate);return layout
    def L(name):
        if name not in layout:raise BlockedCondition('target ABI unavailable: '+name)
        return layout[name]
    ck.check('target ABI table read from linked image',readlayout)
    ck.check('pipeline target ABI fits fixed reservation',lambda:0<L('pipe_bytes')<=8528)
    ck.check('adapter target ABI fits fixed reservation',lambda:0<L('adapter_bytes')<=4304)
    ck.check('late reservation payload and stacks disjoint',lambda:L('pipe_address')+L('pipe_bytes')<=L('adapter_address') and
             L('adapter_address')+L('adapter_bytes')<=L('stack0_address') and L('stack0_address')+4096==L('stack1_address') and L('stack1_address')+4096==L('late_end'))
    for name,upper in [('_data_end',0x3fcb0000),('_bss_end',0x3fcb0000),('_iram_end',0x403a0000)]:
        ck.check('RF SRAM exclusion '+name,lambda name=name,upper=upper:value(address(b(),name)<=upper,dict(address=hex(address(b(),name)),limit=hex(upper))))
    ck.check('four lower DMA frames have 16-byte alignment',lambda:address(b(),'tpre_lower_frames')%16==0)
    ck.check('four lower DMA frames entirely below RF',lambda:address(b(),'tpre_lower_frames')+int(b().symbols['tpre_lower_frames']['st_size'])<=0x3fcb0000)
    ck.check('lower DMA arena exactly four frames',lambda:int(b().symbols['tpre_lower_frames']['st_size'])==4*16384)
    hot=['hbpipe_unpack','hbpipe_prefix','hbpipe_suffix','hbpipe_produce','hbpipe_work','hbpipe_reap','hb31_qacc4','hb31_copy_words',
         'tpre_pie_warmup','tpre_owner_step','tpre_worker_step','tpre_sdk_task','tpre_sdk_submit','tpre_sdk_reap','tpre_sdk_feed',
         'hbnative_step_clocked','hbnative_copy_words','s3_native_poll_budget','s3_cycle_clock_read','spi_intr','SysTickIsrHandler']
    for name in hot:ck.check('IRAM hot function '+name,lambda name=name:0x40370000<=address(b(),name)<0x403e0000)
    ck.check('internal coefficient storage hb31_vectors',lambda:0x3fc88000<=address(b(),'hb31_vectors')<0x3fcb0000)
    for name in ('esp_phy_enable','phy_track_pll_timer_callback','wait_hw_freq_busy','_xt_coproc_exc'):
        ck.check('actual linked SDK dependency '+name,lambda name=name:name in b().symbols)
    contracts=[('SPI3 routing','spi_bus_initialize(SPI3_HOST'),('Quad envelope','SPI_TRANS_MODE_QIO'),('80MHz requested and checked','khz!=80000'),
        ('queue depth two','s->queued>=TPRE_QUEUE_DEPTH'),('IRQ pinned core0','ESP_INTR_CPU_AFFINITY_0'),('level1 IRAM IRQ','ESP_INTR_FLAG_IRAM|ESP_INTR_FLAG_LEVEL1'),
        ('actual watchdog config copied','s->watchdog=*wdt'),('internal object range validation','internal_range(objects[i],sizes[i])'),
        ('DMA endpoints validated','esp_ptr_dma_capable(frame+TPRE_FRAME_BYTES-1)'),('queue error poisons ownership','s->poisoned=true;return sdk_fail(s,SDK_SPI)'),
        ('exact ordered transaction identity','done!=&s->transactions[s->head]'),('one-shot launch','s->attempted=true'),('lazy CP3 warmup','tpre_pie_warmup();'),
        ('worker awake gate','atomic_store_explicit(&s->ready[1],2,memory_order_release)'),('worker pinned core1','stacks[1],tcbs[1],1)'),('owner pinned core0','stacks[0],tcbs[0],0)'),
        ('runtime receives measured clock error','r->clock_error=s->clocks[0].error'),('T native input rate16MSps','s3_native_mmio(),16,'),('RF stopped before drain','s3_native_stop(r->capture)'),
        ('watchdog restored','esp_task_wdt_reconfigure(&s->watchdog)'),('bounded nonblocking drain','i<TPRE_QUEUE_DEPTH&&s->queued'),('watchdog half-timeout cadence','s->watchdog.timeout_ms*240000/2')]
    for label,needle in contracts:ck.check('source contract '+label,lambda needle=needle:needle in sdk())
    ck.check('worker created before owner',lambda:sdk().index('s->handles[1]=xTaskCreate')<sdk().index('s->handles[0]=xTaskCreate'))
    ck.check('DMA ownership stored before driver queue',lambda:sdk().index('++s->queued;')<sdk().index('if(spi_device_queue_trans'))
    ck.check('stopped explicitly not task-death guarantee',lambda:'NOT task deletion' in header() and 'No restart/free API' in header())
    ck.check('late SRAM storage init is one shot',lambda:'static bool storage_attempted;' in app() and
             app().index('if(storage_attempted)return false;')<app().index('storage_attempted=true;')<app().index('memset(n,0,sizeof(*n));'))
    ck.check('late SRAM adapter cleared before owner validation',lambda:app().index('memset(n,0,sizeof(*n));')<app().index('hbnative_init(n,p,1)'))
    ck.check('halfband shift10 matches runtime and quality contract',lambda:'hbpipe_init(p,10)' in app())
    ck.check('application is link only',lambda:not any(x in app().split('void app_main(void)')[1] for x in ('tpre_sdk_launch(','tpre_sdk_open(','esp_phy_enable(','s3_native_start')))
    for needle in ('0x3fcb0000,0x3fce8000','0x3fce9720,0x3fcee940','0x3fcf0000,0x3fcf8000'):
        ck.check('allocator reserves '+needle,lambda needle=needle:'SOC_RESERVE_MEMORY_REGION('+needle in app())
    def idf_hash(name):
        data=res.need(name).encode();digest=sha(data)
        assert sha(subprocess.check_output(['git','-C',str(idf),'show',PIN+':'+name],stderr=subprocess.STDOUT))==digest
        ih[name]=digest;return digest
    for name in SDK_INPUTS:ck.check('pinned SDK source readable '+name,lambda name=name:idf_hash(name))
    def tie():return res.need(SDK_INPUTS[0])
    def vectors():return res.need(SDK_INPUTS[1])
    def port():return res.need(SDK_INPUTS[2])
    ck.check('CP3 context size is208 and align16',lambda:bool(re.search(r'XCHAL_CP3_SA_SIZE\s+208',tie())) and bool(re.search(r'XCHAL_CP3_SA_ALIGN\s+16',tie())))
    ck.check('CP3 lazy owner save/load implemented',lambda:'xchal_cpi_store_funcbody' in vectors() and 'xchal_cpi_load_funcbody' in vectors())
    ck.check('ISR CPENABLE clearing conditional on disabled config',lambda:'#if CONFIG_FREERTOS_FPU_IN_ISR && XCHAL_CP_NUM > 0' in port() and not cfg().get('FREERTOS_FPU_IN_ISR'))
    for name in ('spi_intr','SysTickIsrHandler'):
        ck.check('root ISR contains no PIE '+name,lambda name=name:not any(n['op'].startswith('ee.') for n in b().graph(name).values()))
    ck.check('warmup is exactly entry PIE return',lambda:[n['op'] for _,n in sorted(b().graph('tpre_pie_warmup').items())]==['entry','ee.zero.qacc','retw.n'])
    ck.check('normal interrupt entry has no CPENABLE writes',lambda:'cpenable' not in subprocess.check_output([b().tool,'-d','--disassemble=_frxt_int_enter',str(b().path)],env=b().env,text=True).lower())
    def placement(name):
        s=b().symbols[name];section=b().elf.get_section(s['st_shndx']).name
        row=dict(address=hex(int(s['st_value'])),section=section);cache_placement[name]=row;return row
    for name in ('spi_intr','spi_bus_lock_bg_entry','spi_bus_lock_bg_exit','spi_bus_lock_bg_check_dev_req','spi_bus_lock_get_acquiring_dev'):
        ck.check('cache scope linked helper '+name,lambda name=name:placement(name))
    ck.check('cache enabled receive condition documented',lambda:'Reception assumes flash cache enabled' in header())
    return dict(schema_version=2,status='PASS' if ck.passed else 'FAIL',all_static_checks_pass=ck.passed,checks=ck.rows,
        check_counts={s:sum(c['status']==s for c in ck.rows) for s in ('PASS','FAIL','BLOCKED')},
        elf_sha256=res.data['ELF'].sha if 'ELF' in res.data else None,target_layout=layout,source_sha256=sources,
        idf_source_sha256=ih,cache_placement=cache_placement,non_fail_fast=True,expected_source_inputs=names,
        source_auditor_sha256=sha(Path(__file__).read_bytes()),hardware_executed=False,hardware_wcet=False,
        unresolved_conditions=['Reception requires cache enabled; IRAM ISR roots do not establish transitive cache-off safety.',
        'All other ISR/NMI code must independently prohibit PIE; ordinary ISR entry does not clear CPENABLE.',
        'PHY hardware wait, lock contention, flash/cache/MMIO/bus stalls and task/window context exceptions lack measured bounds.',
        'Fixed stack reservation is not a measured stack high-water or whole-system heap proof.',
        'app_main is link-only; physical RF, diagnostic SPI envelope and original receiver quality are not adopted or measured.'])
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);ap.add_argument('--idf',type=Path,required=True)
    ap.add_argument('--elf',type=Path,default=OUT/'t_preprocess_integration_probe.elf.gz');ap.add_argument('--config',type=Path,default=OUT/'sdkconfig.json.gz')
    ap.add_argument('--provenance',type=Path,default=OUT/'provenance.json');ap.add_argument('--output',type=Path,default=OUT/'audit.json');a=ap.parse_args()
    r=audit(a.toolchain.resolve(),a.elf,a.config,a.idf,a.provenance);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status=r['status'],checks=r['check_counts']),indent=2))
    return 0 if r['all_static_checks_pass'] else 1
if __name__=='__main__':raise SystemExit(main())
