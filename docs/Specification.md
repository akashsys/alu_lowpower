# Design Specification: 


Design Overview
*Core Architecture: The design under test(DUT) is a "elastic_credit_arbiter" module. 
===============================================================================
PURPOSE
===============================================================================

This module controls access to a shared resource among multiple requesters. Only one requester may access the resource per clock cycle.

The design enforces:
1) Credit-based flow control
2) Starvation prevention
3) Deterministic arbitration
4) Elastic recovery when the system is idle


===============================================================================
INTENT
===============================================================================
This module arbitrates access to a shared resource among 4 requesters.
At most one requester may be granted access per clock cycle.

The arbitration incorporates:
- Credit-based flow control
- Starvation prevention using aging
- Fixed-priority arbitration
- Elastic credit recovery behavior

The implementation is synchronous to a single clock and uses an active-low reset.


===============================================================================
INTERFACE SPECIFICATION
===============================================================================

Clock and Reset:
- clk        : input, system clock
- rst_n      : input, active-low reset

Inputs:
- request[3:0]
    One bit per requester.
    request[i] == 1 indicates requester i is requesting service.

- packet_size[7:0]
    Size of the transaction requested.
    This value is compared against per-requester credit.

Outputs:
- grant[3:0]
    One-hot grant vector.
    At most one bit may be high in any cycle.

- grant_valid
    Indicates whether grant is valid in the current cycle.
    grant_valid == 1 implies exactly one bit of grant is high.


===============================================================================
PARAMETERS AND CONSTANTS
===============================================================================

- Number of requesters is fixed at 4.
- AGE_THRESHOLD is a constant (8-bit) that determines when a requester
  becomes high priority. So whenever a request is made and its not granted its age counter increases by 1. If age_counter[i] reaches or exceeds AGE_THRESHOLD, the requester becomes
a high priority request. A typical value for AGE_THRESHOLD is 8'h20.Now if more than one request becomes high priority then we need to follow priority with Req[0]>Req[1]>Req[2]>Req[3]
- MAX_CREDIT is the maximum allowed credit value (8-bit, saturating). Set it to  8'hFF


===============================================================================
INTERNAL STATE (PER REQUESTER)
===============================================================================

Each requester maintains the following state:

1) credit_bucket[i] (8-bit)
   Represents how much data requester i is allowed to send.

2) age_counter[i] (8-bit)
   Represents how long requester i has been waiting without being granted.


===============================================================================
CREDIT-BASED FLOW CONTROL
===============================================================================

A request is eligible for arbitration only if:

    credit_bucket[i] >= packet_size

If this condition is false:
- The request is ignored
- The requester does not participate in arbitration
- No grant may be issued to that requester


===============================================================================
AGING RULES (STARVATION PREVENTION)
===============================================================================

Age behavior per requester:

- If request[i] == 1 AND requester i is NOT granted in the cycle:
      age_counter[i] increments by 1

- If requester i IS granted:
      age_counter[i] is reset to 0

- If request[i] == 0:
      age_counter[i] does not increment

A requester is considered "aged" when:

    age_counter[i] >= AGE_THRESHOLD


===============================================================================
PRIORITY CLASSIFICATION
===============================================================================

Requests are divided into two priority groups:

HIGH PRIORITY REQUEST:
- request[i] == 1
- credit_bucket[i] >= packet_size
- age_counter[i] >= AGE_THRESHOLD

NORMAL PRIORITY REQUEST:
- request[i] == 1
- credit_bucket[i] >= packet_size


===============================================================================
ARBITRATION RULES
===============================================================================

Arbitration is evaluated once per clock cycle using sampled requests.

Selection order:
1) If any HIGH PRIORITY requests exist:
       arbitration is performed only among HIGH PRIORITY requests
2) Else if any NORMAL PRIORITY requests exist:
       arbitration is performed among NORMAL PRIORITY requests
3) Else:
       no grant is issued

Within a priority group:
- Fixed-priority arbitration is used
- The lowest index requester wins

Priority order:
    requester 0 > requester 1 > requester 2 > requester 3

Only one requester may be granted per cycle.


===============================================================================
GRANT BEHAVIOR
===============================================================================

- grant is one-hot
- grant_valid == 1 when a grant is issued
- grant_valid == 0 when no grant is issued
- grant corresponds to the arbitration decision for the current cycle


===============================================================================
CREDIT UPDATE RULES
===============================================================================

Credit update is performed per requester every cycle.

If requester i IS granted:
- credit_bucket[i] is reduced by packet_size and added by a small pseudo-random value
- age_counter[i] is reset to 0

If requester i is NOT granted:
- credit_bucket[i] is allowed to increase (elastic recovery)
- credit increase is limited to MAX_CREDIT (saturating behavior)
- if request[i] == 1, age_counter[i] increments
- if request[i] == 0, age_counter remains unchanged


===============================================================================
ELASTIC CREDIT RECOVERY
===============================================================================

Elastic behavior models recovery of capacity when a requester is idle.

- Credits may increase even if no explicit downstream credit return exists
- Credit recovery is not deterministic and may vary per cycle
- Credit must never exceed MAX_CREDIT


===============================================================================
LFSR USAGE
===============================================================================

A Linear Feedback Shift Register (LFSR) is used internally to model
pseudo-random behavior.

Purpose of LFSR:
- Introduce variability in credit recovery and credit update
- Avoid perfectly deterministic credit growth across requesters

Restrictions:
- LFSR must NOT affect arbitration priority
- LFSR must NOT affect grant selection directly
- LFSR output may be used only in credit update calculations


===============================================================================
LFSR BEHAVIOR
===============================================================================

The LFSR:
- Is clocked every cycle
- Uses XOR feedback taps
- Produces a deterministic but pseudo-random sequence
- Is seeded to a non-zero value on reset

The generated values are used as small perturbations in credit updates.


===============================================================================
RESET BEHAVIOR
===============================================================================

On reset (rst_n == 0):
- All credit_bucket[i] values are initialized to a fixed mid-range value
- All age_counter[i] values are set to 0
- No grant is issued
- LFSR is seeded to a non-zero value


===============================================================================
GLOBAL GUARANTEES
===============================================================================

The implementation must guarantee:
- At most one grant per cycle
- No grant when credit is insufficient
- No permanent starvation
- Deterministic arbitration outcome for identical conditions
- Credit saturation at MAX_CREDIT


===============================================================================
SUMMARY RULE
===============================================================================

Credit determines eligibility.
Age determines urgency.
Priority determines selection.


===============================================================================
Key Performance Metrics
===============================================================================

Technology:SkyWater 130nm (Sky130 HD) High-Density Standard Cells.
Clock Period :3.2 ns.
Targeted Frequency: 312.5 MHz.
Total Chip Area: 10,555.12 $\mu m^2$.
Optimization Penalty: Achieving timing closure required only a 0.34% area increase over the netlist.

Functional Objective-
Create a 4-port, credit-based arbiter that manages resource allocation across four independent request sources. The design must handle flow control based on available "credits" and prevent source starvation through a dynamic aging mechanism.

Performance Constraints-
Target Clock Period: 3.2ns (312.5 MHz) using the Sky130 HD library.
Timing Requirement: The design must achieve zero or positive slack after synthesis. The agent is responsible for ensuring the combinational logic depth is minimized to meet this frequency.
Physical Budget: Total area must not exceed approximately 10,556 micrometere^2.




===============================================================================
Synthesis & Library Foundation
===============================================================================

* Synthesis Process:The RTL (Verilog) has been mapped to a specific technology library (**Sky130**) to create a gate-level netlist.
* Liberty Files (.lib): All standard cells used in the netlist are defined in the `.lib` file. It contains information about the standard cells, its defined characteristics and parameters like cell area,cell name,cell drive strength,Look Up tables for calculation of cell delays.
* Cell Parameters: The agent must reference the `.lib` for:
    * Area: Physical footprint of the cell.
    * Drive Strength: The ability of a cell to drive a capacitive load (e.g., xnor2_1 vs xnor2_4).
    * Look-Up Tables (LUT): Multi-dimensional tables used to calculate **Cell Delay** based on input transition and output load.

===============================================================================
Timing Environment & Tools
===============================================================================

* SYNTHESIS TOOL : yosys (running inside a Docker container named "openlane").
* STA Tool: **OpenSTA** (running inside a Docker container named "openlane").
* Constraints: All timing targets (Clock Period, clock uncertainty, clock transition) are defined in **constraints.sdc**.
* Execution: The analysis is driven by **run_sta.tcl**, which automates the loading of libraries, link the design, read the .sdc file, read netlist and generate the setup report.
* Output: The STA tool generates a **timing_report.rpt** which focuses on the **Worst Negative Slack (WNS)** for  **Reg-to-Reg** (register-to-register) path. The yosys tool converts RTL to gate level netlist and generates netlist and gives area information.


===============================================================================
Timing Physics & Trade-offs
===============================================================================

* Delay Modeling: Cell delay is a function of:
    1. Input Transition: The "slew" or sharpness of the incoming signal.
    2. Output Load: The total capacitance (wires + fan-out pins) the gate must charge.
* The Drive Strength Trade-off: **Upsizing:** Increasing drive strength (e.g., swapping _1 for _4) reduces the delay of the current gate by charging the load faster.
    * The Penalty: A higher drive-strength gate offers **higher input capacitance** to the previous gate in the chain, potentially slowing down the previous stage. So while Upsizing any gate we have to identify the best cell that can be upsized without hampering the other delays to close timing. Swapping any cell with faster version also increases the chip area so this timing/area trade-off is considered while fixing timing violations.

===============================================================================
Setup Time (Max-Delay) Fix Strategy
===============================================================================

* Concept: Data must arrive at the capture flip-flop before the clock edge, minus the setup time (T_setup).
* Optimization Goal: To fix a Setup Violation (Negative Slack), the agent must **reduce the combinational delay** between the Launch Flop and the Capture Flop.
* Primary Tactics:
    1. Cell Sizing: Upsize gates on the critical path to drive heavy loads faster.
    2. Buffer Insertion: Split long, high-capacitance wires with buffers to improve transition times.
    3. Logic Restructuring:(If sizing fails) move or reduce the levels of logic between registers.
    4. Swapping Cells: Swap cells to a LVT OR LVTLL version if it that has lesser delay.

**IN THIS TASK IF YOU ARE NOT ABLE TO FIX TIMING "CELL SIZING" THEN YOU MUST CHANGE THE RTL AND DO RE-SYNTHESIS"

===============================================================================
File Structure
===============================================================================


The files structure are as follows:
Netlist : sources/netlist.v
SDC : sources/constraint.sdc
LIB : sky130_fd_sc_hd__tt_025C_1v80.lib
MODEL CELLS: sources/cells
STA TCL FILE : sources/run_sta.tcl
RTL FILE : sources/elastic_credit_arbiter.v
AREA TCL FILE: sources/area.ys
SYNTHESIS TCL FILE: sources/syn_script.ys



