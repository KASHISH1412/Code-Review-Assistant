import os
import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from dotenv import load_dotenv

# --- Pre-computation and Configuration ---

# Load environment variables from a .env file for security
load_dotenv()

# Configure the Google Gemini API using the key from the environment
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    if not GEMINI_API_KEY:
        raise KeyError
    genai.configure(api_key=GEMINI_API_KEY)
    # Initialize the specific model we want to use
    model = genai.GenerativeModel('gemini-1.0-pro')
except KeyError:
    print("FATAL ERROR: GEMINI_API_KEY environment variable not set or is empty.")
    # Set model to None to indicate a configuration failure
    model = None

# --- FastAPI Application Setup ---

# Initialize the FastAPI application with metadata
app = FastAPI(
    title="AI Code Review Assistant",
    description="An API that uses a Large Language Model to review source code files.",
    version="1.0.0",
)

# Configure CORS (Cross-Origin Resource Sharing) middleware
# This is essential for allowing the frontend (index.html) to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for simplicity (in production, restrict this)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# --- Prompt Engineering: The Core of the AI Interaction ---

def create_review_prompt(code: str, filename: str) => str:
    """
    Engineers a detailed, structured prompt to guide the LLM's response.

    This is the most critical function for ensuring high-quality, parsable output.
    By specifying the persona, context, instructions, and a strict JSON output format,
    we significantly increase the reliability of the AI's response.

    Args:
        code: The source code content as a string.
        filename: The name of the file being reviewed.

    Returns:
        A formatted prompt string to be sent to the LLM.
    """
    return f"""
    You are an expert code reviewer named "CodeSage". Your task is to provide a detailed, constructive, and actionable review for the provided code.

    **Context:**
    - **File Name:** `{filename}`

    **Instructions:**
    Analyze the following code based on these five criteria:
    1.  **Readability**: Is the code clean, well-commented, and easy to understand? Is the naming convention clear?
    2.  **Modularity_Structure**: Is the code well-organized into functions or classes? Is there good separation of concerns?
    3.  **Potential_Bugs**: Are there any logical errors, unhandled edge cases, or common programming mistakes?
    4.  **Best_Practices**: Does the code adhere to standard conventions and idiomatic principles for its language?
    5.  **Security**: Are there any obvious security vulnerabilities (e.g., hardcoded secrets, injection risks, unsafe functions)?

    **Output Format:**
    Your entire response MUST be a single, minified JSON object. Do not include any markdown formatting (like ```json), explanations, or conversational text outside of the JSON structure.

    The root object must have keys for each of the five criteria (use underscores, e.g., "Potential_Bugs"). For each criterion, the value should be an object containing:
    - "rating": An integer rating from 1 (poor) to 10 (excellent).
    - "comment": A concise string (2-3 sentences) with detailed feedback. If you find issues, reference line numbers where applicable.

    **Code to Review:**
    ```
    {code}
    ```
    """

# --- API Endpoint Definition ---

@app.post("/review")
async def review_code_endpoint(file: UploadFile = File(...)):
    """
    API endpoint to receive a code file, process it with the LLM, and return a review.

    This function handles the web request, file processing, AI interaction, and error handling.
    """
    # 1. Configuration Check
    if not model:
        raise HTTPException(
            status_code=503,  # Service Unavailable
            detail="LLM service is not configured. The server is missing the GEMINI_API_KEY."
        )

    try:
        # 2. Read and Decode File Content
        # Asynchronously read the file to prevent blocking, and decode it as UTF-8
        code_content = (await file.read()).decode("utf-8")
        if not code_content.strip():
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        # 3. Generate the Prompt
        prompt = create_review_prompt(code_content, file.filename)

        # 4. Interact with the LLM
        response = model.generate_content(prompt)
        
        # 5. Clean and Parse the LLM's Response
        # The raw response might have markdown artifacts. We must clean it before parsing.
        cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        
        review_data = json.loads(cleaned_response_text)
        
        # 6. Return the successfully parsed data as a JSON response
        return JSONResponse(content=review_data)

    except json.JSONDecodeError:
        # This error occurs if the LLM's response is not valid JSON.
        raise HTTPException(
            status_code=500, # Internal Server Error
            detail="Failed to parse the AI model's response. The model returned an invalid format."
        )
    except Exception as e:
        # Catch-all for any other unexpected errors during the process.
        print(f"An unexpected error occurred: {e}") # Log the error for debugging
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
