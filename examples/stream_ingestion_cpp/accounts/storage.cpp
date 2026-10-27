#include "storage.hpp"
#include "support/db.hpp"

namespace accounts {
void create_table(duckdb_connection connection) {
    support::execute(connection, R"SQL(
        CREATE TABLE IF NOT EXISTS account_snapshots (
            tick BIGINT NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            received_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            team_id VARCHAR NOT NULL,
            currency VARCHAR NOT NULL,
            cash_cents BIGINT NOT NULL,
            positions JSON NOT NULL,
            equity_cents BIGINT NOT NULL,
            pnl_cents BIGINT NOT NULL,
            PRIMARY KEY (tick, team_id)
        )
    )SQL");
}
size_t write_columns(duckdb_connection connection, const support::Columns &columns) {
    return support::append_columns(connection, table_name, columns);
}
size_t write_records(duckdb_connection connection, const support::Json &records, const support::Context &context, const Params &params) {
    return write_columns(connection, records_to_columns(records, context, params));
}
size_t export_parquet(duckdb_connection connection, const std::filesystem::path &path, int64_t start_tick, int64_t end_tick) {
    return support::export_table(connection, table_name, path, start_tick, end_tick);
}
}
