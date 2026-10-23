"""Original structured curriculum for the RevelaCode Faith premium workspace.

Lessons are editorial learning aids, not official denominational rulings. The first
lesson in the Scripture Study Method course is a public preview; all other course
material requires the existing Faith trial or a verified paid subscription.
"""
from __future__ import annotations

COURSES = [
    {
        "slug": "scripture-study-method",
        "title": "Study Scripture with Context",
        "summary": "A practical, repeatable method for reading passages carefully, distinguishing textual observations from interpretations, and writing evidence-based conclusions.",
        "level": "Foundations",
        "duration_minutes": 50,
        "tier": "premium",
        "preview_lesson_slug": "observe-before-interpreting",
        "outcomes": [
            "Observe a passage before forming a conclusion.",
            "Identify genre, audience, structure, and context.",
            "Use cross-references without forcing unrelated texts together.",
            "Record sources and distinguish evidence from inference.",
        ],
        "sources": [
            {"label": "BibleProject — How to Read the Bible", "url": "https://bibleproject.com/explore/how-to-read-the-bible/"},
            {"label": "Acts 17:10–12; Luke 10:25–37; James 1:19–27", "url": "https://www.biblegateway.com/"},
        ],
        "lessons": [
            {
                "slug": "observe-before-interpreting",
                "title": "Observe Before Interpreting",
                "minutes": 12,
                "preview": True,
                "reference": "Luke 10:25–37; Acts 17:10–12",
                "content": """# Learning objective
Learn to separate what a passage actually says from what a reader thinks it means.

## Begin with the whole unit
Read the full scene, paragraph, or argument before extracting a single phrase. Write down who speaks, who is addressed, what happens, repeated terms, contrasts, commands, questions, and the stated outcome. Do not write an interpretation in the observation column yet.

## Ask what the text can support
A direct observation should be traceable to the passage. “The character asks a question” is an observation. “The character secretly intends to deceive everyone” is an inference unless the narrative supplies evidence for that motive. Inferences can be reasonable, but label them and explain why they follow from the text.

## Keep a study record
Use five headings: passage, observations, context, interpretation, and application. Add a source beside any historical claim that does not come directly from the passage. If a detail cannot be verified, leave it marked as uncertain rather than silently turning it into a fact.

## Practice
Read Luke 10:25–37. First list the people, actions, questions, and responses. Then write what the parable challenges the listener to reconsider. Finally, propose one practical application and explain which details in the story support it.

## Check yourself
A study is stronger when another reader can follow your steps and disagree with your conclusion without needing to guess what evidence you used. Intellectual humility does not prevent conviction; it makes conviction accountable.""",
                "sources": [
                    {"label": "Luke 10:25–37", "url": "https://www.biblegateway.com/passage/?search=Luke%2010%3A25-37"},
                    {"label": "Acts 17:10–12", "url": "https://www.biblegateway.com/passage/?search=Acts%2017%3A10-12"},
                ],
                "quiz": [
                    {
                        "question": "Which entry is the clearest textual observation?",
                        "options": [
                            "The speaker asks a question in verse 29.",
                            "The speaker is secretly dishonest.",
                            "This passage proves my modern political view.",
                            "Everyone who disagrees is ignoring the Bible.",
                        ],
                        "answer_index": 0,
                        "explanation": "An observation is traceable to what the passage explicitly depicts; hidden motives and modern applications require additional reasoning.",
                    },
                    {
                        "question": "What should a careful reader do with an interpretation that is plausible but not explicit?",
                        "options": [
                            "Present it as a direct quotation from Scripture.",
                            "Label it as an inference and explain the supporting evidence.",
                            "Remove the surrounding verses.",
                            "Treat confidence as proof.",
                        ],
                        "answer_index": 1,
                        "explanation": "A responsible study distinguishes the text itself from conclusions a reader draws from it.",
                    },
                ],
            },
            {
                "slug": "genre-and-context",
                "title": "Genre, Audience, and Context",
                "minutes": 18,
                "preview": False,
                "reference": "Psalm 13; Mark 4:1–20; Romans 8:18–30; Revelation 1",
                "content": """# Why genre matters
The Bible includes narrative, poetry, wisdom, law, prophetic speech, Gospel accounts, letters, and apocalyptic visions. Genre provides clues about how a text communicates. Poetry may use parallelism and metaphor; a letter develops an argument for particular readers; apocalyptic writing often uses symbolic imagery.

## Reconstruct the immediate context
Read what comes before and after your selected passage. Identify the problem, question, conflict, or theme that the author is addressing. If a sentence is a quotation inside a larger story, do not automatically treat it as the author's endorsement. If a letter responds to a community problem, ask what that problem was.

## Use background sources carefully
Historical introductions, Bible dictionaries, and commentaries can help explain language and social setting. They can also disagree. Prefer sources that show their evidence and distinguish what is known from what is debated. Record the source and the claim it supports.

## A disciplined worksheet
For each passage, record: literary genre; speaker or author; intended audience where knowable; key structure; immediate context; broader book context; background claims and sources; and questions that remain unresolved.

## Practice
Compare Psalm 13 with Mark 4:1–20. Note how a lament and a parable work differently. Then read Revelation 1 and note how the opening frames the visions. Avoid flattening these distinct forms into one generic style of statement.

## Application
Context does not erase a text's contemporary relevance. It helps readers explain how a contemporary application is connected to the original passage, rather than assuming that every sentence addresses every situation in precisely the same way.""",
                "sources": [
                    {"label": "Psalm 13", "url": "https://www.biblegateway.com/passage/?search=Psalm%2013"},
                    {"label": "Mark 4:1–20", "url": "https://www.biblegateway.com/passage/?search=Mark%204%3A1-20"},
                    {"label": "Revelation 1", "url": "https://www.biblegateway.com/passage/?search=Revelation%201"},
                ],
                "quiz": [
                    {
                        "question": "Why identify the genre before interpreting a passage?",
                        "options": [
                            "Every biblical book follows identical literary rules.",
                            "Genre gives clues about how the text communicates.",
                            "Genre means historical context is irrelevant.",
                            "Genre determines the answer without reading the text.",
                        ],
                        "answer_index": 1,
                        "explanation": "Genre helps readers notice features such as poetry, argument, narrative, or symbolic imagery.",
                    },
                    {
                        "question": "What is a good way to use a historical commentary?",
                        "options": [
                            "Repeat every claim without attribution.",
                            "Replace reading the passage with the commentary.",
                            "Record its source and distinguish evidence from debated background claims.",
                            "Use only a source that agrees with your first opinion.",
                        ],
                        "answer_index": 2,
                        "explanation": "A source should help make a claim traceable and open to verification.",
                    },
                ],
            },
            {
                "slug": "cross-references-and-evidence",
                "title": "Cross-References and Responsible Conclusions",
                "minutes": 20,
                "preview": False,
                "reference": "Acts 17:10–12; James 2:14–18; Ephesians 2:8–10",
                "content": """# Let each passage speak
Cross-references can illuminate a theme, but a shared word does not prove two passages make the same point. Check speaker, audience, literary setting, genre, and argument. A reference list is a research starting point, not a substitute for reading the passages in context.

## Compare arguments, not isolated words
For example, when comparing James 2:14–18 with Ephesians 2:8–10, identify the specific issue each author is addressing. Record the reasoning in each text before proposing a synthesis. If a tension remains, state it honestly and consult credible scholarship rather than hiding the difficult part.

## Build an evidence trail
A conclusion should show the chain of reasoning: passage, observation, context, supporting references, interpretive inference, alternative reading, and application. Cite the source for historical or linguistic claims. When a Christian tradition has a distinctive interpretation, name that tradition and link to an official statement or reputable scholarly source.

## Handle disagreement well
Represent alternative readings in their strongest reasonable form. Explain where the evidence differs and what each reading does or does not account for. Do not use a disagreement as proof that the other reader is dishonest or malicious.

## Final assignment
Choose a short passage and produce a one-page study record containing all seven elements above. A classmate should be able to check your sources and understand which parts are direct textual claims and which parts are interpretation. Use their questions to revise your reasoning.""",
                "sources": [
                    {"label": "James 2:14–18", "url": "https://www.biblegateway.com/passage/?search=James%202%3A14-18"},
                    {"label": "Ephesians 2:8–10", "url": "https://www.biblegateway.com/passage/?search=Ephesians%202%3A8-10"},
                ],
                "quiz": [
                    {
                        "question": "When two passages share a keyword, what should you check before treating them as making the same point?",
                        "options": [
                            "Whether their contexts, audiences, genres, and arguments are comparable.",
                            "Whether a social-media post quotes them together.",
                            "Whether one verse can be removed from each.",
                            "Whether both translations use identical punctuation.",
                        ],
                        "answer_index": 0,
                        "explanation": "Cross-references should be interpreted in context rather than linked by a word alone.",
                    },
                    {
                        "question": "What belongs in a transparent interpretive conclusion?",
                        "options": [
                            "Only the conclusion, with no evidence.",
                            "The chain of reasoning, sources, inferences, and material alternatives.",
                            "A claim that all disagreement is bad faith.",
                            "A prediction that cannot be checked.",
                        ],
                        "answer_index": 1,
                        "explanation": "A transparent study lets another reader inspect the basis and limits of the conclusion.",
                    },
                ],
            },
        ],
    },
    {
        "slug": "daniel-revelation-research-lab",
        "title": "Daniel & Revelation Research Lab",
        "summary": "A structured investigation of apocalyptic genre, major Christian interpretive approaches, and responsible connections between prophecy and current events.",
        "level": "Intermediate",
        "duration_minutes": 65,
        "tier": "premium",
        "preview_lesson_slug": None,
        "outcomes": [
            "Identify features of apocalyptic literature.",
            "Compare preterist, historicist, futurist, and idealist readings.",
            "Distinguish verified events from proposed prophetic interpretations.",
            "Avoid unsupported predictions and date-setting.",
        ],
        "sources": [
            {"label": "Daniel 2 and Daniel 7", "url": "https://www.biblegateway.com/"},
            {"label": "Revelation 1–3 and Revelation 12–14", "url": "https://www.biblegateway.com/"},
            {"label": "Seventh-day Adventist official beliefs", "url": "https://gc.adventist.org/beliefs/"},
        ],
        "lessons": [
            {
                "slug": "apocalyptic-literature",
                "title": "How Apocalyptic Literature Communicates",
                "minutes": 18,
                "preview": False,
                "reference": "Daniel 2; Daniel 7; Revelation 1",
                "content": """# Read the vision before decoding the symbol
Daniel contains court narratives and visions; Revelation presents an apocalypse as prophecy and a message to early Christian communities. Both use vivid imagery, recurring patterns, heavenly scenes, and conflict between oppressive powers and God's purposes. These literary features should be noticed before matching images to contemporary headlines.

## Use the book's own explanations
Some visions interpret their own symbols. Begin with explanations supplied in the passage. If a symbol is not explained, identify the interpretive choices being made and the evidence used. Do not present an inference as if it were a direct biblical sentence.

## Follow structure and repetition
Record repeated words, parallel scenes, changes of setting, speakers, and audience. Ask what the vision contributes to the book as a whole. A symbol may draw on earlier biblical imagery; compare the passages carefully before concluding that they have exactly the same meaning.

## Test a proposed decoding
Write the symbol and its textual location, the explanation supplied in the text (if any), proposed background sources, alternative readings, and remaining uncertainty. Good research states both the strength and the limits of its evidence.""",
                "sources": [
                    {"label": "Daniel 2", "url": "https://www.biblegateway.com/passage/?search=Daniel%202"},
                    {"label": "Daniel 7", "url": "https://www.biblegateway.com/passage/?search=Daniel%207"},
                    {"label": "Revelation 1", "url": "https://www.biblegateway.com/passage/?search=Revelation%201"},
                ],
                "quiz": [
                    {
                        "question": "What is the best first step when a vision includes a symbol?",
                        "options": [
                            "Assign it to a current leader immediately.",
                            "Read the literary context and any explanation supplied by the text.",
                            "Assume it has only one modern meaning.",
                            "Ignore the surrounding chapters.",
                        ],
                        "answer_index": 1,
                        "explanation": "Context and the text's own explanations should come before modern identifications.",
                    },
                    {
                        "question": "If the text does not explicitly identify a symbol, how should an explanation be presented?",
                        "options": [
                            "As indisputable Scripture wording.",
                            "As an interpretive proposal with supporting evidence and alternatives.",
                            "As fact because many posts repeat it.",
                            "Without sources.",
                        ],
                        "answer_index": 1,
                        "explanation": "A proposed interpretation should be clearly separated from what the text explicitly states.",
                    },
                ],
            },
            {
                "slug": "compare-prophecy-frameworks",
                "title": "Compare the Major Interpretive Frameworks",
                "minutes": 22,
                "preview": False,
                "reference": "Revelation 1–3; Revelation 12–14",
                "content": """# Four broad approaches
Preterist readings emphasize the historical circumstances of the first-century churches and their world. Historicist readings understand visions as a sequence or panorama through Christian history; Seventh-day Adventism has a distinctive historicist tradition. Futurist readings expect major visions to refer to future events. Idealist or symbolic readings emphasize recurring patterns of faithfulness and opposition rather than one continuous dated timeline.

These are broad categories, not four perfectly uniform camps. Scholars and churches combine or qualify approaches in different ways. An honest comparison explains the assumptions behind a particular reading rather than treating the label as the whole argument.

## Compare the same passages
For each framework, record how it reads a selected passage, which historical context it emphasizes, what evidence it uses, what the reading explains well, and which difficulties its critics raise. When describing the Adventist view, consult official Adventist sources. When describing another church, use that church's own primary documents and reputable scholarship.

## A comparison grid
Use these headings: passage; framework; main claim; evidence; assumption; alternative reading; uncertainty. Avoid scoring a tradition as truthful or false solely because its interpretation differs from yours.

## Discussion
Does the proposed reading account for the full passage or only selected phrases? What evidence could change your view? A serious study should be open to testing, correction, and careful disagreement.""",
                "sources": [
                    {"label": "Revelation 1–3", "url": "https://www.biblegateway.com/passage/?search=Revelation%201-3"},
                    {"label": "Revelation 12–14", "url": "https://www.biblegateway.com/passage/?search=Revelation%2012-14"},
                    {"label": "General Conference of Seventh-day Adventists — Beliefs", "url": "https://gc.adventist.org/beliefs/"},
                ],
                "quiz": [
                    {
                        "question": "What is the most accurate description of the four major approaches?",
                        "options": [
                            "They are exact labels with no internal variation.",
                            "They are broad frameworks that scholars and traditions may combine or qualify.",
                            "They are all official teachings of every church.",
                            "They remove the need to read Revelation.",
                        ],
                        "answer_index": 1,
                        "explanation": "These categories help organize comparison but do not capture every scholar's full position.",
                    },
                    {
                        "question": "How should you represent a denomination's interpretation?",
                        "options": [
                            "Use only an opponent's social post.",
                            "Consult its own official sources, label the perspective, and compare alternatives fairly.",
                            "Assume every member agrees on each detail.",
                            "Avoid giving any source.",
                        ],
                        "answer_index": 1,
                        "explanation": "Primary sources and fair comparison help avoid caricature and misattribution.",
                    },
                ],
            },
            {
                "slug": "events-and-prophecy",
                "title": "Current Events Without Date-Setting",
                "minutes": 25,
                "preview": False,
                "reference": "Matthew 24:36; Acts 1:6–8",
                "content": """# Keep three layers separate
A responsible event study distinguishes (1) the verified report, (2) analysis of causes and implications, and (3) theological interpretation. These are related but not interchangeable. A war, election, economic change, or disaster does not automatically demonstrate that one proposed prophetic timeline has reached a specific stage.

## Verify before interpreting
Find the original record or statement where possible. Corroborate major claims with independent reporting. Check the publication date, event date, location, and what remains unconfirmed. Old footage and recycled claims can appear new. Preserve links to sources and correct errors visibly.

## Describe a proposed connection precisely
For each possible connection, record the exact biblical passage, the interpretive tradition making the connection, its stated reasoning, alternative explanations, and uncertainty. A headline alone is not proof of fulfilment.

## Avoid false precision and fear marketing
Matthew 24:36 cautions against claiming knowledge of the day and hour. Do not use predictions, claims of secret certainty, or fear about imminent catastrophe to pressure people into donations, subscriptions, or religious decisions. A trustworthy study supports patient inquiry rather than exploiting anxiety.

## Practical exercise
Select a current item from the existing World Events workspace. Summarize only what reliable sources establish, separately write the theological question it raises, and list what the evidence does not establish.""",
                "sources": [
                    {"label": "Matthew 24:36", "url": "https://www.biblegateway.com/passage/?search=Matthew%2024%3A36"},
                    {"label": "Reuters Trust Principles", "url": "https://www.reuters.com/about-us/"},
                    {"label": "Associated Press News Values and Principles", "url": "https://www.ap.org/about/news-values-and-principles/"},
                ],
                "quiz": [
                    {
                        "question": "Which is the best way to describe a proposed link between a current event and prophecy?",
                        "options": [
                            "The event proves fulfilment because it is dramatic.",
                            "State the verified event, passage, tradition's argument, alternatives, and uncertainty separately.",
                            "Hide the original news source.",
                            "Use fear to force a quick decision.",
                        ],
                        "answer_index": 1,
                        "explanation": "Verification and theological interpretation should remain distinguishable.",
                    },
                    {
                        "question": "What should the study avoid?",
                        "options": [
                            "Showing event dates and sources.",
                            "Explaining what remains unknown.",
                            "Claiming an exact date or selling fear as certainty.",
                            "Comparing credible interpretations.",
                        ],
                        "answer_index": 2,
                        "explanation": "Responsible prophecy study should not claim prohibited certainty or exploit fear.",
                    },
                ],
            },
        ],
    },
    {
        "slug": "comparative-christian-traditions",
        "title": "Comparative Theology: Scripture, Worship & Tradition",
        "summary": "A sourced, respectful comparison of interpretive authority, Sabbath practice, and interfaith dialogue across traditions without pretending differences do not exist.",
        "level": "Intermediate",
        "duration_minutes": 60,
        "tier": "premium",
        "preview_lesson_slug": None,
        "outcomes": [
            "Compare claims through primary texts and accountable sources.",
            "Explain Catholic and Protestant approaches to interpretive authority.",
            "Compare Christian approaches to Sabbath and worship.",
            "Conduct interfaith dialogue without misrepresentation.",
        ],
        "sources": [
            {"label": "Vatican — Catechism of the Catholic Church", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
            {"label": "Seventh-day Adventist official beliefs", "url": "https://gc.adventist.org/beliefs/"},
            {"label": "Qur'an — Surah Maryam 19", "url": "https://quran.com/19"},
        ],
        "lessons": [
            {
                "slug": "scripture-and-authority",
                "title": "Scripture, Tradition, and Authority",
                "minutes": 20,
                "preview": False,
                "reference": "2 Timothy 3:14–17; 2 Thessalonians 2:15; Luke 24:13–35",
                "content": """# Compare the actual claims
Catholic teaching understands Scripture and Sacred Tradition within the Church's transmission of faith and connects authentic interpretation with the Church's teaching office. Protestant traditions that use “sola Scriptura” emphasize Scripture as the final or sole infallible authority for doctrine, though Protestant positions are not all identical. Other Christian traditions may frame the relationship differently.

## Use the tradition's primary sources
Consult the Catechism and official Catholic documents for Catholic teaching. Consult a denomination's own published confession or official belief statement for its position. Do not rely on a hostile summary as your only source. Distinguish official teaching from regional custom, personal devotion, and individual opinion.

## Compare without caricature
Write each position in language an informed adherent would recognize. Identify areas of agreement, actual differences, and the sources used to support each view. If an important question remains contested, say so rather than forcing a false resolution.

## Exercise
Read the passages listed in this lesson. Then consult the relevant official documents and write a short comparison of the sources each tradition recognizes and how interpretation is conducted in its community.""",
                "sources": [
                    {"label": "Catechism of the Catholic Church", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
                    {"label": "2 Timothy 3:14–17", "url": "https://www.biblegateway.com/passage/?search=2%20Timothy%203%3A14-17"},
                    {"label": "2 Thessalonians 2:15", "url": "https://www.biblegateway.com/passage/?search=2%20Thessalonians%202%3A15"},
                ],
                "quiz": [
                    {
                        "question": "What is a reliable starting point for a fair denominational comparison?",
                        "options": [
                            "An unsourced caricature of the other tradition.",
                            "Each tradition's primary texts and official explanations.",
                            "A guess about what all members believe.",
                            "A viral meme.",
                        ],
                        "answer_index": 1,
                        "explanation": "Primary sources show the position as the tradition describes it and make comparison verifiable.",
                    },
                    {
                        "question": "Why should official doctrine be distinguished from local custom?",
                        "options": [
                            "They are always identical.",
                            "Customs, individual opinions, and formal teaching are different kinds of evidence.",
                            "Only customs matter.",
                            "It removes the need for sources.",
                        ],
                        "answer_index": 1,
                        "explanation": "Accurate comparison requires identifying what type of claim a source supports.",
                    },
                ],
            },
            {
                "slug": "sabbath-and-worship",
                "title": "The Sabbath Across Christian Traditions",
                "minutes": 20,
                "preview": False,
                "reference": "Genesis 2:1–3; Exodus 20:8–11; Mark 2:23–28; Romans 14:5–6",
                "content": """# Start with the relevant passages
Genesis 2:1–3 presents the seventh day as blessed and set apart; Exodus 20:8–11 connects Sabbath with creation; Deuteronomy 5:12–15 also connects the command with Israel's liberation. Mark 2:23–28 places Jesus in a dispute about Sabbath practice. Romans 14:5–6 is often discussed in Christian debates about the observance of particular days.

## The Seventh-day Adventist perspective
The Seventh-day Adventist Church teaches that the seventh-day Sabbath is a continuing gift and command associated with creation, worship, rest, service, redemption, and hope. Consult the Church's official statement for its own explanation; do not reduce it to a slogan.

## Other Christian approaches
Many Christians worship on Sunday and understand it in relation to Jesus' resurrection and early Christian practice. Christians differ about how the Sabbath command applies under the new covenant and how biblical law relates to contemporary worship. Summarize each view from credible sources before comparing them.

## Connect belief and practice
The biblical theme of rest also raises practical questions about limits on labour, care for people and animals, worship, community, and economic vulnerability. A study can discuss doctrinal disagreement without insulting people who hold another position.

## Assignment
Build a table with each tradition's day or practice, primary passages, official statement, theological reasoning, and a charitable summary of an alternative view.""",
                "sources": [
                    {"label": "Seventh-day Adventist official belief: The Sabbath", "url": "https://adventist.org/beliefs/official/the-sabbath"},
                    {"label": "Exodus 20:8–11", "url": "https://www.biblegateway.com/passage/?search=Exodus%2020%3A8-11"},
                    {"label": "Romans 14:5–6", "url": "https://www.biblegateway.com/passage/?search=Romans%2014%3A5-6"},
                ],
                "quiz": [
                    {
                        "question": "What is an academically responsible way to compare Sabbath beliefs?",
                        "options": [
                            "Present one tradition's position as shared by every Christian.",
                            "Use each tradition's primary passages and official explanations, then compare its reasoning.",
                            "Avoid mentioning differences.",
                            "Decide based on an individual's social-media comment.",
                        ],
                        "answer_index": 1,
                        "explanation": "Responsible comparison is specific, sourced, and clear about which tradition holds which view.",
                    },
                    {
                        "question": "What broader practical theme appears in the biblical Sabbath material?",
                        "options": [
                            "Rest and the treatment of people and animals.",
                            "Only a calendar calculation.",
                            "A rule that excludes community life.",
                            "An instruction to stop checking evidence.",
                        ],
                        "answer_index": 0,
                        "explanation": "The texts connect rest with worship, creation, liberation, and the lives of others.",
                    },
                ],
            },
            {
                "slug": "interfaith-dialogue",
                "title": "Interfaith Dialogue: Compare Without Misrepresenting",
                "minutes": 20,
                "preview": False,
                "reference": "Mark 8:27–30; John 1:1–18; Qur'an 19 and 4:157–171",
                "content": """# Distinct traditions, serious questions
Islam and Christianity have their own scriptures, histories, schools of interpretation, and communities. Christian traditions confess Jesus as Christ and centralize his death and resurrection; Muslims honour Jesus (Isa) as Messiah and messenger of God while rejecting central Christian formulations of his divinity within the Trinity. These are substantive differences, not details to hide.

## Begin with primary texts
Read Mark 8:27–30 and John 1:1–18 for Christian claims in their literary settings. Read a recognized translation of Qur'an 19 and 4:157–171 for Qur'anic claims about Jesus and Mary. When discussing exact wording, identify the Bible translation or Qur'an translation being used.

## Represent people accurately
Formal teaching, individual opinion, local culture, and political rhetoric are not interchangeable. Use informed sources from the tradition under discussion. Where scholars disagree, explain that disagreement. Avoid treating an online speaker as representative of every Muslim or Christian.

## A dialogue checklist
Before sharing a conclusion, ask: Is the passage quoted in context? Have I represented the other view fairly? Which claims are supported by primary sources? Which part is inference? What question should I ask an informed adherent rather than assume?

## Reflection
Can you state a genuine disagreement without insulting the people who hold a different view? Respectful dialogue does not require pretending that theological claims are identical; it requires honesty about both common ground and difference.""",
                "sources": [
                    {"label": "Qur'an 19 — Maryam", "url": "https://quran.com/19"},
                    {"label": "Qur'an 4:157–171 — An-Nisa", "url": "https://quran.com/4/157-171"},
                    {"label": "John 1:1–18", "url": "https://www.biblegateway.com/passage/?search=John%201%3A1-18"},
                ],
                "quiz": [
                    {
                        "question": "Does respectful interfaith dialogue require claiming that Christian and Muslim beliefs about Jesus are identical?",
                        "options": [
                            "Yes, all religious differences must be hidden.",
                            "No. It requires honest, sourced representation without insults or caricature.",
                            "Yes, sources should not be consulted.",
                            "No. It requires treating all adherents as malicious.",
                        ],
                        "answer_index": 1,
                        "explanation": "Respectful dialogue can acknowledge real differences while representing people fairly.",
                    },
                    {
                        "question": "Which sources best support a careful comparison?",
                        "options": [
                            "Only an unsourced polemical summary.",
                            "Primary texts in identified translations plus reputable scholarship from the traditions.",
                            "Only social-media comments.",
                            "No sources are needed in theology.",
                        ],
                        "answer_index": 1,
                        "explanation": "Primary texts and accountable scholarship make the comparison auditable.",
                    },
                ],
            },
        ],
    },
]


def get_course(course_slug: str):
    slug = str(course_slug or "").strip().lower()
    for course in COURSES:
        if course["slug"] == slug:
            return course
    return None


def get_lesson(course_slug: str, lesson_slug: str):
    course = get_course(course_slug)
    if not course:
        return None, None
    slug = str(lesson_slug or "").strip().lower()
    for lesson in course["lessons"]:
        if lesson["slug"] == slug:
            return course, lesson
    return course, None


def public_quiz(lesson: dict):
    """Never expose correct answers before an assessment is submitted."""
    return [
        {
            "question": item["question"],
            "options": list(item["options"]),
        }
        for item in lesson.get("quiz", [])
    ]


def public_lesson(lesson: dict, *, include_content: bool):
    result = {
        "slug": lesson["slug"],
        "title": lesson["title"],
        "minutes": lesson.get("minutes", 10),
        "preview": bool(lesson.get("preview")),
        "reference": lesson.get("reference", ""),
        "locked": not include_content,
    }
    if include_content:
        result["content"] = lesson.get("content", "")
        result["sources"] = list(lesson.get("sources") or [])
        result["quiz"] = public_quiz(lesson)
    else:
        result["summary"] = "Unlock this lesson with your 30-day Faith trial or an active Faith subscription."
    return result


def public_course(course: dict, *, has_premium_access: bool, detail: bool = False):
    result = {
        "slug": course["slug"],
        "title": course["title"],
        "summary": course["summary"],
        "level": course["level"],
        "duration_minutes": course["duration_minutes"],
        "tier": course["tier"],
        "outcomes": list(course.get("outcomes") or []),
        "sources": list(course.get("sources") or []),
        "lesson_count": len(course.get("lessons") or []),
        "locked": not has_premium_access,
        "preview_available": bool(course.get("preview_lesson_slug")),
    }
    if detail:
        lessons = []
        for lesson in course.get("lessons") or []:
            preview_only = (
                not has_premium_access
                and lesson["slug"] != course.get("preview_lesson_slug")
            )
            lessons.append(public_lesson(lesson, include_content=not preview_only))
        result["lessons"] = lessons
    return result
