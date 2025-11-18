# post_store.py
# Provides an abstraction: Mongo if MONGO_URI set, else JSON file fallback

import os
import uuid
import json
from pymongo import MongoClient, ASCENDING, DESCENDING

MONGO_URI = os.environ.get('MONGO_URI')
POSTS_JSON = os.environ.get('POSTS_JSON_PATH','posts.json')

class PostStore:
    def __init__(self):
        if MONGO_URI:
            self.client = MongoClient(MONGO_URI)
            self.db = self.client.get_database()
            self.collection = self.db.get_collection('community_posts')
            # create indexes
            self.collection.create_index([('createdAt', DESCENDING)])
            self.use_mongo = True
        else:
            # ensure file exists
            if not os.path.exists(POSTS_JSON):
                with open(POSTS_JSON,'w') as f:
                    json.dump([], f)
            self.use_mongo = False

    def save_post(self, post_dict):
        if self.use_mongo:
            post_dict['_id'] = str(uuid.uuid4())
            self.collection.insert_one(post_dict)
            return self.collection.find_one({'_id': post_dict['_id']})
        else:
            with open(POSTS_JSON,'r+') as f:
                arr = json.load(f)
                post_dict['id'] = str(uuid.uuid4())
                arr.insert(0, post_dict)  # newest first
                f.seek(0)
                json.dump(arr, f, indent=2)
                f.truncate()
            return post_dict

    def list_posts(self, faith=None, tag=None, page=1, limit=20):
        if self.use_mongo:
            q = {'visibility':'public'}
            if faith: q['faith'] = faith
            if tag: q['tags'] = tag
            cursor = self.collection.find(q).sort('createdAt', -1).skip((page-1)*limit).limit(limit)
            return list(cursor)
        else:
            with open(POSTS_JSON,'r') as f:
                arr = json.load(f)
            res = [p for p in arr if p.get('visibility','public')=='public']
            if faith: res = [p for p in res if p.get('faith')==faith]
            if tag: res = [p for p in res if tag in p.get('tags',[])]
            start = (page-1)*limit
            return res[start:start+limit]

    def get_post(self, post_id):
        if self.use_mongo:
            return self.collection.find_one({'_id': post_id})
        else:
            with open(POSTS_JSON,'r') as f:
                arr = json.load(f)
            return next((p for p in arr if p.get('id')==post_id), None)

    def increment_reaction(self, post_id, reaction):
        if self.use_mongo:
            res = self.collection.find_one_and_update({'_id': post_id}, {'$inc': {f'reactions.{reaction}': 1}}, return_document=True)
            return res
        else:
            with open(POSTS_JSON,'r+') as f:
                arr = json.load(f)
                found = False
                for p in arr:
                    if p.get('id') == post_id:
                        p.setdefault('reactions', {'like':0,'insightful':0,'pray':0})
                        p['reactions'][reaction] = p['reactions'].get(reaction,0) + 1
                        p['updatedAt'] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
                        found = True
                        out = p
                        break
                if not found:
                    return None
                f.seek(0)
                json.dump(arr, f, indent=2)
                f.truncate()
                return out
