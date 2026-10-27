#include "transform.hpp"

namespace market {
support::Columns records_to_columns(const support::Json &records, const support::Context &context, const Params &params) {
    using namespace support;
    const auto n = records.size();
    return {
        constant(context.tick, n),
        integers(records, "event_time"),
        constant(context.received_us, n),
        constant(context.ingested_us, n),
        strings(records, "instrument_id"),
        strings(records, "venue", &params.venue),
        strings(records, "currency", &params.currency),
        integers(records, "bid_cents"),
        integers(records, "ask_cents"),
        integers(records, "bid_size"),
        integers(records, "ask_size")
    };
}
}
