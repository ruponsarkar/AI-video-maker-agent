"""
Snack Code - upload a finished video to YouTube with all its details.

Run from inside a video's folder, after youtube_kit.py:
    python ../../upload.py --dry-run                         # show what would be sent, upload nothing
    python ../../upload.py --thumbnail b                     # upload as PRIVATE (the default)
    python ../../upload.py --thumbnail b --title b           # the second title from details.json
    python ../../upload.py --thumbnail b --schedule "2026-11-08 18:00"   # goes public then (India time)
    python ../../upload.py --thumbnail b --publish           # public straight away (asks you first)

Run it again at any time: it never uploads the video twice. It finishes any step that failed, and
posts the comment once the video is public. Progress is kept in youtube/uploaded.json.

First run: a browser opens; choose the Snack Code channel and click Allow. The login is saved in
youtube_token.json. Keep that file and client_secret.json private.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(HERE, "client_secret.json")
TOKEN = os.path.join(HERE, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
CHANNEL_HANDLE = "@snackcode108"   # refuses to upload to any other channel
CATEGORIES = {"tech": "28", "news": "25"}   # Science & Technology, News & Politics
LANGUAGE = "hi"
CAPTION_LANGUAGES = ("hi-Latn", "hi")   # the subtitles are Hindi in Roman letters
IST = timezone(timedelta(hours=5, minutes=30))
CHUNK = 8 * 1024 * 1024
RETRIES = 5

VIDEO = "output/animated.mp4"
SUBTITLES = "output/animated.srt"
DETAILS = "youtube/details.json"
DESCRIPTION = "youtube/description.txt"
RECORD = "youtube/uploaded.json"


def parse_args():
    p = argparse.ArgumentParser(description="Upload this video to YouTube.")
    p.add_argument("--thumbnail", choices=["a", "b", "c"], help="which youtube/thumbnail_X.jpg to use (default: a)")
    p.add_argument("--title", choices=["a", "b"], help="which title from details.json \"titles\" (default: a)")
    p.add_argument("--schedule", metavar="'YYYY-MM-DD HH:MM'", help="publish at this India time")
    p.add_argument("--publish", action="store_true", help="make the video public straight away")
    p.add_argument("--dry-run", action="store_true", help="show what would be sent and stop")
    args = p.parse_args()
    if args.schedule and args.publish:
        p.error("use --schedule or --publish, not both")
    return args


def publish_time(text):
    """India time from the command line -> the UTC time YouTube wants."""
    try:
        when = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    except ValueError:
        raise SystemExit("Write the time like this: --schedule \"2026-11-08 18:00\" (India time)")
    if when <= datetime.now(IST) + timedelta(minutes=30):
        raise SystemExit("The scheduled time must be at least 30 minutes from now.")
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_package(args, record):
    """Check that everything exists and is current BEFORE logging in or sending anything."""
    if not os.path.exists("scripts/script.json"):
        raise SystemExit("Run this from inside a video's folder (projects/<video>).")
    if not os.path.exists(DETAILS) or not os.path.exists(DESCRIPTION):
        raise SystemExit("Run this first: python ../../youtube_kit.py")
    if not os.path.exists(VIDEO):
        raise SystemExit(f"{VIDEO} is missing: render the video first.")
    if os.path.getmtime(VIDEO) > os.path.getmtime(DESCRIPTION):
        raise SystemExit("The video is newer than its chapter times. Run this first: python ../../youtube_kit.py")
    info = json.load(open(DETAILS, encoding="utf-8"))
    titles = info.get("titles") or [info.get("title", "")]
    pick = "ab".index(args.title or "a")
    if pick >= len(titles):
        raise SystemExit('details.json has only one title. Add a second one to "titles".')
    info["title"] = titles[pick]
    description = open(DESCRIPTION, encoding="utf-8").read().strip()
    tags = info.get("tags", [])
    thumbnail = record["thumbnail"] if record else f"youtube/thumbnail_{args.thumbnail or 'a'}.jpg"
    problems = []
    if not 0 < len(info.get("title", "")) <= 100:
        problems.append("The title must be 1 to 100 characters.")
    if len(description) > 5000:
        problems.append("The description is over 5000 characters.")
    if len(", ".join(tags)) > 500:
        problems.append("The tags are over 500 characters.")
    if not os.path.exists(thumbnail):
        problems.append(f"{thumbnail} is missing.")
    script = json.load(open("scripts/script.json", encoding="utf-8"))
    if script.get("kind") == "news" and not script.get("reviewed") and (args.publish or args.schedule):
        problems.append('This is a news video and nobody has marked it checked. Check scripts/review.md, then add '
                        '"reviewed": true to scripts/script.json. A private upload is still allowed.')
    if problems:
        raise SystemExit("Fix these first:\n  " + "\n  ".join(problems))
    return info, description, tags, thumbnail


def video_body(info, description, tags, publish_at, public):
    status = {"privacyStatus": "public" if public else "private",
              "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": True,   # the AI voice: YouTube's altered or synthetic label
              "embeddable": True,
              "license": "youtube"}
    if publish_at:
        status["publishAt"] = publish_at
    return {"snippet": {"title": info["title"], "description": description, "tags": tags,
                        "categoryId": CATEGORIES.get(info.get("category"), CATEGORIES["tech"]), "defaultLanguage": LANGUAGE,
                        "defaultAudioLanguage": LANGUAGE},
            "status": status}


# ---------------------------------------------------------------- login
def login():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not os.path.exists(CLIENT_SECRET):
        raise SystemExit(f"{CLIENT_SECRET} is missing. See 'Uploading by script' in readme.md.")
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES) if os.path.exists(TOKEN) else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:   # Google ends logins for apps in test mode after about 7 days
            print("Your YouTube login has expired, so a browser will open to log in again.")
            creds = None
    if not creds or not creds.valid:
        print("Opening your browser. Choose the Snack Code channel and click Allow.")
        creds = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES).run_local_server(port=0)
    descriptor = os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as f:
        f.write(creds.to_json())
    return creds


def check_channel(youtube):
    items = youtube.channels().list(part="snippet", mine=True).execute().get("items", [])
    handle = items[0]["snippet"].get("customUrl", "") if items else ""
    if handle.lower() != CHANNEL_HANDLE:
        os.remove(TOKEN)   # so the next run asks again and lets you pick the right channel
        raise SystemExit(f"This login is for channel '{handle or 'none'}', not {CHANNEL_HANDLE}. "
                         "Nothing was uploaded. Run again and choose the Snack Code channel.")
    print(f"Channel: {items[0]['snippet']['title']} ({handle})")


# ---------------------------------------------------------------- steps
def explain(error):
    """Turn a YouTube API error into its short reason code."""
    try:
        return json.loads(error.content)["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError):
        return f"HTTP {error.resp.status}"


def upload_video(youtube, body):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(VIDEO, mimetype="video/mp4", chunksize=CHUNK, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response, failures = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            failures = 0
            if status:
                print(f"  {status.progress() * 100:.0f}%", flush=True)
        except (HttpError, OSError) as e:
            temporary = not isinstance(e, HttpError) or e.resp.status in (500, 502, 503, 504)
            failures += 1
            if not temporary or failures > RETRIES:
                raise
            wait = 2 ** failures
            print(f"  connection problem, trying again in {wait} s ...")
            time.sleep(wait)
    return response["id"]


def set_thumbnail(youtube, video_id, path):
    from googleapiclient.http import MediaFileUpload
    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(path, mimetype="image/jpeg")).execute()


def add_subtitles(youtube, video_id):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    for k, language in enumerate(CAPTION_LANGUAGES):
        try:
            youtube.captions().insert(
                part="snippet",
                body={"snippet": {"videoId": video_id, "language": language, "name": "Hinglish", "isDraft": False}},
                media_body=MediaFileUpload(SUBTITLES, mimetype="application/octet-stream")).execute()
            return
        except HttpError as e:
            if e.resp.status != 400 or k == len(CAPTION_LANGUAGES) - 1:
                raise


def post_comment(youtube, video_id, text):
    youtube.commentThreads().insert(part="snippet", body={"snippet": {
        "videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()


def is_public(youtube, video_id):
    items = youtube.videos().list(part="status", id=video_id).execute().get("items", [])
    return bool(items) and items[0]["status"]["privacyStatus"] == "public"


def save(record):
    json.dump(record, open(RECORD, "w", encoding="utf-8"), indent=2)


def run_step(record, name, label, action):
    """Do a step once. A failure is reported and retried on the next run; it doesn't lose the upload."""
    from googleapiclient.errors import HttpError
    if name in record["done"]:
        return
    try:
        action()
        record["done"].append(name)
        save(record)
        print(f"{label}: done")
    except (HttpError, OSError) as e:
        reason = explain(e) if isinstance(e, HttpError) else str(e)
        print(f"{label}: FAILED ({reason}). Run this command again to retry.")
        if reason == "quotaExceeded":
            print("  YouTube's daily API limit is used up. It resets at midnight Pacific time.")
        elif name == "thumbnail" and getattr(e, "resp", None) is not None and e.resp.status == 403:
            print("  Custom thumbnails need a verified channel: https://www.youtube.com/verify")


# ---------------------------------------------------------------- main
def main():
    args = parse_args()
    record = json.load(open(RECORD, encoding="utf-8")) if os.path.exists(RECORD) else None
    info, description, tags, thumbnail = load_package(args, record)
    publish_at = publish_time(args.schedule) if args.schedule and not record else None
    body = video_body(info, description, tags, publish_at, args.publish)
    when = (f"scheduled for {args.schedule} India time" if publish_at else
            "PUBLIC straight away" if args.publish else "private (only you can see it)")

    if record and (args.publish or args.schedule):
        print(f"Already uploaded, so --publish and --schedule do nothing now. "
              f"Change visibility in Studio: https://studio.youtube.com/video/{record['video_id']}/edit")
    if args.dry_run or not record:
        print(f"Video:      {VIDEO} ({os.path.getsize(VIDEO) / 1e6:.0f} MB)\n"
              f"Title:      {info['title']}\n"
              f"Visibility: {when}\n"
              f"Thumbnail:  {thumbnail}\n"
              f"Subtitles:  {SUBTITLES if os.path.exists(SUBTITLES) else 'none'}\n"
              f"Tags:       {len(tags)}, description: {len(description)} characters\n"
              f"Status:     {json.dumps(body['status'])}")
    if os.path.exists("scripts/review.md"):
        print("Warning: scripts/review.md lists script problems the automatic checks couldn't fix.")
    if args.dry_run:
        print("\nDry run: nothing was sent.")
        return 0
    if args.publish and not record:
        if input("\nThis makes the video public now. Type PUBLISH to continue: ").strip() != "PUBLISH":
            raise SystemExit("Stopped. Nothing was uploaded.")

    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    youtube = build("youtube", "v3", credentials=login())
    check_channel(youtube)

    if not record:
        print("Uploading the video ...")
        try:
            video_id = upload_video(youtube, body)
        except HttpError as e:
            raise SystemExit(f"Upload failed: {explain(e)}. Nothing was published. Run this command again to retry.")
        except OSError as e:
            raise SystemExit(f"Upload failed: {e}. Check your connection and run this command again.")
        record = {"video_id": video_id, "thumbnail": thumbnail, "done": []}
        save(record)
    video_id = record["video_id"]

    run_step(record, "thumbnail", "Thumbnail", lambda: set_thumbnail(youtube, video_id, record["thumbnail"]))
    if os.path.exists(SUBTITLES):
        run_step(record, "subtitles", "Subtitles", lambda: add_subtitles(youtube, video_id))
    comment = info.get("pinned_comment", "").strip()
    if comment and "comment" not in record["done"]:
        if is_public(youtube, video_id):
            run_step(record, "comment", "Comment", lambda: post_comment(youtube, video_id, comment))
        else:
            print("Comment: waiting until the video is public. Run this command again then.")

    print(f"\nWatch:  https://www.youtube.com/watch?v={video_id}\n"
          f"Studio: https://studio.youtube.com/video/{video_id}/edit\n"
          "In Studio: check the AI label, add the end screen, pin the comment once it's posted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
