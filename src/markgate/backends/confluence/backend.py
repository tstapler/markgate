"""Confluence backend — uses ported adf/markdown/services modules from markdown-confluence."""

from __future__ import annotations

import pathlib
from typing import Optional

from markgate.backends.base import Backend, PushResult, PullResult


class ConfluenceBackend(Backend):
    name = "confluence"

    def __init__(self, config: dict):
        self.config = config
        self._client: Optional[object] = None

    def _ensure_client(self):
        if self._client is not None:
            return
        cfg = self.config.get("backends", {}).get("confluence", {})
        import os
        base_url = cfg.get("base_url") or os.getenv("CONFLUENCE_BASE_URL")
        username = cfg.get("username") or os.getenv("ATLASSIAN_USER_NAME")
        api_token = cfg.get("api_token") or os.getenv("CONFLUENCE_API_TOKEN")
        if not all([base_url, username, api_token]):
            raise RuntimeError(
                "Confluence credentials incomplete. Run: markgate auth setup confluence\n"
                "Or set CONFLUENCE_BASE_URL, ATLASSIAN_USER_NAME, CONFLUENCE_API_TOKEN."
            )
        from markgate.backends.confluence.config.models import ConfluenceConfig
        from markgate.backends.confluence.services.confluence.client import ConfluenceClient
        confluence_cfg = ConfluenceConfig(
            base_url=base_url,
            username=username,
            api_token=api_token,
        )
        self._client = ConfluenceClient(confluence_cfg)

    def push(self, local_path: str, doc_id: str, **kwargs) -> PushResult:
        """Convert local markdown to ADF and update the Confluence page."""
        self._ensure_client()
        try:
            content = pathlib.Path(local_path).read_text()
            from markgate.backends.confluence.markdown.parser import MarkdownParser
            from markgate.backends.confluence.adf.converter import AdfConverter

            parser = MarkdownParser()
            ast = parser.parse(content)
            converter = AdfConverter()
            adf_doc = converter.convert(ast)

            # Get current page to retrieve title and version
            page = self._client.get_page(doc_id)
            title = page.get("title", "Untitled")
            version = page.get("version", {}).get("number", 1)

            self._client.update_page(
                page_id=doc_id,
                title=title,
                adf_content=adf_doc,
                version=version + 1,
            )
            base_url = self.config.get("backends", {}).get("confluence", {}).get("base_url", "")
            url = f"{base_url}/pages/{doc_id}"
            return PushResult(status="ok", doc_id=doc_id, url=url)
        except Exception as e:
            return PushResult(status="error", doc_id=doc_id, message=str(e))

    def pull(self, doc_id: str, local_path: str, **kwargs) -> PullResult:
        """Fetch Confluence page storage content and convert to markdown."""
        self._ensure_client()
        try:
            from markgate.backends.confluence.services.confluence.crawler import ConfluenceCrawler
            crawler = ConfluenceCrawler(self._client)
            markdown = crawler.page_to_markdown(doc_id)
            pathlib.Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(local_path).write_text(markdown)
            return PullResult(status="ok", doc_id=doc_id, local_path=local_path)
        except Exception as e:
            return PullResult(
                status="error", doc_id=doc_id, local_path=local_path, message=str(e)
            )

    def auth_setup(self) -> None:
        """Interactive Confluence auth wizard."""
        import os
        import typer
        from rich.console import Console
        console = Console()
        console.print("\n[bold]Confluence auth setup[/bold]")
        base_url = typer.prompt("Confluence base URL (e.g. https://yourorg.atlassian.net)")
        username = typer.prompt("Atlassian username (email)")
        api_token = typer.prompt("API token (from id.atlassian.com/manage-profile/security/api-tokens)", hide_input=True)
        # Write to markgate.yaml
        console.print(
            f"\nAdd to [cyan]markgate.yaml[/cyan]:\n\n"
            f"backends:\n"
            f"  confluence:\n"
            f"    base_url: {base_url}\n"
            f"    username: {username}\n"
            f"    api_token: {api_token}\n"
        )
        console.print("[green]Done.[/green] Test with: markgate status")

    def validate_config(self, config: dict) -> None:
        import os
        cfg = config.get("backends", {}).get("confluence", {})
        missing = []
        if not (cfg.get("base_url") or os.getenv("CONFLUENCE_BASE_URL")):
            missing.append("base_url / CONFLUENCE_BASE_URL")
        if not (cfg.get("username") or os.getenv("ATLASSIAN_USER_NAME")):
            missing.append("username / ATLASSIAN_USER_NAME")
        if not (cfg.get("api_token") or os.getenv("CONFLUENCE_API_TOKEN")):
            missing.append("api_token / CONFLUENCE_API_TOKEN")
        if missing:
            raise ValueError(
                f"Missing Confluence config: {', '.join(missing)}. "
                "Run: markgate auth setup confluence"
            )
