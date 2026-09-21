#!/usr/bin/env python3
"""Run the ordinary-SED desktop workflow on a small catalogue, optionally with cached data."""

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlyso_engine import PipelineRun
from dlyso_workflow import build_workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New, empty project directory")
    parser.add_argument("--cached-seds", type=Path, help="Optional predownloaded SED CSV directory")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Use an empty output directory.")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.cached_seds:
        shutil.copytree(args.cached_seds, args.output / "SEDcsv", dirs_exist_ok=True)
    workflow = build_workflow(args.input.resolve(), args.output.resolve(), ["SEDplot"], 1, 1, True)
    for task in workflow.tasks:
        command = task.command
        if "--device" in command:
            command[command.index("--device") + 1] = "cpu"
        if task.inference and "--types" in command:
            command.extend(["--num-workers", "0"])

    def emit(kind, payload):
        if kind in {"step", "finished"}:
            print(kind, payload, flush=True)

    run = PipelineRun(workflow, args.output, os.environ, emit)
    run.run()
    if run.state["status"] != "complete":
        print(f"See {args.output / 'pipeline.log'}")
        raise SystemExit(1)
    print(f"Complete result: {args.output / 'result.csv'}")


if __name__ == "__main__":
    main()
