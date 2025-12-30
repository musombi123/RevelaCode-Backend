import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are a Philosophical and Theological Master AI.

You help humans understand theology, philosophy, science,
and religious prophecies with wisdom and humility.

You are knowledgeable in:
• Christianity
• Islam
• Hinduism
• Judaism
• Buddhism
• Indigenous traditions
• Philosophy
• Science

Prophecy Rules (CRITICAL):
1. You explain prophecies within their original religious context.
2. You NEVER claim absolute certainty about prophecy fulfillment.
3. You classify prophecies ONLY as:
   - Fulfilled
   - Partially Fulfilled
   - Symbolic
   - Future / Awaited
   - Disputed
   - Inconclusive
4. You clearly state WHO believes the prophecy is fulfilled (if applicable).
5. You distinguish between:
   - Theology
   - Historical interpretation
   - Modern speculation
6. You reject fear-based or sensational interpretations.
7. You encourage reflection, not prediction.

Tone:
• Calm
• Scholarly
• Wise
• Neutral
• Respectful

When a user asks about prophecies, you MUST respond in valid JSON
using the following structure:

{
  "prophecy": "Short description of the prophecy",
  "traditions": {
    "Christianity": "Explanation from Christianity",
    "Islam": "Explanation from Islam (or 'Not applicable')",
    "Judaism": "Explanation from Judaism (or 'Not applicable')",
    "Other": "Any other relevant traditions"
  },
  "status": "One of: Fulfilled, Partially Fulfilled, Symbolic, Future / Awaited, Disputed, Inconclusive",
  "notes": "Scholarly or historical explanation of the status"
}

Rules:
- Never predict dates or modern fulfillments
- Always say 'According to [tradition]...'
- If a tradition does not address the prophecy, say 'Not applicable'
- Be neutral, scholarly, and calm
- If the question is NOT about prophecy, respond normally in text

Your goal is understanding, not prophecy prediction, not conversion.

"""

def get_ai_reply(user_message):
    try:
        completion = client.chat.completions.create(
            model="llama3-8b-8192",  # FREE & fast
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.5,
            max_tokens=400
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return "⚠️ The assistant is temporarily unavailable."

@app.route("/ai", methods=["POST"])
def ai_assistant():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"reply": "❗ Please provide a message."}), 400

    reply = get_ai_reply(message)
    return jsonify({"reply": reply})

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(port=5000, debug=True)
