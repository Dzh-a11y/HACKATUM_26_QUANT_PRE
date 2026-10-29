#include "probe.hpp"
#include "pipeline.hpp"
#include "accounts/calculate.hpp"
#include "accounts/storage.hpp"
#include "market/storage.hpp"
#include "trades/storage.hpp"
#include "news/parser.hpp"
#include "support/db.hpp"
#include "support/files.hpp"
#include "support/time.hpp"
#include <iostream>
#include <memory>
#include <thread>

// This adapter adds observation boundaries; all transformations, calculations,
// table definitions, Appender writes and archive publication call existing code.
namespace {
volatile std::sig_atomic_t stopped = 0;
void stop(int) { stopped = 1; }
Settings settings_from(const support::Json &info) {
    const auto &p = info.at("parameters");
    Settings s;
    s.market = {p.at("market").at("venue"), p.at("market").at("currency")};
    s.trades = {p.at("trades").at("venue"), p.at("trades").at("currency")};
    s.accounts.currency = p.at("accounts").at("currency");
    s.accounts.teams = p.at("accounts").at("teams").get<std::vector<std::string>>();
    s.accounts.initial_cash_cents = p.at("accounts").at("initial_cash_cents");
    s.news.known_symbols = p.at("news").at("known_symbols").get<std::vector<std::string>>();
    s.news.symbols_field = p.at("news").at("symbols_field");
    s.news.source = p.at("news").at("source");
    s.news.fsync = p.at("news").at("fsync");
    return s;
}
}
int main(int argc, char **argv) {
    using support::Json;
    if (argc != 6) { std::cerr << "observe_cpp INPUT NEW_OUTPUT THREADS MEMORY fast|realtime\n"; return 2; }
    const std::filesystem::path output(argv[2]);
    if (std::filesystem::exists(output)) { std::cerr << "refusing to overwrite output\n"; return 2; }
    std::filesystem::create_directories(output / "parquet");
    observer::Trace trace(output / "trace.jsonl");
    Json info = {{"status", "starting"}};
    try {
        std::signal(SIGINT, stop); std::signal(SIGTERM, stop);
        const int threads = std::stoi(argv[3]);
        const bool realtime = std::string(argv[5]) == "realtime";
        auto fixture = trace.measure("input_decode", 0, [&] {
            std::ifstream input(argv[1]);
            Json data; input >> data;
            if (data.at("format_version") != 1) throw std::invalid_argument("fixture version");
            return data;
        });
        info = fixture.at("metadata");
        const auto settings = settings_from(info);
        const int64_t step = info.at("tick_seconds"), period = info.at("export_interval_seconds");
        const int64_t total_ticks = fixture.at("ticks").size();
        if (threads < 1 || step < 1 || period < 1 || period % step) throw std::invalid_argument("invalid configuration");
        const auto simulation_us = support::parse_time(info.at("simulation_start")).micros;
        auto state = accounts::initial_state(info.at("instruments").get<std::vector<std::string>>(), settings.accounts);
        info.update({{"status", "running"}, {"implementation", "cpp-existing-modules-observed"},
            {"mode", realtime ? "paced-fixture" : "accelerated"}, {"committed_ticks", 0}, {"committed_seconds", 0},
            {"batches", Json::array()}, {"news_records", 0}, {"duckdb_version", duckdb_library_version()},
            {"runtime", {{"threads", threads}, {"memory_limit", argv[4]}}}});
        support::write_bytes(output / "news.jsonl", "", false, false);
        support::write_json(output / "run.json", info);
        auto database = trace.measure("db_init", 0, [&] {
            auto db = std::make_unique<support::Database>((output / "market.duckdb").string(), argv[4], threads);
            pipeline::create_tables(db->connection); return db;
        });
        auto connection = database->connection;
        info["source_id"] = support::text_scalar(connection, "SELECT source_id FROM pragma_version()");
        const auto timer = observer::Clock::now();
        int64_t next_export = 0;
        for (const auto &data : fixture.at("ticks")) {
            if (stopped) break;
            const int64_t tick = data.at("tick"); trace.tick = tick;
            // Preserve fixture timestamps in both pacing modes, to support exact comparison.
            const support::Context context{tick, data.at("received_us"), data.at("ingested_us")};
            auto next = trace.measure("account_fills", data.at("trades").size(), [&] { return accounts::apply_fills(state, data.at("trades")); });
            auto snapshots = trace.measure("account_value", settings.accounts.teams.size(), [&] { return accounts::value_accounts(data.at("event_us"), next, data.at("market"), settings.accounts); });
            const auto news_count = data.at("news").size();
            auto bytes = trace.measure("news_parse", news_count, [&] {
                std::string bytes;
                for (const auto &raw : data.at("news")) bytes += news::parse_record(raw.get<std::string>(), context, settings.news).dump() + '\n';
                return bytes;
            });
            trace.measure("news_write", news_count, [&] { if (news_count) support::write_bytes(output / "news.jsonl", bytes, true, settings.news.fsync); });
            info["news_records"] = info["news_records"].get<size_t>() + news_count;
            trace.measure("txn_begin", 0, [&] { support::execute(connection, "BEGIN TRANSACTION"); });
            try {
                auto quotes = trace.measure("market_transform", data.at("market").size(), [&] { return market::records_to_columns(data.at("market"), context, settings.market); });
                trace.measure("market_write", data.at("market").size(), [&] { market::write_columns(connection, quotes); });
                auto trade_columns = trace.measure("trades_transform", data.at("trades").size(), [&] { return trades::records_to_columns(data.at("trades"), context, settings.trades); });
                trace.measure("trades_write", data.at("trades").size(), [&] { trades::write_columns(connection, trade_columns); });
                auto account_columns = trace.measure("accounts_transform", snapshots.size(), [&] { return accounts::records_to_columns(snapshots, context, settings.accounts); });
                trace.measure("accounts_write", snapshots.size(), [&] { accounts::write_columns(connection, account_columns); });
                trace.measure("txn_commit", 0, [&] { support::execute(connection, "COMMIT"); });
            } catch (...) {
                trace.measure("txn_rollback", 0, [&] { support::execute(connection, "ROLLBACK"); }); throw;
            }
            trace.measure("state_advance", 0, [&] { state = std::move(next); });
            info["committed_ticks"] = tick + 1; info["committed_seconds"] = (tick + 1) * step;
            trace.emit({{"kind", "commit"}, {"committed_ticks", tick + 1}, {"total_ticks", total_ticks}});
            if (realtime) trace.measure("pace_wait", 0, [&] {
                const auto deadline = timer + std::chrono::seconds((tick + 1) * step);
                while (!stopped && observer::Clock::now() < deadline)
                    std::this_thread::sleep_until(std::min(deadline, observer::Clock::now() + std::chrono::milliseconds(25)));
            });
            if ((tick + 1) * step % period == 0) {
                info["batches"].push_back(trace.measure("parquet_export", 0, [&] { return pipeline::export_batch(connection, output / "parquet", next_export, tick + 1, simulation_us, step, period); }));
                next_export = tick + 1;
            }
            support::write_json(output / "run.json", info);
        }
        const int64_t committed = info.at("committed_ticks");
        if (committed > next_export)
            info["batches"].push_back(trace.measure("parquet_export", 0, [&] { return pipeline::export_batch(connection, output / "parquet", next_export, committed, simulation_us, step, period); }));
        info["rows"] = {{market::table_name, support::scalar(connection, "SELECT count(*) FROM market_quotes")},
            {trades::table_name, support::scalar(connection, "SELECT count(*) FROM team_trades")},
            {accounts::table_name, support::scalar(connection, "SELECT count(*) FROM account_snapshots")}};
        trace.measure("db_close", 0, [&] { database.reset(); });
        info["status"] = committed == total_ticks ? "completed" : "stopped";
        support::write_json(output / "run.json", info);
        trace.emit({{"kind", "done"}, {"status", info["status"]}});
        return 0;
    } catch (const std::exception &error) {
        info.update({{"status", "failed"}, {"error", error.what()}});
        support::write_json(output / "run.json", info);
        std::cerr << error.what() << '\n'; return 1;
    }
}
