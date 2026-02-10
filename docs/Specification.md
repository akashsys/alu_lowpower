# Design Specification: 


Design Overview
*Core Architecture: The design under test(DUT) is a "elastic_credit_arbiter" module. 
===============================================================================
PURPOSE
===============================================================================

This module controls access to a shared resource among multiple requesters. Only one requester may access the resource per clock cycle. This module has a 2-cycle entry/exit latency.

The design enforces:

1) **Credit-based flow control**: Each requester maintains a credit bucket that tracks its available resource capacity. A requester can only be granted access if its credit bucket value is greater than or equal to the current packet_size. When a grant is issued, requester's credit bucket is updated as described further and its age counter resets, when a grant is not issued requester's credit bucket equals the speculative credit in idle state and age counter increments, remember for age counter to increase its not required for the requester to be eligble, so even if a non-eligible requester is asking for access and its not granted its age counter increments. This mechanism prevents resource oversubscription.

2) **Starvation prevention**: Each requester maintains an age counter that increments every cycle when the requester is actively requesting (request signal asserted) but not granted access, regardless of whether it currently has sufficient credits. Once the age counter reaches the AGE_THRESHOLD, that requester transitions to high-priority status. This ensures that even credit-exhausted requesters can eventually gain high priority and escape starvation. 

IF A high priority request (eg. port 3) and normal priority request(eg. port 0) is asking for grant then port 3 should be granted as it is eligble(having enough credits),aged and actively requesting. IF NORMAL PRIORIRY REQUEST is granted over a high priority request, your starvation logic is wrong and you should think about re-building logic till high priority request is granted over a normal prioriry request this is because port 3 has aged(crossed or reached AGE_THRESHOLD) and must be served first over a normal priority request,

A request becomes a high priority
1) eligible(credit bucket value is greater than or equal to the current packet_size)
2) aged
3) asking for request

A request becomes a normal priority
1) eligible (credit bucket value is greater than or equal to the current packet_size)
2) asking for request

3) **Deterministic arbitration**: When multiple requesters compete for access, a fixed priority order (Requester[0] > Requester[1] > Requester[2] > Requester[3]) is enforced. FIXED PRIORITY ORDER FOLLOWS ONLY WHEN TWO OR MORE normal priortity requests OR TWO OR MORE HIGH priortity requests ARE asking for grant. 

4) **Elastic recovery**: When a requester is not requesting or not allowed while requesting, in both cases its credit bucket is incrementally replenished using LFSR-based pseudo-random perturbations, up to a maximum of MAX_CREDIT. This "elastic" behavior allows credit capacity to recover during periods of inactivity, ensuring the system can handle future bursts of traffic.

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
- packet_size[7:0]
    Size of the transaction requested. This value is compared against per-requester credit.

Outputs:
- grant[3:0]
    One-hot grant vector. At most one bit may be high in any cycle.

- grant_valid
    Indicates whether grant is valid in the current cycle. If its high it means the request can be processed by module based on credits.


===============================================================================
PARAMETERS AND CONSTANTS
===============================================================================

- Number of requesters is fixed at 4.
- AGE_THRESHOLD is a constant (8-bit) that determines when a requester becomes high priority. Whenever a requester is asking for access but the request is not granted, its age counter increases by 1, regardless of whether the requester currently has sufficient credits. If age_counter for a request reaches or exceeds AGE_THRESHOLD, the requester becomes a high priority request. A typical value for AGE_THRESHOLD is 8'h20. Now if more than one request becomes high priority then we need to follow priority with Req[0]>Req[1]>Req[2]>Req[3]. Even if in non-priority mode, if more than one request wants to access, the priority follows as Req[0]>Req[1]>Req[2]>Req[3]

- MAX_CREDIT is the maximum allowed credit value (8-bit, saturating).


Each requester maintains

1) credit_bucket(8-bit)
   credit bucket is how much credit the requester has in its bucket to send the data. If request want to send any packet of data, then it must have credits more or equal to packet size to be eligible.
2) age_counter(8-bit)
   Represents how long requester has been waiting without being granted.


===============================================================================
WORKING
===============================================================================

A request is eligible for arbitration only if: credit_bucket is greater than or equals to the packet_size.
If this condition is false:
- The request is ignored.
- The requester does not participate in arbitration.
- No grant may be issued to that requester.

If any request is granted then calculate a speculative credit left in its bucket that equals to remaining credits after transferring packet size of data added with pseudo randomness using LFSR that makes sure that arbiter is fair and it prevents one port from consistently "shadowing" another.

If a requester is not asking for access or request is not granted, in both cases calculate a speculative idle state credit in its bucket that equals to its original credit bucket added with pseudo randomness using LFSR, but make sure that this credit does not cross the MAX_CREDIT limit.

A request becomes a high priority
1) eligible
2) aged
3) asking for request

A request becomes a normal priority
1) eligible
2) asking for request

 When multiple requesters compete for access, a fixed priority order (Requester[0] > Requester[1] > Requester[2] > Requester[3]) is enforced. 
 FIXED PRIORITY ORDER FOLLOWS ONLY WHEN TWO OR MORE normal priortity requests OR TWO OR MORE HIGH priortity requests ARE asking for grant. 
 IF A high priority request (eg. port 3) and normal priority request(eg. port 0) is asking for grant then port 3 should be granted as its a high priority(eligble,aged,asking for access)




- If request is granted in a cycle:
      - Its remaining credit equals to speculated credits discussed before (credit - packet_size + LFSR perturbation)
      - Its age counter resets to 0

- If request signal is asserted but request is not granted in a cycle:
      - Its credit bucket follows elastic behaviour, incrementing by LFSR perturbation (saturating at MAX_CREDIT)
      - Its age counter increments by 1 (regardless of whether it has sufficient credits)

- If request signal is de-asserted (requester is idle) in a cycle:
      - Its credit bucket follows elastic behaviour, incrementing by LFSR perturbation (saturating at MAX_CREDIT)
      - Its age counter remains unchanged (aging only occurs when actively requesting)

A request is said to be aged if its age counter crosses or reaches the maximum threshold.

Only one requester may be granted per cycle.


LFSR USAGE

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
- Is seeded to a non-zero value on reset.
 
LFSR Specification
 -Type: Fibonacci Linear Feedback Shift Register (LFSR)
 -Register Width: 16 bits (lfsr_reg[15:0])
 -Shift Operation: On each rising edge of clk, the register shifts toward the MSB.
  The newly computed feedback bit is inserted at the LSB (bit 0).
  Feedback Taps: Bit positions 15, 13, 12, and 10 (zero-based indexing)
  The generated values are used as small perturbations in credit updates.

  feedback = lfsr_reg[15] ^ lfsr_reg[13] ^ lfsr_reg[12] ^ lfsr_reg[10];
  lfsr_reg <= {lfsr_reg[14:0], feedback};
  Characteristic Polynomial: G(x) = x^{16} + x^{14} + x^{13} + x^{11} + 1
  Initial Seed: 16'hACE1 (loaded on active-low reset)

===============================================================================
RESET BEHAVIOR
===============================================================================

On reset (rst_n == 0):
- All credit_bucket values are initialized to a fixed mid-range value
- All age_counter values are set to 0
- Speculated bucket values are set to 0.
- Speculated idle state bucket are set to 0.
- Speculated age counter(responsible for incrementing age counter by 1)are set to 0.
- No grant is issued
- LFSR is seeded to a non-zero value
- All request access are made to 0.
- Outputs are set to 0.


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
Timing Requirement: The design must achieve zero or positive slack after synthesis. The agent is responsible for ensuring the combinational logic depth is minimized to meet this frequency. Further, even after synthesis , timing is not we may use ECOs to fix to upsize slow cells.
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

**IN THIS TASK TO FIX TIMING USE "CELL SIZING" , IF NETLIST IS NOT ABLE TO MEET TIMING**

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



