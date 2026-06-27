# backend/study/material_preferences.py

from backend.db import get_db
from datetime import datetime


class MaterialPreferences:

    COLLECTION = "study_preferences"


    @staticmethod
    def save_preferences(
        user_id,
        preferences
    ):

        db = get_db()

        db[
            MaterialPreferences.COLLECTION
        ].update_one(

            {
                "user_id": user_id
            },

            {

                "$set": {

                    "preferences":
                    preferences,

                    "updated_at":
                    datetime.utcnow()

                }

            },

            upsert=True

        )

        return {

            "success": True,

            "message":
            "Preferences saved"

        }


    @staticmethod
    def get_preferences(
        user_id
    ):

        db = get_db()

        data = db[
            MaterialPreferences.COLLECTION
        ].find_one(

            {
                "user_id": user_id
            }
        )

        if not data:

            return []

        return data.get(
            "preferences",
            []
        )


    @staticmethod
    def get_recommended_materials(
        user_id
    ):

        db = get_db()

        preferences = (

            MaterialPreferences
            .get_preferences(
                user_id
            )
        )

        if not preferences:

            return []


        materials = list(

            db[
                "study_materials"
            ].find({

                "$or":[

                    {
                        "subcategory":{

                            "$in":
                            preferences
                        }
                    },

                    {
                        "category":{

                            "$in":
                            preferences
                        }
                    },

                    {
                        "tags":{

                            "$in":
                            preferences
                        }
                    },

                    {
                        "material_type":{

                            "$in":
                            preferences
                        }
                    }

                ]

            })

        )


        for item in materials:

            item["_id"] = str(
                item["_id"]
            )


        # -------------------
        # ranking score
        # -------------------

        ranked=[]

        for material in materials:

            score=0


            if material.get(
                "category"
            ) in preferences:

                score += 3


            if material.get(
                "subcategory"
            ) in preferences:

                score += 2


            material_tags = material.get(
                "tags",
                []
            )

            score += len(

                set(
                    material_tags
                )

                &

                set(
                    preferences
                )

            )


            if material.get(
                "material_type"
            ) in preferences:

                score += 2


            material[
                "recommendation_score"
            ]=score


            ranked.append(
                material
            )


        ranked.sort(

            key=lambda x:
                x[
                   "recommendation_score"
                ],

            reverse=True
        )

        return ranked