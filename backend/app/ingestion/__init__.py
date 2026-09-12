"""Data ingestion layer: AkShare adapters, throttling, normalization, scheduling.

Rule: the UI/API never live-calls AkShare. All external fetching happens here, on a
schedule or via explicit CLI/API triggers, and lands in the DB (idempotent upserts).
"""
