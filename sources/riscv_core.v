`timescale 1ns/1ps
module riscv_core (
    input clk,
    input rst_n,
    output reg [31:0] imem_addr,
    input  [31:0] imem_rdata,
    output reg [31:0] dmem_addr,
    output reg [31:0] dmem_wdata,
    output reg        dmem_we,
    input  [31:0] dmem_rdata
);

    reg [31:0] pc;
    reg [31:0] ir;

    reg [31:0] regs [0:31];

    reg [31:0] alu_a, alu_b, alu_out;
    reg [31:0] imm;

    reg [2:0] state;

    localparam FETCH  = 3'd0;
    localparam DECODE = 3'd1;
    localparam EXEC   = 3'd2;
    localparam MEM    = 3'd3;
    localparam WB     = 3'd4;

    wire [6:0] opcode = ir[6:0];
    wire [2:0] funct3 = ir[14:12];
    wire [6:0] funct7 = ir[31:25];
    wire [4:0] rs1 = ir[19:15];
    wire [4:0] rs2 = ir[24:20];
    wire [4:0] rd  = ir[11:7];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pc <= 0;
            state <= FETCH;
            dmem_we <= 0;
        end else begin
            case (state)

                FETCH: begin
                    imem_addr <= pc;
                    state <= DECODE;
                end

                DECODE: begin
                    ir <= imem_rdata;
                    alu_a <= regs[rs1];
                    alu_b <= regs[rs2];
                    imm <= {{20{ir[31]}}, ir[31:20]};
                    state <= EXEC;
                end

                EXEC: begin
                    case (opcode)
                        7'b0110011: begin
                            case ({funct7, funct3})
                                10'b0000000000: alu_out <= alu_a + alu_b;
                                10'b0100000000: alu_out <= alu_a - alu_b;
                                10'b0000000111: alu_out <= alu_a & alu_b;
                                10'b0000000110: alu_out <= alu_a | alu_b;
                                10'b0000000100: alu_out <= alu_a ^ alu_b;
                                default: alu_out <= 0;
                            endcase
                            state <= WB;
                        end
                        7'b0000011, 7'b0100011: begin
                            alu_out <= alu_a + imm;
                            state <= MEM;
                        end
                        7'b1100011: begin
                            if (alu_a == alu_b)
                                pc <= pc + imm;
                            else
                                pc <= pc + 4;
                            state <= FETCH;
                        end
                        7'b1101111: begin
                            regs[rd] <= pc + 4;
                            pc <= pc + imm;
                            state <= FETCH;
                        end
                        default: begin
                            pc <= pc + 4;
                            state <= FETCH;
                        end
                    endcase
                end

                MEM: begin
                    dmem_addr <= alu_out;
                    if (opcode == 7'b0100011) begin
                        dmem_wdata <= regs[rs2];
                        dmem_we <= 1;
                        pc <= pc + 4;
                        state <= FETCH;
                    end else begin
                        dmem_we <= 0;
                        state <= WB;
                    end
                end

                WB: begin
                    if (opcode == 7'b0000011)
                        regs[rd] <= dmem_rdata;
                    else
                        regs[rd] <= alu_out;
                    pc <= pc + 4;
                    state <= FETCH;
                end

            endcase
        end
    end
endmodule


