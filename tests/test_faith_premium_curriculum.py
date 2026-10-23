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
