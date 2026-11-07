"""Mapped full fixture for the cycle-equivalent matrix arbiter experiment."""
import gzip, hashlib, json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_receiver_fft_tile_onehot_evidence import FILES
from ci.gowin_ff_site_audit import audit
D=ROOT/'reports/arbiter-matrix';D.mkdir(exist_ok=True)
files=[f.replace('sdram_client_arbiter_tile_grace_metadata.sv','sdram_client_arbiter_matrix_metadata.sv') for f in FILES]
meta={'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'whole_receiver_verified':False}
def run(cmd,name,timeout):
 (D/(name+'-command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
 with (D/(name+'.log')).open('w')as out:
  result=subprocess.run(cmd,cwd=ROOT/'reports/pr7-fft-archive',stdout=out,stderr=subprocess.STDOUT,timeout=timeout)
 assert result.returncode==0,(name,result.returncode)
ys=D/'synth.ys';ys.write_text('read_verilog -sv '+' '.join(str(ROOT/f) for f in files)+f'\nsynth_gowin -family gw2a -top shared_receiver_fft_tile_probe -nowidelut -json {D}/mapped.json\ncheck -assert\n')
run(['yosys','-Q','-s',str(ys)],'synth',600)
run([sys.executable,str(ROOT/'ci/gowin_materialize_ff_inputs.py'),str(D/'mapped.json'),str(D/'prebuffer.json')],'prebuffer',120)
run([sys.executable,str(ROOT/'ci/gowin_fold_identity_controls.py'),str(D/'prebuffer.json'),str(D/'folded.json')],'fold',180)
(D/'pins.cst').write_bytes((ROOT/'reports/shared-receiver-fft-tile-onehot-pack/pins.cst').read_bytes())
run(['nextpnr-himbaechel','--json',str(D/'folded.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={D}/pins.cst','--pack-only','--write',str(D/'packed.json')],'pack',180)
meta['full_fixture_bound']=audit(json.loads((D/'packed.json').read_text())['modules']['top']['cells'])
for f in files:assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==meta['source_sha256'][f]
for n in ['mapped.json','prebuffer.json','folded.json','packed.json','prebuffer.identity-proof.json','folded.controls-proof.json']:
 p=D/n;meta[n+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(D/(n+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
(D/'mapped-result.json').write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(meta['full_fixture_bound']))
