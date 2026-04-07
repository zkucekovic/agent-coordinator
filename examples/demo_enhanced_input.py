#!/usr/bin/env python3
"""Demonstration of enhanced input features."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_coordinator.infrastructure.enhanced_input import (
    enhanced_input,
    enhanced_choice,
    enhanced_multiline,
    Colors
)

print("=" * 70)
print(Colors.colorize("ENHANCED INPUT DEMONSTRATION", Colors.CYAN + Colors.BOLD))
print("=" * 70)
print()

print(Colors.info("This demonstrates the enhanced input with readline support."))
print()
print("Features enabled:")
print("  • " + Colors.success("Ctrl+A") + " - Move to beginning of line")
print("  • " + Colors.success("Ctrl+E") + " - Move to end of line")
print("  • " + Colors.success("Ctrl+K") + " - Kill (cut) to end of line")
print("  • " + Colors.success("Ctrl+W") + " - Delete word backward")
print("  • " + Colors.success("Ctrl+U") + " - Delete to beginning of line")
print("  • " + Colors.success("Arrow keys") + " - Navigate through line")
print("  • " + Colors.success("Up/Down") + " - Command history")
print("  • " + Colors.success("Tab") + " - Completion for choices")
print()

print("─" * 70)
print(Colors.warning("Test 1: Enhanced Input"))
print("─" * 70)
print()

name = enhanced_input(Colors.prompt("Enter your name: "))
print(f"You entered: {Colors.success(name)}")
print()

print("─" * 70)
print(Colors.warning("Test 2: Choice with Tab Completion"))
print("─" * 70)
print()
print(Colors.info("Try pressing Tab to see completion options!"))
print()

choice = enhanced_choice(
    Colors.prompt("Choose action: "),
    choices=['continue', 'quit', 'retry', 'edit'],
    default='continue'
)
print(f"You chose: {Colors.success(choice)}")
print()

print("─" * 70)
print(Colors.warning("Test 3: Multi-line Input"))
print("─" * 70)
print()

message = enhanced_multiline(
    Colors.info("Enter a multi-line message (empty line to finish):"),
    Colors.prompt("> ")
)

if message:
    print()
    print(Colors.success("Message received:"))
    print("─" * 70)
    for line in message.split('\n'):
        print(Colors.colorize(line, Colors.GREEN))
    print("─" * 70)
else:
    print(Colors.warning("No message entered"))

print()
print("=" * 70)
print(Colors.success("✓ Enhanced input features demonstrated!"))
print("=" * 70)
print()
print("All user inputs in the coordinator now support these features:")
print("  • Interrupt menu (Ctrl+C)")
print("  • Human input prompt")
print("  • Task/spec creation (fallback mode)")
print("  • Message inputs")
print()
print("Command history is saved to: ~/.agent_coordinator_history")
print()
