"""Confluence backend — uses ported adf/markdown/services modules from markdown-confluence."""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Optional

from markgate.backends.base import Backend, PushResult, PullResult

logger = logging.getLogger(__name__)


class ConfluenceBackend(Backend):
    name = "confluence"

    def __init__(self, config: dict):
        self.config = config
        self._client: Optional[object] = None
        self._comment_client: Optional[object] = None

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

    def _ensure_comment_client(self):
        if self._comment_client is not None:
            return
        self._ensure_client()
        from markgate.backends.confluence.services.confluence.comment_client import ConfluenceCommentClient
        # ConfluenceClient stores the config in self.config
        self._comment_client = ConfluenceCommentClient(self._client.config)

    def _write_comment_sidecar(
        self,
        local_path: str,
        page_title: str,
        inline_comments: list,
        footer_comments: list,
    ) -> None:
        """Write inline and footer comments to a sidecar .comments.md file."""
        lines = [f"# Comments: {page_title}", ""]

        if inline_comments:
            lines.append("## Inline comments")
            lines.append("")
            for comment in inline_comments:
                comment_id = comment.get("id", "unknown")
                # v2 API: version.authorId doesn't have displayName directly;
                # try createdBy.displayName (v2) or version.by.displayName (v1)
                author = (
                    comment.get("createdBy", {}).get("displayName")
                    or comment.get("version", {}).get("by", {}).get("displayName", "Unknown")
                )
                date = (
                    comment.get("version", {}).get("createdAt", "")
                    or comment.get("version", {}).get("friendlyWhen", "")
                )
                lines.append(f"### [{comment_id}] {author} — {date}")
                lines.append("")
                # Inline selection (v2 API: properties.inlineOriginalSelection)
                selection = (
                    comment.get("properties", {}).get("inlineOriginalSelection", "")
                    or comment.get("inlineCommentProperties", {}).get("textSelection", "")
                )
                if selection:
                    lines.append(f'> Selection: "{selection}"')
                    lines.append("")
                # Body text
                body_html = (
                    comment.get("body", {}).get("storage", {}).get("value", "")
                    or comment.get("body", {}).get("view", {}).get("value", "")
                )
                body_text = re.sub(r"<[^<]+?>", "", body_html).strip()
                if body_text:
                    lines.append(body_text)
                lines.append("")
                lines.append("---")
                lines.append("")

        if footer_comments:
            lines.append("## Footer comments")
            lines.append("")
            for comment in footer_comments:
                comment_id = comment.get("id", "unknown")
                author = (
                    comment.get("createdBy", {}).get("displayName")
                    or comment.get("version", {}).get("by", {}).get("displayName", "Unknown")
                )
                date = (
                    comment.get("version", {}).get("createdAt", "")
                    or comment.get("version", {}).get("friendlyWhen", "")
                )
                lines.append(f"### [{comment_id}] {author} — {date}")
                lines.append("")
                body_html = (
                    comment.get("body", {}).get("storage", {}).get("value", "")
                    or comment.get("body", {}).get("view", {}).get("value", "")
                )
                body_text = re.sub(r"<[^<]+?>", "", body_html).strip()
                if body_text:
                    lines.append(body_text)
                lines.append("")
                lines.append("---")
                lines.append("")

        sidecar_path = str(local_path) + ".comments.md"
        pathlib.Path(sidecar_path).write_text("\n".join(lines))

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

            from markgate.backends.confluence.models.page import ConfluencePage
            parent_id = page.get("parentId") or (page.get("ancestors") or [{}])[-1].get("id", "")
            confluence_page = ConfluencePage(
                id=doc_id,
                title=title,
                content=adf_doc,
                parent_id=parent_id,
                version=version,  # to_api_data(for_update=True) increments by 1
            )
            self._client.update_page(confluence_page)
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

            # Fetch and write comment sidecar
            try:
                self._ensure_comment_client()
                page = self._client.get_page(doc_id)
                page_title = page.get("title", "Untitled")
            except Exception:
                page_title = "Untitled"

            inline_comments: list = []
            footer_comments: list = []

            try:
                inline_comments = self._comment_client.get_page_inline_comments(doc_id)
            except Exception as exc:
                # Fall back to v1 on 404 or any error
                try:
                    from markgate.backends.confluence.services.confluence.base_client import PageNotFoundError
                    v1_result = self._comment_client.get_comments(doc_id)
                    inline_comments = v1_result.get("results", [])
                except Exception:
                    logger.warning(
                        f"Could not fetch inline comments for {doc_id}: {exc}"
                    )

            try:
                footer_comments = self._comment_client.get_page_footer_comments(doc_id)
            except Exception as exc:
                logger.warning(f"Could not fetch footer comments for {doc_id}: {exc}")

            if inline_comments or footer_comments:
                self._write_comment_sidecar(local_path, page_title, inline_comments, footer_comments)

            return PullResult(status="ok", doc_id=doc_id, local_path=local_path)
        except Exception as e:
            return PullResult(
                status="error", doc_id=doc_id, local_path=local_path, message=str(e)
            )

    def get_remote_version(self, doc_id: str) -> str:
        """Return the current Confluence page version number as a string."""
        self._ensure_client()
        page = self._client.get_page(doc_id)
        return str(page["version"]["number"])

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
