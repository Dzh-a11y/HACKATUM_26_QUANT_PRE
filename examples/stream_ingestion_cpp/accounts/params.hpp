#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace accounts {
struct Params {
    std::string currency = "EUR";
    std::vector<std::string> teams = {"TEAM_A", "TEAM_B"};
    int64_t initial_cash_cents = 10'000'000;
};
}
