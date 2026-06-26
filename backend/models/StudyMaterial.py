# backend/models/StudyMaterial.py

from datetime import datetime
import uuid


class StudyMaterial:

    def __init__(
        self,
        title,
        category,
        subcategory,
        content,
        year=None,
        author="RevelaCode Admin",
        tags=None,
        ai_enabled=True
    ):

        self.id = str(uuid.uuid4())

        self.title = title

        # faith / education
        self.category = category

        # sda / cpa / kcse / university
        self.subcategory = subcategory

        self.content = content

        self.year = year

        self.author = author

        self.tags = tags if tags else []

        self.ai_enabled = ai_enabled

        self.created_at = datetime.utcnow().isoformat()

        self.updated_at = datetime.utcnow().isoformat()


    def to_dict(self):

        return {

            "id": self.id,
            "title": self.title,
            "category": self.category,
            "subcategory": self.subcategory,
            "content": self.content,
            "year": self.year,
            "author": self.author,
            "tags": self.tags,
            "ai_enabled": self.ai_enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
