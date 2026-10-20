-- Calculate background counts only for eligible accounts.
-- Use direction indexes to count all payment methods and self-transfers in [start, cutoff).
-- Use CROSS JOIN to select indexed accounts before transaction rows.
WITH eligible_edges AS MATERIALIZED (
    SELECT * FROM edges
    WHERE event_time >= :window_start AND event_time < :cutoff
      AND src <> dst AND paid > 0 AND received > 0
      AND payment_method = 'ACH' AND paid = received
      AND paid_currency = received_currency
), eligible_nodes AS MATERIALIZED (
    SELECT src AS node FROM eligible_edges
    UNION SELECT dst AS node FROM eligible_edges
), outgoing_counts AS MATERIALIZED (
    SELECT e.node, count(*) AS outgoing,
           sum(t.payment_method = 'ACH') AS outgoing_ach
    FROM eligible_nodes e
    CROSS JOIN nodes n ON n.node_id = e.node
    CROSS JOIN transactions t INDEXED BY transactions_sender
        ON t.sender_bank = n.bank AND t.sender_account = n.account
        AND t.event_time >= :window_start AND t.event_time < :cutoff
    GROUP BY e.node
), incoming_counts AS MATERIALIZED (
    SELECT e.node, count(*) AS incoming,
           sum(t.payment_method = 'ACH') AS incoming_ach
    FROM eligible_nodes e
    CROSS JOIN nodes n ON n.node_id = e.node
    CROSS JOIN transactions t INDEXED BY transactions_receiver
        ON t.receiver_bank = n.bank AND t.receiver_account = n.account
        AND t.event_time >= :window_start AND t.event_time < :cutoff
    GROUP BY e.node
)
SELECT e.*, coalesce(so.outgoing,0) AS outgoing,
       coalesce(si.incoming,0) AS incoming,
       coalesce(so.outgoing_ach,0) AS outgoing_ach,
       coalesce(si.incoming_ach,0) AS incoming_ach,
       coalesce(do.outgoing,0) AS dst_outgoing,
       coalesce(di.incoming,0) AS dst_incoming,
       coalesce(do.outgoing_ach,0) AS dst_outgoing_ach,
       coalesce(di.incoming_ach,0) AS dst_incoming_ach
FROM eligible_edges e
LEFT JOIN outgoing_counts so ON so.node = e.src
LEFT JOIN incoming_counts si ON si.node = e.src
LEFT JOIN outgoing_counts do ON do.node = e.dst
LEFT JOIN incoming_counts di ON di.node = e.dst
ORDER BY e.event_time,e.transaction_id;
