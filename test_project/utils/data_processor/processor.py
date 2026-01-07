import pandas as pd
import numpy as np

def process_data(data_size=10):
    print("--- Running Data Processor ---")
    # Generate random data
    data = np.random.randn(data_size, 4)
    df = pd.DataFrame(data, columns=['A', 'B', 'C', 'D'])
    
    # Simple operations
    df['Sum'] = df.sum(axis=1)
    df['Mean'] = df.mean(axis=1)
    
    print(f"Generated DataFrame with shape: {df.shape}")
    print("First 3 rows:")
    print(df.head(3))
    
    return df['Sum'].tolist()
