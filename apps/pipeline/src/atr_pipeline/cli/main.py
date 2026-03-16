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
    pages: str = typer.Option("", "--pages", help="Page range, e.g. '1-5' or '3,7,12'"),
) -> None:
    """Run pipeline stages for a document."""
    from atr_pipeline.cli.commands.run import run as _run

    _run(doc=doc, from_stage=from_stage, to_stage=to_stage, pages=pages)


@app.command(name="release")
def release_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    output: str = typer.Option("", "--output", help="Output directory"),
) -> None:
    """Build a local release bundle."""
    from atr_pipeline.cli.commands.release import release as _release

    _release(doc=doc, output=output)


@app.command(name="qa")
def qa_cmd(
    doc: str = typer.Option(..., "--doc", help="Document id"),
) -> None:
    """Run QA checks on existing artifacts."""
    from atr_pipeline.cli.commands.qa import qa as _qa

    _qa(doc=doc)


if __name__ == "__main__":
    app()
