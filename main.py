import os
import asyncio
import json
import platform
import aiofiles
from datetime import datetime
from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# File to store videos (survives restarts!)
VIDEO_FILE = "videos.json"

# Concurrency lock to prevent file corruption if multiple uploads happen
file_lock = asyncio.Lock()

# Load videos from file asynchronously
async def load_videos():
    if os.path.exists(VIDEO_FILE):
        try:
            async with aiofiles.open(VIDEO_FILE, 'r') as f:
                content = await f.read()
                return json.loads(content) if content else []
        except Exception as e:
            print(f"Error loading videos: {e}")
            return []
    return []

# Save videos to file asynchronously
async def save_videos(videos):
    async with file_lock:
        async with aiofiles.open(VIDEO_FILE, 'w') as f:
            await f.write(json.dumps(videos, indent=2))

# REPLACE WITH YOUR TELEGRAM USER ID
ADMIN_ID = 6234222988

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = (user_id == ADMIN_ID)
    videos = context.bot_data.get("videos", [])
    
    msg = "🎬 *Video Library Bot*\n\n"
    
    if is_admin:
        msg += "👑 *You are the ADMIN*\n"
        msg += "• Send videos to add them\n"
        msg += "• All videos save permanently\n\n"
        msg += "*Admin Commands:*\n"
        msg += "/clear - Delete all videos\n"
        msg += "/save - Force save to file\n\n"
    else:
        msg += "👋 *Welcome User*\n"
        msg += "• You can only WATCH videos\n"
        msg += "• Admin adds the videos\n\n"
    
    msg += "*Commands:*\n"
    msg += "/send10 - Get first 10 videos\n"
    msg += "/send50 - Get first 50 videos\n"
    msg += "/send100 - Get first 100 videos\n"
    msg += "/sendall - Get all videos\n"
    msg += "/total - Show statistics\n"
    msg += "/recent - Last 5 videos\n\n"
    
    msg += f"📊 Videos in library: {len(videos)}\n"
    msg += f"💾 Storage: File-based (permanent)"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Only admin can upload videos"""
    user_id = update.effective_user.id
    videos = context.bot_data.get("videos", [])
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can upload videos!")
        return
    
    video_file_id = None
    caption = update.message.caption or f"Video #{len(videos) + 1}"
    
    # Get file_id from video
    if update.message.video:
        video_file_id = update.message.video.file_id
    elif update.message.document and update.message.document.mime_type.startswith('video/'):
        video_file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Please send a video file!")
        return
    
    # Save to memory and file
    video_data = {
        'file_id': video_file_id,
        'caption': caption,
        'added_by': update.effective_user.first_name,
        'added_at': datetime.now().isoformat()
    }
    
    videos.append(video_data)
    context.bot_data["videos"] = videos
    await save_videos(videos)  # Save to file immediately
    
    await update.message.reply_text(
        f"✅ *Video #{len(videos)} saved!*\n\n"
        f"📝 {caption[:100]}\n"
        f"💾 Saved to permanent storage\n\n"
        f"Users can now watch it using /send10",
        parse_mode='Markdown'
    )

async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit=None):
    """Send videos to users"""
    # Ensure videos are fresh
    videos = context.bot_data.get("videos", [])
    
    if not videos:
        await update.message.reply_text("📭 No videos in library yet!")
        return
    
    count = len(videos) if limit is None else min(limit, len(videos))
    
    await update.message.reply_text(
        f"📹 Sending {count} of {len(videos)} videos...\n"
        f"⏳ Please wait...",
        parse_mode='Markdown'
    )
    
    sent = 0
    failed = 0
    
    for idx, video in enumerate(videos[:count], start=1):
        try:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video['file_id'],
                caption=f"🎬 Video {idx}/{count}\n📝 {video['caption'][:100]}",
                timeout=30
            )
            sent += 1
            await asyncio.sleep(0.3)  # Standard rate limiting prevention
            
        except RetryAfter as e:
            # Respect Telegram's specific rate limit request
            await asyncio.sleep(e.retry_after + 1)
            # Try once more
            try:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video['file_id'],
                    caption=f"🎬 Video {idx}/{count}\n📝 {video['caption'][:100]}",
                    timeout=30
                )
                sent += 1
            except Exception:
                failed += 1
                
        except Exception as e:
            print(f"Error sending video {idx}: {e}")
            failed += 1
    
    await update.message.reply_text(
        f"✅ *Complete!*\n\n"
        f"✓ Sent: {sent}\n"
        f"✗ Failed: {failed}\n"
        f"📊 Total: {len(videos)}",
        parse_mode='Markdown'
    )

async def send10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=10)

async def send50(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=50)

async def send100(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=100)

async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=None)

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    videos = context.bot_data.get("videos", [])
    await update.message.reply_text(
        f"📊 *Library Stats*\n\n"
        f"📹 Videos: {len(videos)}\n"
        f"💾 Storage: videos.json file\n"
        f"✅ Persists across restarts",
        parse_mode='Markdown'
    )

async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    videos = context.bot_data.get("videos", [])
    if not videos:
        await update.message.reply_text("No videos!")
        return
    
    recent_count = min(5, len(videos))
    recent_videos = videos[-recent_count:]
    
    msg = f"🆕 *Last {recent_count} videos:*\n\n"
    for idx, video in enumerate(reversed(recent_videos), start=1):
        msg += f"{idx}. {video['caption'][:50]}\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    videos = context.bot_data.get("videos", [])
    count = len(videos)
    context.bot_data["videos"] = []
    await save_videos([])
    await update.message.reply_text(f"🗑️ Cleared {count} videos!")

async def save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Force save to file"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    videos = context.bot_data.get("videos", [])
    await save_videos(videos)
    await update.message.reply_text(f"💾 Saved {len(videos)} videos to file!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    videos = context.bot_data.get("videos", [])
    python_version = platform.python_version()
    
    await update.message.reply_text(
        f"🤖 *Bot Status*\n\n"
        f"✅ Running on Python {python_version}\n"
        f"📹 Videos: {len(videos)}\n"
        f"💾 Storage: JSON file (permanent)\n"
        f"🔄 Data survives restarts!\n"
        f"👑 Admin ID: {ADMIN_ID}",
        parse_mode='Markdown'
    )

async def on_startup(app: Application):
    """Load data when bot starts"""
    videos = await load_videos()
    app.bot_data["videos"] = videos
    print(f"✅ Loaded {len(videos)} videos from file")

def main():
    print("=" * 50)
    print("🤖 Starting Video Library Bot (File Storage)")
    print("=" * 50)
    
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ Token not set! Make sure TELEGRAM_BOT_TOKEN environment variable is defined.")
        return
    
    app = Application.builder().token(TOKEN).post_init(on_startup).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send10", send10))
    app.add_handler(CommandHandler("send50", send50))
    app.add_handler(CommandHandler("send100", send100))
    app.add_handler(CommandHandler("sendall", sendall))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("save", save))
    
    # Video upload
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO, 
        handle_video
    ))
    
    print("✅ Bot is running...")
    print("=" * 50)
    
    # Automatically handles the event loop, signals, and graceful shutdown
    app.run_polling()

if __name__ == "__main__":
    main()
