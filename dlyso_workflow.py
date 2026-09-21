"""Shared desktop workflow planning; no GUI dependencies."""

from pathlib import Path
import sys
import re
from dataclasses import dataclass
from dlyso_runtime import model_root

APP_DIR = Path(__file__).resolve().parent
MODALITIES = {
    "SEDplot": "SED plot",
    "SEDrplot": "Dust-aware SED plot",
    "AllWISE": "AllWISE image stamp",
    "DTDM": "ZTF light curve / DTDM image",
}
PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def build_commands(
    input_csv: Path,
    runroot: Path,
    modalities: list[str],
    workers: int,
    batch_size: int,
    classify: bool,
) -> list[tuple[str, list[str]]]:
    """Build the subprocess plan for public archive acquisition and inference."""
    py = sys.executable
    runner = str(APP_DIR / "dlyso.py")
    common = [str(input_csv), "--runroot", str(runroot)]
    plan: list[tuple[str, list[str]]] = [
        ("Validate input", [py, runner, *common, "--steps", "preflight", "--workers", str(workers)])
    ]

    if "SEDplot" in modalities or "SEDrplot" in modalities:
        plan.append(
            (
                "Download SED data",
                [
                    py,
                    str(APP_DIR / "scripts/sed_download_parallel.py"),
                    str(runroot / "coords_normalized.csv"),
                    "--outdir",
                    str(runroot / "SEDcsv"),
                    "--workers",
                    str(workers),
                ],
            )
        )
    if "SEDplot" in modalities:
        plan.append(
            (
                "Create SED plots",
                [
                    py,
                    str(APP_DIR / "scripts/make_sed_plots.py"),
                    "--csvdir",
                    str(runroot / "SEDcsv"),
                    "--plotdir",
                    str(runroot / "SEDplot"),
                ],
            )
        )
    if "SEDrplot" in modalities:
        plan.append(
            (
                "Create dust-aware SED plots",
                [
                    py,
                    str(APP_DIR / "scripts/make_sed_rplots.py"),
                    "--csvdir",
                    str(runroot / "SEDcsv"),
                    "--plotdir",
                    str(runroot / "SEDrplot"),
                ],
            )
        )
    if "AllWISE" in modalities:
        plan.append(
            (
                "Download AllWISE stamps",
                [
                    py,
                    str(APP_DIR / "scripts/getstamp.py"),
                    "--input-csv",
                    str(runroot / "coords_normalized.csv"),
                    "--outdir",
                    str(runroot / "AllWISE"),
                    "--workers",
                    str(workers),
                ],
            )
        )
    if "DTDM" in modalities:
        plan.extend(
            [
                (
                    "Download ZTF light curves",
                    [
                        py,
                        str(APP_DIR / "scripts/getztflc.py"),
                        "--input-csv",
                        str(runroot / "coords_normalized.csv"),
                        "--outdir",
                        str(runroot / "ZTFLC"),
                        "--workers",
                        str(workers),
                    ],
                ),
                (
                    "Create DTDM images",
                    [
                        py,
                        str(APP_DIR / "scripts/dtdm.py"),
                        "--lcdir",
                        str(runroot / "ZTFLC"),
                        "--outdir",
                        str(runroot / "DTDM"),
                        "--workers",
                        str(workers),
                    ],
                ),
            ]
        )

    if classify:
        selected = ",".join(modalities)
        plan.extend(
            [
                (
                    "Run custom classifiers",
                    [
                        py,
                        str(APP_DIR / "scripts/customclass.py"),
                        "--runroot",
                        str(runroot),
                        "--outdir",
                        str(runroot / "customClass"),
                        "--folders",
                        selected,
                        "--batch-size",
                        str(batch_size),
                        "--device",
                        "auto",
                    ],
                ),
                (
                    "Run ensemble classifiers",
                    [
                        py,
                        str(APP_DIR / "scripts/class.py"),
                        "--runroot",
                        str(runroot),
                        "--models-dir",
                        str(model_root() / "models"),
                        "--outdir",
                        str(runroot / "ClassProbs"),
                        "--types",
                        selected,
                        "--batch-size",
                        str(batch_size),
                        "--device",
                        "auto",
                        "--channels-last",
                    ],
                ),
                (
                    "Combine results",
                    [
                        py,
                        str(APP_DIR / "scripts/combineresult.py"),
                        str(runroot / "coords_normalized.csv"),
                        "--classprobs",
                        str(runroot / "ClassProbs"),
                        "--customclass",
                        str(runroot / "customClass"),
                        "--modalities",
                        selected,
                        "--outcsv",
                        str(runroot / "result.csv"),
                    ],
                ),
            ]
        )
    return plan


@dataclass
class Task:
    title: str
    command: list[str]
    needs: tuple[str, ...] = ()
    inference: bool = False
    modality: str | None = None


@dataclass
class Workflow:
    tasks: list[Task]
    combine: tuple[str, list[str]] | None = None

    def stages(self):
        return [(task.title, task.command) for task in self.tasks] + ([self.combine] if self.combine else [])

    def channel_stages(self):
        """Group each selected channel with all its prerequisites, including shared SED data."""
        tasks = {task.title: task for task in self.tasks}
        outputs = {
            "SEDplot": "Create SED plots",
            "SEDrplot": "Create dust-aware SED plots",
            "AllWISE": "Download AllWISE stamps",
            "DTDM": "Create DTDM images",
        }
        groups = {}
        for modality, representation in outputs.items():
            if representation not in tasks:
                continue
            final = next((task.title for task in self.tasks if task.modality == modality), representation)
            needed = set()

            def visit(title):
                if title in needed:
                    return
                needed.add(title)
                for dependency in tasks[title].needs:
                    visit(dependency)

            visit(final)
            groups[modality] = [task.title for task in self.tasks if task.title in needed]
        return groups


def build_workflow(input_csv, runroot, modalities, workers, batch_size, classify) -> Workflow:
    """Each representation unlocks its own inference; only SED acquisition is shared."""
    plan = build_commands(input_csv, runroot, modalities, workers, batch_size, classify)
    commands = dict(plan)
    tasks = [Task(*plan[0])]
    dependencies = {
        "Download SED data": ("Validate input",),
        "Create SED plots": ("Download SED data",),
        "Create dust-aware SED plots": ("Download SED data",),
        "Download AllWISE stamps": ("Validate input",),
        "Download ZTF light curves": ("Validate input",),
        "Create DTDM images": ("Download ZTF light curves",),
    }
    for title, needs in dependencies.items():
        if title in commands:
            tasks.append(Task(title, commands[title], needs))
    ready = {
        "SEDplot": "Create SED plots",
        "SEDrplot": "Create dust-aware SED plots",
        "AllWISE": "Download AllWISE stamps",
        "DTDM": "Create DTDM images",
    }
    if classify:
        for modality in modalities:
            predecessor = ready[modality]
            for family, flag in (("custom", "--folders"), ("ensemble", "--types")):
                command = commands[f"Run {family} classifiers"].copy()
                command[command.index(flag) + 1] = modality
                title = f"Classify {modality} · {family}"
                tasks.append(Task(title, command, (predecessor,), True, modality if family == "ensemble" else None))
                predecessor = title
    return Workflow(tasks, ("Combine results", commands["Combine results"]) if classify else None)
