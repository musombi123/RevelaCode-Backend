"""Structured curriculum for RevelaCode Faith Hub.

All published lessons are available to authenticated Faith Hub members. Lessons are
editorial learning aids, not official denominational rulings.
"""
from __future__ import annotations

COURSES = [
    {
        "slug": "scripture-study-method",
        "title": "Study Scripture with Context",
        "summary": "A practical, repeatable method for reading passages carefully, distinguishing textual observations from interpretations, and writing evidence-based conclusions.",
        "level": "Foundations",
        "duration_minutes": 50,
        "tier": "free",
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
        "tier": "free",
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
        "tier": "free",
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

    {
        "slug": "three-angels-messages",
        "title": "The Three Angels’ Messages — Text, Tradition & Debate",
        "summary": "A priority course on Revelation 14:6–12, presenting the Seventh-day Adventist historicist reading accurately while comparing alternative Christian interpretations and their evidence.",
        "level": "Intermediate",
        "duration_minutes": 75,
        "tier": "free",
        "preview_lesson_slug": None,
        "outcomes": [
            "Explain the three proclamations in Revelation 14:6–12 in context.",
            "Distinguish the biblical wording from specific Seventh-day Adventist interpretations.",
            "Compare major Christian approaches to Babylon, the beast, the mark, worship, and perseverance.",
            "Discuss conscience and religious freedom without demonizing believers or predicting dates.",
        ],
        "sources": [
            {"label": "Revelation 14:6–12 — primary biblical text", "url": "https://www.biblegateway.com/passage/?search=Revelation%2014%3A6-12"},
            {"label": "General Conference of Seventh-day Adventists — Fundamental Beliefs", "url": "https://gc.adventist.org/beliefs/"},
            {"label": "General Conference — Mission statement and the Three Angels’ Messages", "url": "https://gc.adventist.org/official-statements/mission-statement-of-the-seventh-day-adventist-church/"},
        ],
        "lessons": [
            {
                "slug": "everlasting-gospel-and-worship",
                "title": "First Message: Everlasting Gospel, Worship, and the Creator",
                "minutes": 22,
                "preview": False,
                "reference": "Revelation 14:6–7; Genesis 1–2; Psalm 96",
                "content": """# Start with the text
Read Revelation 14:6–7 in full and note the speaker, audience, scope of the proclamation, and each command. The angel announces an everlasting gospel, calls humanity to fear God and give God glory, announces the hour of judgment, and calls people to worship the One who made heaven, earth, sea, and springs of water. Record what is explicit before adding a theological interpretation.

## The Seventh-day Adventist reading
Seventh-day Adventists understand the three messages as a central part of their end-time mission. Their reading connects the call to worship the Creator with creation, the Sabbath, accountability before God, and a final worldwide gospel appeal. This is a defined denominational interpretation informed by how Adventists read Revelation alongside other biblical books; it should not be confused with the only interpretation held by all Christians.

## Questions for interpretation
What does “everlasting gospel” contribute to the call to worship? How do Genesis 1–2 and Psalm 96 illuminate creation language? What is the relationship between judgment and good news in this passage? What can be concluded directly from the passage, and what requires a wider prophetic framework?

## Compare fairly
Other Christians may agree that the passage calls for faithful worship while disagreeing about its historical timetable, the place of the Sabbath, and the identity of the final events. A fair comparison identifies these differences rather than assuming that every tradition uses Adventist definitions.

## Reflection and practice
Ask how the passage's call to worship should shape humility, service, truthfulness, and care for other people. Do not use it to claim that a neighbour's faith makes that neighbour evil. A responsible interpretation can be deeply committed and still represent disagreement honestly.""",
                "sources": [
                    {"label": "Revelation 14:6–7", "url": "https://www.biblegateway.com/passage/?search=Revelation%2014%3A6-7"},
                    {"label": "Adventist official Fundamental Beliefs", "url": "https://gc.adventist.org/beliefs/"},
                ],
                "quiz": [
                    {"question": "Which statement best separates text from interpretation?", "options": ["Revelation 14 calls for Creator worship; linking it to a specific end-time timetable is an interpretive step that needs evidence.", "Every Christian denomination uses the same prophetic timetable.", "The text names every present-day church directly.", "No context is necessary when reading a vision."], "answer_index": 0, "explanation": "The passage contains explicit wording; historical and denominational applications need their own transparent reasoning."},
                ],
            },
            {
                "slug": "babylon-and-competing-readings",
                "title": "Second Message: Babylon and Competing Interpretations",
                "minutes": 25,
                "preview": False,
                "reference": "Revelation 14:8; Revelation 17–18; Daniel 7",
                "content": """# Read the symbol in its literary setting
The second angel announces Babylon's fall. Read Revelation 14:8 together with Revelation 17–18 and pay attention to the book's own imagery, repeated terms, narrative setting, and descriptions of corruption, wealth, coercion, and opposition to God. A symbolic name should not automatically be applied to a modern community without stating the interpretive steps and evidence.

## The Adventist historicist interpretation
Seventh-day Adventist teaching has a distinctive historicist reading of Babylon that relates the symbol to religious confusion and systems that oppose God's truth, with more detailed claims found in Adventist prophetic interpretation. Present that reading as Adventist teaching and consult official Adventist materials when describing its specific conclusions. The symbol has a contested history among Christians; it is not a neutral label that can responsibly be used to insult individual believers.

## Other Christian frameworks
Preterist interpreters tend to give substantial attention to the historical world of the earliest Christian communities and imperial power. Futurist interpretations expect key visions to have a major future fulfilment. Idealist or symbolic approaches emphasize recurring patterns of idolatry, oppression, and compromised allegiance. These categories are broad, overlap in practice, and do not describe every theologian perfectly.

## Debate questions
Which details of Revelation 17–18 does each reading explain well? How does a reading account for the original audience and the wider book? What evidence would count against a proposed identification? What harms arise when an interpretive claim is turned into a personal accusation against people whose beliefs are more varied than the label suggests?

## A fair conclusion
State the Adventist interpretation accurately, then summarize a credible alternative in terms its informed adherents would recognize. Identify shared concerns, real disagreements, and open questions. Do not claim that a current denomination, ethnic group, or individual is Babylon based solely on polemics, headlines, or an unverified chart.""",
                "sources": [
                    {"label": "Revelation 14:8", "url": "https://www.biblegateway.com/passage/?search=Revelation%2014%3A8"},
                    {"label": "Revelation 17–18", "url": "https://www.biblegateway.com/passage/?search=Revelation%2017-18"},
                    {"label": "Adventist official beliefs", "url": "https://gc.adventist.org/beliefs/"},
                ],
                "quiz": [
                    {"question": "How should a proposed identification of Babylon be presented?", "options": ["As a sourced interpretation with its reasoning, alternatives, and limits.", "As permission to demean members of another church.", "As an uncontested fact even when Christians disagree.", "As a claim that does not need the biblical passage."], "answer_index": 0, "explanation": "Interpretive claims need evidence and careful distinctions between systems, doctrines, and individual believers."},
                ],
            },
            {
                "slug": "beast-mark-conscience-and-perseverance",
                "title": "Third Message: Allegiance, Conscience, and Perseverance",
                "minutes": 28,
                "preview": False,
                "reference": "Revelation 13–14; Exodus 20:8–11; Romans 14:1–13",
                "content": """# The warning and its setting
Read Revelation 13 before Revelation 14:9–12. Record what the vision says about worship, coercion, the beast and its image, the mark, endurance, and the commandments of God. The imagery is apocalyptic, so interpretive claims should be tested against the passage, its earlier biblical allusions, and the book's message to its readers.

## The Adventist interpretation
Seventh-day Adventist historicist teaching connects the third message with end-time allegiance, worship, the authority of God, the commandments, and the Sabbath. It interprets the beast and mark within a specific reading of prophecy and church history. Explain that framework from official sources and acknowledge which steps are interpretive rather than explicit labels supplied by the passage itself.

## Other readings and critical questions
Other Christians interpret the beast, mark, and worship imagery in ways that emphasize first-century imperial pressure, future events, recurring political idolatry, or several horizons at once. Ask each interpretation the same questions: What does it explain? Which passages support it? How does it handle difficult details? What would challenge its conclusion? Avoid assuming that a disagreement itself proves bad faith.

## Conscience and religious liberty
Whatever the interpretation, religious claims must not be used to intimidate, threaten, or deny the dignity of people from other traditions. Romans 14 is one useful Christian passage for thinking about disputes in conscience, though its exact relevance to Revelation is itself a matter for interpretation. Discuss doctrine frankly while respecting freedom of belief.

## Guided debate
Have one position argue the strongest evidence for the Adventist historicist reading. Have a second position present a well-sourced alternative. Ask each side to identify its own assumptions, answer the other's strongest objection, and admit an unresolved issue. The AI should facilitate analysis, not pronounce one religious community more powerful, spiritually valuable, or humanly worthy than another.

## Guardrails
Do not predict a date for Christ's return, identify a person as the beast without strong and explicit evidence, or use sensational current events as proof. Separate verified facts, a tradition's teaching, and the learner's inference.""",
                "sources": [
                    {"label": "Revelation 13–14", "url": "https://www.biblegateway.com/passage/?search=Revelation%2013-14"},
                    {"label": "Exodus 20:8–11", "url": "https://www.biblegateway.com/passage/?search=Exodus%2020%3A8-11"},
                    {"label": "Romans 14:1–13", "url": "https://www.biblegateway.com/passage/?search=Romans%2014%3A1-13"},
                    {"label": "Adventist official Fundamental Beliefs", "url": "https://gc.adventist.org/beliefs/"},
                ],
                "quiz": [
                    {"question": "What makes a debate about the beast and the mark responsible?", "options": ["Each side uses the text and sources, states assumptions, answers objections, and avoids personal attacks.", "Each side labels living neighbours as evil.", "A modern headline is treated as proof without textual analysis.", "The AI declares one tradition humanly superior."], "answer_index": 0, "explanation": "Responsible debate tests reasoning and evidence without turning symbols into unsupported accusations."},
                ],
            },
        ],
    },
    {
        "slug": "sda-28-fundamental-beliefs",
        "title": "The 28 Fundamental Beliefs — A Complete Adventist Study",
        "summary": "A structured tour of all 28 Seventh-day Adventist Fundamental Beliefs, grouped into the Church's six official doctrine categories and opened to interpretation, questions, and fair comparison.",
        "level": "Foundations to Intermediate",
        "duration_minutes": 110,
        "tier": "free",
        "preview_lesson_slug": None,
        "outcomes": [
            "Name and understand the scope of all 28 official Seventh-day Adventist Fundamental Beliefs.",
            "Distinguish the Church's official statements from personal opinions and scholarly debates.",
            "Read the supporting biblical references in context.",
            "Invite constructive questions and compare with other traditions without caricature.",
        ],
        "sources": [
            {"label": "General Conference of Seventh-day Adventists — official 28 Fundamental Beliefs", "url": "https://gc.adventist.org/beliefs/"},
            {"label": "Adventist.org — What do Adventists believe?", "url": "https://adventist.org/beliefs"},
        ],
        "lessons": [
            {
                "slug": "beliefs-1-5-god",
                "title": "Beliefs 1–5: God, Scripture, and the Trinity",
                "minutes": 20,
                "preview": False,
                "reference": "Fundamental Beliefs 1–5",
                "content": """# The official Adventist framework
The General Conference groups the first five beliefs under God: (1) Holy Scriptures, (2) the Trinity, (3) God the Father, (4) God the Son, and (5) God the Holy Spirit. These are the Seventh-day Adventist Church's official doctrinal statements; this lesson explains their stated meaning rather than claiming that all Christians or all religions formulate them identically.

## Scripture and authority
Belief 1 describes the Old and New Testaments as inspired Scripture and the authoritative revelation of God's will. Study the claim alongside the listed biblical texts, including 2 Timothy 3:16–17 and 2 Peter 1:20–21. Ask how the statement reasons from those texts and how other Christian traditions understand Scripture in relation to church teaching and tradition.

## The Trinity and the three persons
Beliefs 2–5 describe one God as Father, Son, and Holy Spirit, a unity of three coeternal persons. Beliefs 3, 4, and 5 describe the Father, the eternal Son incarnate in Jesus Christ, and the Holy Spirit respectively. The Trinity is a central Christian doctrine but is rejected in Islamic theology; comparing the claims requires careful definitions, not a caricature of either side.

## Questions for interpretation and debate
What does “one God” mean in Trinitarian theology? How do Christians distinguish person from being? What biblical passages do different Christian interpreters emphasize? How does Qur'anic emphasis on God's oneness articulate a different theological framework? First explain each view from its own recognized sources, then discuss objections without insults or pretending that the views are identical.

## Study practice
Write three columns: the official Adventist statement, the textual or historical reasoning offered for it, and questions or alternative explanations. A question is not automatically a rejection, and identifying a difference does not rank the dignity or worth of a believer.""",
                "sources": [
                    {"label": "Official Adventist beliefs 1–5", "url": "https://gc.adventist.org/beliefs/"},
                    {"label": "Qur’an 112 — Al-Ikhlas", "url": "https://quran.com/en/al-ikhlas"},
                    {"label": "Vatican — The Nicene Creed", "url": "https://www.vatican.va/content/catechism/en/part_one/section_one/chapter_three/article_2/the_credo.index.html"},
                ],
                "quiz": [
                    {"question": "What is the most accurate framing of beliefs 1–5?", "options": ["They are the official Seventh-day Adventist formulations about Scripture, the Trinity, the Father, the Son, and the Holy Spirit.", "All religions accept the Trinity in identical terms.", "They are a statement that every Christian tradition rejects Scripture.", "They are personal views that the Church has never published."], "answer_index": 0, "explanation": "The course reports the denomination's published beliefs and then invites careful study and comparison."},
                ],
            },
            {
                "slug": "beliefs-6-7-humanity",
                "title": "Beliefs 6–7: Creation and Human Nature",
                "minutes": 14,
                "preview": False,
                "reference": "Fundamental Beliefs 6–7; Genesis 1–3; Psalm 8",
                "content": """# Two beliefs about humanity and the world
The second category in the official list is Humanity: (6) Creation and (7) Nature of Humanity. Adventist teaching describes God as Creator and human beings as created in God's image, with an embodied, relational nature and a real moral responsibility. Consult the full official statement rather than relying only on an abbreviated label, and read Genesis 1–3 and Psalm 8 in context.

## Interpretation questions
What does it mean to read Genesis as theological testimony about creation, human dignity, responsibility, and rest? How do interpreters account for literary genre and the relationship between Scripture and scientific explanation? Christians and Muslims share important language about God as Creator but do not necessarily interpret the details of creation, human nature, or scriptural authority in the same way.

## Debate without caricature
A good debate defines its question first: historical sequence, literary genre, theological meaning, human dignity, or a scientific claim. Do not confuse disagreement about the genre of Genesis with a person's moral character. State the strongest argument for each position and identify evidence that would change your judgment.

## Practice
Summarize beliefs 6 and 7 in your own words, list the primary texts being used, and mark where the official statement moves from biblical wording to a theological synthesis. Compare one informed Christian or Muslim interpretation using a source from that community. Keep the comparison focused on claims, reasoning, and implications rather than on stereotypes.""",
                "sources": [
                    {"label": "Official Adventist beliefs 6–7", "url": "https://gc.adventist.org/beliefs/"},
                    {"label": "Genesis 1–3", "url": "https://www.biblegateway.com/passage/?search=Genesis%201-3"},
                    {"label": "Qur’an 3:59 and 7:54", "url": "https://quran.com/"},
                ],
                "quiz": [
                    {"question": "Which is the best way to debate creation and human nature?", "options": ["Define the question, read sources in context, and distinguish theological claims from scientific claims.", "Treat every disagreement as proof of ignorance.", "Assume all traditions use Genesis in the same way.", "Avoid sources and rely on stereotypes."], "answer_index": 0, "explanation": "Clear definitions and evidence allow substantive disagreement without misrepresenting people."},
                ],
            },
            {
                "slug": "beliefs-8-11-salvation",
                "title": "Beliefs 8–11: The Great Controversy and Salvation",
                "minutes": 22,
                "preview": False,
                "reference": "Fundamental Beliefs 8–11; Genesis 3; Romans 3–8; Ephesians 2",
                "content": """# The salvation category
The official Adventist category Salvation includes (8) The Great Controversy, (9) The Life, Death and Resurrection of Christ, (10) The Experience of Salvation, and (11) Growing in Christ. Together the statements offer a framework for understanding evil, Christ's saving work, a believer's response, and ongoing spiritual growth.

## The Great Controversy
Belief 8 frames human history within a cosmic conflict between Christ and Satan over God's character, law, and sovereignty. This theme is distinctive in how Adventist theology connects creation, human freedom, evil, salvation, and final restoration. Other religious traditions may discuss evil, temptation, moral struggle, and divine justice without adopting the same cosmic narrative.

## Christ and the experience of salvation
Belief 9 focuses on the life, death, and resurrection of Christ; belief 10 on the experience of salvation; and belief 11 on growth in Christ. Read Romans 3–8 and Ephesians 2 while asking how grace, faith, transformation, obedience, and assurance are related. Christian traditions differ in their precise accounts of justification, sanctification, sacraments, and perseverance; do not reduce those differences to slogans.

## Debate method
Ask each position to explain its primary sources, logic, and implications. In a Catholic–Protestant comparison, for example, describe official Catholic teaching from Catholic sources and the alternative from the relevant Protestant confession or doctrinal statement. In Muslim comparisons, begin with Islamic sources and qualified Muslim scholarship rather than assuming that Christian categories map directly onto Islam.

## Reflection
How does a theory of evil affect the response to suffering? What responsibility remains for human choice and accountability? Does a proposed interpretation explain the full set of sources, and what questions remain open? The aim is accurate understanding, not declaring one community more humanly valuable than another.""",
                "sources": [
                    {"label": "Official Adventist beliefs 8–11", "url": "https://gc.adventist.org/beliefs/"},
                    {"label": "Romans 3–8", "url": "https://www.biblegateway.com/passage/?search=Romans%203-8"},
                    {"label": "Ephesians 2", "url": "https://www.biblegateway.com/passage/?search=Ephesians%202"},
                ],
                "quiz": [
                    {"question": "Which four themes appear in Adventist beliefs 8–11?", "options": ["The Great Controversy, Christ’s life/death/resurrection, the experience of salvation, and growing in Christ.", "Only rules about church buildings.", "Only dietary customs.", "Four identical statements about astronomy."], "answer_index": 0, "explanation": "These are the published titles of beliefs 8–11 in the Salvation category."},
                ],
            },
            {
                "slug": "beliefs-12-16-church",
                "title": "Beliefs 12–16: Church, Mission, Unity, Baptism, Communion",
                "minutes": 18,
                "preview": False,
                "reference": "Fundamental Beliefs 12–16; Matthew 28:18–20; Acts 2; 1 Corinthians 11",
                "content": """# Five beliefs about church life
The Church category includes (12) The Church, (13) The Remnant and its Mission, (14) Unity in the Body of Christ, (15) Baptism, and (16) The Lord's Supper. Belief 13 is especially important for Adventist identity because the denomination understands its mission in relation to biblical end-time prophecy. Describe this claim as an Adventist self-understanding, not a neutral label accepted by every other church.

## Compare authority and belonging
Church traditions differ on continuity with the apostles, visible and invisible church, institutional authority, spiritual gifts, baptism, and the meaning of Communion or the Eucharist. Catholics locate church unity and sacramental life within a particular understanding of apostolic succession and the magisterium; many Protestant communities emphasize other models of authority and membership. Adventists have their own published understanding of remnant and mission.

## Read before concluding
Study Matthew 28:18–20, Acts 2, and 1 Corinthians 11. Identify what the passages explicitly teach, then compare how different traditions relate these passages to formal doctrinal claims. Do not assume that a term such as “remnant” or “Church” means the same thing in every tradition.

## Debate task
Have each position state its own account of church, mission, baptism, and Communion from an official source. Ask what the evidence supports, what the source presupposes, and how the view understands sincere believers outside its membership. The AI should not decide human worth by denominational affiliation.""",
                "sources": [
                    {"label": "Official Adventist beliefs 12–16", "url": "https://gc.adventist.org/beliefs/"},
                    {"label": "Matthew 28:18–20", "url": "https://www.biblegateway.com/passage/?search=Matthew%2028%3A18-20"},
                    {"label": "1 Corinthians 11", "url": "https://www.biblegateway.com/passage/?search=1%20Corinthians%2011"},
                    {"label": "Vatican — Catechism on the Church", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
                ],
                "quiz": [
                    {"question": "How should the term 'remnant' be handled in comparative theology?", "options": ["Explain the Adventist use as its official self-understanding and compare other views accurately.", "Use it as a universal insult for all outside groups.", "Assume all churches define it identically.", "Avoid the official Adventist statement."], "answer_index": 0, "explanation": "A denomination's self-description should be explained faithfully without treating it as a neutral verdict on all other people."},
                ],
            },
            {
                "slug": "beliefs-17-23-daily-living",
                "title": "Beliefs 17–23: Christian Practice and Daily Living",
                "minutes": 18,
                "preview": False,
                "reference": "Fundamental Beliefs 17–23; Exodus 20; Micah 6:8; Matthew 5–7",
                "content": """# Daily Living in seven statements
The official titles in this category are (17) Spiritual Gifts and Ministries, (18) The Gift of Prophecy, (19) The Law of God, (20) The Sabbath, (21) Stewardship, (22) Christian Behavior, and (23) Marriage and the Family. Together they connect community service, spiritual discernment, moral responsibility, time, resources, conduct, and family life.

## Distinctive emphasis and shared questions
Seventh-day Adventists place special emphasis on seventh-day Sabbath observance and understand it through creation, the commandments, worship, rest, and service. Catholic, Orthodox, other Protestant, and Muslim communities have their own teachings and practices related to weekly worship, law, stewardship, marriage, and ethical life. Similar words do not guarantee identical doctrines; differences should be sourced and specific.

## Read and investigate
Read Exodus 20, Micah 6:8, and Matthew 5–7. Ask how justice, mercy, worship, and obedience relate to faith. When a community makes a practical claim, distinguish the official doctrine from how individual families or local congregations apply it. Consult official sources for formal teaching and research for claims about practice.

## Structured debate
Choose one topic such as Sabbath, marriage, stewardship, or spiritual gifts. Give each view equal opportunity to explain its primary source, reasoning, purpose, and strongest objection. Then identify what the evidence settles, what depends on theological premises, and what remains a matter of practice or pastoral judgment.

## Reflection
A doctrine should be represented with enough detail for its adherents to recognize it. Criticism can be direct, but should address the claim rather than stereotyping an entire religion or community.""",
                "sources": [
                    {"label": "Official Adventist beliefs 17–23", "url": "https://gc.adventist.org/beliefs/"},
                    {"label": "Exodus 20", "url": "https://www.biblegateway.com/passage/?search=Exodus%2020"},
                    {"label": "Matthew 5–7", "url": "https://www.biblegateway.com/passage/?search=Matthew%205-7"},
                ],
                "quiz": [
                    {"question": "Which list correctly names several daily-living beliefs?", "options": ["Spiritual gifts, prophecy, law of God, Sabbath, stewardship, Christian behavior, marriage and family.", "The Trinity, the Father, and the Holy Spirit only.", "Babylon, the mark, and three angels only.", "Only the creation account."], "answer_index": 0, "explanation": "These are the official subjects grouped as beliefs 17–23."},
                ],
            },
            {
                "slug": "beliefs-24-28-restoration",
                "title": "Beliefs 24–28: Sanctuary, Return, Resurrection, and New Earth",
                "minutes": 18,
                "preview": False,
                "reference": "Fundamental Beliefs 24–28; Daniel 7–8; John 14; 1 Thessalonians 4; Revelation 20–22",
                "content": """# The Restoration category
The final five official beliefs are (24) Christ's Ministry in the Heavenly Sanctuary, (25) The Second Coming of Christ, (26) Death and Resurrection, (27) The Millennium and the End of Sin, and (28) The New Earth. In Adventist theology these statements form a connected account of Christ's heavenly ministry, hope in Christ's return, the state of the dead and resurrection, the end of evil, and the renewal of creation.

## Read the source passages
Study John 14, 1 Thessalonians 4, Revelation 20–22, and the Daniel passages identified in the full official statements. Record which details are explicit in the passage and which are linked through a wider interpretive framework. The heavenly sanctuary and the detailed Adventist prophetic chronology are particular theological claims that deserve careful, sourced explanation.

## Compare eschatologies
Other Christian traditions agree on some broad hopes—Christ's return, judgment, resurrection, and final renewal—while differing about the state of the dead, the millennium, prophetic sequences, and the relationship between symbols and history. Islam also teaches resurrection and judgment but uses its own scriptural and theological framework. Do not flatten these into interchangeable accounts.

## Debate and uncertainty
Ask an Adventist reading and a well-sourced alternative to explain the same passages, then identify the assumptions and evidence each uses. Avoid date-setting or claims that current events conclusively prove an end-time schedule. A careful study can affirm the seriousness of religious hope without manufacturing fear.

## Final assignment
Make a table of beliefs 24–28, their main claims, primary texts, official explanations, alternative readings, and questions that remain open. Separate the hope a tradition expresses from predictions a reader has added. Assess arguments, not the human worth of their adherents.""",
                "sources": [
                    {"label": "Official Adventist beliefs 24–28", "url": "https://gc.adventist.org/beliefs/"},
                    {"label": "John 14", "url": "https://www.biblegateway.com/passage/?search=John%2014"},
                    {"label": "1 Thessalonians 4", "url": "https://www.biblegateway.com/passage/?search=1%20Thessalonians%204"},
                    {"label": "Revelation 20–22", "url": "https://www.biblegateway.com/passage/?search=Revelation%2020-22"},
                ],
                "quiz": [
                    {"question": "What is a careful approach to different Christian end-time chronologies?", "options": ["Compare how each reads its sources, state uncertainty, and avoid presenting date-setting as verified fact.", "Choose the most frightening prediction.", "Assume all traditions teach an identical millennium.", "Treat a news headline as a final prophetic proof."], "answer_index": 0, "explanation": "Eschatological claims should be assessed against textual reasoning and stated with appropriate uncertainty."},
                ],
            },
        ],
    },
    {
        "slug": "great-controversy-theme",
        "title": "The Great Controversy — Good, Evil, Freedom & Hope",
        "summary": "A deep study of the Great Controversy as an official Seventh-day Adventist theme, its biblical foundations, ethical implications, and serious questions raised by comparative theology and philosophy.",
        "level": "Intermediate",
        "duration_minutes": 70,
        "tier": "free",
        "preview_lesson_slug": None,
        "outcomes": [
            "Describe the official Adventist teaching on the Great Controversy accurately.",
            "Examine biblical texts commonly used to develop the theme.",
            "Debate free will, evil, suffering, divine justice, and restoration with careful reasoning.",
            "Compare related and contrasting Christian and Muslim accounts without claiming they are identical.",
        ],
        "sources": [
            {"label": "Adventist.org — What Is the Great Controversy?", "url": "https://adventist.org/beliefs/official/the-great-controversy"},
            {"label": "General Conference — Fundamental Beliefs, especially belief 8", "url": "https://gc.adventist.org/beliefs/"},
            {"label": "Job 1–2; Genesis 3; Revelation 20–22", "url": "https://www.biblegateway.com/"},
        ],
        "lessons": [
            {
                "slug": "what-adventists-mean-by-great-controversy",
                "title": "The Great Controversy in Adventist Theology",
                "minutes": 23,
                "preview": False,
                "reference": "Fundamental Belief 8; Genesis 3; Job 1–2; Revelation 12",
                "content": """# The official claim
Seventh-day Adventists use “The Great Controversy” to describe a cosmic conflict between Christ and Satan concerning God's character, law, and sovereignty. In official Adventist teaching, the conflict begins with rebellion in heaven, enters human history through sin, and frames the biblical story of salvation and the final end of evil. This is belief 8 in the denomination's 28 Fundamental Beliefs.

## Biblical themes
Read Genesis 3, Job 1–2, and Revelation 12. Note the different literary forms and contexts rather than treating each passage as a simple continuation of one scene. Ask what each text says about accusation, temptation, human freedom, suffering, allegiance, and God's response. The integrated “Great Controversy” framework is a theological synthesis; be clear about the steps by which the passages are brought together.

## What the framework attempts to explain
The Adventist account places moral agency and the public vindication of God's character near the centre of the story of evil and redemption. It also interprets human history within a wider spiritual conflict. A fair lesson distinguishes that doctrinal explanation from empirically established historical claims and from speculative assertions about particular present-day events.

## Comparative lens
Catholic, other Protestant, Orthodox, Muslim, Jewish, and philosophical traditions discuss evil, temptation, suffering, moral responsibility, and divine justice in different ways. Some concepts may be comparable, but they should not be labeled as the same doctrine without evidence. Begin with each tradition's own authoritative or scholarly sources.

## Reflection
Summarize belief 8 as Adventists state it, list its scriptural foundations, and identify one question it answers well and one question that still deserves debate.""",
                "sources": [
                    {"label": "Official Adventist Great Controversy statement", "url": "https://adventist.org/beliefs/official/the-great-controversy"},
                    {"label": "Genesis 3", "url": "https://www.biblegateway.com/passage/?search=Genesis%203"},
                    {"label": "Job 1–2", "url": "https://www.biblegateway.com/passage/?search=Job%201-2"},
                ],
                "quiz": [
                    {"question": "How is the Great Controversy best described in this course?", "options": ["An official Seventh-day Adventist theological framework about Christ, Satan, God's character, human freedom, sin, and restoration.", "A doctrine identical in wording in all religions.", "An established scientific explanation for every historical event.", "A permission to blame a religious group for evil."], "answer_index": 0, "explanation": "The phrase names a defined Adventist teaching; comparisons require careful and sourced distinctions."},
                ],
            },
            {
                "slug": "problem-of-evil-and-free-will",
                "title": "Debating Evil, Freedom, and Divine Justice",
                "minutes": 24,
                "preview": False,
                "reference": "Job 1–2; Genesis 3; Romans 8; Qur’an 2:155–157",
                "content": """# The central questions
Why does suffering exist? Can meaningful freedom include the possibility of wrongdoing? How can divine goodness, power, and justice be understood alongside human suffering? The Great Controversy framework gives one Adventist answer by placing evil in a conflict that God will ultimately end. It should be examined as an argument, not accepted or rejected through caricature.

## Strong questions for the Adventist account
How does this framework explain suffering that appears unrelated to a person's choices? What can be said responsibly about natural disasters and the suffering of children? How does it avoid blaming victims or treating tragedy as proof of a hidden spiritual status? What evidence supports its reading of Job and Revelation, and what remains a theological commitment?

## Other perspectives
Christian traditions include different accounts of providence, freedom, original sin, spiritual warfare, redemption, and the mystery of suffering. Islamic sources speak of trials, patience, accountability, mercy, and divine sovereignty in a distinct theological framework. These are not interchangeable explanations. If the AI compares them, it must cite each perspective from sources its adherents recognize and give each a fair statement of its strongest argument.

## Structured debate
Position A states the Great Controversy account and its best supporting texts. Position B states a credible alternative account of evil and freedom. Each side must acknowledge a serious objection raised by the other, avoid claiming certainty beyond its sources, and state what evidence or premise its conclusion depends on. A facilitator's synthesis may identify strengths, costs, and unresolved problems, but should not claim that one community has greater human worth.

## Ethical test
Does an interpretation make room for compassion, accountability, and helping those who suffer? Reject explanations that blame a victim without evidence. A theological explanation of evil should not become an excuse to ignore preventable harm.""",
                "sources": [
                    {"label": "Job 1–2", "url": "https://www.biblegateway.com/passage/?search=Job%201-2"},
                    {"label": "Romans 8", "url": "https://www.biblegateway.com/passage/?search=Romans%208"},
                    {"label": "Qur’an 2:155–157", "url": "https://quran.com/2/155-157"},
                    {"label": "Adventist official statement", "url": "https://adventist.org/beliefs/official/the-great-controversy"},
                ],
                "quiz": [
                    {"question": "What is an intellectually responsible debate about the problem of evil?", "options": ["Each account states its premises, engages the strongest objection, cites sources, and acknowledges unresolved questions.", "Each side blames sufferers for their own pain.", "The AI claims that every tradition answers the problem identically.", "Only the loudest position is considered."], "answer_index": 0, "explanation": "Serious theodicy debates require accurate sources, direct engagement with objections, and intellectual humility."},
                ],
            },
            {
                "slug": "great-controversy-and-lived-ethics",
                "title": "Hope, Conflict, and Ethics in Everyday Life",
                "minutes": 23,
                "preview": False,
                "reference": "Micah 6:8; Matthew 5:9; Romans 12:17–21; Revelation 21",
                "content": """# From doctrine to practice
A belief about cosmic conflict should not turn ordinary disagreements into a war against neighbours. In Adventist teaching, the Great Controversy concerns God's character and the origin and end of evil; daily application should be tested against the ethical responsibilities to tell the truth, serve others, resist wrongdoing, and protect those who are vulnerable.

## Test an interpretation by its use
Does the interpretation accurately reflect its primary sources? Does it distinguish fact from inference? Does it encourage non-coercive conviction or pressure people through fear? Does it encourage care for people who disagree? Micah 6:8, Matthew 5:9, and Romans 12:17–21 offer useful ethical passages for Christian reflection, though readers must study them in their own contexts.

## Comparative dialogue
A Catholic discussion might emphasize official Catholic teachings on conscience, virtue, social responsibility, and the common good. A Muslim discussion might consult Qur’anic themes of justice, mercy, accountability, and patience. The AI must not invent equivalences or imply that a short passage represents every member of a tradition. It should explain each source's context and note relevant scholarly disagreements.

## Final debate
Choose a practical issue such as responding to injustice, religious disagreement, or suffering. Present a Great Controversy-informed Adventist argument, a second well-sourced theological perspective, and a reasoned ethical assessment. Separate doctrinal premises from publicly verifiable facts. A disagreement may remain unresolved; respectful, truthful conversation is still a meaningful result.

## Personal reflection
Name one action that would reduce harm or help someone who is suffering. Record how the action follows from your reasoning and which assumptions informed it. Theology should lead to careful responsibility, not to suspicion of entire communities.""",
                "sources": [
                    {"label": "Micah 6:8", "url": "https://www.biblegateway.com/passage/?search=Micah%206%3A8"},
                    {"label": "Matthew 5:9", "url": "https://www.biblegateway.com/passage/?search=Matthew%205%3A9"},
                    {"label": "Romans 12:17–21", "url": "https://www.biblegateway.com/passage/?search=Romans%2012%3A17-21"},
                    {"label": "Revelation 21", "url": "https://www.biblegateway.com/passage/?search=Revelation%2021"},
                ],
                "quiz": [
                    {"question": "Which application is most consistent with responsible comparative theology?", "options": ["Evaluate claims carefully while protecting the dignity and freedom of people who disagree.", "Treat every religious disagreement as permission to threaten others.", "Use fear to sell a study plan.", "Assume a person's religion proves their intent."], "answer_index": 0, "explanation": "The course calls for accountable study, ethical responsibility, and non-coercive dialogue."},
                ],
            },
        ],
    },
    {
        "slug": "catholic-muslim-comparative-dialogue",
        "title": "Catholic & Muslim Perspectives — A Shared Study and Debate",
        "summary": "A joint comparative course on God, Jesus and Mary, revelation and authority, worship, salvation, and ethics, using Catholic primary sources and Qur’anic texts without ranking or merging the traditions.",
        "level": "Foundations to Intermediate",
        "duration_minutes": 85,
        "tier": "free",
        "preview_lesson_slug": None,
        "outcomes": [
            "Explain Catholic and Muslim positions from sources their communities recognize.",
            "Identify shared questions and genuine theological disagreements about God, Jesus, Mary, revelation, and practice.",
            "Use AI to stage a balanced debate that gives each view equal analytical care.",
            "Avoid treating either tradition as monolithic or asserting that one has greater human worth.",
        ],
        "sources": [
            {"label": "Vatican — Catechism of the Catholic Church", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
            {"label": "Vatican II — Nostra Aetate, section 3 on Muslims", "url": "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_nostra-aetate_en.html"},
            {"label": "Qur’an 112 — Al-Ikhlas", "url": "https://quran.com/en/al-ikhlas"},
            {"label": "Qur’an 19 — Maryam", "url": "https://quran.com/en/maryam"},
            {"label": "Qur’an 3:45–55 and 4:157–171", "url": "https://quran.com/3/45-55"},
        ],
        "lessons": [
            {
                "slug": "god-and-monotheism",
                "title": "God, Divine Oneness, and the Trinity",
                "minutes": 22,
                "preview": False,
                "reference": "Catholic Catechism; Nicene Creed; Qur’an 112 and 3:64",
                "content": """# Begin with how each tradition describes itself
Catholic Christianity and Islam both affirm one Creator God and make strong claims about divine oneness, but they do not formulate God's nature in the same way. The Catholic Church's official doctrine confesses the Trinity: one God in three coeternal persons, Father, Son, and Holy Spirit. Islam's foundational emphasis on tawhid insists on the absolute oneness of God and rejects associating partners with God; Muslim theologians explain this in varied scholarly traditions.

## The Catholic perspective
Use the Catechism and the Nicene Creed to understand what Catholics mean by the Trinity. It is not, in Catholic doctrine, belief in three gods. Read the official language before criticizing it. Catholics differ in how they explain theological concepts to a general audience, but the Catechism and creed are the appropriate sources for formal doctrine.

## The Muslim perspective
Read Qur’an 112 and Qur’an 3:64 in a recognized translation. Qur’an 112 emphasizes God's oneness and uniqueness. A Muslim account should be described from the Qur’an and recognized Muslim commentary, not from an outsider's assumption about what Muslims mean. Muslims also differ in jurisprudential and theological schools, while maintaining core commitments to God's oneness.

## Where agreement and disagreement meet
Both traditions reject the idea that God is merely one creature among others and affirm worship of the Creator. The Trinity and Islamic tawhid differ substantively: Catholics affirm the Trinity as monotheistic, while Islamic theology rejects that formulation. A fair comparison neither hides this incompatibility nor claims that either community's adherents are unintelligent or immoral.

## Debate protocol
Ask the Catholic position to state its reasoning from its sources. Ask the Muslim position to state its reasoning from its sources. Give both the same amount of space to set definitions, make an argument, and answer the strongest objection. Finish with what each side believes the other has misunderstood and what question remains genuinely disputed.""",
                "sources": [
                    {"label": "Vatican — The Nicene Creed", "url": "https://www.vatican.va/content/catechism/en/part_one/section_one/chapter_three/article_2/the_credo.index.html"},
                    {"label": "Vatican — Catechism", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
                    {"label": "Qur’an 112 — Al-Ikhlas", "url": "https://quran.com/en/al-ikhlas"},
                    {"label": "Qur’an 3:64", "url": "https://quran.com/3/64"},
                ],
                "quiz": [
                    {"question": "Which statement describes the Catholic-Muslim comparison fairly?", "options": ["Both affirm God’s oneness, but Catholic Trinitarian doctrine and Islamic tawhid make distinct and genuinely contested claims.", "Catholic doctrine teaches three gods, according to the Catechism.", "Muslims accept the Trinity in exactly Catholic terms.", "The traditions have no shared theological questions."], "answer_index": 0, "explanation": "An accurate comparison acknowledges shared monotheistic concern and real doctrinal incompatibility without caricature."},
                ],
            },
            {
                "slug": "jesus-mary-and-revelation",
                "title": "Jesus and Mary: Shared Reverence, Different Claims",
                "minutes": 23,
                "preview": False,
                "reference": "Nicene Creed; John 1:1–18; Qur’an 3:45–55; Surah Maryam 19",
                "content": """# Shared figures, different theological accounts
Catholic Christians and Muslims both revere Mary and regard Jesus as an extraordinary figure, but make different claims about Jesus' identity and mission. A careful dialogue avoids treating this overlap as proof that the doctrines are the same.

## Catholic teaching
The Nicene Creed identifies Jesus Christ as the eternal Son who became human, was crucified, died, and rose again. Catholic teaching on Mary is situated within its understanding of Christ, grace, and the Church. Use the Catechism and official creedal texts for doctrine, and distinguish Catholic teaching about Mary from assumptions that every Catholic devotional practice is mandatory or interpreted identically.

## Muslim teaching
The Qur’an honours Mary (Maryam) and Jesus (Isa), describes Jesus as Messiah and messenger, and presents his miraculous birth. Qur’anic accounts do not affirm the Catholic claim that Jesus is God the Son within the Trinity. Read Qur’an 3:45–55 and Surah Maryam in an identified translation. Where Muslim scholars debate how to interpret a passage, note the difference rather than claiming all Muslims speak with one voice.

## The central disagreement
The traditions differ on Jesus' divine status, crucifixion and resurrection claims, and the way revelation should be interpreted. The exact points need to be studied individually, not collapsed into a vague statement that both “believe in Jesus.” This difference can be discussed frankly without ridicule.

## Balanced debate
Give a Catholic advocate space to explain the creedal reasoning and sources, and a Muslim advocate equal space to explain the Qur’anic framework and sources. Each should summarize the other view accurately before challenging it. Use citations for claims, state when a question depends on a faith commitment, and do not pretend that the AI can prove a revelation by simply asserting one side's premises.

## Questions
What does the word “Messiah” mean within each context? What is the role of Mary? How are scripture and later commentary used? Which claims are shared, which are incompatible, and which require a more specialized discussion?""",
                "sources": [
                    {"label": "Vatican — Nicene Creed", "url": "https://www.vatican.va/content/catechism/en/part_one/section_one/chapter_three/article_2/the_credo.index.html"},
                    {"label": "Vatican — Catechism", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
                    {"label": "Qur’an 3:45–55", "url": "https://quran.com/3/45-55"},
                    {"label": "Qur’an 19 — Maryam", "url": "https://quran.com/en/maryam"},
                    {"label": "Qur’an 4:157–171", "url": "https://quran.com/4/157-171"},
                ],
                "quiz": [
                    {"question": "Which statement best captures Catholic and Muslim beliefs about Jesus?", "options": ["Both honor Jesus, but their formal claims about his identity and mission differ substantially.", "Their formal claims about Jesus are identical.", "Islam has no significant tradition about Jesus or Mary.", "Catholicism does not identify Jesus as divine."], "answer_index": 0, "explanation": "The course compares each tradition's own primary sources and does not erase genuine disagreement."},
                ],
            },
            {
                "slug": "scripture-tradition-and-authority",
                "title": "Scripture, Tradition, Qur’an, and Religious Authority",
                "minutes": 20,
                "preview": False,
                "reference": "Catholic Catechism on Scripture and Tradition; Qur’an 4:82; 16:44",
                "content": """# How do communities identify and interpret revelation?
Catholic Christianity receives the Bible as inspired Scripture and understands Sacred Tradition and the teaching office of the Church in relation to the transmission and interpretation of faith. Islam regards the Qur’an as revelation to Muhammad and draws upon hadith, tafsir, legal schools, and scholarly traditions in different ways. These frameworks are not interchangeable; each has its own history and rules of interpretation.

## Catholic sources
Read the relevant sections of the Catechism on Scripture, Tradition, and the Magisterium. Do not reduce Catholic authority to “the pope decides everything”: the actual doctrine includes Scripture, Tradition, bishops, councils, the papal office, and different levels of teaching authority. A careful answer distinguishes dogma, authoritative teaching, theological opinion, and local custom.

## Muslim sources
Read Qur’anic passages in context and note how translation and tafsir affect the discussion. Islamic authority is not structured exactly like the Catholic magisterium. There are diverse Sunni, Shia, and other scholarly histories, and Muslims may differ about legal and theological questions. Describe the source and community being discussed instead of implying that one modern speaker represents all Muslims.

## Compare the methods
Ask how each tradition treats language, historical context, canon, interpretive community, and disagreement. What happens when a difficult text is read literally, figuratively, historically, or through later commentary? Use one concrete passage from each tradition so the debate is about real sources rather than stereotypes.

## Debate
Each side should describe the other's authority system in terms an informed adherent recognizes before identifying objections. Equal treatment does not mean claiming the systems are identical; it means applying the same standards of clarity, evidence, and charity. Record both a strong argument and a serious open question for each side.""",
                "sources": [
                    {"label": "Vatican — Catechism of the Catholic Church", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
                    {"label": "Vatican — Nostra Aetate", "url": "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_nostra-aetate_en.html"},
                    {"label": "Qur’an 16:44", "url": "https://quran.com/16/44"},
                    {"label": "Qur’an 4:82", "url": "https://quran.com/4/82"},
                ],
                "quiz": [
                    {"question": "Why should Catholic and Muslim authority structures not be treated as identical?", "options": ["They developed different sources, institutions, interpretive methods, and internal scholarly traditions.", "All religions have the same leaders and councils.", "Neither tradition has sources for its teachings.", "The question is settled by a stereotype."], "answer_index": 0, "explanation": "Accurate comparison describes each tradition's actual institutions and interpretive histories."},
                ],
            },
            {
                "slug": "worship-salvation-and-shared-ethics",
                "title": "Worship, Salvation, Moral Life, and Shared Questions",
                "minutes": 20,
                "preview": False,
                "reference": "Matthew 5–7; Catholic Catechism; Qur’an 2:177; 5:8; 49:13",
                "content": """# Practice matters as much as formal statements
Catholic and Muslim communities both give importance to prayer, almsgiving, moral life, fasting, mercy, and accountability before God, though their rituals, theology, calendars, and understanding of salvation differ. Similar ethical language should not be used to conceal differences in worship or doctrine.

## Catholic practice and teaching
Catholic life includes liturgical worship, the sacraments, prayer, works of charity, moral formation, and hope in God's grace. The Catechism relates faith to worship and moral life. Catholic practice also varies by rite, culture, family, and individual; separate official teaching from custom and personal experience.

## Muslim practice and teaching
Muslims commonly describe core practices through the Five Pillars, including prayer, almsgiving, fasting in Ramadan, and pilgrimage for those able, alongside the confession of faith. Qur’anic ethics emphasize accountability, charity, justice, and mercy. Islamic traditions have their own jurisprudence and spiritual diversity; do not claim every Muslim practises in exactly the same way.

## Shared ethical inquiry
The traditions can be brought into conversation on care for the poor, family responsibility, honesty, peace, religious freedom, and community life. Use primary sources from both traditions to support any specific claim. Ask where moral aims converge, where the reasons differ, and how people can cooperate without pretending that theological disagreement has disappeared.

## Balanced debate on salvation
A Catholic account should use official Catholic doctrine and a Muslim account should use recognized Qur’anic texts and appropriate Muslim scholarship. Both should be allowed to articulate their understanding of divine mercy, responsibility, repentance, and the final judgment. Avoid equating Catholic sacraments with Islamic practices or declaring one community spiritually more worthy. If the source material does not settle a question, the AI should say so.

## Final reflection
Name one genuine common concern and one meaningful difference. Explain both with sources and in language that a thoughtful Catholic and a thoughtful Muslim could recognize as fair, even if they disagree with your conclusion.""",
                "sources": [
                    {"label": "Vatican — Catechism", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
                    {"label": "Vatican — Nostra Aetate, section 3", "url": "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_nostra-aetate_en.html"},
                    {"label": "Qur’an 2:177", "url": "https://quran.com/2/177"},
                    {"label": "Qur’an 5:8", "url": "https://quran.com/5/8"},
                    {"label": "Qur’an 49:13", "url": "https://quran.com/49/13"},
                ],
                "quiz": [
                    {"question": "What is the proper purpose of the shared Catholic-Muslim study?", "options": ["Identify common concerns and real differences using each tradition's sources, without ranking the worth of adherents.", "Prove that the two traditions are identical.", "Hide all disagreements to avoid discussion.", "Treat one side as the default and the other as inferior."], "answer_index": 0, "explanation": "The course aims for rigorous understanding and respectful debate, not forced agreement or religious hierarchy."},
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


def public_lesson(lesson: dict, *, include_content: bool = True):
    # Keep the legacy argument for older callers; authenticated Faith members
    # now receive the complete lesson without a trial or subscription.
    return {
        "slug": lesson["slug"],
        "title": lesson["title"],
        "minutes": lesson.get("minutes", 10),
        "preview": bool(lesson.get("preview")),
        "reference": lesson.get("reference", ""),
        "locked": False,
        "content": lesson.get("content", ""),
        "sources": list(lesson.get("sources") or []),
        "quiz": public_quiz(lesson),
    }


def public_course(course: dict, *, has_premium_access: bool = True, detail: bool = False):
    # Keep the legacy keyword argument for compatibility, but never gate
    # Faith curriculum content by a subscription or trial.
    result = {
        "slug": course["slug"],
        "title": course["title"],
        "summary": course["summary"],
        "level": course["level"],
        "duration_minutes": course["duration_minutes"],
        "tier": "free",
        "outcomes": list(course.get("outcomes") or []),
        "sources": list(course.get("sources") or []),
        "lesson_count": len(course.get("lessons") or []),
        "locked": False,
        "preview_available": bool(course.get("preview_lesson_slug")),
    }
    if detail:
        result["lessons"] = [
            public_lesson(lesson, include_content=True)
            for lesson in course.get("lessons") or []
        ]
    return result
