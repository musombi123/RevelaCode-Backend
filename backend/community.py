# community.py
# Flask blueprint for Faith Community Platform (FCP)
# Place in services/community/community.py

import os
import json
import functools
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from models import validate_post_payload
from post_store import PostStore
import jwt

bp = Blueprint('community', __name__, url_prefix='/community')

# Try to use your existing auth_gate.get_user_from_token if present.
# If not present, fall back to JWT + users.json-based auth.
try:
    from auth_gate import get_user_from_token  # type: ignore
    EXTERNAL_AUTH = True
except Exception:
    EXTERNAL_AUTH = False

# Fallback loader: reads users.json and validates token signed with JWT_SECRET
USERS_JSON_PATH = os.environ.get('USERS_JSON_PATH', 'users.json')
JWT_SECRET = os.environ.get('JWT_SECRET', os.environ.get('REVELACODE_JWT_SECRET', 'change-me'))

def fallback_get_user_from_token(authorization_header: str):
    if not authorization_header:
        return None
    token = authorization_header.replace('Bearer ', '')
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        user_id = payload.get('id') or payload.get('sub') or payload.get('email')
        # load users.json
        if os.path.exists(USERS_JSON_PATH):
            with open(USERS_JSON_PATH, 'r') as f:
                users = json.load(f)
            # users.json assumed { "<id_or_email>": { ... } } or list; try both
            if isinstance(users, dict):
                # try id match then email match
                user = users.get(str(user_id)) or next((u for u in users.values() if u.get('email') == user_id), None)
            else:
                user = next((u for u in users if u.get('id') == user_id or u.get('email') == user_id), None)
            return user
        return {'id': user_id, 'email': payload.get('email'), 'displayName': payload.get('displayName', '')}
    except Exception:
        return None

def auth_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', None)
        if EXTERNAL_AUTH:
            # assume external returns user dict or None
            user = get_user_from_token(auth_header)
        else:
            user = fallback_get_user_from_token(auth_header)
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        # attach to flask global via request context
        request.current_user = user
        return f(*args, **kwargs)
    return decorated

# Initialize store (uses MONGO_URI if present, else file)
store = PostStore()

@bp.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'module': 'community'})

@bp.route('/posts', methods=['POST'])
@auth_required
def create_post():
    """
    Expected JSON:
    {
      "title": "On John 3:16",
      "faith": "bible"|"quran"|"other",
      "source": {"book":"John","chapter":3,"verse":"16"},
      "decoded": {"text":"...", "analysis":"...", "confidence":0.92, "references":[...]},
      "visibility": "public"|"private"|"followers",
      "tags": ["prophecy","love"]
    }
    """
    payload = request.get_json() or {}
    valid, msg = validate_post_payload(payload)
    if not valid:
        return jsonify({'error': 'invalid_payload', 'message': msg}), 400

    author = request.current_user
    post = {
        'author': {
            'id': str(author.get('id') or author.get('_id') or author.get('email')),
            'displayName': author.get('displayName') or author.get('display_name') or author.get('email'),
            'preferredFaith': author.get('preferredFaith') or author.get('preferred_faith', None)
        },
        'title': payload.get('title',''),
        'faith': payload.get('faith','other'),
        'source': payload.get('source',{}),
        'decoded': payload.get('decoded',{}),
        'visibility': payload.get('visibility','public'),
        'tags': payload.get('tags', []),
        'reactions': {'like':0,'insightful':0,'pray':0},
        'moderation': {'status':'pending','flagCount':0,'lastModeratedAt':None},
        'createdAt': datetime.now(timezone.utc).isoformat(),
        'updatedAt': datetime.now(timezone.utc).isoformat()
    }

    saved = store.save_post(post)
    # TODO: enqueue saved to moderation worker
    return jsonify(saved), 201

@bp.route('/posts', methods=['GET'])
@auth_required
def get_posts():
    # basic filters: faith, tag, page, limit
    faith = request.args.get('faith')
    tag = request.args.get('tag')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    results = store.list_posts(faith=faith, tag=tag, page=page, limit=limit)
    return jsonify({'meta': {'page': page, 'limit': limit}, 'data': results})

@bp.route('/posts/<post_id>', methods=['GET'])
@auth_required
def get_post(post_id):
    post = store.get_post(post_id)
    if not post:
        return jsonify({'error':'not_found'}), 404
    # respect simple visibility for private
    if post.get('visibility') == 'private':
        author_id = post.get('author',{}).get('id')
        current_id = str(request.current_user.get('id') or request.current_user.get('email'))
        if author_id != current_id:
            return jsonify({'error':'forbidden'}), 403
    return jsonify(post)

@bp.route('/posts/<post_id>/react', methods=['POST'])
@auth_required
def react_post(post_id):
    body = request.get_json() or {}
    reaction = body.get('reaction')
    if reaction not in ('like','insightful','pray'):
        return jsonify({'error':'invalid_reaction'}), 400
    updated = store.increment_reaction(post_id, reaction)
    if not updated:
        return jsonify({'error':'not_found'}), 404
    return jsonify(updated)

# You can register this blueprint in your main flask app:
# from community import bp as community_bp
# app.register_blueprint(community_bp)
