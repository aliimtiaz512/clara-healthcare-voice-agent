-- Clara – Avery Wellness Clinic
-- Run once against the clara_clinic database to initialise the schema and seed data.
-- psql -U postgres -d clara_clinic -f schema.sql

-- ============================================================
-- Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS doctors (
    id        SERIAL       PRIMARY KEY,
    name      VARCHAR(100) NOT NULL UNIQUE,
    specialty VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS availability (
    id        SERIAL      PRIMARY KEY,
    doctor_id INT         NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    slot_time VARCHAR(50) NOT NULL,
    is_booked BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS appointments (
    id               SERIAL       PRIMARY KEY,
    appointment_code VARCHAR(20)  NOT NULL UNIQUE,
    patient_name     VARCHAR(150) NOT NULL,
    doctor_id        INT          NOT NULL REFERENCES doctors(id),
    slot_time        VARCHAR(50)  NOT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index to speed up the availability look-up query in check_availability()
CREATE INDEX IF NOT EXISTS idx_availability_doctor_booked
    ON availability (doctor_id, is_booked);

CREATE TABLE IF NOT EXISTS agent_logs (
    id         SERIAL       PRIMARY KEY,
    level      VARCHAR(20)  NOT NULL DEFAULT 'INFO',
    tool       VARCHAR(100),
    message    TEXT         NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- DESC index so the SSE poller "WHERE id > $last" scans newest rows first
CREATE INDEX IF NOT EXISTS idx_agent_logs_id_desc
    ON agent_logs (id DESC);

-- ============================================================
-- Seed data — representative clinic roster
-- ============================================================

INSERT INTO doctors (name, specialty) VALUES
    ('Dr. Davis',   'cardiology'),
    ('Dr. Patel',   'dermatology'),
    ('Dr. Chen',    'general practice'),
    ('Dr. Nguyen',  'orthopedics'),
    ('Dr. Okafor',  'neurology')
ON CONFLICT (name) DO NOTHING;

-- Seed open timeslots (all unbooked by default)
INSERT INTO availability (doctor_id, slot_time, is_booked)
SELECT d.id, s.slot_time, FALSE
FROM   doctors d
CROSS JOIN (VALUES
    ('09:00 AM'),
    ('10:30 AM'),
    ('01:00 PM'),
    ('02:30 PM'),
    ('04:00 PM')
) AS s(slot_time)
ON CONFLICT DO NOTHING;
