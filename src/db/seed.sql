-- Optional, idempotent development fixtures. Existing rows and state are kept.
INSERT INTO rooms (name) VALUES ('Hall'), ('Living room')
ON CONFLICT (name) DO NOTHING;

INSERT INTO devices (room_id, name, type, state)
SELECT r.id, v.name, v.type, v.state::jsonb
FROM (VALUES
    ('Hall', 'Front door lock', 'lock', '{"locked": true}'),
    ('Hall', 'Hall light', 'light', '{"power": "off"}'),
    ('Living room', 'Lamp', 'light', '{"power": "on"}'),
    ('Living room', 'Thermostat', 'thermostat', '{"temperature_c": 20}')
) AS v(room_name, name, type, state)
JOIN rooms r ON r.name = v.room_name
ON CONFLICT (room_id, name) DO NOTHING;

INSERT INTO inventory_items (name, quantity, unit, low_stock_threshold)
VALUES ('eggs', 6, 'eggs', 2), ('milk', 1, 'carton', 1)
ON CONFLICT (name) DO NOTHING;

INSERT INTO family_members (name) VALUES ('Alex'), ('Sam')
ON CONFLICT (name) DO NOTHING;
