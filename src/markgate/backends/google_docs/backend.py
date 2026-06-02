"""Google Docs backend — wraps the auth/client/converter modules from the fork."""

import pathlib

from markgate.backends.base import Backend, PushResult, PullResult


class GoogleDocsBackend(Backend):
    name = "google_docs"

    def __init__(self, config: dict):
        self.config = config
        self._auth = None
        self._client = None

    def _ensure_auth(self):
        if self._client is None:
            from markgate.backends.google_docs.auth import DualAccountAuth
            from markgate.backends.google_docs.client import GoogleDocsClient
            auth = DualAccountAuth()
            if not auth.is_authenticated():
                raise RuntimeError(
                    "Google Docs credentials not found. Run: markgate auth setup google_docs"
                )
            self._client = GoogleDocsClient(auth.get_account_a_credentials())

    def push(self, local_path: str, doc_id: str, **kwargs) -> PushResult:
        """Convert local markdown to Google Docs format using structural diff and batch update."""
        self._ensure_auth()
        try:
            content = pathlib.Path(local_path).read_text()

            from markgate.backends.google_docs.markdown_to_paragraph_parser import MarkdownToParagraphParser
            from markgate.backends.google_docs.docs_structure_parser import DocsStructureParser
            from markgate.backends.google_docs.docs_request_builder import DocsRequestBuilder

            target_nodes = MarkdownToParagraphParser().parse(content)
            doc = self._client.get_document(doc_id)
            current_nodes = DocsStructureParser().parse(doc)

            # Get doc_end_index from last content element to protect the terminal newline
            if "tabs" in doc and doc["tabs"]:
                body_content = doc["tabs"][0].get("documentTab", doc).get("body", {}).get("content", [])
            else:
                body_content = doc.get("body", {}).get("content", [])
            doc_end_index = body_content[-1].get("endIndex", 1) if body_content else 1

            builder = DocsRequestBuilder()
            requests = builder.build(current_nodes, target_nodes, doc_end_index)

            if not requests:
                return PushResult(status="skipped", doc_id=doc_id, message="No changes detected")

            self._client.batch_update(doc_id, requests)
            url = f"https://docs.google.com/document/d/{doc_id}/edit"
            return PushResult(status="ok", doc_id=doc_id, url=url)
        except Exception as e:
            return PushResult(status="error", doc_id=doc_id, message=str(e))

    def pull(self, doc_id: str, local_path: str, **kwargs) -> PullResult:
        """Export Google Doc as HTML, convert to markdown, write locally."""
        self._ensure_auth()
        from markgate.backends.google_docs.converter import DocumentConverter

        try:
            html_content = self._client.get_doc_content(doc_id)
            converter = DocumentConverter()
            markdown_content = converter.html_to_markdown(html_content)
            pathlib.Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(local_path).write_text(markdown_content)
            return PullResult(status="ok", doc_id=doc_id, local_path=local_path)
        except Exception as e:
            return PullResult(
                status="error", doc_id=doc_id, local_path=local_path, message=str(e)
            )

    def get_remote_version(self, doc_id: str) -> str:
        """Return the revisionId of the Google Doc (opaque, non-empty string)."""
        self._ensure_auth()
        doc = self._client.get_document(doc_id)
        return doc["revisionId"]

    def auth_setup(self) -> None:
        """Interactive OAuth setup for Google account(s)."""
        # TODO: interactive wizard
        raise NotImplementedError("Run: markgate auth setup google_docs")

    def validate_config(self, config: dict) -> None:
        required = ["google_docs"]
        for key in required:
            if key not in config.get("backends", {}):
                raise ValueError(f"Missing [backends.{key}] in markgate.yaml")
