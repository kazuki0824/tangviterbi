// Four associative BSRAM page slots for RF(D711) and FFT(D712).
// Each stream has an independent ordered cursor. Identical offsets across
// streams cannot alias. Leases survive stalls until the final word is accepted.
module s3_pooled_page_store #(
 parameter ALLOW_FFT=1,INPUT_PORTS=2,parameter [19:0] RESET_RF_SEQUENCE=0,RESET_FFT_SEQUENCE=0
)(
 input wire clk,resetn,input wire[15:0]epoch,
 input wire[1:0]in_valid,output wire[1:0]in_ready,
 input wire[35:0]token0,token1,input wire upstream_fault,
 output wire RF_valid,input wire RF_ready,output wire[31:0]RF_data,RF_offset,output wire RF_last,
 output wire FFT_valid,input wire FFT_ready,output wire[31:0]FFT_data,FFT_offset,output wire FFT_last,
 output wire idle,fault
);
 wire[35:0]token[0:1];assign token[0]=token0;assign token[1]=token1;
 wire[1:0]request,grant,start,dv,dr,commit,gfault;
 wire[1:0]stream[0:1];wire[31:0]offset[0:1],data[0:1];
 genvar p;generate for(p=0;p<2;p=p+1)begin:g
 if(p<INPUT_PORTS)begin:enabled
  s3_page_guard guard(clk,resetn,epoch,in_valid[p],in_ready[p],token[p],grant[p],start[p],
   stream[p],offset[p],dv[p],dr[p],data[p],commit[p],gfault[p],request[p]);
 end else begin:disabled
  assign in_ready[p]=0;assign start[p]=0;assign stream[p]=0;assign offset[p]=0;
  assign dv[p]=0;assign data[p]=0;assign commit[p]=0;assign gfault[p]=0;assign request[p]=0;
 end
 end endgenerate
 reg[3:0]occupied,committed;reg[1:0]kinds[0:3],owned[0:1];
 reg[19:0]sequences[0:3],next_RF,next_FFT;reg[9:0]write_index[0:1];
 reg allocator_fault,rr;reg[1:0]picked[0:1],permitted;reg[3:0]available;
 reg duplicate,bad;reg[19:0]delta;integer ri,rj,pi,cj;
 always @*begin
  available=~occupied;permitted=0;picked[0]=0;picked[1]=0;
  for(ri=0;ri<2;ri=ri+1)begin
   duplicate=0;
   for(rj=0;rj<4;rj=rj+1)if(occupied[rj]&&kinds[rj]==stream[ri]&&sequences[rj]==offset[ri][31:12])duplicate=1;
   if(ri==1&&permitted[0]&&stream[0]==stream[1]&&offset[0]==offset[1])duplicate=1;
   delta=offset[ri][31:12]-(ALLOW_FFT&&stream[ri]!=1?next_FFT:next_RF);
   bad=(stream[ri]!=1&&stream[ri]!=2)||(!ALLOW_FFT&&stream[ri]==2)||delta>=4||duplicate;
   if(request[ri]&&!bad&&!fault)begin
    for(rj=3;rj>=0;rj=rj-1)if(available[rj])begin permitted[ri]=1;picked[ri]=rj;end
    if(permitted[ri])available[picked[ri]]=0;
   end
  end
 end
 assign grant=permitted;
 wire choose=dv[1]&&(!dv[0]||rr);
 assign dr[0]=!fault&&dv[0]&&!choose;assign dr[1]=!fault&&dv[1]&&choose;
 wire write_fire=|dr;
 (* ram_style="block" *) reg[31:0]memory[0:4095];
 always @(posedge clk)if(write_fire)memory[{owned[choose],write_index[choose]}]<=data[choose];
 // Two independent held outputs share one synchronous read port. A stalled
 // RF page never pins an FFT page behind it. Keep each stalled word immutable.
 reg[1:0]active,holding;reg read_pending,read_tag,read_rr;
 reg[1:0]read_slot[0:1],chosen_page[0:1];reg[9:0]read_index[0:1];
 reg[31:0]held_offset[0:1],held_value[0:1],read_value;reg[1:0]found;
 always @*begin
  found=0;chosen_page[0]=0;chosen_page[1]=0;
  for(pi=0;pi<4;pi=pi+1)begin
   if(committed[pi]&&kinds[pi]==1&&sequences[pi]==next_RF)begin found[0]=1;chosen_page[0]=pi;end
   if(ALLOW_FFT&&committed[pi]&&kinds[pi]==2&&sequences[pi]==next_FFT)begin found[1]=1;chosen_page[1]=pi;end
  end
 end
 wire[1:0]want_read=active&~holding;
 wire read_choose=want_read[1]&&(!want_read[0]||read_rr);
 wire launch=!read_pending&&(|want_read)&&!fault;
 always @(posedge clk)if(launch)read_value<=memory[{read_slot[read_choose],read_index[read_choose]}];
 assign RF_valid=holding[0]&&!fault;assign FFT_valid=ALLOW_FFT&&holding[1]&&!fault;
 assign RF_data=held_value[0];assign FFT_data=ALLOW_FFT?held_value[1]:32'd0;
 assign RF_offset=held_offset[0];assign FFT_offset=ALLOW_FFT?held_offset[1]:32'd0;
 assign RF_last=read_index[0]==1023;assign FFT_last=read_index[1]==1023;
 wire[1:0]take={FFT_valid&&FFT_ready,RF_valid&&RF_ready};
 assign idle=occupied==0&&active==0&&holding==0&&!read_pending;
 assign fault=allocator_fault||(|gfault)||upstream_fault;
 integer n;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   occupied<=0;committed<=0;next_RF<=RESET_RF_SEQUENCE;next_FFT<=RESET_FFT_SEQUENCE;allocator_fault<=0;rr<=0;
   active<=0;read_pending<=0;holding<=0;read_tag<=0;read_rr<=0;
   for(n=0;n<4;n=n+1)begin kinds[n]<=0;sequences[n]<=0;end
   for(n=0;n<2;n=n+1)begin owned[n]<=0;write_index[n]<=0;read_slot[n]<=0;read_index[n]<=0;held_offset[n]<=0;held_value[n]<=0;end
  end else if(!fault)begin
   for(n=0;n<2;n=n+1)begin
    if(request[n])begin
     if((stream[n]!=1&&stream[n]!=2)||(!ALLOW_FFT&&stream[n]==2)||
      (offset[n][31:12]-(ALLOW_FFT&&stream[n]!=1?next_FFT:next_RF))>=20'd4)allocator_fault<=1;
     for(cj=0;cj<4;cj=cj+1)if(occupied[cj]&&kinds[cj]==stream[n]&&sequences[cj]==offset[n][31:12])allocator_fault<=1;
     if(n==1&&grant[0]&&stream[0]==stream[1]&&offset[0]==offset[1])allocator_fault<=1;
    end
    if(grant[n])begin
     owned[n]<=picked[n];write_index[n]<=0;occupied[picked[n]]<=1;
     kinds[picked[n]]<=ALLOW_FFT?stream[n]:2'd1;sequences[picked[n]]<=offset[n][31:12];
    end
    if(commit[n])committed[owned[n]]<=1;
   end
   if(write_fire)begin write_index[choose]<=write_index[choose]+1'b1;rr<=!choose;end
   for(n=0;n<2;n=n+1)begin
    if(!active[n]&&found[n])begin
     active[n]<=1;read_slot[n]<=chosen_page[n];read_index[n]<=0;held_offset[n]<={sequences[chosen_page[n]],12'd0};
    end
    if(take[n])begin
     holding[n]<=0;read_index[n]<=read_index[n]+1'b1;
     if(read_index[n]==1023)begin
      active[n]<=0;occupied[read_slot[n]]<=0;committed[read_slot[n]]<=0;
      if(n==0)next_RF<=next_RF+1'b1;else next_FFT<=next_FFT+1'b1;
     end
    end
   end
   if(launch)begin read_pending<=1;read_tag<=read_choose;read_rr<=!read_choose;end
   if(read_pending)begin read_pending<=0;held_value[read_tag]<=read_value;holding[read_tag]<=1;end
  end
 end
endmodule
