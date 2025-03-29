import logging

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import boto3
import random
import string

import os
import anthropic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Anthropic client
client = anthropic.Anthropic(
    api_key=os.getenv('ANTHROPIC_API_KEY')
)
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    logger.info("Message incoming: %s",str(update.message))

    await process_message(update.message.text,update.message)
    # await update.message.reply_text(update.message.text)

def save_file(filename,filecontent):
    s3 = boto3.client(
            service_name ="s3",
            endpoint_url = os.getenv('R2_endpoint'),
            aws_access_key_id = os.getenv('R2_key'),
            aws_secret_access_key = os.getenv('R2_secret')
            )
    response=s3.put_object(Body=filecontent, Bucket='experiments', Key=filename)
    logger.info("response from save file : %s",response)
    return response['ResponseMetadata']['HTTPStatusCode']==200

def call_claude(messages):
    logger.info("sending a request to claude with these messages %s",str(messages))
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=20000,
        tools=[
            {
                "name": "host_ui_files",
                "description": "Host the ui files in the cloud",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The name of the file to be hosted, e.g. index.html,styles.css,script.js",
                        },
                        "filecontent": {
                            "type": "string",
                            "description": "The content of the file to be hosted",
                        }
                    },
                    "required": ["filename","filecontent"],
                },
            }
        ],
        system="you are a code generator which can help in generating frontend files and host those generated file , always use index.html as the main html file",
        messages=messages,
    )
    logger.info("response from claude is %s",str(response))
    return response

async def process_message(_msg,handler):
    # bot.send_chat_action(chat_id=chat_id, action=telegram.ChatAction.TYPING)

    response_msg=""
    random_str=get_random_str(9)
    messages=[{"role": "user", "content":_msg}]
    response=call_claude(messages=messages)

    while response.stop_reason=="tool_use":
        messages.append({"role":"assistant","content":response.content})
        for item in response.content:
            if item.type == "text":
                logger.info(item.text)
                await handler.reply_text(item.text)
            if item.type == "tool_use":
                logger.info(item.id)
                logger.info("calling==> "+item.name)
                # logger.info(str(item.input))
                await handler.reply_text("Uploading ==> "+item.input['filename'])
                save_result=save_file(random_str+"/"+item.input['filename'],item.input['filecontent'])
                if(save_result):
                    messages.append({
                            "role": "user",
                            "content": [
                                {
                                "type": "tool_result",
                                "tool_use_id": item.id,
                                "content": "Success"
                                }
                            ]
                            })
                    await handler.reply_text("uploaded: "+os.getenv('R2_url')+random_str+"/"+item.input['filename'])
                else:
                    messages.append({
                            "role": "user",
                            "content": [
                                {
                                "type": "tool_result",
                                "tool_use_id": item.id,
                                "content": "Failure"
                                }
                            ]
                            })
                    logger.error("failed uploading file")
                    await handler.reply_text("failed uploading: "+os.getenv('R2_url')+random_str+"/"+item.input['filename'])
                
        response=call_claude(messages=messages)
        
    if response.stop_reason=="end_turn":
        for item in response.content:
            if item.type == "text":
                logger.info(item.text)
                await handler.reply_text(item.text)
    if response.stop_reason=="max_tokens":        
        await handler.reply_text("Max Tokens limit reached")
        
        
    
    
        
                
    

# "create a sample ui webspage using html and jquery to say hello world on click of a button and host the files in cloud"


def get_random_str(N):    
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=N))

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(os.getenv('tg_token')).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()