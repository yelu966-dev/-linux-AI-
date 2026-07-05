import requests
import json
import os
import wave
import time
import asyncio
import sounddevice as sd
import soundfile as sf
import numpy as np
import edge_tts

from vosk import Model, KaldiRecognizer

# ======================================
# 配置
# ======================================

WAKE_WORDS = [
    "你好小车",
    "你好校车",
    "你好晓车",
    "小车你好",
    "你好修车"
] # 唤醒次 预测误识别

EXIT_WORDS = [
    "再见小车",
    "拜拜小车",
    "退出程序",
    "关闭小车",
    "再见修车"
] # 结束词 预测误识别

LISTEN_TIMEOUT = 30 # 监听超时时间（30秒）
MODEL_PATH = ("vosk-model-small-cn-0.22") # 语音模型路径
MIC_DEVICE = 1 # 声卡

VOICE = "zh-CN-XiaoxiaoNeural"
# 可换：
# zh-CN-YunyangNeural 男声
# zh-CN-XiaoyiNeural 女声


# ======================================
# DeepSeek API
# ======================================

api_key = os.getenv("DEEPSEEK_API_KEY") #API Key 需添加到环境变量中 ~/.bashrc 
# 直接写死有泄露风险

if not api_key:
    raise RuntimeError("请先设置环境变量 ""DEEPSEEK_API_KEY")

url = ("https://api.deepseek.com/"
       "chat/completions")

headers = {
    "Content-Type":
    "application/json",
    "Authorization":
    f"Bearer {api_key}"
}


# ======================================
# 加载语音模型
# ======================================

print("加载语音模型...")
model = Model(MODEL_PATH)
print("加载完成")

# ======================================
# Edge-TTS（稳定版）
# 自动重试 + mpg123
# ======================================

async def speak_async(text):
    if not text:
        return

    text = text.replace('"', '')
    text = text.replace('\n', ' ')

    output_file = "/home/sunrise/car_ai/reply.mp3"

    # =====================
    # Edge-TTS
    # =====================

    for retry in range(3):

        try:
            print(f"TTS连接 "
                f"({retry+1}/3)")

            communicate = edge_tts.Communicate(text=text, voice=VOICE)
            await communicate.save(output_file)

            if not os.path.exists(output_file):
                raise Exception("mp3 未生成")
            
            print("TTS成功")
            os.system(f"mpg123 -q "
                f"{output_file}")
            return

        except Exception as e:
            print(f"Edge-TTS生成失败 "
                f"({retry+1}/3): ")
            await asyncio.sleep(2)

    # =====================
    # 三次失败 -> 本地机器人音
    # =====================
    print( "切换离线机器人语音" )
    try:
        os.system(
            f'espeak -v zh '
            f'"{text}"'
        ) # 需提前下载

    except Exception as e:
        print("离线TTS失败:")

def speak(text):
    try:
        asyncio.run(speak_async(text))

    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(speak_async(text))

# ======================================
# 自动录音（检测说话结束）
# ======================================

def record_until_silence(
        filename="test.wav",
        samplerate=16000,
        silence_threshold=0.1,
        silence_duration=1.5,
        max_duration=10):

    print("等待说话...")

    audio_data = []
    silence_counter = 0
    speaking = False
    chunk_size = 1024
    max_chunks = int(
        max_duration *
        samplerate /
        chunk_size
    )

    silence_limit = int(
        silence_duration *
        samplerate /
        chunk_size
    )

    with sd.InputStream(
            device=MIC_DEVICE,
            samplerate=samplerate,
            channels=1,
            dtype='float32'
    ) as stream:

        for _ in range(max_chunks):
            chunk, overflowed = stream.read(chunk_size)
            volume = np.abs(chunk).mean()
            audio_data.append(chunk)

            # 检测讲话
            if volume > silence_threshold:
                if not speaking:
                    print("检测到讲话...")
                speaking = True
                silence_counter = 0
            else:
                if speaking:
                    silence_counter += 1

            # 停止讲话
            if speaking and silence_counter > silence_limit:
                print("检测到停止说话")
                break

    audio_data = np.concatenate(audio_data,axis=0)
    sf.write(filename,audio_data,samplerate)
    print("录音完成")

# ======================================
# 语音识别
# ======================================

def speech_to_text(audio_file):
    wf = wave.open(audio_file,"rb")
    rec = KaldiRecognizer(model,wf.getframerate())
    all_text = []

    while True:
        data = wf.readframes(4000)

        if len(data) == 0:
            break

        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result["text"]
            if text:
                all_text.append(text)

    final_result = json.loads(rec.FinalResult())
    final_text = final_result["text"]

    if final_text:
        all_text.append(final_text)
    return " ".join(all_text).strip()

# ======================================
# 对话历史
# ======================================

messages = [
    {
        "role":
        "system",
        "content":
        (
            "你是一个轮腿机器人助手，"
            "回答自然、简洁,不要有特殊符号。"
        )
    }
] # 提示词

# ======================================
# 主程序
# ======================================

print("\n等待唤醒词：")
print("你好小车")

warm = 1
while True:
    try:
        # ======================
        # 等待唤醒
        # ======================

        record_until_silence()
        text = speech_to_text("test.wav")

        if not text:
            continue
        print("识别：",text)

        normalized_text = text.replace(" ", "")
        is_wakeup = any(word in normalized_text for word in WAKE_WORDS)

        if not is_wakeup:
            continue
        print("已唤醒")
        warm = 1
        os.system("mpg123 please_say.mp3")
        last_active = time.time()

        # ======================
        # 连续对话
        # ======================

        while True:
            if time.time() - last_active > LISTEN_TIMEOUT:
                print("下次再见")
                os.system("mpg123 bye_next_time.mp3")
                break

            if time.time() - last_active > (LISTEN_TIMEOUT - 10) and warm == 1:
                warm = 2
                print("你好，还在吗")
                os.system("mpg123 hello_are_you_ok.mp3")

            record_until_silence()
            user_input = speech_to_text("test.wav")

            if not user_input:
                continue

            print("你说：",user_input)
            normalized_input = user_input.replace( " ","") # 去空格

            # ==========
            # 退出程序
            # ==========
            is_exit = any( word in normalized_input for word in EXIT_WORDS)

            if is_exit:
                print("收到退出指令")
                os.system("mpg123 byebye.mp3")
                raise KeyboardInterrupt

            last_active = time.time()
            messages.append({ "role": "user","content": user_input})
            payload = {"model": "deepseek-chat", "messages": messages, "temperature": 0.7, "max_tokens": 512, "stream": True}
            response = requests.post( url, headers=headers, json=payload, timeout=15, stream=True )

            if response.status_code != 200:
                print( "请求失败：", response.status_code )
                continue

            print( "AI：",  end="",  flush=True )
            full_response = ""

            for line in response.iter_lines():
                if line:
                    line = line.decode( "utf-8" )

                    if line.startswith("data: "):
                        line = line[6:]

                    if line == "[DONE]":
                        break

                    try:
                        chunk =  json.loads(line)
                        delta =  chunk["choices"][0]["delta"]

                        if  "content" in delta:
                            token =  delta["content"]
                            print(token, end="", flush=True)
                            full_response += token # 低token
                    except:
                        pass
            print("\n")

            messages.append({
                "role":
                "assistant",
                "content":
                full_response})
            
            speak(full_response)
            last_active = time.time()

    except KeyboardInterrupt:

        print("\n退出程序" )
        break

    except Exception as e:
        print("发生错误：",e)
