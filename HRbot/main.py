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
from botbuilder.schema import Activity, ActivityTypes, SuggestedActions, CardAction
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

            # Check if the user input matches a trigger
            if user_input in self.triggers:
                # Show typing indicator before processing response
                await turn_context.send_activity(Activity(type=ActivityTypes.typing))
                await asyncio.sleep(2)

                # Send the actual response
                response = self.triggers[user_input]
                await turn_context.send_activity(response)

                # Log the interaction
                self.log_interaction(turn_context.activity.id, turn_context.activity.text, response, "Pending")

                # Ask for feedback after the response with a display delay
                await asyncio.sleep(1)  # Short delay before showing buttons
                await self.send_feedback_request(turn_context, turn_context.activity.id)
            else:
                # Handle unrecognized input
                await turn_context.send_activity("Sorry, I don't understand that command.")
        else:
            # Handle non-message activities
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))
            await asyncio.sleep(1)
            await turn_context.send_activity("Hello, how can I help you?")

    async def send_feedback_request(self, turn_context: TurnContext, message_id):
        # Create buttons for feedback
        feedback_buttons = SuggestedActions(
            actions=[
                CardAction(title="👍", type="imBack", value="like"),
                CardAction(title="👎", type="imBack", value="dislike")
            ]
        )

        # Send feedback request with buttons
        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                text="Was this response helpful?",
                suggested_actions=feedback_buttons
            )
        )

    def log_interaction(self, message_id, question, response, feedback):
        # Log interaction in CSV file
        with open('feedback_log.csv', mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([message_id, question, response, feedback])

    async def process_feedback(self, turn_context: TurnContext):
        # Process feedback when user clicks buttons
        feedback = turn_context.activity.text
        message_id = turn_context.activity.reply_to_id

        # Update the feedback in the CSV file
        rows = []
        with open('feedback_log.csv', mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] == message_id:
                    row[3] = feedback  # Update feedback column
                rows.append(row)

        with open('feedback_log.csv', mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(rows)

        # Acknowledge feedback
        await turn_context.send_activity("Thank you for your feedback!")

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

        # Check if feedback is being processed
        if activity.text in ["like", "dislike"]:
            await BOT.process_feedback(TurnContext(ADAPTER, activity))
            return Response(status=201)

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
