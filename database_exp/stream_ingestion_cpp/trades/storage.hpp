#pragma once
#include <duckdb.h>
#include <filesystem>
#include "transform.hpp"

namespace trades {
inline constexpr const char *table_name = "team_trades";
void create_table(duckdb_connection connection);
size_t write_columns(duckdb_connection connection, const support::Columns &columns);
size_t write_records(duckdb_connection connection, const support::Json &records, const support::Context &context, const Params &params);
size_t export_parquet(duckdb_connection connection, const std::filesystem::path &path, int64_t start_tick, int64_t end_tick);
}
