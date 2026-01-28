# Design Specification: RISC-V STA & ECO Flow

## 1. Design Overview
*Core Architecture: The design under test(DUT) is a **RISC-V CPU core**.
*Abstraction Level: The agent deals primarily with the **Gate-Level Netlist** generated after Synthesis. Synthesis is a process of conversion of RTL code to gate-level netlist. The tool used to perform is Yosys.
*Goal: Perform Static Timing Analysis (STA), identify violations, and suggest Engineering Change Order (ECO) patches to meet timing constraints.

## 2. The Synthesis & Library Foundation
* Synthesis Process:The RTL (Verilog) has been mapped to a specific technology library (**Sky130**) to create a gate-level netlist.
* Liberty Files (.lib): All standard cells used in the netlist are defined in the `.lib` file. It contains information about the standard cells, its defined characteristics and parameters like cell area,cell name,cell drive strength,Look Up tables for calculation of cell delays.
* Cell Parameters: The agent must reference the `.lib` for:
    * Area: Physical footprint of the cell.
    * Drive Strength: The ability of a cell to drive a capacitive load (e.g., xnor2_1 vs xnor2_4).
    * Look-Up Tables (LUT): Multi-dimensional tables used to calculate **Cell Delay** based on input transition and output load.


## 3. Timing Environment & Tools
* STA Tool: **OpenSTA** (running inside a Docker container named "openlane").
* Constraints: All timing targets (Clock Period, clock uncertainty, clock transition) are defined in **constraints.sdc**.
* Execution: The analysis is driven by **run_sta.tcl**, which automates the loading of libraries, link the design, read the .sdc file, read netlist and generate the setup report.
* Output: The tool generates a **timing_report.rpt** which focuses on the **Worst Negative Slack (WNS)** for  **Reg-to-Reg** (register-to-register) path.

## 4. Timing Physics & Trade-offs
* Delay Modeling: Cell delay is a function of:
    1. Input Transition: The "slew" or sharpness of the incoming signal.
    2. Output Load: The total capacitance (wires + fan-out pins) the gate must charge.
* The Drive Strength Trade-off: **Upsizing:** Increasing drive strength (e.g., swapping _1 for _4) reduces the delay of the current gate by charging the load faster.
    * The Penalty: A higher drive-strength gate offers **higher input capacitance** to the previous gate in the chain, potentially slowing down the previous stage. So while Upsizing any gate we have to identify the best cell that can be upsized without hampering the other delays to close timing.



## 5. Setup Time (Max-Delay) Fix Strategy
* Concept: Data must arrive at the capture flip-flop before the clock edge, minus the setup time (T_setup).
* Optimization Goal: To fix a Setup Violation (Negative Slack), the agent must **reduce the combinational delay** between the Launch Flop and the Capture Flop.
* Primary Tactics:
    1. Cell Sizing: Upsize gates on the critical path to drive heavy loads faster.
    2. Buffer Insertion: Split long, high-capacitance wires with buffers to improve transition times.
    3. Logic Restructuring:(If sizing fails) move or reduce the levels of logic between registers.
    4. Swapping Cells: Swap cells to a LVT OR LVTLL version if it that has lesser delay.

**IN THIS TASK ITS MANDATORY TO STICK ONLY TO "CELL SIZING" AND NOT ANY OTHER METHODS**

## 6. File Structure:

The files structure are as follows:
Netlist : sources/netlist.v
SDC : sources/constraint.sdc
LIB : sky130_fd_sc_hd__tt_025C_1v80.lib
MODEL CELLS: sources/cells
STA TCL FILE : sources/run_sta.tcl
RTL FILE : sources/riscv_core.V



