"""
stream — Real-time data streaming for VCMix.

Provides structured data output during rendering for AI Agent consumption.
Enables closed-loop control: data → judgment → auto-adjust → verify.

Usage:
    from vcmix.stream import DataStream, StreamEvent
"""
from vcmix.stream.emitter import DataStream, StreamEvent

__all__ = ["DataStream", "StreamEvent"]
