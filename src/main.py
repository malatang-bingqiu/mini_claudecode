import ollama

# 定义ANSI转义码，会改变后续的控制台打印颜色
RESET = '\033[0m'
RED = '\033[91m'
GREEN = '\033[92m'
BLUE = '\033[94m'
YELLOW = '\033[93m'

'''
生成与提供的模型进行聊天的下一条消息。这是一个流式端点，因此将有一系列响应。可以通过设置 "stream": false 来禁用流式传输。最终的响应对象将包含统计信息和请求的其他数据。

参数
model: （必需）模型名称
messages: 聊天的消息，可以用于保持聊天记忆
tools: 如果支持，模型可以使用的工具。需要将 stream 设置为 false
message 对象具有以下字段：

role: 消息的角色，可以是 system、user、assistant 或 tool
content: 消息的内容
images（可选）: 要包含在消息中的图像列表（适用于多模态模型，如 llava）
tool_calls（可选）: 模型希望使用的工具列表
高级参数（可选）：

format: 返回响应的格式。目前唯一接受的值是 json
options: 文档中列出的其他模型参数，如 Modelfile 中的 temperature
stream: 如果设置为 false，响应将作为单个响应对象返回，而不是一系列对象
keep_alive: 控制请求后模型在内存中保持加载的时间（默认：5m）
'''

def main():
    history_message = [{
        "role": "system",
        "content": "你是一个python高手，配合我练习开发技能，让我早日能转行成功！"
        }]
    i = 0
    while True:
        i += 1
        user_input = input(f"{RESET}jerry:").strip()
        if user_input in ('/q', 'exit'):
            break
        if user_input == '':
            continue
        history_message.append({'role': 'user', "content": f"{user_input}"})
        print(f"{RED}这是第{i}次循环")
        response = ollama.chat(model='qwen2.5:7b', messages=history_message)
        print(f"{GREEN}{response.message.content}")
        print("*"*10)
        history_message.append(response.message)

if __name__ =='__main__':
    print("第2节：手搓调用循环ollama接口")
    main()