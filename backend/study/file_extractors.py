from PyPDF2 import PdfReader
from docx import Document


class FileExtractors:


    @staticmethod
    def extract_pdf(path):

        reader = PdfReader(path)

        text = ""

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

        return text


    @staticmethod
    def extract_docx(path):

        doc = Document(path)

        return "\n".join(

            p.text

            for p in doc.paragraphs
        )


    @staticmethod
    def extract_txt(path):

        with open(

            path,

            "r",

            encoding="utf-8"

        ) as f:

            return f.read()