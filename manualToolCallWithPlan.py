from openai import OpenAI
import requests
import json
import os
import subprocess
import sys

MEMORY="memory.json"
API_KEY="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"


client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

FREE_MODEL="llama-3.3-70b-versatile"

tools=[
    {
    "type": "function",
    "function": {
      "name": "wiki_search",
      "description": "Search Wikipedia and return summarized results.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Search query"
          }
        },
        "required": ["query"]
      }
    }
  },
    {
    "type": "function",
    "function": {
      "name": "get_note",
      "description": "gets the notes saved in memory to give to user.",
      "parameters": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The label or name for the information (e.g., 'exam_date')"
            },
        },
        "required": ["key"]
    }
    }
    },
    {
    "type": "function",
    "function": {
    "name":"save_note",
    "description": "Save a piece of information in memory using a key and value.",
    "parameters": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The label or name for the information (e.g., 'exam_date')"
            },
            "value": {
                "type": "string",
                "description": "The information to store (e.g., '10th April')"
            }
        },
        "required": ["key", "value"]
    }
    }
    },
    {
        "type":"function",
        "function":{
            "name":"calculate",
            "description":"calculates  maths expressions involving +,-,*,/.Returns the evaluation of that expression",
            "parameters":{
                "type":"object",
                "properties":{
                    "expression":{"type":"string","description":"Maths expression such as 3+5*2"} 
                },
                "required":["expression"]
            }
        }
    }

]


def wiki_search(query):
    try:
        res=requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ','_')}",
                        timeout=10,
                        headers={"User-Agent": "agent/1.0"}
                        )    
        if res.status_code==200:
            data=res.json()
            return json.dumps({
                "query":query,
                "summary":data.get("extract","No summary found.")[:800] 
            })
        return json.dumps({"error":f"Page Not found for query {query}.Try different term"})
    except Exception as e:
        return json.dumps({"error":str(e)})

def calculate(expression):
    try:
        allowed = set("0123456789+-*/.() eE")
        if not all(c in allowed for c in expression):
            return json.dumps({"error":f"Invalid characters in {expression}"})
        result=eval(expression)
        return json.dumps({"expression":expression,"result":round(result,6)})
    except Exception as e:
        return json.dumps({"error":str(e)})
    
def save_memory(mem):
    if os.path.exists(MEMORY):
        with open(MEMORY,"w") as f:
            f.write(json.dumps(mem))

def load_memory():
    try:
        if os.path.exists(MEMORY):
            with open(MEMORY,"r") as f:
                return json.load(f)  
    except:
        return {}

def save_note(key:str,value:str):
    key=str(key)
    value=str(value)
    if not key.strip():
        return json.dumps({"error": "Key cannot be empty"})
    
    if value.lower() in ["", "empty", "none"]:
        return json.dumps({"error": "Value is not meaningful ,ask user for value again"})

    mem=load_memory()
    mem[key]=value
    save_memory(mem)
    return json.dumps({"status":"saved"})

def normalize(s):
    return s.lower().replace("_", "").replace(" ", "")

def get_note(key: str):
    mem = load_memory()

    norm_key = normalize(key)

    # exact match first
    for k in mem:
        if normalize(k) == norm_key:
            return json.dumps({"value": mem[k]})

    # partial match
    for k in mem:
        if norm_key in normalize(k) or normalize(k) in norm_key:
            return json.dumps({"value": mem[k]})

    return json.dumps({"value": "Not Found"})

REACT_SYSTEM_PROMPT = """You are a helpful assistant that solves problems step by step using tools.
You first plan every tool_calls that you need to make before calling any tool and then follow the steps of plan to get desired result.Name plan steps as step1, step2, step3... in the plans object.
You have access to these tools:
{tool_descriptions}

## Output Format (STRICT JSON ONLY)

Always respond in valid JSON.

If you want to plan:
{{
"plans":{{...}},
"why":"your reasoning"
}}

If you want to use a tool:
{{
  "thought": "your reasoning",
  "action": "tool_name",
  "action_input": {{ ... }}
}}

If you want to give final answer:
{{
  "thought": "your reasoning",
  "final_answer": "your complete answer"
}}

## Rules
- Always return valid JSON
- Use only ONE action per turn
- No extra text outside JSON
- Use tools ONLY when they help you get information you do not already have
- You MAY use multiple tools if required
- Do NOT use tools for simple reasoning or general knowledge
- If a question involves stored memory or calculation, use the appropriate tool
- - If the user's request is missing required information (like a value for save_note), do NOT invent or guess the value. Instead, return a final_answer asking the user to provide the missing information.

"""
REQUIRED_FIELDS={}
for tool in tools:
    REQUIRED_FIELDS[tool["function"]["name"]]=tool["function"]["parameters"]["required"]

FXN={
    "calculate":calculate,
    "save_note":save_note,
    "get_note":get_note,
    "wiki_search":wiki_search
}

tools_map = {
    tool["function"]["name"]: tool["function"]
    for tool in tools
}

def run_agent(user_query,verbose=True,max_iterations=10):
    tool_desc = "\n".join(
    f"- {t['function']['name']}: {t['function']['description']}"
    for t in tools
    )
    system = REACT_SYSTEM_PROMPT.format(tool_descriptions=tool_desc)
    conversation=[
        {"role":"system","content":system},
        {"role":"user","content":user_query}
    ]
    checked_plans=False
    for i in range(max_iterations):
        res=client.chat.completions.create(
            model=FREE_MODEL,
            temperature=0.0,
            max_tokens=500,
            messages=conversation
        )
        msg=res.choices[0].message
        conversation.append({"role":"assistant","content":msg.content})
        try:
            parsed=json.loads(msg.content)
        except json.JSONDecodeError:
            conversation.append({"role":"user","content":"Your response was not in valid json format.Please strictly follow json format."})
            if(verbose==True):
                print("⚠️ Invalid JSON — retrying...")
                print(f"No. of tries= {i+1}")
            continue    

        if "plans" in parsed and "why" in parsed:   # ✅ Fix Bug 1
            plans = parsed["plans"]
            for step in plans:
                print(f"{step}= {plans[step]}")
            print(f"Reason: {parsed.get('why', '')}")
            checked_plans = True
            # ✅ Fix Bug 2 — tell the model to now execute the plan
            conversation.append({
                "role": "user",
                "content": "Good plan. Now execute it step by step using the tools."
            })
            continue
        elif checked_plans != True:
            conversation.append({"role":"user","content":"Please first send plans and why before doing anything else."})
            continue
        
        thought=parsed.get("thought","")
        if verbose and thought:
            print("Thought= "+ thought)

        if "final_answer" in parsed:
            result=parsed["final_answer"]
            print(f"The Final Output=\n {result}")
            if verbose:
                print(f"No. of tries= {i+1}")
            break       

        func_name=parsed.get("action", "")
        args=parsed.get("action_input","")

        if func_name not in FXN:
            conversation.append({"role":"user","content":f"Unknown tool: {func_name}"})
            if(verbose==True):
                print("⚠️ Function not given — retrying...")
                print(f"No. of tries= {i+1}")
            continue  
        
        missing=[
            field for field in REQUIRED_FIELDS[func_name]
            if field not in args
        ]

        if missing:
            conversation.append({"role":"user","content":f"Missing required fields: {missing}"})
            print("⚠️ Argument not given — retrying...")
            print(f"No. of tries= {i+1}")
            continue 

        if verbose:
            print(f"Function called= {func_name}")
            print(f"arguments= {args}")
        
        # Get allowed parameters from schema
        allowed_params = tools_map[func_name]["parameters"]["properties"].keys()

        # Filter only valid args
        filtered_args = {
            key: value for key, value in args.items()
            if key in allowed_params
        }
        func=FXN[func_name]
        result= func(**filtered_args)

        conversation.append({"role":"user","content":f"Observation: {result}"})


content=input("Enter the Prompt:\n") 
run_agent(content)