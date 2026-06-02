"""v4 - parallel-personas + skeptic PR review.

The "we got greedy" multi-agent version: instead of bundling all four reviewer
personas into one prompt (v3), v4 runs ONE agent per persona in parallel, pools
their findings, then runs a single Opus "skeptic" pass to prune false positives
and merge duplicates. Powerful but expensive — it sets up v5's tiering. See
`review.py`.
"""
