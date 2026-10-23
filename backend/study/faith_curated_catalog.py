"""Curated, source-linked starter lessons for RevelaCode Faith & Scripture.

These are original editorial study guides, not copied denominational publications.
They reference Scripture by passage rather than republishing copyrighted translations.
The seed operation is deliberately explicit and admin-only; importing the catalogue
does not happen as a side effect of opening a public GET endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any

from backend.db import get_db

logger = logging.getLogger("revelacode.faith_catalog")
CATALOG_VERSION = 1
AUTHOR = "RevelaCode Faith Editorial"

# All lesson copy is original. Links point to primary or authoritative references.
CATALOG: list[dict[str, Any]] = [
    {
        "slug": "study-a-bible-passage",
        "title": "How to Study a Bible Passage: Context Before Conclusions",
        "summary": "A repeatable method for observing a passage, reading it in context, comparing cross-references, and applying it responsibly.",
        "subcategory": "biblical-literacy",
        "tradition": "Christian — shared study method",
        "minutes": 12,
        "tags": ["Bible study", "interpretation", "context", "hermeneutics", "beginner"],
        "sources": [
            {"label": "BibleProject — How to Read the Bible", "url": "https://bibleproject.com/explore/how-to-read-the-bible/"},
            {"label": "Bible passages for practice: Luke 10:25–37; Acts 17:10–12", "url": "https://www.biblegateway.com/"},
        ],
        "content": """# Purpose
A good Bible study should help a reader understand what a passage says, what it meant in its literary and historical setting, how Christians have interpreted it, and how its message can be lived out today. The goal is not to force a favourite conclusion onto a verse.

## 1. Begin with observation
Read the whole paragraph or scene before isolating a single sentence. Ask: Who is speaking? Who is listening? What happens before and after? Which words, actions, contrasts, repeated ideas, or questions stand out? Write observations before writing interpretations.

## 2. Identify the kind of writing
The Bible contains narrative, poetry, law, wisdom, prophecy, letters, Gospel accounts, and apocalyptic visions. These genres do not all communicate in the same way. A proverb is a compact wisdom saying; a lament uses poetic language; a vision may use symbols. Ask what kind of text you are reading before deciding how to read it.

## 3. Restore the context
Read the surrounding chapter and note the book's wider purpose. Where appropriate, consult a reputable Bible dictionary, historical introduction, or commentary. Separate what the passage explicitly says from background information supplied by a modern source. A historical claim should be traceable to evidence, not just repeated because it sounds plausible.

## 4. Compare related passages carefully
Cross-references can illuminate a theme, but a matching word does not automatically mean two passages make the same point. Compare the speaker, audience, setting, genre, and argument in each text. Let each passage speak on its own terms before building a wider synthesis.

## 5. Distinguish four layers
- **Text:** the words and claims actually present in the passage.
- **Context:** literary, historical, and cultural information relevant to understanding it.
- **Interpretation:** the conclusion a reader or tradition draws from the text.
- **Application:** a reasoned response in contemporary life.

RevelaCode should label these layers clearly. When Christian traditions disagree, state the disagreement fairly and link to sources rather than presenting one tradition's conclusion as if no alternative exists.

## 6. Test the application
Ask whether the proposed application follows from the passage, respects its original audience, and is consistent with the wider moral teaching being considered. Avoid applications that excuse abuse, discrimination, deception, or harm. A spiritual interpretation is not a substitute for professional advice in medical, legal, or safety-critical situations.

## Practice: the Good Samaritan
Read Luke 10:25–37. Observe the lawyer's question, Jesus' story, the people who pass by, the Samaritan's actions, and Jesus' closing question. Then ask why the story challenges the listener's definition of neighbour. Only after that, write one practical application for your own community.

## Reflection questions
1. What can I point to directly in the text?
2. Which part of my interpretation is inference rather than an explicit statement?
3. What credible source could confirm or challenge my historical assumption?
4. What application promotes truth, compassion, justice, and responsibility?

## Further study
Practise the same process with Acts 17:10–12 and James 1:19–27. Keep a short note of your observation, interpretation, sources, and application so that another reader can follow your reasoning.""",
    },
    {
        "slug": "gospel-death-and-resurrection",
        "title": "The Gospel: Jesus’ Life, Death, and Resurrection",
        "summary": "A guided reading across the Gospels and New Testament letters, with questions about grace, reconciliation, resurrection, and Christian hope.",
        "subcategory": "christian-foundations",
        "tradition": "Christian — central New Testament theme",
        "minutes": 14,
        "tags": ["Jesus", "Gospel", "grace", "resurrection", "Christianity"],
        "sources": [
            {"label": "Read Mark 8:27–38; Romans 3:21–26; 1 Corinthians 15:1–28", "url": "https://www.biblegateway.com/"},
            {"label": "Vatican — Catechism of the Catholic Church", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
            {"label": "Seventh-day Adventist Fundamental Beliefs", "url": "https://adventist.org/beliefs/"},
        ],
        "content": """# Why begin with the Gospel?
Christianity is not merely a list of moral rules or predictions about the future. Its central claim is about God's action through Jesus Christ. The New Testament presents Jesus' public ministry, his death, the testimony of his followers to his resurrection, and the hope that this creates for a renewed life and creation.

## Read the passages in their own settings
Start with Mark 8:27–38, where Jesus' identity is connected to suffering and discipleship. Then read Romans 3:21–26, which describes righteousness, grace, redemption, and faith in Paul's argument. Finally, read 1 Corinthians 15:1–28, where Paul summarises the resurrection message and argues that Christian hope depends on Christ's resurrection.

These passages are related, but they are not interchangeable. Mark tells a story about Jesus and his disciples; Romans develops a theological argument; 1 Corinthians addresses questions and problems in a particular community. Note each author's emphasis.

## Grace and response
The New Testament repeatedly connects salvation with God's grace. Christian traditions explain the relationship between grace, faith, baptism, sacraments, obedience, and a transformed life in different ways. A fair study describes the source and scope of those differences before judging them. Do not reduce any tradition to a slogan.

For example, Catholic teaching should be consulted through the Catechism and official Catholic sources; Seventh-day Adventist teaching should be represented through its published Fundamental Beliefs; and other Christian traditions should be represented using their own accountable statements. An AI summary is a guide to research, not an authority over those sources.

## Resurrection and hope
In 1 Corinthians 15, resurrection is not presented as an optional decoration around the Christian message. Paul makes it central to hope beyond death and to the meaning of Christian life now. Read verses 12–28 closely and identify the logic of Paul's argument. Then compare it with the resurrection accounts at the end of the Gospels.

## From belief to practice
The New Testament links faith with love of neighbour, forgiveness, truthfulness, care for people in need, and a willingness to serve rather than dominate. Read James 2:14–18 alongside Ephesians 2:8–10. Ask what each author is addressing; do not assume the passages contradict one another merely because they use faith and works in different arguments.

## Study plan
1. Read Mark 8:27–38 and write down what Jesus asks of disciples.
2. Read Romans 3:21–26 and identify the words Paul uses for grace and redemption.
3. Read 1 Corinthians 15:12–28 and outline the resurrection argument.
4. Compare one official statement from your own Christian tradition with the passages.
5. Record both what you conclude and what remains unresolved.

## Discussion
What changes when the Gospel is understood as both a claim about Jesus and a call to a particular way of life? How can a community discuss differences about salvation without misrepresenting one another or neglecting practical compassion?""",
    },
    {
        "slug": "prophecy-without-date-setting",
        "title": "Reading Daniel and Revelation Responsibly",
        "summary": "An introduction to apocalyptic literature, symbolic imagery, interpretive traditions, and why responsible prophecy study avoids date-setting.",
        "subcategory": "prophecy",
        "tradition": "Christian — comparative interpretation",
        "minutes": 16,
        "tags": ["Daniel", "Revelation", "prophecy", "apocalyptic", "interpretation"],
        "sources": [
            {"label": "Read Daniel 2; Daniel 7; Revelation 1; Matthew 24:36", "url": "https://www.biblegateway.com/"},
            {"label": "Seventh-day Adventist official beliefs, including the Second Coming", "url": "https://adventist.org/beliefs/official/second-coming"},
        ],
        "content": """# What kind of literature are Daniel and Revelation?
Daniel includes court narratives and visions; Revelation is an apocalypse presented as prophecy and a letter to early Christian communities. Both use vivid imagery, repeated patterns, heavenly scenes, beasts, numbers, and conflict between oppressive powers and God's purposes. Readers should first notice these literary features rather than immediately matching every symbol to a modern headline.

## Start with the text
Read Daniel 2 and Daniel 7. List the dream or vision, the images, the interpretation supplied in the text, and the response it calls for. Then read Revelation 1 and note how the opening chapter frames the book around Jesus Christ, witness, endurance, and messages to real communities.

The biblical text sometimes interprets its own symbols. Where it does, begin there. Where it does not, identify the interpretive choices being made. Do not pretend that a disputed identification is a simple quotation from Scripture.

## Interpretive approaches differ
Christian readers have used different approaches to Revelation. Some emphasize events around the first-century churches and Roman imperial context; some see patterns that recur throughout church history; some expect major fulfilments in the future; many readers combine elements of these approaches. Seventh-day Adventists have a distinctive historicist tradition and particular readings of Daniel 7–9 and Revelation 12–14. Those positions should be clearly labelled as Adventist interpretation, alongside other readings where relevant.

A responsible guide can explain a tradition from its own primary sources without claiming that every Christian shares it. Users should be able to see the biblical passage, the proposed interpretation, the tradition it comes from, the reasoning offered, and credible counter-readings.

## Avoid false precision
Matthew 24:36 cautions against claiming knowledge of the day and hour. Throughout history, confident predictions of exact dates have failed and caused real harm. Wars, epidemics, elections, natural disasters, and social changes should not automatically be described as proof that a prophetic timetable has reached a specific point.

When connecting an event to prophecy, distinguish:
- **Verified event:** what reliable reporting or primary records establish.
- **Biblical passage:** the text being considered.
- **Interpretive proposal:** the connection a writer believes may be meaningful.
- **Uncertainty:** what is not known and what reasonable readers dispute.

Do not use fear, urgency, or claims of secret certainty to pressure people into payments, donations, or religious decisions.

## A practical investigation worksheet
1. Record the exact passage and surrounding context.
2. Identify images and any interpretation supplied by the text.
3. Check historical and literary context using reliable reference works.
4. Compare at least two credible interpretations.
5. State what evidence supports each reading and where inference begins.
6. Finish with the ethical or spiritual challenge in the passage without setting a date.

## Reflection
Does this interpretation explain the whole passage or only selected phrases? What evidence could change your view? Does the reading encourage patient faithfulness and care for others, or mainly produce fear of current events? These questions improve study whether you agree with an interpretation or not.""",
    },
    {
        "slug": "three-angels-sda-study",
        "title": "The Three Angels’ Messages: A Seventh-day Adventist Study",
        "summary": "A text-led study of Revelation 14:6–12 with the Seventh-day Adventist interpretation explicitly identified and questions for further investigation.",
        "subcategory": "sda",
        "tradition": "Seventh-day Adventist — denominational perspective",
        "minutes": 15,
        "tags": ["SDA", "Revelation 14", "three angels", "worship", "prophecy"],
        "sources": [
            {"label": "Read Revelation 14:6–12 and Revelation 12:17", "url": "https://www.biblegateway.com/"},
            {"label": "General Conference of Seventh-day Adventists — Fundamental Beliefs", "url": "https://gc.adventist.org/beliefs/"},
        ],
        "content": """# Scope and framing
This lesson presents the Three Angels’ Messages as understood within Seventh-day Adventist teaching. It is not a claim that every Christian denomination interprets Revelation 14 in the same way. Readers should compare the biblical text with the denomination’s official explanation and with other Christian readings.

## Read the full unit
Read Revelation 14:6–12 in one sitting. Mark each messenger, what is announced, the commands given, the warning, and the description of the saints. Then read Revelation 12 and 13 to observe how the surrounding visions develop the themes of conflict, worship, witness, and allegiance.

## First message: everlasting gospel and worship
The first angel announces an everlasting gospel and calls people to fear God, give glory to God, and worship the Creator. The message joins good news with a call to worship and accountability. Compare its language with the creation themes in Genesis 1–2 and the call to worship in Psalm 96. Ask how proclamation of the gospel relates to the treatment of other people.

## Second message: Babylon
The second angel announces the fall of Babylon. In Revelation, Babylon is a symbolic image associated with corruption and opposition to God's purposes. Seventh-day Adventist teaching develops a particular historicist interpretation of Babylon and its relationship to end-time religious confusion. Because the symbol's application is disputed across Christian traditions, explain the Adventist view accurately while marking it as interpretation rather than an uncontested historical fact.

## Third message: warning, worship, and endurance
The third message warns against worship of the beast and its image and describes the endurance of the saints. The meaning of the beast, its mark, and the related symbols has been debated. Adventist interpretation connects this passage with questions of authority, worship, conscience, and end-time allegiance. Study the passages and the denomination's own published explanations before asserting that a contemporary person, church, product, or political leader fulfils the symbols.

## How to conduct a fair study
- Quote or reference the biblical passage accurately and keep surrounding verses in view.
- Identify which claims come directly from Revelation and which are part of an Adventist interpretive framework.
- Read the official statement and a credible alternative interpretation.
- Avoid personal accusations that label neighbours or other denominations as evil based on unverified claims.
- Do not predict a date for Christ's return or use prophecy to frighten people into purchasing a course.

## Questions for a group
1. How does Revelation 14:6 connect the message with the gospel?
2. What does worship mean in the chapter's literary context?
3. Which elements of the Adventist interpretation depend on reading symbols across multiple biblical books?
4. What evidence or textual reasoning do other Christian interpreters offer?
5. How can a believer discuss conscience and worship while respecting the dignity and religious freedom of others?

## Further reading
Consult the Seventh-day Adventist Church's official statement of Fundamental Beliefs and compare the relevant biblical passages directly. A helpful study states the tradition, sources, evidence, and uncertainty openly. Its aim is careful understanding and faithful practice, not sensational headlines.""",
    },
    {
        "slug": "sabbath-scripture-and-traditions",
        "title": "The Sabbath in Scripture: Texts, Practice, and Christian Traditions",
        "summary": "Explore the seventh-day Sabbath through biblical passages and distinguish Adventist teaching from other Christian practices and interpretations.",
        "subcategory": "sda",
        "tradition": "Comparative Christian study — includes SDA perspective",
        "minutes": 13,
        "tags": ["Sabbath", "SDA", "Exodus 20", "Genesis 2", "worship", "Christian traditions"],
        "sources": [
            {"label": "Read Genesis 2:1–3; Exodus 20:8–11; Mark 2:23–28; Acts 20:7; Romans 14:5–6", "url": "https://www.biblegateway.com/"},
            {"label": "Adventist.org — The Sabbath", "url": "https://adventist.org/beliefs/official/the-sabbath"},
        ],
        "content": """# Start with the biblical passages
Read Genesis 2:1–3 and note the seventh day, the divine rest, and the blessing of the day. Read Exodus 20:8–11, where the Sabbath command is connected with creation, and Deuteronomy 5:12–15, where Israel's liberation from slavery is also remembered. Then consider Mark 2:23–28, which places Jesus in a dispute about Sabbath practice.

Acts 20:7 and Romans 14:5–6 are often discussed in Christian debates about worship days and the status of particular days. Read the entire surrounding context for each passage and note that Christians interpret their relationship differently.

## The Seventh-day Adventist perspective
The Seventh-day Adventist Church teaches that the seventh-day Sabbath is a continuing gift and command associated with creation, worship, rest, and service. Its official statement describes Sabbath observance from evening to evening, sunset to sunset, and connects the day with redemption and future hope. This is the denomination's own stated position and should be represented as such.

## Other Christian approaches
Many Christians worship on Sunday and understand it in relation to Jesus' resurrection and early church practice. Christian traditions differ on how the Sabbath command applies under the new covenant, how biblical law relates to Christian practice, and whether Sabbath observance is binding in the same way for all believers. A fair comparison should cite the sources of each tradition rather than treating an opposing view as ignorance or bad faith.

## Practical meaning
Whatever a reader concludes about the day, the biblical theme of rest calls attention to limits on labour, care for people and animals, worship, community, and the dignity of those who are economically vulnerable. In Exodus 20 and Deuteronomy 5, Sabbath is not merely a private ritual; its logic also affects households and servants.

## A comparison table to complete
For each tradition you study, record:
- Which day or practice is emphasized?
- Which biblical texts receive the most weight?
- How is the command related to creation, redemption, Jesus, and the early church?
- Which official source states the position?
- What is a charitable and accurate summary of the alternative view?

## Reflection
How could a weekly practice of rest, worship, and service improve your relationships or work habits? What would it look like to discuss a serious theological disagreement without insulting the people who hold another position?""",
    },
    {
        "slug": "catholic-scripture-tradition",
        "title": "Catholic Approaches to Scripture, Tradition, and Interpretation",
        "summary": "An orientation to the Catholic relationship between Scripture, Sacred Tradition, the teaching office of the Church, and everyday Bible reading.",
        "subcategory": "catholic",
        "tradition": "Catholic — denominational perspective",
        "minutes": 14,
        "tags": ["Catholic", "Bible", "Tradition", "Catechism", "liturgy"],
        "sources": [
            {"label": "Vatican — Catechism of the Catholic Church, section on the deposit of faith", "url": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM"},
            {"label": "Read Luke 24:13–35; 2 Thessalonians 2:15; 2 Timothy 3:14–17", "url": "https://www.biblegateway.com/"},
        ],
        "content": """# What this lesson covers
This lesson outlines a Catholic approach to Scripture and Tradition. It is not intended to speak for every Catholic's personal view, nor to settle disputes between churches. For formal teaching, use the Catechism of the Catholic Church and official Catholic documents.

## Scripture within the life of the Church
Catholic teaching receives the Bible as inspired Scripture and understands Sacred Tradition and Scripture in relation to the Church's transmission of the faith. The Catechism explains how the deposit of faith is entrusted to the Church and how its authentic interpretation is connected to the teaching office of the Church. This differs from Protestant traditions that use the phrase *sola Scriptura* to describe the Bible as the final or sole infallible authority for doctrine, though Protestant positions are not all identical.

For a Catholic reader, interpretation is not only an individual exercise. It takes place within the worshipping community and in conversation with historic teaching, liturgy, and the writings of the Church. For comparative study, describe the Catholic position from Catholic primary sources and describe another tradition using that tradition's own sources.

## Reading a passage
Read Luke 24:13–35. Notice how the disciples' understanding grows as Jesus engages them and interprets the Scriptures, and how recognition occurs in the breaking of bread. Then read 2 Timothy 3:14–17, which speaks about Scripture's role in teaching and formation. Ask what each passage says explicitly and how Catholic teachers connect it to the wider life of faith.

## Liturgy and practice
In Catholic life, Scripture is heard and interpreted as part of the liturgy, including the readings proclaimed at Mass. The Catechism also describes the relationship between prayer, sacramental life, moral responsibility, and the life of the Church. A lesson on Catholic practice should distinguish official teaching from regional customs, personal devotions, and the diversity of Catholic communities worldwide.

## Avoid caricatures
It is inaccurate to say that Catholics do not read the Bible. It is equally inaccurate to claim that all Christians outside Catholicism reject history or community. Traditions place different emphasis on authority, interpretation, sacraments, and church teaching. State the actual difference and cite a primary source.

## Study exercise
1. Read the passages above.
2. Consult the relevant sections of the Catechism.
3. Write a two-column comparison: Catholic teaching as the Catechism presents it; another Christian tradition as its official statement presents it.
4. Identify one point of agreement and one real difference.
5. Ask what evidence each source uses and what questions remain.

## Further reading
Begin with the official Catechism rather than unsourced social media summaries. For Bible passages, use a translation you are permitted to access and quote. RevelaCode's editorial notes should help users investigate sources, not replace the sources themselves.""",
    },
    {
        "slug": "islam-christianity-jesus-comparison",
        "title": "Islam and Christianity: A Respectful Study of Jesus and Scripture",
        "summary": "A carefully framed comparison of Muslim and Christian beliefs about Jesus, revelation, and scripture, with primary-text references and no claim that either community is uniform.",
        "subcategory": "interfaith",
        "tradition": "Interfaith literacy — Muslim and Christian perspectives",
        "minutes": 15,
        "tags": ["Islam", "Christianity", "Jesus", "Quran", "Bible", "interfaith"],
        "sources": [
            {"label": "Qur’an: Surah Maryam 19", "url": "https://quran.com/19"},
            {"label": "Qur’an: Surah An-Nisa 4:157–171", "url": "https://quran.com/4/157-171"},
            {"label": "Bible passages: Mark 8:27–30; John 1:1–18; Romans 10:9–13", "url": "https://www.biblegateway.com/"},
            {"label": "Pew Research Center — Religion research", "url": "https://www.pewresearch.org/religion/"},
        ],
        "content": """# Why compare primary texts?
Islam and Christianity are distinct religious traditions with their own scriptures, histories, schools of interpretation, and communities. Respectful comparison begins by representing each tradition as its informed adherents would recognize it. It does not aim to erase real differences or to score points against another faith.

## Jesus in Christian belief
Christian traditions confess Jesus as the Christ and give central importance to his life, crucifixion, and resurrection. Historic Christian creeds affirm the divinity of Christ, though Christians differ on many other doctrines and practices. Read Mark 8:27–30 and John 1:1–18 to identify the claims those texts make in their own literary settings.

## Jesus in Islamic belief
The Qur’an honours Jesus (Isa) as Messiah and messenger of God and gives Mary (Maryam) a notable role. Islamic teaching rejects central Christian formulations of Jesus as divine Son within the Trinity. Qur’anic passages about the crucifixion and Jesus' status have been interpreted and discussed within Islamic scholarship; Muslims are not a single interpretive bloc, and the lesson should not reduce all Muslims to one contemporary speaker's explanation.

Read Surah Maryam (19) and An-Nisa (4:157–171) in a recognised translation, noting the text itself before consulting an informed commentary. A translation is a rendering of the Arabic text, so cite the translator or edition when discussing exact wording.

## Revelation and authority
Christians regard the Bible as Scripture and have differing views about canon, tradition, and interpretation. Muslims regard the Qur’an as revelation to the Prophet Muhammad and draw on hadith and Islamic scholarly traditions in differing ways. These frameworks are not identical; compare them rather than assuming one-to-one equivalence between the Bible and Qur’an, prophets and apostles, or church and ummah.

## A fair comparison method
- Start with a primary text from each tradition.
- Identify the passage's claims in context.
- Use an accountable source: for Islam, consult recognised Qur’anic translations and reputable Muslim scholarship; for Christianity, consult the text and official or scholarly Christian sources.
- Distinguish a tradition's formal teaching from local culture, individual opinion, and online polemics.
- State disagreements plainly without using insults or implying that ordinary believers are malicious.
- Acknowledge uncertainty where scholars disagree.

## Conversation prompts
1. What does each text explicitly say about Jesus?
2. Which claims are shared, and which are incompatible?
3. How does each community understand revelation and authority?
4. Have you represented the other tradition in a form its informed adherents would accept?
5. What questions should be asked directly and respectfully rather than inferred?

## Editorial note
RevelaCode provides comparative literacy, not a religious ruling and not a substitute for a pastor, priest, imam, or qualified scholar. Its goal is informed study and respectful conversation, not conversion pressure, hostility, or the exploitation of religious identity.""",
    },
    {
        "slug": "daily-faith-facts-media-literacy",
        "title": "Daily Faith and World Facts: Verify Before You Interpret",
        "summary": "A practical framework for separating verified current events from commentary, theological interpretation, rumours, and predictions.",
        "subcategory": "daily-life",
        "tradition": "All readers — media literacy",
        "minutes": 9,
        "tags": ["daily facts", "current affairs", "verification", "media literacy", "prophecy"],
        "sources": [
            {"label": "Reuters Trust Principles", "url": "https://www.reuters.com/about-us/"},
            {"label": "Associated Press — Standards and ethics", "url": "https://www.ap.org/about/news-values-and-principles/"},
            {"label": "UN News", "url": "https://news.un.org/"},
        ],
        "content": """# A daily fact is not the same as a daily interpretation
A useful Faith Hub should help readers understand the world without turning every headline into a prediction. A reliable daily briefing should state what happened, when it happened, where the information came from, what remains unconfirmed, and when the item was last checked.

## The five-step verification routine
1. **Find the original source.** Look for an official report, court document, data release, direct statement, scientific paper, or full speech where relevant.
2. **Corroborate.** Check whether independent, reputable outlets report the same core facts. For consequential claims, do not rely on a screenshot or a single anonymous post.
3. **Check the date and place.** Old footage and reports can be recirculated as new. Time zones, event dates, and publication dates are not the same.
4. **Read beyond the headline.** Headlines compress nuance. Note what the body of the report supports and what it does not say.
5. **Label uncertainty.** Use terms such as confirmed, reported, disputed, developing, and unverified accurately. Correct errors visibly.

## Keep fact, analysis, and theology separate
A verified report may document a war, election, economic change, disaster, or public statement. An analyst may then discuss its likely causes and implications. A religious reader may reflect on it through a biblical, Islamic, or other theological framework. These are three different activities.

For an event linked to prophecy, show the source of the news report, the exact scriptural passage, the interpretive tradition making the connection, alternative explanations, and the uncertainty. A headline alone cannot establish that a prophecy has been fulfilled. Do not make date predictions or use frightening claims to push a subscription or donation.

## What a trustworthy daily briefing includes
- A short neutral summary in original wording.
- The event date and the reporting/update timestamp.
- Two or more sources for major contested claims when available.
- A visible link to the primary source where practical.
- A separation between verified facts and editorial commentary.
- A correction path for readers and a record of material corrections.

## Daily practice
Choose one story. Write a sentence describing only what the sources confirm. Write a second sentence saying what is not yet known. Then, separately, write a reflection or a question that a faith tradition might bring to the issue. Do not confuse the reflection with evidence about what happened.

## Questions
What source would change your confidence in the story? Does the article cite direct evidence? Is a claim being repeated because it is true, or because it fits a preferred narrative? Good faith and good information both require intellectual honesty.""",
    },
    {
        "slug": "prayer-compassion-everyday-life",
        "title": "Prayer, Reflection, and Practical Compassion",
        "summary": "A seven-day personal practice that connects reflection with gratitude, honesty, relationships, service, and accountability.",
        "subcategory": "daily-life",
        "tradition": "Christian devotional practice",
        "minutes": 10,
        "tags": ["prayer", "devotional", "compassion", "daily practice", "reflection"],
        "sources": [
            {"label": "Read Matthew 6:5–13; Micah 6:8; James 1:19–27", "url": "https://www.biblegateway.com/"},
        ],
        "content": """# A simple practice with real-world consequences
Prayer and reflection can become repetitive if they are disconnected from the way we treat people. This seven-day guide pairs a short reading with one honest question and one practical action. It is a Christian devotional resource; readers from other traditions may adapt the reflective structure to their own practice.

## Day 1 — Attention
Read Matthew 6:5–8. Consider the difference between sincere prayer and performing spirituality for public approval. Action: set aside a quiet period without posting about it or measuring it by likes.

## Day 2 — Gratitude
Name three specific things for which you are grateful. Make the list concrete rather than generic. Action: thank one person who contributed to your day and explain what their action meant.

## Day 3 — Honest speech
Reflect on the effect of careless words. Read James 1:19–20. Action: before repeating a claim about another person or community, verify it and consider whether sharing it is necessary.

## Day 4 — Reconciliation and boundaries
Think about a relationship that needs repair. Action: take responsibility for your part where appropriate. Reconciliation does not require a person to remain in an unsafe situation or to accept abuse; seek trusted support when safety is involved.

## Day 5 — Justice and mercy
Read Micah 6:8. Consider what justice, mercy, and humility look like beyond a private feeling. Action: identify one practical need in your household, school, workplace, or community and take a realistic step to address it.

## Day 6 — Listening
Read James 1:19–27. Action: listen to someone whose experience differs from yours before deciding what they believe. Ask a clear question instead of assuming motives.

## Day 7 — Review and commit
Review the previous six days. Which action was hardest? Which habit should continue? Write one measurable commitment for the coming week and identify what will help you keep it.

## A short journal format
- **Reading:** Which passage did I read?
- **Observation:** What did I notice in the text?
- **Reflection:** What question does this raise for me?
- **Action:** What practical, safe, and specific step will I take?
- **Review:** What happened when I followed through?

The point is not to earn spiritual worth through productivity. The point is to make reflection honest and to let conviction lead toward compassion, integrity, and responsible action.""",
    },
    {
        "slug": "revelation-reading-across-traditions",
        "title": "Revelation Across Christian Traditions: A Comparative Reading Guide",
        "summary": "Compare preterist, historicist, futurist, and idealist approaches to Revelation without presenting one interpretive framework as universally accepted.",
        "subcategory": "prophecy",
        "tradition": "Comparative Christian study",
        "minutes": 13,
        "tags": ["Revelation", "preterist", "historicist", "futurist", "idealist", "SDA"],
        "sources": [
            {"label": "Read Revelation 1–3 and 12–14", "url": "https://www.biblegateway.com/"},
            {"label": "Seventh-day Adventist Church — official beliefs", "url": "https://gc.adventist.org/beliefs/"},
        ],
        "content": """# Why compare interpretations?
Revelation has inspired hope, worship, resistance to oppression, and intense controversy. Its symbols and chronology have been read through different interpretive frameworks. Comparing those frameworks helps a reader see what assumptions are doing the work in an argument.

## Four broad approaches
- **Preterist readings** emphasize how much of Revelation addressed circumstances of the first-century churches and their historical world.
- **Historicist readings** understand the visions as tracing a sequence or panorama of events through Christian history. Seventh-day Adventism has a notable historicist tradition.
- **Futurist readings** expect major sections of the book, especially later visions, to refer to events still future from the reader's perspective.
- **Idealist or symbolic readings** emphasize recurring patterns of conflict between faithful witness and forces opposed to God rather than one continuous dated timeline.

These are broad labels; scholars and church traditions combine or qualify them in different ways. They are a map for comparison, not four perfectly uniform camps.

## Read the text first
Read Revelation 1–3 and ask who is addressed, what each community is praised or challenged for, and what promises are offered. Then read Revelation 12–14 and track the recurring themes of worship, witness, endurance, deception, and allegiance. Note which details the text explains and which are supplied by the interpreter.

## Compare evidence, not confidence
For each interpretation, record its historical assumptions, how it handles the whole book, which passages it connects, and what difficulties critics identify. A confident speaker is not automatically a reliable interpreter. A good case should be understandable, sourced, open about uncertainty, and fair to other readings.

## The role of the Adventist perspective
Adventist interpretation uses a historicist framework for important passages and gives Revelation 12–14 a central place in its understanding of the church's mission. This is a legitimate topic for careful study but should be labelled rather than assumed to be the position of every Christian. Consult official Adventist statements to learn how the church describes its view.

## Ethics of prophecy teaching
Avoid naming living people or groups as prophetic villains without strong, accountable evidence. Do not declare that a disaster or political event proves a specific prophetic timeline. Avoid exact-date predictions, fear-based claims, and pay-to-access warnings about allegedly imminent catastrophe.

## Study exercise
Choose one symbol in Revelation 12–14. Record the passage, its literary context, two interpretive explanations, the source for each explanation, and the evidence each offers. End with the questions you still have. The purpose is to learn how interpretations are built, not to manufacture certainty.""",
    },
]

def publish_faith_catalog() -> dict[str, Any]:
    """Idempotently publish original curated lessons into the existing study_materials collection."""
    collection = get_db()["study_materials"]
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0
    skipped = 0
    errors: list[dict[str, str]] = []

    for entry in CATALOG:
        try:
            slug = entry["slug"]
            title = entry["title"]
            subcategory = entry["subcategory"]
            content = entry["content"].strip()
            if len(content) < 1200:
                raise ValueError("Editorial minimum content length not met.")

            metadata = {
                "catalog_slug": slug,
                "catalog_version": CATALOG_VERSION,
                "editorial_summary": entry["summary"],
                "tradition": entry["tradition"],
                "estimated_minutes": entry["minutes"],
                "sources": entry["sources"],
                "editorial_review": "requires_theological_review",
                "original_content": True,
                "last_curated_at": now,
            }
            document = {
                "id": f"faith-catalog-v{CATALOG_VERSION}-{slug}",
                "title": title,
                "category": "faith",
                "subcategory": subcategory,
                "material_type": "lesson",
                "content": content,
                "description": entry["summary"],
                "summary": entry["summary"],
                "tradition": entry["tradition"],
                "estimated_minutes": entry["minutes"],
                "sources": entry["sources"],
                "year": datetime.now(timezone.utc).year,
                "author": AUTHOR,
                "tags": entry["tags"],
                "metadata": metadata,
                "ai_enabled": True,
                "published": True,
                "created_at": now,
                "updated_at": now,
            }
            existing = collection.find_one({"metadata.catalog_slug": slug})
            if existing:
                document.pop("created_at", None)
                collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": document},
                )
                updated += 1
                continue

            # Do not overwrite a manually authored lesson that happens to share
            # a title/category/subcategory. Flag it for editorial reconciliation.
            title_collision = collection.find_one({
                "title": title,
                "category": "faith",
                "subcategory": subcategory,
            })
            if title_collision:
                skipped += 1
                continue

            collection.insert_one(document)
            inserted += 1
        except Exception as exc:  # one bad record should not abort the whole seed
            logger.exception("Failed publishing Faith lesson %s", entry.get("slug"))
            errors.append({"slug": str(entry.get("slug", "unknown")), "message": str(exc)})

    return {
        "success": not errors,
        "catalog_version": CATALOG_VERSION,
        "total": len(CATALOG),
        "inserted": inserted,
        "updated": updated,
        "skipped_existing": skipped,
        "errors": errors,
    }
