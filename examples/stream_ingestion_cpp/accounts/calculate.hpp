#pragma once
#include "params.hpp"
#include "support/types.hpp"

namespace accounts {
struct State {
    std::vector<std::string> teams, symbols;
    std::vector<int64_t> cash, positions; // positions[team * symbols.size() + symbol]
    bool operator==(const State &) const = default;
};
State initial_state(const std::vector<std::string> &symbols, const Params &params);
State apply_fills(const State &state, const support::Json &fills);
std::vector<int64_t> mark_to_market(const State &state, const std::vector<int64_t> &marks);
support::Json value_accounts(int64_t event_us, const State &state, const support::Json &quotes, const Params &params);
}
