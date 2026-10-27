#include "pipeline.hpp"
#include "market/storage.hpp"
#include "trades/storage.hpp"
#include "accounts/storage.hpp"
#include "accounts/calculate.hpp"
#include "news/writer.hpp"
#include "support/db.hpp"
#include "support/files.hpp"
#include "support/time.hpp"
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <thread>

namespace pipeline {
using support::Json;
using Clock = std::chrono::steady_clock;
namespace {
double ms(Clock::time_point start) { return std::chrono::duration<double, std::milli>(Clock::now() - start).count(); }
Settings read_settings(const Json &info) {
    const auto &parameters = info.at("parameters");
    Settings result;
    result.market = {parameters.at("market").at("venue"), parameters.at("market").at("currency")};
    result.trades = {parameters.at("trades").at("venue"), parameters.at("trades").at("currency")};
    result.accounts.currency = parameters.at("accounts").at("currency");
    result.accounts.teams = parameters.at("accounts").at("teams").get<std::vector<std::string>>();
    result.accounts.initial_cash_cents = parameters.at("accounts").at("initial_cash_cents");
    result.news.known_symbols = parameters.at("news").at("known_symbols").get<std::vector<std::string>>();
    result.news.symbols_field = parameters.at("news").at("symbols_field");
    result.news.source = parameters.at("news").at("source");
    result.news.fsync = parameters.at("news").at("fsync");
    return result;
}
}
void create_tables(duckdb_connection connection) {
    market::create_table(connection); trades::create_table(connection); accounts::create_table(connection);
}
void write_tick(duckdb_connection connection, const Json &quotes, const Json &fills, const Json &snapshots,
                const support::Context &context, const Settings &settings) {
    support::execute(connection, "BEGIN TRANSACTION");
    try {
        market::write_records(connection, quotes, context, settings.market);
        trades::write_records(connection, fills, context, settings.trades);
        accounts::write_records(connection, snapshots, context, settings.accounts);
        support::execute(connection, "COMMIT");
    } catch (...) { support::execute(connection, "ROLLBACK"); throw; }
}
std::string export_batch(duckdb_connection connection, const std::filesystem::path &root,
                         int64_t start_tick, int64_t end_tick, int64_t simulation_us, int64_t step, int64_t period) {
    std::ostringstream label;
    label << "batch_" << std::setfill('0') << std::setw(6) << start_tick << '_' << std::setw(6) << end_tick;
    const auto name = label.str();
    const auto destination = root / name, staging = root / ("." + name + ".tmp");
    if (std::filesystem::exists(destination) || !std::filesystem::create_directory(staging))
        throw std::runtime_error("archive already exists: " + name);
    bool active = false;
    try {
        support::execute(connection, "BEGIN TRANSACTION"); active = true;
        Json rows = {
            {market::table_name, market::export_parquet(connection, staging / "market_quotes.parquet", start_tick, end_tick)},
            {trades::table_name, trades::export_parquet(connection, staging / "team_trades.parquet", start_tick, end_tick)},
            {accounts::table_name, accounts::export_parquet(connection, staging / "account_snapshots.parquet", start_tick, end_tick)},
        };
        support::execute(connection, "COMMIT"); active = false;
        support::write_json(staging / "manifest.json", {
            {"start_tick", start_tick}, {"end_tick_exclusive", end_tick},
            {"start_time", support::iso_time(simulation_us + start_tick * step * 1'000'000)},
            {"end_time_exclusive", support::iso_time(simulation_us + end_tick * step * 1'000'000)},
            {"complete_interval", (end_tick - start_tick) * step == period}, {"rows", rows},
        });
        std::filesystem::rename(staging, destination);
        return name;
    } catch (...) {
        if (active) support::execute(connection, "ROLLBACK");
        std::filesystem::remove_all(staging); throw;
    }
}
void run(const std::filesystem::path &input, const std::filesystem::path &output,
         const RuntimeParams &runtime, const volatile std::sig_atomic_t &stop) {
    const auto total_start = Clock::now(), input_start = Clock::now();
    std::ifstream file(input);
    if (!file) throw std::runtime_error("cannot read input: " + input.string());
    Json fixture; file >> fixture;
    if (fixture.at("format_version") != 1) throw std::invalid_argument("unsupported fixture version");
    Json info = fixture.at("metadata");
    const auto settings = read_settings(info);
    const auto step = info.at("tick_seconds").get<int64_t>();
    const auto period = runtime.export_every ? runtime.export_every : info.at("export_interval_seconds").get<int64_t>();
    const auto seconds = runtime.seconds ? runtime.seconds : info.at("requested_seconds").get<int64_t>();
    if (step < 1 || period < 1 || seconds < 1 || period % step || seconds % step ||
        seconds / step > static_cast<int64_t>(fixture.at("ticks").size()) || runtime.threads < 1)
        throw std::invalid_argument("invalid duration/interval or insufficient fixture ticks");
    const int64_t ticks = seconds / step;
    const auto simulation_us = support::parse_time(info.at("simulation_start")).micros;
    auto state = accounts::initial_state(info.at("instruments").get<std::vector<std::string>>(), settings.accounts);
    Json metrics = {{"input_decode_ms", ms(input_start)}, {"calculate_ms", 0.0}, {"write_ms", 0.0},
                    {"news_ms", 0.0}, {"export_ms", 0.0}, {"wait_ms", 0.0}, {"write_samples_ms", Json::array()}};
    if (std::filesystem::exists(output)) throw std::runtime_error("refusing to overwrite output directory");
    std::filesystem::create_directories(output / "parquet");
    support::write_bytes(output / "news.jsonl", "", false, false);
    info.update({{"status", "running"}, {"mode", runtime.fast ? "accelerated" : "realtime"},
                 {"implementation", "cpp-c-api-datachunk"}, {"requested_seconds", seconds},
                 {"export_interval_seconds", period}, {"committed_ticks", 0}, {"committed_seconds", 0},
                 {"batches", Json::array()}, {"news_records", 0}, {"duckdb_version", duckdb_library_version()},
                 {"runtime", {{"threads", runtime.threads}, {"memory_limit", runtime.memory_limit}}}});
    std::cout << "RUN_DIR=" << std::filesystem::absolute(output).string() << std::endl;
    support::write_json(output / "run.json", info);
    try {
        auto database = std::make_unique<support::Database>((output / "market.duckdb").string(), runtime.memory_limit, runtime.threads);
        auto connection = database->connection;
        create_tables(connection);
        info["source_id"] = support::text_scalar(connection, "SELECT source_id FROM pragma_version()");
        const auto timer_start = Clock::now();
        int64_t next_export = 0;
        for (int64_t tick = 0; tick < ticks && !stop; ++tick) {
            const auto &data = fixture.at("ticks").at(static_cast<size_t>(tick));
            int64_t ingested = data.at("ingested_us");
            if (!runtime.fast) ingested = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
            const support::Context context{tick, data.at("received_us"), ingested};
            auto start = Clock::now();
            auto next = accounts::apply_fills(state, data.at("trades"));
            const auto snapshots = accounts::value_accounts(data.at("event_us"), next, data.at("market"), settings.accounts);
            metrics["calculate_ms"] = metrics["calculate_ms"].get<double>() + ms(start);
            start = Clock::now();
            info["news_records"] = info["news_records"].get<size_t>() + news::write_records(output / "news.jsonl", data.at("news"), context, settings.news);
            metrics["news_ms"] = metrics["news_ms"].get<double>() + ms(start);
            start = Clock::now();
            write_tick(connection, data.at("market"), data.at("trades"), snapshots, context, settings);
            const auto write_time = ms(start);
            metrics["write_ms"] = metrics["write_ms"].get<double>() + write_time;
            metrics["write_samples_ms"].push_back(write_time);
            state = std::move(next); // Advance only after COMMIT succeeds.
            info["committed_ticks"] = tick + 1; info["committed_seconds"] = (tick + 1) * step;
            if (tick == 0) std::cout << "COMMIT tick=0" << std::endl;
            if (!runtime.fast) {
                start = Clock::now();
                const auto deadline = timer_start + std::chrono::seconds{(tick + 1) * step};
                while (!stop && Clock::now() < deadline) std::this_thread::sleep_until(std::min(deadline, Clock::now() + std::chrono::milliseconds{25}));
                metrics["wait_ms"] = metrics["wait_ms"].get<double>() + ms(start);
            }
            if ((tick + 1) * step % period == 0) {
                start = Clock::now();
                info["batches"].push_back(export_batch(connection, output / "parquet", next_export, tick + 1, simulation_us, step, period));
                metrics["export_ms"] = metrics["export_ms"].get<double>() + ms(start);
                next_export = tick + 1;
                support::write_json(output / "run.json", info);
            }
        }
        const int64_t committed = info.at("committed_ticks");
        if (committed > next_export) {
            const auto start = Clock::now();
            info["batches"].push_back(export_batch(connection, output / "parquet", next_export, committed, simulation_us, step, period));
            metrics["export_ms"] = metrics["export_ms"].get<double>() + ms(start);
        }
        info["rows"] = {
            {market::table_name, support::scalar(connection, "SELECT count(*) FROM market_quotes")},
            {trades::table_name, support::scalar(connection, "SELECT count(*) FROM team_trades")},
            {accounts::table_name, support::scalar(connection, "SELECT count(*) FROM account_snapshots")},
        };
        info["status"] = committed == ticks ? "completed" : "stopped";
        const auto close_start = Clock::now();
        database.reset();
        metrics["close_ms"] = ms(close_start);
    } catch (const std::exception &error) {
        info.update({{"status", "failed"}, {"error", error.what()}, {"metrics", metrics}});
        support::write_json(output / "run.json", info); throw;
    }
    metrics["total_active_ms"] = ms(total_start) - metrics["wait_ms"].get<double>();
    info["metrics"] = metrics;
    support::write_json(output / "run.json", info);
    std::cout << "DONE " << info.at("status").get<std::string>() << " " << info.at("rows").dump() << std::endl;
}
}
