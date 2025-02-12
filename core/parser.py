from openai import OpenAI
import os
import json
import re
import logging
from typing import List, Tuple, Dict, Any
from actions.base import BaseAction

# Configure logging
logging.getLogger('openai').setLevel(logging.DEBUG)

class IntentParser:
    def __init__(self, actions: List[BaseAction]):
        self.actions = actions
        
        # Initialize the OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        self.client = OpenAI(api_key=api_key)
        self.prompt_template = self._build_prompt_template()
        logging.debug("Parser initialized with API key length: %d", len(api_key))
    
    def _build_prompt_template(self) -> str:
        # Build intent documentation from registered actions
        intent_docs = []
        examples = []
        
        for action in self.actions:
            # Add intent and its parameters
            params_doc = [
                f"- {param_name}: {description}"
                for param_name, description in action.parameters.items()
            ]
            intent_docs.append(
                f"{action.intent_name}:\n"
                f"Parameters:\n"
                + "\n".join(params_doc)
            )
            
            # Add examples
            for example in action.examples:
                examples.append(
                    f'Input: "{example.command}"\n'
                    f'Output: {{"intent": "{example.intent}", "params": {json.dumps(example.params)}}}'
                )
        
        # Join all documentation parts
        intent_docs_str = "\n\n".join(intent_docs)
        examples_str = "\n\n".join(examples)
        
        # Build the template with a placeholder for the command
        template = """Parse this command into intent and parameters: %(command)s

Available intents and parameters:
{}

Examples:
{}

Return ONLY a JSON object like this: {{"intent": "intent_name", "params": {{"param1": "value1"}}}}""".format(
            intent_docs_str,
            examples_str
        )
        
        return template
    
    def parse_intent(self, command: str) -> Tuple[str, Dict[str, Any]]:
        """Parse the user command to extract intent and parameters."""
        response_text = None
        try:
            # Log the command being processed
            logging.debug("Processing command: %s", command)
            
            # Format the prompt
            prompt = self.prompt_template % {"command": command}
            print("=== Formatted Prompt ===")
            print(prompt)
            print("======================")
            
            # Get response from OpenAI
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a command parser that returns only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0
                )
                logging.debug("\n=== Raw LLM Response ===")
                logging.debug(response)
                logging.debug("======================\n")
            except Exception as e:
                logging.error("OpenAI API error: %s", str(e))
                return "help", {}
            
            if not response or not response.choices:
                logging.error("No response received from OpenAI")
                return "help", {}
                
            response_text = response.choices[0].message.content
            if not response_text:
                logging.error("Empty response text from OpenAI")
                return "help", {}
                
            logging.debug("\n=== Response Content ===")
            logging.debug(response_text)
            logging.debug("=====================\n")
            
            # Clean up the response text
            response_text = response_text.strip()
            if response_text.startswith('```') and response_text.endswith('```'):
                response_text = response_text[3:-3].strip()
            if response_text.startswith('json'):
                response_text = response_text[4:].strip()
            logging.debug("Cleaned response text: %s", response_text)
            
            try:
                # Parse JSON directly first
                parsed_response = json.loads(response_text)
            except json.JSONDecodeError:
                # If direct parsing fails, try to extract JSON
                json_str = extract_json_from_response(response_text)
                logging.debug("Extracted JSON: %s", json_str)
                try:
                    parsed_response = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logging.error("Failed to parse JSON after extraction: %s", str(e))
                    return "help", {}
            
            logging.debug("Parsed response: %s", parsed_response)
            
            # Validate response structure
            if not isinstance(parsed_response, dict):
                logging.warning("Response is not a dictionary: %s", parsed_response)
                return "help", {}
            if "intent" not in parsed_response or "params" not in parsed_response:
                logging.warning("Response missing required fields: %s", parsed_response)
                return "help", {}
            if not isinstance(parsed_response["params"], dict):
                logging.warning("Parameters is not a dictionary: %s", parsed_response)
                return "help", {}
                
            return parsed_response["intent"], parsed_response["params"]
            
        except Exception as e:
            logging.error("Parser error: %s", str(e))
            logging.debug("Raw response: %s", response_text)
            return "help", {}

def extract_json_from_response(text: str) -> str:
    """Extract JSON object from text, handling potential extra text around it."""
    try:
        # Try to find JSON-like structure with regex
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
        if json_match:
            return json_match.group(0)
        return text
    except Exception as e:
        logging.error("Error extracting JSON: %s", str(e))
        return text
