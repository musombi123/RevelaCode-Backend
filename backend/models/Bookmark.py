# backend/models/Bookmark.py

from datetime import datetime
import uuid


class Bookmark:

    def __init__(

        self,

        user_id,
        material_id,

        material_type="lesson",

        title=None,

        category=None,

        notes=None
    ):

        self.id = str(
            uuid.uuid4()
        )

        self.user_id = user_id

        self.material_id = (
            material_id
        )

        # lesson/pdf/docx/rootword
        self.material_type = (
            material_type
        )

        # quick display title
        self.title = title

        self.category = category

        self.notes = notes

        self.created_at = (
            datetime.utcnow()
            .isoformat()
        )

        self.last_accessed = (
            datetime.utcnow()
            .isoformat()
        )


    def to_dict(self):

        return {

            "id":
            self.id,

            "user_id":
            self.user_id,

            "material_id":
            self.material_id,

            "material_type":
            self.material_type,

            "title":
            self.title,

            "category":
            self.category,

            "notes":
            self.notes,

            "created_at":
            self.created_at,

            "last_accessed":
            self.last_accessed
        }