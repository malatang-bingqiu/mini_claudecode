def agent_loop(user_input, messages):
    {}

def main():
    print("coding开始运行\n")
    messages = [{
        "role": "system",
        "content": f"你是一个python代码专家，帮助用户解决代码问题，遇到不会的就说不知道，不要编造。"
    }]
    while True:
        user_input = input("用户：").strip()
        if user_input.lower()in ("exit", "quit"):
            break
        if user_input:
            reply = agent_loop(user_input,messages)
            print(f"\n助手：{reply}\n{'***'*10}")

if __name__ == "__main__":
    main()