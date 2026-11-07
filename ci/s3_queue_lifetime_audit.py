"""Recheck archived SPI/PHY lifetime ledger for 16KiB and depth two."""
import gzip,hashlib,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/s3-queue-owner'
def audit():
 code=(ROOT/'ci/s3_runtime_memory_audit.py').read_text()
 code=code.replace("TYPE_NAMES = (", "TYPE_NAMES = ('twdt_entry', 'twdt_obj', ",1)
 a='descriptor_count = (32768 + 4092 - 1) // 4092';b='descriptor_count = (16384 + 4092 - 1) // 4092'
 assert code.count(a)==1;code=code.replace(a,b)
 a="sizes['Queue_t'] + sizes['spi_trans_priv_t']";assert code.count(a)==1;code=code.replace(a,"sizes['Queue_t'] + 2*sizes['spi_trans_priv_t']")
 sys.path.insert(0,str(ROOT/'ci'));ns={'__file__':str(ROOT/'ci/s3_runtime_memory_audit.py'),'__name__':'queue_lifetime_adapter'};exec(compile(code,ns['__file__'],'exec'),ns)
 manifest=json.loads((ROOT/'ci/s3_runtime_memory_sources.json').read_text())
 archived=json.loads((OUT/'allocation-sdk/sources.json').read_text())
 compared=[]
 for row in archived['sources']:
  path=row['path'].removeprefix('components/')
  if path in manifest['sources']:
   assert row['sha256']==manifest['sources'][path],path;compared.append(path)
 memory=json.loads((OUT/'memory.json').read_text())
 # This build identity is the source ledger's pinned SDK, not a new measured build.
 memory['build']={'IDF_commit':manifest['IDF_commit']}
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);(td/'result.json').write_text(json.dumps(memory))
  (td/'s3_raw_probe.elf.gz').write_bytes((OUT/'memory-sdk/s3_queue_memory_probe.elf.gz').read_bytes())
  (td/'sdkconfig.json.gz').write_bytes((OUT/'memory-sdk/sdkconfig.json.gz').read_bytes())
  result=ns['audit'](td)
 from ci.s3_raw_watchdog_budget import report as watchdog
 tasks=dict(ELF_sha256=result['input_sha256']['ELF'],checks=[dict(passed=result['types']['twdt_entry']==16 and result['types']['twdt_obj']==16)],watchdog=dict(types={n:result['types'][n] for n in ('twdt_entry','twdt_obj')}))
 result['watchdog']=watchdog(tasks,result)
 assert all(c['passed'] for c in result['watchdog']['checks'])
 result['input_profile']='reports/s3-queue-owner/memory-sdk'
 assert result['all_scoped_checks_pass'],result['checks']
 allocation=json.loads((OUT/'allocations.json').read_text())
 assert result['phases']['fresh_vectors']['SPI_live']['requested_bytes']==allocation['known_driver_lower_bound_bytes']
 result.update(scope=__doc__,queue_depth=2,transfer_bytes=16384,archived_sources_rechecked=compared,source_identity_note='Archived public source hashes match prior pinned SDK ledger; CI build uses espressif/idf:v5.5.1, not a newly attested container digest.',adapted_audit_sha256=hashlib.sha256(code.encode()).hexdigest())
 paths=[Path(__file__),ROOT/'ci/s3_runtime_memory_audit.py',ROOT/'ci/s3_startup_memory_bound.py',ROOT/'ci/s3_raw_watchdog_budget.py',ROOT/'experiments/s3_raw_tasks.c',ROOT/'reports/s3-raw-tasks/sources.json',ROOT/'ci/s3_runtime_memory_sources.json',OUT/'memory.json',OUT/'allocations.json',OUT/'allocation-sdk/sources.json']
 result['source_sha256']={str(p.resolve().relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 return result
if __name__=='__main__':
 r=audit();(OUT/'lifetime-memory.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r['phases'],indent=2))
