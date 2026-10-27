#include "pipeline.hpp"
#include <iostream>
#include <stdexcept>
namespace { volatile std::sig_atomic_t stop_requested = 0; void stop(int) { stop_requested = 1; } }
int main(int argc, char **argv) {
    try {
        RuntimeParams runtime;
        std::filesystem::path input, output;
        for (int i = 1; i < argc; ++i) {
            const std::string argument = argv[i];
            if (argument == "--fast") { runtime.fast = true; continue; }
            if (argument == "--help") {
                std::cout << "ingest_cpp --input fixture.json --output NEW_DIRECTORY [--fast] [--seconds N] [--export-every N] [--threads N] [--memory-limit 8GB]\n";
                return 0;
            }
            if (i + 1 >= argc) throw std::invalid_argument("missing option value");
            const std::string value = argv[++i];
            if (argument == "--input") input = value;
            else if (argument == "--output") output = value;
            else if (argument == "--seconds") runtime.seconds = std::stoll(value);
            else if (argument == "--export-every") runtime.export_every = std::stoll(value);
            else if (argument == "--threads") runtime.threads = std::stoi(value);
            else if (argument == "--memory-limit") runtime.memory_limit = value;
            else throw std::invalid_argument("unknown option: " + argument);
        }
        if (input.empty() || output.empty()) throw std::invalid_argument("--input and --output are required");
        std::signal(SIGINT, stop); std::signal(SIGTERM, stop);
        pipeline::run(input, output, runtime, stop_requested);
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
