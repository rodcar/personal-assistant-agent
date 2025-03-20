import os
import asyncio
from google import genai
from google.genai import types

def read_system_instruction(file_path):
    """Read system instruction from a file."""
    try:
        # Using absolute path to ensure reliability in cloud environment
        abs_path = os.path.join(os.path.dirname(__file__), file_path)
        with open(abs_path, 'r') as file:
            return file.read()
    except Exception as e:
        print(f"Error reading system instruction file: {e}")
        # Fall back to a simple instruction if the file can't be read   
        return "You are a helpful assistant for Ivan. Answer questions professionally."

async def generate_content_async(input_text):
    try:
        # Initialize Gemini API client
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        MODEL_ID = "gemini-2.0-flash-lite"

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=input_text),
                ],
            )
        ]
        
        # Read system instruction from file
        # Use a relative path from the function's root directory
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
                            description="User accepts to be send Ivan's CV to his/her email",
                            parameters=genai.types.Schema(
                                type = genai.types.Type.OBJECT,
                                properties = {
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