from recruitee_mcp import shape


def test_text_keeps_paragraphs_and_list_items():
    assert shape.text("<p>Build <b>APIs</b>.</p><ul><li>Python</li><li>Go</li></ul>") == "Build APIs.\n\n- Python\n- Go"


def test_doc_is_one_paragraph_per_line():
    assert shape.doc("Strong\n\nHire")["doc"]["content"] == [
        {"type": "paragraph", "content": [{"type": "text", "text": "Strong"}]},
        {"type": "paragraph"},
        {"type": "paragraph", "content": [{"type": "text", "text": "Hire"}]},
    ]


def test_slim_drops_noise_and_turns_html_into_text():
    assert shape.slim(
        {
            "subject": "Hi",
            "body_html": "<p>Hello</p>",
            "body_json": {"doc": {}},
            "photo_thumb_url": "x",
            "cc": [],
            "references": [{"id": 1}],
            "summary": "kept",
            "summary_html": "<p>dropped, text twin exists</p>",
        }
    ) == {"subject": "Hi", "body": "Hello", "summary": "kept"}
