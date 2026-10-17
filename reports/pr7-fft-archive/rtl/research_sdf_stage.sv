// Experimental radix-2 DIF SDF stage. Not a qualified complete receiver.
// EXTERNAL=1 exposes a *synchronous 32-bit RAM* port, NOT an SDRAM/PHY.
// External read data is registered on a read_enable clock and retained until
// the next read. Write is acknowledged at the write_enable clock. No bus timing
// or physical SDRAM capacity is claimed by this abstraction.
module research_sdf_stage #(
 parameter integer SHIFT=3,
 parameter integer EXTERNAL=0
)(
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,input wire [31:0] in_data,
 output reg out_valid,input wire out_ready,output reg [31:0] out_data,
 input wire external_ready,
 output wire external_read_enable,
 output wire [((SHIFT>0)?SHIFT:1)-1:0] external_read_addr,
 input wire [31:0] external_read_data,
 output wire external_write_enable,
 output wire [((SHIFT>0)?SHIFT:1)-1:0] external_write_addr,
 output wire [31:0] external_write_data,
 output reg overflow
);
 localparam integer D=(1<<SHIFT);
 localparam integer ADDR_W=(SHIFT>0)?SHIFT:1;
 reg [SHIFT:0] pos;
 reg primed,pending,held_first,held_output;
 reg [ADDR_W-1:0] held_addr;
 reg [31:0] held_data;
 reg [12:0] held_phase;
 wire [ADDR_W-1:0] addr=(pos & (D-1));
 wire first_half=!pos[SHIFT];
 wire [12:0] selected_phase=({{(13-ADDR_W){1'b0}},addr} << (12-SHIFT));
 // SHIFT ranges from 0 through 12 in the supported N<=8192.
 wire [12:0] rom_phase=pending ? held_phase : selected_phase;
 wire signed [17:0] tw_re,tw_im;
 research_sdf_twiddle coeff(clk,rom_phase,tw_re,tw_im);
 wire port_ready=(EXTERNAL==0)||external_ready;
 wire slot_ready=!out_valid||out_ready;
 assign in_ready=resetn&&!pending&&slot_ready&&port_ready;
 wire take=in_valid&&in_ready;
 wire commit=resetn&&pending&&slot_ready&&port_ready;
 assign external_read_enable=(EXTERNAL!=0)&&take;
 assign external_read_addr=addr;
 assign external_write_enable=(EXTERNAL!=0)&&commit;
 assign external_write_addr=held_addr;
 reg [31:0] internal_q;
 generate if(EXTERNAL==0) begin: local_delay
   (* ram_style="block" *) reg [31:0] mem[0:D-1];
   always @(posedge clk) begin
     if(take) internal_q<=mem[addr];
     if(commit) mem[held_addr]<=external_write_data;
   end
 end endgenerate
 wire [31:0] old_word=(EXTERNAL!=0)?external_read_data:internal_q;
 wire signed [16:0] sr=$signed({old_word[15],old_word[15:0]})+
                         $signed({held_data[15],held_data[15:0]});
 wire signed [16:0] si=$signed({old_word[31],old_word[31:16]})+
                         $signed({held_data[31],held_data[31:16]});
 wire signed [16:0] dr=$signed({old_word[15],old_word[15:0]})-
                         $signed({held_data[15],held_data[15:0]});
 wire signed [16:0] di=$signed({old_word[31],old_word[31:16]})-
                         $signed({held_data[31],held_data[31:16]});
 wire signed [15:0] sum_r=sr>>>1,sum_i=si>>>1;
 wire signed [15:0] dif_r=dr>>>1,dif_i=di>>>1;
 wire signed [35:0] mr=$signed(dif_r)*$signed(tw_re)-
                       $signed(dif_i)*$signed(tw_im);
 wire signed [35:0] mi=$signed(dif_r)*$signed(tw_im)+
                       $signed(dif_i)*$signed(tw_re);
 function automatic signed [35:0] round_q16(input signed [35:0] x);
   begin
     if(x>=0) round_q16=(x+36'sd32768)>>>16;
     else round_q16=-(((-x)+36'sd32768)>>>16);
   end
 endfunction
 function automatic [15:0] sat16(input signed [35:0] x);
   begin
     if(x>36'sd32767) sat16=16'h7fff;
     else if(x< -36'sd32768) sat16=16'h8000;
     else sat16=x[15:0];
   end
 endfunction
 wire signed [35:0] zr=round_q16(mr),zi=round_q16(mi);
 wire clipped=(zr>36'sd32767)||(zr< -36'sd32768)||
              (zi>36'sd32767)||(zi< -36'sd32768);
 wire [31:0] new_data=held_first?held_data:
                           {sat16(zi),sat16(zr)};
 assign external_write_data=new_data;
 wire [31:0] produced=held_first?old_word:{sum_i,sum_r};
 always @(posedge clk) begin
   if(!resetn) begin
     pos<=0;primed<=0;pending<=0;held_first<=0;
     held_output<=0;held_addr<=0;held_data<=0;held_phase<=0;
     out_valid<=0;out_data<=0;overflow<=0;
   end else begin
     if(out_valid&&out_ready) out_valid<=0;
     if(take) begin
       pending<=1;
       held_addr<=addr;held_data<=in_data;held_first<=first_half;
       held_phase<=selected_phase;
       held_output<=primed||!first_half;
       pos<=pos+1'b1;
       if(pos==(D-1)) primed<=1;
     end
     if(commit) begin
       pending<=0;
       out_valid<=held_output;
       out_data<=produced;
       if(!held_first&&clipped) overflow<=1;
     end
   end
 end
endmodule
