#pragma once
#include <csignal>
#include <filesystem>
#include "settings.hpp"
#include "support/types.hpp"
#include <duckdb.h>
namespace pipeline {
void create_tables(duckdb_connection connection);
void write_tick(duckdb_connection connection, const support::Json &quotes, const support::Json &fills,
                const support::Json &snapshots, const support::Context &context, const Settings &settings);
std::string export_batch(duckdb_connection connection, const std::filesystem::path &root,
                         int64_t start_tick, int64_t end_tick, int64_t simulation_us, int64_t step, int64_t period);
void run(const std::filesystem::path &input, const std::filesystem::path &output,
         const RuntimeParams &runtime, const volatile std::sig_atomic_t &stop);
}
