"""Pydantic schemas (request/response DTOs).

Read-heavy aggregation endpoints return plain dicts wrapped in a standard envelope
(see ``app.api.common``); strict schemas are used for inputs and auth.
"""
