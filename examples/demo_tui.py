#!/usr/bin/env python3
"""Demo script to show the TUI and interrupt handling."""

import sys
import time
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_coordinator.infrastructure.tui import TUIDisplay, InterruptMenu

def demo_tui():
    """Demonstrate the TUI interface."""
    print("\n" + "="*70)
    print("DEMO: TUI Interface with Interrupt Handling")
    print("="*70)
    print("\nPress Ctrl+C during agent execution to see the interrupt menu")
    print("="*70 + "\n")
    
    display = TUIDisplay()
    
    # Simulate agent turn
    display.start_agent_turn(
        agent="architect",
        backend="copilot",
        task_id="task-001",
        status="continue"
    )
    
    try:
        # Simulate thinking for 5 seconds
        print("\n(Press Ctrl+C now to see the menu...)\n")
        time.sleep(5)
        
        # If not interrupted, show output
        display.update_output("Analysis complete\n")
        display.update_output("Creating implementation plan\n")
        display.update_output("Breaking down into tasks\n")
        
        display.finish_agent_turn(
            success=True,
            new_status="review_required",
            next_agent="developer"
        )
        
    except KeyboardInterrupt:
        print("\n")
        display.thinking.stop()
        
        # Show interrupt menu
        menu = InterruptMenu()
        choice = menu.show()
        
        print(f"You selected: {choice}")
        
        if choice == 'i':
            print("\nWould show handoff.md content here...")
        elif choice == 'm':
            message = menu.get_message()
            print(f"\nMessage entered: {message}")
        elif choice == 'q':
            print("\nExiting...")
        
    print("\n" + "="*70)
    print("DEMO COMPLETE")
    print("="*70)
    print("\nKey Features:")
    print("  - Clean TUI interface (no emoticons)")
    print("  - Animated thinking indicator [⠋]")
    print("  - Ctrl+C interrupt handling")
    print("  - Interactive menu for human intervention")
    print("  - Options: continue, retry, undo, inspect, message, quit")
    print()

if __name__ == "__main__":
    demo_tui()
