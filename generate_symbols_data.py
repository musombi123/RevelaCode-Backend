from pathlib import Path
import json

# Create a self-contained generator script in the workspace.
generator = r'''import json
from pathlib import Path

OUTPUT = Path("backend/symbols_data.json")


def source(title, publisher, source_type, url, supports):
    return {
        "title": title,
        "publisher": publisher,
        "type": source_type,
        "url": url,
        "supports": supports,
    }


SYMBOLS = {
    "666": {
        "symbol": "666",
        "title": "The Number of the Beast",
        "summary": "A cryptic number associated with the beast in Revelation 13:18. The passage invites the reader to calculate its significance.",
        "primary_reference": "Revelation 13:18",
        "cross_references": [
            "Revelation 13:16-17",
            "Revelation 14:9-11",
            "Revelation 15:2",
            "Daniel 7:7-8",
            "Revelation 17:9-13",
        ],
        "category": "Apocalyptic Symbol",
        "status": "debated",
        "historical_context": {
            "period": "First century CE",
            "region": "Roman Asia",
            "description": "Revelation emerged in a first-century Roman setting and uses symbolic language about rulers, worship, allegiance, and persecution.",
            "why_it_matters": "The original social and political environment is important when evaluating historical readings of the beast and its number.",
        },
        "textual_context": {
            "chapter_flow": [
                "The beast appears and exercises authority.",
                "A second beast supports the first and directs worship.",
                "The mark, name, and number are connected with economic participation and allegiance.",
                "Revelation 13:18 tells the reader to calculate the number.",
            ]
        },
        "key_question": "What person, system, or symbolic reality does 666 identify?",
        "interpretations": [
            {
                "name": "Neronian / Gematria",
                "type": "Historical-Critical",
                "summary": "A major scholarly proposal connects 666 with Nero Caesar through ancient letter-number calculations.",
                "evidence": [
                    "The text associates the number with a person's name or identity.",
                    "Gematria/isopsephy was known in the ancient world.",
                    "The Neronian reading fits a first-century Roman context.",
                ],
                "challenges": [
                    "The identification depends on language, spelling, and numerical conventions.",
                    "The interpretation does not settle every theological question about the beast.",
                ],
            },
            {
                "name": "Symbolic Humanity / Imperfection",
                "type": "Symbolic",
                "summary": "Some interpreters read 666 as a symbolic expression of human rebellion, incompleteness, or counterfeit perfection.",
                "evidence": [
                    "Revelation repeatedly uses symbolic numbers.",
                    "The number is associated with the beast and opposition to God.",
                ],
                "challenges": [
                    "A purely symbolic reading may understate the text's instruction to calculate the number.",
                ],
            },
            {
                "name": "Historicist",
                "type": "Historicist",
                "summary": "Historicist interpreters may connect the beast and 666 with a long historical sequence involving religious-political power.",
                "evidence": [
                    "Historicist interpretation reads apocalyptic symbols across extended periods of history.",
                ],
                "challenges": [
                    "Specific identifications vary substantially between interpreters.",
                    "Proposed historical mappings can be difficult to test consistently.",
                ],
            },
            {
                "name": "Futurist",
                "type": "Futurist",
                "summary": "Futurist readings place a major portion of the beast's final manifestation in a future end-time setting.",
                "evidence": [
                    "The wider passage is connected with final conflict, worship, allegiance, and judgment.",
                ],
                "challenges": [
                    "Specific future identities are often speculative until the relevant events occur.",
                ],
            },
        ],
        "sda_perspective": {
            "summary": "Seventh-day Adventist interpreters generally connect the beast, worship, and mark themes with a final conflict over allegiance to God. Interpretations of the precise meaning of 666 should be presented as an interpretive tradition rather than as an uncontested fact.",
            "source": "Adventist Biblical Research Institute",
        },
        "textual_variants": [
            {
                "variant": "616",
                "description": "Some ancient textual witnesses preserve 616 rather than 666.",
                "significance": "The variant is important for textual criticism and for theories that connect the number with a personal name.",
            }
        ],
        "curiosity": [
            "Why does Revelation tell the reader to calculate the number?",
            "Why do some manuscripts read 616?",
            "Why is the number connected with a name?",
            "How does Daniel 7 influence Revelation 13?",
        ],
        "related_symbols": [
            "beast",
            "dragon",
            "mark of the beast",
            "seven heads",
            "ten horns",
        ],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Revelation 13:18 explicitly gives the number 666 in the traditional Greek textual form.",
                "The number is associated with the beast.",
                "The reader is told to calculate or reckon the number.",
            ],
            "historical_evidence": [
                "Ancient letter-number systems provide a historical mechanism for numerical name calculations.",
            ],
            "interpretive_claims": [
                "Identifying the number with a particular historical person or later institution is interpretive.",
            ],
            "speculation": [
                "Identifying an unverified modern individual as 666 without strong textual and historical support.",
            ],
        },
        "confidence": {
            "biblical_text": "high",
            "historical_context": "high",
            "specific_identification": "debated",
        },
        "sources": [
            source(
                "A Calculated Exegesis of the Cryptographic Number of the Beast",
                "Adventist Biblical Research Institute",
                "denominational",
                "https://adventistbiblicalresearch.org/articles/a-calculated-exegesis-of-the-cryptographic-number-of-the-beast",
                ["666", "Neronian interpretation", "textual variant 616"],
            ),
            source(
                "Answers to Questions on the Mark of the Beast and End Time Events",
                "Adventist Biblical Research Institute",
                "denominational",
                "https://adventistbiblicalresearch.org/articles/answers-to-questions-on-the-mark-of-the-beast-and-end-time-events",
                ["mark of the beast", "666", "SDA interpretation"],
            ),
            source(
                "The Genre of the Book of Revelation",
                "Oxford Academic",
                "academic",
                "https://academic.oup.com/edited-volume/34244/chapter-abstract/290344770",
                ["genre", "literary context", "historical context"],
            ),
        ],
    },

    "beast": {
        "symbol": "beast",
        "title": "The Beast from the Sea",
        "summary": "A major apocalyptic figure in Revelation 13 representing a power that opposes God, exercises authority, and demands allegiance.",
        "primary_reference": "Revelation 13:1-10",
        "cross_references": [
            "Daniel 7:1-8",
            "Daniel 7:17-27",
            "Revelation 17:7-14",
            "Revelation 19:19-20",
        ],
        "category": "Apocalyptic Figure",
        "status": "debated",
        "historical_context": {
            "period": "First century CE",
            "region": "Roman Mediterranean world",
            "description": "The imagery draws heavily on the beastly kingdoms of Daniel and places political power, worship, persecution, and empire into a symbolic framework.",
            "why_it_matters": "Daniel is an essential intertext for understanding John's beast imagery.",
        },
        "textual_context": {
            "chapter_flow": [
                "The beast rises from the sea.",
                "The dragon gives the beast authority.",
                "The beast receives worship and wages war against the saints.",
                "A second beast later reinforces the first beast's authority.",
            ]
        },
        "key_question": "Does the beast refer to a historical empire, a religious-political system, a future ruler, or a recurring pattern of anti-God power?",
        "interpretations": [
            {
                "name": "Imperial / Historical",
                "type": "Historical-Critical",
                "summary": "The beast can be read against the Roman imperial environment of the first century.",
                "evidence": ["Roman political power is relevant to the original setting."],
                "challenges": ["A strictly first-century reading may not explain every later Christian application."],
            },
            {
                "name": "Historicist",
                "type": "Historicist",
                "summary": "The beast is interpreted as a power unfolding across centuries of Christian history.",
                "evidence": ["Historicist readings emphasize prophetic continuity through history."],
                "challenges": ["Precise institutional identifications vary and remain contested."],
            },
            {
                "name": "Futurist",
                "type": "Futurist",
                "summary": "The beast has a prominent final manifestation shortly before the end.",
                "evidence": ["Revelation connects the beast with final judgment and Christ's victory."],
                "challenges": ["Specific future identities are necessarily provisional."],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist historicist interpretation commonly treats the beast as a religious-political power involved in the final conflict over worship and allegiance.",
            "source": "Adventist Biblical Research Institute",
        },
        "curiosity": [
            "Why does Revelation reuse Daniel's beast imagery?",
            "What is the relationship between the dragon and the beast?",
            "Why does worship become central to the conflict?",
        ],
        "related_symbols": [
            "dragon",
            "false prophet",
            "mark of the beast",
            "666",
            "ten horns",
            "seven heads",
        ],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The beast rises from the sea in Revelation 13.",
                "The dragon gives the beast authority.",
                "The beast is associated with worship, persecution, and authority.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Identifying the beast with a particular institution or empire is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "historical_context": "high",
            "specific_identification": "debated",
        },
        "sources": [
            source(
                "The Genre of the Book of Revelation",
                "Oxford Academic",
                "academic",
                "https://academic.oup.com/edited-volume/34244/chapter-abstract/290344770",
                ["Revelation genre", "context"],
            ),
            source(
                "Answers to Questions on the Mark of the Beast and End Time Events",
                "Adventist Biblical Research Institute",
                "denominational",
                "https://adventistbiblicalresearch.org/articles/answers-to-questions-on-the-mark-of-the-beast-and-end-time-events",
                ["beast", "mark of the beast", "SDA interpretation"],
            ),
        ],
    },

    "false prophet": {
        "symbol": "false prophet",
        "title": "The False Prophet",
        "summary": "The second beast of Revelation 13, later identified with the false prophet, which directs attention toward the first beast and deceptive worship.",
        "primary_reference": "Revelation 13:11-18",
        "cross_references": [
            "Revelation 16:13-14",
            "Revelation 19:20",
            "Revelation 20:10",
        ],
        "category": "Apocalyptic Figure",
        "status": "debated",
        "key_question": "How does deception work alongside political or coercive power?",
        "interpretations": [
            {
                "name": "Religious Deception",
                "type": "Symbolic",
                "summary": "A religious or persuasive power that legitimizes the beast and deceptive worship.",
                "evidence": ["The second beast performs signs and directs worship toward the first beast."],
                "challenges": ["The exact institutional identity remains debated."],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist readings often connect the second beast with religious influence that supports a broader end-time conflict over worship and authority.",
            "source": "Adventist Biblical Research Institute",
        },
        "curiosity": [
            "Why does the second beast look different from the first?",
            "How can religious language be used to support political power?",
        ],
        "related_symbols": ["beast", "mark of the beast", "dragon"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The second beast performs signs.",
                "It directs worship toward the first beast.",
                "Revelation later calls this figure the false prophet.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "specific_identification": "debated",
        },
        "sources": [
            source(
                "Answers to Questions on the Mark of the Beast and End Time Events",
                "Adventist Biblical Research Institute",
                "denominational",
                "https://adventistbiblicalresearch.org/articles/answers-to-questions-on-the-mark-of-the-beast-and-end-time-events",
                ["false prophet", "end-time deception"],
            )
        ],
    },

    "dragon": {
        "symbol": "dragon",
        "title": "The Dragon",
        "summary": "Revelation explicitly identifies the dragon as Satan, the ancient serpent, the deceiver and adversary.",
        "primary_reference": "Revelation 12:9",
        "cross_references": [
            "Genesis 3:1-15",
            "Revelation 13:1-2",
            "Revelation 20:2",
        ],
        "category": "Apocalyptic Figure",
        "status": "textually_defined",
        "key_question": "How does Revelation portray the conflict between God and the dragon?",
        "interpretations": [],
        "sda_perspective": {
            "summary": "The dragon is understood as Satan, whose strategy includes deception, opposition, persecution, and counterfeit authority.",
            "source": "Biblical Research Institute",
        },
        "curiosity": [
            "Why does Revelation connect the dragon with the serpent from Genesis?",
            "How does the dragon transfer authority to the beast?",
        ],
        "related_symbols": ["beast", "false prophet", "woman clothed with the sun"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Revelation 12:9 explicitly identifies the dragon with the devil and Satan.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "specific_identification": "high",
        },
        "sources": [
            source(
                "The Book of Revelation",
                "Bible / Biblical text",
                "primary_text",
                "https://www.biblegateway.com/passage/?search=Revelation%2012%3A9&version=KJV",
                ["dragon identity"],
            )
        ],
    },

    "mark of the beast": {
        "symbol": "mark of the beast",
        "title": "The Mark of the Beast",
        "summary": "A sign associated with allegiance to the beast and with buying and selling in Revelation 13:16-17.",
        "primary_reference": "Revelation 13:16-17",
        "cross_references": [
            "Revelation 14:9-12",
            "Revelation 16:2",
            "Revelation 19:20",
            "Revelation 20:4",
            "Deuteronomy 6:4-8",
            "Exodus 13:9",
        ],
        "category": "Allegiance / End-Time Symbol",
        "status": "debated",
        "key_question": "Is the mark primarily about physical identification, worship allegiance, institutional authority, or a combination?",
        "interpretations": [
            {
                "name": "Worship and Allegiance",
                "type": "Theological",
                "summary": "The mark is interpreted as a visible or practical sign of allegiance to the beast in opposition to God.",
                "evidence": [
                    "Revelation connects the mark with worship.",
                    "Revelation contrasts those who receive the mark with those who keep God's commandments and faith.",
                ],
                "challenges": [],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation commonly emphasizes the final issue of worship, conscience, and authority, especially in relation to Revelation 13-14.",
            "source": "Adventist Biblical Research Institute",
        },
        "curiosity": [
            "Why is the mark connected to both worship and commerce?",
            "Why does Revelation contrast the mark with God's seal?",
            "What is the relationship between the mark and 666?",
        ],
        "related_symbols": ["666", "beast", "false prophet", "seal of God"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The mark is associated with the beast's authority.",
                "The mark is connected with buying and selling.",
                "The mark is associated with worship.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Connecting the mark to a specific modern technology or device is interpretive unless supported by the text and evidence.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "precise_future_form": "debated",
        },
        "sources": [
            source(
                "Answers to Questions on the Mark of the Beast and End Time Events",
                "Adventist Biblical Research Institute",
                "denominational",
                "https://adventistbiblicalresearch.org/articles/answers-to-questions-on-the-mark-of-the-beast-and-end-time-events",
                ["mark", "worship", "666", "SDA interpretation"],
            )
        ],
    },

    "seven seals": {
        "symbol": "seven seals",
        "title": "The Seven Seals",
        "summary": "A sequence of visions in Revelation 6-8 that progressively unfolds judgment, suffering, and divine action within the apocalyptic narrative.",
        "primary_reference": "Revelation 6:1-17",
        "cross_references": ["Revelation 5", "Revelation 8:1"],
        "category": "Apocalyptic Sequence",
        "status": "interpreted",
        "key_question": "Do the seals represent consecutive historical periods, recurring realities, or a future sequence?",
        "interpretations": [
            {
                "name": "Historicist Sequence",
                "type": "Historicist",
                "summary": "The seals are mapped onto stages of Christian history in historicist readings.",
                "evidence": ["The visions appear in a sequence that can be read as historical progression."],
                "challenges": ["Specific dates and mappings differ between interpreters."],
            },
            {
                "name": "Recapitulation / Thematic",
                "type": "Literary",
                "summary": "The seals can be read as a thematic cycle emphasizing suffering, judgment, and God's sovereignty.",
                "evidence": ["Apocalyptic literature often develops themes through repeated cycles."],
                "challenges": [],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist historicist interpretation has traditionally connected the seals with stages in Christian history and the conflict over God's people.",
            "source": "Adventist interpretive tradition",
        },
        "curiosity": [
            "Why does Revelation place the seals in a scroll?",
            "How do the seals relate to the trumpets and bowls?",
        ],
        "related_symbols": ["seven trumpets", "seven churches", "four horsemen"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The Lamb opens the seals.",
                "The visions unfold in sequence.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Specific historical identifications are interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "historical_mapping": "debated",
        },
        "sources": [
            source(
                "The Genre of the Book of Revelation",
                "Oxford Academic",
                "academic",
                "https://academic.oup.com/edited-volume/34244/chapter-abstract/290344770",
                ["apocalyptic structure"],
            )
        ],
    },

    "seven trumpets": {
        "symbol": "seven trumpets",
        "title": "The Seven Trumpets",
        "summary": "A sequence of trumpet visions in Revelation 8-11 involving judgments, warnings, and escalating conflict.",
        "primary_reference": "Revelation 8:2-13",
        "cross_references": ["Revelation 9", "Revelation 10", "Revelation 11"],
        "category": "Apocalyptic Sequence",
        "status": "interpreted",
        "key_question": "Do the trumpets portray historical judgments, symbolic warnings, or future events?",
        "interpretations": [
            {
                "name": "Historicist",
                "type": "Historicist",
                "summary": "Historicist interpreters have linked the trumpets with major historical conflicts and judgments.",
                "evidence": ["The sequence lends itself to historical mapping."],
                "challenges": ["Specific mappings are highly disputed."],
            },
            {
                "name": "Symbolic / Literary",
                "type": "Literary",
                "summary": "The trumpet visions dramatize warning, judgment, and calls to repentance.",
                "evidence": ["The imagery uses biblical plagues and prophetic motifs."],
                "challenges": [],
            },
        ],
        "sda_perspective": {
            "summary": "Historicist Adventist interpretation has traditionally given the trumpets a significant place in the prophetic timeline, while recognizing interpretive questions around specific details.",
            "source": "Adventist interpretive tradition",
        },
        "curiosity": [
            "How are the trumpets related to the Egyptian plagues?",
            "Why is there a pause before the final trumpet?",
        ],
        "related_symbols": ["seven seals", "seven bowls", "plagues"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Seven angels receive trumpets.",
                "The trumpet visions contain judgments and warnings.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Specific historical events proposed as trumpet fulfillments are interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "historical_mapping": "debated",
        },
        "sources": [],
    },

    "Babylon": {
        "symbol": "Babylon",
        "title": "Babylon the Great",
        "summary": "A symbolic city and power in Revelation associated with luxury, corruption, spiritual unfaithfulness, economic power, and opposition to God.",
        "primary_reference": "Revelation 17:1-6",
        "cross_references": [
            "Revelation 18:1-24",
            "Genesis 11:1-9",
            "Isaiah 13:19-22",
            "Jeremiah 50-51",
        ],
        "category": "Apocalyptic City / System",
        "status": "debated",
        "historical_context": {
            "period": "First century CE",
            "description": "The name Babylon evokes the historic Babylonian empire while also functioning as a symbolic label in Revelation.",
            "why_it_matters": "Understanding both historical Babylon and Roman-era symbolism is important for interpretation.",
        },
        "interpretations": [
            {
                "name": "Rome / Imperial Power",
                "type": "Historical-Critical",
                "summary": "Many scholars understand Babylon as a coded reference to Rome or the Roman imperial order.",
                "evidence": ["The imagery fits the political and economic power of the Roman world."],
                "challenges": ["The symbol can also carry broader theological and recurring meanings."],
            },
            {
                "name": "Symbolic World System",
                "type": "Idealist",
                "summary": "Babylon represents recurring systems of wealth, oppression, idolatry, and spiritual corruption.",
                "evidence": ["The imagery goes beyond a single city and portrays a broad network of influence."],
                "challenges": [],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation commonly treats Babylon as a symbolic representation of religious confusion, apostasy, and allied powers opposed to God's truth.",
            "source": "Adventist prophetic tradition",
        },
        "curiosity": [
            "Why does Revelation call Babylon a woman?",
            "Why does Babylon become associated with merchants and economic power?",
            "How does historic Babylon influence John's imagery?",
        ],
        "related_symbols": ["beast", "scarlet woman", "ten kings", "wine"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Babylon is portrayed as wealthy, influential, corrupt, and opposed to God.",
                "Revelation 17-18 connects Babylon with kings and merchants.",
            ],
            "historical_evidence": [
                "Ancient Babylon was a major imperial center and later became a powerful symbolic reference in Jewish literature.",
            ],
            "interpretive_claims": [
                "Equating Babylon with a specific modern institution is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "historical_background": "high",
            "specific_modern_identity": "debated",
        },
        "sources": [
            source(
                "Babylon",
                "The Metropolitan Museum of Art",
                "museum / historical",
                "https://www.metmuseum.org/essays/babylon",
                ["historical Babylon", "ancient context"],
            ),
            source(
                "The Genre of the Book of Revelation",
                "Oxford Academic",
                "academic",
                "https://academic.oup.com/edited-volume/34244/chapter-abstract/290344770",
                ["Revelation context", "symbolism"],
            ),
        ],
    },

    "144000": {
        "symbol": "144000",
        "title": "The 144,000",
        "summary": "A numbered group described as sealed servants of God in Revelation 7 and associated with loyalty, perseverance, and final victory.",
        "primary_reference": "Revelation 7:4",
        "cross_references": ["Revelation 14:1-5", "Revelation 7:9-17"],
        "category": "End-Time People of God",
        "status": "debated",
        "interpretations": [
            {
                "name": "Literal Number",
                "type": "Literal",
                "summary": "The number refers to a specific group of 144,000 people.",
                "evidence": ["The text gives a precise number and tribal listing."],
                "challenges": ["The symbolic structure of Revelation complicates a purely literal reading."],
            },
            {
                "name": "Symbolic Completeness",
                "type": "Symbolic",
                "summary": "The number represents a complete or covenantally organized people of God.",
                "evidence": ["Revelation uses structured numbers symbolically throughout."],
                "challenges": ["The precise relationship between the 144,000 and the great multitude remains debated."],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist interpretations generally associate the 144,000 with a faithful end-time people of God, with debate over how literally the number should be understood.",
            "source": "Adventist Biblical Research Institute",
        },
        "curiosity": [
            "Are the 144,000 and the great multitude the same group?",
            "Why are twelve tribes listed?",
        ],
        "related_symbols": ["seal of God", "great multitude", "Lamb"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The number 144,000 appears in Revelation 7:4.",
                "The group is described as sealed.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Whether the number is literal or symbolic is debated.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "precise_numerical_meaning": "debated",
        },
        "sources": [],
    },

    "new Jerusalem": {
        "symbol": "new Jerusalem",
        "title": "The New Jerusalem",
        "summary": "The holy city descending from God in Revelation 21, representing God's dwelling with redeemed humanity and the restoration of creation.",
        "primary_reference": "Revelation 21:1-4",
        "cross_references": ["Revelation 21:9-27", "Revelation 22:1-5", "Hebrews 12:22"],
        "category": "Restoration / Eschatological City",
        "status": "future",
        "interpretations": [
            {
                "name": "Literal and Symbolic",
                "type": "Theological",
                "summary": "The city can be read as both a real eschatological reality and a symbol of God's restored relationship with humanity.",
                "evidence": ["The text describes concrete features while using rich symbolic imagery."],
                "challenges": [],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist teaching treats the New Jerusalem as part of the future restoration and eternal dwelling of the redeemed with God.",
            "source": "Adventist belief and biblical teaching",
        },
        "curiosity": [
            "Why are there twelve gates and twelve foundations?",
            "Why is there no temple in the city?",
            "Why does the city descend rather than humanity ascend to it?",
        ],
        "related_symbols": ["tree of life", "river of life", "new earth"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The city descends from heaven.",
                "God dwells with humanity.",
                "Death, mourning, crying, and pain are described as passing away.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "future_specificity": "theological",
        },
        "sources": [],
    },

    "lake of fire": {
        "symbol": "lake of fire",
        "title": "The Lake of Fire",
        "summary": "The final judgment image in Revelation associated with the second death and the destruction or punishment of evil.",
        "primary_reference": "Revelation 20:14-15",
        "cross_references": ["Revelation 19:20", "Revelation 20:10", "Revelation 21:8"],
        "category": "Final Judgment",
        "status": "future",
        "interpretations": [
            {
                "name": "Final Destruction",
                "type": "Conditionalist",
                "summary": "Some interpreters understand the lake of fire as the final destruction of sin, sinners, and death rather than endless conscious torment.",
                "evidence": ["Revelation repeatedly calls it the second death."],
                "challenges": ["Other Christian traditions interpret the imagery differently."],
            },
            {
                "name": "Everlasting Punishment",
                "type": "Traditional",
                "summary": "Other Christian traditions understand the image as indicating enduring punishment.",
                "evidence": ["The imagery is severe and linked with judgment."],
                "challenges": ["The exact relation between symbolic fire imagery and duration is debated."],
            },
        ],
        "sda_perspective": {
            "summary": "Seventh-day Adventist teaching understands final punishment as the ultimate destruction of sin and sinners rather than eternal conscious torment.",
            "source": "Seventh-day Adventist fundamental belief on the millennium and end of sin",
        },
        "curiosity": [
            "Why is the lake of fire called the second death?",
            "How does Revelation distinguish the lake of fire from ordinary fire imagery?",
        ],
        "related_symbols": ["second death", "millennium", "judgment"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The lake of fire is associated with the second death.",
                "The beast and false prophet are cast into the lake of fire.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "The exact nature and duration of final punishment remain doctrinally disputed.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "doctrinal_duration": "debated",
        },
        "sources": [],
    },

    "white horse": {
        "symbol": "white horse",
        "title": "The White Horse",
        "summary": "The white horse appears in multiple Revelation visions; context is essential because Revelation 6:2 and Revelation 19:11 are not automatically identical figures.",
        "primary_reference": "Revelation 19:11",
        "cross_references": ["Revelation 6:1-2", "Revelation 19:11-16"],
        "category": "Apocalyptic Image",
        "status": "debated",
        "interpretations": [
            {
                "name": "Christ's Victorious Return",
                "type": "Christological",
                "summary": "Revelation 19 explicitly identifies the rider as Faithful and True and portrays him as the victorious divine king.",
                "evidence": ["The rider is called Faithful and True.", "He judges and makes war in righteousness.", "He is called the Word of God."],
                "challenges": ["Revelation 6:2 presents a different contextual question."],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist readings commonly understand Revelation 19 as Christ's victorious return.",
            "source": "Biblical text and Adventist teaching",
        },
        "curiosity": [
            "Why is the rider in Revelation 19 called the Word of God?",
            "Why should Revelation 6:2 and Revelation 19:11 be compared carefully rather than assumed identical?",
        ],
        "related_symbols": ["Christ", "crown", "battle", "Word of God"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The rider of Revelation 19 is called Faithful and True.",
                "The rider is identified as the Word of God.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "identification_revelation_19": "high",
            "identification_revelation_6": "debated",
        },
        "sources": [],
    },

    "restoration of israel": {
        "symbol": "restoration of israel",
        "title": "Restoration of Israel",
        "summary": "A prophetic theme involving the restoration of Israel; modern political events are sometimes connected with these texts, but the theological identification is debated.",
        "primary_reference": "Ezekiel 37:21-22",
        "cross_references": ["Ezekiel 36:24-28", "Romans 11:25-29", "Isaiah 11:11-12"],
        "category": "Restoration Prophecy",
        "status": "interpretive_association",
        "historical_context": {
            "period": "Ancient Israel and modern history",
            "description": "The prophetic texts address restoration themes in their ancient covenantal setting. Modern interpreters sometimes compare those themes with the establishment of the modern State of Israel in 1948.",
            "why_it_matters": "The historical event of 1948 should be distinguished from the theological claim that it is a direct prophetic fulfillment.",
        },
        "interpretations": [
            {
                "name": "Modern-State Fulfillment",
                "type": "Dispensational / Futurist",
                "summary": "Some interpreters connect modern Israel's establishment with restoration prophecies.",
                "evidence": ["There is a historical event in 1948 that resembles national restoration in broad terms."],
                "challenges": ["The biblical texts have multiple layers of historical, covenantal, and theological context."],
            },
            {
                "name": "Covenantal / Ecclesial",
                "type": "Theological",
                "summary": "Other interpreters place greater emphasis on covenant restoration, the people of God, or fulfillment in Christ and the church.",
                "evidence": ["New Testament writers reinterpret restoration language in theological ways."],
                "challenges": ["Different traditions assign different weight to ethnic, national, and ecclesial dimensions."],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation should be presented carefully and distinguished from dispensational claims. Modern Israel is a historical reality, but connecting specific modern events to specific prophetic fulfillments remains an interpretive question.",
            "source": "Biblical Research Institute / Adventist prophetic interpretation",
        },
        "curiosity": [
            "What does Ezekiel mean by restoration in its original context?",
            "How did early Christians interpret Israel's restoration?",
            "What exactly happened in 1948?",
        ],
        "related_symbols": ["Jerusalem", "dry bones", "remnant"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Ezekiel 37 contains restoration imagery involving Israel.",
            ],
            "historical_evidence": [
                "The modern State of Israel was established in 1948.",
            ],
            "interpretive_claims": [
                "Claiming that 1948 is a direct prophetic fulfillment is an interpretation.",
            ],
            "speculation": [
                "Assigning specific current political events a guaranteed prophetic role without textual and historical support.",
            ],
        },
        "confidence": {
            "historical_event_1948": "high",
            "direct_prophetic_fulfillment": "debated",
        },
        "sources": [
            source(
                "Postwar Refugee Crisis and the Establishment of the State of Israel",
                "United States Holocaust Memorial Museum",
                "historical",
                "https://encyclopedia.ushmm.org/content/en/article/postwar-refugee-crisis-and-the-establishment-of-the-state-of-israel",
                ["1948", "modern Israel"],
            )
        ],
    },

    "nation vs nation": {
        "symbol": "nation vs nation",
        "title": "Nation Rising Against Nation",
        "summary": "Jesus describes wars and rumors of wars as part of the broader pattern of suffering and crisis before the end.",
        "primary_reference": "Matthew 24:7",
        "cross_references": ["Mark 13:7-8", "Luke 21:9-10"],
        "category": "End-Time Sign",
        "status": "ongoing",
        "key_question": "How should believers distinguish recurring history from signs that belong specifically to the end?",
        "interpretations": [
            {
                "name": "Recurring Birth-Pain Pattern",
                "type": "Textual",
                "summary": "Jesus places wars within a broader set of birth-pain signs rather than giving a single calendar date.",
                "evidence": ["Matthew 24 explicitly places wars alongside famine, earthquakes, persecution, and deception."],
                "challenges": ["Modern attempts to identify one war as a definitive fulfillment may go beyond the text."],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist preaching commonly treats global conflict as part of the wider signs of the times while avoiding a single war as a guaranteed fulfillment marker.",
            "source": "Adventist prophetic preaching tradition",
        },
        "curiosity": [
            "Why does Jesus say these things are only the beginning of sorrows?",
            "Can every war be called a fulfillment of Matthew 24:7?",
        ],
        "related_symbols": ["birth pains", "natural calamities", "false prophets"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Jesus mentions nation rising against nation and kingdom against kingdom.",
                "He says these things are the beginning of sorrows.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Assigning a specific war a fulfillment date is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "specific_war_as_fulfillment": "debated",
        },
        "sources": [],
    },

    "rise of false prophets": {
        "symbol": "rise of false prophets",
        "title": "False Prophets",
        "summary": "Jesus warns that deceptive prophets will arise and mislead many, especially in the context of end-time uncertainty.",
        "primary_reference": "Matthew 24:11",
        "cross_references": [
            "Matthew 24:24",
            "Mark 13:22",
            "1 John 4:1",
            "Revelation 16:13-14",
        ],
        "category": "Warning / Deception",
        "status": "ongoing",
        "interpretations": [],
        "sda_perspective": {
            "summary": "Adventist teaching strongly emphasizes testing teachings by Scripture rather than accepting supernatural claims or charismatic authority without examination.",
            "source": "Adventist biblical teaching",
        },
        "curiosity": [
            "How does Jesus say false prophets should be recognized?",
            "Why is deception so prominent in the end-time passages?",
        ],
        "related_symbols": ["false prophet", "beast", "great deception"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Jesus warns that false prophets will arise.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
        },
        "sources": [],
    },

    "natural calamities": {
        "symbol": "natural calamities",
        "title": "Earthquakes, Famines and Calamities",
        "summary": "Jesus and the prophets use earthquakes, famines, pestilence, and other disasters as part of an end-time warning framework.",
        "primary_reference": "Luke 21:11",
        "cross_references": ["Matthew 24:7-8", "Mark 13:8", "Joel 2:30-31"],
        "category": "End-Time Sign",
        "status": "ongoing",
        "key_question": "Are these disasters themselves the fulfillment, or are they signs within a larger pattern?",
        "interpretations": [
            {
                "name": "Birth-Pain Reading",
                "type": "Textual",
                "summary": "The signs are treated as recurring warnings rather than a single event with a fixed date.",
                "evidence": ["Matthew 24:8 calls the signs the beginning of birth pains."],
                "challenges": ["Claims that disasters are objectively increasing in every respect require external data."],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist teaching commonly presents disasters as reminders of a broken world and signs associated with the approach of the end, while encouraging careful interpretation.",
            "source": "Adventist prophetic teaching",
        },
        "curiosity": [
            "Are earthquakes actually increasing, or are they simply reported more widely?",
            "Why does Jesus use birth-pain imagery?",
        ],
        "related_symbols": ["birth pains", "nation vs nation", "sun darkened"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Luke 21:11 mentions earthquakes, famines, and other signs.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "The claim that disasters are steadily increasing in intensity is an empirical claim requiring data.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "global_trend_claims": "requires_data",
        },
        "sources": [],
    },

    "rise of antichrist": {
        "symbol": "rise of antichrist",
        "title": "The Antichrist / Man of Sin",
        "summary": "New Testament texts describe an opposing power characterized by rebellion, deception, or opposition to Christ; exact identification differs among traditions.",
        "primary_reference": "2 Thessalonians 2:3-4",
        "cross_references": [
            "1 John 2:18",
            "Daniel 7:8-25",
            "Revelation 13",
        ],
        "category": "End-Time Figure / Power",
        "status": "debated",
        "interpretations": [
            {
                "name": "Future Individual",
                "type": "Futurist",
                "summary": "A future individual who becomes a major opponent of God and Christ.",
                "evidence": ["Some readings of 2 Thessalonians focus on a distinct end-time person."],
                "challenges": ["The New Testament's antichrist language is broader than one passage and not identical to every beast figure."],
            },
            {
                "name": "Recurring Anti-Christ Power",
                "type": "Symbolic / Historicist",
                "summary": "Anti-Christ can describe a recurring pattern or system opposed to Christ.",
                "evidence": ["1 John uses antichrist language for multiple deceivers rather than only one future individual."],
                "challenges": ["Specific historical applications vary."],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation generally distinguishes between the broader biblical idea of antichrist and the prophetic power represented by the beast of Daniel and Revelation.",
            "source": "Adventist prophetic interpretation",
        },
        "curiosity": [
            "Is 'antichrist' the same thing as the beast?",
            "Why does John use 'antichrist' differently from Revelation?",
        ],
        "related_symbols": ["beast", "little horn", "man of sin"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "2 Thessalonians describes a lawless/opposing figure.",
                "1 John uses antichrist language in the plural as well as in the singular conceptual sense.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Equating all antichrist references with one end-time person is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "exact_identity": "debated",
        },
        "sources": [],
    },

    "ten kings": {
        "symbol": "ten kings",
        "title": "The Ten Kings",
        "summary": "Ten rulers associated with the beast in Revelation 17 who receive authority and participate in the final conflict.",
        "primary_reference": "Revelation 17:12-14",
        "cross_references": ["Daniel 7:7-8", "Daniel 7:24"],
        "category": "Apocalyptic Political Symbol",
        "status": "debated",
        "interpretations": [
            {
                "name": "Symbolic Completeness",
                "type": "Symbolic",
                "summary": "Ten may signify completeness or a complete coalition rather than a fixed modern count.",
                "evidence": ["Apocalyptic literature often uses numbers symbolically."],
                "challenges": ["The text also portrays the kings as acting as a real coalition within the vision."],
            },
            {
                "name": "Future Coalition",
                "type": "Futurist",
                "summary": "A literal future alliance of rulers or nations.",
                "evidence": ["The passage depicts the kings receiving authority for a short period."],
                "challenges": ["No modern alliance can be identified with certainty from the text alone."],
            },
        ],
        "sda_perspective": {
            "summary": "Historicist Adventist interpretation tends to understand the ten horns across the Daniel-Revelation symbolic framework, while avoiding unsupported modern name lists.",
            "source": "Adventist prophetic tradition",
        },
        "curiosity": [
            "Why does Daniel also use ten horns?",
            "Do the ten kings represent ten literal countries?",
        ],
        "related_symbols": ["beast", "ten horns", "Daniel 7"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The ten kings receive authority with the beast.",
                "They are portrayed as participants in the final conflict.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Identifying the ten kings with a modern list of ten nations is speculative.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "modern_identification": "speculative",
        },
        "sources": [],
    },

    "abomination of desolation": {
        "symbol": "abomination of desolation",
        "title": "The Abomination of Desolation",
        "summary": "A Danielic expression reused by Jesus to describe a desecrating event or power associated with severe crisis and the end-time discourse.",
        "primary_reference": "Matthew 24:15",
        "cross_references": [
            "Daniel 9:27",
            "Daniel 11:31",
            "Daniel 12:11",
            "Mark 13:14",
        ],
        "category": "Prophetic Event",
        "status": "debated",
        "historical_context": {
            "period": "Second Temple and first-century Jewish context",
            "description": "The expression has a historical background in Daniel and was interpreted against episodes of desecration in Jewish history.",
            "why_it_matters": "Understanding earlier fulfillments and later reuse by Jesus prevents the expression from being reduced to a single modern prediction.",
        },
        "interpretations": [
            {
                "name": "Historical / Second Temple",
                "type": "Historical-Critical",
                "summary": "Some interpreters connect Danielic language with historical desecrations, particularly under Antiochus IV.",
                "evidence": ["Daniel reflects conflicts connected with the Second Temple period."],
                "challenges": ["Jesus' reuse of the language introduces a further eschatological horizon."],
            },
            {
                "name": "Future Eschatological",
                "type": "Futurist",
                "summary": "Some traditions expect a future desecrating event in connection with end-time crisis.",
                "evidence": ["Jesus uses the phrase in the context of future warning."],
                "challenges": ["The exact form of a future event is not spelled out in modern terms."],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation generally recognizes historical and prophetic layers in Daniel and Matthew while focusing on Christ's warning about deception and crisis.",
            "source": "Adventist prophetic tradition",
        },
        "curiosity": [
            "What did 'abomination of desolation' mean before Jesus used it?",
            "How does Daniel 9 connect with Matthew 24?",
        ],
        "related_symbols": ["temple", "Antiochus", "man of sin"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Jesus explicitly uses Danielic language.",
                "The phrase is connected with desolation and a crisis requiring response.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Identifying a specific modern building or event as the definitive abomination is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "historical_background": "high",
            "future_specificity": "debated",
        },
        "sources": [],
    },

    "four beasts (Daniel)": {
        "symbol": "four beasts (Daniel)",
        "title": "Daniel's Four Beasts",
        "summary": "Daniel 7 presents four beasts rising from the sea, interpreted within the chapter as four kingdoms.",
        "primary_reference": "Daniel 7:3-7",
        "cross_references": ["Daniel 7:17-27", "Revelation 13:1-2"],
        "category": "Kingdom Prophecy",
        "status": "historical_and_interpretive",
        "interpretations": [
            {
                "name": "Babylon-Persia-Greece-Rome",
                "type": "Historicist / Traditional",
                "summary": "A common Christian interpretation associates the four kingdoms with Babylon, Medo-Persia, Greece, and Rome.",
                "evidence": ["The sequence fits a major succession-of-empires reading."],
                "challenges": ["Scholars differ over dating and the identification of the first kingdom."],
            }
        ],
        "sda_perspective": {
            "summary": "Seventh-day Adventist historicist interpretation commonly identifies the four kingdoms as Babylon, Medo-Persia, Greece, and Rome.",
            "source": "Adventist prophetic tradition",
        },
        "curiosity": [
            "Why does Daniel explain the beasts as kingdoms?",
            "How does Revelation reuse Daniel's imagery?",
        ],
        "related_symbols": ["little horn", "ten horns", "beast", "stone cut without hands"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Daniel 7 interprets the four beasts as four kingdoms.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "The identification of the four specific empires is a traditional interpretation.",
            ],
            "speculation": [],
        },
        "confidence": {
            "textual_kingdom_meaning": "high",
            "specific_historical_mapping": "traditional_and_debated",
        },
        "sources": [],
    },

    "stone cut without hands": {
        "symbol": "stone cut without hands",
        "title": "The Stone Cut Without Hands",
        "summary": "Daniel 2 depicts a stone not cut by human hands that strikes the statue and becomes a great mountain, symbolizing God's everlasting kingdom.",
        "primary_reference": "Daniel 2:34-35",
        "cross_references": ["Daniel 2:44-45", "Matthew 21:42-44", "1 Corinthians 10:4"],
        "category": "Kingdom Prophecy",
        "status": "theological",
        "interpretations": [
            {
                "name": "Messianic Kingdom",
                "type": "Christological",
                "summary": "Christian interpretation commonly associates the stone with God's kingdom and ultimately with Christ.",
                "evidence": ["Daniel explicitly says the God of heaven will establish an everlasting kingdom."],
                "challenges": [],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation commonly sees the stone as God's everlasting kingdom that ultimately replaces human kingdoms.",
            "source": "Adventist prophetic tradition",
        },
        "curiosity": [
            "Why is the stone not cut by human hands?",
            "Does the kingdom begin with Christ's first coming or reach its fullest expression at His return?",
        ],
        "related_symbols": ["four beasts", "kingdom of God", "second coming"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "The stone destroys the statue and becomes a mountain filling the earth.",
                "Daniel 2:44 identifies an everlasting kingdom established by God.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Mapping the sequence to detailed modern geopolitical timelines is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "kingdom_application": "theological",
        },
        "sources": [],
    },

    "sun darkened, moon turned to blood": {
        "symbol": "sun darkened, moon turned to blood",
        "title": "The Darkened Sun and Blood-Red Moon",
        "summary": "A biblical cosmic-sign image associated with the Day of the Lord and divine judgment.",
        "primary_reference": "Joel 2:31",
        "cross_references": [
            "Acts 2:20",
            "Matthew 24:29",
            "Revelation 6:12",
        ],
        "category": "Cosmic Sign",
        "status": "debated",
        "interpretations": [
            {
                "name": "Prophetic Symbolism",
                "type": "Symbolic",
                "summary": "The imagery represents cosmic upheaval and divine intervention using prophetic language.",
                "evidence": ["Prophetic texts regularly use heavenly signs to portray major divine acts."],
                "challenges": [],
            },
            {
                "name": "Literal Cosmic Phenomenon",
                "type": "Literal",
                "summary": "Some interpreters expect actual celestial events in the end-time scenario.",
                "evidence": ["The text describes visible changes in the heavenly bodies."],
                "challenges": ["The prophetic literary style makes it difficult to separate literal and symbolic dimensions with certainty."],
            },
        ],
        "sda_perspective": {
            "summary": "Historicist Adventist interpretation has often associated some cosmic signs with major historical events while also recognizing final eschatological fulfillment.",
            "source": "Adventist prophetic tradition",
        },
        "curiosity": [
            "How did Jesus reuse Joel's cosmic-sign language?",
            "Could a literal astronomical event also function symbolically?",
        ],
        "related_symbols": ["earthquake", "day of the Lord", "second coming"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Joel, Acts, Matthew, and Revelation use cosmic-sign imagery.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Identifying a specific historical eclipse or blood moon as the definitive fulfillment is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "specific_historical_event": "debated",
        },
        "sources": [],
    },

    "birth pains": {
        "symbol": "birth pains",
        "title": "Birth Pains",
        "summary": "Jesus compares wars, famines, earthquakes, and other crises to the beginning of birth pains before the culmination of the age.",
        "primary_reference": "Matthew 24:8",
        "cross_references": ["Mark 13:8", "1 Thessalonians 5:3"],
        "category": "End-Time Metaphor",
        "status": "ongoing",
        "interpretations": [
            {
                "name": "Increasing Pressure Before the End",
                "type": "Eschatological",
                "summary": "The image communicates worsening pressure and anticipation of a decisive future event.",
                "evidence": ["The metaphor naturally combines suffering with approaching culmination."],
                "challenges": ["The text does not provide a precise statistical model for escalation."],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist teaching uses the birth-pain metaphor to describe signs that should awaken spiritual readiness rather than date-setting.",
            "source": "Adventist prophetic teaching",
        },
        "curiosity": [
            "Why does Jesus choose birth pains instead of another metaphor?",
            "Why do the signs not immediately mean the end has arrived?",
        ],
        "related_symbols": ["nation vs nation", "natural calamities", "false prophets"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Jesus calls the listed crises the beginning of birth pains.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
        },
        "sources": [],
    },

    "falling away": {
        "symbol": "falling away",
        "title": "The Great Falling Away",
        "summary": "2 Thessalonians 2:3 describes a rebellion or apostasy associated with the events preceding the revelation of the man of lawlessness.",
        "primary_reference": "2 Thessalonians 2:3",
        "cross_references": ["Matthew 24:10-13", "1 Timothy 4:1", "2 Timothy 4:3-4"],
        "category": "Apostasy / Warning",
        "status": "debated",
        "interpretations": [
            {
                "name": "Religious Apostasy",
                "type": "Theological",
                "summary": "A broad movement away from Christian truth and faithfulness.",
                "evidence": ["The New Testament repeatedly warns of doctrinal and moral departure."],
                "challenges": ["The exact scope and timing of the rebellion in 2 Thessalonians are debated."],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist teaching warns of end-time departure from biblical truth and places strong emphasis on Scripture-based discernment.",
            "source": "Adventist teaching",
        },
        "curiosity": [
            "Does 'falling away' mean political rebellion, religious apostasy, or both?",
            "How does this warning connect with false prophets?",
        ],
        "related_symbols": ["false prophets", "man of sin", "deception"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "2 Thessalonians places a rebellion before the revelation of the man of lawlessness.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Calling a specific modern movement 'the great falling away' is interpretive.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "modern_identification": "debated",
        },
        "sources": [],
    },

    "Gog and Magog": {
        "symbol": "Gog and Magog",
        "title": "Gog and Magog",
        "summary": "Figures and nations associated with a final assault against God's people in Ezekiel 38-39 and later reused in Revelation 20.",
        "primary_reference": "Ezekiel 38-39",
        "cross_references": ["Revelation 20:7-10"],
        "category": "End-Time Coalition",
        "status": "debated",
        "interpretations": [
            {
                "name": "Historical-Grographic",
                "type": "Historical-Critical",
                "summary": "Ezekiel's names are studied in relation to ancient geography, peoples, and symbolic enemy imagery.",
                "evidence": ["Ancient texts use geographic names to represent hostile powers."],
                "challenges": ["Modern identifications are often uncertain."],
            },
            {
                "name": "Final Eschatological Coalition",
                "type": "Futurist",
                "summary": "Revelation uses Gog and Magog as a symbol for the final worldwide rebellion against God.",
                "evidence": ["Revelation places the attack at the end of the millennium."],
                "challenges": ["The relationship between Ezekiel and Revelation is interpretively complex."],
            },
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation generally treats Gog and Magog symbolically within the final conflict rather than confidently assigning them to a specific modern nation without evidence.",
            "source": "Adventist prophetic tradition",
        },
        "curiosity": [
            "Why does Revelation reuse names from Ezekiel?",
            "Are Gog and Magog modern countries or symbolic enemies?",
        ],
        "related_symbols": ["great battle", "final rebellion", "dragon"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Ezekiel describes Gog leading a coalition against God's people.",
                "Revelation uses Gog and Magog for the final rebellion.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [
                "Identifying Gog with a modern country is debated.",
            ],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
            "modern_national_identification": "debated",
        },
        "sources": [],
    },

    "days of Noah": {
        "symbol": "days of Noah",
        "title": "As in the Days of Noah",
        "summary": "Jesus uses Noah's generation as a comparison for normal life, moral unpreparedness, and sudden judgment before the Son of Man comes.",
        "primary_reference": "Matthew 24:37-39",
        "cross_references": ["Genesis 6:5-13", "Luke 17:26-27"],
        "category": "Eschatological Parallel",
        "status": "ongoing",
        "interpretations": [
            {
                "name": "Moral Unpreparedness",
                "type": "Theological",
                "summary": "The central parallel is not merely technological or cultural similarity but spiritual unreadiness and surprise.",
                "evidence": ["Jesus emphasizes ordinary life continuing until judgment arrives."],
                "challenges": [],
            }
        ],
        "sda_perspective": {
            "summary": "Adventist interpretation emphasizes readiness, moral discernment, and the suddenness of Christ's return.",
            "source": "Adventist teaching",
        },
        "curiosity": [
            "Why does Jesus focus on ordinary activities like eating and marrying?",
            "What is the main lesson of Noah for end-time readiness?",
        ],
        "related_symbols": ["birth pains", "second coming", "judgment"],
        "evidence_vs_interpretation": {
            "textual_facts": [
                "Jesus compares the time before His return with the days of Noah.",
                "The emphasis is on sudden judgment and lack of readiness.",
            ],
            "historical_evidence": [],
            "interpretive_claims": [],
            "speculation": [],
        },
        "confidence": {
            "biblical_text": "high",
        },
        "sources": [],
    },
}


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": "2.0",
        "generated_for": "RevelaCode Prophecy Explorer",
        "generated_note": (
            "This dataset deliberately separates biblical facts, historical evidence, "
            "interpretive claims, and speculation. Interpretive traditions are labeled "
            "rather than presented as uncontested facts."
        ),
        "symbols": SYMBOLS,
    }

    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"✅ Generated {OUTPUT}")
    print(f"📚 Symbols: {len(SYMBOLS)}")


if __name__ == "__main__":
    main()
'''

path = Path("/mnt/data/generate_symbols_data.py")
path.write_text(generator, encoding="utf-8")

# Run it from a small project-like workspace.
workspace = Path("/mnt/data/revelacode_prophecy_data")
backend = workspace / "backend"
backend.mkdir(parents=True, exist_ok=True)

(workspace / "generate_symbols_data.py").write_text(generator, encoding="utf-8")

import subprocess, sys
result = subprocess.run(
    [sys.executable, str(workspace / "generate_symbols_data.py")],
    cwd=str(workspace),
    capture_output=True,
    text=True,
)

print(result.stdout)
if result.stderr:
    print(result.stderr)

json_path = workspace / "backend" / "symbols_data.json"
print(f"Generated JSON exists: {json_path.exists()}")
print(f"JSON size: {json_path.stat().st_size:,} bytes")
