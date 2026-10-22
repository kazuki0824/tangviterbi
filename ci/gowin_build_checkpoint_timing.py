"""Build a separate checkpoint timing reader without changing active P&R sources/objects."""
import difflib,hashlib,json,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT.parent;B=W/'nextpnr-build';D=ROOT/'reports/placement-compatible-pairs-timing';D.mkdir(exist_ok=True)
src=W/'nextpnr-source/common/kernel/command.cc';old=src.read_text()
needle='    if (vm.count("write")) {'
insert='''    // Diagnostic only: save estimated timing after placement, without routing.
    if (vm.count("no-route")) {
        ctx->assignArchInfo();
        timing_analysis(ctx.get(), true, true, true, false, true);
    }

'''
assert old.count(needle)==1
new=old.replace(needle,insert+needle);copy=B/'command-checkpoint-timing.cc';copy.write_text(new)
(D/'command.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='command.cc',tofile='command-checkpoint-timing.cc')))
lines=Path('/tmp/nextpnr-build-commands.txt').read_text().splitlines()
compile_cmd=shlex.split(next(s for s in lines if ' -c '+str(src) in s))
obj='himbaechel/CMakeFiles/nextpnr-himbaechel.dir/__/common/kernel/command.cc.o';outobj=str(B/'command-checkpoint-timing.o')
compile_cmd=[str(copy)if x==str(src)else x.replace(obj,outobj)for x in compile_cmd]
link=shlex.split(next(s for s in lines if ' -o nextpnr-himbaechel ' in s));assert link[:2]==[':','&&'] and link[-2:]==['&&',':'];link=link[2:-2]
link=[outobj if x==obj else 'nextpnr-checkpoint-timing' if x=='nextpnr-himbaechel' else x.replace('himbaechel/CMakeFiles/nextpnr-himbaechel.dir/link.d','checkpoint-timing-link.d')for x in link]
(D/'build-commands.json').write_text(json.dumps([compile_cmd,link],indent=2)+'\n')
with (D/'build.log').open('w')as f:
 for cmd in [compile_cmd,link]:subprocess.run(cmd,cwd=B,stdout=f,stderr=subprocess.STDOUT,check=True)
binary=B/'nextpnr-checkpoint-timing';binary.chmod(0o755)
(D/'build.json').write_text(json.dumps({'original_command_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'diagnostic_command_sha256':hashlib.sha256(copy.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'active_route_binary_sha256':hashlib.sha256((B/'nextpnr-himbaechel').read_bytes()).hexdigest(),'original_source_preserved':src.read_text()==old},indent=2)+'\n')
