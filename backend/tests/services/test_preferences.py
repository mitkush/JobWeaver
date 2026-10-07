from app.services.preferences import suggested_titles


def test_suggests_related_titles_the_user_does_not_already_match():
    suggestions = suggested_titles(["Backend Developer"])
    assert "Software Engineer" in suggestions
    # Equivalent wording is matched already, so never suggested.
    assert "Backend Engineer" not in suggestions
    assert "Backend Developer" not in suggestions


def test_a_more_specific_title_finds_its_group_but_not_its_own_shorter_form():
    suggestions = suggested_titles(["Senior Ruby on Rails Developer"])
    assert "Backend Developer" in suggestions
    assert "Ruby on Rails Developer" not in suggestions


def test_one_suggestion_per_wording_and_capped():
    suggestions = suggested_titles(["Software Engineer", "Backend Developer", "DevOps Engineer"])
    assert len(suggestions) <= 8
    assert not {"SDE", "Software Engineer"} <= set(suggestions)


def test_unknown_titles_get_no_suggestions():
    assert suggested_titles(["Pastry Chef"]) == []
