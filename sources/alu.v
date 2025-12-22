`timescale 1ns/1ps
module alu (
    input         clk,
    input         rst_n,
    input         en,
    input  [15:0] A,
    input  [15:0] B,
    input  [3:0]  opcode,
    input         start,

    output reg [15:0] result,
    output            busy
);
    reg [1:0] state;
    reg [3:0] cycle_cnt;

    localparam IDLE     = 2'b00,
               MUL_EXEC = 2'b01,
               DIV_EXEC = 2'b10;

    assign busy = (state != IDLE);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= IDLE;
            cycle_cnt <= 4'd0;
            result    <= 16'd0;
        end 
        else if (en) begin
            case (state)
                IDLE: begin
                    cycle_cnt <= 4'd0;
                    if (start) begin
                        case (opcode)
                            4'b1000: state <= MUL_EXEC;
                            4'b1001: state <= DIV_EXEC;
                            default: begin
                             //TODO
                            end
                        endcase
                    end
                end
                MUL_EXEC: begin
                    //TODO
                end
                DIV_EXEC: begin
                    //TODO
                end
            endcase
        end
    end
endmodule
