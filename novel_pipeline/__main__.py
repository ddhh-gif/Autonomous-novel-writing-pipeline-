import argparse
import sys
from novel_pipeline.orchestrator import Orchestrator


def main():
    parser = argparse.ArgumentParser(prog="novel_pipeline")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run the pipeline")
    run_p.add_argument("--config", default="config.yaml")
    run_p.add_argument("--premise", required=True, help="Story premise")
    run_p.add_argument("--characters", type=int, default=4)

    rb_p = sub.add_parser("rollback", help="Restore a checkpoint")
    rb_p.add_argument("--config", default="config.yaml")
    rb_p.add_argument("--checkpoint", required=True)

    st_p = sub.add_parser("status", help="Show pipeline status")
    st_p.add_argument("--config", default="config.yaml")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    orch = Orchestrator(config_path=args.config)
    if args.command == "run":
        orch.run(premise=args.premise, num_characters=args.characters)
    elif args.command == "rollback":
        orch.rollback(args.checkpoint)
    elif args.command == "status":
        import json
        print(json.dumps(orch.status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
