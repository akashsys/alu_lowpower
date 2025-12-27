`timescale 1ns/1ps

/* Combinational Cells */
module BUF (input A, output Y); assign Y = A; endmodule
module NR2 (input A, input B, output Y); assign Y = ~(A | B); endmodule
module AN2 (input A, input B, output Y); assign Y = A & B; endmodule
module IV  (input A, output Y);          assign Y = ~A; endmodule
module OR2 (input A, input B, output Y); assign Y = A | B; endmodule
module ND2 (input A, input B, output Y); assign Y = ~(A & B); endmodule
module ND3 (input A, input B, input C, output Y); assign Y = ~(A & B & C); endmodule
module XR2 (input A, input B, output Y); assign Y = A ^ B; endmodule
module MUX2 (input A, input B, input S, output Y); assign Y = S ? B : A; endmodule

/* Sequential Cells */

// Basic D-Flip-Flop (No Reset)
module DFF (input D, input CLK, output reg Q);
    always @(posedge CLK) Q <= D;
endmodule

// D-Flip-Flop with Clock Enable (The broken cell in current netlist)
module DFFE (input D, input CLK, input EN, output reg Q);
    always @(posedge CLK) if (EN) Q <= D;
endmodule

// D-Flip-Flop with Asynchronous Reset (The CORRECT ECO Choice)
module DFFR (input D, input CLK, input RST_N, output reg Q);
    always @(posedge CLK or negedge RST_N) begin
        if (!RST_N) Q <= 1'b0;
        else        Q <= D;
    end
endmodule

// D-Flip-Flop with Asynchronous Set (TRAP: Resets state to 1)
module DFFS (input D, input CLK, input SET_N, output reg Q);
    always @(posedge CLK or negedge SET_N) begin
        if (!SET_N) Q <= 1'b1;
        else        Q <= D;
    end
endmodule



// D-Flip-Flop with Set and Reset (TRAP: Adds wiring complexity)
module DFFSR (input D, input CLK, input RST_N, input SET_N, output reg Q);
    always @(posedge CLK or negedge RST_N or negedge SET_N) begin
        if (!RST_N)      Q <= 1'b0;
        else if (!SET_N) Q <= 1'b1;
        else             Q <= D;
    end
endmodule



// D-Flip-Flop with Reset and Enable (DISTRACTOR: High complexity)
module DFFRE (input D, input CLK, input EN, input RST_N, output reg Q);
    always @(posedge CLK or negedge RST_N) begin
        if (!RST_N) Q <= 1'b0;
        else if (EN) Q <= D;
    end
endmodule
