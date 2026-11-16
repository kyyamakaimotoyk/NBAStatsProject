-- ============================================================================
-- gravity_leaders_daily - daily snapshot of nba_api GravityLeaders (added 2026-11-16)
-- ============================================================================
--
-- GravityLeaders returns SEASON-TO-DATE totals per player and has no date
-- filter, so past values cannot be rebuilt later. The home ingest saves one
-- snapshot per day (data_engineering/gravity_snapshot.py). A pre-game feature
-- for a game on date D may only use snapshot_date <= D. The ingest runs around
-- 2:30 AM ET, so a snapshot covers games played before snapshot_date (ET).
--
-- Data exists from 2025-26 on (2024-25 returns nothing). Local MySQL only for
-- now; RDS gets it when a model uses it.
--
-- Usage (Kai runs it once):
--   mysql -u <your_user> -p nba_data < sql/create_gravity_leaders_daily.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS gravity_leaders_daily (
    snapshot_date DATE        NOT NULL COMMENT 'US Eastern date the snapshot was taken',
    season        VARCHAR(7)  NOT NULL COMMENT 'e.g. 2026-27',
    season_type   VARCHAR(20) NOT NULL COMMENT 'Regular Season | Playoffs | PlayIn',
    fetched_at_utc DATETIME   NOT NULL,

    PLAYERID          BIGINT       NOT NULL,
    FIRSTNAME         VARCHAR(64),
    LASTNAME          VARCHAR(64),
    TEAMID            BIGINT,
    TEAMABBREVIATION  VARCHAR(8),
    TEAMNAME          VARCHAR(64),
    TEAMCITY          VARCHAR(64),

    FRAMES                           DOUBLE,
    GRAVITYSCORE                     DOUBLE,
    AVGGRAVITYSCORE                  DOUBLE,
    ONBALLPERIMETERFRAMES            DOUBLE,
    ONBALLPERIMETERGRAVITYSCORE      DOUBLE,
    AVGONBALLPERIMETERGRAVITYSCORE   DOUBLE,
    OFFBALLPERIMETERFRAMES           DOUBLE,
    OFFBALLPERIMETERGRAVITYSCORE     DOUBLE,
    AVGOFFBALLPERIMETERGRAVITYSCORE  DOUBLE,
    ONBALLINTERIORFRAMES             DOUBLE,
    ONBALLINTERIORGRAVITYSCORE       DOUBLE,
    AVGONBALLINTERIORGRAVITYSCORE    DOUBLE,
    OFFBALLINTERIORFRAMES            DOUBLE,
    OFFBALLINTERIORGRAVITYSCORE      DOUBLE,
    AVGOFFBALLINTERIORGRAVITYSCORE   DOUBLE,
    GAMESPLAYED                      INT,
    MINUTES                          DOUBLE,
    PTS                              DOUBLE,
    REB                              DOUBLE,
    AST                              DOUBLE,

    PRIMARY KEY (snapshot_date, season_type, PLAYERID),
    KEY idx_gravity_player (PLAYERID, snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
