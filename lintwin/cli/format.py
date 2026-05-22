def fmt_size(size: int) -> str:
    for unit, threshold in [("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)]:
        if size >= threshold:
            return f"{size / threshold:.1f} {unit}"
    return f"{size} B"
