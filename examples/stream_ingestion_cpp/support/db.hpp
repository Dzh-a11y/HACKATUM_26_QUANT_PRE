#pragma once
#include <duckdb.h>
#include <algorithm>
#include <filesystem>
#include <stdexcept>
#include <string>
#include "types.hpp"

namespace support {
struct Result {
    duckdb_result value{};
    Result(duckdb_connection connection, const std::string &sql) {
        if (duckdb_query(connection, sql.c_str(), &value) == DuckDBError) {
            const std::string error = duckdb_result_error(&value);
            duckdb_destroy_result(&value);
            throw std::runtime_error(error);
        }
    }
    ~Result() { duckdb_destroy_result(&value); }
    Result(const Result &) = delete;
    Result &operator=(const Result &) = delete;
};
inline void execute(duckdb_connection connection, const std::string &sql) { Result result(connection, sql); }
inline int64_t scalar(duckdb_connection connection, const std::string &sql) {
    Result result(connection, sql); return duckdb_value_int64(&result.value, 0, 0);
}
inline std::string text_scalar(duckdb_connection connection, const std::string &sql) {
    Result result(connection, sql);
    char *value = duckdb_value_varchar(&result.value, 0, 0);
    if (!value) throw std::runtime_error("expected non-null scalar");
    std::string text(value); duckdb_free(value); return text;
}
inline std::string quote(const std::string &text) {
    std::string value = "'";
    for (const char c : text) { value += c; if (c == '\'') value += '\''; }
    return value + "'";
}
struct Database {
    duckdb_database database{};
    duckdb_connection connection{};
    explicit Database(const std::string &path, const std::string &memory = "8GB", int threads = 1) {
        duckdb_config config{};
        if (duckdb_create_config(&config) == DuckDBError) throw std::runtime_error("create config failed");
        if (duckdb_set_config(config, "memory_limit", memory.c_str()) == DuckDBError ||
            duckdb_set_config(config, "threads", std::to_string(threads).c_str()) == DuckDBError) {
            duckdb_destroy_config(&config); throw std::runtime_error("invalid DuckDB config");
        }
        char *error = nullptr;
        const auto opened = duckdb_open_ext(path.c_str(), &database, config, &error);
        duckdb_destroy_config(&config);
        if (opened == DuckDBError) {
            const std::string message = error ? error : "open failed";
            duckdb_free(error); throw std::runtime_error(message);
        }
        if (duckdb_connect(database, &connection) == DuckDBError) {
            duckdb_close(&database); throw std::runtime_error("connect failed");
        }
        try { execute(connection, "SET TimeZone='UTC'"); }
        catch (...) { duckdb_disconnect(&connection); duckdb_close(&database); throw; }
    }
    ~Database() { duckdb_disconnect(&connection); duckdb_close(&database); }
    Database(const Database &) = delete;
    Database &operator=(const Database &) = delete;
};
struct Appender {
    duckdb_appender value{};
    Appender(duckdb_connection connection, const char *table) {
        if (duckdb_appender_create(connection, nullptr, table, &value) == DuckDBError) {
            const std::string error = value && duckdb_appender_error(value) ? duckdb_appender_error(value) : "appender create failed";
            duckdb_appender_destroy(&value); throw std::runtime_error(error);
        }
    }
    ~Appender() { duckdb_appender_destroy(&value); }
    void check(duckdb_state state) {
        if (state == DuckDBError) throw std::runtime_error(duckdb_appender_error(value) ? duckdb_appender_error(value) : "append failed");
    }
    Appender(const Appender &) = delete;
    Appender &operator=(const Appender &) = delete;
};
struct Chunk {
    duckdb_data_chunk value{};
    explicit Chunk(duckdb_appender appender) {
        const auto count = duckdb_appender_column_count(appender);
        std::vector<duckdb_logical_type> types(count);
        for (idx_t i = 0; i < count; ++i) types[i] = duckdb_appender_column_type(appender, i);
        value = duckdb_create_data_chunk(types.data(), count);
        for (auto &type : types) duckdb_destroy_logical_type(&type);
        if (!value) throw std::runtime_error("create chunk failed");
    }
    ~Chunk() { duckdb_destroy_data_chunk(&value); }
    Chunk(const Chunk &) = delete;
    Chunk &operator=(const Chunk &) = delete;
};
inline size_t append_columns(duckdb_connection connection, const char *table, const Columns &columns) {
    if (columns.empty()) return 0;
    const size_t rows = columns.front().size();
    for (const auto &column : columns)
        if (column.size() != rows || (!column.valid.empty() && column.valid.size() != rows)) throw std::invalid_argument("unequal column lengths");
    if (!rows) return 0;
    Appender appender(connection, table);
    if (duckdb_appender_column_count(appender.value) != columns.size()) throw std::invalid_argument("wrong column count");
    for (size_t c = 0; c < columns.size(); ++c) {
        auto type = duckdb_appender_column_type(appender.value, c);
        const auto id = duckdb_get_type_id(type);
        duckdb_destroy_logical_type(&type);
        const bool numeric = std::holds_alternative<std::vector<int64_t>>(columns[c].values);
        if ((numeric && id != DUCKDB_TYPE_BIGINT && id != DUCKDB_TYPE_TIMESTAMP_TZ) ||
            (!numeric && id != DUCKDB_TYPE_VARCHAR)) throw std::invalid_argument("column buffer type does not match table");
    }
    Chunk chunk(appender.value);
    const size_t capacity = duckdb_vector_size();
    for (size_t start = 0; start < rows; start += capacity) {
        duckdb_data_chunk_reset(chunk.value);
        const auto count = std::min(capacity, rows - start);
        for (size_t c = 0; c < columns.size(); ++c) {
            auto vector = duckdb_data_chunk_get_vector(chunk.value, c);
            const auto &column = columns[c];
            if (const auto *values = std::get_if<std::vector<int64_t>>(&column.values)) {
                auto *data = static_cast<int64_t *>(duckdb_vector_get_data(vector));
                std::copy_n(values->data() + start, count, data);
            } else {
                const auto &strings = std::get<std::vector<std::string>>(column.values);
                for (size_t row = 0; row < count; ++row) {
                    const auto &text = strings[start + row];
                    duckdb_vector_assign_string_element_len(vector, row, text.data(), text.size());
                }
            }
            if (!column.valid.empty()) {
                duckdb_vector_ensure_validity_writable(vector);
                auto *validity = duckdb_vector_get_validity(vector);
                for (size_t row = 0; row < count; ++row) duckdb_validity_set_row_validity(validity, row, column.valid[start + row]);
            }
        }
        duckdb_data_chunk_set_size(chunk.value, count);
        appender.check(duckdb_append_data_chunk(appender.value, chunk.value));
    }
    appender.check(duckdb_appender_close(appender.value));
    return rows;
}
inline size_t export_table(duckdb_connection connection, const std::string &table,
                           const std::filesystem::path &path, int64_t start, int64_t end) {
    const std::string range = " WHERE tick >= " + std::to_string(start) + " AND tick < " + std::to_string(end);
    const auto count = scalar(connection, "SELECT count(*) FROM " + table + range);
    execute(connection, "COPY (SELECT * FROM " + table + range + ") TO " + quote(path.string()) + " (FORMAT PARQUET, COMPRESSION ZSTD)");
    return size_t(count);
}
} // namespace support
