// Research FFT ONLY. Shared 4-real-multiply datapath, lossless input transport.
// Q15 complex DIF arithmetic matches the archived independent integer oracle.
// mode is latched while resetn=0: 0=2048, 1=4096, 2=8192; 3 is invalid.
// A stream of complete frames needs no inserted zeros or inter-frame reset.
// Output is bit-reversed; the downstream bin-addressed consumer is NOT included.
// EXTERNAL_FIRST exposes an IDEAL synchronous outer delay, not a memory PHY:
// ready at selection promises a read two cycles later AND a write six clocks later.
// Physical memory arbitration must implement that reservation before integration.
module shared_sdf_fft #(
 parameter integer EXTERNAL_FIRST=1
)(
 input wire clk, resetn,
 input wire [1:0] mode,
 input wire in_valid, output wire in_ready, input wire [31:0] in_data,
 output wire out_valid, input wire out_ready, output wire [31:0] out_data,
 output wire [12:0] out_bin, output wire out_frame_end,
 input wire external_ready,
 output wire external_read_enable, output wire [11:0] external_read_addr,
 input wire [31:0] external_read_data,
 output wire external_write_enable, output wire [11:0] external_write_addr,
 output wire [31:0] external_write_data,
 output reg overflow
);
 localparam integer MEM_WORDS=EXTERNAL_FIRST ? 4096 : 8192;
 localparam integer MEM_AW=EXTERNAL_FIRST ? 12 : 13;
 reg [1:0] active_mode;
 reg [3:0] slot;
 reg [12:0] slot_onehot;
 reg [12:0] primed, queue_valid;
 reg [31:0] queue_data[0:12];
 // Consecutive stages issue seven clocks apart modulo 13. The six-clock
 // pipeline commits before the next stage reads, and before slot reuse.
 wire [12:0] indexes[0:12],phases[0:12],addresses[0:12];
 wire [12:0] first_halves,last_addresses;
 wire [12:0] index=indexes[slot];
 wire first_half=first_halves[slot];
 wire [12:0] phase=phases[slot];
 // Region D..2D-1: a constant leading 1, no variable carry chain. Word 0
 // is unused. Stage-local counters have only the bits that can change.
 wire [12:0] memory_index=addresses[slot];
 wire external_slot=(EXTERNAL_FIRST!=0)&&(slot==0);
 wire [12:0] take_stage,first_stages,input_readies;
 wire [31:0] source_words[0:12];
 wire [31:0] source_data=source_words[slot];
 wire take=|take_stage;
 assign in_ready=|input_readies;
 genvar s;
 generate for(s=0;s<13;s=s+1) begin: position
   localparam integer SHIFT=12-s;
   reg [SHIFT:0] count;
   wire first=(s==0&&active_mode==2)||(s==1&&active_mode==1)||(s==2&&active_mode==0);
   wire enabled=(active_mode!=3)&&((s>=2)||(s==1&&active_mode!=0)||(s==0&&active_mode==2));
   wire capacity=resetn&&slot_onehot[s]&&enabled&&!queue_valid[s]&&
                 ((EXTERNAL_FIRST==0)||(s!=0)||external_ready);
   wire previous_valid;
   if(s==0) begin: input_only
     assign previous_valid=1'b0;
     assign source_words[s]=in_data;
   end else begin: input_or_previous
     assign previous_valid=queue_valid[s-1];
     assign source_words[s]=first ? in_data : queue_data[s-1];
   end
   assign first_stages[s]=first;
   assign take_stage[s]=capacity&&(first ? in_valid : previous_valid);
   assign input_readies[s]=capacity&&first;
   assign indexes[s]=count & ((1<<SHIFT)-1);
   assign phases[s]=indexes[s]<<s;
   assign addresses[s]=(1<<SHIFT)|indexes[s];
   assign first_halves[s]=!count[SHIFT];
   assign last_addresses[s]=indexes[s]==((1<<SHIFT)-1);
   always @(posedge clk) begin
     if(!resetn)count<=0;
     else if(take_stage[s])count<=count+1'b1;
   end
 end endgenerate

 (* ram_style="block" *) reg [31:0] memory[0:MEM_WORDS-1];
 reg [31:0] memory_q;
 reg [5:0] valid_pipe;
 reg [3:0] tag[0:5];
 reg [12:0] address[0:5];
 reg [5:0] first_pipe,output_pipe,external_pipe;
 reg [31:0] input_held,input_delayed;
 reg [12:0] phase_held;
 wire signed [17:0] tw_re,tw_im;
 research_sdf_twiddle coeff(clk,phase_held,tw_re,tw_im);
 wire [31:0] old_word=external_pipe[1] ? external_read_data : memory_q;
 wire signed [16:0] sr=$signed({old_word[15],old_word[15:0]})+$signed({input_delayed[15],input_delayed[15:0]});
 wire signed [16:0] si=$signed({old_word[31],old_word[31:16]})+$signed({input_delayed[31],input_delayed[31:16]});
 wire signed [16:0] dr=$signed({old_word[15],old_word[15:0]})-$signed({input_delayed[15],input_delayed[15:0]});
 wire signed [16:0] di=$signed({old_word[31],old_word[31:16]})-$signed({input_delayed[31],input_delayed[31:16]});
 reg signed [15:0] diff_r,diff_i;
 reg signed [17:0] wr,wi;
 reg signed [33:0] rr,ii,ri,ir;
 reg signed [34:0] product_r,product_i;
 reg [31:0] passthrough[2:5],produced[2:5];
 reg [31:0] rotated;
 reg clipped;
 function automatic signed [34:0] round_q16(input signed [34:0] x);
   begin
     if(x>=0) round_q16=(x+35'sd32768)>>>16;
     else round_q16=-(((-x)+35'sd32768)>>>16);
   end
 endfunction
 function automatic [15:0] sat16(input signed [34:0] x);
   begin
     if(x>35'sd32767) sat16=16'h7fff;
     else if(x< -35'sd32768) sat16=16'h8000;
     else sat16=x[15:0];
   end
 endfunction
 wire signed [34:0] rounded_r=round_q16(product_r),rounded_i=round_q16(product_i);
 wire [31:0] write_data=first_pipe[5] ? passthrough[5] : rotated;
 wire commit=resetn&&valid_pipe[5];
 assign external_read_enable=resetn&&valid_pipe[0]&&external_pipe[0];
 assign external_read_addr=address[0][11:0];
 assign external_write_enable=commit&&external_pipe[5];
 assign external_write_addr=address[5][11:0];
 assign external_write_data=write_data;
 always @(posedge clk) begin
   if(resetn&&valid_pipe[0]&&!external_pipe[0]) memory_q<=memory[address[0][MEM_AW-1:0]];
   if(commit&&!external_pipe[5]) memory[address[5][MEM_AW-1:0]]<=write_data;
 end

 reg [12:0] output_seq;
 wire [12:0] last_seq=(13'd8191 >> (2-active_mode));
 wire [12:0] reversed;
 genvar b;
 generate for(b=0;b<13;b=b+1) begin: reverse_index
   assign reversed[b]=output_seq[12-b];
 end endgenerate
 assign out_valid=resetn&&queue_valid[12];
 assign out_data=queue_data[12];
 assign out_bin=reversed >> (2-active_mode);
 assign out_frame_end=output_seq==last_seq;
 integer j;
 always @(posedge clk) begin
   if(!resetn) begin
     active_mode<=mode;slot<=0;slot_onehot<=1;primed<=0;queue_valid<=0;
     valid_pipe<=0;first_pipe<=0;output_pipe<=0;external_pipe<=0;
     overflow<=0;output_seq<=0;input_held<=0;input_delayed<=0;phase_held<=0;
     for(j=0;j<13;j=j+1) queue_data[j]<=0;
     for(j=0;j<6;j=j+1) begin tag[j]<=0;address[j]<=0;end
   end else begin
     slot<=slot>=11 ? slot-4'd11 : slot+4'd2;
     slot_onehot<={slot_onehot[10:0],slot_onehot[12:11]};
     valid_pipe<={valid_pipe[4:0],take};
     first_pipe<={first_pipe[4:0],first_half};
     output_pipe<={output_pipe[4:0],primed[slot]||!first_half};
     external_pipe<={external_pipe[4:0],external_slot};
     for(j=1;j<6;j=j+1) begin tag[j]<=tag[j-1];address[j]<=address[j-1];end
     input_delayed<=input_held;
     // Invalid slots may overwrite pipeline registers: valid_pipe alone
     // controls side effects. Avoid a chip-wide combinational take -> CE.
     tag[0]<=slot;address[0]<=external_slot ? index : memory_index;
     input_held<=source_data;phase_held<=phase;
     for(j=0;j<13;j=j+1) begin
       if(take_stage[j]&&last_addresses[j])primed[j]<=1;
       if(j<12)begin
         if(take_stage[j+1]&&!first_stages[j+1])queue_valid[j]<=0;
       end
     end
     // Registered arithmetic avoids a multiply/add/round path in one cycle.
     diff_r<=dr>>>1;diff_i<=di>>>1;wr<=tw_re;wi<=tw_im;
     passthrough[2]<=input_delayed;
     produced[2]<=first_pipe[1] ? old_word : {si[16:1],sr[16:1]};
     rr<=diff_r*wr;ii<=diff_i*wi;ri<=diff_r*wi;ir<=diff_i*wr;
     product_r<=$signed({rr[33],rr})-$signed({ii[33],ii});
     product_i<=$signed({ri[33],ri})+$signed({ir[33],ir});
     rotated<={sat16(rounded_i),sat16(rounded_r)};
     clipped<=rounded_r>35'sd32767||rounded_r< -35'sd32768||
              rounded_i>35'sd32767||rounded_i< -35'sd32768;
     for(j=3;j<6;j=j+1) begin
       passthrough[j]<=passthrough[j-1];produced[j]<=produced[j-1];
     end
     if(out_valid&&out_ready) begin
       queue_valid[12]<=0;
       output_seq<=out_frame_end ? 13'd0 : output_seq+1'b1;
     end
     if(commit) begin
       queue_valid[tag[5]]<=output_pipe[5];
       queue_data[tag[5]]<=produced[5];
       if(!first_pipe[5]&&clipped) overflow<=1;
     end
   end
 end
endmodule
