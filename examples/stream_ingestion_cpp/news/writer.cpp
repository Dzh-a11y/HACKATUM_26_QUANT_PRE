#include "writer.hpp"
#include "support/files.hpp"
namespace news {
size_t write_records(const std::filesystem::path &path, const support::Json &records,
                     const support::Context &context, const Params &params) {
    if (records.empty()) return 0;
    std::string bytes;
    for (const auto &raw : records) bytes += parse_record(raw.get<std::string>(), context, params).dump() + '\n';
    support::write_bytes(path, bytes, true, params.fsync);
    return records.size();
}
}
