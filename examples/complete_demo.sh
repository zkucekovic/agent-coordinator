#!/bin/bash
# Complete demonstration of all new features

set -e

DEMO_DIR="/tmp/coordinator-demo-$(date +%s)"

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "    COORDINATOR FEATURE DEMONSTRATION"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "This script demonstrates all 5 major features that were added."
echo ""
echo "Creating demo workspace: $DEMO_DIR"
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"

# ========================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "DEMO 1: TUI with Animated Thinking Indicator"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Watch for the animated spinner [⠋] [⠙] [⠹] ..."
echo ""
sleep 2

cat > demo_1_tui.py << 'EOF'
import sys
import time
sys.path.insert(0, '/Users/zkucekovic/Projects/Privatno/agent-coordinator')

from agent_coordinator.infrastructure.tui import TUIDisplay

print("\n[Starting agent turn...]")
display = TUIDisplay()

display.start_agent_turn(
    agent="architect",
    backend="copilot",
    task_id="demo-task",
    status="continue"
)

# Watch the animated spinner for 3 seconds
time.sleep(3)

# Simulate output
display.update_output("Analyzing requirements...\n")
display.update_output("Creating plan...\n")
time.sleep(1)

display.finish_agent_turn(
    success=True,
    new_status="done",
    next_agent="developer"
)

print("\n✓ Notice: No emoticons! Clean [⠹] spinner! Professional boxes!")
EOF

python3 demo_1_tui.py

echo ""
read -p "Press Enter to continue to Demo 2..."

# ========================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "DEMO 2: Ctrl+C Interrupt Menu"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "We'll simulate what happens when you press Ctrl+C during execution."
echo ""
sleep 2

cat > demo_2_interrupt.py << 'EOF'
import sys
sys.path.insert(0, '/Users/zkucekovic/Projects/Privatno/agent-coordinator')

from agent_coordinator.infrastructure.tui import InterruptMenu

menu = InterruptMenu()

print("\nImagine the coordinator is running and you pressed Ctrl+C...")
print("\nThe interrupt menu appears:\n")

# Show what the menu looks like
import shutil
width = shutil.get_terminal_size().columns
print("═" * width)
print("INTERRUPTED (Ctrl+C pressed)")
print("─" * width)
print("")
print("  c - Continue execution")
print("  r - Retry current turn")
print("  e - Edit handoff.md in editor")
print("  m - Add message to handoff")
print("  i - Inspect handoff.md")
print("  q - Quit")
print("")
print("─" * width)
print("\n✓ This menu appears when you press Ctrl+C!")
print("✓ You can edit, inspect, continue, or quit")
print("✓ The workflow resumes gracefully")
EOF

python3 demo_2_interrupt.py

echo ""
read -p "Press Enter to continue to Demo 3..."

# ========================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "DEMO 3: Editor Integration"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Creating a task now opens YOUR editor (vim/vscode/emacs/etc)"
echo "instead of line-by-line prompts."
echo ""
echo "Your editor is: ${EDITOR:-vi}"
echo ""
echo "Let's show what the template looks like:"
sleep 2

cat << 'TEMPLATE'

[Your editor would open with this template:]

────────────────────────────────────────────────────────────────────
# Edit the task below
# First line format: task-id: Task Title
# Lines starting with # will be ignored
# Save and close when done

task-001: Implement user authentication

Build a JWT-based authentication system.
Users should be able to log in and log out.

## Acceptance Criteria

- POST /auth/login endpoint works
- POST /auth/logout endpoint works
- JWT tokens generated correctly
- Tokens expire after 1 hour
- Unit tests pass

## Dependencies

- task-000
────────────────────────────────────────────────────────────────────

✓ Natural multi-line editing in YOUR editor!
✓ Syntax highlighting!
✓ Copy/paste easily!
✓ No more awkward line-by-line prompts!

TEMPLATE

echo ""
echo "To actually try it:"
echo "  python -m agent_coordinator.helpers task --workspace $DEMO_DIR"
echo ""

read -p "Press Enter to continue to Demo 4..."

# ========================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "DEMO 4: Human Agent Support"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "When an agent sets NEXT: human, the coordinator prompts you."
echo ""
sleep 2

# Create a handoff that needs human input
cat > handoff.md << 'EOF'
---HANDOFF---
ROLE: architect
STATUS: needs_human
NEXT: human
TASK_ID: demo-task
SUMMARY: Need human approval before proceeding with implementation
ACCEPTANCE:
- Review the proposed approach
- Approve or suggest modifications
---END---
EOF

echo "Created handoff.md with NEXT: human"
echo ""
echo "If you run: agent-coord --workspace $DEMO_DIR"
echo ""
echo "You would see:"
echo ""

cat << 'PROMPT'
────────────────────────────────────────────────────────────────────
═══════════════════════════════════════════════════════════════════
HUMAN INPUT REQUIRED
───────────────────────────────────────────────────────────────────
Task: demo-task
Status: needs_human
───────────────────────────────────────────────────────────────────

The workflow needs your input to continue.

Options:
  e - Edit handoff.md in your editor
  m - Add a message/guidance
  v - View handoff.md
  c - Continue (handoff already updated)
  q - Quit

───────────────────────────────────────────────────────────────────
Choice [e/m/v/c/q]:

✓ Built-in human-in-the-loop support!
✓ Edit handoff directly in your editor!
✓ Workflow continues after your input!
────────────────────────────────────────────────────────────────────
PROMPT

echo ""
read -p "Press Enter to continue to Demo 5..."

# ========================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "DEMO 5: Auto-Create Handoff"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Starting a new project without handoff.md? No problem!"
echo ""
sleep 2

# Remove handoff to demonstrate auto-creation
rm -f handoff.md

echo "Removed handoff.md from $DEMO_DIR"
echo ""
echo "Now simulating: agent-coord --workspace $DEMO_DIR"
echo ""

cat > demo_5_autocreate.py << 'EOF'
import sys
from pathlib import Path

sys.path.insert(0, '/Users/zkucekovic/Projects/Privatno/agent-coordinator')
from agent_coordinator.cli import _create_initial_handoff

workspace = Path('/tmp/coordinator-demo-new')
workspace.mkdir(parents=True, exist_ok=True)
handoff = workspace / 'handoff.md'

if handoff.exists():
    handoff.unlink()

print(f"\nHandoff file not found: {handoff}")
print("Creating initial handoff.md...")
print()

_create_initial_handoff(workspace)

print("\nHandoff created! Here's what it contains:")
print("─" * 70)
content = handoff.read_text()
for line in content.split('\n')[:15]:
    print(line)
print("...")
print("─" * 70)
print("\n✓ Coordinator auto-creates handoff.md!")
print("✓ Ready to run immediately!")
print("✓ No manual setup needed!")
EOF

python3 demo_5_autocreate.py

# ========================================================================
echo ""
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "    SUMMARY OF ALL FEATURES"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "✓ DEMO 1: Animated thinking indicator [⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]"
echo "           No more static 'Thinking...' text"
echo "           Clean professional appearance"
echo ""
echo "✓ DEMO 2: Ctrl+C interrupt menu"
echo "           Press Ctrl+C anytime to control execution"
echo "           Edit, inspect, retry, or continue"
echo ""
echo "✓ DEMO 3: Editor integration"
echo "           All text input uses YOUR editor"
echo "           No more line-by-line prompts"
echo ""
echo "✓ DEMO 4: Human agent support"
echo "           NEXT: human prompts for input"
echo "           Natural editor-based interaction"
echo ""
echo "✓ DEMO 5: Auto-create handoff"
echo "           Missing handoff.md? We create it"
echo "           Zero manual setup"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "All demos completed!"
echo ""
echo "To try these features yourself:"
echo ""
echo "  1. Run the coordinator:"
echo "     cd $DEMO_DIR"
echo "     agent-coord --workspace ."
echo "     (Press Ctrl+C to see the interrupt menu)"
echo ""
echo "  2. Create a task with editor:"
echo "     python -m agent_coordinator.helpers task --workspace $DEMO_DIR"
echo ""
echo "  3. See the TUI demo:"
echo "     python3 /Users/zkucekovic/Projects/Privatno/agent-coordinator/examples/demo_tui.py"
echo ""
echo "Demo workspace: $DEMO_DIR"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo ""
