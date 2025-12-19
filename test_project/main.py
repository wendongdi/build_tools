import sys
import os

# Add current directory to path so imports work if run from here
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_processor.processor import process_data
from model_utils.predictor import run_prediction

def main():
    print("Starting Test Obfuscation Project...")
    
    # Step 1: Process Data
    processed_sums = process_data(data_size=20)
    
    # Step 2: Run Prediction
    predictions = run_prediction(processed_sums)
    
    print("\n--- Final Results ---")
    print(f"Total predictions generated: {len(predictions)}")
    print("Project run complete.")

if __name__ == "__main__":
    main()

