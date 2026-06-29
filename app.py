"""
Core AI Agent Orchestration Module (LLM Agent) for executing MES queries.
Follows the Single Responsibility Principle (SRP).
Updated: Multi-step Dynamical Operations Planning, English interfaces, Material Design 3.
"""
import warnings
import logging
import os
import threading
import datetime
from queue import Queue, Empty
import re
import ast
import csv
import uuid

from sqlalchemy import create_engine, text
from config import Config
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.tools import tool
import gradio as gr

# Suppress internal warnings
warnings.filterwarnings("ignore")
logging.getLogger("gradio").setLevel(logging.ERROR)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

# ==========================================
# 1. ENTITY STANDARDIZATION MODULE (REQUEST REWRITER)
# ==========================================
class RequestRewriter:
    """Standardizes natural language queries to minimize Information Deviation."""
    
    def __init__(self, llm):
        self.llm = llm
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        
        engine = create_engine(Config.DB_URI)
        entities = []
        metadatas = []
        
        try:
            with engine.connect() as conn:
                for row in conn.execute(text("SELECT customer_name FROM customers")).fetchall():
                    if row[0]:
                        entities.append(str(row[0]))
                        metadatas.append({"standard_name": str(row[0]), "table": "customers", "col": "customer_name"})
                        
                for row in conn.execute(text("SELECT order_name FROM orders")).fetchall():
                    if row[0]:
                        entities.append(str(row[0]))
                        metadatas.append({"standard_name": str(row[0]), "table": "orders", "col": "order_name"})
                        
                for row in conn.execute(text("SELECT description FROM products_types")).fetchall():
                    if row[0]:
                        entities.append(str(row[0]))
                        metadatas.append({"standard_name": str(row[0]), "table": "products_types", "col": "description"})
        except Exception as e:
            print(f"[WARNING] Could not load entity data from MySQL: {e}")
            
        entities.append("PolyU")
        metadatas.append({"standard_name": "Hong Kong Polytechnic University", "table": "customers", "col": "customer_name"})
        
        self.vectorstore = Chroma.from_texts(
            texts=entities if entities else ["Default Data"], 
            embedding=self.embeddings, 
            metadatas=metadatas if metadatas else [{"standard_name": "None", "table": "None", "col": "None"}], 
            collection_name="mes_entities_mysql"
        )

    def rewrite(self, user_input: str) -> str:
        docs = self.vectorstore.similarity_search(user_input, k=3)
        standard_entity_mapping = ""
        if docs:
            mapping_dict = {}
            for doc in docs:
                std_name = doc.metadata.get('standard_name')
                table = doc.metadata.get('table')
                col = doc.metadata.get('col')
                if std_name and std_name != "None":
                    # Map the found entity to its standard form
                    mapping_dict[doc.page_content] = f"<{table}.{col} = '{std_name}'>"
            
            if mapping_dict:
                mapping_str = "\n".join([f"'{k}' -> {v}" for k, v in mapping_dict.items()])
                standard_entity_mapping = mapping_str
        
        # EXACT PROMPT FROM PAPER LISTING 1
        prompt = f"""# role:
You are a professional question optimization model. You can replace entity names in questions with standard entity names.

# Standard Entity Names:
The correspondence between entity names and possible standard entity names is as follows:
{{standard_entity_mapping}}
{standard_entity_mapping}

# Output Requirements:
1. Convert entity names to the most probable standard entity names.
2. Replace the original entity names with "<entity_type = standard_entity_name>"

# Output Examples:
1. Original Question:
Orders of PolyU
Rewritten Question:
<customers.customer_name = 'Hong Kong Polytechnic University'> orders
2. Original Question:
What are the sewing tasks that use silk
Rewritten Question:
What are the sewing tasks that use <products.product_name = 'Silk'>
3. Original Question:
What does the main warehouse have
Rewritten Question:
What does <warehouse.name = 'Warehouse 1'> have
4. Original Question:
What tasks does the Advanced Sewers group have
Rewritten Question:
What tasks does <working_group.name = 'Advanced Sewers'> have

# user_question:
{user_input}

# Rewritten Question:
"""
        rewritten_query = self.llm.invoke(prompt).strip()
        return rewritten_query

# ==========================================
# 2. CUSTOM TOOLS
# ==========================================

@tool
def find_order_details(order_id: int) -> str:
    """Find the product details of an order by the order ID."""
    engine = create_engine(Config.DB_URI)
    with engine.connect() as conn:
        q = text("SELECT product_id, number FROM order_product WHERE order_id = :oid")
        res = conn.execute(q, {"oid": order_id}).fetchall()
        if res:
            return str([dict(r._mapping) for r in res])
        return f"No product details found for order ID {order_id}."

@tool
def allocate_task(order_name: str = None, order_id: int = None) -> str:
    """Automatically allocate product order tasks to workers. Use order_id or order_name."""
    engine = create_engine(Config.DB_URI)
    with engine.connect() as conn:
        if order_id is not None:
            q = text("SELECT id FROM orders WHERE id = :oid LIMIT 1")
            result = conn.execute(q, {"oid": order_id}).fetchone()
        elif order_name is not None:
            order_query = text("SELECT id FROM orders WHERE order_name = :oname LIMIT 1")
            result = conn.execute(order_query, {"oname": order_name}).fetchone()
            if not result:
                order_query = text("SELECT id FROM orders WHERE order_name LIKE :oname LIMIT 1")
                result = conn.execute(order_query, {"oname": f"%{order_name}%"}).fetchone()
        else:
            return "[SYSTEM ERROR] Missing order_id or order_name."
            
        if not result:
            return f"[SYSTEM ERROR] Order not found."
            
        oid = result[0]
        
        op_query = text("SELECT id, number FROM order_product WHERE order_id = :oid")
        op_results = conn.execute(op_query, {"oid": oid}).fetchall()
        
        if not op_results:
            return f"[WARNING] Order (ID: {oid}) currently has no products set up."
            
        now = datetime.datetime.now()
        count = 0
        for op in op_results:
            op_id, op_number = op[0], op[1]
            conn.execute(text("INSERT INTO cutting_tasks (start_time, working_group_id, order_product_id, planned_number, completed_number, status) VALUES (:st, 1, :op_id, :planned, 0, 0)"), {"st": now, "op_id": op_id, "planned": op_number})
            conn.execute(text("INSERT INTO sewing_tasks (start_time, working_group_id, order_product_id, planned_number, completed_number, status) VALUES (:st, 2, :op_id, :planned, 0, 0)"), {"st": now, "op_id": op_id, "planned": op_number})
            count += 1
        conn.commit()
    return f"Successfully allocated cutting and sewing tasks for order ID {oid}. Tasks generated: {count*2}"

@tool
def store_materials(material_id: int, number: float) -> str:
    """Automatically store materials in a free inventory."""
    engine = create_engine(Config.DB_URI)
    with engine.connect() as conn:
        q = text("UPDATE warehouse_material SET left_number = left_number + :num, total_number = total_number + :num WHERE material_id = :mid")
        res = conn.execute(q, {"num": number, "mid": material_id})
        conn.commit()
        if res.rowcount == 0:
            return f"Failed to store. Material ID {material_id} might not exist in warehouse."
    return f"Stored {number} units for material ID {material_id}."

@tool
def complete_task(task_id: int, task_type: str, quantity: int) -> str:
    """Workers reporting the completion of specific production tasks (sewing or cutting)."""
    engine = create_engine(Config.DB_URI)
    table = "cutting_tasks" if "cut" in task_type.lower() else "sewing_tasks"
    with engine.connect() as conn:
        q = text(f"UPDATE {table} SET completed_number = completed_number + :q, status = 1 WHERE id = :tid")
        res = conn.execute(q, {"q": quantity, "tid": task_id})
        conn.commit()
        if res.rowcount == 0:
            return f"Task ID {task_id} not found in {table}."
    return f"Marked task {task_id} ({task_type}) as complete with {quantity} items."

@tool
def get_busy_workers() -> str:
    """Find all working groups and their active task counts."""
    engine = create_engine(Config.DB_URI)
    with engine.connect() as conn:
        q = text("""
            SELECT wg.name, wg.type, 
                   (SELECT COUNT(*) FROM cutting_tasks ct WHERE ct.working_group_id = wg.id AND ct.status = 0) +
                   (SELECT COUNT(*) FROM sewing_tasks st WHERE st.working_group_id = wg.id AND st.status = 0) as task_count
            FROM working_group wg
        """)
        res = conn.execute(q).fetchall()
        return str([dict(r._mapping) for r in res])

# ==========================================
# 3. RESPONSE GENERATOR
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

def export_observation_to_csv(observation: str) -> tuple[str, int, str]:
    if not (isinstance(observation, str) and observation.startswith("[(") and observation.endswith(")]")):
        return "", 0, observation
        
    try:
        clean_obs = re.sub(r'datetime\.(datetime|date|time)\((.*?)\)', r'"\2"', observation)
        clean_obs = re.sub(r'Decimal\((.*?)\)', r'\1', clean_obs)
        data = ast.literal_eval(clean_obs)
        if isinstance(data, list) and len(data) > 10:
            file_name = f"data_export_{uuid.uuid4().hex[:8]}.csv"
            file_path = os.path.join(EXPORT_DIR, file_name)
            with open(file_path, "w", newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerows(data)
            
            truncated_obs = str(data[:10]) + f" ... (and {len(data)-10} other records hidden)"
            return file_path, len(data), truncated_obs
    except Exception as e:
        print("Error creating CSV:", e)
        rows = observation.split("), (")
        if len(rows) > 10:
            file_name = f"data_export_{uuid.uuid4().hex[:8]}.txt"
            file_path = os.path.join(EXPORT_DIR, file_name)
            with open(file_path, "w", encoding='utf-8') as f:
                f.write(observation)
            
            truncated_obs = "), (".join(rows[:10]) + f")] ... (and {len(rows)-10} other records hidden)"
            return file_path, len(rows), truncated_obs
            
    return "", 0, observation

class ResponseGenerator:
    def __init__(self, llm):
        self.llm = llm
        
    def generate(self, user_query: str, intermediate_steps: list, q: Queue = None) -> str:
        context = ""
        download_html = ""
        
        if not intermediate_steps:
            context = "No intermediate data retrieved."
        else:
            for i, (action, observation) in enumerate(intermediate_steps):
                tool_name = getattr(action, 'tool', 'Unknown Tool')
                tool_input = getattr(action, 'tool_input', '')
                
                obs_str = str(observation)
                if tool_name == "SQL":
                    csv_path, row_count, truncated_obs = export_observation_to_csv(obs_str)
                    if csv_path:
                        obs_str = truncated_obs
                        relative_path = os.path.relpath(csv_path, BASE_DIR).replace(os.sep, '/')
                        download_url = f"/file={relative_path}"
                        file_name = os.path.basename(csv_path)
                        download_html = f"""\n\n<a href="{download_url}" download="{file_name}" target="_blank" style="background-color: #1A73E8; color: white; padding: 8px 16px; text-decoration: none; border-radius: 8px; font-weight: 500; display: inline-block; margin-top: 10px;">📥 Download Full Data ({row_count} rows)</a>"""
                        
                context += f"Step {i+1}:\n- Action type: {tool_name}\n- Parameters: {tool_input}\n- Raw Result: {obs_str}\n\n"
                
        prompt = f"""You are the 'Responses Generator' module in the MES Agent system.
Your task is to create a complete, professional, and easily understandable final report based on the user's original request and the raw data retrieved (from the Agent).

[MANDATORY RULES]:
1. PRESENTATION STANDARDS: If the raw data is a list of records (e.g., tuples like [(4, 758, 'Emily Dress', ...)]), YOU MUST convert them into a Markdown Table with clear column headers inferred from context.
2. LANGUAGE: Formal, standard English (software engineering / business report style). DO NOT use colloquial terms.
3. NO TECHNICAL EXPLANATIONS: Absolutely do not print SQL queries or explain how the data was retrieved. The user only needs to see the final data result.
4. ERROR HANDLING: If the retrieved result is empty or there is a system error, politely respond that no matching information was found.

[USER REQUEST]:
{user_query}

[RAW SYSTEM DATA]:
{context}

[YOUR REPORT]:
"""
        if q:
            q.put(f"\n\n---\n🎯 **Final Report:**\n")
            final_ans = ""
            for chunk in self.llm.stream(prompt):
                final_ans += chunk
                q.put(chunk)
            
            if download_html:
                q.put(download_html)
                final_ans += download_html
                
            return final_ans
        else:
            final_ans = self.llm.invoke(prompt)
            if download_html:
                final_ans += download_html
            return final_ans

# ==========================================
# 4. MULTI-STEP DYNAMICAL OPERATIONS PLANNER & EXECUTOR
# ==========================================
class MESAgent:
    def __init__(self, db_uri: str):
        self.engine = create_engine(db_uri)
        self.llm = OllamaLLM(model="llama3", temperature=0.0)
        self.tools = {
            "find_order_details": find_order_details,
            "allocate_task": allocate_task,
            "store_materials": store_materials,
            "complete_task": complete_task,
            "get_busy_workers": get_busy_workers
        }
        self.schema = self._get_schema()

    def _get_schema(self) -> str:
        try:
            with self.engine.connect() as conn:
                tables_res = conn.execute(text("SHOW TABLES")).fetchall()
                schema_str = ""
                for t in tables_res:
                    table_name = t[0]
                    schema_str += f"-- {table_name} Table\nCREATE TABLE `{table_name}` (\n"
                    cols = conn.execute(text(f"DESCRIBE {table_name}")).fetchall()
                    for c in cols:
                        schema_str += f"  `{c[0]}` {c[1]},\n"
                    schema_str += ");\n"
                return schema_str
        except Exception:
            return "Error reading schema."

    def run(self, query: str, q: Queue = None, callbacks=None, eval_mode=False) -> str:
        # 1. Planning Phase - EXACT PROMPT FROM PAPER LISTING 2
        prompt = f"""You are Chat With MES, a powerful AI assistant, a variant of ChatGPT that can
1) decide to invoke some provided tools to solve the query.
2) utilize the database of the Manufacturing Execution System as external symbolic memory.
For any user query, you should always prioritize using the given tools to complete it.
The following are the tools you can use, including their names, descriptions, and input args.
\"\"\"
tool_find_order_details: Find the product details of an order by the order ID.
{{ 'order_id': {{'type': 'integer'}} }}

tool_allocate_task: Automatically allocate product order tasks to workers.
{{ 'order_id': {{'type': 'integer'}}, 'order_name': {{'type': 'string'}} }}

tool_store_materials: Automatically store materials in a free inventory.
{{ 'material_id': {{'type': 'integer'}}, 'number': {{'type': 'number'}} }}

tool_complete_task: Workers reporting the completion of specific production tasks.
{{ 'task_id': {{'type': 'integer'}}, 'task_type': {{'type': 'string'}}, 'quantity': {{'type': 'integer'}} }}

tool_get_busy_workers: Find all working groups and their task counts.
{{}}
\"\"\"
Only if you cannot handle the command/query with any given tools, You are authorized to directly access the database.
In this case, you are an expert in databases, proficient in SQL statements and can use the database to help users. The details of tables in the database are delimited by triple quotes.
\"\"\"
{self.schema}
\"\"\"
Please tell me what basic operations, including sql, tool,and thought, should I use in order to respond to the "USER INPUT". If it needs multiple operations, please list them step by step concisely, and indicate whether the operation involves calling a tool or accessing a database via SQL. If there is no need to use any operations, reply to the "USER INPUT" directly.
At all times, you should prioritize using the provided tool. If the tool does not meet the requirements, only then may you resort to using SQL.
The output should be a markdown code snippet formatted in the following schema, including the leading and trailing "```" and "```":
```
Step1: <Description of first step>
SQL `SQL command for step1`

Step2: <Description of first step>
SQL `SQL command for step2`

Step3: <Description of second step>
Tool `Tool name, arguments for tool, purpose of using this tool`

Step4: <Description of fourth step>
Thought `Purpose of this intermediate reasoning step, what intermediate results are expected. and how to get them based on the results from the previous steps.`
```

Backticks are important and must be added at the beginning and end of the command for every step!

Here are some examples:

USER INPUT: Retrieve all orders and item details for the Customer PolyU
ANSWER:
```
Step1: Retrieve the customer ID for the customer with the name "PolyU"
Execute:
SQL `SELECT id FROM customers WHERE customer_name = 'PolyU';`

Step2: Retrieve the details of products for each order, including product attributes and type description
Tool `tool_find_order_details, {{'order_id': <order_id>}}, Find the product details of an order`
```

USER INPUT: {query}
ANSWER:
"""
        
        if q:
            q.put(f"\n\n> 🧠 **Planning Operations...**\n")
            
        plan_str = self.llm.invoke(prompt)
        
        if q:
            q.put(f"> ✅ **Plan Generated:**\n> {plan_str.replace(chr(10), chr(10)+'> ')}\n")

        # 2. Parsing Phase
        steps = []
        for line in plan_str.split('\n'):
            line = line.strip()
            if line.startswith('SQL `') or line.startswith('Tool `') or line.startswith('Thought `') or line.startswith('Execute:'):
                if line.startswith('Execute:'):
                    continue
                op_type = line.split(' ')[0]
                cmd = line[len(op_type)+2:-1]
                steps.append({'type': op_type, 'command': cmd})

        # 3. Execution Phase
        intermediate_steps = []
        context = []
        
        for i, step in enumerate(steps):
            op_type = step['type'].upper()
            cmd = step['command']
            obs = ""
            
            # EXACT PROMPT FROM PAPER LISTING 3
            if "<" in cmd and ">" in cmd and context:
                if q:
                    q.put(f"\n> 🔍 **Identifying Parameters for Step {i+1}...**\n")
                
                param_prompt = f"""You are now the following python function:
# "Find useful information in the results of the previous operating statement, and replace <> with the corresponding information. "
"If the operation type is 'Tool' and the tool must be invoked multiple times with varying parameters, "
"please output a list of tool operations with distinct parameters."

def populate_operation_statement(operation_str: str, previous_operation_results: list[list[dict]]) -> list[str]:
Only respond with your `return` value. Do not include any other explanatory text in your response.",

# Operation
{cmd}

# Historical Context
{chr(10).join(context)}
"""
                resolved_cmd = self.llm.invoke(param_prompt).strip()
                if resolved_cmd.startswith("['"):
                    try:
                        resolved_cmd = ast.literal_eval(resolved_cmd)[0]
                    except:
                        pass
                cmd = resolved_cmd
            
            if q:
                q.put(f"\n\n> 🛠️ **Executing Step {i+1} ({op_type}):**\n> *Command:* {cmd}\n")
            
            try:
                if op_type == 'SQL':
                    with self.engine.connect() as conn:
                        res = conn.execute(text(cmd)).fetchall()
                        obs = str(res)
                elif op_type == 'TOOL':
                    parts = cmd.split(',', 1)
                    t_name = parts[0].strip().replace('tool_', '')
                    
                    if t_name in self.tools:
                        arg_str = parts[1].strip() if len(parts) > 1 else ""
                        try:
                            # Parse kwargs
                            kwargs = ast.literal_eval(arg_str.split('},')[0] + '}')
                            obs = self.tools[t_name].invoke(kwargs)
                        except:
                            # Fallback mapping
                            obs = self.tools[t_name].invoke({"order_name": arg_str})
                    else:
                        obs = f"Tool {t_name} not found."
                        
                elif op_type == 'THOUGHT':
                    thought_prompt = f"Context from previous steps:\n{chr(10).join(context)}\n\nPlease process this thought: {cmd}"
                    obs = self.llm.invoke(thought_prompt)
                    
            except Exception as e:
                obs = f"Error executing {op_type}: {str(e)}"
                
            if q:
                q.put(f"\n> ✅ **Result:**\n> {obs[:500]}{'...' if len(obs)>500 else ''}\n")
                
            context.append(f"Step {i+1} ({op_type}) Result: {obs}")
            action_mock = type('Action', (), {'tool': op_type, 'tool_input': cmd})
            intermediate_steps.append((action_mock, obs))

        # 4. Response Generation
        generator = ResponseGenerator(self.llm)
        final_response = generator.generate(query, intermediate_steps, q)
        
        if eval_mode:
            return final_response, intermediate_steps
        return final_response

# ==========================================
# 5. USER INTERFACE (GRADIO WEB UI)
# ==========================================
global_rewriter = None
global_agent = None

def init_mes_system():
    global global_rewriter, global_agent
    if global_agent is None:
        global_agent = MESAgent(Config.DB_URI)
    if global_rewriter is None:
        global_rewriter = RequestRewriter(global_agent.llm)

def process_chat(message, history):
    init_mes_system()
    
    q = Queue()
    refined_query = global_rewriter.rewrite(message)
    
    def run_agent():
        try:
            global_agent.run(refined_query, q=q)
        except Exception as e:
            q.put(f"\n\n❌ **System Error:** {str(e)}")
        finally:
            q.put(None)
            
    thread = threading.Thread(target=run_agent)
    thread.start()
    
    output_text = ""
    while True:
        try:
            chunk = q.get(timeout=0.1)
            if chunk is None:
                break
            output_text += chunk
            yield output_text
        except Empty:
            continue

if __name__ == "__main__":
    material_theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="indigo",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("Roboto"), "sans-serif"]
    ).set(
        button_primary_background_fill="*primary_500",
        button_primary_background_fill_hover="*primary_600",
        block_title_text_weight="500",
        block_label_text_weight="500"
    )

    material_css = """
    body { background-color: #F4F7FB; font-family: 'Roboto', sans-serif; }
    .gradio-container { border-radius: 24px !important; box-shadow: 0px 8px 24px rgba(0,0,0,0.05) !important; background: #FFFFFF !important; padding: 24px !important; }
    .message { border-radius: 16px !important; padding: 16px !important; font-size: 15px !important; }
    .user { background-color: #D3E3FD !important; color: #041E49 !important; }
    .bot { background-color: #F8F9FA !important; color: #1F1F1F !important; box-shadow: 0px 2px 6px rgba(0,0,0,0.04) !important; border: 1px solid #E9ECEF !important; }
    textarea { background-color: #FFFFFF !important; border: 2px solid #1A73E8 !important; color: #202124 !important; border-radius: 12px !important; box-shadow: 0px 4px 12px rgba(26,115,232,0.1) !important; }
    """

    with gr.Blocks(theme=material_theme, css=material_css, title="MES Agent Assistant") as demo:
        gr.Markdown("<h1 style='text-align: center; color: #1A73E8; font-weight: 500;'>MES Agent Assistant</h1>")
        gr.Markdown(
            "<div style='text-align: center; color: #5F6368;'>"
            "<strong>Natural Language Interaction System for Manufacturing Execution System (MES)</strong><br>"
            "Designed based on the LLM-driven User Interface architecture. Please enter your request.<br>"
            "<em>The system supports real-time Streaming Thought Process and execution planning.</em></div>"
        )
        
        gr.ChatInterface(fn=process_chat, autoscroll=True)
    
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, allowed_paths=[EXPORT_DIR])