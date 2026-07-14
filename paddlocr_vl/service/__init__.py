"""Triton provider integration."""

from .paddleocr_vl import TritonClient, TritonError

__all__ = ["TritonClient", "TritonError"]
