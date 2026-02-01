# Design Specification: 

## 1. Design Overview
*Core Architecture: The design under test(DUT) is a "elastic_credit_arbiter" module. 

The elastic_credit_arbiter is a high-speed, credit-based 4-port arbiter designed for congestion management in Network-on-Chip (NoC) or bus architectures. 

It uses a speculative math architecture to pre-calculate credit updates, enabling rapid flow-control decisions.

Key Performance Metrics Technology: SkyWater 130nm (Sky130 HD) High-Density Standard Cells.
Clock Period :3.2 ns.
Targeted Frequency: 312.5 MHz.Total 
Chip Area: 10,555.12 $\mu m^2$.
Optimization Penalty: Achieving timing closure required only a 0.34% area increase over the netlist.

1. Functional Objective-
Create a 4-port, credit-based arbiter that manages resource allocation across four independent request sources. The design must handle flow control based on available "credits" and prevent source starvation through a dynamic aging mechanism.

2. Performance Constraints-
Target Clock Period: 3.2ns (312.5 MHz) using the Sky130 HD library.
Timing Requirement: The design must achieve zero or positive slack after synthesis. The agent is responsible for ensuring the combinational logic depth is minimized to meet this frequency.
Physical Budget: Total area must not exceed approximately 10,556 micrometere^2.

3. Logic Requirements
Credit System: Maintain four internal 8-bit credit buckets, initialized to 8'h80. A request can only be granted if the corresponding bucket value is greater than or equal to the current packet_size input.
Elastic Entropy: Implement a 16-bit LFSR with taps at positions [16, 14, 13, 11]. The buckets must be "elastic"—meaning they should increment by a pseudo-random amount derived from the LFSR when idle, up to a maximum of 8'hFF.
Aging & Starvation: * Maintain an 8-bit age counter for each port. The counter increments every cycle a request is pending but not granted. If a counter reaches the threshold of 8'h20, that port must be treated with higher priority than non-aged ports.

4. Interface
Inputs: clk, rst_n (async, active-low), request[3:0], packet_size[7:0].
Outputs: grant[3:0] (one-hot), grant_valid.

Priority Hierarchy:
Tier 1: Requests with sufficient credits AND an active age threshold.
Tier 2: Requests with sufficient credits but no age threshold.
Within each tier, use a fixed priority scheme (Port 0 > Port 1 > Port 2 > Port 3).

5. Implementation Rules
The code must be synthesizable Verilog.
The internal state (buckets and age counters) must update accurately based on the grant results.
The agent must optimize the logic paths such that 8-bit arithmetic and priority encoding do not form a single, unmanageable combinational chain that violates the 3.2ns period.


6. Functional Execution Example
The implementation must produce the following cycle-accurate behavior given a constant packet_size of 8'h10 (16 credits).

Cycle 0: Initialization
State: rst_n is de-asserted.
Buckets: All ports initialized to 8'h80 (128 credits).
Age Counters: All initialized to 8'h00.
LFSR: Initialized to seed 16'hACE1.

Cycle 1: Multi-Port Request
Input: request = 4'b1100 (Ports 2 and 3 requesting).
Logic: Both have >16 credits. Port 2 has higher fixed priority.
Result: grant = 4'b0100 (Port 2 wins).
Update: * Port 2 Bucket: 8'h80 - 8'h10 + LFSR_bit.
Port 3 Bucket: 8'h80 + LFSR_bit (Idle increment).
Port 3 Age: Increments to 8'h01 (Requested but not granted).

Cycle 2: Starvation Escalation
Scenario: Assume Port 3 has been denied for 32 consecutive cycles.
State: age_counter[3] = 8'h20 (Threshold reached).
Input: request = 4'b1001 (Ports 0 and 3 requesting).
Logic: Under normal fixed priority, Port 0 would win. However, Port 3 is now Aged (Tier 1), while Port 0 is Normal (Tier 2).
Result: grant = 4'b1000 (Port 3 wins due to Aging/Starvation Tier).
Update: age_counter[3] resets to 8'h00 immediately upon grant.

Cycle 3: Credit Depletion
Scenario: Port 0 continues to request while its bucket drops to 8'h08.
Input: packet_size = 8'h10. request = 4'b0001.
Logic: bucket[0] (8) < packet_size (16).
Result: grant = 4'b0000, grant_valid = 0.
Update: Port 0 bucket increments by LFSR_bit only. Port 0 age increments because a request was present but could not be serviced.

#Implementation Compliance
Zero-Latency Response: The grant for a given cycle's request must be valid for that same cycle's state, but the timing path from request to grant to bucket_update must be optimized for the 3.2ns target.
Saturation: If a bucket is at 8'hFF, the elastic increment must not roll over to 8'h00.
Polynomial Integrity: The LFSR must shift every cycle regardless of whether a grant is issued, ensuring continuous entropy.




## 2. The Synthesis & Library Foundation
* Synthesis Process:The RTL (Verilog) has been mapped to a specific technology library (**Sky130**) to create a gate-level netlist.
* Liberty Files (.lib): All standard cells used in the netlist are defined in the `.lib` file. It contains information about the standard cells, its defined characteristics and parameters like cell area,cell name,cell drive strength,Look Up tables for calculation of cell delays.
* Cell Parameters: The agent must reference the `.lib` for:
    * Area: Physical footprint of the cell.
    * Drive Strength: The ability of a cell to drive a capacitive load (e.g., xnor2_1 vs xnor2_4).
    * Look-Up Tables (LUT): Multi-dimensional tables used to calculate **Cell Delay** based on input transition and output load.


## 3. Timing Environment & Tools
* SYNTHESIS TOOL : yosys (running inside a Docker container named "openlane").
* STA Tool: **OpenSTA** (running inside a Docker container named "openlane").
* Constraints: All timing targets (Clock Period, clock uncertainty, clock transition) are defined in **constraints.sdc**.
* Execution: The analysis is driven by **run_sta.tcl**, which automates the loading of libraries, link the design, read the .sdc file, read netlist and generate the setup report.
* Output: The STA tool generates a **timing_report.rpt** which focuses on the **Worst Negative Slack (WNS)** for  **Reg-to-Reg** (register-to-register) path. The yosys tool converts RTL to gate level netlist and generates netlist and gives area information.

## 4. Timing Physics & Trade-offs
* Delay Modeling: Cell delay is a function of:
    1. Input Transition: The "slew" or sharpness of the incoming signal.
    2. Output Load: The total capacitance (wires + fan-out pins) the gate must charge.
* The Drive Strength Trade-off: **Upsizing:** Increasing drive strength (e.g., swapping _1 for _4) reduces the delay of the current gate by charging the load faster.
    * The Penalty: A higher drive-strength gate offers **higher input capacitance** to the previous gate in the chain, potentially slowing down the previous stage. So while Upsizing any gate we have to identify the best cell that can be upsized without hampering the other delays to close timing. Swapping any cell with faster version also increases the chip area so this timing/area trade-off is considered while fixing timing violations.


## 5. Setup Time (Max-Delay) Fix Strategy
* Concept: Data must arrive at the capture flip-flop before the clock edge, minus the setup time (T_setup).
* Optimization Goal: To fix a Setup Violation (Negative Slack), the agent must **reduce the combinational delay** between the Launch Flop and the Capture Flop.
* Primary Tactics:
    1. Cell Sizing: Upsize gates on the critical path to drive heavy loads faster.
    2. Buffer Insertion: Split long, high-capacitance wires with buffers to improve transition times.
    3. Logic Restructuring:(If sizing fails) move or reduce the levels of logic between registers.
    4. Swapping Cells: Swap cells to a LVT OR LVTLL version if it that has lesser delay.

**IN THIS TASK IF YOU ARE NOT ABLE TO FIX TIMING "CELL SIZING" THEN YOU MUST CHANGE THE RTL AND DO RE-SYNTHESIS"

## 6. File Structure:

The files structure are as follows:
Netlist : sources/netlist.v
SDC : sources/constraint.sdc
LIB : sky130_fd_sc_hd__tt_025C_1v80.lib
MODEL CELLS: sources/cells
STA TCL FILE : sources/run_sta.tcl
RTL FILE : sources/elastic_credit_arbiter.v
AREA TCL FILE: sources/area.ys
SYNTHESIS TCL FILE: sources/syn_script.ys



