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

CONFIG = DefaultConfig()
SETTINGS = BotFrameworkAdapterSettings(CONFIG.APP_ID, CONFIG.APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)

class FeedbackMiddleware:
    async def on_turn(self, turn_context: TurnContext, next_call):
        # Check if the activity is a feedback response
        if turn_context.activity.text in ["like", "dislike"]:
            await BOT.process_feedback(turn_context)  # Process feedback
            await turn_context.send_activity("Can I assist you with something else!")
            return  # Prevent further processing

        # Continue with normal processing
        await next_call()

class MyBot:
    def __init__(self, triggers):
        self.triggers = triggers
        self.last_message_id = None  # Store the last sent message ID

    async def on_turn(self, turn_context: TurnContext):
        if turn_context.activity.text:
            user_input = turn_context.activity.text.strip().lower()

            # Check if user input matches a trigger
            if user_input in self.triggers:
                await turn_context.send_activity(Activity(type=ActivityTypes.typing))
                await asyncio.sleep(2)

                # Send response
                response = self.triggers[user_input]
                activity = await turn_context.send_activity(response)

                # Log interaction
                self.last_message_id = activity.id  # Save the message ID
                self.log_interaction(activity.id, turn_context.activity.text, response, "Pending")

                # Ask for feedback
                await asyncio.sleep(1)
                await self.send_feedback_request(turn_context, activity.id)
            else:
                await turn_context.send_activity("Sorry, I don't understand that command.")
        else:
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))
            await asyncio.sleep(1)
            await turn_context.send_activity("Hello, how can I help you?")

    async def send_feedback_request(self, turn_context: TurnContext, message_id):
        feedback_buttons = SuggestedActions(
            actions=[
                CardAction(title="👍", type="imBack", value="like"),
                CardAction(title="👎", type="imBack", value="dislike")
            ]
        )

        await turn_context.send_activity(
            Activity(
                type=ActivityTypes.message,
                text="Was this response helpful?",
                suggested_actions=feedback_buttons,
                reply_to_id=message_id  # Explicitly attach reply_to_id
            )
        )

    def log_interaction(self, message_id, question, response, feedback):
        with open('feedback_log.csv', mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([message_id, question, response, feedback])

    async def process_feedback(self, turn_context: TurnContext):
        feedback = turn_context.activity.text
        message_id = turn_context.activity.reply_to_id or self.last_message_id  # Use stored ID if reply_to_id is None

        print(f"Feedback Received: {feedback}, Message ID: {message_id}")

        # Update feedback in the CSV file
        rows = []
        updated = False
        with open('feedback_log.csv', mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] == message_id:
                    row[3] = feedback  # Update feedback column
                    updated = True
                rows.append(row)

        # Fallback: If no match, update the last row
        if not updated and rows:
            rows[-1][3] = feedback
            updated = True

        with open('feedback_log.csv', mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(rows)

        if updated:
            await turn_context.send_activity("Thank you for your feedback!")
        else:
            await turn_context.send_activity("Feedback not associated with a previous response.")


def load_csv_data(file_path):
    triggers = {}
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            triggers[row['Trigger Phrase'].lower()] = row['Response']
    return triggers

triggers_responses = load_csv_data('triggers_data.csv')
BOT = MyBot(triggers_responses)

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
ADAPTER.use(FeedbackMiddleware())

async def messages(req: Request) -> Response:
    if "application/json" in req.headers["Content-Type"]:
        body = await req.json()
        activity = Activity().deserialize(body)
        auth_header = req.headers["Authorization"] if "Authorization" in req.headers else ""

        # Process activity (feedback handled by middleware)
        response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        if response:
            return json_response(data=response.body, status=response.status)
        return Response(status=200)
    else:
        return Response(status=415)

APP = web.Application(middlewares=[aiohttp_error_middleware])
APP.router.add_post("/api/messages", messages)

if __name__ == "__main__":
    web.run_app(APP, host="localhost", port=CONFIG.PORT)
