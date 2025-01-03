import csv
import sys
import traceback
import asyncio
from datetime import datetime
from aiohttp import web
from aiohttp.web import Request, Response, json_response
from botbuilder.core import (
    BotFrameworkAdapterSettings,
    TurnContext,
    BotFrameworkAdapter,
)
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.schema import Activity, ActivityTypes
from config import DefaultConfig

# Load configuration from config.py
CONFIG = DefaultConfig()

# Initialize BotFrameworkAdapter
SETTINGS = BotFrameworkAdapterSettings(CONFIG.APP_ID, CONFIG.APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)

# Define the Bot class
class MyBot:
    def __init__(self, triggers):
        self.triggers = triggers

    async def on_turn(self, turn_context: TurnContext):
        if turn_context.activity.text:
            user_input = turn_context.activity.text.strip().lower()

            # Show typing activity BEFORE processing
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))
            await asyncio.sleep(2)

            # Check if the user input matches a trigger
            if user_input in self.triggers:
                # Send the actual response
                await turn_context.send_activity(self.triggers[user_input])
            else:
                await turn_context.send_activity("Sorry, I don't understand that command.")
        else:
            # Handle non-message activities
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))
            await asyncio.sleep(2)
            await turn_context.send_activity("Hello, how can I help you?")

# Load triggers and responses from a CSV file
def load_csv_data(file_path):
    triggers = {}
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            triggers[row['Trigger Phrase'].lower()] = row['Response']
    return triggers

triggers_responses = load_csv_data('triggers_data.csv')
BOT = MyBot(triggers_responses)

# Error handler
async def on_error(context: TurnContext, error: Exception):
    print(f"\n [on_turn_error] unhandled error: {error}", file=sys.stderr)
    traceback.print_exc()
    await context.send_activity("The bot encountered an error or bug.")
    if context.activity.channel_id == "emulator":
        trace_activity = Activity(
            label="TurnError",
            name="on_turn_error Trace",
            timestamp=datetime.utcnow(),
            type=ActivityTypes.trace,
            value=str(error),
            value_type="https://www.botframework.com/schemas/error",
        )
        await context.send_activity(trace_activity)

ADAPTER.on_turn_error = on_error

# Define messages endpoint
async def messages(req: Request) -> Response:
    if "application/json" in req.headers["Content-Type"]:
        body = await req.json()
        activity = Activity().deserialize(body)
        auth_header = req.headers["Authorization"] if "Authorization" in req.headers else ""
        response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        if response:
            return json_response(data=response.body, status=response.status)
        return Response(status=201)
    else:
        return Response(status=415)

# Set up web server
APP = web.Application(middlewares=[aiohttp_error_middleware])
APP.router.add_post("/api/messages", messages)

# Run the application
if __name__ == "__main__":
    web.run_app(APP, host="localhost", port=CONFIG.PORT)
