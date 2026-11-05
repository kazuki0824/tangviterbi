`timescale 1ns/1ps
// Independent source-bit oracle for two simultaneous 10+10-bit streams.
// In particular 4096-byte source page boundaries are NOT bitstream resets.
module dual_iq10_unpack_tb;
    reg clk=0, resetn=0;
    always #5 clk=~clk;
    localparam integer SAMPLES=4096;
    localparam integer WORDS=SAMPLES*20/32;
    integer cycle=0, tx0=0, tx1=0, rx0=0, rx1=0;

    function automatic [9:0] ival(input integer sample, input integer lane);
        ival=(sample*(lane ? 19:37)+(lane ? 13:5)) & 1023;
    endfunction
    function automatic [9:0] qval(input integer sample, input integer lane);
        qval=(sample*(lane ? 67:83)+(lane ? 29:7)) & 1023;
    endfunction
    function automatic [31:0] make_word(input integer w, input integer lane);
        integer b, bit_at, sample, bit_pos;
        reg [19:0] pair;
        begin
            make_word=32'd0;
            for(b=0;b<32;b=b+1)begin
                bit_at=w*32+b;
                sample=bit_at/20;
                bit_pos=bit_at%20;
                pair={qval(sample,lane),ival(sample,lane)};
                make_word[b]=pair[bit_pos];
            end
        end
    endfunction

    wire valid0 = resetn && tx0<WORDS && cycle%5!=1;
    wire valid1 = resetn && tx1<WORDS && cycle%7!=2;
    wire ready0, ready1, ov0, ov1;
    wire [9:0] oi0,oq0,oi1,oq1;
    wire consume0 = cycle%11!=3 && cycle%11!=4;
    wire consume1 = cycle%13!=7 && cycle%13!=8;

    s3_iq10_unpack t0(
        .clk(clk),.resetn(resetn),.in_valid(valid0),.in_ready(ready0),
        .in_data(make_word(tx0,0)),.out_valid(ov0),.out_ready(consume0),
        .out_i(oi0),.out_q(oq0)
    );
    s3_iq10_unpack s1(
        .clk(clk),.resetn(resetn),.in_valid(valid1),.in_ready(ready1),
        .in_data(make_word(tx1,1)),.out_valid(ov1),.out_ready(consume1),
        .out_i(oi1),.out_q(oq1)
    );

    initial begin
        repeat(5) @(negedge clk);
        resetn=1;
    end
    always @(posedge clk) begin
        if(resetn)begin
            if(valid0 && ready0)tx0<=tx0+1;
            if(valid1 && ready1)tx1<=tx1+1;
            if(ov0 && consume0)begin
                if(rx0>=SAMPLES || oi0!==ival(rx0,0) || oq0!==qval(rx0,0))begin
                    $display("T IQ mismatch sample=%0d I=%0h Q=%0h",rx0,oi0,oq0);
                    $fatal(1,"T stream data loss or bit corruption");
                end
                rx0<=rx0+1;
            end
            if(ov1 && consume1)begin
                if(rx1>=SAMPLES || oi1!==ival(rx1,1) || oq1!==qval(rx1,1))begin
                    $display("S IQ mismatch sample=%0d I=%0h Q=%0h",rx1,oi1,oq1);
                    $fatal(1,"S stream data loss or bit corruption");
                end
                rx1<=rx1+1;
            end
            if(rx0==SAMPLES && rx1==SAMPLES)begin
                if(tx0!=WORDS || tx1!=WORDS)$fatal(1,"incomplete input transfer");
                $display("PASS dual lossless I10Q10 streams %0d+%0d samples, %0d words/stream, crossed two 4096-byte pages",rx0,rx1,WORDS);
                $finish;
            end
            if(cycle>=20000)$fatal(1,"timeout: source/consumer deadlock");
            cycle<=cycle+1;
        end
    end
endmodule
