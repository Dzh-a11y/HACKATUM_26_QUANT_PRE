#pragma once
#include <cerrno>
#include <cstdio>
#include <filesystem>
#include <system_error>
#include <unistd.h>
#include "types.hpp"

namespace support {
inline void write_bytes(const std::filesystem::path &path, const std::string &bytes, bool append, bool sync) {
    FILE *file = std::fopen(path.c_str(), append ? "ab" : "wb");
    if (!file) throw std::system_error(errno, std::generic_category(), path.string());
    try {
        if (std::fwrite(bytes.data(), 1, bytes.size(), file) != bytes.size() || std::fflush(file) != 0)
            throw std::system_error(errno, std::generic_category(), "write/flush");
        if (sync && ::fsync(::fileno(file)) != 0) throw std::system_error(errno, std::generic_category(), "fsync");
    } catch (...) { std::fclose(file); throw; }
    if (std::fclose(file) != 0) throw std::system_error(errno, std::generic_category(), "close");
}
inline void write_json(const std::filesystem::path &path, const Json &value) {
    const auto temporary = path.string() + ".tmp";
    write_bytes(temporary, value.dump(2) + "\n", false, true);
    std::filesystem::rename(temporary, path);
}
}
