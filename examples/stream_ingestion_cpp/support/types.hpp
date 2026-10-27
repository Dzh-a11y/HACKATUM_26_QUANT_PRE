#pragma once
#include <cstdint>
#include <string>
#include <variant>
#include <vector>
#include <stdexcept>
#include <json.hpp>

namespace support {
using Json = nlohmann::json;
struct Context { int64_t tick, received_us, ingested_us; };
struct Column {
    std::variant<std::vector<int64_t>, std::vector<std::string>> values;
    std::vector<bool> valid;
    size_t size() const { return std::visit([](const auto &v) { return v.size(); }, values); }
};
using Columns = std::vector<Column>;

inline Column constant(int64_t value, size_t count) {
    return {std::vector<int64_t>(count, value), {}};
}
// Pure adapters: null remains NULL so NOT NULL is checked by DuckDB.
inline Column integers(const Json &records, const std::string &key) {
    std::vector<int64_t> values; std::vector<bool> valid;
    values.reserve(records.size()); valid.reserve(records.size());
    for (const auto &record : records) {
        const auto &value = record.at(key);
        if (!value.is_null() && !value.is_number_integer()) throw std::invalid_argument(key + " must be an integer");
        if (value.is_number_unsigned() && value.get<uint64_t>() > uint64_t(INT64_MAX)) throw std::overflow_error(key);
        valid.push_back(!value.is_null());
        values.push_back(value.is_null() ? 0 : value.get<int64_t>());
    }
    return {std::move(values), std::move(valid)};
}
inline Column strings(const Json &records, const std::string &key, const std::string *fallback = nullptr) {
    std::vector<std::string> values; std::vector<bool> valid;
    values.reserve(records.size()); valid.reserve(records.size());
    for (const auto &record : records) {
        if (!record.contains(key) && fallback) { values.push_back(*fallback); valid.push_back(true); continue; }
        const auto &value = record.at(key);
        valid.push_back(!value.is_null());
        values.push_back(value.is_null() ? "" : value.get<std::string>());
    }
    return {std::move(values), std::move(valid)};
}
} // namespace support
