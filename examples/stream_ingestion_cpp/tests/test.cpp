#include "pipeline.hpp"
#include "market/storage.hpp"
#include "trades/storage.hpp"
#include "accounts/storage.hpp"
#include "accounts/calculate.hpp"
#include "news/parser.hpp"
#include "support/db.hpp"
#include "support/time.hpp"
#include <iostream>
#include <functional>
#include <unistd.h>

using support::Json;
void require(bool condition, const char *message) { if (!condition) throw std::runtime_error(message); }
void fails(const std::function<void()> &function) {
    bool failed = false;
    try { function(); } catch (const std::exception &) { failed = true; }
    require(failed, "expected rejection");
}
int main() {
    try {
        support::Database db(":memory:");
        pipeline::create_tables(db.connection);
        Settings settings;
        support::Context context{0, 100, 200};
        Json quotes = Json::array({{{"event_time", 0}, {"instrument_id", "ALPHA"}, {"bid_cents", 100}, {"ask_cents", 102}, {"bid_size", 10}, {"ask_size", 20}}});
        Json fills = Json::array({{{"trade_id", "t1"}, {"event_time", 0}, {"team_id", "TEAM_A"}, {"instrument_id", "ALPHA"}, {"side", "BUY"}, {"quantity", 3}, {"price_cents", 102}, {"fee_cents", 1}}});
        auto state = accounts::initial_state({"ALPHA"}, settings.accounts);
        const auto original = state;
        const auto raw = quotes;
        auto next = accounts::apply_fills(state, fills);
        auto snapshots = accounts::value_accounts(0, next, quotes, settings.accounts);
        require(state == original && quotes == raw, "pure inputs changed");
        require(next == accounts::apply_fills(state, fills), "pure function not repeatable");
        require(snapshots[0]["pnl_cents"] == -4, "valuation incorrect");
        snapshots[0]["cash_cents"] = nullptr;
        fails([&] { pipeline::write_tick(db.connection, quotes, fills, snapshots, context, settings); });
        require(support::scalar(db.connection, "SELECT count(*) FROM market_quotes") == 0, "quote rollback failed");
        require(support::scalar(db.connection, "SELECT count(*) FROM team_trades") == 0, "trade rollback failed");
        snapshots = accounts::value_accounts(0, next, quotes, settings.accounts);
        pipeline::write_tick(db.connection, quotes, fills, snapshots, context, settings);
        require(support::text_scalar(db.connection, "SELECT json_type(positions) FROM account_snapshots LIMIT 1") == "OBJECT", "JSON became a string");
        context.tick = 1;
        fails([&] { pipeline::write_tick(db.connection, quotes, fills, snapshots, context, settings); });
        require(support::scalar(db.connection, "SELECT count(*) FROM market_quotes") == 1, "duplicate rollback failed");
        auto repeat = fills;
        repeat.push_back(fills[0]); repeat[1]["quantity"] = 2;
        next = accounts::apply_fills(state, repeat);
        require(next.positions[0] == 5 && next.cash[0] == settings.accounts.initial_cash_cents - 512, "repeated indices lost");
        repeat[0]["quantity"] = INT64_MAX;
        fails([&] { accounts::apply_fills(state, repeat); });
        require(state == original, "failed calculation mutated input");
        repeat[0]["quantity"] = 1; repeat[0]["side"] = "INVALID";
        fails([&] { accounts::apply_fills(state, repeat); });
        next.positions[0] = 999;
        require(state.positions[0] == 0, "returned state aliases input");
        // More rows than a DuckDB DataChunk, including values above float64's exact integer range.
        Json large = Json::array();
        for (int64_t i = 0; i < 5000; ++i) {
            auto row = quotes[0]; row["instrument_id"] = "S" + std::to_string(i);
            row["bid_cents"] = (int64_t(1) << 53) + i;
            row["ask_cents"] = (int64_t(1) << 53) + i + 2;
            large.push_back(std::move(row));
        }
        support::execute(db.connection, "BEGIN");
        market::write_records(db.connection, large, context, settings.market);
        support::execute(db.connection, "COMMIT");
        require(support::scalar(db.connection, "SELECT bid_cents FROM market_quotes WHERE instrument_id='S4999'") == (int64_t(1) << 53) + 4999, "integer precision lost");
        require(support::scalar(db.connection, "SELECT count(*) FROM market_quotes") == 5001, "chunk boundary dropped rows");
        auto bad_columns = market::records_to_columns(quotes, context, settings.market);
        bad_columns[0].values = std::vector<std::string>{"not-an-integer-buffer"};
        fails([&] { market::write_columns(db.connection, bad_columns); });
        char folder[] = "/tmp/hacktum-cpp-test-XXXXXX";
        if (!::mkdtemp(folder)) throw std::runtime_error("mkdtemp failed");
        const std::filesystem::path root(folder);
        try {
            const auto name = pipeline::export_batch(db.connection, root, 1, 2, 0, 1, 300);
            require(support::scalar(db.connection, "SELECT count(*) FROM read_parquet(" + support::quote((root / name / "market_quotes.parquet").string()) + ")") == 5000, "export range wrong");
            require(support::scalar(db.connection, "SELECT count(*) FROM read_parquet(" + support::quote((root / name / "team_trades.parquet").string()) + ")") == 0, "empty trade export wrong");
            fails([&] { pipeline::export_batch(db.connection, root, 1, 2, 0, 1, 300); });
            support::execute(db.connection, "DROP TABLE account_snapshots");
            fails([&] { pipeline::export_batch(db.connection, root, 0, 1, 0, 1, 300); });
            require(!std::filesystem::exists(root / "batch_000000_000001") && !std::filesystem::exists(root / ".batch_000000_000001.tmp"), "partial archive published");
            require(support::scalar(db.connection, "SELECT count(*) FROM market_quotes") == 5001, "failed export removed source rows");
        } catch (...) { std::filesystem::remove_all(root); throw; }
        std::filesystem::remove_all(root);
        const auto stamp = support::parse_time("2026-10-26T17:00:00.123456+08:00");
        require(support::iso_time(stamp.micros) == "2026-10-26T09:00:00.123456+00:00", "UTC conversion failed");
        require(support::iso_time(-1) == "1969-12-31T23:59:59.999999+00:00", "negative epoch failed");
        fails([] { support::parse_time("2026-10-26T09:00:00"); });
        fails([] { support::parse_time("2026-02-30T09:00:00Z"); });
        const std::vector<std::pair<std::string, std::string>> cases = {
            {"  SyMbOlS : ALPHA, BETA, ALPHA\r\n", "ok"}, {"Symbols: \n", "empty"},
            {"Symbols: ALPHA,\n", "malformed"}, {"Symbols: ALPHA\nSymbols: BETA\n", "malformed"},
            {"Symbols: ALPHA BETA\n", "malformed"}, {"Symbols: ALPHA, UNKNOWN\n", "unknown_symbols"}, {"", "missing"},
        };
        for (const auto &[header, status] : cases) {
            const std::string text = "News-ID: n1\nPublished-At: 2026-10-26T09:00:00Z\nTitle: 中文\n" + header + "Body: 第一行\nSymbols: BETA\n";
            const auto record = news::parse_record(text, context, settings.news);
            require(record["symbol_status"] == status && record["raw_text"] == text, "news parsing failed");
            require(record["body"] == "第一行\nSymbols: BETA\n", "body corrupted");
        }
        std::cout << "PASS: C++ pure calculations, rollback, duplicate keys, nulls, JSON, 5000-row chunks, integer overflow/precision, timezone, news, archive boundaries, empty exports and failed-export cleanup\n";
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
