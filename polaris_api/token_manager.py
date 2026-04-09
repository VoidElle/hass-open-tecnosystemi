"""DEPRECATED: Token manager was used for cloud REST API authentication.

The Polaris integration now uses local UDP communication (same as Pico),
so AES token rotation is no longer needed. This file is kept as a no-op
to avoid import errors from any external references.
"""
