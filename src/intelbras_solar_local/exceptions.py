"""Exceptions for the Intelbras Solar local client."""
from __future__ import annotations


class IntelbrasSolarError(Exception):
    """Base error for all Intelbras Solar client failures."""


class IntelbrasSolarConnectionError(IntelbrasSolarError):
    """Raised when the datalogger is unreachable or the transport fails."""


class IntelbrasSolarProtocolError(IntelbrasSolarError):
    """Raised when the device answers with an error (Modbus exception, bad reply)."""
