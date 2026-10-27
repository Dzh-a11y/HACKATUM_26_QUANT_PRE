#include "transform.hpp"

namespace accounts {
namespace {
support::Column positions_column(const support::Json &records) {
    std::vector<std::string> values;
    values.reserve(records.size());
    for (const auto &record : records) {
        const auto &positions = record.at("positions");
        if (!positions.is_object()) throw std::invalid_argument("positions must be an object");
        // Match Python json.dumps separators for the benchmark's integer holdings.
        std::string text = "{";
        bool first = true;
        for (const auto &[symbol, quantity] : positions.items()) {
            if (!first) text += ", ";
            first = false;
            text += support::Json(symbol).dump() + ": " + quantity.dump();
        }
        values.push_back(text + "}");
    }
    return {std::move(values), {}};
}
}
support::Columns records_to_columns(const support::Json &records, const support::Context &context, const Params &params) {
    using namespace support;
    const auto n = records.size();
    return {
        constant(context.tick, n),
        integers(records, "event_time"),
        constant(context.received_us, n),
        constant(context.ingested_us, n),
        strings(records, "team_id"),
        strings(records, "currency", &params.currency),
        integers(records, "cash_cents"),
        positions_column(records),
        integers(records, "equity_cents"),
        integers(records, "pnl_cents")
    };
}
}
