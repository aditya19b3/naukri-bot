"""
main_linkedin.py
----------------
Entry point adapter for the LinkedIn Auto-Apply Bot.
This script is spawned as a subprocess by the unified backend.
It sets up the correct working directory and sys.path so that
the LinkedIn bot's internal imports (config.*, modules.*) resolve correctly.
"""

import os
import sys

def main():
    # Change working directory to the linkedin/ package directory
    # so all relative imports and file paths in runAiBot.py work correctly
    linkedin_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(linkedin_dir)
    
    # Add linkedin dir to the front of sys.path so 'config.*' and 'modules.*' 
    # imports resolve to linkedin/config/ and linkedin/modules/
    if linkedin_dir not in sys.path:
        sys.path.insert(0, linkedin_dir)
    
    # Now import and run the LinkedIn bot
    from runAiBot import main as run_linkedin_bot
    run_linkedin_bot()

if __name__ == "__main__":
    main()
