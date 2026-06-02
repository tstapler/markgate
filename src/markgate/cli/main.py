"""markgate CLI — push, pull, auth, status, conflicts."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from markgate.config import load_config
from markgate.backends import BACKENDS
from markgate.core import (
    SyncState,
    MappingState,
    sha256_of_file,
    sha256_of_content,
    three_way_merge,
)

app = typer.Typer(
    name="markgate",
    help="Push and pull markdown to Google Docs and Confluence.",
    add_completion=False,
    rich_markup_mode="rich",
)
auth_app = typer.Typer(help="Manage authentication for backends.")
conflicts_app = typer.Typer(help="Manage merge conflicts.")
app.add_typer(auth_app, name="auth")
app.add_typer(conflicts_app, name="conflicts")

console = Console()
err_console = Console(stderr=True, style="bold red")


# ─────────────────────────────────────────────────────────────────────────────
# State helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_state_path(config_path: Optional[str]) -> str:
    if config_path is not None:
        state_dir = os.path.dirname(os.path.abspath(config_path))
    else:
        state_dir = os.getcwd()
    return os.path.join(state_dir, ".markgate-state.json")


def _get_state_dir(config_path: Optional[str]) -> str:
    if config_path is not None:
        return os.path.dirname(os.path.abspath(config_path))
    return os.getcwd()


def _get_base_content(state_dir: str, base_hash: str) -> str:
    """Read the base content from the content-addressed store. Returns '' if missing."""
    base_path = os.path.join(state_dir, ".markgate-base", f"{base_hash}.base")
    if not os.path.exists(base_path):
        return ""
    with open(base_path, encoding="utf-8") as f:
        return f.read()


def _save_base_content(state_dir: str, content: str) -> str:
    """
    Write content to the content-addressed base store.

    Returns the sha256 hex digest (used as base_hash).
    Files are write-once (content-addressed) — no race condition risk.
    """
    sha256 = sha256_of_content(content)
    base_dir = os.path.join(state_dir, ".markgate-base")
    os.makedirs(base_dir, exist_ok=True)
    base_path = os.path.join(base_dir, f"{sha256}.base")
    if not os.path.exists(base_path):
        with open(base_path, "w", encoding="utf-8") as f:
            f.write(content)
    return sha256


# ─────────────────────────────────────────────────────────────────────────────
# Backend lookup
# ─────────────────────────────────────────────────────────────────────────────

def _get_backend(backend_name: str, config):
    cls = BACKENDS.get(backend_name)
    if not cls:
        err_console.print(f"Unknown backend '{backend_name}'. Available: {list(BACKENDS.keys())}")
        raise typer.Exit(1)
    return cls(config.model_dump())


# ─────────────────────────────────────────────────────────────────────────────
# push command
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def push(
    files: Optional[list[str]] = typer.Argument(None, help="Local markdown files to push (default: all mappings)"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to markgate.yaml"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
):
    """Push local markdown to remote docs."""
    config = load_config(config_path)
    mappings = config.mappings

    if files:
        mappings = [m for m in mappings if m.local in files]
        if not mappings:
            err_console.print(f"No mappings found for: {files}")
            raise typer.Exit(1)

    if not mappings:
        err_console.print("No mappings configured. Add entries to markgate.yaml.")
        raise typer.Exit(1)

    state_path = _get_state_path(config_path)
    state_dir = _get_state_dir(config_path)
    try:
        state = SyncState.load(state_path)
    except Exception:
        state = SyncState()

    results = []
    for mapping in mappings:
        if mapping.direction == "pull":
            console.print(f"[dim]Skipping {mapping.local} (pull-only)[/dim]")
            continue
        if dry_run:
            console.print(f"[yellow]dry-run[/yellow]  {mapping.local} → [{mapping.backend}] {mapping.remote_id}")
            continue
        backend = _get_backend(mapping.backend, config)
        result = backend.push(mapping.local, mapping.remote_id)
        results.append((mapping.local, result))
        icon = "✓" if result.status == "ok" else "✗"
        style = "green" if result.status == "ok" else "red"
        console.print(f"[{style}]{icon}[/{style}]  {mapping.local} → {result.url or mapping.remote_id}")
        if result.message:
            console.print(f"   [dim]{result.message}[/dim]")

        # Record state after successful push
        if result.status == "ok" and os.path.exists(mapping.local):
            try:
                remote_version = backend.get_remote_version(mapping.remote_id)
                local_content = open(mapping.local, encoding="utf-8").read()
                local_hash = sha256_of_content(local_content)
                base_hash = _save_base_content(state_dir, local_content)
                state.update(mapping.local, MappingState(
                    doc_id=mapping.remote_id,
                    backend=mapping.backend,
                    last_synced_at=datetime.now(timezone.utc).isoformat(),
                    base_hash=base_hash,
                    remote_version=remote_version,
                    local_hash=local_hash,
                ))
                state.save(state_path)
            except Exception as exc:
                console.print(f"   [yellow]Warning: could not save sync state: {exc}[/yellow]")

    errors = [r for _, r in results if r.status == "error"]
    if errors:
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# pull command
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def pull(
    files: Optional[list[str]] = typer.Argument(None, help="Local paths to pull into (default: all mappings)"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Pull remote docs into local markdown files."""
    config = load_config(config_path)
    mappings = config.mappings

    if files:
        mappings = [m for m in mappings if m.local in files]

    if not mappings:
        err_console.print("No mappings configured.")
        raise typer.Exit(1)

    state_path = _get_state_path(config_path)
    state_dir = _get_state_dir(config_path)
    try:
        state = SyncState.load(state_path)
    except Exception:
        state = SyncState()

    for mapping in mappings:
        if mapping.direction == "push":
            console.print(f"[dim]Skipping {mapping.local} (push-only)[/dim]")
            continue
        if dry_run:
            console.print(f"[yellow]dry-run[/yellow]  [{mapping.backend}] {mapping.remote_id} → {mapping.local}")
            continue

        backend = _get_backend(mapping.backend, config)
        entry = state.get(mapping.local)

        # Compute current local state (before any pull)
        local_exists = os.path.exists(mapping.local)
        if local_exists:
            with open(mapping.local, encoding="utf-8") as f:
                local_content = f.read()
            current_local_hash = sha256_of_content(local_content)
        else:
            local_content = ""
            current_local_hash = ""

        # Check remote version
        try:
            remote_version = backend.get_remote_version(mapping.remote_id)
        except Exception as exc:
            err_console.print(f"Could not check remote version for {mapping.remote_id}: {exc}")
            remote_version = None

        if entry is None or remote_version is None:
            # First sync — proceed unconditionally
            result = backend.pull(mapping.remote_id, mapping.local)
            icon = "✓" if result.status == "ok" else "✗"
            style_name = "green" if result.status == "ok" else "red"
            console.print(f"[{style_name}]{icon}[/{style_name}]  {mapping.remote_id} → {mapping.local}")
            if result.message:
                console.print(f"   [dim]{result.message}[/dim]")

            if result.status == "ok" and os.path.exists(mapping.local):
                with open(mapping.local, encoding="utf-8") as f:
                    new_content = f.read()
                local_hash = sha256_of_content(new_content)
                base_hash = _save_base_content(state_dir, new_content)
                rv = remote_version or ""
                state.update(mapping.local, MappingState(
                    doc_id=mapping.remote_id,
                    backend=mapping.backend,
                    last_synced_at=datetime.now(timezone.utc).isoformat(),
                    base_hash=base_hash,
                    remote_version=rv,
                    local_hash=local_hash,
                ))
                state.save(state_path)
            continue

        remote_changed = (remote_version != entry.remote_version)
        local_changed = local_exists and (current_local_hash != entry.local_hash)

        if not remote_changed and not local_changed:
            console.print(f"[dim]up to date[/dim]  {mapping.local}")
            continue

        if remote_changed and not local_changed:
            # Fast-forward pull — remote changed, local unchanged
            result = backend.pull(mapping.remote_id, mapping.local)
            icon = "✓" if result.status == "ok" else "✗"
            style_name = "green" if result.status == "ok" else "red"
            console.print(f"[{style_name}]{icon}[/{style_name}]  {mapping.remote_id} → {mapping.local}")
            if result.message:
                console.print(f"   [dim]{result.message}[/dim]")

            if result.status == "ok" and os.path.exists(mapping.local):
                with open(mapping.local, encoding="utf-8") as f:
                    new_content = f.read()
                local_hash = sha256_of_content(new_content)
                base_hash = _save_base_content(state_dir, new_content)
                state.update(mapping.local, MappingState(
                    doc_id=mapping.remote_id,
                    backend=mapping.backend,
                    last_synced_at=datetime.now(timezone.utc).isoformat(),
                    base_hash=base_hash,
                    remote_version=remote_version,
                    local_hash=local_hash,
                ))
                state.save(state_path)
            continue

        if local_changed and not remote_changed:
            # Local changed, remote unchanged — skip and warn
            console.print(
                f"[yellow]warning[/yellow]  {mapping.local} has local changes not yet pushed. "
                "Pull skipped. Push first or use 'markgate conflicts resolve'."
            )
            continue

        # Both changed — three-way merge
        console.print(f"[yellow]merging[/yellow]  {mapping.local} (both sides changed)")

        # Save pre-merge local content as .orig
        orig_path = mapping.local + ".orig"
        with open(orig_path, "w", encoding="utf-8") as f:
            f.write(local_content)

        # Fetch remote content
        try:
            # Use a temp path to get remote content via backend.pull
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
                tmp_path = tmp.name
            tmp_result = backend.pull(mapping.remote_id, tmp_path)
            if tmp_result.status == "ok":
                with open(tmp_path, encoding="utf-8") as f:
                    theirs_content = f.read()
                os.unlink(tmp_path)
            else:
                os.unlink(tmp_path)
                console.print(f"   [red]Could not fetch remote content: {tmp_result.message}[/red]")
                continue
        except Exception as exc:
            console.print(f"   [red]Could not fetch remote content: {exc}[/red]")
            continue

        # Load base content
        base_content = _get_base_content(state_dir, entry.base_hash)

        merge_result = three_way_merge(base_content, theirs_content, local_content)
        with open(mapping.local, "w", encoding="utf-8") as f:
            f.write(merge_result.merged)

        if merge_result.has_conflicts:
            console.print(
                f"   [yellow]Merge conflicts ({merge_result.conflict_count}) written to "
                f"{mapping.local}. Resolve with: markgate conflicts resolve {mapping.local}[/yellow]"
            )
        else:
            console.print(f"   [green]Merged cleanly.[/green]")

        new_content = merge_result.merged
        local_hash = sha256_of_content(new_content)
        base_hash = _save_base_content(state_dir, new_content)
        state.update(mapping.local, MappingState(
            doc_id=mapping.remote_id,
            backend=mapping.backend,
            last_synced_at=datetime.now(timezone.utc).isoformat(),
            base_hash=base_hash,
            remote_version=remote_version,
            local_hash=local_hash,
        ))
        state.save(state_path)


# ─────────────────────────────────────────────────────────────────────────────
# status command
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def status(
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
):
    """Show current mapping status."""
    config = load_config(config_path)

    if not config.mappings:
        console.print("[yellow]No mappings configured.[/yellow] Add entries to markgate.yaml.")
        return

    table = Table(title="markgate mappings")
    table.add_column("Local file", style="cyan")
    table.add_column("Backend", style="magenta")
    table.add_column("Remote ID")
    table.add_column("Direction")

    for m in config.mappings:
        table.add_row(m.local, m.backend, m.remote_id, m.direction)

    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# auth subcommand
# ─────────────────────────────────────────────────────────────────────────────

@auth_app.command("setup")
def auth_setup(
    backend: str = typer.Argument(..., help="Backend to authenticate: google_docs | confluence"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
):
    """Interactive authentication setup for a backend."""
    config = load_config(config_path)
    b = _get_backend(backend, config)
    b.auth_setup()


# ─────────────────────────────────────────────────────────────────────────────
# conflicts subcommand
# ─────────────────────────────────────────────────────────────────────────────

@conflicts_app.command("list")
def conflicts_list(
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
):
    """List files with unresolved merge conflicts."""
    state_path = _get_state_path(config_path)
    try:
        state = SyncState.load(state_path)
    except Exception:
        console.print("No unresolved conflicts.")
        return

    conflicted = []
    for local_path, entry in state.mappings.items():
        if not os.path.exists(local_path):
            continue
        with open(local_path, encoding="utf-8") as f:
            content = f.read()
        lines = content.splitlines()
        conflict_count = sum(1 for line in lines if line.startswith("<<<<<<< "))
        if conflict_count > 0:
            conflicted.append((local_path, conflict_count))

    if not conflicted:
        console.print("No unresolved conflicts.")
        return

    table = Table(title="Files with merge conflicts")
    table.add_column("File", style="cyan")
    table.add_column("Conflict blocks", style="red")
    for local_path, count in conflicted:
        table.add_row(local_path, str(count))
    console.print(table)


@conflicts_app.command("resolve")
def conflicts_resolve(
    file: str = typer.Argument(..., help="Local file path to resolve"),
    accept: str = typer.Option(..., "--accept", help="Resolution strategy: remote | local | merged"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
):
    """Resolve a merge conflict in a tracked file."""
    if accept not in ("remote", "local", "merged"):
        err_console.print("--accept must be one of: remote, local, merged")
        raise typer.Exit(1)

    state_path = _get_state_path(config_path)
    state_dir = _get_state_dir(config_path)
    try:
        state = SyncState.load(state_path)
    except Exception:
        state = SyncState()

    entry = state.get(file)
    if entry is None:
        err_console.print(f"File '{file}' is not tracked in .markgate-state.json")
        raise typer.Exit(1)

    config = load_config(config_path)
    backend = _get_backend(entry.backend, config)

    if accept == "remote":
        result = backend.pull(entry.doc_id, file)
        if result.status != "ok":
            err_console.print(f"Could not re-fetch remote: {result.message}")
            raise typer.Exit(1)
        # Delete .orig if present
        orig_path = file + ".orig"
        if os.path.exists(orig_path):
            os.unlink(orig_path)
        # Update state
        with open(file, encoding="utf-8") as f:
            new_content = f.read()
        local_hash = sha256_of_content(new_content)
        base_hash = _save_base_content(state_dir, new_content)
        try:
            remote_version = backend.get_remote_version(entry.doc_id)
        except Exception:
            remote_version = entry.remote_version
        state.update(file, MappingState(
            doc_id=entry.doc_id,
            backend=entry.backend,
            last_synced_at=datetime.now(timezone.utc).isoformat(),
            base_hash=base_hash,
            remote_version=remote_version,
            local_hash=local_hash,
        ))
        state.save(state_path)
        console.print(f"[green]Resolved[/green] {file} (accepted remote)")

    elif accept == "local":
        orig_path = file + ".orig"
        if os.path.exists(orig_path):
            import shutil
            shutil.copy2(orig_path, file)
            os.unlink(orig_path)
            console.print(f"[green]Restored[/green] {file} from {orig_path}")
        else:
            # Restore from base content
            base_content = _get_base_content(state_dir, entry.base_hash)
            if base_content:
                with open(file, "w", encoding="utf-8") as f:
                    f.write(base_content)
                console.print(f"[yellow]Warning:[/yellow] .orig not found; restored from base content")
            else:
                err_console.print(f"No .orig file and no base content for '{file}'. Cannot restore.")
                raise typer.Exit(1)
        # Update state
        with open(file, encoding="utf-8") as f:
            new_content = f.read()
        local_hash = sha256_of_content(new_content)
        base_hash = _save_base_content(state_dir, new_content)
        state.update(file, MappingState(
            doc_id=entry.doc_id,
            backend=entry.backend,
            last_synced_at=datetime.now(timezone.utc).isoformat(),
            base_hash=base_hash,
            remote_version=entry.remote_version,
            local_hash=local_hash,
        ))
        state.save(state_path)
        console.print(f"[green]Resolved[/green] {file} (accepted local)")

    elif accept == "merged":
        if not os.path.exists(file):
            err_console.print(f"File '{file}' does not exist")
            raise typer.Exit(1)
        with open(file, encoding="utf-8") as f:
            content = f.read()
        if "<<<<<<< " in content:
            err_console.print(
                f"File '{file}' still contains conflict markers. "
                "Resolve all conflicts before accepting as merged."
            )
            raise typer.Exit(1)
        local_hash = sha256_of_content(content)
        base_hash = _save_base_content(state_dir, content)
        state.update(file, MappingState(
            doc_id=entry.doc_id,
            backend=entry.backend,
            last_synced_at=datetime.now(timezone.utc).isoformat(),
            base_hash=base_hash,
            remote_version=entry.remote_version,
            local_hash=local_hash,
        ))
        state.save(state_path)
        console.print(f"[green]Resolved[/green] {file} (accepted merged)")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
