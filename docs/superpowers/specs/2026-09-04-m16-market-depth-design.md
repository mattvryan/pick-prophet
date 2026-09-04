# M16 market-depth design

Date: 2026-09-04
Status: implemented with paid-access stop condition
Branch: `codex/m16-market-depth`

M16 audits the existing matrix, evaluates publisher documentation, and freezes
a provider-neutral quote contract. It does not purchase data, accept a trial,
or relabel undated CFBD lines. A technically suitable source must provide a
timestamped snapshot history, both moneyline sides, stable event identity, and
lawful research/cache terms before an adapter PR is authorized.

The valid outcome is continued use of the current closing-like baseline with
market-depth features explicitly unavailable. This prevents a weaker or
hindsight-contaminated proxy from making a candidate appear to beat Vegas.
