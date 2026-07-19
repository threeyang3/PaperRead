from __future__ import annotations

import io

from paperflow.cli import _configure_console_stream


def test_legacy_windows_console_escapes_unsupported_pdf_ligatures() -> None:
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(
        buffer,
        encoding="gbk",
        errors="strict",
        write_through=True,
    )

    _configure_console_stream(stream)
    stream.write('{"title": "efﬁcient", "message": "中文"}')
    stream.flush()

    rendered = buffer.getvalue().decode("gbk")
    assert r"ef\ufb01cient" in rendered
    assert '"message": "中文"' in rendered
