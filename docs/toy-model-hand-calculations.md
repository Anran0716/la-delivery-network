# Model v1 hand calculations

These calculations precede implementation and county optimization. Demand is 10
parcels/day in each of four cells, utilization is 1, and the unmet penalty is 100
per parcel. Fractions may be split among stations. Unit delivery costs are:

| Station | Cell 1 | Cell 2 | Cell 3 | Cell 4 |
| --- | ---: | ---: | ---: | ---: |
| A | 1 | 1 | 5 | 5 |
| B | 5 | 5 | 1 | 1 |
| C | 2 | 2 | 2 | 2 |

## Base case

With fixed cost 30 and capacity 40, opening A+B costs 60 fixed plus 40 delivery:
**100**. C alone costs 30+80=110. A or B alone costs 30+120=150. A+C or B+C costs
60+60=120, and all three cost at least 90+40=130. Unmet demand cannot improve on
these solutions at a penalty of 100 per parcel.

## High fixed cost

With fixed cost 100 and capacity 40, C alone costs **180**. A or B alone costs
220; A+B costs 240, A+C or B+C costs 260, and all three cost at least 340.

## Binding capacity

With fixed cost 30 and capacity 15, at least three stations are required to serve
40 parcels. A and B can each deliver 15 parcels at cost 1; C must deliver the
remaining 10 at cost 2. Delivery therefore costs 15+15+20=50 and fixed costs are
90, giving **140**. This attains the lower bound: at most 30 parcels can receive
cost 1 and the other 10 must cost at least 2. With two stations, at least 10
parcels would be unmet and incur at least 1,000 in penalties.

## Coverage restriction and a tie

Delete C-to-cell-4 from the allowed arcs, with fixed cost 100 and capacity 40.
A alone and B alone each cost **220**, so the test must accept either. C alone
cannot serve cell 4 and costs at least 100+60+1,000=1,160. A+B costs 240; B+C
costs 260; A+C costs 290; three stations cost at least 340. Assert the objective,
exactly one open station, no unmet demand, and C closed; do not assert A versus B.

Every case is checked using both strong (`x_ij <= y_i`) and weak (capacity-only)
linking. Their integer optima coincide because every demand is strictly positive.
The independent checker also receives deliberately invalid assignments to prove
that capacity, balance, bounds, closed-station links, coverage, and objective
errors are rejected.
