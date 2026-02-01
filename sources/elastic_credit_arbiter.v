`timescale 1ns/1ps
module elastic_credit_arbiter (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [3:0]  request,      
    input  wire [7:0]  packet_size,  
    output reg  [3:0]  grant,        
    output reg         grant_valid   
);

    localparam MAX_CREDIT = 8'hFF;
    localparam AGE_THRESH = 8'h20; 

    // --- State ---
    reg [7:0]  credit_bucket [0:3];
    reg [7:0]  age_counter   [0:3];
    reg [15:0] lfsr_reg;
    

    reg [3:0] can_service_q;
    reg [3:0] is_aged_q;
    reg [3:0] request_q;
    reg [7:0] spec_bucket_granted [0:3]; 
    reg [7:0] spec_bucket_idle    [0:3]; 
    reg [7:0] spec_age_inc        [0:3]; 

    reg [3:0] grant_pipe;
    reg       grant_valid_pipe;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) lfsr_reg <= 16'hACE1; 
        else lfsr_reg <= {lfsr_reg[14:0], lfsr_reg[15] ^ lfsr_reg[13] ^ lfsr_reg[12] ^ lfsr_reg[10]};
    end

   
    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            can_service_q <= 4'b0;
            is_aged_q     <= 4'b0;
            request_q     <= 4'b0;
            for (i=0; i<4; i=i+1) begin
                spec_bucket_granted[i] <= 8'h0;
                spec_bucket_idle[i]    <= 8'h0;
                spec_age_inc[i]        <= 8'h0;
            end
        end else begin
            request_q <= request;
            for (i=0; i<4; i=i+1) begin
                can_service_q[i] <= (credit_bucket[i] >= packet_size);
                is_aged_q[i]     <= (age_counter[i] >= AGE_THRESH);
                spec_bucket_granted[i] <= credit_bucket[i] - packet_size + lfsr_reg[i];
                spec_bucket_idle[i]    <= (credit_bucket[i] + lfsr_reg[i] > MAX_CREDIT) ? MAX_CREDIT : credit_bucket[i] + lfsr_reg[i];
                spec_age_inc[i]        <= age_counter[i] + 8'h01;
            end
        end
    end

    
    wire [3:0] high_pri_req = request_q & can_service_q & is_aged_q;
    wire [3:0] norm_pri_req = request_q & can_service_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grant_pipe <= 4'b0000;
            grant_valid_pipe <= 1'b0;
        end else begin
            if (|high_pri_req) begin
                grant_pipe <= high_pri_req & ~(high_pri_req - 4'b0001);
                grant_valid_pipe <= 1'b1;
            end else if (|norm_pri_req) begin
                grant_pipe <= norm_pri_req & ~(norm_pri_req - 4'b0001);
                grant_valid_pipe <= 1'b1;
            end else begin
                grant_pipe <= 4'b0000;
                grant_valid_pipe <= 1'b0;
            end
        end
    end

 
    always @(*) begin
        grant = grant_pipe;
        grant_valid = grant_valid_pipe;
    end


    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (j=0; j<4; j=j+1) begin
                credit_bucket[j] <= 8'h80;
                age_counter[j]   <= 8'h00;
            end
        end else begin
            for (j=0; j<4; j=j+1) begin
                if (grant_pipe[j] && grant_valid_pipe) begin
                    credit_bucket[j] <= spec_bucket_granted[j];
                    age_counter[j]   <= 8'h00;
                end else begin
                    credit_bucket[j] <= spec_bucket_idle[j];
                    if (request_q[j]) 
                        age_counter[j] <= spec_age_inc[j];
                end
            end
        end
    end

endmodule




