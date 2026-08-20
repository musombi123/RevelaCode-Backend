from flask import Blueprint,request
from jumuiya.core.permissions import require_authenticated,current_user_id
from jumuiya.core.responses import ok
from jumuiya.notifications import services

notifications_bp=Blueprint("jumuiya_notifications",__name__)

@notifications_bp.get("")
@require_authenticated
def get_notifications():
    try:limit=min(max(int(request.args.get("limit",30)),1),100)
    except ValueError:limit=30
    return ok(services.list_notifications(current_user_id(),limit))

@notifications_bp.put("/<notification_id>/read")
@require_authenticated
def mark_read(notification_id):return ok(services.mark_read(current_user_id(),notification_id),"Notification marked as read.")
