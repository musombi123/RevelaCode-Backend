from backend.study.faith_premium_curriculum import (
    COURSES,
    get_course,
    get_lesson,
    public_course,
)


def test_premium_curriculum_has_unique_slugs_and_substantive_lessons():
    course_slugs = [course["slug"] for course in COURSES]
    assert len(course_slugs) == len(set(course_slugs))
    assert len(COURSES) >= 3

    lesson_slugs = []
    for course in COURSES:
        assert course["title"].strip()
        assert course["summary"].strip()
        assert course["sources"]
        assert course["outcomes"]

        for lesson in course["lessons"]:
            lesson_slugs.append((course["slug"], lesson["slug"]))
            assert lesson["title"].strip()
            assert len(lesson["content"].strip()) >= 500
            assert lesson["sources"]
            assert lesson["quiz"]
            for question in lesson["quiz"]:
                assert len(question["options"]) >= 2
                assert 0 <= question["answer_index"] < len(question["options"])
                assert question["explanation"].strip()

    assert len(lesson_slugs) == len(set(lesson_slugs))


def test_only_explicit_scripture_study_preview_is_open_without_premium():
    course = get_course("scripture-study-method")
    assert course is not None

    public = public_course(course, has_premium_access=False, detail=True)
    assert public["locked"] is True
    lessons = {lesson["slug"]: lesson for lesson in public["lessons"]}

    preview = lessons["observe-before-interpreting"]
    assert preview["preview"] is True
    assert preview["locked"] is False
    assert preview["content"].strip()
    assert preview["quiz"]

    for slug, lesson in lessons.items():
        if slug == "observe-before-interpreting":
            continue
        assert lesson["locked"] is True
        assert "content" not in lesson
        assert "quiz" not in lesson


def test_quiz_answer_keys_are_not_exposed_before_submission():
    for course in COURSES:
        public = public_course(course, has_premium_access=True, detail=True)
        for lesson in public["lessons"]:
            for question in lesson.get("quiz", []):
                assert "answer_index" not in question
                assert "explanation" not in question
                assert question["question"]
                assert question["options"]


def test_course_and_lesson_lookup_reject_unknown_slugs():
    assert get_course("not-a-real-course") is None
    course, lesson = get_lesson("scripture-study-method", "not-a-real-lesson")
    assert course is not None
    assert lesson is None
    course, lesson = get_lesson("not-a-real-course", "observe-before-interpreting")
    assert course is None
    assert lesson is None

def test_priority_faith_courses_cover_requested_topics_and_primary_sources():
    by_slug = {course["slug"]: course for course in COURSES}
    expected = {
        "three-angels-messages",
        "sda-28-fundamental-beliefs",
        "great-controversy-theme",
        "catholic-muslim-comparative-dialogue",
    }
    assert expected.issubset(by_slug)

    for slug in expected:
        course = by_slug[slug]
        assert course["sources"]
        assert len(course["lessons"]) >= 3
        assert course["tier"] == "premium"
        assert course["preview_lesson_slug"] is None
        for lesson in course["lessons"]:
            assert lesson["sources"]
            assert lesson["quiz"]
            assert len(lesson["content"]) >= 500

    beliefs = by_slug["sda-28-fundamental-beliefs"]
    belief_text = "\\n".join(lesson["title"] + "\\n" + lesson["content"] for lesson in beliefs["lessons"])
    required_belief_names = [
        "Holy Scriptures", "The Trinity", "God the Father", "God the Son",
        "God the Holy Spirit", "Creation", "Nature of Humanity", "The Great Controversy",
        "The Life, Death and Resurrection of Christ", "The Experience of Salvation",
        "Growing in Christ", "The Church", "The Remnant and its Mission",
        "Unity in the Body of Christ", "Baptism", "The Lord's Supper",
        "Spiritual Gifts and Ministries", "The Gift of Prophecy", "The Law of God",
        "The Sabbath", "Stewardship", "Christian Behavior", "Marriage and the Family",
        "Christ's Ministry in the Heavenly Sanctuary", "The Second Coming of Christ",
        "Death and Resurrection", "The Millennium and the End of Sin", "The New Earth",
    ]
    for belief in required_belief_names:
        assert belief in belief_text, f"Missing Fundamental Belief: {belief}"

    interfaith_text = "\\n".join(
        lesson["title"] + "\\n" + lesson["content"]
        for lesson in by_slug["catholic-muslim-comparative-dialogue"]["lessons"]
    )
    assert "Catholic" in interfaith_text
    assert "Muslim" in interfaith_text
    assert "without ranking" in by_slug["catholic-muslim-comparative-dialogue"]["summary"]


def test_three_angels_and_great_controversy_are_labeled_as_adventist_perspectives():
    by_slug = {course["slug"]: course for course in COURSES}
    assert "Seventh-day Adventist" in by_slug["three-angels-messages"]["summary"]
    great_controversy_text = " ".join(
        lesson["content"] for lesson in by_slug["great-controversy-theme"]["lessons"]
    )
    assert "official Adventist" in great_controversy_text
    assert "official Seventh-day Adventist" in by_slug["great-controversy-theme"]["summary"]
    assert "not rank the human worth" in great_controversy_text

