# Period 4 preregistered predictions

Recorded before running the hard-service baseline, v2, or any period-4 scenario
(UTC: 2026-11-19T03:01:26+00:00). These are
predictions to test, not measured scenario conclusions.

1. **Fixed costs 15,000 / 40,000 USD/day:** station counts should remain close to
   the new full-service v2 baseline, while locations may change. For this check,
   a change of more than one station is considered material and triggers review
   of geography, utilization, delivery-cost tradeoffs, and incumbent gaps.
   The capacity floor is necessary, rather than a proof of invariant site counts.
2. **Peak demand at 1.4 times baseline:** modeled demand becomes 711,204.05
   parcels/day. Reoptimization with full service, Q=20,000 and u=0.85 needs at
   least **42 stations**. Keeping the legacy **31-station** network and
   allowing u=1 gives capacity 620,000, hence an aggregate unmet lower bound of
   **91,204.05 parcels/day (12.824%)**, before geographic restrictions.

The unchanged model universe is 1,615 mainland cells. The 250 structural exclusions
remain outside optimization and are added separately to study-area unmet totals;
under peak demand their parcel volume is scaled by 1.4 too. The corresponding
whole-mainland demand is 711,694.83 parcels/day; its 31-station capacity shortfall
is at least 91,694.83 (12.884%). The new hard-service/v2 baseline may select more
than 31 stations. Main fixed-network scenarios will use that new baseline, with
an additional legacy-31 peak comparison to test the original conditional forecast.

Results will be compared with these predictions after the scenario runs, with
feasible incumbents distinguished from exact optimality proofs.

