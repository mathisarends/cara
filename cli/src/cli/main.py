import typer
from rich.console import Console

from cli import gateway
from cli.onboarding import onboard

app = typer.Typer(
    name="cara",
    help="Set up and operate Cara.",
    no_args_is_help=True,
)
gateway_app = typer.Typer(
    name="gateway",
    help="Start, stop, and inspect the Cara gateway.",
    no_args_is_help=True,
)
app.add_typer(gateway_app, name="gateway")
console = Console()
error_console = Console(stderr=True)


@app.command("onboard")
def onboard_command() -> None:
    """Create the configured persistent workspace."""
    try:
        results = onboard()
    except (OSError, RuntimeError) as error:
        error_console.print(f"[bold red]Onboarding failed:[/bold red] {error}")
        raise typer.Exit(1) from error
    for path, created in results:
        suffix = "/" if path.is_dir() else ""
        if created:
            console.print(f"[green]Created[/green] {path}{suffix}")
        else:
            console.print(f"[yellow]Already exists[/yellow] {path}{suffix}")
    console.print("\n[bold green]Cara is ready.[/bold green]")


@gateway_app.command("status")
def gateway_status() -> None:
    """Show the local gateway process status."""
    try:
        state = gateway.status()
    except (FileNotFoundError, RuntimeError) as error:
        _render_gateway_error(error)
    if state is gateway.GatewayState.RUNNING:
        console.print("[bold green]Gateway is running.[/bold green]")
    else:
        console.print("[bold yellow]Gateway is stopped.[/bold yellow]")


@gateway_app.command("start")
def gateway_start() -> None:
    """Start the gateway in the background."""
    try:
        returncode, started = gateway.start()
    except (FileNotFoundError, RuntimeError) as error:
        _render_gateway_error(error)
    if returncode:
        _gateway_command_failed(returncode)
    if started:
        console.print("[bold green]Gateway started.[/bold green]")
    else:
        console.print("[bold yellow]Gateway is already running.[/bold yellow]")


@gateway_app.command("stop")
def gateway_stop() -> None:
    """Stop the gateway."""
    try:
        returncode, stopped = gateway.stop()
    except (FileNotFoundError, RuntimeError) as error:
        _render_gateway_error(error)
    if returncode:
        _gateway_command_failed(returncode)
    if stopped:
        console.print("[bold green]Gateway stopped.[/bold green]")
    else:
        console.print("[bold yellow]Gateway is already stopped.[/bold yellow]")


def _render_gateway_error(error: Exception) -> None:
    error_console.print(f"[bold red]Error:[/bold red] {error}")
    raise typer.Exit(1) from error


def _gateway_command_failed(returncode: int) -> None:
    error_console.print(
        f"[bold red]Gateway command failed[/bold red] (exit {returncode})."
    )
    raise typer.Exit(returncode)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
