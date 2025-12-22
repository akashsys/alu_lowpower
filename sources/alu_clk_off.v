`timescale 1ns/1ps
module alu_clk_off (
    input  wire clk,
    input  wire diss_clk,
    output wire alu_en
);

    assign alu_en = !diss_clk;

endmodule
