#include "calculate.hpp"
#include <limits>
#include <unordered_map>

namespace accounts {
namespace {
int64_t checked(__int128 value) {
    if (value > INT64_MAX || value < INT64_MIN) throw std::overflow_error("account int64 overflow");
    return static_cast<int64_t>(value);
}
std::unordered_map<std::string, size_t> indices(const std::vector<std::string> &names) {
    std::unordered_map<std::string, size_t> result;
    for (size_t i = 0; i < names.size(); ++i)
        if (!result.emplace(names[i], i).second) throw std::invalid_argument("duplicate axis label");
    return result;
}
void check_shape(const State &state) {
    if (state.cash.size() != state.teams.size() || state.positions.size() != state.teams.size() * state.symbols.size())
        throw std::invalid_argument("account state shape mismatch");
}
}
State initial_state(const std::vector<std::string> &symbols, const Params &params) {
    if (symbols.empty() || params.teams.empty()) throw std::invalid_argument("empty account axes");
    indices(symbols); indices(params.teams);
    return {params.teams, symbols, std::vector<int64_t>(params.teams.size(), params.initial_cash_cents),
            std::vector<int64_t>(params.teams.size() * symbols.size(), 0)};
}
State apply_fills(const State &state, const support::Json &fills) {
    check_shape(state);
    State next = state;
    const auto teams = indices(state.teams), symbols = indices(state.symbols);
    for (const auto &fill : fills) {
        const auto t = teams.at(fill.at("team_id").get<std::string>());
        const auto s = symbols.at(fill.at("instrument_id").get<std::string>());
        const auto side = fill.at("side").get<std::string>();
        const auto quantity = fill.at("quantity").get<int64_t>();
        const auto price = fill.at("price_cents").get<int64_t>();
        const auto fee = fill.at("fee_cents").get<int64_t>();
        if ((side != "BUY" && side != "SELL") || quantity <= 0 || price <= 0 || fee < 0)
            throw std::invalid_argument("invalid fill");
        const int64_t signed_quantity = side == "BUY" ? quantity : -quantity;
        const auto index = t * state.symbols.size() + s;
        next.positions[index] = checked(__int128(next.positions[index]) + signed_quantity);
        next.cash[t] = checked(__int128(next.cash[t]) - __int128(signed_quantity) * price - fee);
    }
    return next;
}
std::vector<int64_t> mark_to_market(const State &state, const std::vector<int64_t> &marks) {
    check_shape(state);
    if (marks.size() != state.symbols.size()) throw std::invalid_argument("mark shape mismatch");
    std::vector<int64_t> values(state.teams.size());
    for (size_t team = 0; team < state.teams.size(); ++team) {
        // Checked per term to avoid overflow even if a later term could cancel it.
        int64_t value = state.cash[team];
        for (size_t symbol = 0; symbol < marks.size(); ++symbol)
            value = checked(__int128(value) + __int128(state.positions[team * marks.size() + symbol]) * marks[symbol]);
        values[team] = value;
    }
    return values;
}
support::Json value_accounts(int64_t event_us, const State &state, const support::Json &quotes, const Params &params) {
    std::unordered_map<std::string, int64_t> marks_by_symbol;
    for (const auto &quote : quotes)
        marks_by_symbol[quote.at("instrument_id").get<std::string>()] = checked((__int128(quote.at("bid_cents").get<int64_t>()) + quote.at("ask_cents").get<int64_t>()) / 2);
    std::vector<int64_t> marks;
    for (const auto &symbol : state.symbols) marks.push_back(marks_by_symbol.at(symbol));
    const auto equities = mark_to_market(state, marks);
    auto result = support::Json::array();
    for (size_t team = 0; team < state.teams.size(); ++team) {
        auto positions = support::Json::object();
        for (size_t symbol = 0; symbol < state.symbols.size(); ++symbol)
            positions[state.symbols[symbol]] = state.positions[team * state.symbols.size() + symbol];
        result.push_back({{"event_time", event_us}, {"team_id", state.teams[team]}, {"cash_cents", state.cash[team]},
                          {"positions", positions}, {"equity_cents", equities[team]},
                          {"pnl_cents", checked(__int128(equities[team]) - params.initial_cash_cents)}});
    }
    return result;
}
}
