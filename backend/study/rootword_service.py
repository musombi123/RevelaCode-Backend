from backend.db import get_db


class RootWordService:

    @staticmethod
    def add_rootword(

        word,
        language,
        strong_number,

        transliteration=None,

        meaning=None,

        scriptures=None,

        notes=None
    ):

        db = get_db()

        existing = db[
            "rootwords"
        ].find_one({

            "$or":[

                {
                    "word":word
                },

                {
                    "strong_number":
                    strong_number
                }
            ]
        })

        if existing:

            existing["_id"] = str(
                existing["_id"]
            )

            return {

                "success":False,

                "message":
                "Root word already exists",

                "data":
                existing
            }


        data = {

            "word":word,

            "language":
            language,

            "strong_number":
            strong_number,

            "transliteration":
            transliteration,

            "meaning":
            meaning,

            "scriptures":
            scriptures or [],

            "notes":
            notes or []
        }


        result = db[
            "rootwords"
        ].insert_one(
            data
        )

        data["_id"] = str(
            result.inserted_id
        )

        return {

            "success":True,

            "data":
            data
        }
