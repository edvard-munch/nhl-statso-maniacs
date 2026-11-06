"""Checkbox HTML must preserve literal labels/values without adding elements."""

from html.parser import HTMLParser

import pytest

from players import utils

pytestmark = pytest.mark.unit


class Checkboxes(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.tags = []
        self.inputs = []
        self.labels = []
        self.stack = []
        self.feed(markup)
        assert self.stack == []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        assert tag in {"label", "span", "input", "br"}
        if tag == "input":
            self.inputs.append(attrs)
        elif tag == "label":
            self.labels.append({"attrs": attrs, "text": ""})
        if tag not in {"input", "br"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack.pop() == tag

    def handle_data(self, value):
        if "label" in self.stack:
            self.labels[-1]["text"] += value


@pytest.mark.parametrize("value", ["CAN", 'A&B "quoted"', '"><img src=x onerror=alert(1)>'])
@pytest.mark.parametrize("tip", [False, True])
@pytest.mark.parametrize("checked", [False, True])
def test_checkbox_option_preserves_text_attributes_and_checked_state(value, tip, checked):
    tooltip = '<script>alert("tip & text")</script>'
    css = 'nation" onclick="alert(1)'
    parsed = Checkboxes(utils.checkbox_option((value, tooltip), css, tip=tip, check_this=checked))
    assert parsed.labels == [
        {
            "attrs": {"for": value, "class": css + " cell-with-tooltip"},
            "text": value + " " + (tooltip if tip else ""),
        }
    ]
    expected = {"type": "checkbox", "class": css + " checkbox_button", "value": value, "id": value}
    if checked:
        expected["checked"] = None
    assert parsed.inputs == [expected]
    assert parsed.tags == (["label", "span", "input"] if tip else ["label", "input"])


@pytest.mark.parametrize("checked", [None, [], ['A&B "one"'], ['A&B "one"', "<two>"]])
def test_checkbox_selection_uses_original_values_without_changing_options(checked):
    options = [('A&B "one"', "First"), ("<two>", "Second")]
    parsed = Checkboxes(utils.checkbox(options, "nation", tip=False, checked=checked))
    assert [item["value"] for item in parsed.inputs] == [value for value, tip in options]
    assert [item["value"] for item in parsed.inputs if "checked" in item] == (checked or [])
    assert options == [('A&B "one"', "First"), ("<two>", "Second")]


def test_checkbox_wraps_after_eight_options_without_losing_the_next_option():
    options = [(str(index), None) for index in range(9)]
    parsed = Checkboxes(utils.checkbox(options, "nation", tip=False))
    assert [item["value"] for item in parsed.inputs] == [str(index) for index in range(9)]
    assert parsed.tags.count("br") == 1
    assert parsed.tags[-4:] == ["input", "br", "label", "input"]
