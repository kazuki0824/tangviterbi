`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,iv=0,request=0,ordy=0;reg[7:0]id=0;
wire ir,committed,request_ready,ov,last,retired,fault,sf,qf;
wire[7:0]od;wire[9:0]held;
wire wv,wr,ack,acktag,rr,rrdy,rv,rt,rl,cv,cr,cw,bwv,bwr,brv,done;
wire[20:0]wa,ra,ca;wire[31:0]wd,rd,bwd,brd;
s3_rs_psram_store store(clk,rst,qf,iv,ir,id,committed,request,request_ready,
 ov,ordy,od,last,retired,wv,wr,wa,wd,ack,rr,rrdy,ra,rv,rt,rd,rl,held,sf);
s3_psram_queue queue(clk,rst,1'b0,wv,wr,1'b0,wa,wd,ack,acktag,
 rr,rrdy,ra,rv,rt,rd,rl,cv,cr,cw,ca,bwv,bwr,bwd,brv,brd,done,1'b0,qf);
assign fault=sf||qf;
// A burst is non-stallable after its fixed command/latency region, matching
// the actual controller. Request addresses are in 32-bit words.
reg active=0,writing=0,finish_pending=0;reg[20:0]address=0;integer beat=0,timer=0,cooldown=0;
reg[31:0]memory[0:32767];reg br_valid=0,burst_done=0;reg[31:0]br_data=0;
assign cr=!active&&cooldown==0;assign bwr=active&&writing&&timer>=12;
assign brv=br_valid;assign brd=br_data;assign done=burst_done;
always @(posedge clk)begin
 br_valid<=0;burst_done<=finish_pending;finish_pending<=0; if(cooldown>0)cooldown<=cooldown-1;
 if(!rst)begin active<=0;timer<=0;beat<=0;finish_pending<=0;end
 else if(cv&&cr)begin active<=1;writing<=cw;address<=ca;beat<=0;timer<=0;end
 else if(active)begin
  timer<=timer+1;
  if(timer>=(writing?12:12))begin
   if(writing)begin
    if(!bwv)$fatal(1,"write burst underflow");
    memory[address+beat]<=bwd;
   end else begin br_valid<=1;br_data<=memory[address+beat];end
   if(beat==63)begin active<=0;finish_pending<=1;cooldown<=0;end else beat<=beat+1;
  end
 end
end
integer commits=0,retires=0,maxcycles=0,i,j,c,start,elapsed;
reg[7:0]hold_data;reg hold_last;
reg stalled=0;reg[7:0]previous_data;reg previous_last;
always @(posedge clk)if(rst)begin
 if(fault)$fatal(1,"store/queue fault");
 if(stalled&&(!ov||od!==previous_data||last!==previous_last))$fatal(1,"backpressured output changed");
 stalled<=ov&&!ordy;previous_data<=od;previous_last<=last;
 if(committed)commits=commits+1;
 if(retired)retires=retires+1;
end
function[7:0]pattern;input integer blockno,byteoffset;
begin pattern=(blockno*73+byteoffset*29)^(byteoffset>>2);end endfunction
task write_block;input integer blockno;
integer offset,cycles;
begin
 offset=0;cycles=0;
 while(offset<204)begin
  @(negedge clk);iv=cycles%10==0;id=pattern(blockno,offset);
  @(posedge clk);if(iv&&ir)offset=offset+1;
  #1;cycles=cycles+1;if(cycles>4000)$fatal(1,"write deadlock");
 end
 @(negedge clk);iv=0;
 while(!committed)begin @(negedge clk);cycles=cycles+1;if(cycles>4000)$fatal(1,"commit deadlock");end
 if(cycles>maxcycles)maxcycles=cycles;
 if(cycles>2532)$fatal(1,"28.135828us write service budget exceeded %0d",cycles);
 for(j=51;j<64;j=j+1)if(memory[(blockno%512)*64+j]!==0)$fatal(1,"padding leak");
end endtask
task read_block;input integer blockno;
integer offset,cycles;
begin
 @(negedge clk);request=1;
 while(!request_ready)@(negedge clk);
 @(negedge clk);request=0;offset=0;cycles=0;
 while(!retired)begin
  ordy=cycles%17!=3&&cycles%17!=4;
  @(posedge clk);
  if(ov&&ordy)begin
   if(od!==pattern(blockno,offset)||last!==(offset==203))$fatal(1,"read mismatch block=%0d offset=%0d",blockno,offset);
   offset=offset+1;
  end
  #1;cycles=cycles+1;
  @(negedge clk);if(cycles>2000)$fatal(1,"read deadlock");
 end
 if(offset!=204)$fatal(1,"missing codeword bytes");ordy=0;
end endtask
initial begin
 repeat(3)@(negedge clk);rst=1;
 // Fill the entire ring. Codewords remain unavailable until physical writes
 // commit, and ring full prevents accepting another input byte.
 for(i=0;i<512;i=i+1)write_block(i);
 @(negedge clk);if(held!=512||ir)$fatal(1,"full slot ownership");
 iv=1;id=8'hfe;repeat(19)begin @(negedge clk);if(ir||held!=512)$fatal(1,"full overwrite");end iv=0;
 // Read into the actual queue buffer, then hold the consumer. The slot must
 // not be released on PSRAM read/DMA completion, and its output stays stable.
 request=1;@(negedge clk);request=0;
 while(!ov)@(negedge clk);hold_data=od;hold_last=last;
 repeat(29)begin @(negedge clk);if(!ov||od!==hold_data||last!==hold_last||held!=512)$fatal(1,"stalled slot lease");end
 c=0;ordy=1;
 while(!retired)begin @(posedge clk);if(ov&&ordy)begin
  if(od!==pattern(0,c)||last!==(c==203))$fatal(1,"first read mismatch");c=c+1;
 end #1;@(negedge clk);end ordy=0;
 if(c!=204||held!=511)$fatal(1,"first retire");
 // Reuse the freed slot after wrapping its 9-bit physical index.
 write_block(512);
 for(i=1;i<513;i=i+1)read_block(i);
 repeat(3)@(negedge clk);
 if(held!=0||commits!=513||retires!=513)$fatal(1,"count/ownership accounting");
 // Simultaneous producer and consumer share the physical burst engine. Delay
 // the first consumer by an RPC-sized 204-codeword batch, then overlap reads
 // with later writes; verify every byte after multiple pointer wraps.
 fork
  begin:writer integer w;
   for(w=513;w<1025;w=w+1)write_block(w);
  end
  begin:reader integer r;
   while(commits<717)@(negedge clk);
   for(r=513;r<1025;r=r+1)read_block(r);
  end
 join
 repeat(3)@(negedge clk);
 if(held!=0||commits!=1025||retires!=1025)$fatal(1,"concurrent ownership accounting");
 // Dirty reset cannot expose retained physical bytes as a new codeword.
 stalled=0;
 iv=1;repeat(37)@(negedge clk);rst=0;iv=0;repeat(3)@(negedge clk);rst=1;
 repeat(3)@(negedge clk);if(held!=0||request_ready||ov)$fatal(1,"dirty reset stale data");
 $display("PASS codewords=1025 bytes=209100 slots=512 wrap=2 concurrent=512 stalled_consumer=29 max_commit_cycles=%0d",maxcycles);$finish;
end
initial begin #40000000;$fatal(1,"global deadlock");end
endmodule
