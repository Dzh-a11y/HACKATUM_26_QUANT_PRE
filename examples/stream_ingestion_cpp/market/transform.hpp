#pragma once
#include "params.hpp"
#include "support/types.hpp"

namespace market {
// Pure: explicit records, timestamps and per-table settings; inputs stay unchanged.
support::Columns records_to_columns(const support::Json &records, const support::Context &context, const Params &params);
}
