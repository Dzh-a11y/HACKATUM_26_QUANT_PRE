#pragma once
#include "support/types.hpp"
#include <chrono>
#include <fstream>
#include <filesystem>
#include <type_traits>
#include <libproc.h>
#include <sys/resource.h>
#include <unistd.h>

namespace observer {
using Clock = std::chrono::steady_clock;
using Json = support::Json;
struct Snapshot {
    Clock::time_point wall;
    rusage usage{};
    rusage_info_v4 info{};
    bool valid = false;
    int threads = 0;
};
inline Snapshot snapshot() {
    Snapshot s;
    getrusage(RUSAGE_SELF, &s.usage);
    s.valid = proc_pid_rusage(getpid(), RUSAGE_INFO_V4, reinterpret_cast<rusage_info_t *>(&s.info)) == 0;
    proc_taskinfo task{};
    if (proc_pidinfo(getpid(), PROC_PIDTASKINFO, 0, &task, sizeof(task)) == sizeof(task)) s.threads = int(task.pti_threadnum);
    s.wall = Clock::now();
    return s;
}
inline double milliseconds(timeval t) { return double(t.tv_sec) * 1000.0 + double(t.tv_usec) / 1000.0; }
inline Json difference(const Snapshot &a, const Snapshot &b) {
    const bool counters = a.valid && b.valid && b.info.ri_cycles > 0 && b.info.ri_instructions > 0
        && b.info.ri_cycles >= a.info.ri_cycles && b.info.ri_instructions >= a.info.ri_instructions;
    const auto cycles = b.info.ri_cycles - a.info.ri_cycles;
    const auto instructions = b.info.ri_instructions - a.info.ri_instructions;
    return {
        {"wall_ms", std::chrono::duration<double, std::milli>(b.wall - a.wall).count()},
        {"user_ms", milliseconds(b.usage.ru_utime) - milliseconds(a.usage.ru_utime)},
        {"system_ms", milliseconds(b.usage.ru_stime) - milliseconds(a.usage.ru_stime)},
        {"minor_faults", b.usage.ru_minflt - a.usage.ru_minflt},
        {"major_faults", b.usage.ru_majflt - a.usage.ru_majflt},
        {"voluntary_switches", b.usage.ru_nvcsw - a.usage.ru_nvcsw},
        {"involuntary_switches", b.usage.ru_nivcsw - a.usage.ru_nivcsw},
        {"instructions", counters ? Json(instructions) : Json(nullptr)},
        {"cycles", counters ? Json(cycles) : Json(nullptr)},
        {"ipc", counters && cycles ? Json(double(instructions) / double(cycles)) : Json(nullptr)},
        {"rss_bytes", b.valid ? Json(b.info.ri_resident_size) : Json(nullptr)},
        {"threads", b.threads > 0 ? Json(b.threads) : Json(nullptr)},
        {"cache_misses", nullptr}, {"branch_misses", nullptr}
    };
}
class Trace {
    std::ofstream stream;
    Clock::time_point origin = Clock::now();
public:
    int64_t tick = -1;
    explicit Trace(const std::filesystem::path &path) : stream(path) {
        if (!stream) throw std::runtime_error("cannot create trace");
    }
    void emit(Json value) {
        value["at_ms"] = std::chrono::duration<double, std::milli>(Clock::now() - origin).count();
        value["tick"] = tick;
        stream << value.dump() << '\n'; stream.flush();
    }
    template<class Function> auto measure(const std::string &stage, int64_t rows, Function action) {
        emit({{"kind", "start"}, {"stage", stage}, {"rows", rows}});
        const auto before = snapshot();
        try {
            if constexpr (std::is_void_v<std::invoke_result_t<Function>>) {
                action();
                const auto after = snapshot();
                emit({{"kind", "end"}, {"stage", stage}, {"rows", rows}, {"metrics", difference(before, after)}});
            } else {
                auto result = action();
                const auto after = snapshot();
                emit({{"kind", "end"}, {"stage", stage}, {"rows", rows}, {"metrics", difference(before, after)}});
                return result;
            }
        } catch (const std::exception &error) {
            emit({{"kind", "error"}, {"stage", stage}, {"error", error.what()}}); throw;
        }
    }
};
}

