`timescale 1ns/1ps
module stream_tb;
    parameter integer INPUT_BITS=16, L=64, OUTPUT_SHIFT=15, USE_FIFO=1;
    parameter COEFF_FILE="coeff_residual.hex";
    reg clk=0, resetn=0, in_valid=0, out_ready=1;
    // Cycle schedules, not this rounded wall-clock delay, determine ingress.
    always #3.240740740741 clk=~clk;
    reg signed [INPUT_BITS-1:0] in_i, in_q;
    wire in_ready, out_valid;
    wire signed [15:0] out_i, out_q;
    wire [9:0] queue_count;
    generate if (USE_FIFO) begin: g_fifo
        t_diag_fifo_resampler #(.INPUT_BITS(INPUT_BITS),.L(L),.OUTPUT_SHIFT(OUTPUT_SHIFT),.COEFF_FILE(COEFF_FILE)) dut (.*);
        assign queue_count=dut.count;
    end else begin: g_core
        t_diag_resampler #(.INPUT_BITS(INPUT_BITS),.L(L),.OUTPUT_SHIFT(OUTPUT_SHIFT),.COEFF_FILE(COEFF_FILE)) dut (.*);
        assign queue_count=0;
    end endgenerate
    reg [31:0] samples [0:65535];
    reg [31:0] due [0:65535];
    integer n, cycle=0, index=0, accepted=0, lost=0, outputs=0, max_fifo=0;
    integer first_lost=-1, first_lost_cycle=-1, timeout_cycles, backpressure=0, stall_mode=0;
    integer input_fd, output_fd, status_fd;
    reg was_stalled=0;
    reg [31:0] stalled_word;
    integer stable_failures=0;
    string input_file, due_file, accepted_file, output_file, status_file;
    initial begin
        if (!$value$plusargs("N=%d", n) || !$value$plusargs("TIMEOUT=%d",timeout_cycles)) $fatal(1,"missing count");
        if (!$value$plusargs("INPUT=%s",input_file) || !$value$plusargs("DUE=%s",due_file)) $fatal(1,"missing stimulus");
        if (!$value$plusargs("ACCEPTED=%s",accepted_file) || !$value$plusargs("OUTPUT=%s",output_file) || !$value$plusargs("STATUS=%s",status_file)) $fatal(1,"missing result paths");
        if ($value$plusargs("BACKPRESSURE=%d", backpressure)) begin end
        if ($value$plusargs("STALL=%d", stall_mode)) begin end
        $readmemh(input_file,samples,0,n-1); $readmemh(due_file,due,0,n-1);
        input_fd=$fopen(accepted_file,"w"); output_fd=$fopen(output_file,"w");
        repeat(4) @(negedge clk);
        resetn=1;
        while (cycle<timeout_cycles) begin
            in_valid=index<n && cycle>=due[index];
            if (in_valid) begin in_i=samples[index][15:0]; in_q=samples[index][31:16]; end
            out_ready=stall_mode==0 || (cycle%97>=31 && cycle%997<909);
            @(posedge clk);
            if (queue_count>max_fifo) max_fifo=queue_count;
            if (was_stalled && (!out_valid || {out_q,out_i}!==stalled_word)) stable_failures=stable_failures+1;
            was_stalled=out_valid&&!out_ready;
            stalled_word={out_q,out_i};
            if (in_valid && in_ready) begin
                $fwrite(input_fd,"%0d %0d %0d %0d\n",cycle,index,$signed(in_i),$signed(in_q));
                accepted=accepted+1; index=index+1;
            end else if (in_valid && !backpressure) begin
                lost=lost+1;
                if (first_lost<0) begin first_lost=index; first_lost_cycle=cycle; end
                index=index+1;
            end
            if (out_valid && out_ready) begin
                $fwrite(output_fd,"%0d %0d %0d\n",cycle,$signed(out_i),$signed(out_q));
                outputs=outputs+1;
            end
            @(negedge clk); cycle=cycle+1;
        end
        $fclose(input_fd); $fclose(output_fd);
        status_fd=$fopen(status_file,"w");
        $fwrite(status_fd,"{\"offered\":%0d,\"accepted\":%0d,\"lost\":%0d,\"output_count\":%0d,\"max_fifo\":%0d,\"first_lost_index_zero_based\":%0d,\"first_lost_cycle\":%0d,\"stable_failures\":%0d,\"final_fifo\":%0d}\n",index,accepted,lost,outputs,max_fifo,first_lost,first_lost_cycle,stable_failures,queue_count);
        $fclose(status_fd); $finish;
    end
endmodule
