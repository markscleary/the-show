"""Tests for markdown fence stripping."""
from the_show.sanitise import strip_markdown_fences


def test_no_fences_unchanged():
    assert strip_markdown_fences("hello world") == "hello world"


def test_json_fence_stripped():
    text = "```json\n{\"key\": \"value\"}\n```"
    assert strip_markdown_fences(text) == '{"key": "value"}'


def test_plain_fence_stripped():
    text = "```\nhello\n```"
    assert strip_markdown_fences(text) == "hello"


def test_leading_trailing_whitespace():
    text = "  ```json\n{}\n```  "
    assert strip_markdown_fences(text) == "{}"


def test_non_string_returned_unchanged():
    assert strip_markdown_fences(None) is None  # type: ignore[arg-type]
    assert strip_markdown_fences(123) == 123  # type: ignore[arg-type]


def test_multiline_content_preserved():
    text = "```json\n{\n  \"a\": 1,\n  \"b\": 2\n}\n```"
    result = strip_markdown_fences(text)
    assert result == '{\n  "a": 1,\n  "b": 2\n}'


def test_no_fence_json_untouched():
    raw = '{"key": "value"}'
    assert strip_markdown_fences(raw) == raw
