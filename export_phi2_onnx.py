from optimum.exporters.onnx import main_export

# Export the model for text-generation
main_export(
    model_name_or_path="./phi-2",
    output="./phi-2-onnx",
    task="text-generation"
)
print("Phi-2 exported to ONNX at ./phi-2-onnx")