from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def get_ai_reply(user_message):
    lower = user_message.lower()
    if "666" in lower:
        return "🔢 *666* symbolizes imperfection and rebellion. See Revelation 13:18."
    elif "mark of the beast" in lower:
        return "💉 The 'mark of the beast' signifies economic control. See Revelation 13:16–17."
    elif "rapture" in lower:
        return "🌤 The rapture refers to believers being taken up. See 1 Thessalonians 4:16–17."
    elif "false prophet" in lower:
        return "⚠️ The false prophet promotes deception and worship of the beast. See Revelation 13."
    elif "antichrist" in lower:
        return "👤 The antichrist opposes Christ and deceives many. See 1 John 2:18, 2 Thessalonians 2."
    else:
        return "🧠 Try asking about 666, rapture, antichrist, mark of the beast, or signs of the end times."

@app.route("/ai", methods=["POST"])
def ai_assistant():
    data = request.get_json()
    message = data.get("message", "")
    if not message.strip():
        return jsonify({"reply": "❗ Please provide a message to decode or explain."}), 400

    reply = get_ai_reply(message)
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
