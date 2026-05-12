import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6234222988"))
DB_FILE = Path(os.environ.get("DB_FILE", "videos.db"))

db_lock = asyncio.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)


def connect_db() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                media_type TEXT NOT NULL,
                file_name TEXT,
                mime_type TEXT,
                caption TEXT,
                added_by_id INTEGER,
                added_by_name TEXT,
                added_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def row_to_video(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "file_id": row["file_id"],
        "media_type": row["media_type"],
        "file_name": row["file_name"],
        "mime_type": row["mime_type"],
        "caption": row["caption"],
        "added_by_id": row["added_by_id"],
        "added_by_name": row["added_by_name"],
        "added_at": row["added_at"],
    }


def count_videos() -> int:
    with connect_db() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM videos").fetchone()
        return int(row["total"])


def load_videos(limit: int | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM videos ORDER BY id ASC"
    params: tuple[Any, ...] = ()

    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)

    with connect_db() as connection:
        rows = connection.execute(query, params).fetchall()
        return [row_to_video(row) for row in rows]


def load_recent_videos(limit: int = 5) -> list[dict[str, Any]]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT * FROM videos ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row_to_video(row) for row in rows]


def insert_video(video: dict[str, Any]) -> int:
    with connect_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO videos (
                file_id,
                media_type,
                file_name,
                mime_type,
                caption,
                added_by_id,
                added_by_name,
                added_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video["file_id"],
                video["media_type"],
                video.get("file_name"),
                video.get("mime_type"),
                video.get("caption"),
                video.get("added_by_id"),
                video.get("added_by_name"),
                video["added_at"],
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def clear_videos() -> int:
    with connect_db() as connection:
        count = count_videos()
        connection.execute("DELETE FROM videos")
        connection.commit()
        return count


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

    if message.document:
        return {
            "file_id": message.document.file_id,
            "media_type": "document",
            "file_name": message.document.file_name,
            "mime_type": message.document.mime_type,
            "caption": caption,
        }

    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    total = count_videos()
    role = "Admin" if is_admin(update) else "User"

    text = (
        "Video Sharing Bot\n\n"
        f"Role: {role}\n"
        f"Videos saved: {total}\n\n"
        "Commands:\n"
        "/send10 - Send first 10 videos\n"
        "/send50 - Send first 50 videos\n"
        "/send100 - Send first 100 videos\n"
        "/sendall - Send all videos\n"
        "/total - Show total videos\n"
        "/recent - Show last 5 saved videos\n"
        "/status - Bot status\n\n"
        "Admin:\n"
        "Send any Telegram video or any video file as a document.\n"
        "All video formats are supported because document uploads are stored and resent as documents."
    )

    await update.effective_message.reply_text(text)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Only admin can upload videos.")
        return

    async with db_lock:
        total = count_videos()
        video_data = get_upload_data(update, total)

        if not video_data:
            await update.effective_message.reply_text("Please send a Telegram video or a video file as a document.")
            return

        video_data.update(
            {
                "added_by_id": update.effective_user.id,
                "added_by_name": update.effective_user.first_name,
                "added_at": utc_now(),
            }
        )
        saved_id = insert_video(video_data)

    file_name = video_data.get("file_name") or video_data.get("caption") or "video file"
    await update.effective_message.reply_text(
        f"Saved video #{saved_id}\n\n"
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
    total = count_videos()
    if total == 0:
        await update.effective_message.reply_text("No videos saved yet.")
        return

    count = total if limit is None else min(limit, total)
    videos = load_videos(count)

    await update.effective_message.reply_text(f"Sending {count} of {total} videos. Please wait...")

    sent = 0
    failed = 0
    first_error = None

    for index, video in enumerate(videos, start=1):
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

    result = f"Complete\n\nSent: {sent}\nFailed: {failed}\nTotal saved: {total}"
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
    await update.effective_message.reply_text(f"Total videos saved: {count_videos()}")


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    videos = load_recent_videos(5)
    if not videos:
        await update.effective_message.reply_text("No videos saved yet.")
        return

    lines = [f"Last {len(videos)} videos:"]

    for index, video in enumerate(videos, start=1):
        name = video.get("caption") or video.get("file_name") or "Untitled video"
        media_type = video.get("media_type", "unknown")
        lines.append(f"{index}. [{media_type}] {name[:80]}")

    await update.effective_message.reply_text("\n".join(lines))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Bot status\n\n"
        "Running: yes\n"
        f"Database file: {DB_FILE}\n"
        f"Videos saved: {count_videos()}\n"
        f"Admin ID: {ADMIN_ID}"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text("Admin only.")
        return

    async with db_lock:
        count = clear_videos()

    await update.effective_message.reply_text(f"Cleared {count} videos from SQLite.")


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
    app.add_handler(CommandHandler("clear", clear))

    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, handle_video))
    app.add_error_handler(error_handler)

    return app


def main() -> None:
    init_db()
    print("Starting Video Sharing Bot")
    print(f"Database file: {DB_FILE}")
    print(f"Loaded videos: {count_videos()}")

    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
