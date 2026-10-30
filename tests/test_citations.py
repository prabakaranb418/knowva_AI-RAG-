from citations import long_label, normalize_markers, replace_markers, short_label


def test_valid_markers_are_kept_in_order():
    text, used = normalize_markers("A fact. [S2] Another fact. [S1]", "S", [1, 2, 3])
    assert text == "A fact. [S2] Another fact. [S1]"
    assert used == [2, 1]


def test_invented_markers_are_removed():
    text, used = normalize_markers("Claim [S9] and claim [S1].", "S", [1, 2])
    assert "[S9]" not in text
    assert "[S1]" in text
    assert used == [1]


def test_grouped_markers_are_split_and_filtered():
    text, used = normalize_markers("Claim [S1, S3, S7].", "S", [1, 2, 3])
    assert text == "Claim [S1][S3]."
    assert used == [1, 3]


def test_spaced_and_lowercase_markers():
    text, used = normalize_markers("Claim [s 2] ok.", "S", [2])
    assert "[S2]" in text and used == [2]


def test_removed_marker_does_not_leave_a_gap_before_punctuation():
    text, _ = normalize_markers("It is true [S9].", "S", [1])
    assert text == "It is true."


def test_replace_markers_uses_stored_locations():
    out = replace_markers("Point one [C12]. Point two [C99].", "C", {12: "p.3 ¶2"})
    assert out == "Point one [p.3 ¶2]. Point two."


def test_labels():
    assert short_label(3, 2, 2, "x") == "p.3 ¶2"
    assert short_label(3, 2, 4, "x") == "p.3 ¶2–4"
    assert short_label(None, 5, 5, "x") == "¶5"
    assert short_label(None, None, None, "Slide 4") == "Slide 4"
    assert long_label(3, 2, 2, "x") == "Page 3, Paragraph 2"
    assert long_label(3, 2, 4, "x") == "Page 3, Paragraphs 2–4"
    assert long_label(None, 5, 5, "x") == "Paragraph 5"
