"""Portable SQLite projections. JSONL remains authoritative; views grant no authority."""
# Every child join includes the evaluation cohort, including OWNER_DECISION's separate
# evaluation_source. A later REPLAY evaluation cannot erase a LIVE cohort from statistics.
VIEWS = (
    """CREATE VIEW v_ticket_cohorts AS
    WITH ranked AS (
      SELECT *, COALESCE(ticket_id, evaluation_id) AS ticket_key,
        ROW_NUMBER() OVER (PARTITION BY COALESCE(ticket_id,evaluation_id), source
                          ORDER BY evaluated_at_utc DESC, evaluation_id DESC) AS rank
      FROM evaluations
    ) SELECT e.ticket_key AS ticket_id, e.strategy, e.symbol, e.session, e.source,
      e.evaluated_at_utc, e.state, e.record_json AS evaluation,
      (SELECT json_group_array(json(record_json)) FROM
        (SELECT record_json FROM evaluations x WHERE COALESCE(x.ticket_id,x.evaluation_id)=e.ticket_key
         AND x.source=e.source ORDER BY evaluated_at_utc,evaluation_id)) AS evaluations,
      (SELECT json_group_array(json(record_json)) FROM
        (SELECT record_json FROM deliveries x WHERE x.ticket_id=e.ticket_key AND x.source=e.source
         ORDER BY recorded_at_utc,record_id)) AS deliveries,
      (SELECT json_group_array(json(record_json)) FROM
        (SELECT record_json FROM owner_decisions x WHERE x.ticket_id=e.ticket_key AND x.evaluation_source=e.source
         ORDER BY recorded_at_utc,record_id)) AS decisions,
      (SELECT json_group_array(json(record_json)) FROM
        (SELECT record_json FROM order_events x WHERE x.ticket_id=e.ticket_key AND x.source=e.source
         ORDER BY recorded_at_utc,record_id)) AS orders,
      (SELECT json_group_array(json(record_json)) FROM
        (SELECT record_json FROM position_closes x WHERE x.ticket_id=e.ticket_key AND x.source=e.source
         ORDER BY recorded_at_utc,record_id)) AS closes,
      (SELECT json_group_array(json(record_json)) FROM
        (SELECT record_json FROM outcomes x WHERE x.ticket_id=e.ticket_key AND x.source=e.source
         ORDER BY recorded_at_utc,outcome_id)) AS outcomes,
      EXISTS(SELECT 1 FROM owner_decisions x WHERE x.ticket_id=e.ticket_key AND x.evaluation_source=e.source) AS decided,
      EXISTS(SELECT 1 FROM order_events x WHERE x.ticket_id=e.ticket_key AND x.source=e.source
             AND x.event IN ('FILLED','PARTIALLY_FILLED')) AS filled,
      COALESCE(
        (SELECT json_extract(record_json,'$.realized_R') FROM position_closes x
         WHERE x.ticket_id=e.ticket_key AND x.source=e.source
         ORDER BY recorded_at_utc DESC,record_id DESC LIMIT 1),
        (SELECT COALESCE(json_extract(record_json,'$.payload.net_R'),
                         json_extract(record_json,'$.payload.realized_R')) FROM outcomes x
         WHERE x.ticket_id=e.ticket_key AND x.source=e.source AND outcome_kind NOT LIKE 'COUNTERFACTUAL%'
         ORDER BY recorded_at_utc DESC,outcome_id DESC LIMIT 1)) AS realized_R,
      (SELECT MAX(adverse) FROM (
         SELECT json_extract(record_json,'$.max_adverse_R') AS adverse FROM position_closes x
          WHERE x.ticket_id=e.ticket_key AND x.source=e.source
         UNION ALL
         SELECT json_extract(record_json,'$.payload.mae_R') AS adverse FROM outcomes x
          WHERE x.ticket_id=e.ticket_key AND x.source=e.source AND outcome_kind NOT LIKE 'COUNTERFACTUAL%'
       )) AS max_adverse_R
    FROM ranked e WHERE rank=1""",
    """CREATE VIEW v_ticket_history AS
    SELECT ticket_id,strategy,symbol,session,source,evaluated_at_utc,state,evaluation,evaluations,
           deliveries,decisions,orders,closes,outcomes,decided,filled,realized_R,max_adverse_R
    FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY ticket_id
          ORDER BY evaluated_at_utc DESC,source DESC) AS ticket_rank FROM v_ticket_cohorts)
    WHERE ticket_rank=1""",
    """CREATE VIEW v_strategy_stats AS
    SELECT strategy,symbol,session,source,COUNT(*) AS tickets,SUM(decided) AS decided,SUM(filled) AS filled,
      COUNT(realized_R) AS resolved,
      AVG(CASE WHEN realized_R IS NULL THEN NULL WHEN realized_R>0 THEN 1.0 ELSE 0.0 END) AS win_rate,
      AVG(realized_R) AS avg_R, AVG(realized_R) AS expectancy, MAX(max_adverse_R) AS max_adverse_R
    FROM v_ticket_cohorts WHERE source IN ('LIVE','DEMO')
    GROUP BY strategy,symbol,session,source""",
)
