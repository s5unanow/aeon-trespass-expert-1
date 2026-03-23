"""Main Typer CLI entrypoint for the ATR pipeline."""

import typer

from atr_pipeline.version import __version__


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"atr-pipeline {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="atr",
    help="Aeon Trespass Rules — document compiler pipeline",
    no_args_is_help=True,
    invoke_without_command=True,
)


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Print version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Aeon Trespass Rules — document compiler pipeline."""


@app.command()
def version_cmd() -> None:
    """Print the pipeline version."""
    typer.echo(f"atr-pipeline {__version__}")


@app.command()
def ingest(
    doc: str = typer.Option(..., "--doc", help="Document id from configs/documents/"),
) -> None:
    """Ingest a source PDF: fingerprint, rasterize, emit manifest."""
    from atr_pipeline.cli.commands.ingest import ingest as _ingest

    _ingest(doc=doc)


@app.command(name="run")
def run_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    from_stage: str = typer.Option("ingest", "--from", help="First stage"),
    to_stage: str = typer.Option("qa", "--to", help="Last stage"),
    edition: str = typer.Option("all", "--edition", help="'en' (source-only) or 'all'"),
    pages: str = typer.Option("", "--pages", help="Page filter: '15' or '15,18-20'"),
) -> None:
    """Run pipeline stages for a document."""
    from atr_pipeline.cli.commands.run import run as _run

    _run(doc=doc, from_stage=from_stage, to_stage=to_stage, edition=edition, pages=pages)


@app.command(name="release")
def release_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    output: str = typer.Option("", "--output", help="Output directory"),
    run_id: str = typer.Option("", "--run-id", help="Specific run to release"),
) -> None:
    """Build a local release bundle."""
    from atr_pipeline.cli.commands.release import release as _release

    _release(doc=doc, output=output, run_id=run_id)


@app.command(name="patch")
def patch_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    patch_file: str = typer.Option(..., "--patch-file", help="Path to PatchSetV1 JSON"),
    cascade: bool = typer.Option(False, "--cascade", help="Re-run render+qa after patching"),
) -> None:
    """Apply a patch set to a target artifact."""
    from pathlib import Path

    from atr_pipeline.cli.commands.patch import patch as _patch

    _patch(doc=doc, patch_file=Path(patch_file), cascade=cascade)


@app.command(name="qa")
def qa_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id"),
) -> None:
    """Run QA checks on existing artifacts."""
    from atr_pipeline.cli.commands.qa import qa as _qa

    _qa(doc=doc)


@app.command(name="verify-extraction")
def verify_extraction_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id to verify"),
    pages: str = typer.Option("", "--pages", help="Page filter: 'p0001' or 'p0001,p0002'"),
    output_json: str = typer.Option("", "--output-json", help="Path to write JSON report"),
) -> None:
    """Run invariant checks on extraction artifacts."""
    from atr_pipeline.cli.commands.verify_extraction_cmd import verify_extraction_command

    verify_extraction_command(doc=doc, pages=pages, output_json=output_json)


@app.command(name="verify-refs")
def verify_refs_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id to verify"),
    pages: str = typer.Option("", "--pages", help="Page filter: 'p0001' or 'p0001,p0002'"),
    output_json: str = typer.Option("", "--output-json", help="Path to write JSON report"),
) -> None:
    """Run cross-stage reference-integrity checks on pipeline artifacts."""
    from atr_pipeline.cli.commands.verify_refs_cmd import verify_refs_command

    verify_refs_command(doc=doc, pages=pages, output_json=output_json)


@app.command(name="eval")
def eval_cmd(
    golden_set: str = typer.Option(..., "--golden-set", help="Golden set name (e.g. 'core')"),
    doc: str = typer.Option("", "--doc", help="Document id (inferred from golden set if omitted)"),
    pages: str = typer.Option("", "--pages", help="Page filter: 'p0001' or 'p0001,p0002'"),
    output_json: str = typer.Option("", "--output-json", help="Path to write JSON report"),
    overlays: bool = typer.Option(False, "--overlays", help="Generate visual overlay PNGs"),
    fail_on_threshold: bool = typer.Option(
        False, "--fail-on-threshold", help="Fail if blocking thresholds are not met"
    ),
) -> None:
    """Run extraction evaluation against a golden set."""
    from atr_pipeline.cli.commands.eval_cmd import eval_command

    eval_command(
        golden_set=golden_set,
        doc=doc,
        pages=pages,
        output_json=output_json,
        overlays=overlays,
        fail_on_threshold=fail_on_threshold,
    )


@app.command(name="runs-list")
def runs_list_cmd(
    doc: str = typer.Option("", "--doc", help="Filter by document id"),
    limit: int = typer.Option(20, "--limit", help="Max runs to show"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List recent pipeline runs."""
    from atr_pipeline.cli.commands.runs import runs_list

    runs_list(doc=doc, limit=limit, output_json=output_json)


@app.command(name="runs-show")
def runs_show_cmd(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show detailed info for a specific run."""
    from atr_pipeline.cli.commands.runs import runs_show

    runs_show(run_id=run_id, output_json=output_json)


@app.command(name="audit")
def audit_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id to audit"),
    pages: str = typer.Option("", "--pages", help="Page filter: 'p0001' or 'p0001,p0002'"),
    output_json: str = typer.Option("", "--output-json", help="Path to write JSON report"),
    baseline: str = typer.Option(
        "", "--baseline", help="Path to a previous audit report for delta comparison"
    ),
) -> None:
    """Run full-document extraction audit (non-blocking diagnostic)."""
    from atr_pipeline.cli.commands.audit_cmd import audit_command

    audit_command(doc=doc, pages=pages, output_json=output_json, baseline=baseline)


if __name__ == "__main__":
    app()
