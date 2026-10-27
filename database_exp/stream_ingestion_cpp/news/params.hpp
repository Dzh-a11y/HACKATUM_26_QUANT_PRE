#pragma once
#include <string>
#include <vector>
namespace news {
struct Params {
    std::vector<std::string> known_symbols = {"ALPHA", "BETA"};
    std::string symbols_field = "Symbols", source = "simulated_feed";
    bool fsync = true;
};
}
