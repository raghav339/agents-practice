from openai import OpenAI
import requests
import json
import os
import subprocess
import sys

API_KEY="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"

content=input("Enter the Prompt:\n")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

FREE_MODEL="llama-3.3-70b-versatile"

tools=[
  {
    "type": "function",
    "function": {
      "name": "read_file",
      "description": "Read the contents of a file from a SAFE workspace directory only.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "Relative path inside /workspace (e.g., notes.txt, folder/file.py)"
          }
        },
        "required": ["path"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "write_file",
      "description": "Write content to a file inside the SAFE workspace directory. Cannot overwrite system files.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "Relative path inside /workspace"
          },
          "content": {
            "type": "string",
            "description": "Content to write into the file"
          },
          "mode": {
            "type": "string",
            "enum": ["overwrite", "append"],
            "description": "Write mode: overwrite replaces file, append adds to file"
          }
        },
        "required": ["path", "content"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "list_files",
      "description": "List all files and folders inside a SAFE workspace directory.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "Relative path inside /workspace (default: root)"
          }
        },
        "required": ["path"]
      }
    }
  },
 {
  "type": "function",
  "function": {
    "name": "run_code",
    "description": "Execute a Python file that exists in the workspace.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "The relative path to the .py file to execute (e.g., 'script.py')"
        }
      },
      "required": ["path"]
    }
  }
 },
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
  }
]

REQUIRED_FIELDS={}
for tool in tools:
    REQUIRED_FIELDS[tool["function"]["name"]]=tool["function"]["parameters"]["required"]

def read_file(path):
    try:
        if os.path.getsize(path) > 1_000_000:
            return json.dumps({"error": "File too large"})
        
        with open(path,"r",encoding="utf-8") as f:
            content=f.read()
        return json.dumps({"path":path,"content":content[:3000],"truncated":len(content)>3000})    
    except Exception as e:
        return json.dumps({"error":str(e)})
    
def write_file(content, path, mode="overwrite"):
    try:
        file_mode = "w" if mode == "overwrite" else "a"
        
        dir = os.path.dirname(path)
        if dir:
            os.makedirs(dir, exist_ok=True)

        with open(path, file_mode, encoding="utf-8") as f:
            f.write(content)

        return json.dumps({"status": "success", "path": path, "bytes": len(content)})
    except Exception as e:
        return json.dumps({"error": str(e)})
    
def list_files(path="."):
    try:
        items=sorted(os.listdir(path))
        return json.dumps({"path":path,"files":items[:50]})
    except Exception as e:
        return json.dumps({"error":str(e)})

def run_code(path,timeout=10):
    try:
        # 1. Basic safety: ensure they are running a .py file
        if not path.endswith(".py"):
            return json.dumps({"error": "Only .py files can be executed."})

        # 2. Run the file using the current Python interpreter
        # We don't use -c because we are running a file, not a string
        result = subprocess.run(
            [sys.executable, path], 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )

        return json.dumps({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        })
    except Exception as e:
        return json.dumps({"error": str(e)})
    
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


SYSTEM_PROMPT='''
You are a helpful assistant that can:
1. Write and execute Python code
2. Search information using Wikipedia

You have access to these tools:
- write_file
- read_file
- run_code
- wiki_search
- list_files

## Rules for coding tasks
- When the user asks for code:
  1. Create a .py file using write_file
  2. Read the file using read_file to confirm content
  3. Execute the code using run_code
  4. If there is an error, fix the code and retry
  5. Provide the program's output as the final answer. If the logic requires user input, the agent must replace input() calls with hardcoded test values or arguments within the code to ensure the script runs to completion without hanging.

- Limit retries to a maximum of 3 attempts
- Always explain what you are doing

## Rules for search tasks
- Use wiki_search for factual queries
- If the tool fails, respond with a fallback explanation
#IMPORTANT:
- If a question requires external knowledge, you MUST call a tool.
- Do NOT answer directly.
- Do NOT return JSON as text.
- ALWAYS use tool_calls format.

#When using a tool, respond ONLY with a tool call.

#Example:
- User: Who is Newton?

#You MUST respond with:
- (use wiki_search tool with query="Isaac Newton")


## General Rules
- Do not overwrite important files
- Do not execute unsafe or harmful code
- Always validate tool outputs before proceeding
- Always call one tool at a time
- When you decide to use a tool, do NOT provide any conversational text. ONLY provide the tool call. Once you have the tool output, you can then explain the results to the user.
'''

conversation=[
    {"role":"system","content":SYSTEM_PROMPT},
    {"role":"user", "content":content}
]

FNC={
    "write_file":write_file,
    "read_file":read_file,
    "list_files":list_files,
    "run_code":run_code,
    "wiki_search":wiki_search
}
for _ in range(5):  # Increased range to allow for thought + tool + response
    res = client.chat.completions.create(
        model=FREE_MODEL,
        temperature=0.0,
        max_tokens=500,
        messages=conversation,
        tools=tools
    )

    msg = res.choices[0].message
    
    # 1. Append the assistant's message (whether it has tool_calls or content)
    conversation.append(msg)

    if msg.tool_calls:
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            # Validation logic
            if func_name not in FNC:
                result = json.dumps({"error": f"Tool {func_name} not found"})
            else:
                # Check for missing required fields
                required = REQUIRED_FIELDS.get(func_name, [])
                missing = [field for field in required if field not in args]
                
                if missing:
                    result = json.dumps({"error": f"Missing fields: {missing}"})
                else:
                    # 2. Execute the actual function
                    print(f"--- Calling tool: {func_name} with {args} ---")
                    func = FNC[func_name]
                    result = func(**args)

            # 3. Append the tool output to conversation
            conversation.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": func_name,
                "content": result
            })
    else:
        # If no tool calls, the model has provided a final answer
        print("\nFinal Response:")
        print(msg.content)
        break