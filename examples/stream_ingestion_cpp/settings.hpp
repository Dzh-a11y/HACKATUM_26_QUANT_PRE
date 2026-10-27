#pragma once
#include "market/params.hpp"
#include "trades/params.hpp"
#include "accounts/params.hpp"
#include "news/params.hpp"
struct Settings {
    market::Params market;
    trades::Params trades;
    accounts::Params accounts;
    news::Params news;
};
struct RuntimeParams {
    bool fast = false;
    int threads = 1;
    std::string memory_limit = "8GB";
    // 0 means use the fixture's duration/interval; all values are seconds.
    int64_t seconds = 0, export_every = 0;
};
