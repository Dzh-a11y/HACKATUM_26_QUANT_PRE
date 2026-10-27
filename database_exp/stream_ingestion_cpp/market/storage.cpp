#include "storage.hpp"
#include "support/db.hpp"

namespace market {
void create_table(duckdb_connection connection) {
    support::execute(connection, R"SQL(
        CREATE TABLE IF NOT EXISTS market_quotes (
            tick BIGINT NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            received_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            instrument_id VARCHAR NOT NULL,
            venue VARCHAR NOT NULL,
            currency VARCHAR NOT NULL,
            bid_cents BIGINT NOT NULL CHECK (bid_cents > 0),
            ask_cents BIGINT NOT NULL CHECK (ask_cents >= bid_cents),
            bid_size BIGINT NOT NULL CHECK (bid_size > 0),
            ask_size BIGINT NOT NULL CHECK (ask_size > 0),
            PRIMARY KEY (tick, instrument_id, venue)
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
