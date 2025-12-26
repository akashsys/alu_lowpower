`timescale 1ns/1ps
module top (
    input         clk,
    input         rst_n,
    input  [15:0] A,
    input  [15:0] B,
    input  [3:0]  opcode,
    input         start,
    input         diss_clk,

    output reg [15:0] result,
    output     [15:0] clamp_obs
);
    wire [15:0] alu_result;
    wire        busy;
    wire        alu_en;
    wire [15:0] clamp_value = 16'd0;
    
    assign clamp_obs = clamp_value;

    alu_clk_off u_clk_off (
        .clk      (clk),
        .diss_clk (diss_clk),
        .alu_en   (alu_en)
    );

    alu u_alu (
        .clk    (clk),
        .rst_n  (rst_n),
        .en     (alu_en),
        .A      (A),
        .B      (B),
        .opcode (opcode),
        .start  (start),
        .result (alu_result),
        .busy   (busy)
    );

    always @(*) begin
        if (!rst_n) begin
            result = 16'd0;
        end 
        else if (diss_clk) begin
            result = clamp_value;
        end 
        else begin
            result = alu_result;
        end
    end

endmodule

