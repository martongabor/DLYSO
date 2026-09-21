"""Cancellable workflow execution, independent of the desktop toolkit."""

from __future__ import annotations

import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from dlyso_runtime import atomic_json, require_models, terminate_tree
from dlyso_workflow import APP_DIR


class PipelineRun:
    def __init__(self, workflow, runroot: Path, env: dict, emit: Callable):
        self.workflow = workflow
        self.runroot = runroot
        self.env = env.copy()
        self.emit = emit
        self.cancelled = threading.Event()
        self.lock = threading.RLock()
        self.processes = []
        self.state = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(), "steps": {}}

    def _record(self, title: str, status: str):
        with self.lock:
            self.state["steps"][title] = status
            atomic_json(self.runroot / "run_state.json", self.state)
        self.emit("step", (title, status))

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            processes = list(self.processes)
        for process in processes:
            terminate_tree(process)

        # Kill lingering descendants even if their immediate parent has exited.
        def force():
            for process in processes:
                terminate_tree(process, force=True)

        timer = threading.Timer(3, force)
        timer.daemon = True
        timer.start()

    def _log(self, text: str):
        with self.lock:
            with (self.runroot / "pipeline.log").open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        self.emit("log", text)

    def command(self, step):
        title, command = step
        if self.cancelled.is_set():
            raise InterruptedError
        self._record(title, "running")
        self._log(f"\n{title}")
        env = self.env.copy()
        env["PYTHONUNBUFFERED"] = "1"
        with self.lock:
            if self.cancelled.is_set():
                raise InterruptedError
            process = subprocess.Popen(
                command,
                cwd=APP_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=(os.name == "posix"),
            )
            self.processes.append(process)
        try:
            for line in process.stdout:
                self._log(line.rstrip())
            code = process.wait()
            if self.cancelled.is_set():
                self._record(title, "cancelled")
                raise InterruptedError
            if code:
                self._record(title, "failed")
                raise RuntimeError(f"{title} failed. See the activity log; completed downloads can be reused.")
            self._record(title, "complete")
        finally:
            process.stdout.close()
            with self.lock:
                self.processes.remove(process)

    def run(self):
        completed_modalities = set()
        failures = []
        try:
            tasks = {task.title: task for task in self.workflow.tasks}
            for title in tasks:
                self._record(title, "waiting")
            pending = list(tasks.values())
            active = {}
            with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
                while pending or active:
                    if self.cancelled.is_set():
                        pending.clear()
                    inference_active = any(task.inference for task in active.values())
                    for task in list(pending):
                        states = [self.state["steps"][name] for name in task.needs]
                        if any(value in {"failed", "blocked", "cancelled"} for value in states):
                            self._record(task.title, "blocked")
                            pending.remove(task)
                        elif all(value == "complete" for value in states):
                            if task.inference and inference_active:
                                continue
                            active[pool.submit(self._execute_task, task)] = task
                            pending.remove(task)
                            inference_active |= task.inference
                    if not active:
                        if pending:
                            raise RuntimeError("Workflow has unresolved dependencies")
                        break
                    done, _ = wait(active, return_when=FIRST_COMPLETED)
                    refresh = False
                    for future in done:
                        task = active.pop(future)
                        try:
                            future.result()
                            if task.modality:
                                completed_modalities.add(task.modality)
                                refresh = True
                        except InterruptedError:
                            pass
                        except Exception as exc:
                            self._record(task.title, "failed")
                            failures.append(str(exc))
                            self._log(str(exc))
                    if refresh and self.workflow.combine and not self.cancelled.is_set():
                        self._combine(completed_modalities)
            if self.cancelled.is_set():
                raise InterruptedError
            if self.workflow.combine and (
                "Validate input" not in tasks or self.state["steps"]["Validate input"] == "complete"
            ):
                self._combine(completed_modalities)
            if failures:
                status = "partial" if completed_modalities else "failed"
                message = "Run finished with errors. Successful channels are retained. " + " ".join(failures)
            else:
                status, message = "complete", "Run complete. Review coverage before interpreting predictions."
        except InterruptedError:
            status, message = "cancelled", "Run stopped. Completed artifacts are available to resume."
        except Exception as exc:
            status, message = "failed", str(exc)
            self.cancel()
        with self.lock:
            self.state.update(status=status, finished_at=datetime.now(timezone.utc).isoformat())
            for title, value in self.state["steps"].items():
                if value in {"running", "waiting"}:
                    self.state["steps"][title] = "cancelled"
            atomic_json(self.runroot / "run_state.json", self.state)
        self._log(message)
        self.env = {}
        self.emit("finished", (status, message))

    def _execute_task(self, task):
        # Check models per channel: missing weights must not block other channels.
        if task.inference:
            flag = "--types" if "--types" in task.command else "--folders"
            if flag in task.command:
                require_models(task.command[task.command.index(flag) + 1].split(","))
        self.command((task.title, task.command))

    def _combine(self, completed_modalities):
        title, command = self.workflow.combine
        # Ignore old/unfinished channel CSVs, including those from previous attempts.
        self.command((title, [*command, "--available-modalities", ",".join(sorted(completed_modalities))]))
        self.emit("results", str(self.runroot / "result.csv"))
