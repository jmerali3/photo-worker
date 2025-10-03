"""Shared helpers for configuring boto3 sessions."""

from typing import Optional, Dict, Any

import boto3


def create_boto3_session(
    *,
    region: str,
    profile_name: Optional[str] = None,
) -> boto3.Session:
    """Build a boto3 session honoring profile configuration first."""

    session_kwargs: Dict[str, Any] = {"region_name": region}

    if profile_name:
        session_kwargs["profile_name"] = profile_name

    return boto3.Session(**session_kwargs)
