"""只读查看一个 Parquet 文件：总行数、字段类型、前 10 条数据。"""

import argparse
from pathlib import Path

import duckdb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="要查看的 Parquet 文件路径")
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error(f"文件不存在或不是普通文件：{args.file}")

    with duckdb.connect(":memory:") as con:
        con.execute("SET TimeZone = 'UTC'")
        path = str(args.file.resolve())
        quotes = con.read_parquet(path)
        count = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [path]).fetchall()[0][0]
        print(f"File: {path}\nRows: {count}\n")
        print("Columns:")
        for name, data_type in zip(quotes.columns, quotes.types):
            print(f"  {name}: {data_type}")
        print("\nPreview (up to 10 rows):")
        quotes.limit(10).show()


if __name__ == "__main__":
    main()
