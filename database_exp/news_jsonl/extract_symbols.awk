# 只检查 Body: 之前的新闻头部。标签不区分大小写，代码保持原样。
# 输出：每行一个代码，保留首次出现顺序，去除重复项。
# 退出码：0=找到字段（可以为空），2=格式异常，3=缺少字段。
tolower($0) ~ /^[[:space:]]*body[[:space:]]*:/ { exit }

tolower($0) ~ /^[[:space:]]*symbols[[:space:]]*:/ {
    if (++found > 1) { invalid = 1; exit }
    value = $0
    sub(/^[^:]*:/, "", value)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
    if (value == "") next

    count = split(value, codes, ",")
    for (i = 1; i <= count; i++) {
        code = codes[i]
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", code)
        if (code !~ /^[A-Za-z0-9][A-Za-z0-9._-]*$/) {
            invalid = 1
            exit
        }
        if (!(code in seen)) { print code; seen[code] = 1 }
    }
}

END {
    if (invalid) exit 2
    if (!found) exit 3
}
