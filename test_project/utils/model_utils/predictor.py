import numpy as np

try:
    import tensorflow as tf
    _HAS_TF = True
except ImportError:
    _HAS_TF = False
    print("! TensorFlow not found. Using mock for testing logic.")
    
    # Mocking a minimal TF subset for demonstration
    class MockTensor:
        def __init__(self, data):
            self._data = np.array(data)
            self.shape = self._data.shape
        def numpy(self):
            return self._data
        def __mul__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data * val)
        def __add__(self, other):
            val = other._data if isinstance(other, MockTensor) else other
            return MockTensor(self._data + val)

    class MockTF:
        float32 = "float32"
        def constant(self, data, dtype=None):
            return MockTensor(data)
            
    tf = MockTF()

def run_prediction(input_data):
    print("\n--- Running Model Predictor (TensorFlow) ---")
    try:
        # Convert list to tensor
        input_tensor = tf.constant(input_data, dtype=tf.float32)
        
        # Simple "model" operation: y = x * 2 + 1
        weights = tf.constant(2.0, dtype=tf.float32)
        bias = tf.constant(1.0, dtype=tf.float32)
        
        # Note: In real TF, we'd use tf.math operations, but operators are overloaded
        output = input_tensor * weights + bias  # This works for both real TF and our Mock
        
        print(f"Input tensor shape: {input_tensor.shape}")
        
        # .numpy() is consistent for both
        result_data = output.numpy()
        print("Output tensor sample (first 5):", result_data[:5])
        
        return result_data
    except Exception as e:
        print(f"Error running TensorFlow operation: {e}")
        return []
