#!/usr/bin/env python3
"""Paired noisy-symbol RTL comparison; not a receiver C/N qualification."""
from pathlib import Path
import hashlib,json,math,random,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk_precision import metric_source,viterbi_source,bound

def main():
    out=ROOT/'build/s3-precision-ber';out.mkdir(parents=True,exist_ok=True)
    n=16384;warmup=128;seed=0x14082324;shifts=(22,23,24,25)
    conditions=[(.65,None)]+[(a,snr) for a in (.25,.65) for snr in (6,10,14)]
    points={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))
            for k,label in enumerate((0,1,3,2,4,5,7,6))}
    samples=[];wanted=[];metadata=[]
    for epoch,(amplitude,snr) in enumerate(conditions):
        rng=random.Random(seed+epoch);state=37;pairs=[];clipped=0
        sigma=0 if snr is None else amplitude*32768/math.sqrt(2*10**(snr/10))
        for _ in range(n):
            pair=rng.randrange(4);pairs.append(pair);state=((state<<1)|(pair&1))&127
            x=(state&0o171).bit_count()&1;y=(state&0o133).bit_count()&1
            p=points[((pair>>1)<<2)|(y<<1)|x]
            iq=[round(v*amplitude+rng.gauss(0,sigma)) for v in p]
            clipped+=int(any(v< -32768 or v>32767 for v in iq))
            i,q=[min(32767,max(-32768,v)) for v in iq]
            samples.append(((q&65535)<<16)|(i&65535))
        wanted.append(pairs)
        metadata.append(dict(epoch=epoch,amplitude_Q15_full_scale=amplitude,Es_N0_dB=snr,
            noise_sigma_Q15_per_axis=sigma,clipped_symbols=clipped,input_symbols=n,seed=seed+epoch))
    (out/'input.hex').write_text(''.join(f'{w:08x}\n' for w in samples))
    declarations=[];checks=[];writes=[];paths=[]
    for shift in shifts:
        m=f'metric{shift}';v=f'viterbi{shift}'
        (out/f'{m}.sv').write_text(metric_source(shift).replace('module s3_tc8psk_metric_folded',f'module {m}'))
        (out/f'{v}.sv').write_text(viterbi_source(shift).replace('module s3_tc8psk',f'module {v}'))
        paths += [f'{m}.sv',f'{v}.sv']
        declarations.append(f'''wire ir{shift},mv{shift},mr{shift},ov{shift};wire[35:0]cost{shift};wire[3:0]choice{shift};wire[1:0]bits{shift};
{m} m{shift}(clk,rst,iv,ir{shift},w[15:0],w[31:16],mv{shift},mr{shift},cost{shift},choice{shift});
{v} v{shift}(clk,rst,mv{shift},mr{shift},cost{shift},choice{shift},ov{shift},bits{shift});''')
        if shift!=22:checks.append(f'if(ir{shift}!==ir22||ov{shift}!==ov22)$fatal(1,"control mismatch shift{shift}");')
        writes.append(f'$fwrite(f," %0d",bits{shift});')
    (out/'tb.sv').write_text(f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0;reg[31:0]w=0;
{chr(10).join(declarations)}
reg[31:0]words[0:{len(samples)-1}];integer e,s,cycle=0,f,got=0;
initial begin $readmemh("input.hex",words);f=$fopen("output.txt","w");
for(e=0;e<{len(conditions)};e=e+1)begin
 @(negedge clk);rst=0;iv=0;repeat(4)@(negedge clk);rst=1;s=0;
 while(s<{n})begin
  @(negedge clk);iv=cycle%31!=7;w=words[e*{n}+s];
  @(posedge clk);if(iv&&ir22)s=s+1;cycle=cycle+1;
 end
 @(negedge clk);iv=0;repeat(500)@(negedge clk);
end $fclose(f);$display("PASS paired_symbols=%0d",got);$finish;end
always @(posedge clk)begin #1;if(rst)begin
 {chr(10).join(checks)}
 if(ov22)begin $fwrite(f,"%0d",e);{''.join(writes)}$fwrite(f,"\\n");got=got+1;end
end end
endmodule''')
    for cmd in (['iverilog','-g2012','-s','tb','-o','sim',*paths,'tb.sv'],['vvp','sim']):
        p=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=600)
        with (out/'simulation.log').open('a') as f:f.write(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
    actual=[[[] for _ in shifts] for _ in conditions]
    for line in (out/'output.txt').read_text().splitlines():
        epoch,*values=map(int,line.split())
        for j,v in enumerate(values):actual[epoch][j].append(v)
    results=[]
    for epoch,meta in enumerate(metadata):
        length=len(actual[epoch][0]);assert n-300<length<=n
        assert all(len(a)==length for a in actual[epoch])
        reference=actual[epoch][0][warmup:];truth=wanted[epoch][warmup:length]
        counts=[]
        for j,shift in enumerate(shifts):
            got=actual[epoch][j][warmup:]
            e0=sum((a^b)&1 for a,b in zip(got,truth));e1=sum(((a^b)>>1)&1 for a,b in zip(got,truth))
            if epoch==0:assert e0+e1==0,(shift,e0,e1)
            differs=sum((a^b).bit_count() for a,b in zip(got,reference))
            worsened=sum(((a^b)&~(r^b)&3).bit_count() for a,r,b in zip(got,reference,truth))
            improved=sum(((r^b)&~(a^b)&3).bit_count() for a,r,b in zip(got,reference,truth))
            assert worsened-improved==e0+e1-sum((a^b).bit_count() for a,b in zip(reference,truth))
            counts.append(dict(cost_shift=shift,checked_information_bits=2*len(truth),coded_B0_errors=e0,
                uncoded_B1_errors=e1,total_bit_errors=e0+e1,empirical_BER=(e0+e1)/(2*len(truth)),
                output_bit_differences_from_shift22=differs,paired_additional_errors=worsened,
                paired_corrected_errors=improved))
        results.append(dict(**meta,decoded_symbols=length,discarded_startup_symbols=warmup,quantizers=counts))
    result=dict(scope=__doc__,result='completed',conditions=results,proofs={s:bound(s) for s in shifts},
        sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.sv')},
        vectors_sha256=hashlib.sha256((out/'input.hex').read_bytes()).hexdigest(),
        decoded_sha256=hashlib.sha256((out/'output.txt').read_bytes()).hexdigest(),
        uncertainty='One deterministic seed per condition; correlated trellis errors; no statistical equivalence or C/N threshold claimed.',
        excluded=['RF acquisition/carrier/timing/AGC','TMCC/frame/deinterleaving','RS and transport stream'],
        receiver_adopted=False,safe_to_flash=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
