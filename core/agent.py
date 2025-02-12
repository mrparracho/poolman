import logging
import sys
from actions.index import get_available_actions
from typing import Optional
from core.parser import IntentParser

# Configure logging with a formatter
logging.basicConfig(
    filename="logs/agent.log",
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)

# Add console handler for immediate feedback
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logging.getLogger().addHandler(console_handler)

class Agent:
    def __init__(self):
        # Initialize all actions from the index
        self.actions = get_available_actions()
        self.parser = IntentParser(list(self.actions.values()))
        logging.info("Agent initialized with %d actions", len(self.actions))

    def get_help(self, topic: Optional[str] = None) -> str:
        """Generate help message for all actions or a specific action"""
        if topic and topic in self.actions:
            action = self.actions[topic]
            help_text = [
                f"Help for: {action.intent_name}",
                f"\nDescription:",
                f"{action.description}",
                f"\nParameters:",
            ]
            for param, desc in action.parameters.items():
                help_text.append(f"- {param}: {desc}")
            help_text.append("\nExamples:")
            for example in action.examples:
                help_text.append(f"- {example.command}")
            return "\n".join(help_text)
        
        # General help
        help_text = ["Available commands:"]
        for action in self.actions.values():
            help_text.extend([
                f"\n{action.intent_name}:",
                f"  {action.description}",
                "  Examples:",
                f"  - {action.examples[0].command}"
            ])
        help_text.append("\nFor detailed help on a specific command, type 'help <command>'")
        return "\n".join(help_text)

    def handle_input(self, user_input: str) -> str:
        """Process user input and return response"""
        try:
            # Log the incoming command
            logging.info("Processing command: %s", user_input)
            
            # Check for help command first
            if user_input.lower().startswith('help'):
                topic = user_input[4:].strip()  # Remove 'help' and whitespace
                return self.get_help(topic if topic else None)
            
            # Parse the intent
            intent, params = self.parser.parse_intent(user_input)
            
            # Handle help intent from parser
            if intent == "help":
                return self.get_help(params.get("topic"))
            
            if intent not in self.actions:
                return f"Sorry, I don't know how to handle that command.\nType 'help' to see available commands."
            
            # Execute the action
            result = self.actions[intent].run(**params)
            logging.info("Command executed successfully: %s", result)
            return result
            
        except Exception as e:
            logging.error("Error processing command: %s", str(e))
            return "Sorry, I couldn't understand that command. Type 'help' to see examples."

def main():
    """Main entry point with proper signal handling"""
    print("Welcome to PoolMan! Type 'exit' or 'quit' to end the session.")
    print("\nAvailable commands:")
    print("- Create a pool: create a new pool for ETH/USDC using wallet 0x123")
    print("\nNote: Replace ETH/USDC with your desired trading pair and 0x123 with your wallet address.")
    
    agent = Agent()
    
    while True:
        try:
            command = input("\nEnter command: ").strip()
            
            if not command:  # Skip empty commands
                continue
                
            if command.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break
                
            response = agent.handle_input(command)
            print(f"\n{response}")
            
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        except Exception as e:
            logging.error("Unexpected error: %s", str(e))
            print("\nAn unexpected error occurred. Please try again.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error("Fatal error: %s", str(e))
        sys.exit(1)
