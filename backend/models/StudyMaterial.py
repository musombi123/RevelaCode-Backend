# backend/models/StudyMaterial.py

from datetime import datetime
import uuid


class StudyMaterial:

    def __init__(

        self,

        title,
        category,
        subcategory,

        content=None,

        material_type="lesson",

        file_path=None,

        year=None,

        author="RevelaCode Admin",

        tags=None,

        metadata=None,

        ai_enabled=True
    ):

        self.id = str(
            uuid.uuid4()
        )

        self.title = title

        self.category = category

        self.subcategory = subcategory


        # lesson | pdf | docx | pptx
        # image | audio | rootword

        self.material_type = (
            material_type
        )


        self.content = content

        self.file_path = (
            file_path
        )

        self.year = year

        self.author = author

        self.tags = (
            tags or []
        )

        self.metadata = (
            metadata or {}
        )

        self.ai_enabled = (
            ai_enabled
        )

        self.created_at = (
            datetime.utcnow()
            .isoformat()
        )

        self.updated_at = (
            datetime.utcnow()
            .isoformat()
        )


    def to_dict(self):

        return {

            "id":
            self.id,

            "title":
            self.title,

            "category":
            self.category,

            "subcategory":
            self.subcategory,

            "material_type":
            self.material_type,

            "content":
            self.content,

            "file_path":
            self.file_path,

            "year":
            self.year,

            "author":
            self.author,

            "tags":
            self.tags,

            "metadata":
            self.metadata,

            "ai_enabled":
            self.ai_enabled,

            "created_at":
            self.created_at,

            "updated_at":
            self.updated_at
        }