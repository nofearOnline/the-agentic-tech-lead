"""v5 - tiered parallel-personas + skeptic PR review.

The "redesign that made it ~7x cheaper" version. v4 ran one Sonnet agent per
persona in parallel plus an Opus skeptic — powerful but expensive. v5 keeps that
exact multi-agent shape and matches its quality while slashing cost via two
blog ideas: (A) a deterministic, zero-inference pre-phase that gates which
personas are worth running and shrinks the skeptic's input, and (B) model
tiering — Haiku for the breadth personas, Opus kept only as the skeptic. See
`review.py`.
"""
