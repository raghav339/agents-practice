from openai import OpenAI
import requests
import json

API_KEY="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"
WEATHER_API_KEY="bd25756d504440ca839180652252707"
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

FREE_MODEL="llama-3.3-70b-versatile"

inp=input("Enter weather if you want to check weather else enter maths if you want to evaluate math expression: \n")
if(inp=="weather"):
    city=input("enter name of city for which you want weather \n")
    content=f"What is weather of {city}"
elif (inp=="maths"):
    expression=input("enter mathematical expression \n")
    content=f"Evaluate the expression : {expression}"
else:
    print("invalid input \n")
    exit()

conversation=[{
    "role":"system",
    "content":"You are an helpful assistant. Use tools wto find information. After receiving tool results, use the results to give complete answer using everthing present in reults."
},{
    "role":"user",
    "content":content
}]

def get_weather(city):
    try:
        res=requests.get(f"https://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}")
        if res.status_code==200:
            data=res.json()
            if "error" in data:
                return f"Could not find weather for {city}. Reason: {data['error']['message']}"

            current = data.get("current", {})
            temp = current.get("temp_c", "error")
            condn = current.get("condition", {}).get("text", "error")
            result={
                "temp_c":temp,
                "condition":condn
            }
            return json.dumps(result)
        return json.dumps({"error":"Page not found for query"})
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

tools=[
    {
        "type":"function",
        "function":{
            "name":"get_weather",
            "description":"Get cuurent weather for a city.Returns temperature and condition",
            "parameters":{
                "type":"object",
                "properties":{
                    "city":{"type":"string","description":"City Name ,eg: Tokyo"}
                },
                "required":["city"]
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
FNC={"get_weather":get_weather,"calculate":calculate}

conversation=[{
    "role":"system",
    "content":"You are an helpful assistant. Use tools wto find information. After receiving tool results, use the results to give complete answer using everthing present in reults."
},{
    "role":"user",
    "content":content
}]

for _ in range(3):
    res=client.chat.completions.create(
        model=FREE_MODEL,
        messages=conversation,
        max_tokens=100,
        temperature=0.0,
        tools=tools
    )
    finish=res.choices[0].finish_reason
    msg=res.choices[0].message
    print(finish)
    print(msg.content)
    if msg.tool_calls is not None:
        print(msg.tool_calls)
        if msg.tool_calls[0].function.name != "" and msg.tool_calls[0].function.arguments:
            if msg.tool_calls[0].function.name== "get_weather" and "city" not in msg.tool_calls[0].function.arguments:
                conversation.append({
                    "role": "assistant",
                    "content": "Which city?"
                })
                continue

            if msg.tool_calls[0].function.name == "calculate" and "expression" not in msg.tool_calls[0].function.arguments:
                conversation.append({
                    "role": "assistant",
                    "content": "Please provide an expression to calculate."
                })
                continue
            func=FNC[msg.tool_calls[0].function.name]
            result=func(**json.loads(msg.tool_calls[0].function.arguments))
            conversation.append(msg)
            conversation.append({"role":"tool","tool_call_id":msg.tool_calls[0].id,"content":result})
            for _ in range(3):
                res=client.chat.completions.create(
                model=FREE_MODEL,
                messages=conversation,
                max_tokens=100,
                temperature=0.0,
                tools=tools
                )
                content=res.choices[0].message.content
                if content is not None:
                    print(content)
                    exit()
            print("Try again")
    else:
        continue