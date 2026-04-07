"""Entry point for helper commands."""
import sys

COMMANDS = {
    "task":   "Create a new task interactively",
    "spec":   "Create a new specification interactively",
    "import": "Import an existing specification or implementation plan",
}

if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
    print("Usage: python -m agent_coordinator.helpers <command> [options]")
    print()
    print("Commands:")
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd:<10} {desc}")
    print()
    print("Run 'python -m agent_coordinator.helpers <command> --help' for command options.")
    sys.exit(0 if sys.argv[1:] else 1)

command = sys.argv[1]

if command == "task":
    sys.argv = ["create_task"] + sys.argv[2:]
    from agent_coordinator.helpers.create_task import main_task
    main_task()

elif command == "spec":
    sys.argv = ["create_spec"] + sys.argv[2:]
    from agent_coordinator.helpers.create_task import main_spec
    main_spec()

elif command == "import":
    sys.argv = ["import"] + sys.argv[2:]
    from agent_coordinator.helpers.import_plan import main_import
    main_import()

else:
    print(f"Unknown command: {command!r}")
    print(f"Available commands: {', '.join(COMMANDS)}")
    sys.exit(1)
