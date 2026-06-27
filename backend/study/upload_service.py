import os

from uuid import uuid4
from werkzeug.utils import secure_filename


BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

UPLOAD_FOLDER = os.path.join(

    BASE_DIR,

    "user_data",

    "uploads"
)


class UploadService:


    @staticmethod
    def save(file):

        if not os.path.exists(

            UPLOAD_FOLDER
        ):

            os.makedirs(
                UPLOAD_FOLDER
            )

        filename = secure_filename(
            file.filename
        )

        extension = (
            filename.split(
                "."
            )[-1]
        )

        unique_name = (

            f"{uuid4()}.{extension}"
        )

        path = os.path.join(

            UPLOAD_FOLDER,

            unique_name
        )

        file.save(path)

        return path