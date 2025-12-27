### Power-Aware ALU


### **OVERVIEW**

The Arithmetic Logic Unit (ALU) is a synchronous digital block designed for 16-bit arithmetic and logical operations. This design incorporates power-aware features by modeling a Power-Off state through Clock Enabling Control and Output Clamping. These mechanisms ensure the design behaves predictably when the ALU power domain is logically disconnected, preventing invalid data propagation.

This design intentionally represents a **late-stage Engineering Change Order (ECO) scenario**. The current synthesized netlist was generated from Yosys tool from a version of the RTL where the asynchronous reset logic was incorrectly optimized or omitted. 

During post-synthesis and power-aware verification, a functional issue was identified related to **power-off behavior and output determinism**. At this point in the project lifecycle:

* RTL has already been synthesized
* Module interfaces are frozen
* Full re-synthesis is not permitted
* Only minimal, localized RTL changes are allowed

---

### **INPUTS AND OUTPUTS**

* CLK: The system clock driving all internal sequential logic.
* RST_N: An active-low asynchronous reset that initializes all internal registers.
* A / B: Dual 16-bit operand inputs for mathematical and logical processing.
* OPCODE: A 4-bit control signal that selects the specific operation for the ALU to perform.
* START: A signal used to initiate a new ALU operation when the unit is in its idle state.
* DISS_CLK: An active-high control signal that initiates the power-off sequence by disabling the clock enable and activating the output clamp.
* RESULT: The primary 16-bit output of the top-level design, which either shows ALU results or the clamp value.
* BUSY: A status flag indicating that a multi-cycle operation is currently executing.
* CLAMP_OBS: A dedicated observation port that exposes the internal constant clamp value for verification purposes.

---

### **CLOCK ENABLING AND POWER-OFF LOGIC**

In this architecture, power gating is modeled using an Enable-based Gating strategy rather than physically removing the clock source:

* The alu_clk_off Module: This module acts as the power controller, monitoring the diss_clk input to generate the alu_en (ALU Enable) signal.
* Logical Implementation: The enable signal is defined by the logic alu_en = !diss_clk, meaning the ALU is only active when the power-off signal is de-asserted.
* State Preservation: When diss_clk is high, the en input to the ALU goes low. This causes all internal registers—including the state machine, cycle counters, and intermediate result registers—to freeze in their current state. No state transitions or computations can occur until the domain is powered back on.

---

### **OUTPUT CLAMPING BEHAVIOR**

When the ALU power domain is OFF (diss_clk = 1), the output must be driven to a deterministic value via a multiplexer in the top module.

**Why Clamping is Required:**
In a real-world SoC (System on Chip), when a power domain is gated (turned off), its output signals often become floating or undefined (represented as X or Z in simulation). If these undefined signals propagate to other parts of the chip that are still ON, they can cause:

1. Metastability
2. Functional Failures
3. Power Leakage

To prevent this, an Isolation Cell (modeled here as a Mux-based clamp) is used to ensure the RESULT remains at a known, safe value.

**Clamping Implementation:**

* Clamp Value: The design uses a fixed constant of 16'd0 as the safe state.
* Determinism: The specification requires that the clamp value must always be a known value (0 or 1) and never X or Z.
* Matching: When diss_clk = 1, the top-level RESULT must exactly match the CLAMP_OBS port value to prove the isolation logic is active.

---

### **FUNCTIONAL OPERATION AND OPCODE LIST**

The following list defines the 4-bit opcode values and the corresponding operation performed by the ALU.

* Opcode 4'b0000: Addition operation. Calculates the sum of A and B (Result = A + B) in a single clock cycle.
* Opcode 4'b0001: Subtraction operation. Calculates the difference (Result = A - B) in a single clock cycle.
* Opcode 4'b0010: Bitwise AND operation. Performs a logical AND on operands A and B in a single clock cycle.
* Opcode 4'b0011: Bitwise OR operation. Performs a logical OR on operands A and B in a single clock cycle.
* Opcode 4'b0100: Bitwise XOR operation. Performs a logical XOR on operands A and B in a single clock cycle.
* Opcode 4'b0101: Bitwise NOR operation. Performs a logical NOR on operands A and B in a single clock cycle.
* Opcode 4'b0110: Shift-left logical (SLL). Shifts operand A left by the amount specified in the lower 4 bits of operand B in a single clock cycle.
* Opcode 4'b0111: Bitwise XNOR operation. Performs a logical XNOR on operands A and B in a single clock cycle.
* Opcode 4'b1000: Multiplication (MUL). A multi-cycle operation that calculates the product of A and B (Result = A * B). This operation requires 4 clock cycles to complete.
* Opcode 4'b1001: Division (DIV). A multi-cycle operation that calculates the quotient (Result = A / B). This operation requires 8 clock cycles to complete. If the divisor B is 0, the result is forced to 0.

---

### **MULTI-CYCLE SEQUENTIAL OPERATIONS**

Multi-cycle operations utilize an internal state machine and cycle counter to manage execution over several clock periods.

* Multi-Cycle Protocol: When a multi-cycle opcode (MUL or DIV) is detected along with the assertion of the start signal, the ALU transitions from the IDLE state to the corresponding execution state (MUL_EXEC or DIV_EXEC).
* Busy Signal: The busy output is asserted as soon as the ALU leaves the IDLE state and remains high until the operation is finished and the unit returns to IDLE.
* Cycle Counting: An internal cycle_cnt increments on every active clock edge while the ALU is in an execution state.
* Multiplication Timing: For opcode 4'b1000, the ALU stays in the MUL_EXEC state for 4 cycles. The result is calculated and latched when cycle_cnt reaches 3.
* Division Timing: For opcode 4'b1001, the ALU stays in the DIV_EXEC state for 8 cycles. The result is calculated and latched when cycle_cnt reaches 7.
