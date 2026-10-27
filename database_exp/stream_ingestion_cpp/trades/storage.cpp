#include "storage.hpp"
#include "support/db.hpp"

namespace trades {
void create_table(duckdb_connection connection) {
    support::execute(connection, R"SQL(
        CREATE TABLE IF NOT EXISTS team_trades (
            trade_id VARCHAR PRIMARY KEY,
            tick BIGINT NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            received_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            team_id VARCHAR NOT NULL,
            instrument_id VARCHAR NOT NULL,
            venue VARCHAR NOT NULL,
            currency VARCHAR NOT NULL,
            side VARCHAR NOT NULL CHECK (side IN ('BUY', 'SELL')),
            quantity BIGINT NOT NULL CHECK (quantity > 0),
            price_cents BIGINT NOT NULL CHECK (price_cents > 0),
            fee_cents BIGINT NOT NULL CHECK (fee_cents >= 0)
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
