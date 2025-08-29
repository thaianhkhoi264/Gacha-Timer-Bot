from optimum.exporters.onnx import main_export
import sys

# Export the model for text-generation
sys.argv = [
    "optimum.exporters.onnx",
    "--model", "./phi-2",
    "--task", "text-generation",
    "--output", "./phi-2-onnx"
]
main_export()
print("Phi-2 exported to ONNX at ./phi-2-onnx")