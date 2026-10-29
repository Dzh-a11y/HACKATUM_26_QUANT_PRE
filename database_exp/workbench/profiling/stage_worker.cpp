#include "accounts/calculate.hpp"
#include "accounts/storage.hpp"
#include "market/storage.hpp"
#include "support/db.hpp"
#include "support/files.hpp"
#include <chrono>
#include <csignal>
#include <fstream>
#include <iostream>
#include <memory>
#include <thread>

using support::Json;
namespace {
volatile std::sig_atomic_t stopped = 0;
void stop(int) { stopped = 1; }
}

// These non-inlined boundaries identify the stage in a sampled stack.
// All actual business functions remain the original implementations.
__attribute__((noinline)) Json profile_account_value(int64_t event, const accounts::State &state,
        const Json &quotes, const accounts::Params &params) {
    return accounts::value_accounts(event, state, quotes, params);
}
__attribute__((noinline)) support::Columns profile_accounts_transform(const Json &records,
        const support::Context &context, const accounts::Params &params) {
    return accounts::records_to_columns(records, context, params);
}
__attribute__((noinline)) size_t profile_market_write(duckdb_connection connection, const support::Columns &columns) {
    return market::write_columns(connection, columns);
}

int main(int argc, char **argv) {
    if (argc != 5) { std::cerr << "profile_stage FIXTURE NEW_DIRECTORY STAGE THREADS\n"; return 2; }
    const std::filesystem::path root(argv[2]);
    try {
        std::signal(SIGTERM, stop); std::signal(SIGINT, stop);
        if (!std::filesystem::create_directory(root)) throw std::runtime_error("output already exists");
        std::ifstream file(argv[1]); Json fixture; file >> fixture;
        const auto &meta = fixture.at("metadata"), &p = meta.at("parameters"), &data = fixture.at("ticks").at(0);
        accounts::Params account_params;
        account_params.currency = p.at("accounts").at("currency");
        account_params.teams = p.at("accounts").at("teams").get<std::vector<std::string>>();
        account_params.initial_cash_cents = p.at("accounts").at("initial_cash_cents");
        market::Params market_params{p.at("market").at("venue"), p.at("market").at("currency")};
        const auto state = accounts::apply_fills(accounts::initial_state(meta.at("instruments").get<std::vector<std::string>>(), account_params), data.at("trades"));
        const auto snapshots = accounts::value_accounts(data.at("event_us"), state, data.at("market"), account_params);
        if (snapshots != data.at("accounts")) throw std::runtime_error("account result differs from fixture reference");
        const support::Context context{0, data.at("received_us"), data.at("ingested_us")};
        const auto columns = market::records_to_columns(data.at("market"), context, market_params);
        const std::string stage(argv[3]);
        if (stage != "account_value" && stage != "accounts_transform" && stage != "market_write") throw std::invalid_argument("unsupported stage");
        std::unique_ptr<support::Database> db;
        if (stage == "market_write") {
            db = std::make_unique<support::Database>((root / "market.duckdb").string(), "1GB", std::stoi(argv[4]));
            market::create_table(db->connection);
        }
        support::write_json(root / "ready.json", {{"stage", stage}, {"pid", getpid()}, {"fixture_tick", 0}});
        const auto start = std::chrono::steady_clock::now();
        uint64_t calls = 0, checksum = 0;
        while (!stopped && !std::filesystem::exists(root / "stop.flag")) {
            if (std::chrono::steady_clock::now() - start > std::chrono::seconds(45)) throw std::runtime_error("sampler watchdog expired");
            if (stage == "account_value") {
                auto result = profile_account_value(data.at("event_us"), state, data.at("market"), account_params);
                checksum += result.size();
            } else if (stage == "accounts_transform") {
                auto result = profile_accounts_transform(snapshots, context, account_params);
                checksum += result.front().size();
            } else {
                support::execute(db->connection, "BEGIN TRANSACTION");
                checksum += profile_market_write(db->connection, columns);
                // Keep storage bounded; transaction setup/rollback are outside the sampled marker.
                support::execute(db->connection, "ROLLBACK");
            }
            ++calls;
        }
        if (db && support::scalar(db->connection, "SELECT count(*) FROM market_quotes") != 0) throw std::runtime_error("profile transaction did not roll back");
        support::write_json(root / "worker.json", {{"stage", stage}, {"calls", calls}, {"checksum", checksum},
            {"elapsed_ms", std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()},
            {"fixture_tick",0}, {"account_reference_verified",true}, {"rows_per_call",stage=="market_write"?data.at("market").size():snapshots.size()}});
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
