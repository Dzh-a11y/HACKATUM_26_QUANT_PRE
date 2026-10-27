#include "transform.hpp"

namespace trades {
support::Columns records_to_columns(const support::Json &records, const support::Context &context, const Params &params) {
    using namespace support;
    const auto n = records.size();
    return {
        strings(records, "trade_id"),
        constant(context.tick, n),
        integers(records, "event_time"),
        constant(context.received_us, n),
        constant(context.ingested_us, n),
        strings(records, "team_id"),
        strings(records, "instrument_id"),
        strings(records, "venue", &params.venue),
        strings(records, "currency", &params.currency),
        strings(records, "side"),
        integers(records, "quantity"),
        integers(records, "price_cents"),
        integers(records, "fee_cents")
    };
}
}
