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
                    }

                ]

            })

        )

        for m in materials:

            m["_id"] = str(
                m["_id"]
            )

        return materials