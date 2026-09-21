"""Publish adapters: validate() checks a local release package; send() is always
blocked by the egress guard in internal_only mode. No adapter imports a network
library -- enforced by a static AST test, not just this docstring.
"""

from __future__ import annotations

from tools.publish_adapters.base import BasePublishAdapter, PublishAdapterError
from tools.publish_adapters.ecommerce import EcommerceAdapter
from tools.publish_adapters.facebook import FacebookAdapter
from tools.publish_adapters.instagram import InstagramAdapter
from tools.publish_adapters.tiktok import TiktokAdapter
from tools.publish_adapters.youtube import YoutubeAdapter

ADAPTERS: dict[str, type[BasePublishAdapter]] = {
    "youtube": YoutubeAdapter,
    "instagram": InstagramAdapter,
    "facebook": FacebookAdapter,
    "tiktok": TiktokAdapter,
    "ecommerce": EcommerceAdapter,
}

__all__ = [
    "ADAPTERS",
    "BasePublishAdapter",
    "PublishAdapterError",
    "YoutubeAdapter",
    "InstagramAdapter",
    "FacebookAdapter",
    "TiktokAdapter",
    "EcommerceAdapter",
]
