cmake_minimum_required(VERSION 3.20)
project(stream_ingestion_cpp LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(DUCKDB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor/duckdb" CACHE PATH "DuckDB 2.0.0 library and headers")
find_path(DUCKDB_INCLUDE duckdb.h PATHS "${DUCKDB_DIR}" "${DUCKDB_DIR}/include" NO_DEFAULT_PATH REQUIRED)
find_library(DUCKDB_LIBRARY duckdb PATHS "${DUCKDB_DIR}" "${DUCKDB_DIR}/lib" NO_DEFAULT_PATH REQUIRED)
add_library(ingestion
    market/transform.cpp market/storage.cpp
    trades/transform.cpp trades/storage.cpp
    accounts/transform.cpp accounts/storage.cpp accounts/calculate.cpp
    news/parser.cpp news/writer.cpp pipeline.cpp)
target_include_directories(ingestion PUBLIC . vendor "${DUCKDB_INCLUDE}")
target_link_libraries(ingestion PUBLIC "${DUCKDB_LIBRARY}")
target_compile_options(ingestion PRIVATE -Wall -Wextra -Wconversion -Wshadow)
add_executable(ingest_cpp main.cpp)
target_link_libraries(ingest_cpp PRIVATE ingestion)
add_executable(test_cpp tests/test.cpp)
target_link_libraries(test_cpp PRIVATE ingestion)
enable_testing()
add_test(NAME cpp_contracts COMMAND test_cpp)
