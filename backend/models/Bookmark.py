# backend/models/Bookmark.py

from datetime import datetime
import uuid


class Bookmark:

    def __init__(
        self,
        user_id,
        material_id
    ):

        self.id = str(
            uuid.uuid4()
        )

        self.user_id = user_id

        self.material_id = material_id

        self.created_at = (
            datetime.utcnow()
            .isoformat()
        )


    def to_dict(self):

        return {

            "id": self.id,
            "user_id": self.user_id,
            "material_id": self.material_id,
            "created_at": self.created_at
        }
