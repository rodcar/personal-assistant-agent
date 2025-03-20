import os
import json
import asyncio
from google import genai
from google.genai import types
from google.genai.types import (
    FunctionDeclaration,
    GenerateContentConfig,
    GenerateContentResponse,
    Part,
    Tool,
)

def extract_function_calls(response: GenerateContentResponse) -> list[dict]:
    function_calls: list[dict] = []
    for function_call in response.function_calls:
        function_call_dict: dict[str, dict[str, Any]] = {function_call.name: {}}
        for key, value in function_call.args.items():
            function_call_dict[function_call.name][key] = value
        function_calls.append(function_call_dict)
    return function_calls

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

async def generate_content_async(chat):
    try:
        # Initialize Gemini API client
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        MODEL_ID = "gemini-2.0-flash-lite"

        # Use chat directly instead of parsing it again
        data = chat

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

        extracted_functions_called = extract_function_calls(response)

        if extracted_functions_called:
            return str(extracted_functions_called)

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