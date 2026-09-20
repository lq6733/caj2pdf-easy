from app.bootstrap import ensure_runtime, show_error


def _entry() -> None:
    try:
        ensure_runtime()
        from app.main import main

        main()
    except SystemExit:
        raise
    except Exception as exc:
        show_error(f"启动失败：{exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    _entry()
