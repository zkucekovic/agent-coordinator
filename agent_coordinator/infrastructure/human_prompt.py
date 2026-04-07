"""Human interaction prompts for the coordinator."""

from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import datetime, timezone


def prompt_human_input(handoff_path: Path, task_id: str, current_status: str) -> str:
    """
    Prompt human for input when the workflow requires human action.
    
    Returns:
        Action taken ('continue', 'quit', etc.)
    """
    print("\n" + "═" * 70)
    print("HUMAN INPUT REQUIRED")
    print("─" * 70)
    print(f"Task: {task_id}")
    print(f"Status: {current_status}")
    print("─" * 70)
    print("\nThe workflow needs your input to continue.")
    print("\nOptions:")
    print("  r - Respond with guidance (creates new handoff)")
    print("  e - Edit handoff.md manually in your editor")
    print("  v - View current handoff.md")
    print("  q - Quit")
    print("\n" + "─" * 70)
    
    from agent_coordinator.infrastructure.enhanced_input import enhanced_choice, enhanced_input, enhanced_multiline, Colors
    
    while True:
        prompt = Colors.prompt("Choice [r/e/v/q]: ")
        choice = enhanced_choice(prompt, choices=['r', 'e', 'v', 'q'])
        
        if choice == 'r':
            # Get human response and create new handoff block
            print("\n" + Colors.info("Provide your response/guidance:"))
            print(Colors.info("(This will be added to the handoff for the next agent)"))
            print()
            
            response = enhanced_multiline(
                "",
                Colors.prompt("> ")
            )
            
            if not response.strip():
                print(Colors.warning("No response entered. Try again."))
                continue
            
            # Ask which agent should receive this
            print()
            next_agent = enhanced_input(
                Colors.prompt("Route to agent [architect/developer/qa_engineer/helper]: "),
                default="architect"
            ).strip().lower()
            
            if not next_agent:
                next_agent = "architect"
            
            # Decide if we should format with helper agent
            use_helper = False
            if next_agent != "helper":
                format_choice = enhanced_input(
                    Colors.prompt("Format with helper agent first? [y/N]: "),
                    default="n"
                ).strip().lower()
                use_helper = format_choice in ['y', 'yes']
            
            if use_helper:
                # Route to helper first to format the human input
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                handoff_block = f"""
---HANDOFF---
ROLE: system
STATUS: continue
NEXT: helper
TASK_ID: {task_id}
TITLE: Format human input
SUMMARY: Human provided informal guidance that needs to be formatted into a proper handoff block for the {next_agent} agent.

Raw human input ({timestamp}):
{response}

Target agent: {next_agent}

ACCEPTANCE:
- Human input formatted into proper handoff structure
- Key requirements extracted and organized
- Handoff routed to {next_agent}

CONSTRAINTS:
- Preserve all information from human input
- Follow handoff format standards
---END---
"""
                print()
                print(Colors.info(f"✓ Routing to helper agent for formatting"))
                print(Colors.info(f"  Helper will format and route to: {next_agent}"))
            else:
                # Create new handoff block with human response directly
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                handoff_block = f"""
---HANDOFF---
ROLE: human
STATUS: continue
NEXT: {next_agent}
TASK_ID: {task_id}
TITLE: Human response provided
SUMMARY: Human provided guidance and direction for the workflow to continue.

Human response ({timestamp}):
{response}

ACCEPTANCE:
- Agent acknowledges human guidance
- Agent proceeds with implementation

CONSTRAINTS:
- Follow human guidance provided above

FILES_TO_TOUCH:
- handoff.md

CHANGED_FILES:
- handoff.md

VALIDATION:
- n/a

BLOCKERS:
- None
---END---
"""
            
            with open(handoff_path, 'a') as f:
                f.write(handoff_block)
            
            print()
            print(Colors.success(f"✓ Response added to handoff.md"))
            if use_helper:
                print(Colors.success(f"✓ Routing to: helper → {next_agent}"))
            else:
                print(Colors.success(f"✓ Routing to: {next_agent}"))
            print("═" * 70)
            return 'continue'
                
        elif choice == 'e':
            from agent_coordinator.infrastructure.editor import get_editor
            editor = get_editor()
            print(f"\nOpening handoff.md in {editor}...")
            try:
                subprocess.run([editor, str(handoff_path)], check=True)
                print(Colors.success("Handoff updated"))
                print("═" * 70)
                return 'continue'
            except Exception as e:
                print(Colors.error(f"Editor error: {e}"))
                continue
                
        elif choice == 'v':
            if handoff_path.exists():
                print("\nCurrent handoff.md:")
                print("─" * 70)
                content = handoff_path.read_text()
                # Show last 50 lines
                lines = content.split('\n')
                for line in lines[-50:]:
                    print(line)
                print("─" * 70)
            enhanced_input(Colors.prompt("\nPress Enter to continue..."))
            continue
            
        elif choice == 'q':
            print("═" * 70)
            return 'quit'
            
        else:
            print("Invalid choice. Try again.")

