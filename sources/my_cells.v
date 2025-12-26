`timescale 1ns/1ps

module NR2 (input A, input B, output Y); assign Y = ~(A | B); endmodule
module AN2 (input A, input B, output Y); assign Y = A & B; endmodule
module IV  (input A, output Y);          assign Y = ~A; endmodule
module OR2 (input A, input B, output Y); assign Y = A | B; endmodule
module ND2 (input A, input B, output Y); assign Y = ~(A & B); endmodule
module ND3 (input A, input B, input C, output Y); assign Y = ~(A & B & C); endmodule
module XR2 (input A, input B, output Y); assign Y = A ^ B; endmodule
module MUX2 (input A, input B, input S, output Y); assign Y = S ? B : A; endmodule

module DFFE (input D, input CLK, input EN, output reg Q);
    always @(posedge CLK) if (EN) Q <= D;
endmodule

module DFFR (input D, input CLK, input RST_N, output reg Q);
    always @(posedge CLK or negedge RST_N) begin
        if (!RST_N) Q <= 1'b0;
        else        Q <= D;
    end
endmodule
