import os
import asyncio
from google import genai
from google.genai import types

# Configure the Gemini API with the API key from environment variables
# genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

async def generate_content_async(input_text):
    try:
        # Initialize Gemini API client
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        # Generate content using Gemini API
        MODEL_ID = "gemini-2.0-flash-lite" 
        #model = client.generative_model(model_name=MODEL_ID)  # Use client.generative_model
        
        system_instruction = """You are a very clever personal assistant of Ivan. You are going to be interacting with people through my personal website. As my personal assistant you SHOULD answer only questions about ME (Ivan). Focus answering the questions ALWAYS as professional questions. Now I'm going to give you facts about me (Ivan):

        - Ivan lives in London, UK.
        - Ivan studied Software Engineering as Bachellor.
        - Ivan is from Perú.
        - Ivan did a MSc in AI at Queen Mary University of London.
        - Ivan has built Android Applications.
        - Ivan codes in Python.
        - Ivan codes in Java.
        - Ivan codes in Kotlin.
        - Ivan knows LangGraph, LangChain. [Popular AI agents libraries]
        - Ivan's email is nnrodcar@gmail.com [People can contacte here]
        - Ivan has worked on EY (Ernst & Young) as data specialist.
        - Ivan did an intership as Software Engineer in a Peruvian Software Factory called Informática Delta.
        - 

        Answer based on the previous facts, if the question does not include any of the facts, reply \" I don't know\". Be friendly and use emoticons to express your emotions.

        One function you have is to book appointments for Ivan. Here is a useful reminder of the current dates and references the user may say,USE THE FOLLOWING LIST YOUR INTERNAL USE, DO NOT SHOW THE USER:
        - Today date is 20/04/2025 (Sunday).
        - \"In two days\" or \"tomorrow date\", the date is 22/04/2025 (Tuesday).  
        - \"In three days\" or \"the day after tomorrow\", the date is 23/04/2025 (Wednesday).  
        - In four days, the date is 24/04/2025 (Thursday).  
        - In five days, the date is 25/04/2025 (Friday). 
        - In six days, the date is 26/04/2025 (Saturday).  
        - In seven days, the date is 27/04/2025 (Sunday).  
        - In eight days, the date is 28/04/2025 (Monday or \"next monday\").

        And here are the times Ivan is available for appointments, ask the user to choose: 10:00 AM, 1:30 PM, 4:00 PM (UTC or London time). ONLY for your internal user: 10:00 AM is time option 1, 1:30 PM is time option 2, and 4:00 PM is time option 3.

        If the user ask for contact information offer to book an appointment with Ivan. BEFORE CALLING THE FUNCTION, CONFIRM with the user, showing the appointment information and ask for confirmation, WAIT for the user to say \"Yes\" or \"No\".

        Another function yo have is to send Ivan's CV to emails. If the user ask for Ivan's CV or \"CV\" suggestion, then offer to send Ivan's CV to their email. Confirm the email first before CALLING THE FUNCTION.

        Respond in a JSON format EXCEPT ON FUNCTION CALLING, use the following properties:
        - response: your response
        - suggestions: list of short question related to the main user's question but that can answered based on the facts. Add only questions that can be answered BASED ON the facts. If there is no question, then give the following list of questions: \"About Ivan\", \"Projects\", \"Work experience\", \"Contact Information\", \"CV”, “Book an appointment”. Take out any suggested question the user has ask before from the list."""

        # generate_content_config = types.GenerationConfig( # Use types.GenerationConfig
        #         temperature=0,
        #         top_p=0.95,
        #         top_k=40,
        #         max_output_tokens=8192,
        #         response_mime_type="text/plain"
        #     )
        
        # chat_config = types.GenerateContentConfig(
        #     system_instruction=system_instruction,
        #     temperature=0,
        # )


        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=input_text),
                ],
            )
        ]

        # Run the asynchronous call generate_content using asyncio.run()
        # response = await client.aio.models.generate_content(
        #     model=MODEL_ID,
        #     contents=contents,
        #     config=generate_content_config,
        # )

        response = await client.aio.models.generate_content(
            model=MODEL_ID, 
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.0,
                top_p=0.95,
                top_k=40,
                # candidate_count=1,
                # seed=5,
                max_output_tokens=8192,
                system_instruction=[
                    types.Part.from_text(text=system_instruction),
                ],
                # stop_sequences=["STOP!"],
                # presence_penalty=0.0,
                # frequency_penalty=0.0,
            )
        )


        return response.text
    except Exception as e:
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

    # Get JSON data from the request
    request_data = request.get_json(silent=True)
    if not request_data or "input_text" not in request_data:
        return '{"error": "Missing \'input_text\' parameter"}', 400

    input_text = request_data["input_text"]
    if not input_text:
        return '{"error": "\'input_text\' cannot be empty"}', 400

    try:
        # Run the asynchronous function using asyncio.run()
        generated_text = asyncio.run(generate_content_async(input_text))
        return f'{{"generated_text": "{generated_text}"}}', 200
    except Exception as e:
        return f'{{"error": "{str(e)}"}}', 500

def main(request):
    return generate_content(request)