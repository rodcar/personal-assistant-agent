import os
import json
import asyncio
import datetime
import uuid  # Add this import for generating unique IDs
from zoneinfo import ZoneInfo  # For timezone handling
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.types import (
    FunctionDeclaration,
    GenerateContentConfig,
    GenerateContentResponse,
    Part,
    Tool,
)

import base64
# Replace EmailMessage import with these
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# email
#from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Load service account credentials from environment variable
#os.getenv('GEMINI_API_KEY')
#SERVICE_ACCOUNT_INFO = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
with open(os.path.join(os.path.dirname(__file__), 'personal-assistant-2025-edcd74d26375.json')) as f:
    SERVICE_ACCOUNT_INFO = json.load(f)
#SCOPES = ["https://www.googleapis.com/auth/calendar"]
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/gmail.send"]

#credentials = service_account.Credentials.from_service_account_info(
#    SERVICE_ACCOUNT_INFO, scopes=SCOPES
#)

PRINCIPAL_EMAIL = "nnrodcar@gmail.com"
PRINCIPAL_CALENDAR_ID = "8fcf00a41b1d8b5ca37408238ce07c9d1abd6873e3d792f4cef9217853fcda02@group.calendar.google.com"
PRINCIPAL_TIME_ZONE = "Europe/London"

def get_credentials():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def extract_function_calls(response: GenerateContentResponse) -> list[dict]:
    if response.function_calls is None:
            return []

    function_calls: list[dict] = []
    for function_call in response.function_calls:
        function_call_dict: dict[str, dict[str, Any]] = {function_call.name: {}}
        for key, value in function_call.args.items():
            function_call_dict[function_call.name][key] = value
        function_calls.append(function_call_dict)
    return function_calls

def generate_dynamic_dates():
    """Generate a string of dynamic dates based on the current date in London timezone."""
    # Get current time in London/UK timezone
    today = datetime.datetime.now(ZoneInfo("Europe/London"))
    
    date_info = []
    
    # Today
    date_info.append(f"- Today date is {today.strftime('%d/%m/%Y')} ({today.strftime('%A')}).")
    
    # Tomorrow
    tomorrow = today + datetime.timedelta(days=1)
    date_info.append(f'- Tomorrow date is {tomorrow.strftime("%d/%m/%Y")} ({tomorrow.strftime("%A")}).')
    
    # In two days (labeled as "the day after tomorrow")
    two_days = today + datetime.timedelta(days=2)
    date_info.append(f'- "In two days" or "the day after tomorrow", the date is {two_days.strftime("%d/%m/%Y")} ({two_days.strftime("%A")}).')
    
    # In three days (labeled as "the day after tomorrow")
    three_days = today + datetime.timedelta(days=3)
    date_info.append(f'- "In three days" or "the day after tomorrow", the date is {three_days.strftime("%d/%m/%Y")} ({three_days.strftime("%A")}).')
    
    # Add 4-8 days
    day_names = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    for i in range(4, 9):
        future_date = today + datetime.timedelta(days=i)
        day_str = future_date.strftime("%A")
        
        # Special case for day 8
        if i == 8:
            date_info.append(f"- In {day_names[i]} days, the date is {future_date.strftime('%d/%m/%Y')} ({day_str} or \"next {day_str}\").")
        else:
            date_info.append(f"- In {day_names[i]} days, the date is {future_date.strftime('%d/%m/%Y')} ({day_str}).")
    
    return "\n".join(date_info)

def read_system_instruction(file_path):
    """Read system instruction from a file and inject dynamic dates."""
    try:
        # Using absolute path to ensure reliability in cloud environment
        abs_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_path, 'r') as file:
            content = file.read()
        
        # Generate dynamic dates
        dynamic_dates = generate_dynamic_dates()
        
        # Replace the hardcoded date section with dynamic dates
        #appointment_phrase = "One function you have is to book appointments for Ivan. Here is a useful reminder of the current dates and references the user may say,USE THE FOLLOWING LIST YOUR INTERNAL USE, DO NOT SHOW THE USER:"
        appointment_phrase = "One function you have is to book appointments for Ivan. Here is a useful reminder of the current dates and references the user may say,USE THE FOLLOWING LIST WHEN THE USER WANT AN APPOINTMENT, THEN INTERPRET THE DATE USER SAYS:"
        available_times_phrase = "And here are the times Ivan is available for appointments"
        
        if appointment_phrase in content and available_times_phrase in content:
            parts = content.split(appointment_phrase)
            if len(parts) == 2:
                before_dates = parts[0] + appointment_phrase + "\n"
                
                after_dates_parts = parts[1].split(available_times_phrase)
                if len(after_dates_parts) == 2:
                    after_dates = "\n\n" + available_times_phrase + after_dates_parts[1]
                    
                    # Combine everything with the dynamic dates
                    return before_dates + dynamic_dates + after_dates
        
        # If we couldn't find the markers or something went wrong, return the original content
        print(content)
        return content
    except Exception as e:
        print(f"Error reading system instruction file: {e}")
        # Fall back to a simple instruction if the file can't be read   
        return "You are a helpful assistant for Ivan. Answer questions professionally."

def check_free_time(service, date, start_time, end_time):
    time_min = f"{date}T{start_time}:00Z"
    time_max = f"{date}T{end_time}:00Z"
    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "timeZone": "UTC",
        "items": [{"id": PRINCIPAL_CALENDAR_ID}]
    }
    try:
        events_result = service.freebusy().query(body=body).execute()
        busy_times = events_result['calendars'][PRINCIPAL_CALENDAR_ID]['busy']
        return len(busy_times) == 0
    except HttpError as error:
        print(f"An error occurred: {error}")
        return False

async def generate_content_async(chat_data):
    try:
        creds = get_credentials()
        # Initialize Google Calendar API
        service = build("calendar", "v3", credentials=creds)
        # Initialize Gemini API client
        client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

        MODEL_ID = "gemini-2.0-flash-lite"

        # Use chat_data directly instead of parsing it again
        data = chat_data

        # Generate the contents list from the input_text list
        contents = [
            types.Content(
                role=item["role"],
                parts=[
                    types.Part.from_text(text=item["parts"]),
                ],
            )
            for item in data
        ]
        
        # Read system instruction from file
        system_instruction = read_system_instruction("system_instruction.txt")

        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="makeAppointment",
                        description="User's accepts with \"Yes\" to make an appoitment with Ivan",
                        parameters=genai.types.Schema(
                            type = genai.types.Type.OBJECT,
                            properties = {
                                "date": genai.types.Schema(
                                    type = genai.types.Type.OBJECT,
                                    properties = {
                                        "dayOfMonth": genai.types.Schema(
                                            type = genai.types.Type.NUMBER,
                                        ),
                                        "Month": genai.types.Schema(
                                            type = genai.types.Type.NUMBER,
                                        ),
                                        "Year": genai.types.Schema(
                                            type = genai.types.Type.NUMBER,
                                        ),
                                        "timeOption": genai.types.Schema(
                                            type = genai.types.Type.NUMBER,
                                        ),
                                    },
                                ),
                                "email": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                                "name": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                            },
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="sendCV",
                        description="User shares his/her email to receive Ivan's CV",
                        parameters=genai.types.Schema(
                            type = genai.types.Type.OBJECT,
                            properties = {
                                "email": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                            },
                        ),
                    ),
                    # types.FunctionDeclaration(
                    #     name="check_free_time_specific_day",
                    #     description="Check Ivan's availability for an specific date before booking",
                    #     parameters=genai.types.Schema(
                    #         type = genai.types.Type.OBJECT,
                    #         properties = {
                    #             "date": genai.types.Schema(
                    #                 type = genai.types.Type.OBJECT,
                    #                 properties = {
                    #                     "dayOfMonth": genai.types.Schema(
                    #                         type = genai.types.Type.NUMBER,
                    #                     ),
                    #                     "Month": genai.types.Schema(
                    #                         type = genai.types.Type.NUMBER,
                    #                     ),
                    #                     "Year": genai.types.Schema(
                    #                         type = genai.types.Type.NUMBER,
                    #                     )
                    #                 },
                    #             )
                    #         },
                    #     ),
                    # ),
                    # types.FunctionDeclaration(
                    #     name="check_free_time_specific_day_and_time",
                    #     description="Check Ivan's availability for an specific date and time before booking",
                    #     parameters=genai.types.Schema(
                    #         type = genai.types.Type.OBJECT,
                    #         properties = {
                    #             "date": genai.types.Schema(
                    #                 type = genai.types.Type.OBJECT,
                    #                 properties = {
                    #                     "dayOfMonth": genai.types.Schema(
                    #                         type = genai.types.Type.NUMBER,
                    #                     ),
                    #                     "Month": genai.types.Schema(
                    #                         type = genai.types.Type.NUMBER,
                    #                     ),
                    #                     "Year": genai.types.Schema(
                    #                         type = genai.types.Type.NUMBER,
                    #                     ),
                    #                     "timeOption": genai.types.Schema(
                    #                         type = genai.types.Type.NUMBER,
                    #                     ),
                    #                 },
                    #             )
                    #         },
                    #     ),
                    # ),
                    types.FunctionDeclaration(
                        name="leaveOrSendAMessageTo",
                        description="User leave or sends a message to Ivan",
                        parameters=genai.types.Schema(
                            type = genai.types.Type.OBJECT,
                            properties = {
                                "message": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                                "name": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                                "email": genai.types.Schema(
                                    type = genai.types.Type.STRING,
                                ),
                            },
                        ),
                    ),
                ])
        ]
        
        generate_content_config = types.GenerateContentConfig(
            temperature=0.0,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            tools=tools,
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text=system_instruction),
            ],
        )

        response = await client.aio.models.generate_content(
            model=MODEL_ID, 
            contents=contents,
            config=generate_content_config
        )

        function_calls = extract_function_calls(response)

        api_response: dict[str, Any] = {}  # type: ignore

        # Loop over multiple function calls
        if function_calls:
            for function_call in function_calls:
                print(function_call)
                for function_name, function_args in function_call.items():
                    # Determine which external API call to make
                    if function_name == "makeAppointment":
                        result = "Appointment made successfully."

                        # Determine start and end times based on timeOption
                        time_options = {
                            1: ("10:00", "11:00"),
                            2: ("13:30", "14:30"),
                            3: ("16:00", "17:00"),
                        }
                        start_time, end_time = time_options.get(function_args['date']['timeOption'], ("10:00", "11:00"))

                        # Convert to UTC for checking availability
                        date_str = f"{function_args['date']['Year']}-{function_args['date']['Month']:02d}-{function_args['date']['dayOfMonth']:02d}"
                        start_time_utc = datetime.datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/London")).astimezone(ZoneInfo("UTC")).strftime("%H:%M")
                        end_time_utc = datetime.datetime.strptime(f"{date_str} {end_time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/London")).astimezone(ZoneInfo("UTC")).strftime("%H:%M")

                        if not check_free_time(service, date_str, start_time_utc, end_time_utc):
                            # Check availability for other time slots on the same day
                            other_time_slots = {
                                1: ("10:00", "11:00"),
                                2: ("13:30", "14:30"),
                                3: ("16:00", "17:00"),
                            }
                            available_slots = {}
                            for option, (start, end) in other_time_slots.items():
                                if option != function_args['date']['timeOption']:
                                    start_utc = datetime.datetime.strptime(f"{date_str} {start}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/London")).astimezone(ZoneInfo("UTC")).strftime("%H:%M")
                                    end_utc = datetime.datetime.strptime(f"{date_str} {end}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/London")).astimezone(ZoneInfo("UTC")).strftime("%H:%M")
                                    if check_free_time(service, date_str, start_utc, end_utc):
                                        available_slots[option] = f"{start} - {end}"

                            api_response[function_name] = {
                                "message": "No slot time available",
                                "available_slots": available_slots
                            }

                            contents.append(
                                types.Content(
                                    role="model",
                                    parts=[
                                        types.Part.from_text(text=f"""```Function call
                        {json.dumps(api_response['makeAppointment'], indent=4)}
                        ```"""),
                                    ]
                                )
                            )

                            response_function_calling = await client.aio.models.generate_content(
                                model=MODEL_ID,
                                contents=contents,
                                config=generate_content_config
                            )
                            print(api_response)
                            return response_function_calling.text
                        else:
                            event = {
                                "summary": f"General Discussion",
                                "description": "description",
                                "start": {
                                    "dateTime": f"{date_str}T{start_time}:00",
                                    "timeZone": PRINCIPAL_TIME_ZONE
                                },
                                "end": {
                                    "dateTime": f"{date_str}T{end_time}:00",
                                    "timeZone": PRINCIPAL_TIME_ZONE
                                },
                                "conferenceData": {
                                    "createRequest": {
                                        "requestId": str(uuid.uuid4()),
                                        'conferenceSolutionKey': {
                                            'type': 'hangoutsMeet'
                                        },
                                        'status': {
                                            'statusCode': 'success'
                                        }
                                    }
                                },
                            }

                            event = service.events().insert(
                                calendarId=PRINCIPAL_CALENDAR_ID, body=event, conferenceDataVersion=1
                            ).execute()

                            # Format the datetime as "July 15, 2024 at 2:30 PM"
                            formatted_date = datetime.datetime(
                                function_args['date']['Year'],
                                function_args['date']['Month'],
                                function_args['date']['dayOfMonth'],
                                int(start_time.split(":")[0]),
                                int(start_time.split(":")[1])
                            ).strftime("%B %d, %Y at %I:%M %p")

                            result = {
                                "eventLink": event.get("htmlLink"),
                                "meetLink": event.get('conferenceData', {}).get('entryPoints', [{}])[0].get('uri', 'No Meet Link'),
                                "date": formatted_date
                            }

                            print(event.get("htmlLink"))
                            api_response[function_name] = result
                    if function_name == "sendCV":
                        result = "CV sent successfully."
                        try:
                                service = build("gmail", "v1", credentials=creds)
                                # Replace EmailMessage with MIMEMultipart
                                message = MIMEMultipart()

                                # Body of the email
                                body = "Hello,\n\nI hope you're doing well.\n\nI'm sending over my CV for your reference.\n\nFeel free to reach out if you need more information. Thanks for your time!\n\nBest regards,\nIvan Yang Rodriguez Carranza"

                                # Add text content as a part
                                message.attach(MIMEText(body))

                                # Use the provided email argument
                                message["To"] = function_args["email"]
                                message["From"] = PRINCIPAL_EMAIL
                                message["Subject"] = "CV of Ivan Yang Rodriguez Carranza"

                                # Attach a file
                                attachment_file_path = "Ivan_Yang_Rodriguez_Carranza_CV.pdf"  # Replace with your file path
                                with open(attachment_file_path, "rb") as attachment_file:
                                    file_data = attachment_file.read()
                                    file_name = os.path.basename(attachment_file_path)

                                    part = MIMEBase("application", "pdf")
                                    part.set_payload(file_data)
                                    encoders.encode_base64(part)
                                    part.add_header(
                                        "Content-Disposition", f"attachment; filename={file_name}"
                                    )

                                    message.attach(part)

                                # Convert message to string and then encode to base64
                                encoded_message = base64.urlsafe_b64encode(message.as_string().encode()).decode()

                                create_message = {"raw": encoded_message}

                                # Send the message
                                send_message = (
                                    service.users()
                                    .messages()
                                    .send(userId="me", body=create_message)
                                    .execute()
                                )
                                print(f'Message Id: {send_message["id"]}')
                                api_response[function_name] = result
                        except HttpError as error:
                            print(f"An error occurred: {error}")
                            send_message = None
                    if function_name == "check_free_time_specific_day":
                        date = function_args['date']
                        day = date['dayOfMonth']
                        month = date['Month']
                        year = date['Year']
                        date_str = f"{year}-{month:02d}-{day:02d}"
                        
                        # Check availability for specific times
                        time_slots = [
                            ("10:00:00", "11:00:00"),
                            ("13:30:00", "14:30:00"),
                            ("16:00:00", "17:00:00")
                        ]
                        
                        availability = {}
                        for start_time, end_time in time_slots:
                            is_free = check_free_time(service, date_str, start_time, end_time)
                            availability[f"{start_time}-{end_time}"] = is_free
                        
                        result = {
                            "date": date_str,
                            "availability": availability
                        }
                        
                        api_response[function_name] = result
                    if function_name == "check_free_time_specific_day_and_time":
                        date = function_args['date']
                        day = date['dayOfMonth']
                        month = date['Month']
                        year = date['Year']
                        time_option = date['timeOption']
                        
                        # Determine start and end times based on timeOption
                        time_options = {
                            1: ("10:00:00", "11:00:00"),
                            2: ("13:30:00", "14:30:00"),
                            3: ("16:00:00", "17:00:00"),
                        }
                        start_time, end_time = time_options.get(time_option, ("10:00", "11:00"))
                        
                        date_str = f"{year}-{month:02d}-{day:02d}"
                        
                        # Check availability for the specific time
                        is_free = check_free_time(service, date_str, start_time, end_time)
                        
                        result = {
                            "date": date_str,
                            "time": f"{start_time}-{end_time}",
                            "is_free": is_free
                        }
                        
                        api_response[function_name] = result

                    if function_name == "leaveOrSendAMessageTo":
                        result = "Message not sent successfully."
                        try:
                            service = build("gmail", "v1", credentials=creds)
                            # Replace EmailMessage with MIMEMultipart
                            message = MIMEMultipart()

                            # Body of the email
                            body = function_args["message"] + "\n\nBy: \n" + function_args["name"] + "\n" + function_args["email"]

                            # Add text content as a part
                            message.attach(MIMEText(body))

                            # Use the provided email argument
                            message["To"] = PRINCIPAL_EMAIL
                            message["From"] = PRINCIPAL_EMAIL
                            # Remove newline characters from the subject
                            message["Subject"] = f"Message from {function_args['name']}".replace("\n", " ")

                            # Convert message to string and then encode to base64
                            encoded_message = base64.urlsafe_b64encode(message.as_string().encode()).decode()

                            create_message = {"raw": encoded_message}

                            # Send the message
                            send_message = (
                                service.users()
                                .messages()
                                .send(userId="me", body=create_message)
                                .execute()
                            )
                            print(f'Message Id: {send_message["id"]}')
                            api_response[function_name] = "Message sent successfully."


                            contents.append(
                                types.Content(
                                    role="model",
                                    parts=[
                                        types.Part.from_text(text=f"""```Function call
                        {json.dumps(api_response['leaveOrSendAMessageTo'], indent=4)}
                        ```"""),
                                    ]
                                )
                            )

                            response_function_calling = await client.aio.models.generate_content(
                                model=MODEL_ID,
                                contents=contents,
                                config=generate_content_config
                            )
                            print(api_response)
                            return response_function_calling.text
                        except HttpError as error:
                            print(f"An error occurred: {error}")
                            send_message = None
                    #if function_name == "summarize_wikipedia":
                        #result = wikipedia.summary(function_args["topic"], auto_suggest=False)

                    # Collect all API responses
                    #api_response[function_name] = send_message

        if api_response:
            return json.dumps(api_response), 200, {'Content-Type': 'application/json'}

        return response.text
    except Exception as e:
        print(f"An error occurred: {e}")
        raise e

def generate_content(request):
    """
    HTTP Cloud Function that generates content based on input_text from a POST request.
    Args:
        request (flask.Request): The request object from Cloud Functions
    Returns:
        str or tuple: Response text or (text, status_code)
    """
    # Health check response for GET requests
    if request.method == "GET":
        return "Healthy: Send a POST request with {'input_text': 'your text'} to generate content", 200

    # Handle POST requests
    if request.method != "POST":
        return "Method not allowed. Use POST.", 405

    try:
        # Get JSON data from the request with more detailed error handling
        request_data = request.get_json(silent=True)
        if not request_data:
            return json.dumps({"error": "Invalid JSON or empty request body"}), 400, {'Content-Type': 'application/json'}
        
        # Check if chat exists in the request data
        if "chat" not in request_data:
            return json.dumps({"error": "Missing 'chat' field in request"}), 400, {'Content-Type': 'application/json'}
        
        chat = request_data["chat"]
        
        # Verify chat is a list
        if not isinstance(chat, list):
            return json.dumps({"error": f"'chat' must be a list, got {type(chat).__name__}"}), 400, {'Content-Type': 'application/json'}
        
        if not chat:
            return json.dumps({"error": "'chat' cannot be empty"}), 400, {'Content-Type': 'application/json'}
            
        # Run the asynchronous function using asyncio.run()
        generated_text = asyncio.run(generate_content_async(chat))
        
        # Properly format the JSON response
        response_data = {"generated_text": generated_text}
        return json.dumps(response_data), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        # Include traceback for better debugging
        import traceback
        error_response = {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        return json.dumps(error_response), 500, {'Content-Type': 'application/json'}

def main(request):
    return generate_content(request)