"""Report every failing synchronous endpoint, without changing P&R decisions."""
import hashlib,json,subprocess,sys
from pathlib import Path
from patch_nextpnr_endpoint_report import EXTRA,patch_router,PIN
root=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==PIN
p=root/'common/kernel/timing.cc';old=p.read_text()
anchor='''            empty_clocks.erase(launch.clock);
        }
    }

    for (int i = 0; i < int(domain_pairs.size()); i++) {'''
assert old.count(anchor)==1 and 'diagnostics/final_report'not in old
extra=EXTRA.replace('''                    if (rank == 32)
                        break;
                    auto slack = ports.at(ep).domain_pairs.at(i).setup_slack;''','''                    auto slack = ports.at(ep).domain_pairs.at(i).setup_slack;
                    if (rank >= 32 && ctx->getDelayNS(slack) >= 0)
                        break;''')
extra=extra.replace('Endpoint diagnostic rank=%d cell=%s port=%s setup_slack_ns=%.6f','Endpoint diagnostic domain=%d rank=%d cell=%s port=%s setup_slack_ns=%.6f').replace('++rank, ep.cell.c_str(ctx)','i, ++rank, ep.cell.c_str(ctx)')
extra=extra.replace('                int rank = 0;','''                int negative = 0;
                for (const auto &ep : diagnostic_endpoints)
                    if (ctx->getDelayNS(ports.at(ep).domain_pairs.at(i).setup_slack) < 0)
                        ++negative;
                log_info("Endpoint coverage domain=%d clock=%s total=%zu failing=%d\\n",
                         i, launch.clock.c_str(ctx), diagnostic_endpoints.size(), negative);
                int rank = 0;''')
new=old.replace(anchor,anchor.replace('        }\n    }','        }\n'+extra+'    }',1))
assert new.replace(extra,'')==old
p.write_text(new)
r=root/'common/route/router1.cc';before=r.read_text();after=patch_router(before);r.write_text(after)
meta={'pin':PIN,'scope':'All negative-setup-slack synchronous endpoints in each modeled same-clock domain pair, plus at least 32 worst endpoints. Not every path, external IO STA or false-path proof.','timing_before_sha256':hashlib.sha256(old.encode()).hexdigest(),'timing_after_sha256':hashlib.sha256(new.encode()).hexdigest(),'router_before_sha256':hashlib.sha256(before.encode()).hexdigest(),'router_after_sha256':hashlib.sha256(after.encode()).hexdigest(),'placement_and_routing_decisions_unchanged':True}
(out/'patch.json').write_text(json.dumps(meta,indent=2)+'\n')
for name,a,b in [('timing',old,new),('router',before,after)]:
 import difflib
 (out/(name+'.patch')).write_text(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True))))
print(json.dumps(meta,indent=2))
