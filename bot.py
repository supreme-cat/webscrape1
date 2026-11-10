import os
import time
import discord
from discord.ext import tasks, commands
import requests
from bs4 import BeautifulSoup
from deepdiff import DeepDiff
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
YOUR_DISCORD_USER_ID = int(os.getenv("DISCORD_USER_ID"))

ARTICLE_URL = "https://support.discord.com/hc/en-us/articles/360046057772-Discord-Bugs"
STATE_FILE = "last_content.txt"

intents = discord.Intents.default()
intents.message_content = True  # Required to read command messages in DMs
bot = commands.Bot(command_prefix="!", intents=intents)

def fetch_article_text():
    """Extracts all structural elements and text boxes (including mega-box announcements) from the article."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    response = requests.get(ARTICLE_URL, headers=headers)
    if response.status_code != 200:
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    article_body = soup.find("div", class_="article-body")
    
    if not article_body:
        return None
    
    # Remove unwanted side items
    for unwanted in article_body.select(".article-votes, .social-share, script, style"):
        unwanted.decompose()

    # Target all text-bearing structural tags as well as custom Zendesk callout boxes like .mega-box or .toc-box
    tags_to_find = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "blockquote", "div"]
    
    content_lines = []
    for el in article_body.find_all(tags_to_find):
        # Only grab specific container divs like mega-box or toc-box to avoid nesting duplicates, 
        # or grab standard atomic text elements.
        if el.name == "div":
            if not any(cls in el.get("class", []) for cls in ["mega-box", "toc-box"]):
                continue
                
        text = el.get_text(strip=True)
        # Avoid empty strings or exact duplicate container text wrapping
        if text and text not in content_lines:
            content_lines.append(text)
            
    return content_lines

async def process_and_notify_changes(user):
    """Core checking and diff logic shared by the loop and the manual command."""
    current_paragraphs = fetch_article_text()
    if not current_paragraphs:
        return "Failed to fetch article content."

    old_paragraphs = []
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            old_paragraphs = [line.strip() for line in f.readlines()]

    if not old_paragraphs:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(current_paragraphs))
        return "Baseline article content saved."

    if current_paragraphs != old_paragraphs:
        diff = DeepDiff(old_paragraphs, current_paragraphs)
        
        change_summary = "**Discord Bug Article Update Detected!**\n"
        change_summary += f"<{ARTICLE_URL}>\n\n"
        
        if "iterable_item_added" in diff:
            change_summary += "**Added/Changed Content:**\n"
            for key, value in diff["iterable_item_added"].items():
                change_summary += f"+ {value}\n"
        
        if "iterable_item_removed" in diff:
            change_summary += "\n**Removed Content:**\n"
            for key, value in diff["iterable_item_removed"].items():
                change_summary += f"- {value}\n"

        if len(change_summary) > 1900:
            chunks = [change_summary[i:i+1900] for i in range(0, len(change_summary), 1900)]
            for chunk in chunks:
                await user.send(chunk)
        else:
            await user.send(change_summary)

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(current_paragraphs))
        return "Changes found and sent via DM."
    else:
        return "Checked article. No changes detected."

@tasks.loop(hours=2)
async def check_article():
    user = await bot.fetch_user(YOUR_DISCORD_USER_ID)
    if not user:
        return
    result = await process_and_notify_changes(user)
    print(result)

@bot.command(name="fetch")
async def manual_fetch(ctx):
    if ctx.author.id != YOUR_DISCORD_USER_ID:
        return

    await ctx.send("Manually fetching article and checking for updates...")
    result = await process_and_notify_changes(ctx.author)
    await ctx.send(f"Result: {result}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Starting article monitor loop...")
    check_article.start()

bot.run(TOKEN)