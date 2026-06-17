"""Strategy modules. Each exposes ``generate_signals(df) -> DataFrame``
with columns ``signal`` (-1/0/+1) and ``sl_pts`` (float), plus a
``KIND`` constant ("trend" or "reversion") for regime gating.
"""
