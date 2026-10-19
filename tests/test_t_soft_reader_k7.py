"""Finite real-K7 integration under a hypothetical 160-clock SDRAM grant."""
import hashlib,json,os,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,cv=0;wire cr;reg[62:0]ca=0;reg[47:0]cl={16'd4032,16'd2880,16'd576};
wire[1:0]live;wire reuse,qv,rr,tv,tf;wire[20:0]qa;wire[1:0]tc;wire[7:0]td;
reg qr=0,rv=0;reg[255:0]rd=0;
wire tr;
t_soft_reader reader(clk,resetn,cv,cr,ca,cl,live,reuse,qv,qr,qa,rv,rr,rd,tv,tr,tc,td,tf);
reg[7:0]soft_words[0:44967];
wire ir,ov,ob;wire[1:0]oc;wire[3:0]fault;
reg choose_s,locked=0,locked_s=0;reg[1:0]phase=0;
integer available_s=0,consumed_s=0,acc=0;
wire iv=choose_s ? available_s>consumed_s : tv;
wire[1:0]ic=choose_s ? 2'd3 : tc;
wire[7:0]data=choose_s ? soft_words[14976+consumed_s] : td;
assign tr=!choose_s && ir;
shared_k7_depuncture_stream k7(clk,resetn,12'h924,iv,ir,ic,data,ov,ob,oc,fault);
always @*begin
 choose_s=available_s>consumed_s && (phase!=2 || !tv);
 if(locked)choose_s=locked_s;
end
integer got[0:3],step[0:3],per_symbol[0:2];
integer cycle,i,j,base,bank,c,offset,delay_left=-1,requests=0,max_s=0;
integer t_offset[0:2],first_done[0:2],s=0,f;reg pending=0;
initial begin
 $readmemh("soft.hex",soft_words);f=$fopen("bits.txt","w");
 t_offset[0]=0;t_offset[1]=1152;t_offset[2]=6912;
 for(i=0;i<3;i=i+1)first_done[i]=-1;
 per_symbol[0]=504;per_symbol[1]=2520;per_symbol[2]=3528;
 for(i=0;i<4;i=i+1)begin got[i]=0;step[i]=0;end
 for(cycle=0;cycle<125000;cycle=cycle+1)begin
  @(negedge clk);resetn=cycle>2;cv=(cycle==10 || cycle==40105);
  base=cycle==10?0:1872;ca={21'd0,21'd0,21'd0};
  ca[20:0]=base;ca[41:21]=base+144;ca[62:42]=base+864;
  qr=!pending && cycle%160==80;
  if(pending && delay_left==0)rv=1;
  if(pending && delay_left>0)delay_left=delay_left-1;
  @(posedge clk);
  if(resetn)begin
   if(cv && !cr)$fatal(1,"symbol bank unavailable");
   if(iv && !ir)begin locked<=1;locked_s<=choose_s;end
   if(iv && ir)begin
    locked<=0;phase<=phase==2?0:phase+1;
    if(choose_s)consumed_s<=consumed_s+1;
    else begin
     if(td!==soft_words[t_offset[tc]+got[tc]])$fatal(1,"T soft byte corruption");
    end
    got[ic]=got[ic]+1;
   end
   if(qv && qr)begin
    pending=1;delay_left=16;requests=requests+1;
    bank=qa>=1872;offset=qa-bank*1872;
    if(offset<144)begin c=0;offset=offset*4;end
    else if(offset<864)begin c=1;offset=(offset-144)*4;end
    else begin c=2;offset=(offset-864)*4;end
    for(j=0;j<32;j=j+1)rd[j*8+:8]=soft_words[t_offset[c]+bank*(c==0?576:c==1?2880:4032)+offset+j];
   end
   if(rv && rr)pending=0;
   if(cycle<80200 && available_s<29992)begin
    acc=acc+404040000;
    if(acc>=1080000000)begin acc=acc-1080000000;available_s<=available_s+1;end
   end
   if(available_s-consumed_s>max_s)max_s=available_s-consumed_s;
   if(available_s-consumed_s>256)$fatal(1,"S finite FIFO overflow");
   if(k7.stream.core.tick && k7.stream.core.initialized[k7.stream.core.context_id] && k7.stream.core.phase)begin
    c=k7.stream.core.context_id;step[c]=step[c]+1;
    if(c<3 && step[c]==per_symbol[c])begin first_done[c]=cycle-10;if(cycle>=80200)$fatal(1,"T first symbol deadline");end
   end
  end
  #1;if(tf || fault)$fatal(1,"fault");
  if(ov)$fdisplay(f,"%0d %0d",oc,ob);
  if(!pending)rv=0;
 end
 if(got[0]!=1152 || got[1]!=5760 || got[2]!=8064 || got[3]!=29992 || live)$fatal(1,"not drained");
 if(requests!=468)$fatal(1,"request count");
 $display("PASS requests=%0d T_bytes=%0d/%0d/%0d S_bytes=%0d S_peak=%0d first_T_steps_done=%0d/%0d/%0d",requests,got[0],got[1],got[2],got[3],max_s,first_done[0],first_done[1],first_done[2]);
 $finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ReaderK7Test(unittest.TestCase):
 def test_two_mode1_symbols_and_paced_S(self):
  rng=random.Random(19032026);streams=[];bits=[]
  for size in (1152,5760,8064,29992):
   b=[rng.randrange(2) for _ in range(size*7//8)];bits.append(b);state=0;soft=[]
   for j,bit in enumerate(b):
    state=((state<<1)|bit)&127
    for g,mask in ((0o171,'1000101'),(0o133,'1111010')):
     if mask[j%7]=='1':soft.append(230 if (state&g).bit_count()%2 else 25)
   self.assertEqual(len(soft),size);streams+=soft
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'soft.hex').write_text(''.join(f'{x:02x}\n' for x in streams));(p/'tb.sv').write_text(TB)
   files=['t_soft_reader.sv','shared_k7_context.sv','shared_k7_stream.sv','s3_depuncture.sv','shared_k7_depuncture_stream.sv']
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),*(str(ROOT/'rtl'/f)for f in files)],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],cwd=d,text=True,capture_output=True,timeout=180)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout.strip())
   actual=[[]for _ in range(4)]
   for line in (p/'bits.txt').read_text().splitlines():
    c,b=map(int,line.split());actual[c].append(b)
   for c in range(4):
    self.assertGreater(len(actual[c]),len(bits[c])-256)
    self.assertEqual(actual[c][64:],bits[c][64:len(actual[c])],f'context {c}')
   print('decoded output counts',list(map(len,actual)))
  result=dict(scope=__doc__,summary=r.stdout.strip(),decoded_output_counts=list(map(len,actual)),all_contexts_known_bits_match_after_64=True,source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in [Path(__file__),*(ROOT/'rtl'/x for x in files)]},actual_service_included=False,S_FIFO_RTL_included=False,whole_receiver_verified=False)
  if os.environ.get('T_SOFT_K7_REPORT'):Path(os.environ['T_SOFT_K7_REPORT']).write_text(json.dumps(result,indent=2)+'\n')
