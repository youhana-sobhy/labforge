"""`labforge` command line: run the web UI, or drive labs from a terminal or a CI pipeline."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import typer

from . import __version__, catalog

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="LabForge: on-demand virtual network labs.")


def _mgr():
    from .manager import LabManager
    return LabManager()


def _fmt_left(seconds: int) -> str:
    h, rem = divmod(max(0, seconds), 3600)
    return f"{h}h{rem // 60:02d}m" if h else f"{rem // 60}m{rem % 60:02d}s"


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8080, log_level: str = "info"):
    """Start the web UI and API (with the auto-expiry reaper)."""
    import uvicorn

    from .api import create_app
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    typer.secho(f"LabForge {__version__} on http://{host}:{port}", fg="cyan", bold=True)
    uvicorn.run(create_app(), host=host, port=port, log_level=log_level)


@app.command("catalog")
def list_catalog():
    """List lab templates."""
    for topo, source in catalog.load_all().values():
        typer.secho(f"{topo.id:<20}", fg="cyan", nl=False)
        typer.echo(f"{topo.name:<32} {len(topo.nodes):>2} devices  {len(topo.checks):>2} tests  [{source}]")


@app.command()
def validate(path: Path):
    """Validate a topology YAML file before adding it to the catalog."""
    try:
        topo = catalog.parse(path.read_text())
    except Exception as e:  # noqa: BLE001
        typer.secho(f"invalid: {e}", fg="red")
        raise typer.Exit(1) from e
    typer.secho(f"ok: {topo.name} ({len(topo.nodes)} devices, {len(topo.links)} links)", fg="green")


@app.command()
def up(template: str, name: str = "", owner: str = typer.Option("cli", envvar="USER"), ttl: int | None = None):
    """Launch a lab and wait until it is ready."""
    m = _mgr()
    lab = m.create(template, name=name, owner=owner, ttl_minutes=ttl, wait=True)
    lab = m.get(lab["id"])
    if lab["status"] != "running":
        typer.secho(f"failed: {lab.get('error')}", fg="red")
        raise typer.Exit(1)
    typer.secho(f"{lab['id']} ready in {lab['deploy_seconds']}s, expires in {_fmt_left(lab['remaining_seconds'])}",
                fg="green")


@app.command("ls")
def list_labs(all_: bool = typer.Option(False, "--all", "-a", help="include finished labs")):
    """List labs."""
    labs = _mgr().list(active_only=not all_)
    if not labs:
        typer.echo("no labs")
    for lab in labs:
        color = {"running": "green", "deploying": "yellow", "failed": "red"}.get(lab["status"], "white")
        typer.secho(f"{lab['id']}  ", fg="cyan", nl=False)
        typer.secho(f"{lab['status']:<10}", fg=color, nl=False)
        typer.echo(f" {lab['name']:<30} {lab['owner']:<12} left {_fmt_left(lab['remaining_seconds'])}")


@app.command()
def down(lab_id: str):
    """Destroy a lab."""
    _mgr().destroy(lab_id, by="cli", wait=True)
    typer.secho(f"{lab_id} destroyed", fg="green")


@app.command()
def extend(lab_id: str, minutes: int = 60):
    """Give a lab more time before it auto-destroys."""
    lab = _mgr().extend(lab_id, minutes)
    typer.echo(f"{lab_id} now expires in {_fmt_left(lab['remaining_seconds'])}")


@app.command("exec")
def exec_(lab_id: str, node: str, command: str):
    """Run a command on a device (router commands go to its CLI; prefix with ! for a shell)."""
    r = _mgr().exec(lab_id, node, command)
    typer.echo(r["output"], nl=False)
    raise typer.Exit(r["exit_code"])


def _print_results(run: dict) -> None:
    for r in run["results"]:
        typer.secho("  PASS " if r["ok"] else "  FAIL ", fg="green" if r["ok"] else "red", nl=False)
        typer.echo(f"{r['name']}  ({r['detail']}, {r['seconds']}s)")
    color = "green" if run["passed"] == run["total"] else "red"
    typer.secho(f"{run['passed']}/{run['total']} tests passed", fg=color, bold=True)


@app.command()
def check(lab_id: str):
    """Run a running lab's built-in tests."""
    run = _mgr().run_checks(lab_id)
    _print_results(run)
    raise typer.Exit(0 if run["passed"] == run["total"] else 1)


@app.command()
def test(templates: list[str] = typer.Argument(None, help="template ids (default: all)"),
         keep: bool = typer.Option(False, help="keep labs running afterwards")):
    """CI mode: launch each template, run its tests, tear it down. Exit code 1 if anything fails."""
    m = _mgr()
    ids = templates or list(catalog.load_all())
    failed = []
    for tid in ids:
        typer.secho(f"\n▶ {tid}", fg="cyan", bold=True)
        t0 = time.time()
        lab = m.create(tid, name=f"ci-{tid}", owner="ci", ttl_minutes=30, wait=True)
        lab = m.get(lab["id"])
        try:
            if lab["status"] != "running":
                typer.secho(f"  deploy failed: {lab.get('error')}", fg="red")
                failed.append(tid)
                continue
            typer.echo(f"  deployed in {lab['deploy_seconds']}s")
            run = m.run_checks(lab["id"])
            _print_results(run)
            if run["passed"] != run["total"]:
                failed.append(tid)
        finally:
            if not keep:
                m.destroy(lab["id"], by="ci", wait=True)
        typer.echo(f"  total {time.time() - t0:.1f}s")
    if failed:
        typer.secho(f"\nFAILED: {', '.join(failed)}", fg="red", bold=True)
        raise typer.Exit(1)
    typer.secho(f"\nAll {len(ids)} labs passed", fg="green", bold=True)


@app.command()
def stats():
    """Usage KPIs for the last 30 days."""
    for k, v in _mgr().store.stats().items():
        if k not in ("daily", "by_template"):
            typer.echo(f"{k:<22} {v}")


@app.command()
def version():
    typer.echo(__version__)


if __name__ == "__main__":
    sys.exit(app())
