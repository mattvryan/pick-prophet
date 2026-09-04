# Superseded derived snapshot

Do not use `market.csv` from this directory. It revealed that taking the median
of displayed American moneylines can cross the discontinuity at even money and
produce an invalid number. The raw `cfbd_lines.json` remains valid and is retained
for auditability. A later snapshot uses probability-space consensus calculation.
