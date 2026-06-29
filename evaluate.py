import os
import json
import glob
import csv
import re
from config import Config
from app import MESAgent
from langchain_ollama import OllamaLLM

# Sử dụng model do user cấu hình (llama3)
JUDGE_MODEL = "llama3"

def load_dataset():
    dataset_dir = os.path.join(os.path.dirname(__file__), "paper", "CWM_repo", "questions", "q0702")
    questions = []
    for filepath in glob.glob(os.path.join(dataset_dir, "*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            questions.append({
                "id": data.get("ID"),
                "q_en": data.get("q_en"),
                "q_ch": data.get("q_ch"),
                "gt": data.get("gt")
            })
    # Sắp xếp theo ID
    questions.sort(key=lambda x: x["id"] if isinstance(x["id"], int) else 999)
    return questions

def evaluate_with_llm(llm: OllamaLLM, question: str, ground_truth: str, generated_actions: list, final_answer: str) -> dict:
    prompt = f"""You are an expert SQL and logic evaluator for a smart manufacturing execution system (MES).
Your task is to determine if an AI Agent correctly solved a user request.

[User Request]: {question}
[Ground Truth Action/SQL]: {ground_truth}
[Agent's Generated Actions]: {generated_actions}
[Agent's Final Answer]: {final_answer}

EVALUATION CRITERIA:
1. If the Agent's Generated Actions contain a SQL query or Tool call that achieves the exact same logical result as the Ground Truth, it is a PASS.
2. If the Agent's Final Answer correctly addresses the user request based on the Ground Truth logic, it is a PASS.
3. Otherwise, it is a FAIL.

Output ONLY a JSON object in the following format, nothing else:
{{"pass": true, "reason": "brief explanation"}} or {{"pass": false, "reason": "brief explanation"}}
"""
    try:
        response = llm.invoke(prompt)
        # Tìm đoạn JSON trong câu trả lời
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            return {"pass": result.get("pass", False), "reason": result.get("reason", "No reason provided")}
        else:
            return {"pass": False, "reason": "Judge did not return JSON format. Raw output: " + response}
    except Exception as e:
        return {"pass": False, "reason": f"Evaluation error: {str(e)}"}

def main():
    print("🚀 Starting the Evaluation Pipeline...")
    questions = load_dataset()
    print(f"📦 Loaded {len(questions)} questions from Benchmark Dataset.")
    
    # Khởi tạo Agent và Judge
    agent = MESAgent(db_uri=Config.DB_URI)
    judge_llm = OllamaLLM(model=JUDGE_MODEL, temperature=0.0)
    
    results = []
    passed = 0
    
    export_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(export_dir, exist_ok=True)
    csv_path = os.path.join(export_dir, "evaluation_results.csv")
    
    # Mở file CSV để ghi trực tiếp trong lúc chạy (phòng trường hợp lỗi giữa chừng)
    with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Question", "Ground Truth", "Agent Actions", "Final Answer", "Pass", "Reason"])
        
        for q in questions:
            print(f"\n--- Processing Question {q['id']} ---")
            print(f"Q: {q['q_en']}")
            try:
                # Chạy Agent với eval_mode=True để lấy intermediate_steps
                final_response, intermediate_steps = agent.run(q['q_en'], eval_mode=True)
                
                # Trích xuất các action/SQL mà Agent đã sinh ra
                generated_actions = []
                for action, _ in intermediate_steps:
                    tool_name = getattr(action, 'tool', 'Unknown Tool')
                    tool_input = getattr(action, 'tool_input', '')
                    generated_actions.append(f"[{tool_name}]: {tool_input}")
                
                # Chấm điểm bằng LLM Judge
                eval_result = evaluate_with_llm(judge_llm, q['q_en'], q['gt'], generated_actions, final_response)
                
                is_pass = eval_result["pass"]
                reason = eval_result["reason"]
                if is_pass:
                    passed += 1
                    print(f"✅ PASS: {reason}")
                else:
                    print(f"❌ FAIL: {reason}")
                
                writer.writerow([q['id'], q['q_en'], q['gt'], " | ".join(generated_actions), final_response, is_pass, reason])
                f.flush()
                
            except Exception as e:
                print(f"⚠️ ERROR RUNNING QUESTION {q['id']}: {e}")
                writer.writerow([q['id'], q['q_en'], q['gt'], "ERROR", str(e), False, "Execution Error"])
                f.flush()

    total = len(questions)
    accuracy = (passed / total) * 100 if total > 0 else 0
    print("\n" + "="*40)
    print("📊 EVALUATION RESULTS REPORT")
    print(f"Total questions: {total}")
    print(f"PASS count: {passed}")
    print(f"FAIL count: {total - passed}")
    print(f"Accuracy: {accuracy:.2f}%")
    print(f"Details saved at: {csv_path}")
    print("="*40)

if __name__ == "__main__":
    main()
