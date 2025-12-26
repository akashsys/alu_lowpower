`timescale 1ns/1ps
// 2-Input AND gate
module AN2 (input A, input B, output X);
    assign X = A & B;
endmodule

// Inverter
module IV (input A, output X);
    assign X = ~A;
endmodule

// 2-Input OR gate
module OR2 (input A, input B, output X);
    assign X = A | B;
endmodule

// 2-to-1 Multiplexer
module MUX2 (input A, input B, input S, output X);
    assign X = S ? B : A;
endmodule

// D-Flip-Flop with Enable (No internal reset)
// This is likely what is in the baseline netlist
module DFFE (input D, input CLK, input EN, output reg Q);
    always @(posedge CLK) begin
        if (EN)
            Q <= D;
    end
endmodule

// D-Flip-Flop with Asynchronous Reset (Target for Golden/ECO)
module DFFR (input D, input CLK, input RST_N, output reg Q);
    always @(posedge CLK or negedge RST_N) begin
        if (!RST_N)
            Q <= 1'b0;
        else
            Q <= D;
    end
endmodule
