module k7_grouped_miter(input [12:0] a,b, output equal);
    // Exact modulo-8192 subtraction with independent group borrow lookahead.
    function automatic [12:0] grouped_difference;
        input [12:0] a,b;
        reg borrow4,borrow8;
        begin
            borrow4 = a[3:0] < b[3:0];
            borrow8 = (a[7:4] < b[7:4]) || ((a[7:4] == b[7:4]) && borrow4);
            grouped_difference[3:0] = a[3:0]-b[3:0];
            grouped_difference[7:4] = a[7:4]-b[7:4]-borrow4;
            grouped_difference[12:8] = a[12:8]-b[12:8]-borrow8;
        end
    endfunction
wire [12:0] reference_difference=a-b;
assign equal=reference_difference==grouped_difference(a,b);
endmodule
