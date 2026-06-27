# backend/models/models.py

from datetime import datetime
import uuid


COLLECTIONS = {

    "users":"users",

    "scriptures":"scriptures",

    "admin_actions":"admin_actions",

    "support_tickets":"support_tickets",

    "study_materials":"study_materials",

    "study_preferences":"study_preferences",

    "study_bookmarks":"study_bookmarks",

    "rootwords":"rootwords"
}


# ==========================
# Create User
# ==========================

def create_user(

    db,

    full_name,

    contact,

    role,

    verified=False
):

    existing = db[
        COLLECTIONS[
            "users"
        ]
    ].find_one({

        "contact":
        contact
    })

    if existing:

        existing["_id"] = str(
            existing["_id"]
        )

        return existing


    user = {

        "id":
        str(
            uuid.uuid4()
        ),

        "full_name":
        full_name,

        "contact":
        contact,

        "role":
        role,

        "verified":
        verified,

        "status":
        "active",

        "created_at":
        datetime.utcnow()
        .isoformat(),

        "updated_at":
        datetime.utcnow()
        .isoformat()
    }


    db[
        COLLECTIONS[
            "users"
        ]
    ].insert_one(
        user
    )

    return user


# ==========================
# Get Users
# ==========================

def get_all_users(
    db
):

    users = list(

        db[
            COLLECTIONS[
                "users"
            ]
        ].find()

    )

    for user in users:

        user["_id"] = str(
            user["_id"]
        )

    return users


# ==========================
# Get One User
# ==========================

def get_user(

    db,
    contact
):

    user = db[
        COLLECTIONS[
            "users"
        ]
    ].find_one({

        "contact":
        contact
    })

    if user:

        user["_id"] = str(
            user["_id"]
        )

    return user


# ==========================
# Update User
# ==========================

def update_user(

    db,
    contact,
    updates
):

    updates[
        "updated_at"
    ] = (

        datetime.utcnow()
        .isoformat()
    )

    db[
        COLLECTIONS[
            "users"
        ]
    ].update_one(

        {
            "contact":
            contact
        },

        {
            "$set":
            updates
        }
    )

    return get_user(
        db,
        contact
    )


# ==========================
# Delete User
# ==========================

def delete_user(

    db,
    contact
):

    result = db[
        COLLECTIONS[
            "users"
        ]
    ].delete_one({

        "contact":
        contact
    })

    return {

        "success":
        result.deleted_count > 0
    }