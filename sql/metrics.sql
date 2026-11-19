-- Definitions and input contracts: docs/metrics.md.
-- Demand-driven left join retains entirely unserved and excluded cells.
CREATE OR REPLACE VIEW assign_enriched AS
SELECT d.scenario, d.h3, d.in_model, d.demand_parcels,
       a.candidate_id, coalesce(a.served_parcels, 0.0) AS served_parcels,
       t.travel_time_min, p.coverage_minutes,
       coalesce(a.served_parcels, 0.0) * t.travel_time_min
           * p.delivery_usd_per_parcel_minute AS delivery_cost
FROM demand_input d
LEFT JOIN assignment_input a USING (scenario, h3)
LEFT JOIN travel_input t USING (scenario, h3, candidate_id)
JOIN parameter_input p USING (scenario);

-- Open sites only; physical Q denominator, not 0.85*Q. Unused open sites are zero.
CREATE OR REPLACE VIEW station_metrics AS
SELECT s.scenario, s.candidate_id, s.capacity, s.fixed_cost,
       coalesce(sum(a.served_parcels), 0.0) AS served_parcels,
       coalesce(sum(a.served_parcels), 0.0) / s.capacity AS utilization,
       coalesce(sum(a.served_parcels), 0.0) / s.capacity > 0.85
           AS above_baseline_headroom
FROM station_input s
LEFT JOIN assign_enriched a USING (scenario, candidate_id)
WHERE s.opened
GROUP BY s.scenario, s.candidate_id, s.capacity, s.fixed_cost;

CREATE OR REPLACE VIEW scenario_metrics AS
WITH flows AS (
    SELECT scenario, scope, sum(demand_parcels) AS total_demand,
           sum(served_parcels) AS served_parcels,
           greatest(0.0, sum(demand_parcels) - sum(served_parcels)) AS unmet_parcels,
           sum(served_parcels * coalesce(travel_time_min, 0.0)) AS parcel_minutes,
           sum(CASE WHEN travel_time_min <= coverage_minutes
                    THEN served_parcels ELSE 0.0 END) AS covered_parcels,
           sum(coalesce(delivery_cost, 0.0)) AS delivery_cost
    FROM assign_enriched
    CROSS JOIN (VALUES ('modeled'), ('study_area')) scopes(scope)
    WHERE scope = 'study_area' OR in_model
    GROUP BY scenario, scope
), costs AS (
    SELECT p.scenario, count(s.candidate_id) AS open_stations,
           coalesce(sum(s.fixed_cost), 0.0) AS fixed_cost,
           coalesce(sum(s.capacity), 0.0) AS total_capacity
    FROM parameter_input p
    LEFT JOIN station_metrics s USING (scenario)
    GROUP BY p.scenario
)
SELECT f.scenario, f.scope, c.open_stations, f.total_demand, f.served_parcels,
       f.served_parcels / nullif(c.total_capacity, 0.0) AS network_utilization,
       f.unmet_parcels, f.parcel_minutes / nullif(f.served_parcels, 0.0)
           AS weighted_mean_travel_minutes,
       f.covered_parcels / nullif(f.total_demand, 0.0) AS coverage_20min,
       c.fixed_cost, f.delivery_cost,
       (c.fixed_cost + f.delivery_cost) / nullif(f.served_parcels, 0.0)
           AS cost_per_served_parcel,
       f.unmet_parcels / nullif(f.total_demand, 0.0) AS unmet_rate
FROM flows f JOIN costs c USING (scenario);
