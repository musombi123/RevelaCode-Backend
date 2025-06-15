from flask import Flask, request, jsonify
from backend.bible_decoder import decode_verse

app = Flask(__name__)

@app.route('/decode', methods=['POST'])
def decode():
    data = request.get_json()
    verse = data.get('verse', '')
    result = decode_verse(verse)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)
