
import os
import shutil
from datetime import datetime

def archive_old_events():
    events_dir = './backend/events'
    archived_dir = './backend/archived'
    os.makedirs(archived_dir, exist_ok=True)

    for filename in os.listdir(events_dir):
        if filename.startswith('events_') and filename.endswith('.json'):
            date_str = filename.replace('events_', '').replace('.json', '')
            file_date = datetime.strptime(date_str, '%Y-%m-%d')
            if (datetime.now() - file_date).days > 7:
                src = os.path.join(events_dir, filename)
                dst = os.path.join(archived_dir, filename)
                shutil.move(src, dst)
                print(f'Archived {filename}')

if __name__ == '__main__':
    archive_old_events()
