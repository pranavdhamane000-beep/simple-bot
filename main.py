import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6234222988"))
VIDEO_FILE = Path(os.environ.get("VIDEO_FILE", "videos.json"))

VIDEO_EXTENSIONS = {
    ".3g2",
    ".3gp",
    ".avi",
    ".divx",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogv",
    ".rm",
    ".rmvb",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
}

videos_lock = asyncio.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)


def load_videos() -> list[dict[str, Any]]:
    if not VIDEO_FILE.exists():
        return []

    try:
        with VIDEO_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Could not load {VIDEO_FILE}: {error}")
        return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict) and item.get("file_id")]

    return []


def save_videos(videos: list[dict[str, Any]]) -> None:
    VIDEO_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = VIDEO_FILE.with_suffix(VIDEO_FILE.suffix + ".tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(videos, file, ensure_ascii=False, indent=2)

    os.replace(temp_file, VIDEO_FILE)


def document_is_video(document) -> bool:
    mime_type = document.mime_type or ""
    file_name = document.file_name or ""

    if mime_type.startswith("video/"):
        return True

    return Path(file_name).suffix.lower() in VIDEO_EXTENSIONS


def get_upload_data(update: Update, current_count: int) -> dict[str, Any] | None:
    message = update.effective_message
    if not message:
        return None

    caption = message.caption or f"Video #{current_count + 1}"

    if message.video:
        return {
            "file_id": message.video.file_id,
            "media_type": "video",
            "file_name": message.video.file_name,
            "mime_type": message.video.mime_type,
            "caption": caption,
        }

    if message.document and document_is_video(message.document):
        return {
            "file_id": message.document.file_id,
            "media_type": "document",
            "file_name": message.document.file_name,
            "mime_type": message.document.mime_type,
            "caption": caption,
        }

    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    videos = load_videos()
    role = "Admin" if is_admin(update) else "User"

    text = (
        "Video Sharing Bot\n\n"
        f"Role: {role}\n"
        f"Videos saved: {len(videos)}\n\n"
        "Commands:\n"
        "/send10 - Send first 10 videos\n"
        "/send50 - Send first 50 videos\n"
        "/send100 - Send first 100 videos\n"
        "/sendall - Send all videos\n"
        "/total - Show total videos\n"
        "/recent - Show last 5 saved videos\n"
        "/status - Bot status\n\n"
        "Admin:\n"
        "Send any video file to save it.\n"
        "Supported: MP4, MKV, AVI, MOV, WEBM, WMV, FLV, M4V, 3GP, MPG and other video documents."
    )

    await update.effective_message.reply_text(text)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Only admin can upload videos.")
        return

    async with videos_lock:
        videos = load_videos()
        video_data = get_upload_data(update, len(videos))

        if not video_data:
            await update.effective_message.reply_text(
                "Please send a video file. If Telegram sends it as a document, the file name should have a video extension."
            )
            return

        video_data.update(
            {
                "added_by_id": update.effective_user.id,
                "added_by_name": update.effective_user.first_name,
                "added_at": utc_now(),
            }
        )

        videos.append(video_data)
        save_videos(videos)
        saved_count = len(videos)

    file_name = video_data.get("file_name") or "video file"
    await update.effective_message.reply_text(
        f"Saved video #{saved_count}\n\n"
        f"Name: {file_name}\n"
        f"Type: {video_data.get('media_type')}\n"
        "Users can now watch it with /send10, /send100 or /sendall."
    )


async def send_saved_video(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    video: dict[str, Any],
    caption: str,
) -> None:
    file_id = video["file_id"]

    if video.get("media_type") == "document":
        await context.bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
        return

    try:
        await context.bot.send_video(chat_id=chat_id, video=file_id, caption=caption)
    except TelegramError as video_error:
        try:
            await context.bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
        except TelegramError as document_error:
            raise RuntimeError(
                f"send_video failed: {video_error}; send_document failed: {document_error}"
            ) from document_error


async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit: int | None) -> None:
    videos = load_videos()
    if not videos:
        await update.effective_message.reply_text("No videos saved yet.")
        return

    count = len(videos) if limit is None else min(limit, len(videos))
    selected_videos = videos[:count]

    await update.effective_message.reply_text(f"Sending {count} of {len(videos)} videos. Please wait...")

    sent = 0
    failed = 0
    first_error = None

    for index, video in enumerate(selected_videos, start=1):
        try:
            caption = video.get("caption") or video.get("file_name") or f"Video {index}"
            await send_saved_video(
                context=context,
                chat_id=update.effective_chat.id,
                video=video,
                caption=f"Video {index}/{count}\n{caption[:900]}",
            )
            sent += 1
            await asyncio.sleep(0.5)
        except Exception as error:
            failed += 1
            first_error = first_error or str(error)
            print(f"Error sending video {index}: {error}")

    result = f"Complete\n\nSent: {sent}\nFailed: {failed}\nTotal saved: {len(videos)}"
    if first_error:
        result += f"\n\nFirst error:\n{first_error[:500]}"

    await update.effective_message.reply_text(result)


async def send10(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_videos(update, context, 10)


async def send50(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_videos(update, context, 50)


async def send100(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_videos(update, context, 100)


async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_videos(update, context, None)


async def total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    videos = load_videos()
    await update.effective_message.reply_text(f"Total videos saved: {len(videos)}")


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    videos = load_videos()
    if not videos:
        await update.effective_message.reply_text("No videos saved yet.")
        return

    recent_videos = videos[-5:]
    lines = [f"Last {len(recent_videos)} videos:"]

    for index, video in enumerate(reversed(recent_videos), start=1):
        name = video.get("caption") or video.get("file_name") or "Untitled video"
        media_type = video.get("media_type", "unknown")
        lines.append(f"{index}. [{media_type}] {name[:80]}")

    await update.effective_message.reply_text("\n".join(lines))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    videos = load_videos()
    await update.effective_message.reply_text(
        "Bot status\n\n"
        "Running: yes\n"
        f"Storage file: {VIDEO_FILE}\n"
        f"Videos saved: {len(videos)}\n"
        f"Admin ID: {ADMIN_ID}"
    )


async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Admin only.")
        return

    async with videos_lock:
        videos = load_videos()
        save_videos(videos)

    await update.effective_message.reply_text(f"Saved {len(videos)} videos to JSON.")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Admin only.")
        return

    async with videos_lock:
        videos = load_videos()
        count = len(videos)
        save_videos([])

    await update.effective_message.reply_text(f"Cleared {count} videos from JSON.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Update caused error: {context.error}")


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is missing.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send10", send10))
    app.add_handler(CommandHandler("send50", send50))
    app.add_handler(CommandHandler("send100", send100))
    app.add_handler(CommandHandler("sendall", sendall))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("save", save_command))
    app.add_handler(CommandHandler("clear", clear))

    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, handle_video))
    app.add_error_handler(error_handler)

    return app


def main() -> None:
    print("Starting Video Sharing Bot")
    print(f"Storage file: {VIDEO_FILE}")
    print(f"Loaded videos: {len(load_videos())}")

    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
