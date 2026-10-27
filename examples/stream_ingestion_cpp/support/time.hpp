#pragma once
#include <chrono>
#include <iomanip>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>

namespace support {
inline std::string iso_time(int64_t micros, int offset_minutes = 0) {
    using namespace std::chrono;
    const sys_time<microseconds> time{microseconds{micros} + minutes{offset_minutes}};
    const auto day = floor<days>(time);
    const year_month_day date{day};
    const hh_mm_ss<microseconds> clock{time - day};
    std::ostringstream out;
    out << std::setfill('0') << std::setw(4) << int(date.year()) << '-' << std::setw(2) << unsigned(date.month())
        << '-' << std::setw(2) << unsigned(date.day()) << 'T' << std::setw(2) << clock.hours().count()
        << ':' << std::setw(2) << clock.minutes().count() << ':' << std::setw(2) << clock.seconds().count();
    if (clock.subseconds().count()) out << '.' << std::setw(6) << clock.subseconds().count();
    out << (offset_minutes < 0 ? '-' : '+') << std::setw(2) << std::abs(offset_minutes) / 60
        << ':' << std::setw(2) << std::abs(offset_minutes) % 60;
    return out.str();
}
struct ParsedTime { int64_t micros; int offset_minutes; };
inline ParsedTime parse_time(const std::string &text) {
    const std::regex format(R"((\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2}))");
    std::smatch match;
    if (!std::regex_match(text, match, format)) throw std::invalid_argument("expected timezone-aware ISO timestamp: " + text);
    using namespace std::chrono;
    year_month_day date{year{std::stoi(match[1])}, month{unsigned(std::stoi(match[2]))}, day{unsigned(std::stoi(match[3]))}};
    const int hour = std::stoi(match[4]), minute = std::stoi(match[5]), second = std::stoi(match[6]);
    if (!date.ok() || hour > 23 || minute > 59 || second > 59) throw std::invalid_argument("invalid timestamp");
    const std::string zone = match[8];
    int offset = 0;
    if (zone != "Z") {
        const int h = std::stoi(zone.substr(1, 2)), m = std::stoi(zone.substr(4, 2));
        if (h > 23 || m > 59) throw std::invalid_argument("invalid UTC offset");
        offset = (h * 60 + m) * (zone[0] == '-' ? -1 : 1);
    }
    std::string fraction = match[7];
    fraction.resize(6, '0');
    const auto time = sys_days{date} + hours{hour} + minutes{minute - offset} + seconds{second} + microseconds{std::stoi(fraction)};
    return {duration_cast<microseconds>(time.time_since_epoch()).count(), offset};
}
} // namespace support
