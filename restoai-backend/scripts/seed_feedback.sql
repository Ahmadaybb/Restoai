-- Seed mock feedback for UI testing
-- Run with: docker compose exec db psql -U restoai -d restoai -f /dev/stdin < scripts/seed_feedback.sql

-- Mock customers
INSERT INTO customers (id, display_name, phone_e164, created_at, last_seen_at)
VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', 'Layla Hassan',  '+96170111001', now(), now()),
  ('aaaaaaaa-0000-0000-0000-000000000002', 'Omar Khalil',   '+96170111002', now(), now()),
  ('aaaaaaaa-0000-0000-0000-000000000003', 'Sara Mansour',  '+96170111003', now(), now()),
  ('aaaaaaaa-0000-0000-0000-000000000004', 'Karim Abboud',  '+96170111004', now(), now()),
  ('aaaaaaaa-0000-0000-0000-000000000005', 'Nadia Frem',    '+96170111005', now(), now())
ON CONFLICT (id) DO NOTHING;

-- Mock orders
INSERT INTO orders (id, customer_id, items_snapshot, fulfillment, language, transcript_url, estimated_total_usd, flags, state, created_at)
VALUES
  ('bbbbbbbb-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', '[{"menu_item_id":"hummus","quantity":2,"customizations":[]}]', 'delivery', 'en', '/api/transcripts/mock', 15.00, '[]', 'out_for_delivery', now() - interval '48 hours'),
  ('bbbbbbbb-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000002', '[{"menu_item_id":"fattoush","quantity":1,"customizations":[]}]', 'pickup',   'en', '/api/transcripts/mock', 6.00,  '[]', 'out_for_delivery', now() - interval '36 hours'),
  ('bbbbbbbb-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000003', '[{"menu_item_id":"shawarma","quantity":3,"customizations":[]}]', 'delivery', 'ar_lb', '/api/transcripts/mock', 21.00, '[]', 'out_for_delivery', now() - interval '24 hours'),
  ('bbbbbbbb-0000-0000-0000-000000000004', 'aaaaaaaa-0000-0000-0000-000000000004', '[{"menu_item_id":"hummus","quantity":1,"customizations":[]}]', 'delivery', 'en', '/api/transcripts/mock', 5.00,  '[]', 'out_for_delivery', now() - interval '12 hours'),
  ('bbbbbbbb-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000005', '[{"menu_item_id":"tabbouleh","quantity":2,"customizations":[]}]', 'pickup', 'en', '/api/transcripts/mock', 10.00, '[]', 'out_for_delivery', now() - interval '2 hours')
ON CONFLICT (id) DO NOTHING;

-- Mock feedback
INSERT INTO order_feedback (id, order_id, customer_id, star_rating, comment, sentiment, status, feedback_requested_at, responded_at, created_at)
VALUES
  (gen_random_uuid(), 'bbbbbbbb-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 5, 'Everything was perfect! The hummus was amazing and delivery was fast.', 'good',    'received',    now() - interval '46 hours', now() - interval '45 hours', now() - interval '46 hours'),
  (gen_random_uuid(), 'bbbbbbbb-0000-0000-0000-000000000002', 'aaaaaaaa-0000-0000-0000-000000000002', 2, 'Order was late and the fattoush was soggy. Disappointed.',             'bad',     'received',    now() - interval '34 hours', now() - interval '33 hours', now() - interval '34 hours'),
  (gen_random_uuid(), 'bbbbbbbb-0000-0000-0000-000000000003', 'aaaaaaaa-0000-0000-0000-000000000003', 3, 'Food was okay, nothing special.',                                     'neutral', 'received',    now() - interval '22 hours', now() - interval '21 hours', now() - interval '22 hours'),
  (gen_random_uuid(), 'bbbbbbbb-0000-0000-0000-000000000004', 'aaaaaaaa-0000-0000-0000-000000000004', NULL, NULL,                                                               NULL,      'no_response', now() - interval '10 hours', NULL,                         now() - interval '10 hours'),
  (gen_random_uuid(), 'bbbbbbbb-0000-0000-0000-000000000005', 'aaaaaaaa-0000-0000-0000-000000000005', NULL, NULL,                                                               NULL,      'pending',     now() - interval '1 hour',  NULL,                         now() - interval '1 hour')
ON CONFLICT (order_id) DO NOTHING;

SELECT status, count(*) FROM order_feedback GROUP BY status;
