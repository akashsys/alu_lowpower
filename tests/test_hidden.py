import os
import re
import subprocess
import pytest
from pathlib import Path
from cocotb_tools.runner import get_runner
import cocotb

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
        hdl_toplevel="riscv_core",
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
        hdl_toplevel="riscv_core",
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
    WNS_TARGET = 0.15

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
    """Cocotb Test: Chip Area check via Report-File extraction"""
    AREA_CEILING = 60878.387
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    current_task_path = get_dynamic_container_path()

    dut._log.info(f"Analyzing Area in: {current_task_path}")

    # 1. Define the Yosys command to run analysis
    yosys_cmd = (
        "read_liberty -lib sky130_fd_sc_hd__tt_025C_1v80.lib; "
        "read_verilog netlist.v; "
        "stat -liberty sky130_fd_sc_hd__tt_025C_1v80.lib"
    )
    
    # 2. Execute Yosys and REDIRECT output to area.rpt inside the container
    # We use ' > area.rpt 2>&1' to capture both success and error messages into the file
    gen_rpt_cmd = [
        "docker", "exec", CONTAINER_ID, "bash", "-c", 
        f"cd {current_task_path} && yosys -p '{yosys_cmd}' > area.rpt 2>&1"
    ]
    
    dut._log.info("Generating area report file...")
    subprocess.run(gen_rpt_cmd, check=True, shell=True)

    # 3. Read the generated report file back from the container
    read_rpt_cmd = ["docker", "exec", CONTAINER_ID, "cat", f"{current_task_path}/area.rpt"]
    result = subprocess.run(read_rpt_cmd, capture_output=True, text=True, check=True, shell=True)
    
    report_content = result.stdout

    # 4. Robust Parsing of the file content
    # Look for the number following 'Chip area'
    area_match = re.search(r"Chip area.*:\s*([\d\.]+)", report_content)

    if area_match:
        current_area = float(area_match.group(1))
        # Round to 3 decimal places for target comparison
        current_area_rd = round(current_area, 3)
        
        status = "PASSED" if current_area_rd <= AREA_CEILING else "FAILED"
        msg = f"Area: {current_area_rd} um^2 | Target: <= {AREA_CEILING}"
        
        if status == "PASSED":
            dut._log.info(f"AREA SIGN-OFF {status}: {msg}")
        else:
            dut._log.error(f"AREA SIGN-OFF {status}: {msg}")

        assert current_area_rd <= AREA_CEILING, f"Area Sign-off Failed: {msg}"
    else:
        # If regex fails, show exactly what Yosys wrote to the file for debugging
        dut._log.error("FAILED TO PARSE REPORT. File content (last 300 chars):")
        dut._log.error(f"\n{report_content[-300:]}")
        raise RuntimeError(f"Area data missing from {current_task_path}/area.rpt")