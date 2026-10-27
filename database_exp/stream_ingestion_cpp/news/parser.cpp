#include "parser.hpp"
#include "support/time.hpp"
#include <algorithm>
#include <cctype>
#include <unordered_map>
#include <unordered_set>

namespace news {
namespace {
std::string trim(std::string text) {
    const auto start = text.find_first_not_of(" \t\r\n\v\f");
    return start == std::string::npos ? "" : text.substr(start, text.find_last_not_of(" \t\r\n\v\f") - start + 1);
}
std::string lower(std::string text) {
    for (auto &c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return text;
}
bool alnum(char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'); }
}
Symbols extract_symbols(const std::vector<std::string> &header_lines, const Params &params) {
    std::vector<std::string> values;
    for (const auto &line : header_lines) {
        const auto colon = line.find(':');
        if (colon != std::string::npos && lower(trim(line.substr(0, colon))) == lower(params.symbols_field))
            values.push_back(trim(line.substr(colon + 1)));
    }
    if (values.empty()) return {{}, "missing", {}};
    if (values.size() != 1) return {{}, "malformed", {}};
    if (values[0].empty()) return {{}, "empty", {}};
    std::vector<std::string> candidates;
    size_t start = 0;
    do {
        const auto comma = values[0].find(',', start);
        const auto code = trim(values[0].substr(start, comma == std::string::npos ? comma : comma - start));
        if (code.empty() || !alnum(code[0]) || !std::all_of(code.begin(), code.end(), [](char c) { return alnum(c) || c == '.' || c == '_' || c == '-'; }))
            return {{}, "malformed", {}};
        candidates.push_back(code);
        if (comma == std::string::npos) break;
        start = comma + 1;
    } while (true);
    Symbols result{{}, "ok", {}};
    std::unordered_set<std::string> seen;
    for (const auto &code : candidates) {
        if (!seen.insert(code).second) continue;
        auto &target = std::find(params.known_symbols.begin(), params.known_symbols.end(), code) != params.known_symbols.end() ? result.known : result.unknown;
        target.push_back(code);
    }
    if (!result.unknown.empty()) result.status = "unknown_symbols";
    return result;
}
support::Json parse_record(const std::string &raw, const support::Context &context, const Params &params) {
    std::unordered_map<std::string, std::string> headers;
    std::vector<std::string> header_lines;
    std::string body;
    for (size_t start = 0; start < raw.size();) {
        const auto newline = raw.find('\n', start);
        const size_t end = newline == std::string::npos ? raw.size() : newline + 1;
        const auto line = raw.substr(start, end - start);
        const auto colon = line.find(':');
        if (colon != std::string::npos) {
            const auto key = lower(trim(line.substr(0, colon)));
            if (key == "body") {
                size_t content = start + colon + 1;
                while (content < raw.size() && (raw[content] == ' ' || raw[content] == '\t')) ++content;
                body = raw.substr(content); break;
            }
            headers[key] = trim(line.substr(colon + 1));
        }
        header_lines.push_back(line); start = end;
    }
    const auto published = support::parse_time(headers.at("published-at"));
    const auto symbols = extract_symbols(header_lines, params);
    return {{"news_id", headers.at("news-id")}, {"tick", context.tick}, {"source", params.source},
            {"published_at", support::iso_time(published.micros, published.offset_minutes)},
            {"received_at", support::iso_time(context.received_us)}, {"ingested_at", support::iso_time(context.ingested_us)},
            {"title", headers.at("title")}, {"body", body}, {"symbols", symbols.known},
            {"symbol_status", symbols.status}, {"unrecognized_symbols", symbols.unknown},
            {"symbol_method", "symbols_header_v1"}, {"raw_text", raw}};
}
}
