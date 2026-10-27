#pragma once
#include "params.hpp"
#include "support/types.hpp"
namespace news {
struct Symbols { std::vector<std::string> known; std::string status; std::vector<std::string> unknown; };
Symbols extract_symbols(const std::vector<std::string> &header_lines, const Params &params);
support::Json parse_record(const std::string &raw, const support::Context &context, const Params &params);
}
