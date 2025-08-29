from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "microsoft/phi-2"
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

model.save_pretrained("./phi-2")
tokenizer.save_pretrained("./phi-2")
print("Phi-2 model and tokenizer downloaded to ./phi-2")