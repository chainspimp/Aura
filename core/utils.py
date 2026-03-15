from datetime import datetime, timedelta

def get_time():
    return datetime.now()

def get_time_str(dt=None):
    return (dt or get_time()).strftime("%Y-%m-%d %H:%M:%S")

def get_relative_time(dt):
    diff = get_time() - dt
    if diff < timedelta(minutes=1):
        return "just now"
    elif diff < timedelta(hours=1):
        return f"{int(diff.total_seconds()/60)} min ago"
    elif diff < timedelta(days=1):
        return f"{int(diff.total_seconds()/3600)} hr ago"
    elif diff < timedelta(days=7):
        return f"{diff.days} day ago"
    elif diff < timedelta(days=30):
        return f"{int(diff.days/7)} week ago"
    elif diff < timedelta(days=365):
        return f"{int(diff.days/30)} month ago"
    else:
        return f"{int(diff.days/365)} year ago"

def get_time_context():
    now = get_time()
    hour = now.hour
    if 5 <= hour < 12:
        tod = "morning"
    elif 12 <= hour < 17:
        tod = "afternoon"
    elif 17 <= hour < 21:
        tod = "evening"
    else:
        tod = "night"
    return f"Current time: {now.strftime('%A, %B %d, %Y at %I:%M %p')} ({tod})"