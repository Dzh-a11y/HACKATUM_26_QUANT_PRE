#pragma once
#include <filesystem>
#include "parser.hpp"
namespace news {
size_t write_records(const std::filesystem::path &path, const support::Json &records,
                     const support::Context &context, const Params &params);
}
