"""
Confluence API integration module.

This module provides functionality for interacting with the Confluence API,
including specialized clients for different Confluence resources.
"""

from markgate.backends.confluence.services.confluence.base_client import (
    ConfluenceApiError,
    ArchivedPageError,
    PageNotFoundError,
    RestrictedPageError,
    BaseConfluenceClient
)
from markgate.backends.confluence.services.confluence.page_client import PageClient
from markgate.backends.confluence.services.confluence.attachment_client import AttachmentClient
from markgate.backends.confluence.services.confluence.label_client import LabelClient
from markgate.backends.confluence.services.confluence.space_client import SpaceClient
from markgate.backends.confluence.services.confluence.client import ConfluenceClient
from markgate.backends.confluence.services.confluence.comment_client import (
    ConfluenceCommentClient,
    CommentNotFoundError,
    InlineCommentNotSupportedError,
)

__all__ = [
    "ConfluenceClient",
    "BaseConfluenceClient",
    "PageClient",
    "AttachmentClient",
    "LabelClient",
    "SpaceClient",
    "ConfluenceCommentClient",
    "ConfluenceApiError",
    "ArchivedPageError",
    "PageNotFoundError",
    "RestrictedPageError",
    "CommentNotFoundError",
    "InlineCommentNotSupportedError",
]