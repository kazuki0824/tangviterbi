`timescale 1ns/1ps
module memory_tb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg req = 0, write = 0;
    reg [21:0] addr = 0;
    reg [31:0] wdata = 32'h12345678;
    reg [1:0] rwds = 0;
    wire ready, busy;
    wire [1:0] cs, ck, oe;
    wire [15:0] tx;
    wire [31:0] rx;
    wire hready, hbusy, hcs, hck, hoe;
    wire [7:0] htx;
    wire [31:0] hrx;

    psram_ctrl psram (
        .clk(clk), .resetn(resetn), .req(req), .write(write), .addr(addr),
        .wdata(wdata), .phy_rdata(16'hbbaa), .phy_rwds(rwds),
        .ready(ready), .busy(busy), .cs_n(cs), .ck_en(ck),
        .phy_oe(oe), .phy_wdata(tx), .rdata(rx)
    );
    hyperram_ctrl hyperram (
        .clk(clk), .resetn(resetn), .req(req), .write(write), .addr(addr),
        .wdata(wdata), .phy_rdata(8'hcc), .phy_rwds(rwds[0]),
        .ready(hready), .busy(hbusy), .cs_n(hcs), .ck_en(hck),
        .phy_oe(hoe), .phy_wdata(htx), .rdata(hrx)
    );

    task tick;
        begin @(posedge clk); #1; end
    endtask

    task transfer;
        input die;
        input op_write;
        input extra;
        output integer cycles;
        reg [47:0] got_ca, got_hca;
        reg [31:0] got_data;
        integer n;
        begin
            @(negedge clk);
            addr = die ? 22'h200246 : 22'h000246;
            write = op_write;
            rwds = extra ? 2'b11 : 2'b00;
            req = 1;
            tick();
            if (!busy || !hbusy || cs != (die ? 2'b01 : 2'b10))
                $fatal(1, "request did not select exactly one die");
            @(negedge clk); req = 0;
            got_ca = 0; got_hca = 0;
            for (n = 0; n < 6; n = n + 1) begin
                tick();
                got_ca = {got_ca[39:0], tx[die*8 +: 8]};
                got_hca = {got_hca[39:0], htx};
            end
            // Independent literal packet values for local word address 0x246.
            if (got_ca !== (op_write ? 48'h000000480006 : 48'h800000480006))
                $fatal(1, "PSRAM CA layout or wrapped-burst bit incorrect: %h", got_ca);
            if (got_hca !== (die ?
                (op_write ? 48'h200400480006 : 48'ha00400480006) :
                (op_write ? 48'h200000480006 : 48'ha00000480006)))
                $fatal(1, "HyperRAM CA layout or linear-burst bit incorrect: %h", got_hca);
            cycles = 0;
            // Change the external address while busy: read mux must retain die.
            @(negedge clk); addr = die ? 22'h000246 : 22'h200246;
            // The sizing contract specifies 6 or 12 abstract-PHY wait beats.
            cycles = extra ? 12 : 6;
            for (n = 0; n < cycles; n = n + 1) begin
                tick();
                if (cs != (die ? 2'b01 : 2'b10))
                    $fatal(1, "die changed while busy");
            end
            if (oe != (op_write ? (die ? 2'b10 : 2'b01) : 2'b00))
                $fatal(1, "data output enable incorrect");
            got_data = 0;
            for (n = 0; n < 4; n = n + 1) begin
                tick();
                got_data = {got_data[23:0], tx[die*8 +: 8]};
            end
            if (op_write && got_data !== 32'h12345678)
                $fatal(1, "write data was truncated/reordered: %h", got_data);
            tick();
            if (!ready || !hready || cs !== 2'b11 || hcs !== 1)
                $fatal(1, "transfer did not complete");
            if (!op_write && rx !== (die ? 32'hbbbbbbbb : 32'haaaaaaaa))
                $fatal(1, "read selected wrong die: %h", rx);
            if (!op_write && hrx !== 32'hcccccccc)
                $fatal(1, "HyperRAM read assembly incorrect");
            tick();
        end
    endtask

    integer normal, extra, unused;
    initial begin
        tick(); tick();
        @(negedge clk); resetn = 1;
        transfer(0, 1, 0, normal);
        transfer(1, 1, 1, extra);
        if (extra != normal + 6) $fatal(1, "RWDS extra latency not honored");
        transfer(0, 0, 0, unused);
        transfer(1, 0, 1, unused);
        $display("PASS: HyperRAM and both PSRAM dies, CA, data, RWDS latency");
        $finish;
    end
    initial begin #10000; $fatal(1, "test timeout"); end
endmodule
