/*
 * Copyright (c) 2025 Renaldas Zioma
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module lgn (
    input  wire clk,
    input  wire write_enable,
    input  wire [7:0]  ui_in,    // Dedicated inputs
    output wire [15:0] uo_out    // Dedicated outputs
);
  localparam INPUTS  = 28*28;
  localparam CATEGORIES = 10;
  localparam BITS_PER_CATEGORY = 800;
  localparam OUTPUTS = BITS_PER_CATEGORY * CATEGORIES;
  localparam BITS_PER_CATEGORY_SUM = $clog2(BITS_PER_CATEGORY);

  reg   [INPUTS-1:0] x;
  always @(posedge clk) begin : set_inputs
    if (write_enable)
      x <= {x[INPUTS-8-1:0], ui_in[7:0]};
  end

  wire [OUTPUTS-1:0] y; wire _unused = &{y};
  wire [BITS_PER_CATEGORY*CATEGORIES-1:0] y_categories;
  net net(
    .in(x),
    .out(y),
    .categories(y_categories)
  );

  wire [BITS_PER_CATEGORY_SUM*CATEGORIES-1:0] sum_categories;
  genvar i;
  generate
    for (i = 0; i < CATEGORIES; i = i+1) begin : calc_categories
      sum_bits #(.N(BITS_PER_CATEGORY)) sum_bits(
        .y(y_categories[i*BITS_PER_CATEGORY +: BITS_PER_CATEGORY]),      
        .sum(sum_categories[i*BITS_PER_CATEGORY_SUM +: BITS_PER_CATEGORY_SUM])
      );
    end
  endgenerate

  /* verilator lint_off UNUSEDSIGNAL */
  wire [3:0] best_category_index;
  wire [BITS_PER_CATEGORY_SUM-1:0] best_category_value;
  arg_max_10 #(.N(BITS_PER_CATEGORY_SUM)) arg_max_categories(
    .categories(sum_categories),
    .out_index(best_category_index),
    .out_value(best_category_value)
  );

  // assign  uo_out[7:0] = best_category_value[7:0];
  // assign uio_out[3:0] = best_category_index[3:0];
  // assign uio_out[6:4] = 0;
  // assign uio_out[7]   = 0;

  wire [6:0] display;
  seven_segment seven_segment(
    .in(best_category_index[3:0]),
    .out(display)
  );

  // assign  uo_out[3:0] = best_category_index[3:0]; assign  uo_out[6:4] = 0;
  assign  uo_out[6:0] = display;
  assign  uo_out[7] = ~write_enable;
  assign  uo_out[15:8] = best_category_value[BITS_PER_CATEGORY_SUM-1 -: 8];
  /* verilator lint_on UNUSEDSIGNAL */
endmodule

module sum_bits #(
    parameter N = 16
) (
    input wire [N-1:0] y,
    output wire [$clog2(N)-1:0] sum
);
    // integer i;
    // reg [$clog2(N)-1:0] temp_sum;
    
    // always @(*) begin
    //     temp_sum = 0;
    //     for (i = 0; i < N; i = i + 1) begin
    //         if (y[i]) temp_sum = temp_sum + 1; // avoids warning "Operator ADD expects 10 bits on the RHS, but RHS's SEL generates 1 bits"
    //     end
    // end
    
    // assign sum = temp_sum;
    assign sum = $countones(y); 
endmodule

module arg_max_10 #(
    parameter N = 8,
    parameter CATEGORIES = 10  // CAN NOT change this, 10 is hardcoded in the number of Stages below
) (
    input wire [CATEGORIES*N-1:0] categories,
    output reg [3:0] out_index,
    output reg [N-1:0] out_value
);
    localparam int INDEX_WIDTH = $clog2(CATEGORIES);

    // Intermediate wires for the tree comparison
    (* mem2reg *) reg [N-1:0] max_value_stage1 [4:0];  // Stage 1: Compare adjacent pairs
    (* mem2reg *) reg [3:0]   max_index_stage1 [4:0]; 

    (* mem2reg *) reg [N-1:0] max_value_stage2 [2:0];  // Stage 2: Compare reduced pairs
    (* mem2reg *) reg [3:0]   max_index_stage2 [2:0]; 

                  reg [N-1:0] max_value_stage3;        // Stage 3: Final comparison
                  reg [3:0]   max_index_stage3;

    integer i;

    always @(*) begin
        // Stage 1: Compare adjacent pairs
        for (i = 0; i < 5; i = i + 1) begin
            assert (2*i+1 <= CATEGORIES);
            if (categories[(2*i)*N +: N] > categories[(2*i+1)*N +: N]) begin
                max_value_stage1[i] = categories[(2*i)*N +: N];
                max_index_stage1[i] = INDEX_WIDTH'(2*i);
            end else begin
                max_value_stage1[i] = categories[(2*i+1)*N +: N];
                max_index_stage1[i] = INDEX_WIDTH'(2*i+1);
            end
        end

        // Stage 2: Compare reduced pairs
        for (i = 0; i < 2; i = i + 1) begin
            if (max_value_stage1[2*i] > max_value_stage1[2*i+1]) begin
                max_value_stage2[i] = max_value_stage1[2*i];
                max_index_stage2[i] = max_index_stage1[2*i];
            end else begin
                max_value_stage2[i] = max_value_stage1[2*i+1];
                max_index_stage2[i] = max_index_stage1[2*i+1];
            end
        end
        // Handle the last element (if odd number of inputs)
        max_value_stage2[2] = max_value_stage1[4];
        max_index_stage2[2] = max_index_stage1[4];

        // Stage 3: Final comparison
        if (max_value_stage2[0] > max_value_stage2[1]) begin
            if (max_value_stage2[0] > max_value_stage2[2]) begin
                max_value_stage3 = max_value_stage2[0];
                max_index_stage3 = max_index_stage2[0];
            end else begin
                max_value_stage3 = max_value_stage2[2];
                max_index_stage3 = max_index_stage2[2];
            end
        end else begin
            if (max_value_stage2[1] > max_value_stage2[2]) begin
                max_value_stage3 = max_value_stage2[1];
                max_index_stage3 = max_index_stage2[1];
            end else begin
                max_value_stage3 = max_value_stage2[2];
                max_index_stage3 = max_index_stage2[2];
            end
        end

        // Assign final max index
        out_index = max_index_stage3;
        out_value = max_value_stage3;
    end
endmodule


//          1
//         ---
//        |   |
//      6 | 7 | 2
//         ---
//        |   |
//      5 | 4 | 3
//         ---

module seven_segment (
    input  wire [3:0] in,
    output reg  [6:0] out
);
    always @(*) begin
        case(in)
            //          .7654321
            0:  out = 7'b0111111;
            1:  out = 7'b0000110;
            2:  out = 7'b1011011;
            3:  out = 7'b1001111;
            4:  out = 7'b1100110;
            5:  out = 7'b1101101;
            6:  out = 7'b1111100;
            7:  out = 7'b0000111;
            8:  out = 7'b1111111;
            9:  out = 7'b1100111;
            default:
                out = 7'b0000000;
        endcase
    end
endmodule

