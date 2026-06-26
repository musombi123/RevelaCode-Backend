# backend/study/ai_context_service.py

from backend.study.study_service import StudyService
from backend.services.ai_router import ask_ai


class AIContextService:

    @staticmethod
    def ask_material_ai(
        material_id,
        user_question
    ):

        material = (
            StudyService.get_material_by_id(
                material_id
            )
        )

        if not material:

            return {
                "success": False,
                "message": "Study material not found"
            }

        lesson_content = material.get(
            "content",
            ""
        )

        try:

            ai_response = ask_ai(

                prompt=user_question,

                domain="study",

                context={

                    "title":
                    material.get(
                        "title"
                    ),

                    "category":
                    material.get(
                        "category"
                    ),

                    "content":
                    lesson_content
                }
            )

            # AI fallback handling
            if isinstance(
                ai_response,
                dict
            ) and ai_response.get(
                "fallback"
            ):

                content = (
                    lesson_content[:300]
                )

                return {

                    "success": True,

                    "material_title":
                    material.get(
                        "title"
                    ),

                    "question":
                    user_question,

                    "answer":
                    f"AI is busy right now.\n\nStudy summary:\n{content}"
                }

            return {

                "success": True,

                "material_title":
                material.get(
                    "title"
                ),

                "question":
                user_question,

                "answer":
                ai_response
            }

        except Exception as e:

            return {

                "success": False,

                "error":
                str(e)
            }