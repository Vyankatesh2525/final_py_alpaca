-- V1__extend_users_schema.sql
-- Migration: extend clau_trading_db to absorb all columns from clau_app_user_db
-- Safe to run multiple times (all statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).

-- ===========================================================================
-- 1. Extend users table with all columns from the Spring Boot User entity
-- ===========================================================================

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS full_name                  VARCHAR(100),
    ADD COLUMN IF NOT EXISTS phone_number               VARCHAR(20),
    ADD COLUMN IF NOT EXISTS reset_token                TEXT,
    ADD COLUMN IF NOT EXISTS reset_token_expiry         TIMESTAMP,
    ADD COLUMN IF NOT EXISTS token                      TEXT,
    ADD COLUMN IF NOT EXISTS kyc_status                 VARCHAR(20)  NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS subscribed                 BOOLEAN      NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ai_message_count           INTEGER      NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ai_week_start              BIGINT,
    ADD COLUMN IF NOT EXISTS learn_points               INTEGER      NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS card_points                INTEGER      NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS plaid_access_token         TEXT,
    ADD COLUMN IF NOT EXISTS is_admin                   BOOLEAN      NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stripe_customer_id         TEXT,
    ADD COLUMN IF NOT EXISTS stripe_account_ids         TEXT,
    ADD COLUMN IF NOT EXISTS stripe_balance_cache       TEXT,
    ADD COLUMN IF NOT EXISTS stripe_transactions_cache  TEXT,
    ADD COLUMN IF NOT EXISTS stripe_data_synced_at      TIMESTAMP;

-- Partial unique index on email: allow NULL but enforce uniqueness for real addresses.
-- The existing column is nullable; this replaces any full unique constraint the ORM may have added.
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_notnull
    ON users (email)
    WHERE email IS NOT NULL;

-- ===========================================================================
-- 2. user_goals — mirrors Spring Boot UserGoal entity
-- ===========================================================================

CREATE TABLE IF NOT EXISTS user_goals (
    id          VARCHAR(36)   PRIMARY KEY,
    user_id     INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(500)  NOT NULL,
    created_at  BIGINT        NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT * 1000),
    sub_tasks   TEXT          NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_user_goals_user_id ON user_goals(user_id);

-- ===========================================================================
-- 3. kyc_submissions — mirrors Spring Boot KYCSubmission entity
-- ===========================================================================

CREATE TABLE IF NOT EXISTS kyc_submissions (
    id                SERIAL        PRIMARY KEY,
    user_id           INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    full_name         VARCHAR(100)  NOT NULL,
    date_of_birth     DATE          NOT NULL,
    id_type           VARCHAR(50)   NOT NULL,
    id_number         VARCHAR(100)  NOT NULL,
    address           TEXT          NOT NULL,
    phone             VARCHAR(20)   NOT NULL,
    front_doc_url     TEXT,
    back_doc_url      TEXT,
    status            VARCHAR(20)   NOT NULL DEFAULT 'pending',
    rejection_reason  TEXT,
    submitted_at      TIMESTAMP     NOT NULL DEFAULT NOW(),
    reviewed_at       TIMESTAMP,
    reviewed_by       VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_kyc_user_id ON kyc_submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_kyc_status  ON kyc_submissions(status);
