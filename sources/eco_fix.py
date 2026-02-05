import re
import argparse
import os

def swap_cell(instance_name, new_cell_type, netlist_path):
    """
    Enhanced ECO tool with better error handling and Docker sync support
    """
    # Verify file existence
    if not os.path.exists(netlist_path):
        print(f"ERROR: Netlist not found at {netlist_path}")
        print(f"       Make sure you've run synthesis first (bash sources/run_sta_cmd.sh)")
        return False

    # Read the netlist
    with open(netlist_path, 'r') as f:
        content = f.read()

    # Regex: Look for [CellType] followed by [InstanceName] and an opening parenthesis
    # Example match: sky130_fd_sc_hd__o311ai_0 _5748_ (
    pattern = rf"(\w+)\s+{re.escape(instance_name)}\s*\("
    
    matches = list(re.finditer(pattern, content))
    
    if not matches:
        print(f"ERROR: Instance '{instance_name}' not found in {netlist_path}!")
        print(f"       Check instance name spelling and ensure synthesis has completed")
        return False
    
    if len(matches) > 1:
        print(f"WARNING: Found {len(matches)} matches for '{instance_name}'")
        print(f"         This should not happen. Check for duplicate instances.")
    
    # Get old cell type
    old_cell = matches[0].group(1)
    
    # Replace old cell type with the new one
    new_content = re.sub(pattern, rf"{new_cell_type} {instance_name} (", content)

    # Write the updated netlist back to the same file
    with open(netlist_path, 'w') as f:
        f.write(new_content)
    
    print(f"SUCCESS: Swapped {instance_name}")
    print(f"         From: {old_cell}")
    print(f"         To:   {new_cell_type}")
    print(f"         File: {netlist_path}")
    
    # Sync to Docker if needed
    sync_to_docker_if_needed(netlist_path)
    
    return True

def sync_to_docker_if_needed(netlist_path):
    """
    If we're in an ECO workflow, sync the modified netlist back to Docker
    """
    container_file = "./sources/.container_name"
    state_file = "./sources/.active_task_id"
    
    if os.path.exists(container_file) and os.path.exists(state_file):
        with open(container_file, 'r') as f:
            container_name = f.read().strip()
        with open(state_file, 'r') as f:
            task_id = f.read().strip()
        
        docker_path = f"/openlane/{task_id}/netlist.v"
        
        print(f"\nDETECTED ACTIVE ECO SESSION:")
        print(f"  Container: {container_name}")
        print(f"  Task: {task_id}")
        print(f"  Syncing modified netlist to Docker...")
        
        # Sync using docker cp
        import subprocess
        result = subprocess.run(
            ["docker", "cp", netlist_path, f"{container_name}:{docker_path}"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"  ✓ Netlist synced to container successfully")
            print(f"\nNext step: Run 'bash sources/run_sta_cmd.sh' to analyze timing")
        else:
            print(f"  ⚠ Warning: Could not sync to Docker (container may not be running)")
            print(f"  This is OK - netlist will be synced when you run run_sta_cmd.sh")
    else:
        print(f"\nNote: No active Docker session detected")
        print(f"      Modified netlist will be used in next synthesis run")

def list_weak_cells(netlist_path, drive_strength="_0"):
    """
    Helper function to find all cells with weak drive strength
    """
    if not os.path.exists(netlist_path):
        print(f"ERROR: Netlist not found at {netlist_path}")
        return
    
    with open(netlist_path, 'r') as f:
        content = f.read()
    
    # Find all cells with specified drive strength
    pattern = rf"(sky130_\w+{re.escape(drive_strength)})\s+(_\d+_)\s*\("
    matches = re.findall(pattern, content)
    
    if matches:
        print(f"\nFound {len(matches)} cells with drive strength '{drive_strength}':")
        print(f"{'Instance':<15} {'Cell Type'}")
        print("-" * 60)
        
        cell_counts = {}
        for cell_type, instance in matches[:50]:  # Show first 50
            print(f"{instance:<15} {cell_type}")
            cell_counts[cell_type] = cell_counts.get(cell_type, 0) + 1
        
        if len(matches) > 50:
            print(f"... and {len(matches) - 50} more")
        
        print(f"\nCell type distribution:")
        for cell_type, count in sorted(cell_counts.items(), key=lambda x: -x[1]):
            print(f"  {cell_type}: {count} instances")
    else:
        print(f"No cells found with drive strength '{drive_strength}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enhanced ECO tool with Docker sync support",
        epilog="""
Examples:
  # Swap a single cell
  python eco_fix.py --instance _5748_ --new_cell sky130_fd_sc_hd__o311ai_1
  
  # List all weak (_0) cells
  python eco_fix.py --list-weak
  
  # Swap using default netlist location
  python eco_fix.py --instance _0752_ --new_cell sky130_fd_sc_hd__o21ai_1
        """
    )
    
    # Main operation: swap cell
    parser.add_argument("--instance", help="Instance name to swap (e.g., _5748_)")
    parser.add_argument("--new_cell", help="New cell type (e.g., sky130_fd_sc_hd__o311ai_1)")
    
    # Helper operations
    parser.add_argument("--list-weak", action="store_true", 
                       help="List all cells with weak drive strength (_0)")
    parser.add_argument("--drive-strength", default="_0",
                       help="Drive strength to search for (default: _0)")
    
    # File location
    parser.add_argument("--file", default="./sources/netlist.v",
                       help="Netlist file path (default: ./sources/netlist.v)")
    
    args = parser.parse_args()
    
    if args.list_weak:
        # List weak cells
        list_weak_cells(args.file, args.drive_strength)
    elif args.instance and args.new_cell:
        # Perform ECO swap
        success = swap_cell(args.instance, args.new_cell, args.file)
        exit(0 if success else 1)
    else:
        parser.print_help()
        print("\nERROR: Either provide --instance and --new_cell, or use --list-weak")
        exit(1)
