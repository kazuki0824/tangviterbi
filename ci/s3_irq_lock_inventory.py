"""Inventory every direct allocator spinlock user in pinned source and ELF."""
import gzip
import hashlib
import io
import json
import re
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'esp_intr_mark_shared','esp_intr_reserve','shared_intr_isr',
          'non_shared_intr_isr','esp_intr_alloc_intrstatus_bind','esp_intr_set_in_iram',
          'intr_free_for_current_cpu','esp_intr_enable','esp_intr_disable',
          'esp_intr_noniram_disable','esp_intr_noniram_enable'}

def report():
    path=ROOT/'reports/s3-raw-tasks/sources/intr_alloc.c'
    source=path.read_text();rows=[]
    for match in re.finditer(r'^\w[^;{}]*?\b(\w+)\([^;{}]*\)\n\{',source,re.M):
        start=match.end();i=start;depth=1
        while depth:
            depth+=(source[i]=='{')-(source[i]=='}');i+=1
        body=source[start:i]
        count=len(re.findall(r'portENTER_CRITICAL\w*\(&spinlock\)',body))
        if count:rows.append(dict(function=match[1],line=source.count('\n',0,match.start())+1,critical_entries=count))
    assert {row['function'] for row in rows}==EXPECTED
    manifest=json.loads((ROOT/'reports/s3-raw-tasks/sources.json').read_text())
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest==manifest['intr_alloc.c']['sha256']
    data=gzip.decompress((ROOT/'reports/s3-raw-tasks/sdk-launcher/n16r8-late-stacks-no-phy-nvs-raw-only-spi/s3_raw_probe.elf.gz').read_bytes())
    elf_hash=hashlib.sha256(data).hexdigest()
    assert elf_hash=='7ee25471a6dc96c056c2afd883cf4f70282fd186be920cced7dddefa40554fc7'
    symbols=ELFFile(io.BytesIO(data)).get_section_by_name('.symtab')
    wrappers={name:[dict(address=hex(s['st_value']),size=s['st_size'])
        for s in symbols.get_symbol_by_name(name) or []]
        for name in ('shared_intr_isr','non_shared_intr_isr')}
    assert wrappers['shared_intr_isr'] and not wrappers['non_shared_intr_isr']
    return dict(source_sha256=digest,elf_sha256=elf_hash,lock_users=rows,
                wrapper_symbols=wrappers,actual_runtime_shared_irqs_known=False,
                lock_wait_upper_cycles=None,receiver_adopted=False)

if __name__=='__main__':
    (ROOT/'reports/s3-irq-lock-inventory/result.json').write_text(json.dumps(report(),indent=2)+'\n')
