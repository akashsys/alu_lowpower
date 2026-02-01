import os
import re
import subprocess
import pytest
from pathlib import Path
from cocotb_tools.runner import get_runner
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# --- CONFIGURATION ---
CONTAINER_ID = "openlane"

def get_dynamic_container_path():
    """
    Locates the .task_dir file created by the agent.
    If not found, it uses the standard project root in the container.
    """
    test_dir = Path(__file__).resolve().parent
    state_file = test_dir.parent / "sources" / ".task_dir"
    
    # 1. PRIORITY: Use the agent's random directory if it exists
    if state_file.exists():
        path = state_file.read_text().strip()
        if path:
            return path
            
    # 2. LOGIC FALLBACK: Use the default project mount point 
    return "/openlane/PHINITY"

# ==============================================================================
# 1. THE PYTEST RUNNER
# ==============================================================================
def test_vlsi_signoff_runner():
    """Orchestrates sync and Cocotb simulation."""
    #os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:2375"
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    
    sim = os.getenv("SIM", "icarus")
    proj_path = Path(__file__).resolve().parent.parent 
    sources_dir = proj_path / "sources"
    
    # Resolve dynamic path for this specific agent task
    current_task_path = get_dynamic_container_path()

    # --- Step 1: Sync to Docker ---
    print(f"\nSyncing to Docker container {CONTAINER_ID} at {current_task_path}...")
    subprocess.run(["docker", "exec", CONTAINER_ID, "mkdir", "-p", current_task_path], check=True)
    subprocess.run(f"docker cp \"{sources_dir}/.\" {CONTAINER_ID}:{current_task_path}/", shell=True, check=True)

    # --- Step 2: Setup Cocotb Runner ---
    sources = [sources_dir / "netlist.v"]
    runner = get_runner(sim)

    runner.build(
        sources=sources,
        hdl_toplevel="elastic_credit_arbiter",
        always=True,
        build_args=[
            f"-y{sources_dir}/cells/base",
            f"-y{sources_dir}/cells/strength", 
            f"-y{sources_dir}/models",          
            f"-I{sources_dir}/cells/base",      
            f"-I{sources_dir}/models",   
            "-Y.v",     
            "-grelative-include",
        ]
    )    

    runner.test(
        hdl_toplevel="elastic_credit_arbiter",
        test_module=Path(__file__).stem
    )

# ==============================================================================
# 2. THE COCOTB TESTS (VLSI Sign-off Checks)
# ==============================================================================

@cocotb.test()
async def test_wns_slack(dut):
    """Cocotb Test: Worst Negative Slack check via Dynamic Docker Path"""
    #os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:2375"
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    current_task_path = get_dynamic_container_path()
    WNS_TARGET = 0

    dut._log.info(f"Analyzing Timing in: {current_task_path}")

    # --- Step 1: Execute STA ---
    # We use the dynamic path resolved from .task_dir
    cmd = ["docker", "exec", CONTAINER_ID, "bash", "-c", f"cd {current_task_path} && sta -no_init run_sta.tcl"]
    subprocess.run(cmd, check=True)

    # --- Step 2: Copy report back ---
    subprocess.run(f"docker cp {CONTAINER_ID}:{current_task_path}/timing_report.rpt .", shell=True, check=True)

    # --- Step 3: Parse and Validate ---
    with open("timing_report.rpt", "r") as f:
        report_content = f.read()

    all_slacks = re.findall(r"([-+]?[\d\.]+)\s+slack", report_content)

    if all_slacks:
        wns = min(float(s) for s in all_slacks)
        status_msg = f"WNS is {wns}ns (Target: >= {WNS_TARGET}ns)"
        
        if wns >= WNS_TARGET:
            dut._log.info(f"TIMING MET: {status_msg}")
        else:
            dut._log.error(f"TIMING VIOLATED: {status_msg}")

        assert wns >= WNS_TARGET, f"Timing check failed: {status_msg}"
    else:
        raise RuntimeError("Slack not found in report.")

@cocotb.test()
async def test_area_constraint(dut):
    """Cocotb Test: Chip Area check via script.ys and report extraction"""
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    current_task_path = get_dynamic_container_path()
    AREA_CEILING = 10556.0

    dut._log.info(f"Analyzing Area in: {current_task_path}")

    # --- Step 1: Execute Yosys using the .ys script ---
    # This generates the area.rpt inside the container
    cmd = ["docker", "exec", CONTAINER_ID, "bash", "-c", f"cd {current_task_path} && yosys area.ys"]
    subprocess.run(cmd, check=True)

    # --- Step 2: Copy report back to host ---
    # Parity with timing_report.rpt logic
    subprocess.run(f"docker cp {CONTAINER_ID}:{current_task_path}/area.rpt .", shell=True, check=True)

    # --- Step 3: Parse and Validate ---
    with open("area.rpt", "r") as f:
        report_content = f.read()

    # Capture the area number
    area_match = re.search(r"Chip area.*:\s*([\d\.]+)", report_content)

    if area_match:
        current_area = float(area_match.group(1))
        current_area_rd = round(current_area, 3)
        status_msg = f"Area is {current_area_rd} um^2 (Target: <= {AREA_CEILING})"
        
        if current_area_rd <= AREA_CEILING:
            dut._log.info(f"AREA MET: {status_msg}")
        else:
            dut._log.error(f"AREA VIOLATED: {status_msg}")

        assert current_area_rd <= AREA_CEILING, f"Area check failed: {status_msg}"
    else:
        # Debugging aid: show what the file actually contains if parsing fails
        dut._log.error(f"Regex failed. Report snippet:\n{report_content[-200:]}")
        raise RuntimeError("Area data not found in area.rpt.")



# ==============================================================================
# 3. FUNCTIONAL TESTS (Hardware Logic)
# ==============================================================================

async def reset_dut(dut):
    dut.rst_n.value = 0
    await Timer(10, units="ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_arbiter_full_logic(dut):
    """Full Logic Check: Priority, Starvation, Credits, and Elasticity."""
    clock = Clock(dut.clk, 3.2, units="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # --- 1. Fixed Priority Check ---
    dut.packet_size.value = 0x10
    dut.request.value = 0b1001 
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.grant.value == 0b0001, "Port 0 should win via fixed priority"

    # --- 2. Starvation Escalation Check ---
    dut._log.info("Stalling Port 3 to escalate priority...")
    for _ in range(35): 
        await RisingEdge(dut.clk)
    
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.grant.value == 0b1000, "Port 3 should win via Starvation Escalation (Tier 1)"

    # --- 3. Credit Exhaustion Check ---
    # Port 0 (1 grant) and Port 3 (1 grant) used 0x10 each. Remaining: 0x70.
    dut.packet_size.value = 0x71
    dut.request.value = 0b1000 
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.grant_valid.value == 0, "Error: Grant issued with insufficient credits"
    dut._log.info("Credit Guard Verified.")

    # --- 4. Elastic Increment Check ---
    dut.request.value = 0x0
    dut._log.info("Idling to allow LFSR increments...")
    for _ in range(100):
        await RisingEdge(dut.clk)

    # Bucket should now exceed 0x80 due to idle increments
    dut.packet_size.value = 0x85
    dut.request.value = 0b0001
    await RisingEdge(dut.clk)
    await Timer(1, "ns")
    assert dut.grant.value == 0b0001, "Elasticity failed: Bucket did not increment while idle"
    dut._log.info("Full Functional Suite Passed.")