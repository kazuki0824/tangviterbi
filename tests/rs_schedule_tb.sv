`timescale 1ns/1ps
module rs_schedule_tb;
parameter integer FAST_CHIEN=1;
reg clk=0; always #5 clk=~clk;
reg resetn=0, in_valid=0;
reg [7:0] in_byte=0;
wire ready, valid, fail;
wire [7:0] data_out;
rs204_188_compact dut(clk,resetn,in_valid,ready,in_byte,valid,data_out,fail);
integer a, b, k, degree, cycle, outputs, accepted, maxcycles=0;
integer j, p, expected_cycles;
reg [7:0] product, x, y;
reg [7:0] poly[0:8], positions[0:7], root;
function automatic [7:0] gf;
 input [7:0] left, right;
 reg [7:0] xx, yy, result;
 integer bitno;
 begin
  xx=left; yy=right; result=0;
  for(bitno=0;bitno<8;bitno=bitno+1) begin
   if(yy[0])result=result^xx;
   xx={xx[6:0],1'b0} ^ (xx[7]?8'h1d:8'h00); yy=yy>>1;
  end
  gf=result;
 end
endfunction
initial begin
 // Check the generated ROM with multiplication, independently of its pow254 generator.
 #1;
 if(dut.inverse_rom[0] !== 0)$fatal(1,"zero inverse convention");
 for(a=1;a<256;a=a+1) begin
  x=a; y=dut.inverse_rom[a]; product=0;
  for(k=0;k<8;k=k+1) begin
   if(y[0])product=product^x;
   x={x[6:0],1'b0} ^ (x[7]?8'h1d:8'h00); y=y>>1;
  end
  if(product !== 1)$fatal(1,"inverse ROM mismatch a=%0d",a);
 end
 // Path injection is a control-flow test, not an RF/RS golden vector.
 // A nonzero discrepancy after 8..15 leading zeros requests degree 9..16.
 // These cases must finish early and preserve the received payload.
 for(degree=9;degree<=16;degree=degree+1) begin
  @(negedge clk); resetn=0; in_valid=0;
  repeat(3) @(negedge clk); resetn=1; accepted=0;
  while(accepted<204) begin
   in_valid=1; in_byte=accepted;
   @(posedge clk); if(ready)accepted=accepted+1;
   @(negedge clk);
  end
  in_valid=0;
  // BM_INIT has not executed; establish an adversarial syndrome trajectory.
  if(dut.state !== dut.ST_BM_INIT)$fatal(1,"bad injection point");
  for(k=0;k<16;k=k+1) dut.synd[k]=(k==degree-1)?8'h01:8'h00;
  outputs=0;
  for(cycle=0;cycle<2364 && !ready;cycle=cycle+1) begin
   @(posedge clk); #1;
   if(valid) begin
    if(data_out !== (outputs & 255))$fatal(1,"early fail modified payload");
    if(!fail)$fatal(1,"early fail missing flag");
    outputs=outputs+1;
   end
   @(negedge clk);
  end
  if(!ready || outputs!=188)$fatal(1,"degree %0d failed to terminate",degree);
  if(cycle+204>maxcycles)maxcycles=cycle+204;
 end
 // Independent polynomial construction covers all supported degrees, the
 // first/last positions, and every stored root. Test prefetch scheduling.
 positions[0]=0; positions[1]=203; positions[2]=1; positions[3]=202;
 positions[4]=50; positions[5]=100; positions[6]=150; positions[7]=200;
 for(degree=0;degree<=8;degree=degree+1) begin
  @(negedge clk); resetn=0;
  repeat(3) @(negedge clk); resetn=1;
  for(k=0;k<9;k=k+1)poly[k]=0;
  poly[0]=1;
  for(j=0;j<degree;j=j+1) begin
   root=1;
   for(p=0;p<positions[j];p=p+1)root=gf(root,2);
   for(k=j+1;k>0;k=k-1)poly[k]=poly[k-1]^gf(poly[k],root);
   poly[0]=gf(poly[0],root);
  end
  for(k=0;k<9;k=k+1)dut.lambda[k]=poly[k];
  dut.bm_l=degree; dut.state=dut.ST_CHIEN_INIT;
  dut.lambda_q=poly[degree]; dut.lambda_select=(1<<degree)>>1;
  for(cycle=0;cycle<2100 && dut.state!=dut.ST_FORNEY_INIT;cycle=cycle+1) begin
   @(posedge clk); #1; @(negedge clk);
  end
  expected_cycles=1+204*((degree==0?1:degree)+(FAST_CHIEN?0:(degree==0?1:2)));
  if(cycle!=expected_cycles)$fatal(1,"Chien cycles degree=%0d got=%0d expected=%0d",degree,cycle,expected_cycles);
  if(dut.error_count!=degree)$fatal(1,"root count degree=%0d got=%0d",degree,dut.error_count);
  for(j=0;j<degree;j=j+1) begin
   b=0;
   for(k=0;k<degree;k=k+1)if(dut.error_pos[k]==positions[j])b=b+1;
   if(b!=1)$fatal(1,"missing/duplicate root at %0d",positions[j]);
  end
 end
 $display("PASS: 256 inverse entries; degree 9..16 early-fail maximum=%0d; Chien degrees 0..8 with first/last roots and exact cycle counts",maxcycles);
 $finish;
end
endmodule
