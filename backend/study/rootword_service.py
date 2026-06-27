# backend/study/rootword_service.py

from backend.db import get_db


class RootWordService:


    @staticmethod
    def add_rootword(

        word,
        language,
        strong_number,
        meaning,
        scriptures=None,
        notes=None

    ):

        db = get_db()

        data = {

            "word":word,

            "language":language,

            "strong_number":strong_number,

            "meaning":meaning,

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

        return data


    @staticmethod
    def search(word):

        db = get_db()

        result = db[
            "rootwords"
        ].find_one({

            "$or":[

                {
                    "word":{
                        "$regex":
                        word,
                        "$options":"i"
                    }
                },

                {
                    "strong_number":
                    word
                }
            ]
        })

        if result:

            result["_id"] = str(
                result["_id"]
            )

        return result