import requests
import json
import os

# 读取环境变量
api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    raise RuntimeError("请先设置环境变量 DEEPSEEK_API_KEY")

url = "https://api.deepseek.com/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# 对话历史
messages = [{"role": "system", "content": "你是一个有帮助的助手，回答简洁。"}]

print("\n=== 流式 AI 对话已启动（输入 quit 退出）===\n")

while True:
    user_input = input("你：")
    if user_input.strip().lower() in ("quit", "exit", "q"):
        print("再见！")
        break

    messages.append({"role": "user", "content": user_input})

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
        "stream": True
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60, stream=True)

        if response.status_code != 200:
            print(f"请求失败，状态码：{response.status_code}")
            print(response.text)
            continue

        print("AI：", end="", flush=True)
        full_response = ""

        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]  # 去掉 "data: " 前缀
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                    delta = chunk["choices"][0]["delta"]
                    if "content" in delta:
                        token = delta["content"]
                        print(token, end="", flush=True)
                        full_response += token
                except json.JSONDecodeError:
                    continue

        print()  # 换行
        messages.append({"role": "assistant", "content": full_response})

    except Exception as e:
        print(f"发生错误：{e}")

