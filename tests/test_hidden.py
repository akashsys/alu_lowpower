import os
import re
import subprocess
import pytest
from pathlib import Path
from cocotb_tools.runner import get_runner

# --- CONFIGURATION ---
CONTAINER_ID = "openlane"
CONTAINER_PATH = "/openlane/PHINITY"

# ==============================================================================
# 1. THE PYTEST RUNNER
# ==============================================================================
def test_vlsi_signoff_runner():
    """
    Orchestrates the sync to Docker and the Cocotb simulation build.
    """
    sim = os.getenv("SIM", "icarus")
    # Correct path to reach 'sources' from 'tests' folder
    proj_path = Path(__file__).resolve().parent.parent 
    sources_dir = proj_path / "sources"

    # --- Step 1: Sync to Docker for STA ---
    # This sends .lib, .sdc, and .tcl to the container
    print(f"\nSyncing to Docker container {CONTAINER_ID}...")
    subprocess.run(["docker", "exec", CONTAINER_ID, "mkdir", "-p", CONTAINER_PATH], check=True)
    subprocess.run(f"docker cp \"{sources_dir}/.\" {CONTAINER_ID}:{CONTAINER_PATH}/", shell=True, check=True)

    # --- Step 2: Setup Cocotb Runner ---
    # Only Verilog design files go in 'sources'
    sources = [sources_dir / "netlist.v"]
    
    cells_path = sources_dir / "cells"
    models_path = sources_dir / "models"
    
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
                "-grelative-include",  # Keep this as its own string
            ]   )    
    # Step 3: Trigger the Cocotb tests defined below
    runner.test(
        hdl_toplevel="riscv_core",
        test_module=Path(__file__).stem
    )

# ==============================================================================
# 2. THE COCOTB TESTS (VLSI Sign-off Checks)
# ==============================================================================
import cocotb

@cocotb.test()
async def test_wns_slack(dut):
    """Cocotb Test: Worst Negative Slack check via Docker STA"""

    # --- Step 1: Execute STA ---
    dut._log.info("Running OpenSTA inside Docker container...")
    cmd = ["docker", "exec", CONTAINER_ID, "bash", "-c", f"cd {CONTAINER_PATH} && sta -no_init run_sta.tcl"]
    subprocess.run(cmd, check=True)

    # --- Step 2: Copy the report back to Windows ---
    subprocess.run(f"docker cp {CONTAINER_ID}:{CONTAINER_PATH}/timing_report.rpt .", shell=True, check=True)

    # --- Step 3: Parse the Report ---
    with open("timing_report.rpt", "r") as f:
        report_content = f.read()

    # --- Step 4: Extract WNS ---
    all_slacks = re.findall(r"([-+]?[\d\.]+)\s+slack", report_content)

    if all_slacks:
        wns = min(float(s) for s in all_slacks)
        
        # Determine the status message
        if wns >= 0:
            msg = f"TIMING MET : WNS is {wns}ns"
            dut._log.info(msg)
        else:
            msg = f"TIMING VIOLATED : WNS is {wns}ns"
            dut._log.error(msg)

        # The assertion ensures the 'STATUS' column shows PASS/FAIL
        # The message here often appears in the 'Notes' or failure log
        assert wns >= 0, msg
        
        # Explicitly log the final result so it appears right above the table
        print(f"\nREGRESSION RESULT: {msg}\n")
        
    else:
        raise RuntimeError("Slack not found in timing_report.rpt. Check your SDC constraints.")