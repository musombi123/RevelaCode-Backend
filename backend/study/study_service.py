# backend/study/study_service.py

import os
import json

from backend.db import get_db


BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

STUDY_PATH = os.path.join(

    BASE_DIR,

    "user_data",

    "study_materials"
)


class StudyService:


    @staticmethod
    def get_categories():

        return [

            "faith",
            "education"
        ]


    @staticmethod
    def get_materials(

        category=None,
        subcategory=None,
        file_type=None

    ):

        db = get_db()

        query = {}

        if category:

            query[
                "category"
            ] = category

        if subcategory:

            query[
                "subcategory"
            ] = subcategory

        if file_type:

            query[
                "file_type"
            ] = file_type

        try:

            materials = list(

                db[
                    "study_materials"
                ].find(
                    query
                )

            )

            for item in materials:

                item["_id"] = str(
                    item["_id"]
                )

            return materials


        except Exception:

            # fallback to local files

            return StudyService.load_local(
                category
            )


    @staticmethod
    def load_local(
        category=None
    ):

        materials=[]

        if not os.path.exists(
            STUDY_PATH
        ):

            return []

        for root,dirs,files in os.walk(
            STUDY_PATH
        ):

            for file in files:

                if not file.endswith(
                    ".json"
                ):

                    continue

                try:

                    path=os.path.join(
                        root,
                        file
                    )

                    with open(

                        path,
                        "r",
                        encoding="utf-8"

                    ) as f:

                        data=json.load(f)

                    if category:

                        if data.get(
                            "category"
                        ) != category:

                            continue

                    materials.append(
                        data
                    )

                except Exception as e:

                    print(
                        f"Read error:{e}"
                    )

        return materials


    @staticmethod
    def get_material_by_id(
        material_id
    ):

        db=get_db()

        material=db[
            "study_materials"
        ].find_one({

            "_id":material_id

        })

        if material:

            material["_id"]=str(
                material["_id"]
            )

        return material


    @staticmethod
    def search_materials(
        query
    ):

        db=get_db()

        results=list(

            db[
                "study_materials"
            ]

            .find({

                "$or":[

                    {

                        "title":{

                            "$regex":
                            query,

                            "$options":"i"
                        }
                    },

                    {

                        "content":{

                            "$regex":
                            query,

                            "$options":"i"
                        }
                    },

                    {

                        "tags":{

                            "$regex":
                            query,

                            "$options":"i"
                        }
                    }

                ]

            })

        )

        for item in results:

            item["_id"]=str(
                item["_id"]
            )

        return results