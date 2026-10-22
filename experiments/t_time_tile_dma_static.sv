// Experimental tile transaction engine. Descriptor supplier is external.
// scratch_base identifies the first carrier of a 16-carrier tile; stride is
// one full symbol in bytes. Both must be BL8 aligned. Rings are disjoint,
// base/end BL8 aligned, write start BL8 aligned, read start halfword aligned.
// Exactly 16 in-order ring descriptors per invocation. No cold-fill validity
// handling: caller must suppress invalid warm-up output. Reset is GLOBAL with
// arbiter/controller, never independent while a transaction is in flight.
module t_time_tile_dma(
 input wire clk,resetn,start_valid,output wire start_ready,
 input wire[22:0]scratch_base,input wire[15:0]scratch_stride,
 input wire cfg_valid,output wire cfg_ready,input wire cfg_bypass,
 input wire[22:0]cfg_base,input wire[23:0]cfg_end,
 input wire[22:0]cfg_write_start,cfg_read_start,
 output wire req_valid,input wire req_ready,output reg req_write,
 output reg[20:0]req_address,output reg[255:0]req_data,
 input wire rsp_valid,input wire[255:0]rsp_data,
 output reg done,output wire collision
);
 localparam IDLE=0,LOAD=1,RING=2,STORE=3;
 localparam CONFIG=0,GATHER=1,WRITE=2,READ=3;
 reg[1:0]phase,op;
 reg outstanding;
 reg[22:0]scratch,load_address,store_address;
 reg[15:0]stride;
 reg[4:0]load_row,store_row,column,issued;
 reg[1:0]beat;
 reg[767:0]row_buffer,write_buffer,scatter_buffer;
 reg row_pending,scatter_pending,store_active;
 reg[3:0]row_index,scatter_index;
 reg bypass;
 reg[22:0]base,write_address,read_address;
 reg[23:0]ending;
 reg[4:0]prefix;
 reg[1:0]read_beat;
 reg[1023:0]read_buffer;
 reg aligning;
 reg[3:0]skip_halfwords,align_sample;
 wire put_ready,get_ready,result_valid;
 wire[767:0]result_data;
 wire put_valid=(phase==LOAD&&row_pending)||(phase==RING&&scatter_pending);
 wire get_valid=(phase==RING||phase==STORE)&&issued<16;
 wire result_ready=(phase==RING&&op==GATHER&&(!bypass||(!aligning&&!scatter_pending)))||
                   (phase==STORE&&!store_active&&store_row<16);
 t_time_tile_store tile(clk,resetn,put_valid,put_ready,phase==RING,
   phase==LOAD?row_index:scatter_index,phase==LOAD?row_buffer:scatter_buffer,
   get_valid,get_ready,phase==RING,issued[3:0],result_valid,result_ready,result_data,collision);
 assign start_ready=resetn&&phase==IDLE;
 assign cfg_ready=resetn&&phase==RING&&op==CONFIG&&column<16;
 wire issue_load=phase==LOAD&&load_row<16&&!row_pending;
 wire issue_write=phase==RING&&op==WRITE;
 // Do not overwrite the preceding read block while it is being aligned.
 wire issue_read=phase==RING&&op==READ&&(!aligning&&!scatter_pending);
 wire issue_store=phase==STORE&&store_active;
 assign req_valid=resetn&&!outstanding&&(issue_load||issue_write||issue_read||issue_store);
 always @*begin
  req_write=issue_write||issue_store;req_data=0;req_address=0;
  if(phase==LOAD)req_address=(load_address+{beat,5'b0})>>2;
  if(phase==STORE)begin req_address=(store_address+{beat,5'b0})>>2;req_data=write_buffer[255:0];end
  if(phase==RING)begin
   req_address=(op==WRITE?write_address:read_address)>>2;
   if(op==WRITE)req_data=write_buffer[255:0];
  end
 end
 always @(posedge clk)begin
  if(!resetn)begin
   phase<=IDLE;op<=CONFIG;outstanding<=0;done<=0;row_pending<=0;
   scatter_pending<=0;aligning<=0;store_active<=0;
   scratch<=0;stride<=0;load_address<=0;store_address<=0;load_row<=0;store_row<=0;
   column<=0;issued<=0;beat<=0;read_beat<=0;prefix<=0;skip_halfwords<=0;align_sample<=0;
   row_index<=0;scatter_index<=0;bypass<=0;base<=0;ending<=0;write_address<=0;read_address<=0;
  end else begin
   done<=0;
   if(req_valid&&req_ready)outstanding<=1;
   if(rsp_valid)outstanding<=0;
   if(get_valid&&get_ready)issued<=issued+1'b1;
   if(put_valid&&put_ready)begin
    if(phase==LOAD)row_pending<=0;else scatter_pending<=0;
   end
   if(aligning)begin
    if(skip_halfwords!=0)begin read_buffer<=read_buffer>>16;skip_halfwords<=skip_halfwords-1'b1;end
    else begin
     scatter_buffer<={read_buffer[47:0],scatter_buffer[767:48]};read_buffer<=read_buffer>>48;
     align_sample<=align_sample+1'b1;
     if(align_sample==15)begin aligning<=0;scatter_pending<=1;end
    end
   end
   case(phase)
    IDLE:if(start_valid)begin
     phase<=LOAD;scratch<=scratch_base;load_address<=scratch_base;store_address<=scratch_base;
     stride<=scratch_stride;load_row<=0;store_row<=0;column<=0;issued<=0;beat<=0;
     row_pending<=0;scatter_pending<=0;aligning<=0;store_active<=0;op<=CONFIG;
    end
    LOAD:begin
     if(rsp_valid)begin
      case(beat)
       0:row_buffer[255:0]<=rsp_data;
       1:row_buffer[511:256]<=rsp_data;
       2:row_buffer[767:512]<=rsp_data;
      endcase
      if(beat==2)begin
       beat<=0;row_pending<=1;row_index<=load_row[3:0];load_row<=load_row+1'b1;load_address<=load_address+stride;
      end else beat<=beat+1'b1;
     end
     if(load_row==16&&!row_pending&&put_ready)begin phase<=RING;issued<=0;end
    end
    RING:begin
     if(cfg_valid&&cfg_ready)begin
      bypass<=cfg_bypass;base<=cfg_base;ending<=cfg_end;write_address<=cfg_write_start;
      read_address<={cfg_read_start[22:5],5'b0};prefix<=cfg_read_start[4:0];op<=GATHER;
     end
     if(result_valid&&result_ready)begin
      if(bypass)begin
       scatter_buffer<=result_data;scatter_pending<=1;scatter_index<=column[3:0];
       column<=column+1'b1;op<=CONFIG;
      end else begin write_buffer<=result_data;beat<=0;read_beat<=0;op<=WRITE;end
     end
     if(rsp_valid)begin
      if(op==WRITE)begin
       write_buffer<=write_buffer>>256;
       write_address<=write_address+24'd32==ending?base:write_address+23'd32;
       if(beat==2)begin beat<=0;op<=READ;end else beat<=beat+1'b1;
      end else if(op==READ)begin
       case(read_beat)
        0:read_buffer[255:0]<=rsp_data;
        1:read_buffer[511:256]<=rsp_data;
        2:read_buffer[767:512]<=rsp_data;
        3:read_buffer[1023:768]<=rsp_data;
       endcase
       read_address<=read_address+24'd32==ending?base:read_address+23'd32;
       if((read_beat==2&&prefix==0)||read_beat==3)begin
        aligning<=1;skip_halfwords<=prefix[4:1];align_sample<=0;scatter_index<=column[3:0];
        column<=column+1'b1;op<=CONFIG;
       end else read_beat<=read_beat+1'b1;
      end
     end
     if(column==16&&!aligning&&!scatter_pending&&put_ready)begin phase<=STORE;issued<=0;end
    end
    STORE:begin
     if(result_valid&&result_ready)begin write_buffer<=result_data;beat<=0;store_active<=1;end
     if(rsp_valid)begin
      write_buffer<=write_buffer>>256;
      if(beat==2)begin
       store_active<=0;beat<=0;store_row<=store_row+1'b1;store_address<=store_address+stride;
       if(store_row==15)begin phase<=IDLE;done<=1;end
      end else beat<=beat+1'b1;
     end
    end
   endcase
  end
 end
endmodule
